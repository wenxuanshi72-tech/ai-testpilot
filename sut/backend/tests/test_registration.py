from __future__ import annotations

import re

import pytest
from flask import Flask
from flask.testing import FlaskClient
from werkzeug.security import check_password_hash

from sut.backend.app.extensions import db
from sut.backend.app.models import User, UserSession
from sut.backend.tests.conftest import registration_payload
from sut.backend.tests.helpers import response_json


def test_registration_persists_hash_and_opaque_session(app: Flask, client: FlaskClient) -> None:
    response = client.post("/api/auth/register", json=registration_payload(" Example_User "))

    assert response.status_code == 201
    assert response_json(response)["data"]["username"] == "example_user"
    assert "password" not in response.get_data(as_text=True).lower()
    cookie = response.headers["Set-Cookie"]
    raw_token = re.search(r"sut_session=([^;]+)", cookie)
    assert raw_token is not None

    with app.app_context():
        user = db.session.scalar(db.select(User))
        session = db.session.scalar(db.select(UserSession))
        assert user is not None
        assert session is not None
        assert user.password_hash != "Test1234"
        assert check_password_hash(user.password_hash, "Test1234")
        assert session.token_hash != raw_token.group(1)
        assert len(session.token_hash) == 64


def test_seeded_defect_allows_five_character_username(client: FlaskClient) -> None:
    """Internal sentinel, not formal REQ-AUTH-USERNAME-001 acceptance."""
    response = client.post("/api/auth/register", json=registration_payload("z1234"))

    assert response.status_code == 201
    assert response_json(response)["data"]["username"] == "z1234"


def test_duplicate_username_is_case_insensitive(client: FlaskClient) -> None:
    first = client.post("/api/auth/register", json=registration_payload("Unique_User"))
    second = client.post("/api/auth/register", json=registration_payload("unique_user"))

    assert first.status_code == 201
    assert second.status_code == 409
    assert response_json(second)["error"]["code"] == "USERNAME_EXISTS"


@pytest.mark.parametrize("field", ["username", "password", "password_confirmation"])
def test_registration_requires_all_fields(client: FlaskClient, field: str) -> None:
    payload = registration_payload()
    del payload[field]

    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 400
    assert response_json(response)["error"]["code"] == "VALIDATION_ERROR"
    assert response_json(response)["error"]["details"][0]["field"] == field


@pytest.mark.parametrize(
    ("field", "value"),
    [("username", 123), ("password", 123), ("username", ""), ("password", "")],
)
def test_registration_rejects_invalid_field_types_and_empty_values(
    client: FlaskClient, field: str, value: object
) -> None:
    payload: dict[str, object] = dict(registration_payload())
    payload[field] = value

    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 400
    assert response_json(response)["error"]["details"][0] == {
        "field": field,
        "code": "required_string",
    }


def test_password_confirmation_must_match(client: FlaskClient) -> None:
    payload = registration_payload()
    payload["password_confirmation"] = "Different123"

    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 400
    assert response_json(response)["error"]["details"] == [
        {"field": "password_confirmation", "code": "mismatch"}
    ]


@pytest.mark.parametrize("username", ["bad-name", "bad name", "x" * 33])
def test_username_format_and_maximum_are_enforced(client: FlaskClient, username: str) -> None:
    response = client.post("/api/auth/register", json=registration_payload(username))

    assert response.status_code == 400
    assert response_json(response)["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize("password", ["short1A", "alllowercase1", "ALLUPPERCASE1", "NoDigitsHere"])
def test_password_policy_is_enforced(client: FlaskClient, password: str) -> None:
    payload = registration_payload()
    payload["password"] = password
    payload["password_confirmation"] = password

    response = client.post("/api/auth/register", json=payload)

    assert response.status_code == 400
    assert response_json(response)["error"]["details"] == [
        {"field": "password", "code": "password_policy"}
    ]


def test_content_type_malformed_json_and_non_object_are_rejected(client: FlaskClient) -> None:
    non_json = client.post("/api/auth/register", data="username=test")
    malformed = client.post(
        "/api/auth/register", data='{"username":', content_type="application/json"
    )
    array_body = client.post("/api/auth/register", json=[])

    assert non_json.status_code == 415
    assert response_json(non_json)["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert malformed.status_code == 400
    assert response_json(malformed)["error"]["code"] == "MALFORMED_JSON"
    assert array_body.status_code == 400
    assert response_json(array_body)["error"]["details"][0]["code"] == "object_required"


def test_oversized_request_is_rejected_before_parsing(client: FlaskClient) -> None:
    response = client.post(
        "/api/auth/register",
        data=b"{" + (b"x" * 20000),
        content_type="application/json",
    )

    assert response.status_code == 413
    assert response_json(response)["error"]["code"] == "REQUEST_TOO_LARGE"
