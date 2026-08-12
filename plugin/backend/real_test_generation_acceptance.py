from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.prompts import PromptRegistry
from plugin.backend.app.providers import (
    DeepSeekProvider,
    LLMProvider,
    ProviderConfigurationError,
    ProviderMetadata,
    ProviderResponse,
)
from plugin.backend.app.test_generation import TestGenerationService
from plugin.backend.app.test_generation_budget import calculate_cost, microusd_to_usd
from plugin.backend.app.test_generation_payloads import (
    contract_for_case_type,
    project_generation_slot,
)
from plugin.backend.app.test_generation_planning import capacity_report_for_plan
from plugin.backend.app.test_generation_prompts import (
    TEST_GENERATION_PROMPT_VERSION,
    TestGenerationPromptRegistry,
)
from plugin.backend.app.test_generation_schemas import (
    TEST_CASE_SCHEMA_VERSION,
    TestCaseSchemas,
)
from plugin.backend.app.test_intent_schemas import (
    TEST_INTENT_SCHEMA_VERSION,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "instance" / "plugin.db"
REAL_CONFIRMATION = "PHASE5B_REAL_CONFIRM"


class RealAcceptanceError(Exception):
    pass


@dataclass(frozen=True)
class AcceptanceLimits:
    max_calls: int
    max_retries: int
    budget_microusd: int
    max_output_tokens: int
    max_provider_retries: int = 0


class BudgetGuardProvider:
    def __init__(
        self,
        provider: LLMProvider,
        *,
        limits: AcceptanceLimits,
        prompts: TestGenerationPromptRegistry,
        reservation_costs: dict[str, int] | None = None,
    ) -> None:
        self.provider = provider
        self.limits = limits
        self.prompts = prompts
        self.reservation_costs = dict(reservation_costs or {})
        self.remaining_initial_batches = set(self.reservation_costs)
        self.call_count = 0
        self.actual_cost_microusd = 0

    @property
    def metadata(self) -> ProviderMetadata:
        return self.provider.metadata

    def validate_config(self) -> None:
        self.provider.validate_config()

    def analyze_outline(self, prd_text: str) -> ProviderResponse:
        raise ProviderConfigurationError("PHASE5A_CALL_FORBIDDEN")

    def extract_requirements_batch(self, **_kwargs: Any) -> ProviderResponse:
        raise ProviderConfigurationError("PHASE5A_CALL_FORBIDDEN")

    def generate_test_cases(
        self,
        *,
        case_type: str,
        batch_id: str,
        generation_run_id: str,
        generation_slots: list[dict[str, Any]],
        max_cases: int,
        max_tokens: int,
        recovery: bool = False,
        validation_error: str | None = None,
    ) -> ProviderResponse:
        if max_tokens > self.limits.max_output_tokens:
            raise ProviderConfigurationError("REAL_OUTPUT_TOKEN_LIMIT_EXCEEDED")
        projected = [project_generation_slot(item, item["snapshot"]) for item in generation_slots]
        api_contract, ui_contract = contract_for_case_type(case_type)
        messages = self.prompts.generation_messages(
            case_type=case_type,
            batch_id=batch_id,
            generation_run_id=generation_run_id,
            provider_mode="real",
            generation_slots=projected,
            max_cases=max_cases,
            recovery=recovery,
            validation_error=validation_error,
            api_contract=api_contract,
            ui_contract=ui_contract,
        )
        from plugin.backend.app.test_generation_budget import estimate_serialized_value

        estimate = estimate_serialized_value(messages)
        worst = calculate_cost(
            provider_mode="real",
            input_tokens=estimate.budget_tokens,
            output_tokens=max_tokens,
            estimated=True,
            pricing_provider=self.metadata.provider,
            pricing_model=self.metadata.model,
        )
        pending_after = set(self.remaining_initial_batches)
        if not recovery:
            pending_after.discard(batch_id)
        projected_calls = self.call_count + 1 + len(pending_after)
        if projected_calls > self.limits.max_calls:
            raise ProviderConfigurationError("REAL_INITIAL_CALL_RESERVATION_EXCEEDED")
        reserved_cost = sum(self.reservation_costs[key] for key in pending_after)
        if (
            self.actual_cost_microusd + worst.estimated_cost_microusd + reserved_cost
            > self.limits.budget_microusd
        ):
            raise ProviderConfigurationError("REAL_INITIAL_COST_RESERVATION_EXCEEDED")
        self.call_count += 1
        if not recovery:
            self.remaining_initial_batches.discard(batch_id)
        response = self.provider.generate_test_cases(
            case_type=case_type,
            batch_id=batch_id,
            generation_run_id=generation_run_id,
            generation_slots=generation_slots,
            max_cases=max_cases,
            max_tokens=max_tokens,
            recovery=recovery,
            validation_error=validation_error,
        )
        actual = calculate_cost(
            provider_mode="real",
            input_tokens=int(response.input_tokens or 0),
            output_tokens=int(response.output_tokens or 0),
            input_cache_hit_tokens=response.input_cache_hit_tokens,
            input_cache_miss_tokens=response.input_cache_miss_tokens,
            pricing_provider=self.metadata.provider,
            pricing_model=self.metadata.model,
        )
        self.actual_cost_microusd += actual.actual_cost_microusd
        return response


def _reservation_summary(costs: dict[str, int], limits: AcceptanceLimits) -> dict[str, int]:
    initial_calls = len(costs)
    initial_cost = sum(costs.values())
    if initial_calls > limits.max_calls:
        raise RealAcceptanceError("DRY_RUN_CALL_LIMIT_INSUFFICIENT")
    if initial_cost > limits.budget_microusd:
        raise RealAcceptanceError("DRY_RUN_BUDGET_INSUFFICIENT")
    call_slots = max(0, limits.max_calls - initial_calls)
    budget_left = limits.budget_microusd - initial_cost
    correction_slots = 0
    correction_cost = 0
    for value in sorted(costs.values(), reverse=True)[:call_slots]:
        if correction_cost + value > budget_left:
            break
        correction_cost += value
        correction_slots += 1
    return {
        "initial_call_count": initial_calls,
        "initial_worst_cost_microusd": initial_cost,
        "correction_call_slots": correction_slots,
        "correction_worst_cost_microusd": correction_cost,
        "worst_cost_microusd": initial_cost + correction_cost,
    }


def build_dry_run_report(
    database: PluginDatabase,
    *,
    project_id: str,
    limits: AcceptanceLimits,
    resume_run_id: str | None,
    recovery_reason: str | None = None,
) -> dict[str, Any]:
    if limits.max_calls < 1:
        raise RealAcceptanceError("DRY_RUN_CALL_LIMIT_INSUFFICIENT")
    if bool(resume_run_id) != bool(recovery_reason):
        raise RealAcceptanceError("RECOVERY_LINK_AND_REASON_REQUIRED_TOGETHER")
    if recovery_reason not in {
        None,
        "PROMPT_FIELD_CONTRACT_REPAIR",
        "TEST_INTENT_COMPILER_REDESIGN",
        "SYSTEM_OWNED_GENERATION_SLOTS",
        "PROVIDER_NETWORK_RECOVERY",
    }:
        raise RealAcceptanceError("RECOVERY_REASON_NOT_APPROVED")
    before = _database_file_hash(database)
    service = TestGenerationService(
        database,
        max_tokens_per_batch=limits.max_output_tokens,
        max_retries=min(1, limits.max_retries),
        max_corrections_per_run=limits.max_retries,
        max_provider_retries_per_run=limits.max_provider_retries,
        max_total_provider_calls=limits.max_calls,
        max_run_cost_usd=Decimal(limits.budget_microusd) / Decimal(1_000_000),
    )
    plan = service.preflight(project_id)
    snapshots = service._load_requirement_snapshots(project_id)
    capacities = capacity_report_for_plan(plan, snapshots, service.prompts)
    reusable_batch_keys, checkpoint_rejections = _reusable_batch_keys(
        service,
        resume_run_id=resume_run_id,
        requirement_snapshot_hash=plan["requirement_snapshot_hash"],
        batches=plan["batches"],
        snapshots=snapshots,
        provider_metadata=ProviderMetadata("deepseek", "deepseek-v4-pro", "real"),
    )
    pending_capacities = [
        item for item in capacities if item["batch_key"] not in reusable_batch_keys
    ]
    reservation_costs = {
        str(item["batch_key"]): calculate_cost(
            provider_mode="real",
            input_tokens=int(item["input_estimate"]["budget_tokens"]),
            output_tokens=int(item["max_tokens"]),
            estimated=True,
        ).estimated_cost_microusd
        for item in pending_capacities
    }
    reservation = _reservation_summary(reservation_costs, limits)
    after = _database_file_hash(database)
    if before != after:
        raise RealAcceptanceError("DRY_RUN_DATABASE_CHANGED")
    return {
        "mode": "dry_run",
        "provider": "real",
        "model": "deepseek-v4-pro",
        "thinking": "disabled",
        "provider_calls": 0,
        "database_writes": 0,
        "requirement_snapshot_hash": plan["requirement_snapshot_hash"],
        "prompt_version": TEST_GENERATION_PROMPT_VERSION,
        "prompt_hash": service.prompts.content_hash,
        "schema_version": TEST_INTENT_SCHEMA_VERSION,
        "schema_hash": service.intent_schemas.content_hash,
        "candidate_schema_version": TEST_CASE_SCHEMA_VERSION,
        "candidate_schema_hash": _schema_hash(service.schemas),
        "resume_run_id": resume_run_id,
        "recovery_reason": recovery_reason,
        "total_batch_count": len(plan["batches"]),
        "reusable_batch_count": len(reusable_batch_keys),
        "reusable_batch_keys": sorted(reusable_batch_keys),
        "checkpoint_rejections": checkpoint_rejections,
        "planned_call_count": reservation["initial_call_count"],
        "max_calls": limits.max_calls,
        "max_retries": limits.max_retries,
        "max_provider_retries": limits.max_provider_retries,
        "max_output_tokens": limits.max_output_tokens,
        "budget_microusd": limits.budget_microusd,
        "budget_usd": microusd_to_usd(limits.budget_microusd),
        "initial_worst_cost_microusd": reservation["initial_worst_cost_microusd"],
        "correction_call_slots": reservation["correction_call_slots"],
        "correction_worst_cost_microusd": reservation["correction_worst_cost_microusd"],
        "worst_cost_microusd": reservation["worst_cost_microusd"],
        "worst_cost_usd": microusd_to_usd(reservation["worst_cost_microusd"]),
        "reservation_costs": reservation_costs,
        "batches": capacities,
    }


def _reusable_batch_keys(
    service: TestGenerationService,
    *,
    resume_run_id: str | None,
    requirement_snapshot_hash: str,
    batches: list[dict[str, Any]],
    snapshots: dict[str, dict[str, Any]],
    provider_metadata: ProviderMetadata,
) -> tuple[set[str], dict[str, str]]:
    if resume_run_id is None:
        return set(), {}
    database = service.database
    table = database.fetch_one(
        "SELECT COUNT(*) AS count FROM sqlite_master "
        "WHERE type='table' AND name='test_generation_runs'"
    )
    if table != {"count": 1}:
        raise RealAcceptanceError("RESUME_SCHEMA_NOT_MIGRATED")
    source = database.fetch_one(
        "SELECT provider,model,provider_mode,status,requirement_snapshot_hash "
        "FROM test_generation_runs WHERE test_generation_run_id=:run",
        {"run": resume_run_id},
    )
    if not source:
        raise RealAcceptanceError("RESUME_RUN_NOT_FOUND")
    if source["status"] not in {"running", "blocked", "failed"}:
        raise RealAcceptanceError("RESUME_RUN_NOT_INCOMPLETE")
    if (
        source["provider"] != "deepseek"
        or source["model"] != "deepseek-v4-pro"
        or source["provider_mode"] != "real"
        or source["requirement_snapshot_hash"] != requirement_snapshot_hash
    ):
        raise RealAcceptanceError("RESUME_RUN_INCOMPATIBLE")
    reusable: set[str] = set()
    rejections: dict[str, str] = {}
    planned = {item.batch_key: item for item in service._plan_batches({"batches": batches})}
    for batch_key, batch in planned.items():
        qualification = service.qualify_checkpoint(
            resume_run_id=resume_run_id,
            batch=batch,
            snapshots=[snapshots[item] for item in batch.requirement_ids],
            provider_metadata=provider_metadata,
        )
        if qualification.reusable:
            reusable.add(batch_key)
        else:
            rejections[batch_key] = qualification.rejection_reason or "CHECKPOINT_REJECTED"
    return reusable, rejections


def _execute(args: argparse.Namespace, database: PluginDatabase, project_id: str) -> int:
    if os.getenv(REAL_CONFIRMATION) != "YES":
        raise RealAcceptanceError("EXPLICIT_REAL_CONFIRMATION_REQUIRED")
    _load_real_process_environment(args.model)
    if args.provider != "real" or args.thinking != "disabled":
        raise RealAcceptanceError("REAL_PROVIDER_AND_DISABLED_THINKING_REQUIRED")
    limits = _limits(args)
    report = build_dry_run_report(
        database,
        project_id=project_id,
        limits=limits,
        resume_run_id=args.resume_run_id,
        recovery_reason=args.recovery_reason,
    )
    backup = _backup_database()
    before = _phase5a_fingerprint(database)
    database.migrate()
    _assert_migrated_database(database, before)
    prompts = TestGenerationPromptRegistry()
    provider = DeepSeekProvider(
        base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
        model=args.model,
        timeout_seconds=float(os.environ.get("LLM_TIMEOUT_SECONDS", "60")),
        max_tokens=args.max_output_tokens,
        prompts=PromptRegistry(),
        generation_prompts=prompts,
    )
    guarded: LLMProvider = BudgetGuardProvider(
        provider,
        limits=limits,
        prompts=prompts,
        reservation_costs={str(k): int(v) for k, v in report["reservation_costs"].items()},
    )
    service = TestGenerationService(
        database,
        max_tokens_per_batch=args.max_output_tokens,
        max_retries=min(1, limits.max_retries),
        max_corrections_per_run=limits.max_retries,
        max_provider_retries_per_run=limits.max_provider_retries,
        max_total_provider_calls=limits.max_calls,
        max_run_cost_usd=Decimal(limits.budget_microusd) / Decimal(1_000_000),
    )
    result = service.start(
        project_id,
        guarded,
        "phase5b-real-"
        f"{report['requirement_snapshot_hash']}-"
        f"{report['prompt_hash'][:16]}-"
        f"{args.resume_run_id or 'initial'}",
        resume_run_id=args.resume_run_id,
        recovery_reason=args.recovery_reason,
    )
    print(
        json.dumps(
            {
                "result": asdict(result),
                "backup_sha256": backup["sha256"],
                "provider_calls": guarded.call_count,  # type: ignore[attr-defined]
                "actual_cost_microusd": guarded.actual_cost_microusd,  # type: ignore[attr-defined]
            },
            separators=(",", ":"),
        )
    )
    return 0 if result.status == "validated_pending_review" else 1


def _load_real_process_environment(expected_model: str) -> None:
    env_path = PROJECT_ROOT / ".env"
    allowed = {"DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"}
    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name in allowed:
            values[name] = value.strip().strip("\"'")
    key = values.get("DEEPSEEK_API_KEY", "")
    base_url = values.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = values.get("DEEPSEEK_MODEL", expected_model)
    if not re.fullmatch(r"sk-[A-Za-z0-9_-]{20,}", key):
        raise RealAcceptanceError("DEEPSEEK_API_KEY_INVALID")
    if base_url.rstrip("/") != "https://api.deepseek.com":
        raise RealAcceptanceError("DEEPSEEK_BASE_URL_NOT_OFFICIAL")
    if model != expected_model or model != "deepseek-v4-pro":
        raise RealAcceptanceError("DEEPSEEK_MODEL_MISMATCH")
    os.environ["DEEPSEEK_API_KEY"] = key
    os.environ["DEEPSEEK_BASE_URL"] = base_url.rstrip("/")
    os.environ["DEEPSEEK_MODEL"] = model
    logging.getLogger("httpx").disabled = True
    logging.getLogger("httpcore").disabled = True


def _limits(args: argparse.Namespace) -> AcceptanceLimits:
    try:
        budget = Decimal(str(args.budget_usd))
    except InvalidOperation as error:
        raise RealAcceptanceError("INVALID_BUDGET") from error
    if budget < 0:
        raise RealAcceptanceError("INVALID_BUDGET")
    budget_microusd = int(
        (budget * Decimal(1_000_000)).quantize(Decimal("1"), rounding=ROUND_CEILING)
    )
    if (
        args.max_calls < 0
        or not 0 <= args.max_corrections <= 8
        or not 0 <= args.max_provider_retries <= 15
    ):
        raise RealAcceptanceError("INVALID_CALL_OR_RETRY_LIMIT")
    return AcceptanceLimits(
        max_calls=args.max_calls,
        max_retries=args.max_corrections,
        budget_microusd=budget_microusd,
        max_output_tokens=args.max_output_tokens,
        max_provider_retries=args.max_provider_retries,
    )


def _project_id(database: PluginDatabase, configured: str | None) -> str:
    if configured:
        row = database.fetch_one(
            "SELECT project_id FROM projects WHERE project_id=:id", {"id": configured}
        )
        if not row:
            raise RealAcceptanceError("PROJECT_NOT_FOUND")
        return configured
    rows = database.fetch_all("SELECT project_id FROM projects ORDER BY project_id")
    if len(rows) != 1:
        raise RealAcceptanceError("PROJECT_ID_NOT_UNIQUE")
    return str(rows[0]["project_id"])


def _database_file_hash(database: PluginDatabase) -> str:
    if database.url != f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}":
        return "non-default-database"
    return hashlib.sha256(DEFAULT_DATABASE_PATH.read_bytes()).hexdigest()


