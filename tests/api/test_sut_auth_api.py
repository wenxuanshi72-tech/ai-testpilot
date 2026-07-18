from __future__ import annotations

import httpx
import pytest

from tests.api.conftest import (
    TEST_PASSWORD,
    record_evidence,
    registration_payload,
    response_json,
    unique_username,
)

pytestmark = pytest.mark.black_box


def assert_error(response: httpx.Response, code: str) -> None:
    payload = response_json(response)
    assert payload["error"]["code"] == code
    assert isinstance(payload["error"]["details"], list)
    assert payload["error"]["retryable"] is False
    assert payload["meta"]["request_id"] == response.headers["X-Request-ID"]


def test_health(api_client: httpx.Client) -> None:
    response = api_client.get("/api/health")
    record_evidence(
        case_id="API-AUTH-HEALTH-001",
        response=response,
        expected_status=200,
        requirement_ids=["AUTH-HEALTH-001"],
    )
    assert response.status_code == 200
    assert response_json(response)["data"]["status"] == "ok"


def test_register_valid_user(api_client: httpx.Client) -> None:
    username = unique_username("register")
    response = api_client.post("/api/auth/register", json=registration_payload(username))
    record_evidence(
        case_id="API-AUTH-REGISTER-001",
        response=response,
        expected_status=201,
        requirement_ids=["AUTH-REG-001", "AUTH-REG-003", "AUTH-SESSION-001"],
    )
    assert response.status_code == 201
    assert response_json(response)["data"]["username"] == username
    cookie = response.headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "SameSite=Lax" in cookie and "Path=/" in cookie


def test_reject_duplicate_username(api_client: httpx.Client) -> None:
    username = unique_username("duplicate")
    assert (
        api_client.post("/api/auth/register", json=registration_payload(username)).status_code
        == 201
    )
    response = api_client.post("/api/auth/register", json=registration_payload(username.upper()))
    record_evidence(
        case_id="API-AUTH-REGISTER-002",
        response=response,
        expected_status=409,
        requirement_ids=["AUTH-REG-005"],
    )
    assert response.status_code == 409
    assert_error(response, "USERNAME_EXISTS")


def test_reject_missing_username(api_client: httpx.Client) -> None:
    payload = registration_payload(unique_username())
    del payload["username"]
    response = api_client.post("/api/auth/register", json=payload)
    record_evidence(
        case_id="API-AUTH-REGISTER-003",
        response=response,
        expected_status=400,
        requirement_ids=["AUTH-REG-001", "AUTH-ERROR-001"],
    )
    assert response.status_code == 400
    assert_error(response, "VALIDATION_ERROR")
    assert response_json(response)["error"]["details"][0]["field"] == "username"


def test_reject_missing_password(api_client: httpx.Client) -> None:
    payload = registration_payload(unique_username())
    del payload["password"]
    response = api_client.post("/api/auth/register", json=payload)
    record_evidence(
        case_id="API-AUTH-REGISTER-004",
        response=response,
        expected_status=400,
        requirement_ids=["AUTH-REG-003", "AUTH-ERROR-001"],
    )
    assert response.status_code == 400
    assert_error(response, "VALIDATION_ERROR")
    assert response_json(response)["error"]["details"][0]["field"] == "password"


def test_reject_non_json_request(api_client: httpx.Client) -> None:
    response = api_client.post("/api/auth/register", content="username=example")
    record_evidence(
        case_id="API-AUTH-REGISTER-005",
        response=response,
        expected_status=415,
        requirement_ids=["AUTH-HTTP-001"],
    )
    assert response.status_code == 415
    assert_error(response, "UNSUPPORTED_MEDIA_TYPE")


def test_reject_malformed_json(api_client: httpx.Client) -> None:
    response = api_client.post(
        "/api/auth/register", content=b'{"username":', headers={"Content-Type": "application/json"}
    )
    record_evidence(
        case_id="API-AUTH-REGISTER-006",
        response=response,
        expected_status=400,
        requirement_ids=["AUTH-HTTP-002"],
    )
    assert response.status_code == 400
    assert_error(response, "MALFORMED_JSON")


def test_reject_illegal_username(api_client: httpx.Client) -> None:
    response = api_client.post("/api/auth/register", json=registration_payload("bad-name"))
    record_evidence(
        case_id="API-AUTH-REGISTER-007",
        response=response,
        expected_status=400,
        requirement_ids=["AUTH-REG-002"],
    )
    assert response.status_code == 400
    assert response_json(response)["error"]["details"][0]["code"] == "invalid_format"


def test_reject_long_username(api_client: httpx.Client) -> None:
    response = api_client.post("/api/auth/register", json=registration_payload("x" * 33))
    record_evidence(
        case_id="API-AUTH-REGISTER-008",
        response=response,
        expected_status=400,
        requirement_ids=["REQ-AUTH-USERNAME-001"],
    )
    assert response.status_code == 400
    assert response_json(response)["error"]["details"][0]["code"] == "too_long"


def test_reject_weak_password(api_client: httpx.Client) -> None:
    payload = {"username": unique_username(), "password": "weak", "password_confirmation": "weak"}
    response = api_client.post("/api/auth/register", json=payload)
    record_evidence(
        case_id="API-AUTH-REGISTER-009",
        response=response,
        expected_status=400,
        requirement_ids=["AUTH-REG-003"],
    )
    assert response.status_code == 400
    assert response_json(response)["error"]["details"][0]["code"] == "password_policy"


