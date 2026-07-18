from __future__ import annotations

import logging
from pathlib import Path

import pytest
from _pytest.logging import LogCaptureFixture
from flask import Flask
from flask.testing import FlaskClient

from sut.backend.app import create_app
from sut.backend.app.extensions import db
from sut.backend.app.models import User, UserSession
from sut.backend.app.services import AuthService
from sut.backend.tests.conftest import registration_payload
from sut.backend.tests.helpers import response_json


def test_cookie_security_attributes(client: FlaskClient) -> None:
    response = client.post("/api/auth/register", json=registration_payload("cookie_user"))

    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie
    assert "Path=/" in cookie
    assert "Max-Age=28800" in cookie
    assert "Secure" not in cookie


def test_secure_cookie_can_be_enabled(tmp_path: Path) -> None:
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'secure.db').as_posix()}",
            "SESSION_COOKIE_SECURE": True,
        }
    )
    with app.app_context():
        db.create_all()
    response = app.test_client().post(
        "/api/auth/register", json=registration_payload("secure_user")
    )

    assert response.status_code == 201
    assert "Secure" in response.headers["Set-Cookie"]


def test_allowed_cors_is_credentialed_without_wildcard(client: FlaskClient) -> None:
    response = client.get("/api/health", headers={"Origin": "http://127.0.0.1:5173"})

    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert response.headers["Access-Control-Allow-Origin"] != "*"


def test_untrusted_mutation_origin_is_rejected(client: FlaskClient) -> None:
    response = client.post(
        "/api/auth/register",
        json=registration_payload("origin_user"),
        headers={"Origin": "https://untrusted.example"},
    )

    assert response.status_code == 403
    assert response_json(response)["error"]["code"] == "ORIGIN_NOT_ALLOWED"
    assert "Access-Control-Allow-Origin" not in response.headers


def test_preflight_uses_exact_allowed_origin(client: FlaskClient) -> None:
    response = client.options(
        "/api/auth/logout",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"
    assert "POST" in response.headers["Access-Control-Allow-Methods"]


def test_error_logging_does_not_include_sensitive_input(
    client: FlaskClient, caplog: LogCaptureFixture
) -> None:
    password = "SensitiveTest123"
    with caplog.at_level(logging.INFO):
        response = client.post(
            "/api/auth/login", json={"username": "missing_user", "password": password}
        )

    assert response.status_code == 401
    assert password not in caplog.text
    assert "cookie" not in caplog.text.lower()


def test_unexpected_error_returns_safe_500(
    client: FlaskClient, monkeypatch: pytest.MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    def fail_register(self: AuthService, _registration: object) -> object:
        raise RuntimeError("internal sentinel detail")

    monkeypatch.setattr(AuthService, "register", fail_register)
    with caplog.at_level(logging.ERROR):
        response = client.post("/api/auth/register", json=registration_payload("failure_user"))

    body = response.get_data(as_text=True)
    assert response.status_code == 500
    assert response_json(response)["error"]["code"] == "INTERNAL_ERROR"
    assert "internal sentinel detail" not in body
    assert "RuntimeError" in caplog.text


def test_separate_database_configurations_are_isolated(tmp_path: Path) -> None:
    first_app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'first.db').as_posix()}",
        }
    )
    second_app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'second.db').as_posix()}",
        }
    )
    with first_app.app_context():
        db.create_all()
    first_app.test_client().post("/api/auth/register", json=registration_payload("isolated_user"))
    with second_app.app_context():
        db.create_all()
        assert db.session.scalar(db.select(db.func.count()).select_from(User)) == 0
        assert db.session.scalar(db.select(db.func.count()).select_from(UserSession)) == 0


def test_error_envelope_never_serializes_hashes(app: Flask, client: FlaskClient) -> None:
    client.post("/api/auth/register", json=registration_payload("hash_user"))
    with app.app_context():
        user = db.session.scalar(db.select(User))
        session = db.session.scalar(db.select(UserSession))
        assert user is not None and session is not None
        secrets = [user.password_hash, session.token_hash]

    body = client.get("/api/unknown").get_data(as_text=True)
    assert all(secret not in body for secret in secrets)
