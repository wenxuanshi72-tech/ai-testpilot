from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import plugin.backend.app.run_artifact_bundles as bundle_module
from plugin.backend.app.action_tape import ActionTapeWriter
from plugin.backend.app.run_artifact_bundles import (
    RunArtifactBundleError,
    RunArtifactBundleWriter,
    manifest_bundle_hash,
    verify_run_artifact_bundle,
)

RUN_ID = "RUN-" + "A" * 32


def _fields() -> dict[str, object]:
    return {
        "run_id": RUN_ID,
        "project_id": "PRJ-PORTFOLIO",
        "environment_id": "local-windows-demo",
        "source_commit": "1" * 40,
        "frozen_baseline_id": "FBL-" + "B" * 32,
        "executor": "api",
        "protocol_version": "test-executor@1.0.0",
        "started_at": "2026-08-28T01:00:00Z",
        "completed_at": "2026-08-28T01:01:00Z",
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
            "producer_version": "run-artifact-writer@1.0.0",
            "operating_system": "Windows 11",
            "python_version": "3.11.9",
            "node_version": None,
            "playwright_version": None,
            "browser_name": None,
            "browser_version": None,
        },
        "source_run": None,
        "result_ids": ["APIRES-1"],
        "evidence_policy": {
            "action_tape_required": False,
            "trace_required": False,
            "screenshot_required": False,
            "network_required": False,
            "console_required": False,
            "redaction_verified": True,
        },
    }


def _bundle(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    writer = RunArtifactBundleWriter(tmp_path, _fields())
    writer.start()
    writer.add_bytes(
        "results/api-results.json",
        b'{"status":"PASS"}\n',
        role="result",
        mime_type="application/json",
        source_record_ids=["APIRES-1"],
        redaction_status="not_applicable",
        artifact_id="ART-" + "C" * 32,
    )
    manifest = writer.finalize()
    return tmp_path / RUN_ID, manifest


def test_writer_finalizes_verified_bundle_atomically(tmp_path: Path) -> None:
    path, manifest = _bundle(tmp_path)
    assert path.is_dir()
    assert not (tmp_path / f".{RUN_ID}.staging").exists()
    assert verify_run_artifact_bundle(path) == manifest
    assert manifest["bundle_hash"] == manifest_bundle_hash(manifest)


@pytest.mark.parametrize(
    "relative",
    ["../escape.json", "D:/escape.json", "/escape.json", "results\\escape.json", "manifest.json"],
)
def test_writer_rejects_unsafe_or_reserved_paths(tmp_path: Path, relative: str) -> None:
    writer = RunArtifactBundleWriter(tmp_path, _fields())
    writer.start()
    with pytest.raises(RunArtifactBundleError):
        writer.add_bytes(
            relative,
            b"data",
            role="result",
            mime_type="application/json",
            source_record_ids=["APIRES-1"],
            redaction_status="not_applicable",
        )
    writer.abort()


def test_writer_rejects_empty_and_duplicate_artifacts(tmp_path: Path) -> None:
    writer = RunArtifactBundleWriter(tmp_path, _fields())
    writer.start()
    with pytest.raises(RunArtifactBundleError, match="EMPTY"):
        writer.add_bytes(
            "results/empty.json",
            b"",
            role="result",
            mime_type="application/json",
            source_record_ids=["APIRES-1"],
            redaction_status="not_applicable",
        )
    writer.add_bytes(
        "results/one.json",
        b"one",
        role="result",
        mime_type="application/json",
        source_record_ids=["APIRES-1"],
        redaction_status="not_applicable",
    )
    with pytest.raises(RunArtifactBundleError, match="PATH_DUPLICATE"):
        writer.add_bytes(
            "results/one.json",
            b"two",
            role="result",
            mime_type="application/json",
            source_record_ids=["APIRES-1"],
            redaction_status="not_applicable",
        )
    writer.abort()


def test_verifier_rejects_tampered_member(tmp_path: Path) -> None:
    path, _ = _bundle(tmp_path)
    (path / "results" / "api-results.json").write_text("tampered", encoding="utf-8")
    with pytest.raises(RunArtifactBundleError, match="SIZE_MISMATCH|HASH_MISMATCH"):
        verify_run_artifact_bundle(path)


def test_verifier_rejects_tampered_manifest_hash(tmp_path: Path) -> None:
    path, _ = _bundle(tmp_path)
    manifest_path = path / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["project_id"] = "changed"
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RunArtifactBundleError, match="BUNDLE_HASH_MISMATCH"):
        verify_run_artifact_bundle(path)


def test_verifier_rejects_missing_and_extra_files(tmp_path: Path) -> None:
    path, _ = _bundle(tmp_path)
    (path / "extra.txt").write_text("extra", encoding="utf-8")
    with pytest.raises(RunArtifactBundleError, match="FILE_SET_MISMATCH"):
        verify_run_artifact_bundle(path)


def test_verifier_rejects_duplicate_logical_id_even_with_rehashed_manifest(tmp_path: Path) -> None:
    path, _ = _bundle(tmp_path)
    manifest_path = path / "manifest.json"
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    duplicate = copy.deepcopy(payload["artifacts"][0])
    duplicate["relative_path"] = "results/copy.json"
    original = (path / "results" / "api-results.json").read_bytes()
    (path / "results" / "copy.json").write_bytes(original)
    payload["artifacts"].append(duplicate)
    payload["bundle_hash"] = manifest_bundle_hash(payload)
    manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RunArtifactBundleError, match="ARTIFACT_ID_DUPLICATE"):
        verify_run_artifact_bundle(path)


