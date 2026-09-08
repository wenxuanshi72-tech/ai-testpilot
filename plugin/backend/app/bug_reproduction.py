from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

from plugin.backend.app.action_tape import validate_action_tape
from plugin.backend.app.database import PROJECT_ROOT
from plugin.backend.app.run_artifact_bundles import verify_run_artifact_bundle

REPRODUCTION_RESULT_VERSION = "reproduction-result@1.0.0"
REPRODUCTION_OBSERVATION_VERSION = "reproduction-observation@1.0.0"
REPRODUCTION_PACKAGE_VERSION = "bug-reproduction-package@1.0.0"
PACKAGE_MANIFEST_NAME = "package-manifest.json"
REPRODUCTION_RESULT_NAME = "reproduction-result.json"
SENSITIVE_MARKERS = (
    b"test1234",
    b"authorization: bearer",
    b"deepseek_api_key",
    b"sqlite:///",
)


class BugReproductionError(Exception):
    pass


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _validator(filename: str) -> Draft202012Validator:
    path = PROJECT_ROOT / "schemas" / "reproduction" / "v1" / filename
    schema = json.loads(path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def _validate(payload: dict[str, Any], validator: Draft202012Validator, error_code: str) -> None:
    errors = sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        raise BugReproductionError(f"{error_code}:{errors[0].json_path}")


def _read_json(path: Path, error_code: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise BugReproductionError(error_code)
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BugReproductionError(error_code) from error
    if not isinstance(decoded, dict):
        raise BugReproductionError(error_code)
    return cast(dict[str, Any], decoded)


def _artifact_for_result(
    bundle_dir: Path, manifest: dict[str, Any], *, role: str, result_id: str
) -> tuple[dict[str, Any], bytes]:
    matches = [
        artifact
        for artifact in manifest["artifacts"]
        if artifact["role"] == role and result_id in artifact["source_record_ids"]
    ]
    if len(matches) != 1:
        raise BugReproductionError(f"REPRODUCTION_{role.upper()}_ARTIFACT_INVALID")
    artifact = matches[0]
    path = bundle_dir / Path(*str(artifact["relative_path"]).split("/"))
    return artifact, path.read_bytes()


def _observation(bundle_dir: Path, manifest: dict[str, Any], result_id: str) -> dict[str, Any]:
    _, content = _artifact_for_result(bundle_dir, manifest, role="result", result_id=result_id)
    try:
        decoded = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BugReproductionError("REPRODUCTION_OBSERVATION_JSON_INVALID") from error
    if not isinstance(decoded, dict):
        raise BugReproductionError("REPRODUCTION_OBSERVATION_JSON_INVALID")
    observation = cast(dict[str, Any], decoded)
    if content != _canonical(observation) + b"\n":
        raise BugReproductionError("REPRODUCTION_OBSERVATION_NOT_CANONICAL")
    _validate(
        observation,
        _validator("reproduction_observation.schema.json"),
        "REPRODUCTION_OBSERVATION_SCHEMA_INVALID",
    )
    if observation["result_id"] != result_id or result_id not in manifest["result_ids"]:
        raise BugReproductionError("REPRODUCTION_RESULT_OWNERSHIP_MISMATCH")
    if manifest["executor"] not in {observation["executor"], "mixed"}:
        raise BugReproductionError("REPRODUCTION_EXECUTOR_MISMATCH")
    return observation


def _tape_facts(
    bundle_dir: Path, manifest: dict[str, Any], result_id: str
) -> tuple[str, list[str]]:
    artifact, content = _artifact_for_result(
        bundle_dir, manifest, role="action_tape", result_id=result_id
    )
    events = validate_action_tape(
        content,
        expected_run_id=str(manifest["run_id"]),
        expected_result_id=result_id,
    )
    references = sorted(
        {reference for event in events for reference in event["evidence_artifact_ids"]}
    )
    artifact_ids = {item["artifact_id"] for item in manifest["artifacts"]}
    if not references or not set(references).issubset(artifact_ids):
        raise BugReproductionError("REPRODUCTION_EVIDENCE_REFERENCE_INVALID")
    referenced_roles = {
        item["role"] for item in manifest["artifacts"] if item["artifact_id"] in references
    }
    if referenced_roles & {"result", "action_tape", "reproduction", "bug", "report"}:
        raise BugReproductionError("REPRODUCTION_EVIDENCE_ROLE_INVALID")
    return str(artifact["sha256"]), references


def _evaluate(source: dict[str, Any], reproduction: dict[str, Any]) -> str:
    identity = ("case_id", "case_version", "snapshot_id", "snapshot_hash", "expected", "executor")
    if any(source[field] != reproduction[field] for field in identity):
        raise BugReproductionError("REPRODUCTION_ORACLE_OR_VERSION_CHANGED")
    if source["status"] != "FAIL":
        raise BugReproductionError("REPRODUCTION_SOURCE_NOT_FAILED")
    if reproduction["status"] in {"BLOCKED", "SKIPPED"}:
        return "BLOCKED"
    if reproduction["status"] == "ERROR":
        return "ERROR"
    if reproduction["status"] == "FAIL" and reproduction["actual"] == source["actual"]:
        return "REPRODUCED"
    return "NOT_REPRODUCED"


def _require_source_link(
    source_manifest: dict[str, Any],
    reproduction_manifest: dict[str, Any],
    source_result_id: str,
) -> None:
    if source_manifest["trust_state"] not in {"executed", "verified"} or reproduction_manifest[
        "trust_state"
    ] not in {"executed", "verified"}:
        raise BugReproductionError("REPRODUCTION_RUN_NOT_EXECUTED")
    if source_manifest["run_id"] == reproduction_manifest["run_id"]:
        raise BugReproductionError("REPRODUCTION_RUN_NOT_INDEPENDENT")
    if reproduction_manifest.get("source_run") != {
        "run_id": source_manifest["run_id"],
        "result_id": source_result_id,
        "manifest_hash": source_manifest["bundle_hash"],
    }:
        raise BugReproductionError("REPRODUCTION_SOURCE_LINK_INVALID")


def _result_payload(
    *,
    bug_id: str,
    source_manifest: dict[str, Any],
    reproduction_manifest: dict[str, Any],
    source: dict[str, Any],
    reproduction: dict[str, Any],
    action_tape_hash: str,
    evidence_artifact_ids: list[str],
    completed_at: str,
) -> dict[str, Any]:
    status = _evaluate(source, reproduction)
    payload = {
        "schema_version": REPRODUCTION_RESULT_VERSION,
        "bug_id": bug_id,
        "source_run_id": source_manifest["run_id"],
        "source_result_id": source["result_id"],
        "source_manifest_hash": source_manifest["bundle_hash"],
        "reproduction_run_id": reproduction_manifest["run_id"],
        "reproduction_result_id": reproduction["result_id"],
        "case_id": source["case_id"],
        "case_version": source["case_version"],
        "snapshot_id": source["snapshot_id"],
        "snapshot_hash": source["snapshot_hash"],
        "oracle_unchanged": True,
        "status": status,
        "expected": source["expected"],
        "actual": reproduction["actual"],
        "evidence_artifact_ids": evidence_artifact_ids,
        "action_tape_hash": action_tape_hash,
        "reproduction_manifest_hash": reproduction_manifest["bundle_hash"],
        "determined_by": "deterministic_reproduction_runner",
        "completed_at": completed_at,
    }
    _validate(
        payload,
        _validator("reproduction_result.schema.json"),
        "REPRODUCTION_RESULT_SCHEMA_INVALID",
    )
    return payload


def _package_hash(manifest: dict[str, Any]) -> str:
    return _sha256(
        _canonical({key: value for key, value in manifest.items() if key != "package_hash"})
    )


def verify_bug_reproduction_package(package_dir: Path) -> dict[str, Any]:
    """Verify a copied package without database or mutable source directories."""
    if package_dir.is_symlink() or not package_dir.is_dir():
        raise BugReproductionError("REPRODUCTION_PACKAGE_DIRECTORY_INVALID")
    package_manifest = _read_json(
        package_dir / PACKAGE_MANIFEST_NAME, "REPRODUCTION_PACKAGE_MANIFEST_INVALID"
    )
    _validate(
        package_manifest,
        _validator("reproduction_package_manifest.schema.json"),
        "REPRODUCTION_PACKAGE_MANIFEST_SCHEMA_INVALID",
    )
    if _package_hash(package_manifest) != package_manifest["package_hash"]:
        raise BugReproductionError("REPRODUCTION_PACKAGE_HASH_MISMATCH")

    actual_files: set[str] = set()
    for path in package_dir.rglob("*"):
        if path.is_symlink():
            raise BugReproductionError("REPRODUCTION_PACKAGE_SYMLINK_FORBIDDEN")
        if path.is_file():
            actual_files.add(path.relative_to(package_dir).as_posix())
    expected_files = {
        PACKAGE_MANIFEST_NAME,
        *(item["relative_path"] for item in package_manifest["files"]),
    }
    if actual_files != expected_files:
        raise BugReproductionError("REPRODUCTION_PACKAGE_FILE_SET_MISMATCH")
    paths = [item["relative_path"] for item in package_manifest["files"]]
    if len(paths) != len(set(paths)) or PACKAGE_MANIFEST_NAME in paths:
        raise BugReproductionError("REPRODUCTION_PACKAGE_FILE_LIST_INVALID")
    for item in package_manifest["files"]:
        path = package_dir / Path(*str(item["relative_path"]).split("/"))
        content = path.read_bytes()
        if len(content) != item["size_bytes"] or _sha256(content) != item["sha256"]:
            raise BugReproductionError("REPRODUCTION_PACKAGE_MEMBER_HASH_INVALID")
        if any(marker in content.lower() for marker in SENSITIVE_MARKERS):
            raise BugReproductionError("REPRODUCTION_PACKAGE_SENSITIVE_CONTENT")

    source_dir = package_dir / str(package_manifest["source_bundle_path"])
    reproduction_dir = package_dir / str(package_manifest["reproduction_bundle_path"])
    source_manifest = verify_run_artifact_bundle(source_dir)
    reproduction_manifest = verify_run_artifact_bundle(reproduction_dir)
    result = _read_json(
        package_dir / str(package_manifest["reproduction_result_path"]),
        "REPRODUCTION_RESULT_INVALID",
    )
    _validate(
        result,
        _validator("reproduction_result.schema.json"),
        "REPRODUCTION_RESULT_SCHEMA_INVALID",
    )
    result_path = package_dir / str(package_manifest["reproduction_result_path"])
    if result_path.read_bytes() != _canonical(result) + b"\n":
        raise BugReproductionError("REPRODUCTION_RESULT_NOT_CANONICAL")
    _require_source_link(source_manifest, reproduction_manifest, str(result["source_result_id"]))
    source = _observation(source_dir, source_manifest, str(result["source_result_id"]))
    reproduction = _observation(
        reproduction_dir, reproduction_manifest, str(result["reproduction_result_id"])
    )
    tape_hash, references = _tape_facts(
        reproduction_dir, reproduction_manifest, str(result["reproduction_result_id"])
    )
    expected = _result_payload(
        bug_id=str(result["bug_id"]),
        source_manifest=source_manifest,
        reproduction_manifest=reproduction_manifest,
        source=source,
        reproduction=reproduction,
        action_tape_hash=tape_hash,
        evidence_artifact_ids=references,
        completed_at=str(result["completed_at"]),
    )
    if result != expected:
        raise BugReproductionError("REPRODUCTION_RESULT_FACT_MISMATCH")
    if (
        package_manifest["bug_id"] != result["bug_id"]
        or package_manifest["source_run_id"] != source_manifest["run_id"]
        or package_manifest["reproduction_run_id"] != reproduction_manifest["run_id"]
        or package_manifest["status"] != result["status"]
        or package_manifest["reproduction_result_hash"] != _sha256(_canonical(result) + b"\n")
    ):
        raise BugReproductionError("REPRODUCTION_PACKAGE_FACT_MISMATCH")
    return {"manifest": package_manifest, "reproduction_result": result}


class BugReproductionPackageWriter:
    def __init__(
        self,
        artifact_root: Path,
        *,
        bug_id: str,
        source_bundle_dir: Path,
        reproduction_bundle_dir: Path,
        source_result_id: str,
        reproduction_result_id: str,
        clock: Callable[[], str] = _timestamp,
    ) -> None:
        self.artifact_root = artifact_root
        self.bug_id = bug_id
        self.source_bundle_dir = source_bundle_dir
        self.reproduction_bundle_dir = reproduction_bundle_dir
        self.source_result_id = source_result_id
        self.reproduction_result_id = reproduction_result_id
        self.clock = clock

    def write(self) -> dict[str, Any]:
        source_manifest = verify_run_artifact_bundle(self.source_bundle_dir)
        reproduction_manifest = verify_run_artifact_bundle(self.reproduction_bundle_dir)
        _require_source_link(source_manifest, reproduction_manifest, self.source_result_id)
        source = _observation(self.source_bundle_dir, source_manifest, self.source_result_id)
        reproduction = _observation(
            self.reproduction_bundle_dir, reproduction_manifest, self.reproduction_result_id
        )
        tape_hash, references = _tape_facts(
            self.reproduction_bundle_dir, reproduction_manifest, self.reproduction_result_id
        )
        result = _result_payload(
            bug_id=self.bug_id,
            source_manifest=source_manifest,
            reproduction_manifest=reproduction_manifest,
            source=source,
            reproduction=reproduction,
            action_tape_hash=tape_hash,
            evidence_artifact_ids=references,
            completed_at=self.clock(),
        )

        basename = f"{self.bug_id.lower()}--{reproduction_manifest['run_id'].lower()}"
        final_dir = self.artifact_root / basename
        staging_dir = self.artifact_root / f".{basename}.staging"
        if final_dir.exists() or staging_dir.exists():
            raise BugReproductionError("REPRODUCTION_PACKAGE_PATH_CONFLICT")
        self.artifact_root.mkdir(parents=True, exist_ok=True)
        try:
            staging_dir.mkdir()
            shutil.copytree(self.source_bundle_dir, staging_dir / "source-run")
            shutil.copytree(self.reproduction_bundle_dir, staging_dir / "reproduction-run")
            result_path = staging_dir / REPRODUCTION_RESULT_NAME
            result_path.write_bytes(_canonical(result) + b"\n")
            files = []
            for path in sorted(staging_dir.rglob("*")):
                if path.is_symlink():
                    raise BugReproductionError("REPRODUCTION_PACKAGE_SYMLINK_FORBIDDEN")
                if path.is_file():
                    content = path.read_bytes()
                    files.append(
                        {
                            "relative_path": path.relative_to(staging_dir).as_posix(),
                            "size_bytes": len(content),
                            "sha256": _sha256(content),
                        }
                    )
            manifest = {
                "format_version": REPRODUCTION_PACKAGE_VERSION,
                "bug_id": self.bug_id,
                "status": result["status"],
                "source_run_id": source_manifest["run_id"],
                "reproduction_run_id": reproduction_manifest["run_id"],
                "source_bundle_path": "source-run",
                "reproduction_bundle_path": "reproduction-run",
                "reproduction_result_path": REPRODUCTION_RESULT_NAME,
                "reproduction_result_hash": _sha256(result_path.read_bytes()),
                "files": files,
            }
            manifest["package_hash"] = _package_hash(manifest)
            _validate(
                manifest,
                _validator("reproduction_package_manifest.schema.json"),
                "REPRODUCTION_PACKAGE_MANIFEST_SCHEMA_INVALID",
            )
            (staging_dir / PACKAGE_MANIFEST_NAME).write_bytes(_canonical(manifest) + b"\n")
            verify_bug_reproduction_package(staging_dir)
            os.replace(staging_dir, final_dir)
            verified = verify_bug_reproduction_package(final_dir)
        except Exception:
            shutil.rmtree(staging_dir, ignore_errors=True)
            shutil.rmtree(final_dir, ignore_errors=True)
            raise
        return {"package_path": final_dir, **verified}
