from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path, PurePosixPath
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

from plugin.backend.app.action_tape import (
    ACTION_TAPE_MEDIA_TYPE,
    ActionTapeError,
    validate_action_tape,
)
from plugin.backend.app.database import PROJECT_ROOT
from plugin.backend.app.ids import new_id

MANIFEST_SCHEMA_VERSION = "run-manifest@1.0.0"
BUNDLE_WRITER_VERSION = "run-artifact-writer@1.0.0"
BUNDLE_VERIFIER_VERSION = "run-bundle-verifier@1.0.0"
MANIFEST_NAME = "manifest.json"
_REQUIRED_ROLE_BY_POLICY = {
    "action_tape_required": "action_tape",
    "trace_required": "trace",
    "screenshot_required": "screenshot",
    "network_required": "network",
    "console_required": "console",
}


class RunArtifactBundleError(Exception):
    pass


def _canonical(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _schema_validator() -> Draft202012Validator:
    schema_path = PROJECT_ROOT / "schemas" / "run-bundles" / "v1" / "run_manifest.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _safe_relative_path(value: str) -> PurePosixPath:
    if not value or "\\" in value or "\x00" in value or ":" in value.split("/", 1)[0]:
        raise RunArtifactBundleError("BUNDLE_PATH_INVALID")
    path = PurePosixPath(value)
    if path.is_absolute() or path.drive or any(part in {"", ".", ".."} for part in path.parts):
        raise RunArtifactBundleError("BUNDLE_PATH_INVALID")
    if path.as_posix() == MANIFEST_NAME:
        raise RunArtifactBundleError("BUNDLE_MANIFEST_RESERVED")
    return path


def _contained_path(root: Path, relative: str, *, must_exist: bool) -> Path:
    safe = _safe_relative_path(relative)
    root_resolved = root.resolve()
    candidate = root.joinpath(*safe.parts)
    current = root
    for part in safe.parts:
        current = current / part
        if current.exists() and current.is_symlink():
            raise RunArtifactBundleError("BUNDLE_SYMLINK_FORBIDDEN")
    resolved = candidate.resolve(strict=must_exist)
    if not resolved.is_relative_to(root_resolved):
        raise RunArtifactBundleError("BUNDLE_PATH_ESCAPE")
    return candidate


def manifest_bundle_hash(manifest: dict[str, Any]) -> str:
    content = {key: value for key, value in manifest.items() if key != "bundle_hash"}
    return _sha256(_canonical(content))


def verify_run_artifact_bundle(bundle_dir: Path) -> dict[str, Any]:
    """Independently verify a finalized or staging Bundle without database state."""
    if bundle_dir.is_symlink() or not bundle_dir.is_dir():
        raise RunArtifactBundleError("BUNDLE_DIRECTORY_INVALID")
    manifest_path = bundle_dir / MANIFEST_NAME
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise RunArtifactBundleError("BUNDLE_MANIFEST_MISSING")
    try:
        decoded = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RunArtifactBundleError("BUNDLE_MANIFEST_INVALID_JSON") from error
    if not isinstance(decoded, dict):
        raise RunArtifactBundleError("BUNDLE_MANIFEST_INVALID_JSON")
    manifest = cast(dict[str, Any], decoded)
    errors = sorted(_schema_validator().iter_errors(manifest), key=lambda item: list(item.path))
    if errors:
        raise RunArtifactBundleError(f"BUNDLE_MANIFEST_SCHEMA_INVALID:{errors[0].json_path}")
    if manifest_bundle_hash(manifest) != manifest["bundle_hash"]:
        raise RunArtifactBundleError("BUNDLE_HASH_MISMATCH")

    artifacts = manifest["artifacts"]
    ids = [item["artifact_id"] for item in artifacts]
    paths = [item["relative_path"] for item in artifacts]
    if len(ids) != len(set(ids)):
        raise RunArtifactBundleError("BUNDLE_ARTIFACT_ID_DUPLICATE")
    if len(paths) != len(set(paths)):
        raise RunArtifactBundleError("BUNDLE_ARTIFACT_PATH_DUPLICATE")

    expected_files = {MANIFEST_NAME, *paths}
    actual_files: set[str] = set()
    for path in bundle_dir.rglob("*"):
        if path.is_symlink():
            raise RunArtifactBundleError("BUNDLE_SYMLINK_FORBIDDEN")
        if path.is_file():
            actual_files.add(path.relative_to(bundle_dir).as_posix())
    if actual_files != expected_files:
        raise RunArtifactBundleError("BUNDLE_FILE_SET_MISMATCH")

    artifact_ids = set(ids)
    for artifact in artifacts:
        path = _contained_path(bundle_dir, artifact["relative_path"], must_exist=True)
        if not path.is_file():
            raise RunArtifactBundleError("BUNDLE_ARTIFACT_MISSING")
        content = path.read_bytes()
        if not content:
            raise RunArtifactBundleError("BUNDLE_ARTIFACT_EMPTY")
        if len(content) != artifact["size_bytes"]:
            raise RunArtifactBundleError("BUNDLE_ARTIFACT_SIZE_MISMATCH")
        if _sha256(content) != artifact["sha256"]:
            raise RunArtifactBundleError("BUNDLE_ARTIFACT_HASH_MISMATCH")
        if artifact["role"] == "action_tape":
            try:
                events = validate_action_tape(content, expected_run_id=manifest["run_id"])
            except ActionTapeError as error:
                raise RunArtifactBundleError(f"BUNDLE_ACTION_TAPE_INVALID:{error}") from error
            if any(event["result_id"] not in manifest["result_ids"] for event in events):
                raise RunArtifactBundleError("BUNDLE_ACTION_TAPE_RESULT_MISMATCH")
            references = {
                reference for event in events for reference in event["evidence_artifact_ids"]
            }
            if not references.issubset(artifact_ids):
                raise RunArtifactBundleError("BUNDLE_ACTION_TAPE_REFERENCE_MISSING")

    roles = {item["role"] for item in artifacts}
    for policy_name, role in _REQUIRED_ROLE_BY_POLICY.items():
        if manifest["evidence_policy"][policy_name] and role not in roles:
            raise RunArtifactBundleError(f"BUNDLE_REQUIRED_ARTIFACT_MISSING:{role}")
    return manifest


class RunArtifactBundleWriter:
    """Write one self-contained Run Bundle and promote it only after full verification."""

    def __init__(self, artifact_root: Path, manifest_fields: dict[str, Any]) -> None:
        self.artifact_root = artifact_root
        self.manifest_fields = dict(manifest_fields)
        self.run_id = str(self.manifest_fields.get("run_id", ""))
        if not self.run_id:
            raise RunArtifactBundleError("BUNDLE_RUN_ID_REQUIRED")
        self.final_dir = artifact_root / self.run_id
        self.staging_dir = artifact_root / f".{self.run_id}.staging"
        self._artifacts: list[dict[str, Any]] = []
        self._started = False

    def start(self) -> None:
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        if self.final_dir.exists() or self.staging_dir.exists():
            raise RunArtifactBundleError("BUNDLE_PATH_CONFLICT")
        self.staging_dir.mkdir()
        self._started = True

    def add_bytes(
        self,
        relative_path: str,
        content: bytes,
        *,
        role: str,
        mime_type: str,
        source_record_ids: list[str],
        redaction_status: str,
        artifact_id: str | None = None,
    ) -> dict[str, Any]:
        if not self._started:
            raise RunArtifactBundleError("BUNDLE_NOT_STARTED")
        if not content:
            raise RunArtifactBundleError("BUNDLE_ARTIFACT_EMPTY")
        if not source_record_ids or len(source_record_ids) != len(set(source_record_ids)):
            raise RunArtifactBundleError("BUNDLE_SOURCE_RECORD_IDS_INVALID")
        if relative_path in {item["relative_path"] for item in self._artifacts}:
            raise RunArtifactBundleError("BUNDLE_ARTIFACT_PATH_DUPLICATE")
        target = _contained_path(self.staging_dir, relative_path, must_exist=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        record = {
            "artifact_id": artifact_id or new_id("ART"),
            "role": role,
            "relative_path": _safe_relative_path(relative_path).as_posix(),
            "mime_type": mime_type,
            "size_bytes": len(content),
            "sha256": _sha256(content),
            "source_record_ids": list(source_record_ids),
            "redaction_status": redaction_status,
            "integrity_status": "verified",
        }
        self._artifacts.append(record)
        return dict(record)

    def add_file(self, source: Path, relative_path: str, **metadata: Any) -> dict[str, Any]:
        if source.is_symlink() or not source.is_file():
            raise RunArtifactBundleError("BUNDLE_SOURCE_FILE_INVALID")
        return self.add_bytes(relative_path, source.read_bytes(), **metadata)

    def add_action_tape(
        self,
        relative_path: str,
        content: bytes,
        *,
        source_record_ids: list[str],
        artifact_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            validate_action_tape(content, expected_run_id=self.run_id)
        except ActionTapeError as error:
            raise RunArtifactBundleError(f"BUNDLE_ACTION_TAPE_INVALID:{error}") from error
        return self.add_bytes(
            relative_path,
            content,
            role="action_tape",
            mime_type=ACTION_TAPE_MEDIA_TYPE,
            source_record_ids=source_record_ids,
            redaction_status="verified",
            artifact_id=artifact_id,
        )

    def finalize(self) -> dict[str, Any]:
        if not self._started:
            raise RunArtifactBundleError("BUNDLE_NOT_STARTED")
        manifest = {
            **self.manifest_fields,
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "artifacts": sorted(self._artifacts, key=lambda item: item["relative_path"]),
        }
        manifest["bundle_hash"] = manifest_bundle_hash(manifest)
        promoted = False
        try:
            (self.staging_dir / MANIFEST_NAME).write_bytes(_canonical(manifest) + b"\n")
            verified = verify_run_artifact_bundle(self.staging_dir)
            os.replace(self.staging_dir, self.final_dir)
            promoted = True
            verify_run_artifact_bundle(self.final_dir)
        except Exception:
            if promoted and self.final_dir.exists():
                shutil.rmtree(self.final_dir)
            self.abort()
            raise
        self._started = False
        return verified

    def abort(self) -> None:
        if self.staging_dir.exists():
            shutil.rmtree(self.staging_dir)
        self._started = False
