from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pypdfium2 as pdfium  # type: ignore[import-untyped]
import pytest
from flask.testing import FlaskClient
from pypdf import PdfReader
from sqlalchemy.exc import IntegrityError

from plugin.backend.app.bug_artifacts import BugArtifactService
from plugin.backend.app.database import PROJECT_ROOT, PluginDatabase
from plugin.backend.app.evidence import EvidenceService
from plugin.backend.app.ids import new_id
from plugin.backend.app.reporting import TestReportService
from plugin.backend.tests.test_evidence import _source_runs


def _report_sources(
    database: PluginDatabase, monkeypatch: pytest.MonkeyPatch
) -> tuple[str, str, list[Path]]:
    api_run, ui_run, evidence_root = _source_runs(database, monkeypatch)
    consolidation = EvidenceService(database).consolidate(api_run, ui_run)
    bug_root = PROJECT_ROOT / "artifacts" / "bugs" / new_id("PHASE10BUG")
    bug = BugArtifactService(database, artifact_root=bug_root).generate(
        str(consolidation["evidence_consolidation_run_id"]), "BUG-AUTH-001"
    )
    return (
        str(consolidation["evidence_consolidation_run_id"]),
        str(bug["canonical_bug_record_id"]),
        [evidence_root, bug_root],
    )


def test_report_formats_manifest_rendering_and_immutability(
    database: PluginDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id, bug_id, cleanup = _report_sources(database, monkeypatch)
    report_root = PROJECT_ROOT / "artifacts" / "reports" / new_id("PHASE10TEST")
    cleanup.append(report_root)
    try:
        service = TestReportService(database, artifact_root=report_root)
        result = service.generate(run_id, bug_id)
        report = result["canonical_report"]
        assert report["summary"]["total"] == 10
        assert report["summary"]["api_total"] == 9
        assert report["summary"]["ui_total"] == 1
        assert (
            sum(report["summary"][key] for key in ("pass", "fail", "blocked", "error", "skipped"))
            == 10
        )
        assert sum(report["classifications"].values()) == 10
        assert report["classifications"]["seeded_product_bug"] == 2
        assert report["evidence_count"] == 11
        assert (
            service.generate(run_id, bug_id)["canonical_test_report_id"]
            == result["canonical_test_report_id"]
        )

        bundle = result["bundle"]
        paths = {
            name: PROJECT_ROOT / bundle[f"{name}_path"]
            for name in ("json", "markdown", "html", "pdf", "manifest")
        }
        manifest = json.loads(paths["manifest"].read_text("utf-8"))
        for name in ("json", "markdown", "html", "pdf"):
            assert (
                hashlib.sha256(paths[name].read_bytes()).hexdigest()
                == manifest["files"][name]["sha256"]
            )
        markdown = paths["markdown"].read_text("utf-8")
        html_text = paths["html"].read_text("utf-8")
        for value in (
            "Total: 10",
            f"PASS: {report['summary']['pass']}",
            f"FAIL: {report['summary']['fail']}",
            "BUG-AUTH-001",
        ):
            assert value in markdown
        assert "<caption>Persisted deterministic API and UI results</caption>" in html_text
        assert 'scope="col"' in html_text
        assert '<a class="skip"' in html_text
        reader = PdfReader(paths["pdf"])
        assert len(reader.pages) >= 2
        pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
        for value in ("Total", "PASS", "FAIL", "BUG-AUTH-001", "Evidence Index"):
            assert value in pdf_text
        rendered = pdfium.PdfDocument(paths["pdf"])
        bitmap = rendered[0].render(scale=1)
        assert bitmap.width > 500 and bitmap.height > 700
        bitmap.close()
        rendered.close()
        for item in manifest["evidence"]:
            path = PROJECT_ROOT / item["relative_path"]
            assert path.is_file()
            assert hashlib.sha256(path.read_bytes()).hexdigest() == item["content_hash"]

        with pytest.raises(IntegrityError, match="canonical test reports are immutable"):
            database.execute(
                "UPDATE canonical_test_reports SET status='completed' "
                "WHERE canonical_test_report_id=:id",
                {"id": result["canonical_test_report_id"]},
            )
    finally:
        for path in cleanup:
            shutil.rmtree(path, ignore_errors=True)


def test_report_html_escapes_untrusted_content() -> None:
    report = {
        "title": "<script>alert(1)</script>",
        "summary": {"total": 1, "pass": 1, "fail": 0},
        "evidence_count": 1,
        "bugs": [{"bug_id": "BUG-X", "bug_version": 1, "title": "<unsafe>"}],
        "results": [
            {
                "executor": "api",
                "case_id": "<case>",
                "case_version": 1,
                "verdict": "PASS",
                "classification": "none",
                "expected": 200,
                "actual": 200,
                "bug_id": None,
                "evidence": [
                    {
                        "kind": "api_exchange",
                        "relative_path": "artifacts/evidence/safe.json",
                        "content_hash": "a" * 64,
                    }
                ],
            }
        ],
    }
    output = TestReportService._html(report, PROJECT_ROOT / "artifacts" / "reports" / "x")
    assert "<script>" not in output
    assert "&lt;script&gt;" in output
    assert "&lt;unsafe&gt;" in output
    assert "&lt;case&gt;" in output


def test_report_export_failure_does_not_create_completed_record(
    database: PluginDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_id, bug_id, cleanup = _report_sources(database, monkeypatch)
    report_root = PROJECT_ROOT / "artifacts" / "reports" / new_id("PHASE10TEST")
    cleanup.append(report_root)
    try:
        service = TestReportService(database, artifact_root=report_root)

        def fail(*_args: object, **_kwargs: object) -> dict[str, str]:
            raise OSError("simulated report export failure")

        monkeypatch.setattr(service, "_write_bundle", fail)
        with pytest.raises(OSError, match="simulated report export failure"):
            service.generate(run_id, bug_id)
        assert database.fetch_one("SELECT COUNT(*) AS count FROM canonical_test_reports") == {
            "count": 0
        }
    finally:
        for path in cleanup:
            shutil.rmtree(path, ignore_errors=True)


def test_phase10_routes_generate_and_read_report(
    client: FlaskClient, database: PluginDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.post("/api/v1/evidence-consolidations/ECR-X/reports", json={}).status_code == 422
    run_id, bug_id, cleanup = _report_sources(database, monkeypatch)
    report_root = PROJECT_ROOT / "artifacts" / "reports" / new_id("PHASE10TEST")
    cleanup.append(report_root)
    monkeypatch.setattr(
        "plugin.backend.app.routes._test_report_service",
        lambda: TestReportService(database, artifact_root=report_root),
    )
    try:
        response = client.post(
            f"/api/v1/evidence-consolidations/{run_id}/reports",
            json={"canonical_bug_record_id": bug_id},
        )
        assert response.status_code == 201
        report_id = response.get_json()["data"]["canonical_test_report_id"]
        assert client.get(f"/api/v1/reports/{report_id}").status_code == 200
        assert client.get("/api/v1/reports/RPT-MISSING").status_code == 404
    finally:
        for path in cleanup:
            shutil.rmtree(path, ignore_errors=True)
