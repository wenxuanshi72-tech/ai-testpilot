from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from flask.testing import FlaskClient

from plugin.backend.app.database import PluginDatabase

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRD_TEXT = (PROJECT_ROOT / "docs" / "prd" / "login_register_prd.md").read_text(encoding="utf-8")


def _project(client: FlaskClient, name: str = "Authentication") -> str:
    response = client.post("/api/v1/projects", json={"name": name})
    assert response.status_code == 201
    return cast(str, response.get_json()["data"]["project_id"])


def _prd(client: FlaskClient, project_id: str, content: str = PRD_TEXT) -> dict[str, object]:
    response = client.post(
        f"/api/v1/projects/{project_id}/prds",
        json={"title": "Login registration", "content": content, "media_type": "text/markdown"},
    )
    assert response.status_code == 201
    return cast(dict[str, object], response.get_json()["data"])


def test_health_is_non_sensitive(client: FlaskClient) -> None:
    response = client.get("/api/v1/health", headers={"X-Request-ID": "REQ-client-1"})
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["data"] == {
        "status": "ready",
        "database": "plugin",
        "real_provider_configured": False,
    }
    assert payload["meta"]["request_id"] == "REQ-client-1"
    assert "key" not in response.get_data(as_text=True).lower()


def test_project_boundary_validation(client: FlaskClient) -> None:
    assert client.post("/api/v1/projects", data="no").status_code == 415
    assert client.post("/api/v1/projects", json=[]).status_code == 400
    response = client.post("/api/v1/projects", json={"name": ""})
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "VALIDATION_ERROR"


def test_prd_import_is_versioned_and_hashed(client: FlaskClient, database: PluginDatabase) -> None:
    project_id = _project(client)
    first = _prd(client, project_id)
    second = _prd(client, project_id, PRD_TEXT + "\n")
    assert first["version_number"] == 1
    assert second["version_number"] == 2
    assert first["prd_document_id"] == second["prd_document_id"]
    assert len(str(first["content_hash"])) == 64
    rows = database.fetch_all("SELECT * FROM prd_versions ORDER BY version_number")
    assert len(rows) == 2


def test_prd_rejects_unknown_project_media_and_empty_content(client: FlaskClient) -> None:
    assert (
        client.post(
            "/api/v1/projects/PRJ-MISSING/prds", json={"title": "x", "content": "x"}
        ).status_code
        == 404
    )
    project_id = _project(client)
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/prds",
            json={"title": "x", "content": "x", "media_type": "application/pdf"},
        ).status_code
        == 415
    )
    assert (
        client.post(
            f"/api/v1/projects/{project_id}/prds",
            json={"title": "x", "content": "  "},
        ).status_code
        == 422
    )


def test_mock_analysis_promotes_requeryable_requirements(
    client: FlaskClient, database: PluginDatabase
) -> None:
    project_id = _project(client)
    version_id = _prd(client, project_id)["version_id"]
    response = client.post(
        f"/api/v1/prd-versions/{version_id}/analysis-runs",
        json={"provider_mode": "mock"},
        headers={"Idempotency-Key": "mock-auth-analysis"},
    )
    assert response.status_code == 202
    run = response.get_json()["data"]
    assert run["status"] == "succeeded"
    assert run["provider"] == "mock"
    assert run["provider_mode"] == "mock"

    status = client.get(f"/api/v1/analysis-runs/{run['analysis_run_id']}")
    detail = status.get_json()["data"]
    assert status.status_code == 200
    assert len(detail["batches"]) >= 2
    assert all(batch["validation_status"] == "valid" for batch in detail["batches"])
    assert all(call["provider_mode"] == "mock" for call in detail["llm_calls"])

    requirements_response = client.get(f"/api/v1/projects/{project_id}/requirements")
    requirements = [item["requirement"] for item in requirements_response.get_json()["data"]]
    assert requirements_response.status_code == 200
    assert len(requirements) >= 5
    username = next(
        requirement
        for requirement in requirements
        if requirement["requirement_id"] == "REQ-AUTH-USERNAME-001"
    )
    assert "at least 6" in " ".join(username["business_rules"]).lower()
    searchable = json.dumps(requirements).lower()
    assert all(term in searchable for term in ("register", "login", "current-user", "logout"))

    repeated = client.post(
        f"/api/v1/prd-versions/{version_id}/analysis-runs",
        json={"provider_mode": "mock"},
        headers={"Idempotency-Key": "mock-auth-analysis"},
    )
    assert repeated.get_json()["data"]["analysis_run_id"] == run["analysis_run_id"]
    run_count = database.fetch_one("SELECT COUNT(*) AS count FROM analysis_runs")
    assert run_count is not None
    assert run_count["count"] == 1


def test_real_mode_without_key_is_blocked_and_never_falls_back(
    client: FlaskClient, database: PluginDatabase
) -> None:
    project_id = _project(client)
    version_id = _prd(client, project_id)["version_id"]
    response = client.post(
        f"/api/v1/prd-versions/{version_id}/analysis-runs",
        json={"provider_mode": "real"},
        headers={"Idempotency-Key": "missing-key"},
    )
    run = response.get_json()["data"]
    assert response.status_code == 202
    assert run["status"] == "blocked"
    assert run["provider"] == "deepseek"
    assert run["provider_mode"] == "real"
    requirement_count = database.fetch_one("SELECT COUNT(*) AS count FROM requirements")
    call_count = database.fetch_one("SELECT COUNT(*) AS count FROM llm_call_logs")
    assert requirement_count is not None
    assert call_count is not None
    assert requirement_count["count"] == 0
    assert call_count["count"] == 0


def test_analysis_and_requirements_not_found(client: FlaskClient) -> None:
    assert client.get("/api/v1/analysis-runs/ANR-MISSING").status_code == 404
    assert client.get("/api/v1/analysis-runs/ANR-MISSING/requirements").status_code == 404


def test_migration_contains_required_tables(database: PluginDatabase) -> None:
    rows = database.fetch_all("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    names = {row["name"] for row in rows}
    assert {
        "projects",
        "prd_documents",
        "prd_versions",
        "prompt_versions",
        "analysis_runs",
        "analysis_batches",
        "llm_call_logs",
        "requirement_candidates",
        "requirements",
        "requirement_relationships",
    } <= names
    database.migrate()
    migration_count = database.fetch_one("SELECT COUNT(*) AS count FROM schema_migrations")
    assert migration_count is not None
    assert migration_count["count"] == 11
