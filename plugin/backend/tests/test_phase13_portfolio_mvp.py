from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from scripts.verify_phase13_portfolio_mvp import PortfolioReplayError, _sha256_text, verify


def _database(path: Path, *, valid_analysis: bool = True) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE analysis_runs(
              analysis_run_id TEXT, status TEXT, provider TEXT, model TEXT
            );
            CREATE TABLE requirements(analysis_run_id TEXT);
            CREATE TABLE llm_call_logs(
              analysis_run_id TEXT, provider TEXT, model TEXT, http_status INTEGER,
              finish_reason TEXT, created_at TEXT
            );
            """
        )
        connection.execute(
            "INSERT INTO analysis_runs VALUES(?,?,?,?)",
            (
                "ANR-8D946E45913A418F899774282E8121C2",
                "succeeded" if valid_analysis else "failed",
                "deepseek",
                "deepseek-v4-pro",
            ),
        )
        connection.executemany(
            "INSERT INTO requirements VALUES(?)",
            [("ANR-8D946E45913A418F899774282E8121C2",)] * 19,
        )
        connection.execute(
            "INSERT INTO llm_call_logs VALUES(?,?,?,?,?,?)",
            (
                "ANR-8D946E45913A418F899774282E8121C2",
                "deepseek",
                "deepseek-v4-pro",
                200,
                "stop",
                "2026-08-18",
            ),
        )


def test_hash_uses_exact_persisted_canonical_text() -> None:
    payload = json.dumps({"case": "TC-API-AUTH-REG-005"}, separators=(",", ":"))
    assert _sha256_text(payload) == (
        "68071697887c133a7dcb0318ca671b5f1210bb3df39f7cb143208489e4d9b278"
    )


def test_invalid_real_analysis_is_rejected(tmp_path: Path) -> None:
    analysis = tmp_path / "analysis.db"
    _database(analysis, valid_analysis=False)
    with pytest.raises(PortfolioReplayError, match="REAL_ANALYSIS_EVIDENCE_INVALID"):
        verify(tmp_path / "missing.db", analysis)
