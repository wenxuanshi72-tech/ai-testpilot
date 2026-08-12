from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import text

from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.ids import new_id
from plugin.backend.app.test_generation import GENERATION_VALIDATOR_VERSION
from plugin.backend.app.test_generation_audit import (
    OFFLINE_BACKFILL_ORIGIN,
    TEST_GENERATION_PARSER_VERSION,
    insert_parsed_artifact,
    insert_validation_outcome,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "instance" / "plugin.db"
EXPECTED_RUN_ID = "TGR-4D22911C1E834A96A0B8E5698B8F361D"
EXPECTED_BATCH_KEY = "TGB-API-001"
EXPECTED_RESPONSE_HASH = "4ea731ed2a0ea1b1f8c34ef0dc48779a6be84a4461660f1681997ef980598bd1"
EXPECTED_FAILURE_CODE = "RAW_CASE_FIELD_BOUNDARY_INVALID"


class OfflineAuditBackfillError(Exception):
    pass


def backfill_failed_generation_response(
    database: PluginDatabase,
    *,
    run_id: str = EXPECTED_RUN_ID,
    batch_key: str = EXPECTED_BATCH_KEY,
    expected_response_hash: str = EXPECTED_RESPONSE_HASH,
    expected_failure_code: str = EXPECTED_FAILURE_CODE,
) -> dict[str, Any]:
    original = database.fetch_one(
        "SELECT r.status AS run_status,r.error_type AS run_error,"
        "b.test_generation_batch_id,b.status AS batch_status,b.error_type AS batch_error,"
        "c.test_generation_llm_call_id,c.validation_status AS call_status,"
        "c.error_type AS call_error,a.response_content,a.response_hash,"
        "COALESCE(v.validation_status,c.validation_status) AS effective_call_status,"
        "COALESCE(v.failure_code,c.error_type) AS effective_call_error "
        "FROM test_generation_runs r JOIN test_generation_batches b "
        "ON b.test_generation_run_id=r.test_generation_run_id "
        "JOIN test_generation_llm_calls c "
        "ON c.test_generation_batch_id=b.test_generation_batch_id "
        "JOIN test_generation_response_artifacts a "
        "ON a.test_generation_llm_call_id=c.test_generation_llm_call_id "
        "LEFT JOIN test_generation_call_validation_outcomes v "
        "ON v.test_generation_llm_call_id=c.test_generation_llm_call_id "
        "AND v.outcome_origin='runtime' "
        "WHERE r.test_generation_run_id=:run AND b.batch_key=:batch "
        "ORDER BY c.created_at,c.test_generation_llm_call_id LIMIT 1",
        {"run": run_id, "batch": batch_key},
    )
    if not original:
        raise OfflineAuditBackfillError("FAILED_CALL_NOT_FOUND")
    if (
        original["run_status"] != "failed"
        or original["batch_status"] != "failed"
        or original["effective_call_status"] != "invalid"
        or original["effective_call_error"] != expected_failure_code
    ):
        raise OfflineAuditBackfillError("FAILED_CALL_STATE_MISMATCH")
    content = str(original["response_content"])
    stored_hash = str(original["response_hash"])
    calculated_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if stored_hash != expected_response_hash or calculated_hash != expected_response_hash:
        raise OfflineAuditBackfillError("RESPONSE_HASH_MISMATCH")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as error:
        raise OfflineAuditBackfillError("HISTORICAL_RESPONSE_JSON_INVALID") from error
    if not isinstance(parsed, dict):
        raise OfflineAuditBackfillError("HISTORICAL_RESPONSE_ROOT_NOT_OBJECT")
    call_id = str(original["test_generation_llm_call_id"])
    existing = database.fetch_one(
        "SELECT test_generation_parsed_artifact_id,parsed_hash "
        "FROM test_generation_parsed_artifacts "
        "WHERE test_generation_llm_call_id=:call AND artifact_origin=:origin",
        {"call": call_id, "origin": OFFLINE_BACKFILL_ORIGIN},
    )
    candidates_before = database.fetch_one(
        "SELECT COUNT(*) AS count FROM test_case_candidates WHERE test_generation_run_id=:run",
        {"run": run_id},
    )
    if existing:
        return {
            "status": "already_backfilled",
            "run_id": run_id,
            "batch_key": batch_key,
            "call_id": call_id,
            "parsed_artifact_id": existing["test_generation_parsed_artifact_id"],
            "parsed_hash": existing["parsed_hash"],
            "parser_version": TEST_GENERATION_PARSER_VERSION,
            "response_hash_verified": True,
            "candidate_count": int((candidates_before or {"count": 0})["count"]),
        }
    with database.transaction() as connection:
        artifact = insert_parsed_artifact(
            connection,
            database,
            call_id=call_id,
            parsed=parsed,
            validation_status="invalid",
            error_code=expected_failure_code,
            origin=OFFLINE_BACKFILL_ORIGIN,
            derived_from_failed_call=True,
            original_call_id=call_id,
            original_failure_code=expected_failure_code,
        )
        insert_validation_outcome(
            connection,
            call_id=call_id,
            validation_status="invalid",
            error_code=expected_failure_code,
            validator_version=GENERATION_VALIDATOR_VERSION,
            origin=OFFLINE_BACKFILL_ORIGIN,
        )
        connection.execute(
            text(
                "INSERT INTO test_case_generation_audit_events("
                "test_case_generation_audit_event_id,test_generation_run_id,"
                "test_generation_batch_id,event_type,event_status,details_json) "
                "VALUES (:id,:run,:batch,'offline_parsed_artifact_backfilled','passed',:details)"
            ),
            {
                "id": new_id("TGA"),
                "run": run_id,
                "batch": original["test_generation_batch_id"],
                "details": database.encode_json(
                    {
                        "original_call_id": call_id,
                        "original_failure_code": expected_failure_code,
                        "response_hash": expected_response_hash,
                        "parsed_hash": artifact["parsed_hash"],
                        "parser_version": TEST_GENERATION_PARSER_VERSION,
                        "artifact_origin": OFFLINE_BACKFILL_ORIGIN,
                        "candidate_promotion": False,
                        "model_calls": 0,
                    }
                ),
            },
        )
    after = database.fetch_one(
        "SELECT r.status AS run_status,r.error_type AS run_error,b.status AS batch_status,"
        "b.error_type AS batch_error,c.validation_status AS call_status,"
        "c.error_type AS call_error,a.response_hash "
        "FROM test_generation_runs r JOIN test_generation_batches b "
        "ON b.test_generation_run_id=r.test_generation_run_id "
        "JOIN test_generation_llm_calls c "
        "ON c.test_generation_batch_id=b.test_generation_batch_id "
        "JOIN test_generation_response_artifacts a "
        "ON a.test_generation_llm_call_id=c.test_generation_llm_call_id "
        "WHERE r.test_generation_run_id=:run AND b.batch_key=:batch "
        "ORDER BY c.created_at,c.test_generation_llm_call_id LIMIT 1",
        {"run": run_id, "batch": batch_key},
    )
    expected_after = {key: original[key] for key in after or {}}
    if after != expected_after:
        raise OfflineAuditBackfillError("HISTORICAL_RECORD_CHANGED")
    candidates_after = database.fetch_one(
        "SELECT COUNT(*) AS count FROM test_case_candidates WHERE test_generation_run_id=:run",
        {"run": run_id},
    )
    if candidates_after != candidates_before:
        raise OfflineAuditBackfillError("CANDIDATE_COUNT_CHANGED")
    return {
        "status": "backfilled",
        "run_id": run_id,
        "batch_key": batch_key,
        "call_id": call_id,
        **artifact,
        "parser_version": TEST_GENERATION_PARSER_VERSION,
        "response_hash_verified": True,
        "candidate_count": int((candidates_after or {"count": 0})["count"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", default=EXPECTED_RUN_ID)
    parser.add_argument("--batch-key", default=EXPECTED_BATCH_KEY)
    parser.add_argument("--expected-response-hash", default=EXPECTED_RESPONSE_HASH)
    args = parser.parse_args()
    database = PluginDatabase(f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}")
    report = backfill_failed_generation_response(
        database,
        run_id=args.run_id,
        batch_key=args.batch_key,
        expected_response_hash=args.expected_response_hash,
    )
    print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
