from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from flask.testing import FlaskClient
from sqlalchemy.exc import IntegrityError

from plugin.backend.app.bug_artifacts import BugArtifactError, BugArtifactService
from plugin.backend.app.database import PROJECT_ROOT, PluginDatabase
from plugin.backend.app.evidence import EvidenceService
from plugin.backend.app.ids import new_id
from plugin.backend.tests.test_evidence import _source_runs


def _eligible(database: PluginDatabase, monkeypatch: pytest.MonkeyPatch) -> tuple[str, Path, Path]:
    api_run, ui_run, evidence_root = _source_runs(database, monkeypatch)
    consolidation = EvidenceService(database).consolidate(api_run, ui_run)
    bug_root = PROJECT_ROOT / "artifacts" / "bugs" / new_id("PHASE9TEST")
    return str(consolidation["evidence_consolidation_run_id"]), evidence_root, bug_root


def test_canonical_bug_bundle_is_traceable_idempotent_and_immutable(
    database: PluginDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id, evidence_root, bug_root = _eligible(database, monkeypatch)
    try:
        service = BugArtifactService(database, artifact_root=bug_root)
        result = service.generate(run_id, "BUG-AUTH-001")
        canonical = result["canonical_bug"]
        assert canonical["bug_id"] == "BUG-AUTH-001"
        assert canonical["actual_result"].find("HTTP 201") >= 0
        assert canonical["actual_result"].find("/profile") >= 0
        assert canonical["advisory_ai"] == []
        assert {item["case_id"] for item in canonical["sources"]} == {
            "TC-API-AUTH-REG-005",
            "TC-UI-AUTH-REG-005",
        }
        assert all(item["case_version"] > 0 for item in canonical["sources"])
        assert (
            service.generate(run_id, "BUG-AUTH-001")["canonical_bug_record_id"]
            == result["canonical_bug_record_id"]
        )

        bundle = result["bundle"]
        json_path = PROJECT_ROOT / bundle["json_path"]
        markdown_path = PROJECT_ROOT / bundle["markdown_path"]
        manifest_path = PROJECT_ROOT / bundle["manifest_path"]
        assert json.loads(json_path.read_text("utf-8")) == canonical
        markdown = markdown_path.read_text("utf-8")
        assert canonical["title"] in markdown
        assert canonical["expected_result"] in markdown
        assert canonical["actual_result"] in markdown
        manifest = json.loads(manifest_path.read_text("utf-8"))
        assert hashlib.sha256(json_path.read_bytes()).hexdigest() == manifest["json"]["sha256"]
        assert (
            hashlib.sha256(markdown_path.read_bytes()).hexdigest() == manifest["markdown"]["sha256"]
        )
        for source in canonical["sources"]:
            for evidence in source["evidence"]:
                assert (PROJECT_ROOT / evidence["relative_path"]).is_file()
        serialized = (json_path.read_bytes() + markdown_path.read_bytes()).lower()
        assert b"test1234" not in serialized
        assert b"authorization: bearer" not in serialized
        assert str(PROJECT_ROOT).encode().lower() not in serialized

        with pytest.raises(IntegrityError, match="canonical bug records are immutable"):
            database.execute(
                "UPDATE canonical_bug_records SET status='closed' "
                "WHERE canonical_bug_record_id=:id",
                {"id": result["canonical_bug_record_id"]},
            )
        with pytest.raises(IntegrityError, match="canonical bug records are immutable"):
            database.execute(
                "DELETE FROM canonical_bug_records WHERE canonical_bug_record_id=:id",
                {"id": result["canonical_bug_record_id"]},
            )
    finally:
        shutil.rmtree(evidence_root, ignore_errors=True)
        shutil.rmtree(bug_root, ignore_errors=True)


def test_bug_gate_rejects_corrupt_evidence_and_non_product_bug(
    database: PluginDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id, evidence_root, bug_root = _eligible(database, monkeypatch)
    try:
        service = BugArtifactService(database, artifact_root=bug_root)
        with pytest.raises(BugArtifactError, match="BUG_POLICY_UNSUPPORTED"):
            service.generate(run_id, "BUG-TEST-DATA")
        screenshot = next(evidence_root.rglob("final.png"))
        screenshot.write_bytes(b"corrupt")
        with pytest.raises(BugArtifactError, match="BUG_EVIDENCE_HASH_INVALID"):
            service.generate(run_id, "BUG-AUTH-001")
        assert database.fetch_one("SELECT COUNT(*) AS count FROM canonical_bug_records") == {
            "count": 0
        }
    finally:
        shutil.rmtree(evidence_root, ignore_errors=True)
        shutil.rmtree(bug_root, ignore_errors=True)


def test_export_failure_does_not_create_completed_bug(
    database: PluginDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id, evidence_root, bug_root = _eligible(database, monkeypatch)
    try:
        service = BugArtifactService(database, artifact_root=bug_root)

        def fail(*_args: object, **_kwargs: object) -> dict[str, str]:
            raise OSError("simulated local export failure")

        monkeypatch.setattr(service, "_write_bundle", fail)
        with pytest.raises(OSError, match="simulated local export failure"):
            service.generate(run_id, "BUG-AUTH-001")
        assert database.fetch_one("SELECT COUNT(*) AS count FROM canonical_bug_records") == {
            "count": 0
        }
        assert database.fetch_one("SELECT COUNT(*) AS count FROM bug_artifact_bundles") == {
            "count": 0
        }
    finally:
        shutil.rmtree(evidence_root, ignore_errors=True)
        shutil.rmtree(bug_root, ignore_errors=True)


def test_phase9_routes_generate_and_read_bug(
    client: FlaskClient, database: PluginDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert (
        client.post("/api/v1/evidence-consolidations/ECR-MISSING/bugs", json={}).status_code == 422
    )
    run_id, evidence_root, bug_root = _eligible(database, monkeypatch)
    monkeypatch.setattr(
        "plugin.backend.app.routes._bug_artifact_service",
        lambda: BugArtifactService(database, artifact_root=bug_root),
    )
    try:
        response = client.post(
            f"/api/v1/evidence-consolidations/{run_id}/bugs", json={"bug_id": "BUG-AUTH-001"}
        )
        assert response.status_code == 201
        record_id = response.get_json()["data"]["canonical_bug_record_id"]
        assert client.get(f"/api/v1/bugs/{record_id}").status_code == 200
        assert client.get("/api/v1/bugs/BUGR-MISSING").status_code == 404
    finally:
        shutil.rmtree(evidence_root, ignore_errors=True)
        shutil.rmtree(bug_root, ignore_errors=True)
