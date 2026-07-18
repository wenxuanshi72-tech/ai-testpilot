from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sut.backend.app.errors import ApiError, ErrorDetail

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")
USERNAME_MAX_LENGTH = 32
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128


def _required_string(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value:
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            "The request is invalid.",
            [ErrorDetail(field, "required_string")],
        )
    return value


def normalize_username(value: str) -> str:
    username = value.strip().lower()
    details: list[ErrorDetail] = []
    if not username:
        details.append(ErrorDetail("username", "required_string"))
    elif len(username) > USERNAME_MAX_LENGTH:
        details.append(ErrorDetail("username", "too_long"))
    elif not USERNAME_PATTERN.fullmatch(username):
        details.append(ErrorDetail("username", "invalid_format"))
    # Protected seeded defect: REQ-AUTH-USERNAME-001 minimum length is intentionally omitted.
    if details:
        raise ApiError(400, "VALIDATION_ERROR", "The request is invalid.", details)
    return username


def validate_password(value: str) -> str:
    valid = (
        PASSWORD_MIN_LENGTH <= len(value) <= PASSWORD_MAX_LENGTH
        and any(character.islower() for character in value)
        and any(character.isupper() for character in value)
        and any(character.isdigit() for character in value)
    )
    if not valid:
        raise ApiError(
            400,
            "VALIDATION_ERROR",
            "The request is invalid.",
            [ErrorDetail("password", "password_policy")],
        )
    return value


@dataclass(frozen=True)
class RegistrationInput:
    username: str
    password: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> RegistrationInput:
        username = normalize_username(_required_string(payload, "username"))
        password = validate_password(_required_string(payload, "password"))
        confirmation = _required_string(payload, "password_confirmation")
        if confirmation != password:
            raise ApiError(
                400,
                "VALIDATION_ERROR",
                "The request is invalid.",
                [ErrorDetail("password_confirmation", "mismatch")],
            )
        return cls(username=username, password=password)


@dataclass(frozen=True)
class LoginInput:
    username: str
    password: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> LoginInput:
        return cls(
            username=normalize_username(_required_string(payload, "username")),
            password=_required_string(payload, "password"),
        )
