from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "instance" / "sut.db"


def _as_bool(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _allowed_origins() -> list[str]:
    configured = os.getenv(
        "SUT_CORS_ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173"
    )
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "SUT_DATABASE_URL", f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    MAX_CONTENT_LENGTH = 16 * 1024

    SESSION_COOKIE_NAME = os.getenv("SUT_SESSION_COOKIE_NAME", "sut_session")
    SESSION_COOKIE_SECURE = _as_bool(os.getenv("SUT_SESSION_COOKIE_SECURE"), default=False)
    SESSION_ABSOLUTE_SECONDS = int(os.getenv("SUT_SESSION_ABSOLUTE_SECONDS", "28800"))
    SESSION_IDLE_SECONDS = int(os.getenv("SUT_SESSION_IDLE_SECONDS", "1800"))

    CORS_ALLOWED_ORIGINS = _allowed_origins()
    MIGRATIONS_DIR = str(PROJECT_ROOT / "sut" / "backend" / "migrations")
    TESTING = False
