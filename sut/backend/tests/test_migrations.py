from __future__ import annotations

import sqlite3
from pathlib import Path

from sut.backend.app import create_app


def test_blank_database_upgrades_to_migration_head(tmp_path: Path) -> None:
    database_path = tmp_path / "migrated.db"
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
        }
    )

    result = app.test_cli_runner().invoke(args=["db", "upgrade"])

    assert result.exit_code == 0, result.output
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            )
        }
        revision = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert {"users", "user_sessions", "alembic_version"}.issubset(tables)
    assert revision == ("0001_sut_auth",)
