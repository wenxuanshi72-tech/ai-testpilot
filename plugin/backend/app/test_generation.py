from __future__ import annotations

import hashlib
import json
import os
import random
import re
import time
from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Any

from jsonschema import ValidationError as JsonSchemaError
from sqlalchemy import text

from plugin.backend.app.analysis import TruncationError, parse_json_object
from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.ids import new_id
from plugin.backend.app.providers import (
    LLMProvider,
    ProviderCallError,
    ProviderConfigurationError,
    ProviderMetadata,
    ProviderResponse,
)
from plugin.backend.app.test_generation_audit import (
    RUNTIME_ORIGIN,
    RUNTIME_VALIDATION_ORIGIN,
    insert_parsed_artifact,
    insert_validation_outcome,
    redact_parsed_json,
    redact_text,
)
from plugin.backend.app.test_generation_budget import calculate_cost
from plugin.backend.app.test_generation_diagnostics import safe_schema_error_details
from plugin.backend.app.test_generation_planning import build_capacity_bounded_batches
from plugin.backend.app.test_generation_prompts import (
    TEST_GENERATION_PROMPT_VERSION,
    TestGenerationPromptRegistry,
)
from plugin.backend.app.test_generation_schemas import (
    TEST_CASE_SCHEMA_VERSION,
    TestCaseSchemas,
)
from plugin.backend.app.test_generation_trace import (
    SeededRequirementResolutionError,
    resolve_seeded_username_requirement,
)
from plugin.backend.app.test_intent_compiler import (
    TEST_INTENT_COMPATIBILITY_VERSION,
    TEST_INTENT_COMPILER_VERSION,
    CompilationContext,
    DeterministicCandidateCompiler,
    TestIntentCompilationError,
    compatibility_audit_records,
    normalize_intent_batch,
)
from plugin.backend.app.test_intent_contract import (
    INTENT_FIELDS,
    validate_test_intent_prompt_contract,
)
from plugin.backend.app.test_intent_schemas import (
    TEST_INTENT_SCHEMA_VERSION,
    TestIntentSchemas,
)

GENERATION_VALIDATOR_VERSION = "test-generation-validator@1.0.0"
EXPECTED_REQUIREMENT_COUNT = 19
CASE_TYPES = ("api", "ui", "manual")
MAX_CORRECTIONS_PER_BATCH = 1
MAX_CORRECTIONS_PER_RUN = 8
MAX_PROVIDER_RETRIES_PER_BATCH = 3
MAX_PROVIDER_RETRIES_PER_RUN = 15
MAX_TOTAL_PROVIDER_CALLS = 40
MAX_RUN_COST_USD = Decimal("0.25")
APPROVED_API_STATUSES = {200, 201, 204, 400, 401, 403, 404, 405, 409, 413, 415, 422, 429, 500}
RAW_CASE_KEYS = {
    "case_id",
    "title",
    "objective",
    "requirement_ids",
    "priority",
    "risk_level",
    "test_level",
    "test_category",
    "preconditions",
    "test_data",
    "steps",
    "expected_results",
    "cleanup",
    "tags",
    "type_details",
}


class TestGenerationError(Exception):
    pass


class IntentSchemaValidationError(TestGenerationError):
    pass


class CandidateSchemaValidationError(TestGenerationError):
    pass


class CandidateCompilationError(TestGenerationError):
    pass


@dataclass
class RunCallCounters:
    initial_call_count: int = 0
    correction_call_count: int = 0
    provider_retry_count: int = 0
    total_provider_call_count: int = 0


def is_structure_correction_eligible(
    error_type: str, response: ProviderResponse | None = None
) -> bool:
    if error_type == "INTENT_SCHEMA_VALIDATION":
        return True
    if error_type != "JSON_PARSE_ERROR" or response is None:
        return False
    content = response.content.strip()
    if (
        response.http_status != 200
        or response.finish_reason != "stop"
        or not content
        or len(content) > 100_000
        or content.lstrip().lower().startswith(("<html", "<!doctype html"))
    ):
        return False
    return True


@dataclass(frozen=True)
class GenerationBatch:
    batch_key: str
    batch_index: int
    case_type: str
    requirement_ids: tuple[str, ...]
    generation_slots: tuple[dict[str, Any], ...]
    max_cases: int
    max_tokens: int
    input_hash: str


@dataclass(frozen=True)
class GenerationResult:
    run_id: str
    status: str
    provider_mode: str
    candidate_count: int
    collection_version: int | None
    collection_hash: str | None


@dataclass(frozen=True)
class CheckpointQualification:
    batch_key: str
    reusable: bool
    rejection_reason: str | None
    source_run_id: str | None = None
    source_batch_id: str | None = None
    source_call_id: str | None = None
    response_hash: str | None = None
    semantic_hash: str | None = None
    candidates: tuple[dict[str, Any], ...] = ()


MAX_CHECKPOINT_PARENT_DEPTH = 100


