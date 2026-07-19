from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from flask import Flask
from flask.testing import FlaskClient

from plugin.backend.app import create_app
from plugin.backend.app.database import PluginDatabase


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "plugin-test.db"


@pytest.fixture
def app(database_path: Path, monkeypatch: pytest.MonkeyPatch) -> Flask:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    return create_app(
        {
            "TESTING": True,
            "PLUGIN_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "PRD_BATCH_MAX_CHARS": 700,
            "PRD_BATCH_MAX_REQUIREMENTS": 12,
            "LLM_MAX_RETRIES": 2,
            "LLM_RUN_MAX_OUTPUT_TOKENS": 26624,
        }
    )


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def database(app: Flask) -> PluginDatabase:
    return cast(PluginDatabase, app.extensions["plugin_database"])
