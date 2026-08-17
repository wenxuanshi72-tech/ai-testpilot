from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from plugin.backend.app.database import PROJECT_ROOT, PluginDatabase


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify persisted Phase 7B UI evidence.")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    arguments = parser.parse_args()
    database = PluginDatabase(f"sqlite:///{arguments.database.resolve().as_posix()}")
    run = database.fetch_one(
        "SELECT * FROM ui_test_runs WHERE ui_test_run_id=:run", {"run": arguments.run_id}
    )
    if not run or run["status"] != "completed" or int(run["total_count"]) != 3:
        raise SystemExit("UI_RUN_INVALID")
    results = database.fetch_all(
        "SELECT * FROM ui_test_results WHERE ui_test_run_id=:run ORDER BY case_id",
        {"run": arguments.run_id},
    )
    evidence = database.fetch_all(
        "SELECT e.* FROM ui_test_evidence e JOIN ui_test_results r "
        "ON r.ui_test_result_id=e.ui_test_result_id WHERE r.ui_test_run_id=:run",
        {"run": arguments.run_id},
    )
    if len(results) != 3 or len(evidence) != 3:
        raise SystemExit("UI_RESULT_OR_EVIDENCE_COUNT_INVALID")
    for item in evidence:
        payload = json.loads(str(item["evidence_json"]))
        if hashlib.sha256(_canonical(payload).encode()).hexdigest() != item["evidence_hash"]:
            raise SystemExit("UI_EVIDENCE_HASH_INVALID")
        for path_key, hash_key in (
            ("screenshot_path", "screenshot_hash"),
            ("trace_path", "trace_hash"),
        ):
            path = (PROJECT_ROOT / str(item[path_key])).resolve()
            if not path.is_relative_to(PROJECT_ROOT) or not path.is_file():
                raise SystemExit("UI_EVIDENCE_FILE_MISSING")
            if hashlib.sha256(path.read_bytes()).hexdigest() != item[hash_key]:
                raise SystemExit("UI_EVIDENCE_FILE_HASH_INVALID")
    seeded = next(row for row in results if row["case_id"] == "TC-UI-AUTH-REG-005")
    if not (
        seeded["status"] == "FAIL"
        and seeded["failure_type"] == "suspected_product_bug"
        and seeded["expected_route"] == "/register"
        and seeded["actual_route"] == "/profile"
    ):
        raise SystemExit("SEEDED_UI_DEFECT_VERDICT_INVALID")
    if database.fetch_one("PRAGMA integrity_check") != {"integrity_check": "ok"}:
        raise SystemExit("DATABASE_INTEGRITY_INVALID")
    if database.fetch_all("PRAGMA foreign_key_check"):
        raise SystemExit("DATABASE_FOREIGN_KEY_INVALID")
    print(
        json.dumps(
            {
                "run_id": arguments.run_id,
                "total": 3,
                "pass": run["pass_count"],
                "fail": run["fail_count"],
                "screenshots": 3,
                "traces": 3,
                "seeded_defect": "FAIL/suspected_product_bug",
                "integrity": "ok",
                "foreign_key_violations": 0,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
