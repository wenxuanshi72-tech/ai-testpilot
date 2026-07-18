from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flask import Flask
from flask_cors import CORS

from sut.backend.app.config import Config
from sut.backend.app.errors.handlers import register_error_handlers
from sut.backend.app.extensions import db, migrate
from sut.backend.app.request_context import register_request_context
from sut.backend.app.routes.auth import auth_blueprint
from sut.backend.app.routes.health import health_blueprint
from sut.backend.app.security.origins import enforce_trusted_origin


def create_app(config_override: Mapping[str, Any] | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(Config)
    if config_override:
        app.config.from_mapping(config_override)

    db.init_app(app)
    migrate.init_app(app, db, directory=app.config["MIGRATIONS_DIR"])
    CORS(
        app,
        origins=app.config["CORS_ALLOWED_ORIGINS"],
        supports_credentials=True,
        methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    register_request_context(app)
    app.before_request(enforce_trusted_origin)
    app.register_blueprint(health_blueprint)
    app.register_blueprint(auth_blueprint)
    register_error_handlers(app)
    return app
