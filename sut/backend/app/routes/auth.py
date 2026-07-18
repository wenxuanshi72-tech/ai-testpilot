from __future__ import annotations

from typing import Any, cast

from flask import Blueprint, Response, current_app, make_response, request

from sut.backend.app.errors import ApiError, ErrorDetail
from sut.backend.app.repositories import AuthRepository
from sut.backend.app.responses import success_response, user_payload
from sut.backend.app.services import AuthenticatedSession, AuthService
from sut.backend.app.validation import LoginInput, RegistrationInput

auth_blueprint = Blueprint("auth", __name__, url_prefix="/api/auth")


def _service() -> AuthService:
    return AuthService(
        AuthRepository(),
        absolute_seconds=int(current_app.config["SESSION_ABSOLUTE_SECONDS"]),
        idle_seconds=int(current_app.config["SESSION_IDLE_SECONDS"]),
    )


def _json_object() -> dict[str, Any]:
    if not request.is_json:
        raise ApiError(415, "UNSUPPORTED_MEDIA_TYPE", "Content-Type must be application/json.")
    payload = request.get_json(silent=False)
    if not isinstance(payload, dict):
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            "The request is invalid.",
            [ErrorDetail("body", "object_required")],
        )
    return cast(dict[str, Any], payload)


def _with_session_cookie(
    response_and_status: tuple[Response, int], authenticated: AuthenticatedSession
) -> tuple[Response, int]:
    response, status_code = response_and_status
    response.set_cookie(
        current_app.config["SESSION_COOKIE_NAME"],
        authenticated.raw_token,
        max_age=int(current_app.config["SESSION_ABSOLUTE_SECONDS"]),
        expires=authenticated.expires_at,
        secure=bool(current_app.config["SESSION_COOKIE_SECURE"]),
        httponly=True,
        samesite="Lax",
        path="/",
    )
    return response, status_code


@auth_blueprint.post("/register")
def register() -> tuple[Response, int]:
    authenticated = _service().register(RegistrationInput.from_payload(_json_object()))
    return _with_session_cookie(
        success_response(user_payload(authenticated.user), status_code=201), authenticated
    )


@auth_blueprint.post("/login")
def login() -> tuple[Response, int]:
    authenticated = _service().login(LoginInput.from_payload(_json_object()))
    return _with_session_cookie(success_response(user_payload(authenticated.user)), authenticated)


@auth_blueprint.get("/me")
def me() -> tuple[Response, int]:
    raw_token = request.cookies.get(current_app.config["SESSION_COOKIE_NAME"])
    user = _service().authenticate(raw_token)
    if user is None:
        raise ApiError(401, "AUTHENTICATION_REQUIRED", "Authentication is required.")
    return success_response(user_payload(user))


@auth_blueprint.post("/logout")
def logout() -> Response:
    cookie_name = current_app.config["SESSION_COOKIE_NAME"]
    _service().logout(request.cookies.get(cookie_name))
    response = make_response("", 204)
    response.delete_cookie(
        cookie_name,
        secure=bool(current_app.config["SESSION_COOKIE_SECURE"]),
        httponly=True,
        samesite="Lax",
        path="/",
    )
    return response
