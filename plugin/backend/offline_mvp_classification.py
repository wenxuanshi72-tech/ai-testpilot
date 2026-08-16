from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from plugin.backend.app.mvp_baseline import propose_mvp_classification

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE = PROJECT_ROOT / "instance" / "plugin.db"


def build_offline_mvp_plan(database_path: Path, run_id: str) -> dict[str, Any]:
    connection = sqlite3.connect(
        f"file:{database_path.resolve().as_posix()}?mode=ro", uri=True, timeout=5
    )
    connection.row_factory = sqlite3.Row
    try:
        run = connection.execute(
            "SELECT status,candidate_count,collection_hash FROM test_generation_runs "
            "WHERE test_generation_run_id=?",
            (run_id,),
        ).fetchone()
        if run is None:
            raise ValueError("GENERATION_RUN_NOT_FOUND")
        rows = connection.execute(
            "SELECT payload_json FROM test_case_candidates WHERE test_generation_run_id=? "
            "ORDER BY case_type,case_id",
            (run_id,),
        ).fetchall()
        candidates = [json.loads(str(row["payload_json"])) for row in rows]
        if len(candidates) != int(run["candidate_count"]):
            raise ValueError("CANDIDATE_COUNT_MISMATCH")
        plan = propose_mvp_classification(candidates)
        return {
            "generation_run_id": run_id,
            "source_status": str(run["status"]),
            "source_collection_hash": str(run["collection_hash"]),
            "database_writes": 0,
            **plan,
        }
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args()
    print(json.dumps(build_offline_mvp_plan(args.database, args.run_id), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
