from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE_DATABASE = ROOT / "instance" / "plugin.db"
DEFAULT_ANALYSIS_DATABASE = ROOT / "tmp" / "phase13-e2e" / "E2E-20260818T072720Z" / "plugin.db"
ANALYSIS_RUN_ID = "ANR-8D946E45913A418F899774282E8121C2"
BASELINE_ID = "FBL-5BCEA5DA11144E9BB47C545AD73919DD"
BUG_ID = "BUG-AUTH-001"
REPORT_ID = "RPT-BE5D133ABFB54EF2A4AFEFC82D86A189"
SEEDED_CASES = {"TC-API-AUTH-REG-005", "TC-UI-AUTH-REG-005"}


class PortfolioReplayError(RuntimeError):
    pass


def _connect(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise PortfolioReplayError(f"DATABASE_NOT_FOUND:{path.name}")
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True, timeout=5)
    connection.row_factory = sqlite3.Row
    return connection


def _one(connection: sqlite3.Connection, sql: str, values: tuple[Any, ...] = ()) -> sqlite3.Row:
    row = connection.execute(sql, values).fetchone()
    if row is None:
        raise PortfolioReplayError("EXPECTED_RECORD_NOT_FOUND")
    return cast(sqlite3.Row, row)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _database_health(connection: sqlite3.Connection) -> dict[str, Any]:
    integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    if integrity != "ok" or foreign_keys:
        raise PortfolioReplayError("DATABASE_INTEGRITY_FAILED")
    return {"integrity_check": integrity, "foreign_key_violations": foreign_keys}


def _verify_analysis(path: Path) -> dict[str, Any]:
    with _connect(path) as connection:
        run = _one(
            connection,
            "SELECT analysis_run_id,status,provider,model FROM analysis_runs "
            "WHERE analysis_run_id=?",
            (ANALYSIS_RUN_ID,),
        )
        requirements = int(
            _one(
                connection,
                "SELECT COUNT(*) AS count FROM requirements WHERE analysis_run_id=?",
                (ANALYSIS_RUN_ID,),
            )["count"]
        )
        calls = connection.execute(
            "SELECT provider,model,http_status,finish_reason FROM llm_call_logs "
            "WHERE analysis_run_id=? ORDER BY created_at",
            (ANALYSIS_RUN_ID,),
        ).fetchall()
        if (
            run["status"] != "succeeded"
            or run["provider"] != "deepseek"
            or run["model"] != "deepseek-v4-pro"
            or requirements != 19
            or not calls
        ):
            raise PortfolioReplayError("REAL_ANALYSIS_EVIDENCE_INVALID")
        if any(
            row["provider"] != "deepseek"
            or row["model"] != "deepseek-v4-pro"
            or int(row["http_status"] or 0) != 200
            or row["finish_reason"] != "stop"
            for row in calls
        ):
            raise PortfolioReplayError("REAL_ANALYSIS_CALL_EVIDENCE_INVALID")
        return {
            "analysis_run_id": ANALYSIS_RUN_ID,
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "requirements": requirements,
            "content_calls": len(calls),
            "database": _database_health(connection),
        }


