from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from plugin.backend.app.database import PluginDatabase


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a persisted Phase 7A API run.")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--run-id", required=True)
    arguments = parser.parse_args()
    database = PluginDatabase(f"sqlite:///{arguments.database.resolve().as_posix()}")
    run = database.fetch_one(
        "SELECT * FROM api_test_runs WHERE api_test_run_id=:run", {"run": arguments.run_id}
    )
    if not run or run["status"] != "completed" or int(run["total_count"]) != 7:
        raise SystemExit("API_RUN_INVALID")
    results = database.fetch_all(
        "SELECT * FROM api_test_results WHERE api_test_run_id=:run ORDER BY case_id",
        {"run": arguments.run_id},
    )
    evidence = database.fetch_all(
        "SELECT e.evidence_json,e.evidence_hash,e.redaction_applied FROM api_test_evidence e "
        "JOIN api_test_results r ON r.api_test_result_id=e.api_test_result_id "
        "WHERE r.api_test_run_id=:run ORDER BY r.case_id",
        {"run": arguments.run_id},
    )
    if len(results) != 7 or len(evidence) != 7:
        raise SystemExit("API_RESULT_OR_EVIDENCE_COUNT_INVALID")
    for item in evidence:
        payload = json.loads(str(item["evidence_json"]))
        digest = hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()
        if digest != item["evidence_hash"] or item["redaction_applied"] != 1:
            raise SystemExit("API_EVIDENCE_INTEGRITY_INVALID")
    seeded = next(row for row in results if row["case_id"] == "TC-API-AUTH-REG-005")
    if not (
        seeded["status"] == "FAIL"
        and seeded["failure_type"] == "suspected_product_bug"
        and seeded["expected_status"] == 400
        and seeded["actual_status"] == 201
    ):
        raise SystemExit("SEEDED_DEFECT_VERDICT_INVALID")
    if database.fetch_one("PRAGMA integrity_check") != {"integrity_check": "ok"}:
        raise SystemExit("DATABASE_INTEGRITY_INVALID")
    if database.fetch_all("PRAGMA foreign_key_check"):
        raise SystemExit("DATABASE_FOREIGN_KEY_INVALID")
    print(
        json.dumps(
            {
                "run_id": arguments.run_id,
                "total": run["total_count"],
                "pass": run["pass_count"],
                "fail": run["fail_count"],
                "evidence": len(evidence),
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