def _schema_hash(schemas: TestCaseSchemas) -> str:
    value = "\n".join(
        json.dumps(schemas.schemas[name], sort_keys=True, separators=(",", ":"))
        for name in sorted(schemas.schemas)
    )
    return hashlib.sha256(value.encode()).hexdigest()


def _backup_database() -> dict[str, str]:
    backup_root = PROJECT_ROOT / "tmp" / "phase5b" / "backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(DEFAULT_DATABASE_PATH.read_bytes()).hexdigest()
    target = backup_root / f"plugin-before-0004-{digest[:16]}.db"
    shutil.copy2(DEFAULT_DATABASE_PATH, target)
    if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
        raise RealAcceptanceError("DATABASE_BACKUP_HASH_MISMATCH")
    with sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RealAcceptanceError("DATABASE_BACKUP_NOT_READABLE")
    return {"path": target.relative_to(PROJECT_ROOT).as_posix(), "sha256": digest}


def _phase5a_fingerprint(database: PluginDatabase) -> dict[str, Any]:
    requirements = database.fetch_all(
        "SELECT requirement_id,version_number,payload_json FROM requirements "
        "ORDER BY requirement_id"
    )
    return {
        "requirements": requirements,
        "analysis_runs": database.fetch_one("SELECT COUNT(*) AS count FROM analysis_runs"),
        "llm_calls": database.fetch_one("SELECT COUNT(*) AS count FROM llm_call_logs"),
        "source_audits": database.fetch_one(
            "SELECT COUNT(*) AS count FROM source_reference_audits"
        ),
    }


