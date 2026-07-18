from __future__ import annotations

from typing import Any

from flask import Flask, Response, current_app, jsonify
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import BadRequest, HTTPException, RequestEntityTooLarge

from sut.backend.app.errors.api_error import ApiError
from sut.backend.app.extensions import db
from sut.backend.app.request_context import current_request_id

HTTP_ERROR_CODES = {
    404: ("NOT_FOUND", "The requested resource was not found."),
    405: ("METHOD_NOT_ALLOWED", "The HTTP method is not allowed for this resource."),
    415: ("UNSUPPORTED_MEDIA_TYPE", "The request media type is not supported."),
}


def _error_response(error: ApiError) -> tuple[Response, int]:
    payload: dict[str, Any] = {
        "error": {
            "code": error.code,
            "message": error.message,
            "details": [{"field": detail.field, "code": detail.code} for detail in error.details],
            "retryable": error.retryable,
        },
        "meta": {"request_id": current_request_id()},
    }
    return jsonify(payload), error.status_code


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError) -> tuple[Response, int]:
        return _error_response(error)

    @app.errorhandler(BadRequest)
    def handle_bad_request(_error: BadRequest) -> tuple[Response, int]:
        return _error_response(
            ApiError(400, "MALFORMED_JSON", "The JSON request body is malformed.")
        )

    @app.errorhandler(RequestEntityTooLarge)
    def handle_too_large(_error: RequestEntityTooLarge) -> tuple[Response, int]:
        return _error_response(ApiError(413, "REQUEST_TOO_LARGE", "The request is too large."))

    @app.errorhandler(HTTPException)
    def handle_http_error(error: HTTPException) -> tuple[Response, int]:
        code, message = HTTP_ERROR_CODES.get(
            error.code or 500, ("HTTP_ERROR", "The HTTP request could not be completed.")
        )
        return _error_response(ApiError(error.code or 500, code, message))

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(error: SQLAlchemyError) -> tuple[Response, int]:
        db.session.rollback()
        current_app.logger.error(
            "Database operation failed request_id=%s error_type=%s",
            current_request_id(),
            type(error).__name__,
        )
        return _error_response(ApiError(500, "INTERNAL_ERROR", "An internal error occurred."))

    @app.errorhandler(Exception)
    def handle_unexpected_error(error: Exception) -> tuple[Response, int]:
        db.session.rollback()
        current_app.logger.error(
            "Unhandled application error request_id=%s error_type=%s",
            current_request_id(),
            type(error).__name__,
        )
        return _error_response(ApiError(500, "INTERNAL_ERROR", "An internal error occurred."))
