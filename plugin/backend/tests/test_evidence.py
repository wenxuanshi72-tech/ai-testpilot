from __future__ import annotations

import hashlib
import shutil
from pathlib import Path
from typing import Any

import pytest
from flask.testing import FlaskClient
from sqlalchemy.exc import IntegrityError

from plugin.backend.app.api_execution import (
    ApiExecutionService,
    LocalFlaskSutRuntime,
    RuntimeResponse,
    _canonical,
)
from plugin.backend.app.database import PROJECT_ROOT, PluginDatabase
from plugin.backend.app.evidence import (
    CLASSIFIER_VERSION,
    EVIDENCE_POLICY_VERSION,
    EvidenceError,
    EvidenceService,
)
from plugin.backend.app.ids import new_id
from plugin.backend.app.ui_execution import UiExecutionService
from plugin.backend.tests.test_api_execution import _frozen_api_baseline
from plugin.backend.tests.test_test_generation import _seed_formal_requirements
from plugin.backend.tests.test_ui_execution import _FakePlaywright


def _source_runs(
    database: PluginDatabase, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, str, Path]:
    _seed_formal_requirements(database)
    baseline_id = _frozen_api_baseline(database)

    class HistoricalDefectRuntime(LocalFlaskSutRuntime):
        """Reproduce the immutable pre-fix API observation for Phase 8-10 tests."""

        def request(
            self, method: str, path: str, *, headers: dict[str, str], body: Any
        ) -> RuntimeResponse:
            historical_body = body
            if (
                self.case_id == "TC-API-AUTH-REG-005"
                and method == "POST"
                and path == "/api/auth/register"
                and isinstance(body, dict)
                and body.get("username") == "z1234"
            ):
                historical_body = {**body, "username": "z12345"}
            return super().request(method, path, headers=headers, body=historical_body)

    api_run = ApiExecutionService(database, HistoricalDefectRuntime).execute(
        baseline_id, environment_id="local-test"
    )
    evidence_root = PROJECT_ROOT / "artifacts" / "evidence" / new_id("PHASE8TEST")
    service = UiExecutionService(database, evidence_root=evidence_root)
    monkeypatch.setattr("plugin.backend.app.ui_execution.sync_playwright", _FakePlaywright)

    def staged(_browser: Any, row: dict[str, Any], _base: str, run_dir: Path) -> dict[str, Any]:
        snapshot = row["snapshot"]
        case_id = str(snapshot["case_id"])
        result_id = new_id("UIRES")
        evidence_id = new_id("EVD")
        case_dir = run_dir / case_id
        case_dir.mkdir(parents=True)
        screenshot = case_dir / "final.png"
        trace = case_dir / "trace.zip"
        screenshot.write_bytes(b"safe-phase8-screenshot")
        trace.write_bytes(b"safe-phase8-trace")
        evidence = {
            "screenshot_path": screenshot.relative_to(PROJECT_ROOT).as_posix(),
            "screenshot_hash": hashlib.sha256(screenshot.read_bytes()).hexdigest(),
            "trace_path": trace.relative_to(PROJECT_ROOT).as_posix(),
            "trace_hash": hashlib.sha256(trace.read_bytes()).hexdigest(),
        }
        result = {
            "schema_version": "ui-execution-result@1.0.0",
            "case_id": case_id,
            "case_version": int(snapshot["case_version"]),
            "status": "FAIL",
            "failure_type": "suspected_product_bug",
            "expected_route": "/register",
            "actual_route": "/profile",
            "duration_ms": 1,
            "network_observations": [
                {"method": "POST", "path": "/api/auth/register", "status": 201}
            ],
            "assertions": [],
            "evidence_id": evidence_id,
            "evidence_hash": hashlib.sha256(_canonical(evidence).encode()).hexdigest(),
        }
        return {
            "snapshot_id": row["immutable_execution_snapshot_id"],
            "result_id": result_id,
            "status": "FAIL",
            "result": result,
            "evidence": evidence,
        }

    monkeypatch.setattr(service, "_execute_snapshot", staged)
    ui_run = service.execute(
        baseline_id,
        environment_id="local-test",
        base_url="http://127.0.0.1:5173",
    )
    return api_run.run_id, str(ui_run["run_id"]), evidence_root


