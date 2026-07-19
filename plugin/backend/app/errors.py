from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flask import Flask, jsonify, request

from plugin.backend.app.ids import new_id


@dataclass
class ApiError(Exception):
    code: str
    message: str
    status: int
    details: list[dict[str, Any]] | None = None
    retryable: bool = False


def request_id() -> str:
    supplied = request.headers.get("X-Request-ID", "").strip()
    if (
        supplied
        and len(supplied) <= 96
        and all(char.isalnum() or char in "-_." for char in supplied)
    ):
        return supplied
    return new_id("REQ")


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError) -> tuple[Any, int]:
        return jsonify(
            {
                "error": {
                    "code": error.code,
                    "message": error.message,
                    "details": error.details or [],
                    "retryable": error.retryable,
                },
                "meta": {"request_id": request_id()},
            }
        ), error.status

    @app.errorhandler(404)
    def handle_not_found(_error: Exception) -> tuple[Any, int]:
        return handle_api_error(ApiError("NOT_FOUND", "The resource was not found.", 404))

    @app.errorhandler(500)
    def handle_internal(_error: Exception) -> tuple[Any, int]:
        return handle_api_error(ApiError("INTERNAL_ERROR", "An internal error occurred.", 500))
