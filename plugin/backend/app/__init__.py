from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from flask import Flask

from plugin.backend.app.config import PluginConfig
from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.errors import register_error_handlers
from plugin.backend.app.routes import api


def create_app(config_override: Mapping[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(PluginConfig.as_mapping())
    if config_override:
        app.config.from_mapping(config_override)
    database = PluginDatabase(app.config["PLUGIN_DATABASE_URL"])
    database.migrate()
    app.extensions["plugin_database"] = database
    app.register_blueprint(api)
    register_error_handlers(app)
    return app