def test_login_success(api_client: httpx.Client) -> None:
    username = unique_username("login")
    assert (
        api_client.post("/api/auth/register", json=registration_payload(username)).status_code
        == 201
    )
    assert api_client.post("/api/auth/logout").status_code == 204
    response = api_client.post(
        "/api/auth/login", json={"username": username, "password": TEST_PASSWORD}
    )
    record_evidence(
        case_id="API-AUTH-LOGIN-001",
        response=response,
        expected_status=200,
        requirement_ids=["AUTH-LOGIN-001", "AUTH-SESSION-001"],
    )
    assert response.status_code == 200
    assert response_json(response)["data"]["username"] == username


def test_reject_wrong_password(api_client: httpx.Client) -> None:
    username = unique_username("wrong")
    assert (
        api_client.post("/api/auth/register", json=registration_payload(username)).status_code
        == 201
    )
    response = api_client.post(
        "/api/auth/login", json={"username": username, "password": "Wrong1234"}
    )
    record_evidence(
        case_id="API-AUTH-LOGIN-002",
        response=response,
        expected_status=401,
        requirement_ids=["AUTH-LOGIN-002"],
    )
    assert response.status_code == 401
    assert_error(response, "INVALID_CREDENTIALS")


def test_reject_nonexistent_user(api_client: httpx.Client) -> None:
    response = api_client.post(
        "/api/auth/login", json={"username": unique_username("missing"), "password": TEST_PASSWORD}
    )
    record_evidence(
        case_id="API-AUTH-LOGIN-003",
        response=response,
        expected_status=401,
        requirement_ids=["AUTH-LOGIN-002"],
    )
    assert response.status_code == 401
    assert_error(response, "INVALID_CREDENTIALS")


def test_authenticated_me(api_client: httpx.Client) -> None:
    username = unique_username("current")
    assert (
        api_client.post("/api/auth/register", json=registration_payload(username)).status_code
        == 201
    )
    response = api_client.get("/api/auth/me")
    record_evidence(
        case_id="API-AUTH-ME-001",
        response=response,
        expected_status=200,
        requirement_ids=["AUTH-ME-001", "AUTH-SESSION-002"],
    )
    assert response.status_code == 200
    assert response_json(response)["data"]["username"] == username


def test_unauthenticated_me(api_client: httpx.Client) -> None:
    response = api_client.get("/api/auth/me")
    record_evidence(
        case_id="API-AUTH-ME-002",
        response=response,
        expected_status=401,
        requirement_ids=["AUTH-ME-002"],
    )
    assert response.status_code == 401
    assert_error(response, "AUTHENTICATION_REQUIRED")


def test_logout(api_client: httpx.Client) -> None:
    assert (
        api_client.post(
            "/api/auth/register", json=registration_payload(unique_username("logout"))
        ).status_code
        == 201
    )
    response = api_client.post("/api/auth/logout")
    record_evidence(
        case_id="API-AUTH-LOGOUT-001",
        response=response,
        expected_status=204,
        requirement_ids=["AUTH-LOGOUT-001"],
    )
    assert response.status_code == 204
    assert response.content == b""
    assert "Max-Age=0" in response.headers["Set-Cookie"]


def test_logout_invalidates_session(api_client: httpx.Client) -> None:
    assert (
        api_client.post(
            "/api/auth/register", json=registration_payload(unique_username("revoke"))
        ).status_code
        == 201
    )
    assert api_client.post("/api/auth/logout").status_code == 204
    response = api_client.get("/api/auth/me")
    record_evidence(
        case_id="API-AUTH-SESSION-001",
        response=response,
        expected_status=401,
        requirement_ids=["AUTH-LOGOUT-001", "AUTH-ME-002"],
    )
    assert response.status_code == 401
    assert_error(response, "AUTHENTICATION_REQUIRED")


def test_cookie_maintains_session(api_client: httpx.Client) -> None:
    username = unique_username("cookie")
    assert (
        api_client.post("/api/auth/register", json=registration_payload(username)).status_code
        == 201
    )
    response = api_client.get("/api/auth/me")
    record_evidence(
        case_id="API-AUTH-SESSION-002",
        response=response,
        expected_status=200,
        requirement_ids=["AUTH-SESSION-002", "AUTH-ME-001"],
    )
    assert response.status_code == 200
    assert response_json(response)["data"]["username"] == username


def test_request_id_propagation(api_client: httpx.Client) -> None:
    expected_request_id = "REQ-phase3-black-box"
    response = api_client.get("/api/health", headers={"X-Request-ID": expected_request_id})
    record_evidence(
        case_id="API-AUTH-REQUEST-001",
        response=response,
        expected_status=200,
        requirement_ids=["AUTH-ERROR-001"],
    )
    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == expected_request_id
    assert response_json(response)["meta"]["request_id"] == expected_request_id


def test_uniform_error_envelope(api_client: httpx.Client) -> None:
    response = api_client.get("/api/not-found")
    record_evidence(
        case_id="API-AUTH-ERROR-001",
        response=response,
        expected_status=404,
        requirement_ids=["AUTH-ERROR-001"],
    )
    assert response.status_code == 404
    assert_error(response, "NOT_FOUND")


@pytest.mark.known_defect
@pytest.mark.xfail(
    strict=True,
    reason="BUG-AUTH-001: SUT intentionally omits the username minimum-length validation",
)
def test_formal_requirement_rejects_five_character_username(api_client: httpx.Client) -> None:
    response = api_client.post("/api/auth/register", json=registration_payload("z1234"))
    record_evidence(
        case_id="API-AUTH-SEED-001",
        response=response,
        expected_status=400,
        requirement_ids=["REQ-AUTH-USERNAME-001"],
        bug_id="BUG-AUTH-001",
        classification="known_seeded_product_defect",
    )
    assert response.status_code == 400
