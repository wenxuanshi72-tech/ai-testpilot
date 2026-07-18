from __future__ import annotations

from flask import current_app, request

from sut.backend.app.errors import ApiError


def enforce_trusted_origin() -> None:
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return
    origin = request.headers.get("Origin")
    if origin is None:
        return
    allowed_origins = current_app.config["CORS_ALLOWED_ORIGINS"]
    if origin not in allowed_origins:
        raise ApiError(403, "ORIGIN_NOT_ALLOWED", "The request origin is not allowed.")
