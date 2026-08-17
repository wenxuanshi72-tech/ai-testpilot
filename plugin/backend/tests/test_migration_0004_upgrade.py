from __future__ import annotations

import sqlite3
from pathlib import Path

from plugin.backend.app.database import MIGRATIONS_DIR, PluginDatabase


def test_existing_0003_database_upgrades_through_phase6(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "upgrade-from-0003.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations ("
            "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        for migration in sorted(MIGRATIONS_DIR.glob("000[1-3]_*.sql")):
            connection.executescript(migration.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)",
                (migration.stem,),
            )
    database = PluginDatabase(f"sqlite:///{database_path.as_posix()}")
    database.migrate()
    assert database.fetch_one("SELECT COUNT(*) AS count FROM schema_migrations") == {"count": 9}
    assert database.fetch_one("PRAGMA integrity_check") == {"integrity_check": "ok"}
    assert database.fetch_all("PRAGMA foreign_key_check") == []
    tables = {
        row["name"]
        for row in database.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "test_generation_runs" in tables
    assert {
        "test_case_reviews",
        "approved_test_case_versions",
        "frozen_baselines",
        "frozen_baseline_members",
        "immutable_execution_snapshots",
        "test_case_human_revisions",
    } <= tables
    assert {"api_test_runs", "api_test_results", "api_test_evidence"} <= tables
    assert {"ui_test_runs", "ui_test_results", "ui_test_evidence"} <= tables