def _assert_migrated_database(database: PluginDatabase, before: dict[str, Any]) -> None:
    if _phase5a_fingerprint(database) != before:
        raise RealAcceptanceError("PHASE5A_FINGERPRINT_CHANGED")
    integrity = database.fetch_one("PRAGMA integrity_check")
    if integrity != {"integrity_check": "ok"}:
        raise RealAcceptanceError("DATABASE_INTEGRITY_FAILED")
    if database.fetch_all("PRAGMA foreign_key_check"):
        raise RealAcceptanceError("DATABASE_FOREIGN_KEY_FAILED")
    migration = database.fetch_one(
        "SELECT COUNT(*) AS count FROM schema_migrations WHERE version='0004_test_case_generation'"
    )
    if migration != {"count": 1}:
        raise RealAcceptanceError("MIGRATION_0004_MISSING")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--max-calls", required=True, type=int)
    parser.add_argument(
        "--max-corrections", "--max-retries", dest="max_corrections", required=True, type=int
    )
    parser.add_argument("--max-provider-retries", default=15, type=int)
    parser.add_argument("--budget-usd", required=True)
    parser.add_argument("--max-output-tokens", required=True, type=int)
    parser.add_argument("--project-id")
    parser.add_argument("--resume-run-id")
    parser.add_argument(
        "--recovery-reason",
        choices=(
            "PROMPT_FIELD_CONTRACT_REPAIR",
            "TEST_INTENT_COMPILER_REDESIGN",
            "PROVIDER_NETWORK_RECOVERY",
        ),
    )
    parser.add_argument("--thinking", required=True, choices=("disabled",))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", dest="dry_run", action="store_true")
    mode.add_argument("--execute", dest="dry_run", action="store_false")
    parser.set_defaults(dry_run=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.provider != "real" or args.model != "deepseek-v4-pro":
        raise RealAcceptanceError("UNAPPROVED_PROVIDER_OR_MODEL")
    database = PluginDatabase(f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}")
    project_id = _project_id(database, args.project_id)
    limits = _limits(args)
    if args.dry_run:
        report = build_dry_run_report(
            database,
            project_id=project_id,
            limits=limits,
            resume_run_id=args.resume_run_id,
            recovery_reason=args.recovery_reason,
        )
        print(json.dumps(report, ensure_ascii=False, separators=(",", ":")))
        return 0
    return _execute(args, database, project_id)


if __name__ == "__main__":
    raise SystemExit(main())
