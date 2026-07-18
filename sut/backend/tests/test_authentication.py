from __future__ import annotations

from datetime import timedelta

from flask import Flask
from flask.testing import FlaskClient

from sut.backend.app.extensions import db
from sut.backend.app.models import UserSession
from sut.backend.app.time import utc_now
from sut.backend.tests.conftest import registration_payload
from sut.backend.tests.helpers import response_json


def _register_and_logout(client: FlaskClient, username: str = "login_user") -> None:
    assert client.post("/api/auth/register", json=registration_payload(username)).status_code == 201
    assert client.post("/api/auth/logout").status_code == 204


def test_login_and_current_user(client: FlaskClient) -> None:
    _register_and_logout(client)

    login = client.post("/api/auth/login", json={"username": "LOGIN_USER", "password": "Test1234"})
    current_user = client.get("/api/auth/me")

    assert login.status_code == 200
    assert current_user.status_code == 200
    assert response_json(current_user)["data"]["username"] == "login_user"


def test_wrong_password_and_unknown_user_are_generic(client: FlaskClient) -> None:
    _register_and_logout(client)

    wrong = client.post("/api/auth/login", json={"username": "login_user", "password": "Wrong1234"})
    missing = client.post(
        "/api/auth/login", json={"username": "missing_user", "password": "Wrong1234"}
    )

    assert wrong.status_code == missing.status_code == 401
    assert response_json(wrong)["error"] == response_json(missing)["error"]
    assert response_json(wrong)["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_requires_authentication(client: FlaskClient) -> None:
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response_json(response)["error"]["code"] == "AUTHENTICATION_REQUIRED"


def test_logout_revokes_session_and_is_idempotent(app: Flask, client: FlaskClient) -> None:
    client.post("/api/auth/register", json=registration_payload("logout_user"))

    first = client.post("/api/auth/logout")
    after_logout = client.get("/api/auth/me")
    second = client.post("/api/auth/logout")

    assert first.status_code == second.status_code == 204
    assert "Max-Age=0" in first.headers["Set-Cookie"]
    assert after_logout.status_code == 401
    with app.app_context():
        session = db.session.scalar(db.select(UserSession))
        assert session is not None and session.revoked_at is not None


def test_absolute_session_expiry_revokes_access(app: Flask, client: FlaskClient) -> None:
    client.post("/api/auth/register", json=registration_payload("expired_user"))
    with app.app_context():
        session = db.session.scalar(db.select(UserSession))
        assert session is not None
        session.expires_at = utc_now() - timedelta(seconds=1)
        db.session.commit()

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    with app.app_context():
        session = db.session.scalar(db.select(UserSession))
        assert session is not None and session.revoked_at is not None


def test_idle_session_expiry_revokes_access(app: Flask, client: FlaskClient) -> None:
    client.post("/api/auth/register", json=registration_payload("idle_user"))
    with app.app_context():
        session = db.session.scalar(db.select(UserSession))
        assert session is not None
        session.last_seen_at = utc_now() - timedelta(seconds=1801)
        db.session.commit()

    assert client.get("/api/auth/me").status_code == 401


def test_manually_revoked_session_is_denied(app: Flask, client: FlaskClient) -> None:
    client.post("/api/auth/register", json=registration_payload("revoked_user"))
    with app.app_context():
        session = db.session.scalar(db.select(UserSession))
        assert session is not None
        session.revoked_at = utc_now()
        db.session.commit()

    assert client.get("/api/auth/me").status_code == 401