def test_consolidation_verifies_sources_and_keeps_verdict_authoritative(
    database: PluginDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    api_run, ui_run, evidence_root = _source_runs(database, monkeypatch)
    try:
        service = EvidenceService(database)
        result = service.consolidate(api_run, ui_run)
        assert result["policy_version"] == EVIDENCE_POLICY_VERSION
        assert result["classifier_version"] == CLASSIFIER_VERSION
        assert result["result_count"] == 10
        assert result["evidence_count"] == 11
        assert len(result["classifications"]) == 10
        seeded = [
            row
            for row in result["classifications"]
            if row["classification_code"] == "seeded_product_bug"
        ]
        assert {row["case_id"] for row in seeded} == {
            "TC-API-AUTH-REG-005",
            "TC-UI-AUTH-REG-005",
        }
        assert all(row["suspected_bug_id"] == "BUG-AUTH-001" for row in seeded)
        assert (
            service.consolidate(api_run, ui_run)["evidence_consolidation_run_id"]
            == result["evidence_consolidation_run_id"]
        )

        advisory = service.record_advisory(
            str(seeded[0]["failure_classification_id"]),
            provider="offline-test",
            model="none",
            prompt_version="advisory-test@1.0.0",
            analysis={
                "schema_version": "advisory-evidence-analysis@1.0.0",
                "summary": "Possible requirement mismatch.",
                "hypotheses": ["Product validation may be missing."],
                "limitations": ["Advisory only; deterministic verdict is unchanged."],
                "advisory_label": "advisory_non_authoritative",
            },
        )
        assert advisory["authoritative_verdict"] == "FAIL"
        assert advisory["authoritative_classification"] == "seeded_product_bug"
        with pytest.raises(IntegrityError, match="failure classifications are immutable"):
            database.execute(
                "UPDATE deterministic_failure_classifications SET verdict='PASS' "
                "WHERE failure_classification_id=:id",
                {"id": seeded[0]["failure_classification_id"]},
            )
    finally:
        shutil.rmtree(evidence_root, ignore_errors=True)


def test_consolidation_rejects_corrupt_or_sensitive_evidence(
    database: PluginDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    api_run, ui_run, evidence_root = _source_runs(database, monkeypatch)
    try:
        service = EvidenceService(database)
        ui_item = service._ui_items(ui_run)[0]
        Path(PROJECT_ROOT / str(ui_item["screenshot_path"])).write_bytes(b"changed")
        with pytest.raises(EvidenceError, match="SOURCE_ARTIFACT_HASH_INVALID"):
            service.consolidate(api_run, ui_run)
    finally:
        shutil.rmtree(evidence_root, ignore_errors=True)


def test_phase8_routes_validate_and_return_consolidation(
    client: FlaskClient, database: PluginDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.post("/api/v1/evidence-consolidations", json={}).status_code == 422
    api_run, ui_run, evidence_root = _source_runs(database, monkeypatch)
    try:
        response = client.post(
            "/api/v1/evidence-consolidations",
            json={"api_test_run_id": api_run, "ui_test_run_id": ui_run},
        )
        assert response.status_code == 201
        run_id = response.get_json()["data"]["evidence_consolidation_run_id"]
        assert client.get(f"/api/v1/evidence-consolidations/{run_id}").status_code == 200
        assert client.get("/api/v1/evidence-consolidations/ECR-MISSING").status_code == 404
    finally:
        shutil.rmtree(evidence_root, ignore_errors=True)


def test_advisory_schema_and_source_context_are_strict(database: PluginDatabase) -> None:
    service = EvidenceService(database)
    with pytest.raises(EvidenceError, match="SOURCE_EVIDENCE_NOT_REDACTED"):
        service._verify_redaction(b"safe", {"redaction_applied": 0})
    with pytest.raises(EvidenceError, match="SOURCE_EVIDENCE_SENSITIVE_MARKER"):
        service._verify_redaction(b"Authorization: Bearer redacted", {"redaction_applied": 1})
    with pytest.raises(EvidenceError, match="SOURCE_ARTIFACT_PATH_INVALID"):
        service._safe_artifact_path("docs/ROADMAP.md")
    with pytest.raises(EvidenceError, match="ADVISORY_ANALYSIS_SCHEMA_INVALID"):
        service.record_advisory(
            "CLS-MISSING",
            provider="none",
            model="none",
            prompt_version="none",
            analysis={"summary": "missing contract fields"},
        )
    with pytest.raises(EvidenceError, match="SOURCE_RUN_TYPE_INVALID"):
        service._run("projects", "project_id", "PRJ-MISSING")
    with pytest.raises(EvidenceError, match="SOURCE_RUN_NOT_FOUND"):
        service._run("api_test_runs", "api_test_run_id", "RUN-MISSING")
