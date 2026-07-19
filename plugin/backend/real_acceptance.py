from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from plugin.backend.app.analysis import AnalysisService, content_hash, normalize_prd, plan_batches
from plugin.backend.app.config import PROJECT_ROOT, PluginConfig
from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.prompts import RECOVERY_PROMPT_VERSION, PromptRegistry
from plugin.backend.app.providers import DeepSeekProvider

PRD_PATH = PROJECT_ROOT / "docs" / "prd" / "login_register_prd.md"


def run_real_acceptance() -> dict[str, Any]:
    config = PluginConfig.as_mapping()
    database_url = str(config["PLUGIN_DATABASE_URL"])
    database_path = _validated_database_path(database_url)
    database = PluginDatabase(database_url)
    database.migrate()
    normalized = normalize_prd(PRD_PATH.read_text(encoding="utf-8"))
    prd_hash = content_hash(normalized)

    source_run_id = os.getenv("PHASE5A_RECOVERY_SOURCE_RUN_ID", "").strip()
    if not source_run_id:
        raise RealAcceptanceError("PHASE5A_RECOVERY_SOURCE_RUN_ID is required.")
    source_run = database.fetch_one(
        "SELECT r.*, v.content_hash FROM analysis_runs r "
        "JOIN prd_versions v ON v.version_id=r.prd_version_id "
        "WHERE r.analysis_run_id=:id",
        {"id": source_run_id},
    )
    if not source_run or source_run["status"] != "failed":
        raise RealAcceptanceError("Recovery source must be an existing failed run.")
    if source_run["content_hash"] != prd_hash:
        raise RealAcceptanceError("Recovery source PRD does not match the approved PRD.")
    source_requirement_count = database.fetch_one(
        "SELECT COUNT(*) AS count FROM requirements WHERE analysis_run_id=:run",
        {"run": source_run_id},
    )
    if not source_requirement_count or source_requirement_count["count"] != 0:
        raise RealAcceptanceError("Recovery source must have zero formal requirements.")

    prompts = PromptRegistry()
    provider = DeepSeekProvider(
        base_url=str(config["DEEPSEEK_BASE_URL"]),
        model=str(config["DEEPSEEK_MODEL"]),
        timeout_seconds=float(config["LLM_TIMEOUT_SECONDS"]),
        max_tokens=int(config["LLM_MAX_OUTPUT_TOKENS"]),
        prompts=prompts,
    )
    provider.validate_config()
    expected_batches = len(plan_batches(normalized, int(config["PRD_BATCH_MAX_CHARS"])))
    key = (
        f"phase5a-recovery:{source_run_id}:{prd_hash}:{provider.metadata.model}:"
        f"{RECOVERY_PROMPT_VERSION}:{int(config['PRD_BATCH_MAX_CHARS'])}"
    )
    run = AnalysisService(
        database,
        prompts=prompts,
        batch_max_chars=int(config["PRD_BATCH_MAX_CHARS"]),
        batch_max_requirements=int(config["PRD_BATCH_MAX_REQUIREMENTS"]),
        max_retries=0,
        call_max_output_tokens=int(config["LLM_MAX_OUTPUT_TOKENS"]),
        run_max_output_tokens=int(config["LLM_MAX_OUTPUT_TOKENS"]),
    ).start_recovery(source_run_id, provider, key)

    run_id = str(run["analysis_run_id"])
    batches = database.fetch_all(
        "SELECT batch_index, status, retry_count, finish_reason, validation_status, "
        "error_type FROM analysis_batches WHERE analysis_run_id=:run ORDER BY batch_index",
        {"run": run_id},
    )
    calls = database.fetch_all(
        "SELECT call_type, provider, model, provider_mode, prompt_version, http_status, "
        "finish_reason, input_tokens, output_tokens, max_tokens, latency_ms, retry_count, "
        "validation_status, error_type "
        "FROM llm_call_logs WHERE analysis_run_id=:run ORDER BY created_at, llm_call_id",
        {"run": run_id},
    )
    rows = database.fetch_all(
        "SELECT requirement_id, payload_json FROM requirements "
        "WHERE analysis_run_id=:run ORDER BY requirement_id",
        {"run": run_id},
    )
    requirements = [json.loads(row["payload_json"]) for row in rows]
    reuse_links = database.fetch_all(
        "SELECT artifact_type, source_analysis_run_id, source_entity_id, target_entity_id "
        "FROM analysis_reuse_links WHERE analysis_run_id=:run ORDER BY artifact_type",
        {"run": run_id},
    )
    response_artifact_count = database.fetch_one(
        "SELECT COUNT(*) AS count FROM llm_response_artifacts a "
        "JOIN llm_call_logs c ON c.llm_call_id=a.llm_call_id "
        "WHERE c.analysis_run_id=:run",
        {"run": run_id},
    )
    source_audit_count = database.fetch_one(
        "SELECT COUNT(*) AS count FROM source_reference_audits WHERE analysis_run_id=:run",
        {"run": run_id},
    )
    if response_artifact_count is None or source_audit_count is None:
        raise RealAcceptanceError("Recovery audit counts are unavailable.")
    searchable = json.dumps(requirements, ensure_ascii=False).lower()
    key_value = os.environ["DEEPSEEK_API_KEY"].encode("utf-8")
    database_contains_key = key_value in database_path.read_bytes()
    summary: dict[str, Any] = {
        "result": "PASS" if run["status"] == "succeeded" else "FAIL",
        "analysis_run_id": run_id,
        "source_analysis_run_id": source_run_id,
        "provider": run["provider"],
        "provider_mode": run["provider_mode"],
        "model": run["model"],
        "prompt_version": run["prompt_version"],
        "schema_version": run["schema_version"],
        "expected_initial_batches": expected_batches,
        "persisted_batches": len(batches),
        "batches": batches,
        "call_count": len(calls),
        "calls": calls,
        "reuse_links": reuse_links,
        "response_artifact_count": int(response_artifact_count["count"]),
        "source_audit_count": int(source_audit_count["count"]),
        "input_tokens": sum(int(call["input_tokens"] or 0) for call in calls),
        "output_tokens": sum(int(call["output_tokens"] or 0) for call in calls),
        "latency_ms": sum(int(call["latency_ms"] or 0) for call in calls),
        "formal_requirement_count": len(requirements),
        "username_minimum_six_present": (
            "username" in searchable
            and any(term in searchable for term in ("at least 6", "minimum of 6", "between 6"))
        ),
        "registration_present": "register" in searchable,
        "login_present": "login" in searchable,
        "current_user_present": any(
            term in searchable for term in ("current user", "current-user", "account data", "/me")
        ),
        "logout_present": "logout" in searchable,
        "database_relative_path": database_path.relative_to(PROJECT_ROOT).as_posix(),
        "database_contains_api_key": database_contains_key,
    }
    checks = [
        summary["result"] == "PASS",
        summary["provider"] == "deepseek",
        summary["provider_mode"] == "real",
        len(calls) == 1,
        calls[0]["call_type"] == "requirements_recovery",
        all(call["http_status"] == 200 for call in calls),
        all(call["finish_reason"] == "stop" for call in calls),
        all(call["validation_status"] == "valid" for call in calls),
        all(batch["status"] == "validated" for batch in batches),
        all(batch["validation_status"] == "valid" for batch in batches),
        {link["artifact_type"] for link in reuse_links} == {"outline", "validated_batch"},
        summary["response_artifact_count"] == 1,
        summary["source_audit_count"] >= len(requirements),
        bool(requirements),
        summary["username_minimum_six_present"],
        summary["registration_present"],
        summary["login_present"],
        summary["current_user_present"],
        summary["logout_present"],
        not database_contains_key,
    ]
    if not all(checks):
        summary["result"] = "FAIL"
        raise RealAcceptanceError(json.dumps(summary, ensure_ascii=False))
    return summary


class RealAcceptanceError(Exception):
    pass


def _validated_database_path(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise RealAcceptanceError("Phase 5A acceptance requires the local SQLite plugin database.")
    raw_path = Path(database_url.removeprefix("sqlite:///"))
    path = raw_path if raw_path.is_absolute() else PROJECT_ROOT / raw_path
    resolved = path.resolve()
    try:
        resolved.relative_to(PROJECT_ROOT)
    except ValueError as error:
        raise RealAcceptanceError("Plugin database path escapes the V3 project root.") from error
    return resolved


def main() -> None:
    if os.getenv("PHASE5A_REAL_CONFIRM") != "YES":
        raise SystemExit("Real acceptance is blocked without PHASE5A_REAL_CONFIRM=YES.")
    summary = run_real_acceptance()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
