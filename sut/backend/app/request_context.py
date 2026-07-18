from __future__ import annotations

import re
import secrets

from flask import Flask, Response, g, request

REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


def current_request_id() -> str:
    return str(g.request_id)


def register_request_context(app: Flask) -> None:
    @app.before_request
    def assign_request_id() -> None:
        candidate = request.headers.get("X-Request-ID", "")
        g.request_id = (
            candidate if REQUEST_ID_PATTERN.fullmatch(candidate) else f"REQ-{secrets.token_hex(12)}"
        )

    @app.after_request
    def add_request_id(response: Response) -> Response:
        response.headers["X-Request-ID"] = current_request_id()
        return response