def test_required_evidence_role_is_enforced(tmp_path: Path) -> None:
    fields = _fields()
    fields["evidence_policy"]["trace_required"] = True  # type: ignore[index]
    writer = RunArtifactBundleWriter(tmp_path, fields)
    writer.start()
    writer.add_bytes(
        "results/api-results.json",
        b"result",
        role="result",
        mime_type="application/json",
        source_record_ids=["APIRES-1"],
        redaction_status="not_applicable",
    )
    with pytest.raises(RunArtifactBundleError, match="REQUIRED_ARTIFACT_MISSING:trace"):
        writer.finalize()
    assert not writer.staging_dir.exists()
    assert not writer.final_dir.exists()


def test_action_tape_is_validated_and_bound_to_bundle_records(tmp_path: Path) -> None:
    fields = _fields()
    fields["evidence_policy"]["action_tape_required"] = True  # type: ignore[index]
    writer = RunArtifactBundleWriter(tmp_path, fields)
    writer.start()
    result_artifact_id = "ART-" + "D" * 32
    writer.add_bytes(
        "results/api-results.json",
        b'{"status":"FAIL"}\n',
        role="result",
        mime_type="application/json",
        source_record_ids=["APIRES-1"],
        redaction_status="not_applicable",
        artifact_id=result_artifact_id,
    )
    tape = ActionTapeWriter(
        run_id=RUN_ID,
        result_id="APIRES-1",
        case_id="TC-API-AUTH-REG-005",
        case_version=1,
        snapshot_id="IES-" + "E" * 32,
        executor="api",
        clock=lambda: "2026-09-08T10:00:00Z",
    )
    tape.record(
        phase="assertion",
        action="assert",
        resolved_target=None,
        state_before_route=None,
        state_after_route=None,
        status="failed",
        evidence_artifact_ids=[result_artifact_id],
    )
    writer.add_action_tape(
        "action-tape/APIRES-1.ndjson",
        tape.finalize(),
        source_record_ids=["APIRES-1"],
    )

    manifest = writer.finalize()
    assert {artifact["role"] for artifact in manifest["artifacts"]} == {
        "action_tape",
        "result",
    }
    assert verify_run_artifact_bundle(tmp_path / RUN_ID) == manifest


def test_bundle_rejects_action_tape_with_missing_artifact_reference(tmp_path: Path) -> None:
    fields = _fields()
    fields["evidence_policy"]["action_tape_required"] = True  # type: ignore[index]
    writer = RunArtifactBundleWriter(tmp_path, fields)
    writer.start()
    tape = ActionTapeWriter(
        run_id=RUN_ID,
        result_id="APIRES-1",
        case_id="TC-API-AUTH-REG-005",
        case_version=1,
        snapshot_id="IES-" + "E" * 32,
        executor="api",
        clock=lambda: "2026-09-08T10:00:00Z",
    )
    tape.record(
        phase="assertion",
        action="assert",
        resolved_target=None,
        state_before_route=None,
        state_after_route=None,
        evidence_artifact_ids=["ART-" + "F" * 32],
    )
    writer.add_action_tape(
        "action-tape/APIRES-1.ndjson",
        tape.finalize(),
        source_record_ids=["APIRES-1"],
    )
    with pytest.raises(RunArtifactBundleError, match="ACTION_TAPE_REFERENCE_MISSING"):
        writer.finalize()


def test_schema_failure_cleans_staging_without_formal_bundle(tmp_path: Path) -> None:
    fields = _fields()
    fields["source_commit"] = "invalid"
    writer = RunArtifactBundleWriter(tmp_path, fields)
    writer.start()
    writer.add_bytes(
        "results/api-results.json",
        b"result",
        role="result",
        mime_type="application/json",
        source_record_ids=["APIRES-1"],
        redaction_status="not_applicable",
    )
    with pytest.raises(RunArtifactBundleError, match="MANIFEST_SCHEMA_INVALID"):
        writer.finalize()
    assert not writer.staging_dir.exists()
    assert not writer.final_dir.exists()


def test_add_file_rejects_missing_source(tmp_path: Path) -> None:
    writer = RunArtifactBundleWriter(tmp_path, _fields())
    writer.start()
    with pytest.raises(RunArtifactBundleError, match="SOURCE_FILE_INVALID"):
        writer.add_file(
            tmp_path / "missing.json",
            "results/missing.json",
            role="result",
            mime_type="application/json",
            source_record_ids=["APIRES-1"],
            redaction_status="not_applicable",
        )
    writer.abort()


def test_post_promotion_verification_failure_removes_formal_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = RunArtifactBundleWriter(tmp_path, _fields())
    writer.start()
    writer.add_bytes(
        "results/api-results.json",
        b"result",
        role="result",
        mime_type="application/json",
        source_record_ids=["APIRES-1"],
        redaction_status="not_applicable",
    )
    original = bundle_module.verify_run_artifact_bundle
    calls = 0

    def fail_second_verification(path: Path) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RunArtifactBundleError("SIMULATED_POST_PROMOTION_FAILURE")
        return original(path)

    monkeypatch.setattr(bundle_module, "verify_run_artifact_bundle", fail_second_verification)
    with pytest.raises(RunArtifactBundleError, match="POST_PROMOTION_FAILURE"):
        writer.finalize()
    assert not writer.staging_dir.exists()
    assert not writer.final_dir.exists()
