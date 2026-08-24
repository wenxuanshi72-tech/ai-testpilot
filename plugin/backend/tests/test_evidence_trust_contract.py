from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[3]
SCHEMAS = {
    "manifest": ROOT / "schemas/run-bundles/v1/run_manifest.schema.json",
    "action": ROOT / "schemas/action-tape/v1/action_tape_event.schema.json",
    "reproduction": ROOT / "schemas/reproduction/v1/reproduction_result.schema.json",
}
HASH = "a" * 64
RUN_ID = "RUN-" + "A" * 32
REPRODUCTION_RUN_ID = "RUN-" + "B" * 32
ARTIFACT_ID = "ART-" + "C" * 32


def _schema(name: str) -> dict[str, Any]:
    return json.loads(SCHEMAS[name].read_text(encoding="utf-8"))


def _validate(name: str, payload: dict[str, Any]) -> list[str]:
    validator = Draft202012Validator(_schema(name), format_checker=FormatChecker())
    return [error.message for error in validator.iter_errors(payload)]


def _manifest() -> dict[str, Any]:
    return {
        "schema_version": "run-manifest@1.0.0",
        "run_id": RUN_ID,
        "project_id": "PRJ-PORTFOLIO",
        "environment_id": "local-windows-demo",
        "source_commit": "1" * 40,
        "frozen_baseline_id": "FBL-" + "D" * 32,
        "executor": "mixed",
        "protocol_version": "test-executor@1.0.0",
        "started_at": "2026-08-25T01:00:00Z",
        "completed_at": "2026-08-25T01:01:00Z",
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
            "node_version": "22.0.0",
            "playwright_version": "1.55.0",
            "browser_name": "msedge",
            "browser_version": "140.0.0",
        },
        "source_run": None,
        "result_ids": ["UIRES-1"],
        "artifacts": [
            {
                "artifact_id": ARTIFACT_ID,
                "role": "trace",
                "relative_path": "evidence/traces/uires-1.zip",
                "mime_type": "application/zip",
                "size_bytes": 1024,
                "sha256": HASH,
                "source_record_ids": ["UIRES-1"],
                "redaction_status": "verified",
                "integrity_status": "verified",
            }
        ],
        "evidence_policy": {
            "action_tape_required": True,
            "trace_required": True,
            "screenshot_required": True,
            "network_required": True,
            "console_required": True,
            "redaction_verified": True,
        },
        "bundle_hash": "e" * 64,
    }


def _action() -> dict[str, Any]:
    return {
        "schema_version": "action-tape-event@1.0.0",
        "event_id": "ATE-" + "F" * 32,
        "sequence": 1,
        "timestamp": "2026-08-25T01:00:10Z",
        "run_id": RUN_ID,
        "result_id": "UIRES-1",
        "case_id": "TC-UI-AUTH-REG-005",
        "case_version": 2,
        "snapshot_id": "IES-1",
        "executor": "ui",
        "phase": "test",
        "action": "fill",
        "resolved_target": {
            "strategy": "label",
            "role": None,
            "name": "Password",
            "path": None,
            "method": None,
        },
        "value_source": "test_data.password",
        "value_sensitivity": "sensitive",
        "value_display": "[REDACTED]",
        "state_before": {"route": "/register", "captured_at": "2026-08-25T01:00:09Z"},
        "state_after": {"route": "/register", "captured_at": "2026-08-25T01:00:10Z"},
        "status": "completed",
        "evidence_artifact_ids": [ARTIFACT_ID],
        "redaction_applied": True,
    }


def _reproduction() -> dict[str, Any]:
    return {
        "schema_version": "reproduction-result@1.0.0",
        "bug_id": "BUG-AUTH-001",
        "source_run_id": RUN_ID,
        "source_result_id": "UIRES-1",
        "source_manifest_hash": HASH,
        "reproduction_run_id": REPRODUCTION_RUN_ID,
        "reproduction_result_id": "RRES-1",
        "case_id": "TC-UI-AUTH-REG-005",
        "case_version": 2,
        "snapshot_id": "IES-1",
        "snapshot_hash": HASH,
        "oracle_unchanged": True,
        "status": "REPRODUCED",
        "expected": "/register",
        "actual": "/profile",
        "evidence_artifact_ids": [ARTIFACT_ID],
        "action_tape_hash": HASH,
        "reproduction_manifest_hash": HASH,
        "determined_by": "deterministic_reproduction_runner",
        "completed_at": "2026-08-25T01:02:00Z",
    }


def test_contract_schemas_are_valid_draft_2020_12() -> None:
    for name in SCHEMAS:
        Draft202012Validator.check_schema(_schema(name))


@pytest.mark.parametrize(
    ("name", "payload"),
    [("manifest", _manifest()), ("action", _action()), ("reproduction", _reproduction())],
)
def test_valid_contract_examples_pass(name: str, payload: dict[str, Any]) -> None:
    assert _validate(name, payload) == []


@pytest.mark.parametrize(
    "path",
    ["D:/secret/trace.zip", "/absolute/trace.zip", "evidence/../secret.txt"],
)
def test_manifest_rejects_unsafe_artifact_paths(path: str) -> None:
    payload = _manifest()
    payload["artifacts"][0]["relative_path"] = path
    assert _validate("manifest", payload)


def test_manifest_rejects_invalid_hash_and_unknown_ai_authority() -> None:
    payload = _manifest()
    payload["bundle_hash"] = "not-a-hash"
    payload["ai_verified"] = True
    errors = _validate("manifest", payload)
    assert len(errors) == 2


def test_manifest_rejects_exact_duplicate_artifacts() -> None:
    payload = _manifest()
    payload["artifacts"].append(copy.deepcopy(payload["artifacts"][0]))
    assert _validate("manifest", payload)


def test_verified_manifest_requires_reproduction_result() -> None:
    payload = _manifest()
    payload["trust_state"] = "verified"
    assert _validate("manifest", payload)
    payload["trust_evaluation"]["reproduction_result_id"] = "RRES-1"
    assert _validate("manifest", payload) == []


def test_action_rejects_unsupported_action_and_sequence_zero() -> None:
    payload = _action()
    payload["sequence"] = 0
    payload["action"] = "execute_shell"
    assert len(_validate("action", payload)) == 2


def test_action_requires_sensitive_value_redaction() -> None:
    payload = _action()
    payload["value_display"] = "raw-secret"
    assert _validate("action", payload)


def test_reproduction_rejects_ai_verdict_or_oracle_change() -> None:
    payload = _reproduction()
    payload["determined_by"] = "deepseek"
    payload["oracle_unchanged"] = False
    assert len(_validate("reproduction", payload)) == 2


def test_reproduction_rejects_unknown_fields_and_bad_hash() -> None:
    payload = _reproduction()
    payload["model_confidence"] = 0.99
    payload["source_manifest_hash"] = "bad"
    assert len(_validate("reproduction", payload)) == 2


def test_documents_define_truthfulness_boundaries() -> None:
    trust = (ROOT / "docs/architecture/EVIDENCE_TRUST_MODEL.md").read_text(encoding="utf-8")
    bundle = (ROOT / "docs/architecture/RUN_ARTIFACT_BUNDLE.md").read_text(encoding="utf-8")
    for state in ("UNVERIFIED", "EXECUTED", "VERIFIED"):
        assert state in trust
    assert "Hashes prove only" in trust
    assert "not rewritten as `VERIFIED`" in trust
    assert "atomically rename" in bundle
