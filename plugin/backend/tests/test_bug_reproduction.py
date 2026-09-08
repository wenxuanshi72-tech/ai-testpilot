from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

import plugin.backend.app.bug_reproduction as reproduction_module
from plugin.backend.app.action_tape import ActionTapeWriter
from plugin.backend.app.bug_reproduction import (
    BugReproductionError,
    BugReproductionPackageWriter,
    verify_bug_reproduction_package,
)
from plugin.backend.app.database import PROJECT_ROOT
from plugin.backend.app.run_artifact_bundles import (
    RunArtifactBundleWriter,
    manifest_bundle_hash,
)

SOURCE_RUN_ID = "RUN-" + "A" * 32
REPRODUCTION_RUN_ID = "RUN-" + "B" * 32
SOURCE_RESULT_ID = "RES-" + "C" * 32
REPRODUCTION_RESULT_ID = "RES-" + "D" * 32
SNAPSHOT_ID = "IES-" + "E" * 32
SNAPSHOT_HASH = "1" * 64


def _fields(
    run_id: str,
    result_id: str,
    *,
    source_run: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "project_id": "PRJ-PORTFOLIO",
        "environment_id": "local-test",
        "source_commit": "2" * 40,
        "frozen_baseline_id": "FBL-" + "F" * 32,
        "executor": "api",
        "protocol_version": "test-executor@1.0.0",
        "started_at": "2026-09-08T10:00:00Z",
        "completed_at": "2026-09-08T10:01:00Z",
        "finalization_status": "completed",
        "trust_state": "executed",
        "trust_evaluation": {
            "policy_version": "evidence-trust-policy@1.0.0",
            "determined_by": "deterministic_trust_evaluator",
            "verifier_version": "run-bundle-verifier@1.0.0",
            "reproduction_result_id": None,
        },
        "provenance": {
            "producer": "deterministic_executor",
            "producer_version": "api-executor@1.0.0",
            "operating_system": "test-double",
            "python_version": "3.11.9",
            "node_version": None,
            "playwright_version": None,
            "browser_name": None,
            "browser_version": None,
        },
        "source_run": source_run,
        "result_ids": [result_id],
        "evidence_policy": {
            "action_tape_required": True,
            "trace_required": False,
            "screenshot_required": False,
            "network_required": False,
            "console_required": False,
            "redaction_verified": True,
        },
    }


def _observation(result_id: str, status: str, actual: Any, *, version: int = 2) -> bytes:
    payload = {
        "schema_version": "reproduction-observation@1.0.0",
        "executor": "api",
        "result_id": result_id,
        "case_id": "TC-API-AUTH-REG-005",
        "case_version": version,
        "snapshot_id": SNAPSHOT_ID,
        "snapshot_hash": SNAPSHOT_HASH,
        "status": status,
        "expected": {"status": 400, "user_created": False},
        "actual": actual,
        "determined_by": "deterministic_assertions",
    }
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )


def _bundle(
    root: Path,
    *,
    run_id: str,
    result_id: str,
    status: str,
    actual: Any,
    source_run: dict[str, Any] | None = None,
    version: int = 2,
    reference_kind: str = "evidence",
) -> tuple[Path, dict[str, Any]]:
    writer = RunArtifactBundleWriter(root, _fields(run_id, result_id, source_run=source_run))
    writer.start()
    evidence_artifact_id = "ART-" + ("1" if run_id == SOURCE_RUN_ID else "2") * 32
    writer.add_bytes(
        f"evidence/api/{result_id}.json",
        b'{"method":"POST","path":"/api/auth/register","status":201}\n',
        role="api_exchange",
        mime_type="application/json",
        source_record_ids=[result_id],
        redaction_status="verified",
        artifact_id=evidence_artifact_id,
    )
    result_artifact = writer.add_bytes(
        f"results/{result_id}.json",
        _observation(result_id, status, actual, version=version),
        role="result",
        mime_type="application/json",
        source_record_ids=[result_id],
        redaction_status="verified",
    )
    tape = ActionTapeWriter(
        run_id=run_id,
        result_id=result_id,
        case_id="TC-API-AUTH-REG-005",
        case_version=version,
        snapshot_id=SNAPSHOT_ID,
        executor="api",
        clock=lambda: "2026-09-08T10:00:30Z",
    )
    tape.record(
        phase="test",
        action="http_request",
        resolved_target={
            "strategy": "http",
            "role": None,
            "name": None,
            "path": "/api/auth/register",
            "method": "POST",
        },
        state_before_route=None,
        state_after_route=None,
        status="failed" if status == "FAIL" else "completed",
        evidence_artifact_ids=(
            [evidence_artifact_id]
            if reference_kind == "evidence"
            else ([result_artifact["artifact_id"]] if reference_kind == "result" else [])
        ),
    )
    writer.add_action_tape(
        f"action-tape/{result_id}.ndjson",
        tape.finalize(),
        source_record_ids=[result_id],
    )
    manifest = writer.finalize()
    return root / run_id, manifest


def _pair(
    tmp_path: Path,
    *,
    reproduction_status: str = "FAIL",
    reproduction_actual: Any = None,
    reproduction_version: int = 2,
    reference_kind: str = "evidence",
) -> tuple[Path, Path]:
    actual = reproduction_actual or {"status": 201, "user_created": True}
    source_dir, source_manifest = _bundle(
        tmp_path / "source",
        run_id=SOURCE_RUN_ID,
        result_id=SOURCE_RESULT_ID,
        status="FAIL",
        actual={"status": 201, "user_created": True},
    )
    reproduction_dir, _ = _bundle(
        tmp_path / "reproduction",
        run_id=REPRODUCTION_RUN_ID,
        result_id=REPRODUCTION_RESULT_ID,
        status=reproduction_status,
        actual=actual,
        version=reproduction_version,
        reference_kind=reference_kind,
        source_run={
            "run_id": SOURCE_RUN_ID,
            "result_id": SOURCE_RESULT_ID,
            "manifest_hash": source_manifest["bundle_hash"],
        },
    )
    return source_dir, reproduction_dir


