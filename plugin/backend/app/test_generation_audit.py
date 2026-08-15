from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection

from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.ids import new_id

TEST_GENERATION_PARSER_VERSION = "test-generation-json-parser@1.0.0"
TEST_GENERATION_REDACTION_VERSION = "test-generation-redaction@1.0.0"
OFFLINE_BACKFILL_ORIGIN = "offline_audit_backfill"
RUNTIME_ORIGIN = "runtime"
RUNTIME_VALIDATION_ORIGIN = "runtime_validation"

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)\b(authorization|api[_-]?key|cookie|access[_-]?token|refresh[_-]?token|"
    r"bearer[_-]?token|secret)\b(\s*[:=]\s*)([^,\s;\"']+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{8,}=*")
_KEY_SHAPE = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")


def redact_text(value: str) -> tuple[str, bool]:
    redacted = _SECRET_ASSIGNMENT.sub(r"\1\2[REDACTED]", value)
    redacted = _BEARER.sub("Bearer [REDACTED]", redacted)
    redacted = _KEY_SHAPE.sub("[REDACTED_API_KEY]", redacted)
    return redacted, redacted != value


def redact_parsed_json(value: Any) -> tuple[Any, bool]:
    applied = False

    def visit(item: Any) -> Any:
        nonlocal applied
        if isinstance(item, dict):
            result: dict[str, Any] = {}
            for key, nested in item.items():
                key_name = str(key)
                if re.search(
                    r"(?i)(authorization|api[_-]?key|cookie|access[_-]?token|"
                    r"refresh[_-]?token|bearer[_-]?token|secret)",
                    key_name,
                ):
                    result[key_name] = "[REDACTED]"
                    applied = True
                else:
                    result[key_name] = visit(nested)
            return result
        if isinstance(item, list):
            return [visit(nested) for nested in item]
        if isinstance(item, str):
            clean, changed = redact_text(item)
            applied = applied or changed
            return clean
        return item

    return visit(value), applied


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def parsed_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def failure_stage(error_code: str | None) -> str | None:
    if not error_code:
        return None
    if error_code in {"OUTPUT_TRUNCATED", "INVALID_JSON_RESPONSE", "JSON_ROOT_NOT_OBJECT"}:
        return "json_parse"
    if error_code in {
        "RAW_CASE_FIELD_BOUNDARY_INVALID",
        "BATCH_ID_OR_TYPE_MISMATCH",
        "REPORTED_COUNT_MISMATCH",
        "BATCH_CASE_LIMIT_EXCEEDED",
        "UNSUPPORTED_REQUIREMENT_OUTSIDE_BATCH",
    }:
        return "field_boundary"
    if error_code.startswith("SCHEMA_VALIDATION_FAILED"):
        return "schema"
    return "domain"


def insert_parsed_artifact(
    connection: Connection,
    database: PluginDatabase,
    *,
    call_id: str,
    parsed: dict[str, Any],
    validation_status: str,
    error_code: str | None,
    origin: str,
    derived_from_failed_call: bool = False,
    original_call_id: str | None = None,
    original_failure_code: str | None = None,
) -> dict[str, Any]:
    clean, redaction_applied = redact_parsed_json(parsed)
    digest = parsed_hash(clean)
    artifact_id = new_id("TPA")
    connection.execute(
        text(
            "INSERT INTO test_generation_parsed_artifacts("
            "test_generation_parsed_artifact_id,test_generation_llm_call_id,parsed_json,"
            "parsed_hash,validation_status,failure_stage,failure_code,parser_version,"
            "redaction_version,artifact_origin,derived_from_failed_call,original_call_id,"
            "original_failure_code,backfilled_at) VALUES "
            "(:id,:call,:parsed,:hash,:status,:stage,:code,:parser,:redaction,:origin,"
            ":derived,:original_call,:original_code,"
            "CASE WHEN :origin='offline_audit_backfill' THEN CURRENT_TIMESTAMP ELSE NULL END)"
        ),
        {
            "id": artifact_id,
            "call": call_id,
            "parsed": database.encode_json(clean),
            "hash": digest,
            "status": validation_status,
            "stage": failure_stage(error_code),
            "code": error_code,
            "parser": TEST_GENERATION_PARSER_VERSION,
            "redaction": TEST_GENERATION_REDACTION_VERSION,
            "origin": origin,
            "derived": int(derived_from_failed_call),
            "original_call": original_call_id,
            "original_code": original_failure_code,
        },
    )
    return {
        "parsed_artifact_id": artifact_id,
        "parsed_hash": digest,
        "redaction_applied": redaction_applied,
    }


def insert_validation_outcome(
    connection: Connection,
    *,
    call_id: str,
    validation_status: str,
    error_code: str | None,
    validator_version: str,
    origin: str = RUNTIME_ORIGIN,
) -> None:
    connection.execute(
        text(
            "INSERT INTO test_generation_call_validation_outcomes("
            "test_generation_call_validation_outcome_id,test_generation_llm_call_id,"
            "validation_status,failure_stage,failure_code,validator_version,outcome_origin) "
            "VALUES (:id,:call,:status,:stage,:code,:version,:origin)"
        ),
        {
            "id": new_id("TVO"),
            "call": call_id,
            "status": validation_status,
            "stage": failure_stage(error_code),
            "code": error_code,
            "version": validator_version,
            "origin": origin,
        },
    )