class TestGenerationService:
    def __init__(
        self,
        database: PluginDatabase,
        *,
        schemas: TestCaseSchemas | None = None,
        prompts: TestGenerationPromptRegistry | None = None,
        max_requirements_per_batch: int = 10,
        max_cases_per_batch: int = 12,
        max_tokens_per_batch: int = 3072,
        max_retries: int = MAX_CORRECTIONS_PER_BATCH,
        max_corrections_per_batch: int | None = None,
        max_corrections_per_run: int = MAX_CORRECTIONS_PER_RUN,
        max_provider_retries_per_batch: int = MAX_PROVIDER_RETRIES_PER_BATCH,
        max_provider_retries_per_run: int = MAX_PROVIDER_RETRIES_PER_RUN,
        max_total_provider_calls: int = MAX_TOTAL_PROVIDER_CALLS,
        max_run_cost_usd: Decimal | str = MAX_RUN_COST_USD,
        provider_retry_wait: Any = time.sleep,
        provider_retry_jitter: Any = random.random,
    ) -> None:
        if not 1 <= max_requirements_per_batch <= 10:
            raise ValueError("max_requirements_per_batch must be between 1 and 10")
        if not 1 <= max_cases_per_batch <= 25:
            raise ValueError("max_cases_per_batch must be between 1 and 25")
        if not 256 <= max_tokens_per_batch <= 8192:
            raise ValueError("max_tokens_per_batch must be between 256 and 8192")
        corrections_per_batch = (
            max_retries if max_corrections_per_batch is None else max_corrections_per_batch
        )
        if not 0 <= corrections_per_batch <= 1:
            raise ValueError("max_corrections_per_batch must be between 0 and 1")
        if not 0 <= max_corrections_per_run <= 8:
            raise ValueError("max_corrections_per_run must be between 0 and 8")
        if not 0 <= max_provider_retries_per_batch <= 3:
            raise ValueError("max_provider_retries_per_batch must be between 0 and 3")
        if not 0 <= max_provider_retries_per_run <= 15:
            raise ValueError("max_provider_retries_per_run must be between 0 and 15")
        if max_total_provider_calls < 1:
            raise ValueError("max_total_provider_calls must be positive")
        try:
            max_cost = Decimal(str(max_run_cost_usd))
        except InvalidOperation as error:
            raise ValueError("max_run_cost_usd must be decimal") from error
        if max_cost < 0:
            raise ValueError("max_run_cost_usd must not be negative")
        self.database = database
        self.schemas = schemas or TestCaseSchemas()
        self.intent_schemas = TestIntentSchemas()
        self.prompts = prompts or TestGenerationPromptRegistry()
        self.compiler = DeterministicCandidateCompiler(self.schemas)
        validate_test_intent_prompt_contract(self.prompts, self.intent_schemas)
        self.max_requirements_per_batch = max_requirements_per_batch
        self.max_cases_per_batch = max_cases_per_batch
        self.max_tokens_per_batch = max_tokens_per_batch
        self.max_retries = corrections_per_batch
        self.max_corrections_per_batch = corrections_per_batch
        self.max_corrections_per_run = max_corrections_per_run
        self.max_provider_retries_per_batch = max_provider_retries_per_batch
        self.max_provider_retries_per_run = max_provider_retries_per_run
        self.provider_retry_wait = provider_retry_wait
        self.provider_retry_jitter = provider_retry_jitter
        self.max_total_provider_calls = max_total_provider_calls
        self.max_run_cost_microusd = int(
            (max_cost * Decimal(1_000_000)).quantize(Decimal("1"), rounding=ROUND_CEILING)
        )

    def preflight(self, project_id: str) -> dict[str, Any]:
        snapshots = self._load_requirement_snapshots(project_id)
        plan = self._build_plan(snapshots)
        self.schemas.validate("generation_plan.schema.json", plan)
        return plan

    def start(
        self,
        project_id: str,
        provider: LLMProvider,
        idempotency_key: str,
        resume_run_id: str | None = None,
        recovery_reason: str | None = None,
    ) -> GenerationResult:
        if bool(resume_run_id) != bool(recovery_reason):
            raise TestGenerationError("RECOVERY_LINK_AND_REASON_REQUIRED_TOGETHER")
        if recovery_reason not in {
            None,
            "PROMPT_FIELD_CONTRACT_REPAIR",
            "TEST_INTENT_COMPILER_REDESIGN",
            "SYSTEM_OWNED_GENERATION_SLOTS",
            "PROVIDER_NETWORK_RECOVERY",
        }:
            raise TestGenerationError("RECOVERY_REASON_NOT_APPROVED")
        existing = self.database.fetch_one(
            "SELECT * FROM test_generation_runs WHERE idempotency_key=:key",
            {"key": idempotency_key},
        )
        if existing:
            return self._result(existing)
        snapshots = self._load_requirement_snapshots(project_id)
        plan = self._build_plan(snapshots)
        self.schemas.validate("generation_plan.schema.json", plan)
        metadata = provider.metadata
        run_id = new_id("TGR")
        self._create_run(
            run_id,
            project_id,
            metadata,
            idempotency_key,
            snapshots,
            plan,
            resume_run_id,
            recovery_reason,
        )
        try:
            provider.validate_config()
        except ProviderConfigurationError as error:
            self._terminal(run_id, "blocked", "PROVIDER_CONFIGURATION_ERROR", str(error))
            return self._result_by_id(run_id)
        try:
            validated_batches: list[tuple[GenerationBatch, list[dict[str, Any]]]] = []
            counters = RunCallCounters()
            for batch in self._plan_batches(plan):
                batch_snapshots = [
                    snapshots[requirement_id] for requirement_id in batch.requirement_ids
                ]
                reused = (
                    self._reuse_validated_batch(
                        run_id,
                        resume_run_id,
                        batch,
                        batch_snapshots,
                        provider,
                    )
                    if resume_run_id
                    else None
                )
                validated_batches.append(
                    (
                        batch,
                        reused
                        if reused is not None
                        else self._run_batch(run_id, batch, batch_snapshots, provider, counters),
                    )
                )
            self._assert_snapshots_current(project_id, snapshots)
            cases = [case for _, batch_cases in validated_batches for case in batch_cases]
            aggregate, findings, coverage = self._validate_aggregate(run_id, snapshots, cases)
            self._promote(run_id, snapshots, aggregate, findings, coverage)
        except Exception as error:
            code = _safe_error(error)
            self._terminal(run_id, "failed", code, code)
        return self._result_by_id(run_id)

    def phase6_candidate_collection(self, run_id: str) -> dict[str, Any]:
        run = self.database.fetch_one(
            "SELECT * FROM test_generation_runs WHERE test_generation_run_id=:id", {"id": run_id}
        )
        if not run:
            raise TestGenerationError("GENERATION_RUN_NOT_FOUND")
        if run["status"] != "validated_pending_review":
            raise TestGenerationError("CANDIDATE_COLLECTION_NOT_READY")
        rows = self.database.fetch_all(
            "SELECT case_id, case_version, case_type, content_hash, payload_json "
            "FROM test_case_candidates WHERE test_generation_run_id=:run "
            "ORDER BY case_type, case_id",
            {"run": run_id},
        )
        cases = [json.loads(str(row.pop("payload_json"))) for row in rows]
        return {
            "generation_run_id": run_id,
            "status": run["status"],
            "collection_version": run["collection_version"],
            "collection_hash": run["collection_hash"],
            "candidate_count": run["candidate_count"],
            "review_disposition": "not_reviewed_phase6_required",
            "cases": cases,
        }

    def _load_requirement_snapshots(self, project_id: str) -> dict[str, dict[str, Any]]:
        rows = self.database.fetch_all(
            "SELECT r.requirement_id, r.version_number, r.prd_version_id, r.analysis_run_id, "
            "r.payload_json, r.source_excerpt, p.content_hash AS prd_content_hash, "
            "p.prd_document_id FROM requirements r "
            "JOIN prd_versions p ON p.version_id=r.prd_version_id "
            "WHERE r.project_id=:project ORDER BY r.requirement_id",
            {"project": project_id},
        )
        if len(rows) != EXPECTED_REQUIREMENT_COUNT:
            raise TestGenerationError("FORMAL_REQUIREMENT_COUNT_MISMATCH")
        snapshots: dict[str, dict[str, Any]] = {}
        prd_versions: set[str] = set()
        analysis_runs: set[str] = set()
        for row in rows:
            requirement = json.loads(str(row["payload_json"]))
            requirement_id = str(row["requirement_id"])
            if requirement.get("requirement_id") != requirement_id:
                raise TestGenerationError("REQUIREMENT_PAYLOAD_ID_MISMATCH")
            source_block_id = str(requirement.get("source_block_id") or "")
            if not source_block_id or not row["source_excerpt"]:
                raise TestGenerationError("REQUIREMENT_TRACE_INCOMPLETE")
            payload_hash = _hash_json(requirement)
            snapshot_core = {
                "requirement_id": requirement_id,
                "requirement_version": int(row["version_number"]),
                "payload_hash": payload_hash,
                "prd_version_id": str(row["prd_version_id"]),
                "prd_content_hash": str(row["prd_content_hash"]),
                "source_block_id": source_block_id,
            }
            snapshots[requirement_id] = {
                **snapshot_core,
                "snapshot_hash": _hash_json(snapshot_core),
                "analysis_run_id": str(row["analysis_run_id"]),
                "prd_document_id": str(row["prd_document_id"]),
                "source_excerpt": str(row["source_excerpt"]),
                "requirement": requirement,
            }
            prd_versions.add(str(row["prd_version_id"]))
            analysis_runs.add(str(row["analysis_run_id"]))
        if len(snapshots) != EXPECTED_REQUIREMENT_COUNT:
            raise TestGenerationError("DUPLICATE_FORMAL_REQUIREMENT_ID")
        if len(prd_versions) != 1 or len(analysis_runs) != 1:
            raise TestGenerationError("REQUIREMENT_SNAPSHOT_NOT_COHERENT")
        return snapshots

    def _build_plan(self, snapshots: dict[str, dict[str, Any]]) -> dict[str, Any]:
        applicability: dict[str, list[str]] = {case_type: [] for case_type in CASE_TYPES}
        not_applicable: list[dict[str, str]] = []
        requirement_plan: list[dict[str, Any]] = []
        for requirement_id, snapshot in snapshots.items():
            types = _applicable_types(snapshot["requirement"])
            for case_type in CASE_TYPES:
                if case_type in types:
                    applicability[case_type].append(requirement_id)
                else:
                    not_applicable.append(
                        {
                            "requirement_id": requirement_id,
                            "case_type": case_type,
                            "reason": (
                                "The requirement is not directly observable at this test layer."
                            ),
                        }
                    )
            requirement_plan.append(
                {
                    "requirement_id": requirement_id,
                    "requirement_version": snapshot["requirement_version"],
                    "snapshot_hash": snapshot["snapshot_hash"],
                    "applicable_case_types": list(types),
                }
            )
        try:
            batches, _capacities = build_capacity_bounded_batches(
                snapshots=snapshots,
                applicability=applicability,
                prompts=self.prompts,
                max_requirements_per_batch=self.max_requirements_per_batch,
                max_cases_per_batch=self.max_cases_per_batch,
                max_tokens_per_batch=self.max_tokens_per_batch,
            )
        except Exception as error:
            raise TestGenerationError(str(error)) from error
        snapshot_hash = _hash_json([snapshots[item]["snapshot_hash"] for item in sorted(snapshots)])
        return {
            "schema_version": TEST_CASE_SCHEMA_VERSION,
            "requirement_snapshot_hash": snapshot_hash,
            "requirement_count": len(snapshots),
            "requirements": requirement_plan,
            "generation_slot_count": sum(len(item["generation_slots"]) for item in batches),
            "batches": batches,
            "estimated_call_count": len(batches),
            "max_retries": self.max_retries,
            "coverage_dimensions": [
                "functional",
                "positive",
                "negative",
                "boundary",
                "security",
                "accessibility",
            ],
            "not_applicable": not_applicable,
        }

    def _assert_snapshots_current(
        self, project_id: str, expected: dict[str, dict[str, Any]]
    ) -> None:
        current = self._load_requirement_snapshots(project_id)
        expected_hashes = {key: value["snapshot_hash"] for key, value in expected.items()}
        current_hashes = {key: value["snapshot_hash"] for key, value in current.items()}
        if current_hashes != expected_hashes:
            raise TestGenerationError("STALE_REQUIREMENT_SNAPSHOT")

    def _create_run(
        self,
        run_id: str,
        project_id: str,
        metadata: Any,
        idempotency_key: str,
        snapshots: dict[str, dict[str, Any]],
        plan: dict[str, Any],
        resume_run_id: str | None,
        recovery_reason: str | None,
    ) -> None:
        first = next(iter(snapshots.values()))
        run_cost = calculate_cost(
            provider_mode=metadata.provider_mode,
            input_tokens=0,
            output_tokens=0,
            pricing_provider=metadata.provider,
            pricing_model=metadata.model,
        )
        with self.database.transaction() as connection:
            connection.execute(
                text(
                    "INSERT OR IGNORE INTO prompt_versions(prompt_version_id, semantic_version, "
                    "content_hash, schema_version, status) VALUES "
                    "(:id,:version,:hash,:schema,'active')"
                ),
                {
                    "id": new_id("PMT"),
                    "version": TEST_GENERATION_PROMPT_VERSION,
                    "hash": self.prompts.content_hash,
                    "schema": TEST_INTENT_SCHEMA_VERSION,
                    "compiler_version": TEST_INTENT_COMPILER_VERSION,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO test_generation_runs("
                    "test_generation_run_id,project_id,prd_version_id,source_analysis_run_id,"
                    "resume_source_run_id,recovery_reason,"
                    "provider,model,provider_mode,prompt_version,schema_version,idempotency_key,"
                    "requirement_snapshot_hash,plan_json,plan_hash,status,pricing_provider,"
                    "pricing_model,pricing_version,pricing_checked_at,"
                    "input_cache_hit_rate_usd_per_million,"
                    "input_cache_miss_rate_usd_per_million,output_rate_usd_per_million,"
                    "currency,cost_calculation_version,calculation_assumption) VALUES "
                    "(:id,:project,:prd,:analysis,:resume,:recovery_reason,:provider,:model,:mode,"
                    ":prompt,:schema,:key,"
                    ":snapshot,:plan,:plan_hash,'running',:pricing_provider,:pricing_model,"
                    ":pricing_version,:pricing_checked_at,:hit_rate,:miss_rate,:output_rate,"
                    ":currency,:cost_version,:cost_assumption)"
                ),
                {
                    "id": run_id,
                    "project": project_id,
                    "prd": first["prd_version_id"],
                    "analysis": first["analysis_run_id"],
                    "resume": resume_run_id,
                    "recovery_reason": recovery_reason,
                    "provider": metadata.provider,
                    "model": metadata.model,
                    "mode": metadata.provider_mode,
                    "prompt": TEST_GENERATION_PROMPT_VERSION,
                    "schema": TEST_INTENT_SCHEMA_VERSION,
                    "compiler_version": TEST_INTENT_COMPILER_VERSION,
                    "key": idempotency_key,
                    "snapshot": plan["requirement_snapshot_hash"],
                    "plan": self.database.encode_json(plan),
                    "plan_hash": _hash_json(plan),
                    "pricing_provider": run_cost.pricing_provider,
                    "pricing_model": run_cost.pricing_model,
                    "pricing_version": run_cost.pricing_version,
                    "pricing_checked_at": run_cost.pricing_checked_at,
                    "hit_rate": run_cost.input_cache_hit_rate_usd_per_million,
                    "miss_rate": run_cost.input_cache_miss_rate_usd_per_million,
                    "output_rate": run_cost.output_rate_usd_per_million,
                    "currency": run_cost.currency,
                    "cost_version": run_cost.cost_calculation_version,
                    "cost_assumption": run_cost.calculation_assumption,
                },
            )
            for batch in self._plan_batches(plan):
                connection.execute(
                    text(
                        "INSERT INTO test_generation_batches("
                        "test_generation_batch_id,test_generation_run_id,batch_key,batch_index,"
                        "case_type,requirement_ids_json,input_hash,max_cases,max_tokens,status) "
                        "VALUES (:id,:run,:key,:index,:type,:requirements,:hash,:max_cases,"
                        ":max_tokens,'pending')"
                    ),
                    {
                        "id": new_id("TGB"),
                        "run": run_id,
                        "key": batch.batch_key,
                        "index": batch.batch_index,
                        "type": batch.case_type,
                        "requirements": self.database.encode_json(list(batch.requirement_ids)),
                        "hash": batch.input_hash,
                        "max_cases": batch.max_cases,
                        "max_tokens": batch.max_tokens,
                    },
                )
            self._audit_tx(connection, run_id, None, "plan_created", "passed", plan)

    def _reuse_validated_batch(
        self,
        run_id: str,
        resume_run_id: str,
        batch: GenerationBatch,
        snapshots: list[dict[str, Any]],
        provider: LLMProvider,
    ) -> list[dict[str, Any]] | None:
        qualification = self.qualify_checkpoint(
            resume_run_id=resume_run_id,
            batch=batch,
            snapshots=snapshots,
            provider_metadata=provider.metadata,
            target_run_id=run_id,
        )
        if not qualification.reusable:
            row = self.database.fetch_one(
                "SELECT test_generation_batch_id FROM test_generation_batches "
                "WHERE test_generation_run_id=:run AND batch_key=:key",
                {"run": run_id, "key": batch.batch_key},
            )
            if not row:
                raise TestGenerationError("GENERATION_BATCH_NOT_FOUND")
            self._audit(
                run_id,
                str(row["test_generation_batch_id"]),
                "checkpoint_reuse_rejected",
                "passed",
                {
                    "resume_source_run_id": resume_run_id,
                    "batch_key": batch.batch_key,
                    "reason": qualification.rejection_reason,
                    "fallback": "provider_generation",
                    "structure_correction_consumed": False,
                },
            )
            return None
        enriched = list(qualification.candidates)
        row = self.database.fetch_one(
            "SELECT test_generation_batch_id FROM test_generation_batches "
            "WHERE test_generation_run_id=:run AND input_hash=:hash",
            {"run": run_id, "hash": batch.input_hash},
        )
        if not row:
            raise TestGenerationError("GENERATION_BATCH_NOT_FOUND")
        batch_id = str(row["test_generation_batch_id"])
        self.database.execute(
            "UPDATE test_generation_batches SET status='validated',retry_count=0,"
            "reported_count=:reported,actual_count=:actual,finish_reason='reused_checkpoint',"
            "validation_status='valid',completed_at=CURRENT_TIMESTAMP "
            "WHERE test_generation_batch_id=:id",
            {"reported": len(enriched), "actual": len(enriched), "id": batch_id},
        )
        self._audit(
            run_id,
            batch_id,
            "validated_batch_reused",
            "passed",
            {
                "resume_source_run_id": resume_run_id,
                "source_run_id": qualification.source_run_id,
                "source_batch_id": qualification.source_batch_id,
                "source_call_id": qualification.source_call_id,
                "source_response_hash": qualification.response_hash,
                "source_semantic_hash": qualification.semantic_hash,
                "compatible_recovery_key": batch.input_hash,
                "prompt_hash": self.prompts.content_hash,
                "intent_schema_version": TEST_INTENT_SCHEMA_VERSION,
                "candidate_schema_version": TEST_CASE_SCHEMA_VERSION,
                "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                "compiler_version": TEST_INTENT_COMPILER_VERSION,
            },
        )
        return enriched

    def qualify_checkpoint(
        self,
        *,
        resume_run_id: str,
        batch: GenerationBatch,
        snapshots: list[dict[str, Any]],
        provider_metadata: ProviderMetadata,
        target_run_id: str | None = None,
    ) -> CheckpointQualification:
        current_snapshot_hashes = {
            str(item["requirement_id"]): str(item["snapshot_hash"]) for item in snapshots
        }
        visited: set[str] = set()
        source_run_id: str | None = resume_run_id
        last_rejection = "CHECKPOINT_NOT_FOUND"
        depth = 0
        while source_run_id is not None:
            if source_run_id in visited:
                raise TestGenerationError("CHECKPOINT_PARENT_CYCLE")
            if depth >= MAX_CHECKPOINT_PARENT_DEPTH:
                raise TestGenerationError("CHECKPOINT_PARENT_DEPTH_EXCEEDED")
            visited.add(source_run_id)
            depth += 1
            run = self.database.fetch_one(
                "SELECT resume_source_run_id,requirement_snapshot_hash,plan_json "
                "FROM test_generation_runs WHERE test_generation_run_id=:run",
                {"run": source_run_id},
            )
            if not run:
                raise TestGenerationError("CHECKPOINT_PARENT_RUN_NOT_FOUND")
            source_plan_document = json.loads(str(run["plan_json"]))
            source_snapshot_hashes = {
                str(item["requirement_id"]): str(item["snapshot_hash"])
                for item in source_plan_document.get("requirements", [])
                if str(item.get("requirement_id")) in current_snapshot_hashes
            }
            if source_snapshot_hashes != current_snapshot_hashes:
                return CheckpointQualification(
                    batch.batch_key, False, "REQUIREMENT_SNAPSHOT_MISMATCH"
                )
            source_batches = {
                str(item["batch_key"]): item for item in source_plan_document.get("batches", [])
            }
            source_plan = source_batches.get(batch.batch_key)
            if not source_plan or not self._checkpoint_plan_matches(batch, source_plan):
                last_rejection = "CHECKPOINT_BATCH_CONTRACT_MISMATCH"
                source_run_id = (
                    str(run["resume_source_run_id"]) if run["resume_source_run_id"] else None
                )
                continue
            sources = self.database.fetch_all(
                "SELECT b.test_generation_batch_id,c.test_generation_llm_call_id,"
                "c.retry_count,c.http_status,c.finish_reason,a.response_content,a.response_hash,"
                "COALESCE(p.parsed_json,a.parsed_json) AS parsed_json,p.parsed_hash "
                "FROM test_generation_batches b "
                "JOIN test_generation_llm_calls c ON c.test_generation_batch_id="
                "b.test_generation_batch_id "
                "JOIN test_generation_response_artifacts a ON "
                "a.test_generation_llm_call_id=c.test_generation_llm_call_id "
                "LEFT JOIN test_generation_parsed_artifacts p "
                "ON p.test_generation_llm_call_id=c.test_generation_llm_call_id "
                "AND p.artifact_origin='runtime' "
                "WHERE b.test_generation_run_id=:source AND b.batch_key=:key "
                "AND c.http_status=200 AND c.finish_reason='stop' "
                "ORDER BY c.retry_count DESC,c.created_at DESC,c.test_generation_llm_call_id DESC",
                {"source": source_run_id, "key": batch.batch_key},
            )
            for source in sources:
                qualification = self._qualify_checkpoint_artifact(
                    source_run_id=source_run_id,
                    source=source,
                    batch=batch,
                    snapshots=snapshots,
                    provider_metadata=provider_metadata,
                    target_run_id=target_run_id,
                )
                if qualification.reusable:
                    return qualification
                last_rejection = qualification.rejection_reason or "CHECKPOINT_REJECTED"
            source_run_id = (
                str(run["resume_source_run_id"]) if run["resume_source_run_id"] else None
            )
        return CheckpointQualification(batch.batch_key, False, last_rejection)

    @staticmethod
    def _checkpoint_plan_matches(batch: GenerationBatch, source: dict[str, Any]) -> bool:
        return (
            source.get("case_type") == batch.case_type
            and tuple(source.get("requirement_ids", ())) == batch.requirement_ids
            and tuple(
                str(slot.get("generation_slot_id")) for slot in source.get("generation_slots", ())
            )
            == tuple(str(slot["generation_slot_id"]) for slot in batch.generation_slots)
        )

    def _qualify_checkpoint_artifact(
        self,
        *,
        source_run_id: str,
        source: dict[str, Any],
        batch: GenerationBatch,
        snapshots: list[dict[str, Any]],
        provider_metadata: ProviderMetadata,
        target_run_id: str | None,
    ) -> CheckpointQualification:
        if not source["parsed_json"]:
            return CheckpointQualification(batch.batch_key, False, "PARSED_ARTIFACT_MISSING")
        response_content = str(source["response_content"])
        if hashlib.sha256(response_content.encode()).hexdigest() != source["response_hash"]:
            raise TestGenerationError("RESPONSE_ARTIFACT_HASH_MISMATCH")
        try:
            parsed = json.loads(str(source["parsed_json"]))
        except (TypeError, ValueError):
            return CheckpointQualification(batch.batch_key, False, "PARSED_ARTIFACT_INVALID_JSON")
        if source["parsed_hash"] and _hash_json(parsed) != source["parsed_hash"]:
            raise TestGenerationError("PARSED_ARTIFACT_HASH_MISMATCH")
        try:
            accepted = normalize_intent_batch(parsed)
            self._validate_batch_envelope(batch, accepted)
            context_run_id = target_run_id or source_run_id
            candidates = tuple(
                self._compile_intent_with_metadata(
                    context_run_id, provider_metadata, batch, snapshots, intent
                )
                for intent in accepted["intents"]
            )
        except TestGenerationError as error:
            return CheckpointQualification(batch.batch_key, False, _safe_error(error))
        return CheckpointQualification(
            batch.batch_key,
            True,
            None,
            source_run_id,
            str(source["test_generation_batch_id"]),
            str(source["test_generation_llm_call_id"]),
            str(source["response_hash"]),
            _hash_json(parsed),
            candidates,
        )

    def _run_batch(
        self,
        run_id: str,
        batch: GenerationBatch,
        snapshots: list[dict[str, Any]],
        provider: LLMProvider,
        counters: RunCallCounters | None = None,
    ) -> list[dict[str, Any]]:
        counters = counters or RunCallCounters()
        row = self.database.fetch_one(
            "SELECT test_generation_batch_id FROM test_generation_batches "
            "WHERE test_generation_run_id=:run AND batch_key=:key",
            {"run": run_id, "key": batch.batch_key},
        )
        if not row:
            raise TestGenerationError("GENERATION_BATCH_NOT_FOUND")
        batch_id = str(row["test_generation_batch_id"])
        validation_error: str | None = None
        for correction_index in range(self.max_corrections_per_batch + 1):
            parsed: dict[str, Any] | None = None
            call_id: str | None = None
            response: ProviderResponse | None = None
            self.database.execute(
                "UPDATE test_generation_batches SET status='running',retry_count=:retry "
                "WHERE test_generation_batch_id=:id",
                {"retry": correction_index, "id": batch_id},
            )
            try:
                provider_retry_index = 0
                while True:
                    call_type = (
                        "provider_retry"
                        if provider_retry_index
                        else "structure_correction"
                        if correction_index
                        else "initial"
                    )
                    self._check_call_budget(run_id, batch.batch_key, correction_index, counters)
                    counters.total_provider_call_count += 1
                    if provider_retry_index:
                        counters.provider_retry_count += 1
                    elif correction_index == 0:
                        counters.initial_call_count += 1
                    else:
                        counters.correction_call_count += 1
                    self._audit(
                        run_id,
                        batch_id,
                        "provider_call_started",
                        "pending",
                        {
                            "call_type": call_type,
                            "correction_index": correction_index,
                            "provider_retry_index": provider_retry_index,
                            "total_provider_call_count": counters.total_provider_call_count,
                        },
                    )
                    try:
                        response = provider.generate_test_cases(
                            case_type=batch.case_type,
                            batch_id=batch.batch_key,
                            generation_run_id=run_id,
                            generation_slots=[
                                {
                                    **slot,
                                    "snapshot": next(
                                        item
                                        for item in snapshots
                                        if item["requirement_id"] == slot["primary_requirement_id"]
                                    ),
                                }
                                for slot in batch.generation_slots
                            ],
                            max_cases=batch.max_cases,
                            max_tokens=batch.max_tokens,
                            recovery=correction_index > 0,
                            validation_error=validation_error,
                        )
                        break
                    except ProviderCallError as error:
                        self._persist_failed_call(
                            run_id, batch_id, correction_index, provider, error
                        )
                        can_retry = (
                            error.retryable
                            and provider_retry_index < self.max_provider_retries_per_batch
                            and counters.provider_retry_count < self.max_provider_retries_per_run
                            and counters.total_provider_call_count < self.max_total_provider_calls
                        )
                        if not can_retry:
                            self._fail_batch(batch_id, correction_index, error.error_type)
                            raise
                        provider_retry_index += 1
                        jitter = min(max(float(self.provider_retry_jitter()), 0.0), 1.0)
                        delay_seconds = min(float(2**provider_retry_index), 8.0) + jitter
                        delay_seconds = min(delay_seconds, 10.0)
                        self._audit(
                            run_id,
                            batch_id,
                            "provider_retry_requested",
                            "pending",
                            {
                                "call_type": "provider_retry",
                                "failure_code": error.error_type,
                                "batch_provider_retry_count": provider_retry_index,
                                "run_provider_retry_count": counters.provider_retry_count + 1,
                                "total_provider_call_count": counters.total_provider_call_count,
                                "delay_seconds": delay_seconds,
                                "jitter_seconds": jitter,
                            },
                        )
                        self.provider_retry_wait(delay_seconds)
                parsed = parse_json_object(response)
                call_id = self._persist_call(
                    run_id,
                    batch_id,
                    correction_index,
                    provider,
                    response,
                    parsed,
                    "parsed",
                    None,
                )
                try:
                    accepted = normalize_intent_batch(parsed)
                    self._validate_batch_envelope(batch, accepted)
                    compiled = [
                        self._compile_intent(run_id, provider, batch, snapshots, intent)
                        for intent in accepted["intents"]
                    ]
                except Exception as error:
                    code = _safe_error(error)
                    schema_error = _caused_by_schema_error(error)
                    if schema_error is not None:
                        self._audit(
                            run_id,
                            batch_id,
                            "schema_validation_failed",
                            "failed",
                            {
                                "error_type": code,
                                "details": safe_schema_error_details(
                                    schema_error,
                                    validation_stage=(
                                        "intent_schema"
                                        if isinstance(error, IntentSchemaValidationError)
                                        else "candidate_schema"
                                    ),
                                ),
                            },
                        )
                    self._persist_validation_outcome(call_id, "invalid", code)
                    raise
                self._persist_validation_outcome(call_id, "valid", None)
                self.database.execute(
                    "UPDATE test_generation_batches SET status='validated',retry_count=:retry,"
                    "reported_count=:reported,actual_count=:actual,finish_reason=:finish,"
                    "validation_status='valid',completed_at=CURRENT_TIMESTAMP "
                    "WHERE test_generation_batch_id=:id",
                    {
                        "retry": correction_index,
                        "reported": len(parsed["intents"]),
                        "actual": len(compiled),
                        "finish": response.finish_reason,
                        "id": batch_id,
                    },
                )
                self._audit(
                    run_id,
                    batch_id,
                    "intent_batch_compiled",
                    "passed",
                    {
                        "retry": correction_index,
                        "intent_count": len(parsed["intents"]),
                        "candidate_count": len(compiled),
                        "compiler_version": TEST_INTENT_COMPILER_VERSION,
                        "intent_schema_version": TEST_INTENT_SCHEMA_VERSION,
                        "candidate_schema_version": TEST_CASE_SCHEMA_VERSION,
                        "compatibility_records": compatibility_audit_records(parsed["intents"]),
                    },
                )
                return compiled
            except Exception as error:
                code = _safe_error(error)
                if response is not None and call_id is None:
                    call_id = self._persist_call(
                        run_id,
                        batch_id,
                        correction_index,
                        provider,
                        response,
                        parsed,
                        "invalid",
                        code,
                    )
                    if parsed is not None:
                        self._persist_validation_outcome(call_id, "invalid", code)
                correction_allowed = (
                    is_structure_correction_eligible(code, response)
                    and correction_index < self.max_corrections_per_batch
                )
                if not correction_allowed:
                    self._fail_batch(batch_id, correction_index, code)
                    raise
                if counters.correction_call_count >= self.max_corrections_per_run:
                    self._fail_batch(batch_id, correction_index, "CORRECTION_BUDGET_EXCEEDED")
                    raise TestGenerationError("CORRECTION_BUDGET_EXCEEDED") from error
                validation_error = code
                if code == "JSON_PARSE_ERROR" and response is not None:
                    safe_content, _ = _redact_response(response.content)
                    validation_error = (
                        "JSON_PARSE_ERROR; safely redacted malformed response to repair: "
                        + safe_content[:20_000]
                    )
                self._audit(
                    run_id,
                    batch_id,
                    "intent_correction_requested",
                    "pending",
                    {
                        "retry": correction_index + 1,
                        "call_type": "structure_correction",
                        "batch_correction_count": correction_index + 1,
                        "run_correction_count": counters.correction_call_count + 1,
                        "total_provider_call_count": counters.total_provider_call_count,
                        "failure_code": code,
                        "same_batch_only": True,
                    },
                )
        raise TestGenerationError("GENERATION_RETRY_EXHAUSTED")

    def _check_call_budget(
        self,
        run_id: str,
        batch_key: str,
        retry: int,
        counters: RunCallCounters,
    ) -> None:
        if retry > self.max_corrections_per_batch:
            raise TestGenerationError("CORRECTION_BUDGET_EXCEEDED")
        if retry > 0 and counters.correction_call_count >= self.max_corrections_per_run:
            raise TestGenerationError("CORRECTION_BUDGET_EXCEEDED")
        if counters.total_provider_call_count >= self.max_total_provider_calls:
            raise TestGenerationError("CALL_BUDGET_EXCEEDED")
        row = self.database.fetch_one(
            "SELECT actual_cost_microusd FROM test_generation_runs "
            "WHERE test_generation_run_id=:run",
            {"run": run_id},
        )
        if row and int(row["actual_cost_microusd"] or 0) >= self.max_run_cost_microusd:
            raise TestGenerationError("BUDGET_EXCEEDED")
        self._audit(
            run_id,
            None,
            "provider_call_budget_checked",
            "passed",
            {
                "batch_key": batch_key,
                "call_type": "initial" if retry == 0 else "correction",
                "batch_correction_count": retry,
                "run_correction_count": counters.correction_call_count,
                "initial_call_count": counters.initial_call_count,
                "correction_call_count": counters.correction_call_count,
                "provider_retry_count": counters.provider_retry_count,
                "total_provider_call_count": counters.total_provider_call_count,
                "accumulated_cost_microusd": int(row["actual_cost_microusd"] or 0) if row else 0,
                "prompt_version": TEST_GENERATION_PROMPT_VERSION,
                "schema_version": TEST_INTENT_SCHEMA_VERSION,
            },
        )

    def _validate_batch_envelope(self, batch: GenerationBatch, parsed: dict[str, Any]) -> None:
        if set(parsed) != {"intents"}:
            raise TestGenerationError("INTENT_RESPONSE_FIELD_BOUNDARY_INVALID")
        intents = parsed.get("intents")
        if not isinstance(intents, list) or any(
            not isinstance(intent, dict) or set(intent) != INTENT_FIELDS for intent in intents
        ):
            raise TestGenerationError("INTENT_FIELD_BOUNDARY_INVALID")
        try:
            self.intent_schemas.validate(f"{batch.case_type}_intent_batch.schema.json", parsed)
        except JsonSchemaError as error:
            raise IntentSchemaValidationError("INTENT_SCHEMA_VALIDATION") from error
        expected = [str(slot["generation_slot_id"]) for slot in batch.generation_slots]
        actual = [str(intent["generation_slot_id"]) for intent in intents]
        if len(actual) != len(set(actual)):
            raise TestGenerationError("GENERATION_SLOT_DUPLICATE")
        if set(actual) - set(expected):
            raise TestGenerationError("GENERATION_SLOT_UNKNOWN_OR_CROSS_BATCH")
        if set(expected) - set(actual):
            raise TestGenerationError("GENERATION_SLOT_MISSING")
        if len(intents) > batch.max_cases:
            raise TestGenerationError("BATCH_CASE_LIMIT_EXCEEDED")

    def _compile_intent(
        self,
        run_id: str,
        provider: LLMProvider,
        batch: GenerationBatch,
        snapshots: list[dict[str, Any]],
        intent: Any,
    ) -> dict[str, Any]:
        return self._compile_intent_with_metadata(
            run_id, provider.metadata, batch, snapshots, intent
        )

    def _compile_intent_with_metadata(
        self,
        run_id: str,
        provider_metadata: ProviderMetadata,
        batch: GenerationBatch,
        snapshots: list[dict[str, Any]],
        intent: Any,
    ) -> dict[str, Any]:
        if not isinstance(intent, dict) or set(intent) != INTENT_FIELDS:
            raise TestGenerationError("INTENT_FIELD_BOUNDARY_INVALID")
        available = {item["requirement_id"]: item for item in snapshots}
        try:
            candidate = self.compiler.compile(
                intent,
                CompilationContext(
                    run_id=run_id,
                    project_id=self._run_project_id(run_id),
                    provider=provider_metadata,
                    snapshots=available,
                    slots={
                        str(slot["generation_slot_id"]): slot for slot in batch.generation_slots
                    },
                ),
            )
        except JsonSchemaError as error:
            raise CandidateSchemaValidationError("CANDIDATE_SCHEMA_VALIDATION") from error
        except TestIntentCompilationError as error:
            raise CandidateCompilationError("COMPILATION_ERROR") from error
        self._validate_candidate_domain(candidate, batch)
        return candidate

    def _validate_candidate_domain(self, candidate: dict[str, Any], batch: GenerationBatch) -> None:
        prefix = {"api": "TC-API-", "ui": "TC-UI-", "manual": "TC-MAN-"}[batch.case_type]
        if not str(candidate["case_id"]).startswith(prefix):
            raise TestGenerationError("CASE_ID_TYPE_MISMATCH")
        details = candidate["type_details"]
        if candidate["primary_requirement_id"] not in candidate["requirement_ids"]:
            raise TestGenerationError("PRIMARY_REQUIREMENT_LINK_INVALID")
        if details["kind"] != batch.case_type:
            raise TestGenerationError("TYPE_DETAILS_MISMATCH")
        steps = candidate["steps"]
        expected_steps = [f"STEP-{index:03d}" for index in range(1, len(steps) + 1)]
        if [step["step_id"] for step in steps] != expected_steps:
            raise TestGenerationError("STEP_ORDER_INVALID")
        serialized = json.dumps(candidate, ensure_ascii=False)
        if _contains_secret(serialized):
            raise TestGenerationError("SENSITIVE_VALUE_DETECTED")
        if re.search(r"\b(?:PASS|FAIL)\b", serialized):
            raise TestGenerationError("AI_VERDICT_FORBIDDEN")
        if batch.case_type == "api":
            if details["method"] == "N/A":
                if details["path"] != "" or details["expected_status"] != 0:
                    raise TestGenerationError("API_UNRESOLVED_TARGET_INCONSISTENT")
            elif not str(details["path"]).startswith("/") or "://" in details["path"]:
                raise TestGenerationError("API_PATH_INVALID")
            if (
                details["expected_status"] != 0
                and details["expected_status"] not in APPROVED_API_STATUSES
            ):
                raise TestGenerationError("API_STATUS_NOT_APPROVED")
        if batch.case_type == "ui":
            if not str(details["route"]).startswith("/") or "://" in details["route"]:
                raise TestGenerationError("UI_ROUTE_INVALID")
            if any(
                locator["strategy"] not in {"role", "label", "name", "test-id", "placeholder"}
                for locator in details["locator_intents"]
            ):
                raise TestGenerationError("FRAGILE_LOCATOR_FORBIDDEN")
        if candidate["content_hash"] != _case_hash(candidate):
            raise TestGenerationError("CASE_CONTENT_HASH_MISMATCH")

    def _validate_aggregate(
        self,
        run_id: str,
        snapshots: dict[str, dict[str, Any]],
        cases: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
        if not cases:
            raise TestGenerationError("NO_CANDIDATE_CASES")
        ids = [case["case_id"] for case in cases]
        if len(ids) != len(set(ids)):
            raise TestGenerationError("DUPLICATE_CASE_ID")
        signatures: dict[str, dict[str, Any]] = {}
        scenarios: dict[str, str] = {}
        findings: list[dict[str, Any]] = []
        for case in cases:
            signature = _duplicate_signature(case)
            if signature in signatures:
                raise TestGenerationError("DETERMINISTIC_DUPLICATE_CASE")
            signatures[signature] = case
            scenario = _scenario_signature(case)
            oracle = _hash_json(case["expected_results"])
            if scenario in scenarios and scenarios[scenario] != oracle:
                raise TestGenerationError("CONFLICTING_EXPECTED_RESULT")
            scenarios[scenario] = oracle
        coverage: list[dict[str, Any]] = []
        covered: set[str] = set()
        for requirement_id in snapshots:
            case_ids = sorted(
                case["case_id"] for case in cases if requirement_id in case["requirement_ids"]
            )
            status = "covered" if case_ids else "gap"
            coverage.append(
                {
                    "requirement_id": requirement_id,
                    "dimension": "requirement",
                    "status": status,
                    "case_ids": case_ids,
                    "rationale": (
                        "At least one validated candidate links the immutable requirement snapshot."
                    )
                    if case_ids
                    else "No validated candidate links this requirement.",
                }
            )
            if case_ids:
                covered.add(requirement_id)
        if covered != set(snapshots):
            raise TestGenerationError("REQUIREMENT_COVERAGE_INCOMPLETE")
        if {case["case_type"] for case in cases} != set(CASE_TYPES):
            raise TestGenerationError("CASE_TYPE_COVERAGE_INCOMPLETE")
        categories = {case["test_category"] for case in cases}
        required_categories = {"positive", "boundary", "security", "accessibility"}
        if not required_categories <= categories:
            raise TestGenerationError("COVERAGE_DIMENSION_MISSING")
        seeded_resolution = self._validate_seeded_defect(cases, snapshots)
        ordered = sorted(cases, key=lambda item: (item["case_type"], item["case_id"]))
        collection_hash = _hash_json(ordered)
        aggregate = {
            "schema_version": TEST_CASE_SCHEMA_VERSION,
            "generation_run_id": run_id,
            "requirement_snapshot_hash": _hash_json(
                [snapshots[item]["snapshot_hash"] for item in sorted(snapshots)]
            ),
            "collection_version": 1,
            "collection_hash": collection_hash,
            "status": "validated_pending_review",
            "cases": ordered,
            "coverage_complete": True,
            "aggregate_complete": True,
        }
        self.schemas.validate("test_case_candidate_aggregate.schema.json", aggregate)
        findings.append(
            {
                "scope": "aggregate",
                "rule_code": "BUG_AUTH_001_REQUIREMENT_RESOLUTION",
                "status": "passed",
                "details": seeded_resolution,
            }
        )
        findings.append(
            {
                "scope": "aggregate",
                "rule_code": "EXACT_DUPLICATE_AND_CONFLICT_SCAN",
                "status": "passed",
                "details": {"signature_count": len(signatures), "conflicts": 0},
            }
        )
        return aggregate, findings, coverage

    def _validate_seeded_defect(
        self, cases: list[dict[str, Any]], snapshots: dict[str, dict[str, Any]]
    ) -> dict[str, Any]:
        try:
            resolution = resolve_seeded_username_requirement(snapshots)
        except SeededRequirementResolutionError as error:
            raise TestGenerationError(str(error)) from error
        requirement_id = resolution.resolved_requirement_id
        api_case = next((case for case in cases if case["case_id"] == "TC-API-AUTH-REG-005"), None)
        ui_case = next((case for case in cases if case["case_id"] == "TC-UI-AUTH-REG-005"), None)
        if not api_case or not ui_case:
            raise TestGenerationError("BUG_AUTH_001_GUARD_CASES_MISSING")
        if (
            requirement_id not in api_case["requirement_ids"]
            or requirement_id not in ui_case["requirement_ids"]
        ):
            raise TestGenerationError("BUG_AUTH_001_REQUIREMENT_LINK_MISSING")
        api_text = json.dumps(api_case, ensure_ascii=False).lower()
        ui_text = json.dumps(ui_case, ensure_ascii=False).lower()
        if "z1234" not in api_text or "test1234" not in api_text:
            raise TestGenerationError("BUG_AUTH_001_API_DATA_MISSING")
        if api_case["type_details"]["expected_status"] != 400 or "201" in " ".join(
            api_case["expected_results"]
        ):
            raise TestGenerationError("BUG_AUTH_001_ORACLE_INVALID")
        if "z1234" not in ui_text or "six" not in ui_text:
            raise TestGenerationError("BUG_AUTH_001_UI_GUARD_INVALID")
        return resolution.as_dict()

    def _promote(
        self,
        run_id: str,
        snapshots: dict[str, dict[str, Any]],
        aggregate: dict[str, Any],
        findings: list[dict[str, Any]],
        coverage: list[dict[str, Any]],
    ) -> None:
        with self.database.transaction() as connection:
            existing = connection.execute(
                text("SELECT COUNT(*) FROM test_case_candidates WHERE test_generation_run_id=:run"),
                {"run": run_id},
            ).scalar_one()
            if existing:
                raise TestGenerationError("CANDIDATE_COLLECTION_ALREADY_EXISTS")
            batch_specs = {
                row["batch_key"]: {
                    "id": row["test_generation_batch_id"],
                    "requirements": set(json.loads(row["requirement_ids_json"])),
                }
                for row in connection.execute(
                    text(
                        "SELECT batch_key,test_generation_batch_id,requirement_ids_json "
                        "FROM test_generation_batches WHERE test_generation_run_id=:run"
                    ),
                    {"run": run_id},
                ).mappings()
            }
            candidate_ids: dict[str, str] = {}
            for case in aggregate["cases"]:
                candidate_id = new_id("TCC")
                candidate_ids[case["case_id"]] = candidate_id
                batch_key = _batch_key_for_case(case, batch_specs)
                connection.execute(
                    text(
                        "INSERT INTO test_case_candidates("
                        "test_case_candidate_id,test_generation_run_id,test_generation_batch_id,"
                        "case_id,case_version,case_type,payload_json,content_hash,"
                        "lifecycle_status) "
                        "VALUES (:id,:run,:batch,:case_id,1,:type,:payload,:hash,"
                        "'validated_pending_review')"
                    ),
                    {
                        "id": candidate_id,
                        "run": run_id,
                        "batch": batch_specs[batch_key]["id"],
                        "case_id": case["case_id"],
                        "type": case["case_type"],
                        "payload": self.database.encode_json(case),
                        "hash": case["content_hash"],
                    },
                )
                trace_by_id = {
                    item["requirement_id"]: item for item in case["trace"]["requirements"]
                }
                for requirement_id in case["requirement_ids"]:
                    snapshot = snapshots[requirement_id]
                    link_type = (
                        "negative_boundary" if "negative-boundary" in case["tags"] else "verifies"
                    )
                    connection.execute(
                        text(
                            "INSERT INTO test_case_candidate_requirement_links("
                            "test_case_candidate_requirement_link_id,test_case_candidate_id,"
                            "requirement_id,requirement_version,requirement_snapshot_hash,"
                            "source_block_id,link_type) VALUES "
                            "(:id,:candidate,:requirement,:version,:hash,:block,:type)"
                        ),
                        {
                            "id": new_id("TCL"),
                            "candidate": candidate_id,
                            "requirement": requirement_id,
                            "version": snapshot["requirement_version"],
                            "hash": trace_by_id[requirement_id]["snapshot_hash"],
                            "block": snapshot["source_block_id"],
                            "type": link_type,
                        },
                    )
                self._validation_tx(
                    connection,
                    run_id,
                    candidate_id,
                    "candidate",
                    "CANDIDATE_SCHEMA_AND_DOMAIN",
                    "passed",
                    {"case_id": case["case_id"]},
                )
            for finding in findings:
                self._validation_tx(
                    connection,
                    run_id,
                    None,
                    finding["scope"],
                    finding["rule_code"],
                    finding["status"],
                    finding["details"],
                )
            for result in coverage:
                connection.execute(
                    text(
                        "INSERT INTO test_case_coverage_results("
                        "test_case_coverage_result_id,test_generation_run_id,requirement_id,"
                        "dimension,status,case_ids_json,rationale) VALUES "
                        "(:id,:run,:requirement,:dimension,:status,:cases,:rationale)"
                    ),
                    {
                        "id": new_id("TCR"),
                        "run": run_id,
                        "requirement": result["requirement_id"],
                        "dimension": result["dimension"],
                        "status": result["status"],
                        "cases": self.database.encode_json(result["case_ids"]),
                        "rationale": result["rationale"],
                    },
                )
            seeded_resolution = resolve_seeded_username_requirement(snapshots)
            self._audit_tx(
                connection,
                run_id,
                None,
                "seeded_requirement_resolved",
                "passed",
                seeded_resolution.as_dict(),
            )
            self._audit_tx(
                connection,
                run_id,
                None,
                "candidate_collection_promoted",
                "passed",
                {
                    "candidate_count": len(aggregate["cases"]),
                    "collection_hash": aggregate["collection_hash"],
                    "review_status": "draft",
                },
            )
            connection.execute(
                text(
                    "UPDATE test_generation_runs SET status='validated_pending_review',"
                    "validation_status='valid',collection_version=1,collection_hash=:hash,"
                    "candidate_count=:count,completed_at=CURRENT_TIMESTAMP "
                    "WHERE test_generation_run_id=:id"
                ),
                {
                    "hash": aggregate["collection_hash"],
                    "count": len(aggregate["cases"]),
                    "id": run_id,
                },
            )

    def _persist_call(
        self,
        run_id: str,
        batch_id: str,
        retry: int,
        provider: LLMProvider,
        response: ProviderResponse,
        parsed: dict[str, Any] | None,
        validation_status: str,
        error_type: str | None,
    ) -> str:
        call_id = new_id("TGC")
        redacted, applied = _redact_response(response.content)
        parsed_value = None
        if parsed is not None:
            parsed_value, parsed_redacted = redact_parsed_json(parsed)
            applied = applied or parsed_redacted
        input_tokens = int(response.input_tokens or 0)
        output_tokens = int(response.output_tokens or 0)
        metadata = provider.metadata
        actual_cost = calculate_cost(
            provider_mode=metadata.provider_mode,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            input_cache_hit_tokens=response.input_cache_hit_tokens,
            input_cache_miss_tokens=response.input_cache_miss_tokens,
            pricing_provider=metadata.provider,
            pricing_model=metadata.model,
        )
        estimated_cost = calculate_cost(
            provider_mode=metadata.provider_mode,
            input_tokens=input_tokens,
            output_tokens=response.max_tokens,
            estimated=True,
            pricing_provider=metadata.provider,
            pricing_model=metadata.model,
        )
        with self.database.transaction() as connection:
            connection.execute(
                text(
                    "INSERT INTO test_generation_llm_calls("
                    "test_generation_llm_call_id,test_generation_run_id,"
                    "test_generation_batch_id,provider,model,provider_mode,provider_request_id,"
                    "prompt_version,prompt_hash,schema_version,retry_count,http_status,"
                    "finish_reason,input_tokens,input_cache_hit_tokens,input_cache_miss_tokens,"
                    "output_tokens,pricing_provider,pricing_model,pricing_version,"
                    "pricing_checked_at,input_cache_hit_rate_usd_per_million,"
                    "input_cache_miss_rate_usd_per_million,output_rate_usd_per_million,"
                    "estimated_cost_microusd,actual_cost_microusd,currency,"
                    "cost_calculation_version,calculation_assumption,max_tokens,latency_ms,"
                    "validation_status,error_type,redacted_error) VALUES "
                    "(:id,:run,:batch,:provider,:model,:mode,:request,:prompt,:prompt_hash,"
                    ":schema,:retry,:http,:finish,:input,:hit_tokens,:miss_tokens,:output,"
                    ":pricing_provider,:pricing_model,:pricing_version,:pricing_checked_at,"
                    ":hit_rate,:miss_rate,:output_rate,:estimated_cost,:actual_cost,:currency,"
                    ":cost_version,:cost_assumption,:max_tokens,:latency,:validation,:error,"
                    ":redacted)"
                ),
                {
                    "id": call_id,
                    "run": run_id,
                    "batch": batch_id,
                    "provider": metadata.provider,
                    "model": metadata.model,
                    "mode": metadata.provider_mode,
                    "request": response.provider_request_id,
                    "prompt": TEST_GENERATION_PROMPT_VERSION,
                    "prompt_hash": self.prompts.content_hash,
                    "schema": TEST_INTENT_SCHEMA_VERSION,
                    "compiler_version": TEST_INTENT_COMPILER_VERSION,
                    "retry": retry,
                    "http": response.http_status,
                    "finish": response.finish_reason,
                    "input": input_tokens,
                    "hit_tokens": actual_cost.input_cache_hit_tokens,
                    "miss_tokens": actual_cost.input_cache_miss_tokens,
                    "output": output_tokens,
                    "pricing_provider": actual_cost.pricing_provider,
                    "pricing_model": actual_cost.pricing_model,
                    "pricing_version": actual_cost.pricing_version,
                    "pricing_checked_at": actual_cost.pricing_checked_at,
                    "hit_rate": actual_cost.input_cache_hit_rate_usd_per_million,
                    "miss_rate": actual_cost.input_cache_miss_rate_usd_per_million,
                    "output_rate": actual_cost.output_rate_usd_per_million,
                    "estimated_cost": estimated_cost.estimated_cost_microusd,
                    "actual_cost": actual_cost.actual_cost_microusd,
                    "currency": actual_cost.currency,
                    "cost_version": actual_cost.cost_calculation_version,
                    "cost_assumption": actual_cost.calculation_assumption,
                    "max_tokens": response.max_tokens,
                    "latency": response.latency_ms,
                    "validation": validation_status,
                    "error": error_type,
                    "redacted": error_type,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO test_generation_response_artifacts("
                    "test_generation_llm_call_id,response_content,response_hash,parsed_json,"
                    "redaction_applied) VALUES (:call,:content,:hash,:parsed,:redacted)"
                ),
                {
                    "call": call_id,
                    "content": redacted,
                    "hash": hashlib.sha256(redacted.encode()).hexdigest(),
                    "parsed": self.database.encode_json(parsed_value)
                    if parsed_value is not None
                    else None,
                    "redacted": int(applied),
                },
            )
            if parsed_value is not None:
                insert_parsed_artifact(
                    connection,
                    self.database,
                    call_id=call_id,
                    parsed=parsed_value,
                    validation_status="parsed",
                    error_code=None,
                    origin=RUNTIME_ORIGIN,
                )
                self._audit_tx(
                    connection,
                    run_id,
                    batch_id,
                    "parsed_artifact_saved",
                    "passed",
                    {"call_id": call_id, "candidate_promotion": False},
                )
            else:
                self._audit_tx(
                    connection,
                    run_id,
                    batch_id,
                    "response_parse_failed",
                    "failed",
                    {"call_id": call_id, "failure_code": error_type},
                )
            connection.execute(
                text(
                    "UPDATE test_generation_runs SET estimated_cost_microusd="
                    "estimated_cost_microusd+:estimated,actual_cost_microusd="
                    "actual_cost_microusd+:actual,calculation_assumption=:assumption "
                    "WHERE test_generation_run_id=:run AND status='running'"
                ),
                {
                    "estimated": estimated_cost.estimated_cost_microusd,
                    "actual": actual_cost.actual_cost_microusd,
                    "assumption": actual_cost.calculation_assumption,
                    "run": run_id,
                },
            )
        return call_id

    def _persist_validation_outcome(
        self, call_id: str, validation_status: str, error_code: str | None
    ) -> None:
        parsed_row = self.database.fetch_one(
            "SELECT parsed_json FROM test_generation_parsed_artifacts "
            "WHERE test_generation_llm_call_id=:call AND artifact_origin=:origin",
            {"call": call_id, "origin": RUNTIME_ORIGIN},
        )
        if not parsed_row:
            raise TestGenerationError("PARSED_ARTIFACT_NOT_FOUND")
        with self.database.transaction() as connection:
            insert_parsed_artifact(
                connection,
                self.database,
                call_id=call_id,
                parsed=json.loads(str(parsed_row["parsed_json"])),
                validation_status=validation_status,
                error_code=error_code,
                origin=RUNTIME_VALIDATION_ORIGIN,
            )
            insert_validation_outcome(
                connection,
                call_id=call_id,
                validation_status=validation_status,
                error_code=error_code,
                validator_version=GENERATION_VALIDATOR_VERSION,
            )

    def _persist_failed_call(
        self,
        run_id: str,
        batch_id: str,
        retry: int,
        provider: LLMProvider,
        error: ProviderCallError,
    ) -> None:
        metadata = provider.metadata
        zero_cost = calculate_cost(
            provider_mode=metadata.provider_mode,
            input_tokens=0,
            output_tokens=0,
            pricing_provider=metadata.provider,
            pricing_model=metadata.model,
        )
        with self.database.transaction() as connection:
            connection.execute(
                text(
                    "INSERT INTO test_generation_llm_calls("
                    "test_generation_llm_call_id,test_generation_run_id,"
                    "test_generation_batch_id,provider,model,provider_mode,prompt_version,"
                    "prompt_hash,schema_version,retry_count,http_status,input_cache_hit_tokens,"
                    "input_cache_miss_tokens,pricing_provider,pricing_model,pricing_version,"
                    "pricing_checked_at,input_cache_hit_rate_usd_per_million,"
                    "input_cache_miss_rate_usd_per_million,output_rate_usd_per_million,"
                    "estimated_cost_microusd,actual_cost_microusd,currency,"
                    "cost_calculation_version,calculation_assumption,max_tokens,latency_ms,"
                    "validation_status,error_type,redacted_error) VALUES "
                    "(:id,:run,:batch,:provider,:model,:mode,:prompt,:prompt_hash,:schema,"
                    ":retry,:http,0,0,:pricing_provider,:pricing_model,:pricing_version,"
                    ":pricing_checked_at,:hit_rate,:miss_rate,:output_rate,0,0,:currency,"
                    ":cost_version,'request_failed_before_usage',:max_tokens,0,'invalid',"
                    ":error,:error)"
                ),
                {
                    "id": new_id("TGC"),
                    "run": run_id,
                    "batch": batch_id,
                    "provider": metadata.provider,
                    "model": metadata.model,
                    "mode": metadata.provider_mode,
                    "prompt": TEST_GENERATION_PROMPT_VERSION,
                    "prompt_hash": self.prompts.content_hash,
                    "schema": TEST_INTENT_SCHEMA_VERSION,
                    "compiler_version": TEST_INTENT_COMPILER_VERSION,
                    "retry": retry,
                    "http": error.http_status,
                    "pricing_provider": zero_cost.pricing_provider,
                    "pricing_model": zero_cost.pricing_model,
                    "pricing_version": zero_cost.pricing_version,
                    "pricing_checked_at": zero_cost.pricing_checked_at,
                    "hit_rate": zero_cost.input_cache_hit_rate_usd_per_million,
                    "miss_rate": zero_cost.input_cache_miss_rate_usd_per_million,
                    "output_rate": zero_cost.output_rate_usd_per_million,
                    "currency": zero_cost.currency,
                    "cost_version": zero_cost.cost_calculation_version,
                    "max_tokens": self.max_tokens_per_batch,
                    "error": error.error_type,
                },
            )

    def _fail_batch(self, batch_id: str, retry: int, error: str) -> None:
        self.database.execute(
            "UPDATE test_generation_batches SET status='failed',retry_count=:retry,"
            "validation_status='invalid',error_type=:error,redacted_error=:error,"
            "completed_at=CURRENT_TIMESTAMP WHERE test_generation_batch_id=:id",
            {"retry": retry, "error": error, "id": batch_id},
        )

    def _terminal(self, run_id: str, status: str, error: str, redacted: str) -> None:
        self.database.execute(
            "UPDATE test_generation_runs SET status=:status,validation_status='invalid',"
            "error_type=:error,redacted_error=:redacted,completed_at=CURRENT_TIMESTAMP "
            "WHERE test_generation_run_id=:id",
            {"status": status, "error": error, "redacted": redacted, "id": run_id},
        )

    def _audit(
        self,
        run_id: str,
        batch_id: str | None,
        event_type: str,
        status: str,
        details: dict[str, Any],
    ) -> None:
        with self.database.transaction() as connection:
            self._audit_tx(connection, run_id, batch_id, event_type, status, details)

    def _audit_tx(
        self,
        connection: Any,
        run_id: str,
        batch_id: str | None,
        event_type: str,
        status: str,
        details: dict[str, Any],
    ) -> None:
        connection.execute(
            text(
                "INSERT INTO test_case_generation_audit_events("
                "test_case_generation_audit_event_id,test_generation_run_id,"
                "test_generation_batch_id,event_type,event_status,details_json) "
                "VALUES (:id,:run,:batch,:type,:status,:details)"
            ),
            {
                "id": new_id("TGA"),
                "run": run_id,
                "batch": batch_id,
                "type": event_type,
                "status": status,
                "details": self.database.encode_json(details),
            },
        )

    def _validation_tx(
        self,
        connection: Any,
        run_id: str,
        candidate_id: str | None,
        scope: str,
        rule: str,
        status: str,
        details: dict[str, Any],
    ) -> None:
        connection.execute(
            text(
                "INSERT INTO test_case_validation_results("
                "test_case_validation_result_id,test_generation_run_id,test_case_candidate_id,"
                "scope,validator_version,rule_code,status,details_json) VALUES "
                "(:id,:run,:candidate,:scope,:version,:rule,:status,:details)"
            ),
            {
                "id": new_id("TVR"),
                "run": run_id,
                "candidate": candidate_id,
                "scope": scope,
                "version": GENERATION_VALIDATOR_VERSION,
                "rule": rule,
                "status": status,
                "details": self.database.encode_json(details),
            },
        )

    def _run_project_id(self, run_id: str) -> str:
        row = self.database.fetch_one(
            "SELECT project_id FROM test_generation_runs WHERE test_generation_run_id=:id",
            {"id": run_id},
        )
        if not row:
            raise TestGenerationError("GENERATION_RUN_NOT_FOUND")
        return str(row["project_id"])

    @staticmethod
    def _plan_batches(plan: dict[str, Any]) -> list[GenerationBatch]:
        return [
            GenerationBatch(
                batch_key=item["batch_key"],
                batch_index=item["batch_index"],
                case_type=item["case_type"],
                requirement_ids=tuple(item["requirement_ids"]),
                generation_slots=tuple(item["generation_slots"]),
                max_cases=item["max_cases"],
                max_tokens=item["max_tokens"],
                input_hash=item["input_hash"],
            )
            for item in plan["batches"]
        ]

    def _result_by_id(self, run_id: str) -> GenerationResult:
        row = self.database.fetch_one(
            "SELECT * FROM test_generation_runs WHERE test_generation_run_id=:id", {"id": run_id}
        )
        if not row:
            raise TestGenerationError("GENERATION_RUN_NOT_FOUND")
        return self._result(row)

    @staticmethod
    def _result(row: dict[str, Any]) -> GenerationResult:
        return GenerationResult(
            run_id=str(row["test_generation_run_id"]),
            status=str(row["status"]),
            provider_mode=str(row["provider_mode"]),
            candidate_count=int(row["candidate_count"]),
            collection_version=int(row["collection_version"])
            if row["collection_version"] is not None
            else None,
            collection_hash=str(row["collection_hash"])
            if row["collection_hash"] is not None
            else None,
        )


def _applicable_types(requirement: dict[str, Any]) -> tuple[str, ...]:
    text_value = json.dumps(requirement, ensure_ascii=False).lower()
    requirement_type = str(requirement.get("requirement_type", "functional"))
    types: list[str] = []
    if requirement_type in {"functional", "security", "privacy", "quality"}:
        types.append("api")
    ui_terms = (
        "registration",
        "login",
        "logout",
        "current-user",
        "username",
        "error",
        "cookie",
        "session",
        "accessib",
    )
    if any(term in text_value for term in ui_terms):
        types.append("ui")
    manual_terms = ("security", "privacy", "quality", "seeded defect", "migration", "logging")
    if any(term in text_value for term in manual_terms):
        types.append("manual")
    if not types:
        types.append("manual")
    return tuple(types)


def _hash_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _case_hash(case: dict[str, Any]) -> str:
    value = dict(case)
    value["content_hash"] = ""
    return _hash_json(value)


def _duplicate_signature(case: dict[str, Any]) -> str:
    details = case["type_details"]
    target = details.get("path") or details.get("route") or details.get("kind")
    method = details.get("method") or ""
    inputs = sorted(item["name"] for item in case["test_data"])
    expected = [" ".join(item.split()).casefold() for item in case["expected_results"]]
    return _hash_json(
        {
            "case_type": case["case_type"],
            "requirement_ids": sorted(case["requirement_ids"]),
            "target": target,
            "method": method,
            "inputs": inputs,
            "expected": expected,
        }
    )


def _scenario_signature(case: dict[str, Any]) -> str:
    details = case["type_details"]
    return _hash_json(
        {
            "case_type": case["case_type"],
            "requirement_ids": sorted(case["requirement_ids"]),
            "target": details.get("path") or details.get("route") or details.get("kind"),
            "method": details.get("method") or "",
            "inputs": sorted(item["name"] for item in case["test_data"]),
        }
    )


def _contains_secret(content: str) -> bool:
    patterns = (
        r"sk-[A-Za-z0-9_-]{20,}",
        r"(?i)authorization\s*[:=]\s*bearer\s+[A-Za-z0-9._-]+",
        r"(?i)deepseek_api_key\s*[:=]",
    )
    return any(re.search(pattern, content) for pattern in patterns)


def _redact_response(content: str) -> tuple[str, bool]:
    redacted, applied = redact_text(content)
    secret = os.getenv("DEEPSEEK_API_KEY", "")
    if secret and secret in redacted:
        redacted = redacted.replace(secret, "[REDACTED_SECRET]")
        applied = True
    return redacted, applied


def _safe_error(error: Exception) -> str:
    if isinstance(error, TruncationError):
        if str(error) in {"JSON_NOT_CLOSED", "MALFORMED_JSON"}:
            return "JSON_PARSE_ERROR"
        return "OUTPUT_TRUNCATED"
    if isinstance(error, IntentSchemaValidationError):
        return "INTENT_SCHEMA_VALIDATION"
    if isinstance(error, CandidateSchemaValidationError):
        return "CANDIDATE_SCHEMA_VALIDATION"
    if isinstance(error, CandidateCompilationError):
        return "COMPILATION_ERROR"
    if isinstance(error, JsonSchemaError):
        path = "/".join(str(part) for part in error.absolute_path) or "$"
        return f"SCHEMA_VALIDATION:{path}:{error.validator}"
    if isinstance(error, ProviderConfigurationError):
        return "PROVIDER_CONFIGURATION_ERROR"
    if isinstance(error, ProviderCallError):
        return "PROVIDER_REQUEST_ERROR"
    if isinstance(error, (TestGenerationError, TestIntentCompilationError, ProviderCallError)):
        return str(error)
    return type(error).__name__


def _caused_by_schema_error(error: Exception) -> JsonSchemaError | None:
    current: BaseException | None = error
    while current is not None:
        if isinstance(current, JsonSchemaError):
            return current
        current = current.__cause__
    return None


def _batch_key_for_case(case: dict[str, Any], batch_specs: dict[str, dict[str, Any]]) -> str:
    label = {"api": "API", "ui": "UI", "manual": "MAN"}[case["case_type"]]
    requirement_ids = set(case["requirement_ids"])
    matches = [
        key
        for key, spec in batch_specs.items()
        if key.startswith(f"TGB-{label}-") and requirement_ids <= set(spec["requirements"])
    ]
    if len(matches) != 1:
        raise TestGenerationError("CANDIDATE_BATCH_TRACE_AMBIGUOUS")
    return matches[0]
