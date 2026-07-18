from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from sut.backend.app import create_app
from sut.backend.app.extensions import db


@pytest.fixture
def app(tmp_path: Path) -> Iterator[Flask]:
    database_path = tmp_path / "sut-test.db"
    application = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
            "SESSION_COOKIE_SECURE": False,
            "CORS_ALLOWED_ORIGINS": ["http://127.0.0.1:5173"],
        }
    )
    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


def registration_payload(username: str = "example_user") -> dict[str, str]:
    return {
        "username": username,
        "password": "Test1234",
        "password_confirmation": "Test1234",
    }
