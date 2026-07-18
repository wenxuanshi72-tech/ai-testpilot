from __future__ import annotations

from typing import Any

from flask import Response, jsonify

from sut.backend.app.models import User
from sut.backend.app.request_context import current_request_id
from sut.backend.app.time import to_rfc3339


def user_payload(user: User) -> dict[str, Any]:
    return {
        "user_id": user.user_id,
        "username": user.username,
        "created_at": to_rfc3339(user.created_at),
    }


def success_response(data: dict[str, Any], status_code: int = 200) -> tuple[Response, int]:
    return jsonify({"data": data, "meta": {"request_id": current_request_id()}}), status_code