def _verify_reference(path: Path) -> dict[str, Any]:
    with _connect(path) as connection:
        baseline = _one(
            connection,
            "SELECT * FROM frozen_baselines WHERE frozen_baseline_id=?",
            (BASELINE_ID,),
        )
        if baseline["status"] != "frozen":
            raise PortfolioReplayError("MVP_BASELINE_NOT_FROZEN")
        snapshots = connection.execute(
            "SELECT s.snapshot_json,s.snapshot_hash FROM immutable_execution_snapshots s "
            "JOIN frozen_baseline_members m ON "
            "m.frozen_baseline_member_id=s.frozen_baseline_member_id "
            "WHERE m.frozen_baseline_id=?",
            (BASELINE_ID,),
        ).fetchall()
        if len(snapshots) != 10 or any(
            _sha256_text(str(row["snapshot_json"])) != row["snapshot_hash"] for row in snapshots
        ):
            raise PortfolioReplayError("MVP_SNAPSHOT_SET_INVALID")

        before_api = _one(
            connection,
            "SELECT * FROM api_test_runs WHERE api_test_run_id="
            "(SELECT api_test_run_id FROM canonical_test_reports "
            "WHERE canonical_test_report_id=?)",
            (REPORT_ID,),
        )
        before_ui = _one(
            connection,
            "SELECT * FROM ui_test_runs WHERE ui_test_run_id="
            "(SELECT ui_test_run_id FROM canonical_test_reports "
            "WHERE canonical_test_report_id=?)",
            (REPORT_ID,),
        )
        if int(before_api["fail_count"]) < 1 or int(before_ui["fail_count"]) < 1:
            raise PortfolioReplayError("PRE_FIX_FAILURE_EVIDENCE_MISSING")

        bug = _one(
            connection,
            "SELECT * FROM canonical_bug_records WHERE bug_id=? AND bug_version=1",
            (BUG_ID,),
        )
        report = _one(
            connection,
            "SELECT * FROM canonical_test_reports WHERE canonical_test_report_id=?",
            (REPORT_ID,),
        )
        if (
            _sha256_text(str(bug["canonical_json"])) != bug["canonical_hash"]
            or _sha256_text(str(report["canonical_json"])) != report["canonical_hash"]
        ):
            raise PortfolioReplayError("BUG_OR_REPORT_HASH_INVALID")
        sources = connection.execute(
            "SELECT case_id FROM canonical_bug_sources WHERE canonical_bug_record_id=?",
            (bug["canonical_bug_record_id"],),
        ).fetchall()
        if {str(row["case_id"]) for row in sources} != SEEDED_CASES:
            raise PortfolioReplayError("BUG_SEEDED_TRACE_INVALID")

        regression = _one(
            connection,
            "SELECT * FROM defect_regression_runs WHERE canonical_bug_record_id=? "
            "ORDER BY rowid DESC LIMIT 1",
            (bug["canonical_bug_record_id"],),
        )
        if (
            regression["status"] != "completed"
            or regression["api_seeded_before"] != "FAIL"
            or regression["api_seeded_after"] != "PASS"
            or regression["ui_seeded_before"] != "FAIL"
            or regression["ui_seeded_after"] != "PASS"
            or _sha256_text(str(regression["trace_json"])) != regression["trace_hash"]
        ):
            raise PortfolioReplayError("REGRESSION_TRACE_INVALID")
        status_event = _one(
            connection,
            "SELECT * FROM bug_status_events WHERE defect_regression_run_id=?",
            (regression["defect_regression_run_id"],),
        )
        if status_event["from_status"] != "open" or status_event["to_status"] != "closed":
            raise PortfolioReplayError("BUG_CLOSURE_INVALID")

        return {
            "frozen_baseline_id": BASELINE_ID,
            "immutable_snapshots": len(snapshots),
            "pre_fix_runs": {
                "api": before_api["api_test_run_id"],
                "ui": before_ui["ui_test_run_id"],
            },
            "bug_id": BUG_ID,
            "bug_record_id": bug["canonical_bug_record_id"],
            "report_id": REPORT_ID,
            "regression_run_id": regression["defect_regression_run_id"],
            "seeded_transitions": {
                "TC-API-AUTH-REG-005": "FAIL->PASS",
                "TC-UI-AUTH-REG-005": "FAIL->PASS",
            },
            "effective_bug_status": "closed",
            "database": _database_health(connection),
        }


def verify(reference_database: Path, analysis_database: Path) -> dict[str, Any]:
    return {
        "status": "PASS",
        "mode": "portfolio_mvp_evidence_replay",
        "provider_calls_performed": 0,
        "new_runs_created": 0,
        "truthfulness": {
            "new_candidate_generation_claimed": False,
            "historical_generation_failures_preserved": True,
            "existing_real_evidence_revalidated": True,
        },
        "real_provider_analysis": _verify_analysis(analysis_database),
        "mvp_execution_chain": _verify_reference(reference_database),
        "next_gate": "PHASE13_DOCUMENTATION_AND_QUALITY_GATES",
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the Phase 13 portfolio MVP evidence replay."
    )
    parser.add_argument("--database", type=Path, default=DEFAULT_REFERENCE_DATABASE)
    parser.add_argument("--analysis-database", type=Path, default=DEFAULT_ANALYSIS_DATABASE)
    arguments = parser.parse_args()
    print(
        json.dumps(
            verify(arguments.database, arguments.analysis_database),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
