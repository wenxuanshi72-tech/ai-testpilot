from __future__ import annotations

from flask import Blueprint, Response

from sut.backend.app.responses import success_response

health_blueprint = Blueprint("health", __name__)


@health_blueprint.get("/api/health")
def health() -> tuple[Response, int]:
    return success_response({"status": "ok"})
