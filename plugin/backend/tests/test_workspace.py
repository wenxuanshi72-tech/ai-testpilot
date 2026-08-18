from __future__ import annotations

from flask.testing import FlaskClient

from plugin.backend.app.database import PluginDatabase


def test_workspace_empty_state_is_real_and_read_only(client: FlaskClient) -> None:
    response = client.get("/api/v1/workspace")
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["project"] is None
    assert payload["metrics"]["requirements"] == 0


def test_workspace_reads_project_without_creating_workflow_data(
    client: FlaskClient, database: PluginDatabase
) -> None:
    project = database.create_project("Portfolio workspace")
    response = client.get("/api/v1/workspace")
    assert response.status_code == 200
    payload = response.get_json()["data"]
    assert payload["project"]["project_id"] == project["project_id"]
    assert payload["meta"]["source"] == "plugin.db"
    assert database.fetch_one("SELECT COUNT(*) AS count FROM analysis_runs") == {"count": 0}