def _writer(tmp_path: Path, source: Path, reproduction: Path) -> BugReproductionPackageWriter:
    return BugReproductionPackageWriter(
        tmp_path / "packages",
        bug_id="BUG-AUTH-001",
        source_bundle_dir=source,
        reproduction_bundle_dir=reproduction,
        source_result_id=SOURCE_RESULT_ID,
        reproduction_result_id=REPRODUCTION_RESULT_ID,
        clock=lambda: "2026-09-08T11:00:00Z",
    )


def test_reproduction_schemas_are_valid() -> None:
    for filename in (
        "reproduction_observation.schema.json",
        "reproduction_package_manifest.schema.json",
    ):
        schema = json.loads(
            (PROJECT_ROOT / "schemas" / "reproduction" / "v1" / filename).read_text("utf-8")
        )
        Draft202012Validator.check_schema(schema)


def test_writer_creates_self_contained_reproduced_package(tmp_path: Path) -> None:
    source, reproduction = _pair(tmp_path)
    result = _writer(tmp_path, source, reproduction).write()

    assert result["reproduction_result"]["status"] == "REPRODUCED"
    assert result["reproduction_result"]["oracle_unchanged"] is True
    assert result["manifest"]["source_run_id"] == SOURCE_RUN_ID
    assert result["manifest"]["reproduction_run_id"] == REPRODUCTION_RUN_ID
    assert verify_bug_reproduction_package(result["package_path"]) == {
        "manifest": result["manifest"],
        "reproduction_result": result["reproduction_result"],
    }


def test_runner_retains_not_reproduced_as_a_real_outcome(tmp_path: Path) -> None:
    source, reproduction = _pair(
        tmp_path,
        reproduction_status="PASS",
        reproduction_actual={"status": 400, "user_created": False},
    )
    result = _writer(tmp_path, source, reproduction).write()
    assert result["reproduction_result"]["status"] == "NOT_REPRODUCED"
    assert result["reproduction_result"]["actual"] == {
        "status": 400,
        "user_created": False,
    }


@pytest.mark.parametrize(
    ("execution_status", "reproduction_status"),
    [("BLOCKED", "BLOCKED"), ("SKIPPED", "BLOCKED"), ("ERROR", "ERROR")],
)
def test_runner_retains_incomplete_execution_state(
    tmp_path: Path, execution_status: str, reproduction_status: str
) -> None:
    source, reproduction = _pair(tmp_path, reproduction_status=execution_status)
    result = _writer(tmp_path, source, reproduction).write()
    assert result["reproduction_result"]["status"] == reproduction_status


def test_writer_rejects_version_drift_and_missing_evidence_links(tmp_path: Path) -> None:
    source, reproduction = _pair(tmp_path / "drift", reproduction_version=3)
    with pytest.raises(BugReproductionError, match="ORACLE_OR_VERSION_CHANGED"):
        _writer(tmp_path / "drift", source, reproduction).write()

    source, reproduction = _pair(tmp_path / "missing", reference_kind="none")
    with pytest.raises(BugReproductionError, match="EVIDENCE_REFERENCE_INVALID"):
        _writer(tmp_path / "missing", source, reproduction).write()

    source, reproduction = _pair(tmp_path / "role", reference_kind="result")
    with pytest.raises(BugReproductionError, match="EVIDENCE_ROLE_INVALID"):
        _writer(tmp_path / "role", source, reproduction).write()


def test_writer_rejects_invalid_source_link(tmp_path: Path) -> None:
    source, reproduction = _pair(tmp_path)
    manifest_path = reproduction / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["source_run"]["manifest_hash"] = "0" * 64
    manifest["bundle_hash"] = manifest_bundle_hash(manifest)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(BugReproductionError, match="SOURCE_LINK_INVALID"):
        _writer(tmp_path, source, reproduction).write()


def test_writer_rejects_unexecuted_source_bundle(tmp_path: Path) -> None:
    source, reproduction = _pair(tmp_path)
    manifest_path = source / "manifest.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    manifest["trust_state"] = "unverified"
    manifest["bundle_hash"] = manifest_bundle_hash(manifest)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(BugReproductionError, match="RUN_NOT_EXECUTED"):
        _writer(tmp_path, source, reproduction).write()


def test_standalone_verifier_rejects_tampered_copied_evidence(tmp_path: Path) -> None:
    source, reproduction = _pair(tmp_path)
    result = _writer(tmp_path, source, reproduction).write()
    copied = result["package_path"] / "reproduction-run" / "evidence" / "api"
    next(copied.glob("*.json")).write_bytes(b"tampered")

    with pytest.raises(BugReproductionError, match="PACKAGE_MEMBER_HASH_INVALID"):
        verify_bug_reproduction_package(result["package_path"])


def test_post_promotion_verification_failure_removes_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source, reproduction = _pair(tmp_path)
    writer = _writer(tmp_path, source, reproduction)
    original = reproduction_module.verify_bug_reproduction_package
    calls = 0

    def fail_second(path: Path) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise BugReproductionError("SIMULATED_POST_PROMOTION_FAILURE")
        return original(path)

    monkeypatch.setattr(reproduction_module, "verify_bug_reproduction_package", fail_second)
    with pytest.raises(BugReproductionError, match="POST_PROMOTION_FAILURE"):
        writer.write()

    package_root = tmp_path / "packages"
    assert not list(package_root.glob("bug-auth-001--*"))
    assert not list(package_root.glob(".*.staging"))
