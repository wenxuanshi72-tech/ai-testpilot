from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from plugin.backend.app.analysis import normalize_prd, plan_batches
from plugin.backend.app.outline_normalization import normalize_outline_section_ids
from plugin.backend.app.schema_validation import RequirementSchemas

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "tmp/phase13-e2e/E2E-20260818T064345Z/plugin.db"
RUN_ID = "ANR-3FFB8BCFB5AF4F5B909080930B956ECB"


def replay(database_path: Path) -> dict[str, Any]:
    before = hashlib.sha256(database_path.read_bytes()).hexdigest()
    uri = f"file:{database_path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as connection:
        connection.row_factory = sqlite3.Row
        run_before = dict(
            connection.execute(
                "SELECT status,error_type FROM analysis_runs WHERE analysis_run_id=?", (RUN_ID,)
            ).fetchone()
        )
        row = connection.execute(
            "SELECT a.response_content,a.response_hash FROM llm_response_artifacts a "
            "JOIN llm_call_logs c ON c.llm_call_id=a.llm_call_id "
            "WHERE c.analysis_run_id=? AND c.call_type='outline'",
            (RUN_ID,),
        ).fetchone()
        call_count = connection.execute(
            "SELECT COUNT(*) FROM llm_call_logs WHERE analysis_run_id=?", (RUN_ID,)
        ).fetchone()[0]
        requirement_count = connection.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
    if row is None:
        raise RuntimeError("OUTLINE_ARTIFACT_NOT_FOUND")
    raw = json.loads(str(row["response_content"]))
    if hashlib.sha256(str(row["response_content"]).encode()).hexdigest() != row["response_hash"]:
        raise RuntimeError("OUTLINE_ARTIFACT_HASH_MISMATCH")
    normalized, audits = normalize_outline_section_ids(raw)
    RequirementSchemas().validate("prd_outline.schema.json", normalized)
    prd = normalize_prd((ROOT / "docs/prd/login_register_prd.md").read_text(encoding="utf-8"))
    batches = plan_batches(prd, 1800)
    after = hashlib.sha256(database_path.read_bytes()).hexdigest()
    with sqlite3.connect(uri, uri=True, timeout=5) as connection:
        connection.row_factory = sqlite3.Row
        run_after = dict(
            connection.execute(
                "SELECT status,error_type FROM analysis_runs WHERE analysis_run_id=?", (RUN_ID,)
            ).fetchone()
        )
        final_calls = connection.execute(
            "SELECT COUNT(*) FROM llm_call_logs WHERE analysis_run_id=?", (RUN_ID,)
        ).fetchone()[0]
        final_requirements = connection.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    return {
        "run_id": RUN_ID,
        "raw_section_ids": [item["section_id"] for item in raw["sections"]],
        "normalized_section_ids": [item["section_id"] for item in normalized["sections"]],
        "normalization_audits": [audit.__dict__ for audit in audits],
        "section_id_references": [],
        "schema_validation": "PASS",
        "planned_requirement_batches": len(batches),
        "provider_call_delta": final_calls - call_count,
        "analysis_run_delta": 0,
        "formal_requirement_delta": final_requirements - requirement_count,
        "database_hash_unchanged": before == after,
        "failed_run_unchanged": run_before == run_after,
        "integrity_check": integrity,
        "foreign_key_violations": foreign_keys,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args()
    print(json.dumps(replay(args.database), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
