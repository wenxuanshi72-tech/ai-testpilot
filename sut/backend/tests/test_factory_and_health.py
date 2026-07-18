from __future__ import annotations

from pathlib import Path

from flask.testing import FlaskClient

from sut.backend.app import create_app
from sut.backend.tests.helpers import response_json


def test_create_app_uses_explicit_configuration(tmp_path: Path) -> None:
    database_path = tmp_path / "factory.db"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
        }
    )

    assert app.testing is True
    assert str(app.config["SQLALCHEMY_DATABASE_URI"]).endswith("factory.db")
    assert "/api/auth/login" in {str(rule) for rule in app.url_map.iter_rules()}


def test_health_is_non_sensitive_and_has_request_id(client: FlaskClient) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "REQ-test-health"})

    assert response.status_code == 200
    assert response.json == {
        "data": {"status": "ok"},
        "meta": {"request_id": "REQ-test-health"},
    }
    assert response.headers["X-Request-ID"] == "REQ-test-health"
    assert "database" not in response.get_data(as_text=True).lower()


def test_invalid_request_id_is_replaced(client: FlaskClient) -> None:
    response = client.get("/api/health", headers={"X-Request-ID": "invalid request id"})

    request_id = response.headers["X-Request-ID"]
    assert request_id.startswith("REQ-")
    assert request_id != "invalid request id"


def test_not_found_and_method_errors_use_contract(client: FlaskClient) -> None:
    not_found = client.get("/api/unknown")
    not_allowed = client.put("/api/health")

    assert not_found.status_code == 404
    assert response_json(not_found)["error"]["code"] == "NOT_FOUND"
    assert not_allowed.status_code == 405
    assert response_json(not_allowed)["error"]["code"] == "METHOD_NOT_ALLOWED"
    assert response_json(not_found)["meta"]["request_id"] == not_found.headers["X-Request-ID"]
