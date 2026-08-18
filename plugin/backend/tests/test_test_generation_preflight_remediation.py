from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.providers import (
    ProviderConfigurationError,
    ProviderMetadata,
    ProviderResponse,
)
from plugin.backend.app.test_generation import TestGenerationService as GenerationService
from plugin.backend.app.test_generation_budget import (
    INPUT_CACHE_HIT_RATE,
    INPUT_CACHE_MISS_RATE,
    OUTPUT_RATE,
    calculate_cost,
    estimate_serialized_text,
)
from plugin.backend.app.test_generation_payloads import (
    project_generation_slot,
    project_requirement_snapshot,
)
from plugin.backend.app.test_generation_planning import (
    capacity_report_for_plan,
    make_generation_slot,
)
from plugin.backend.app.test_generation_prompts import (
    TEST_GENERATION_PROMPT_VERSION,
)
from plugin.backend.app.test_generation_prompts import (
    TestGenerationPromptRegistry as GenerationPromptRegistry,
)
from plugin.backend.app.test_generation_trace import (
    SeededRequirementResolutionError,
    resolve_seeded_username_requirement,
)
from plugin.backend.real_test_generation_acceptance import (
    AcceptanceLimits,
    BudgetGuardProvider,
    RealAcceptanceError,
    _reservation_summary,
    build_dry_run_report,
)
from plugin.backend.tests.test_test_generation import (
    PROJECT_ID,
    SEEDED_REQUIREMENT_ID,
    _seed_formal_requirements,
)


@pytest.fixture
def formal_database(tmp_path: Path) -> PluginDatabase:
    database_path = tmp_path / "preflight-remediation.db"
    database = PluginDatabase(f"sqlite:///{database_path.as_posix()}")
    database.migrate()
    _seed_formal_requirements(database)
    return database


def _snapshot(requirement_id: str, excerpt: str) -> dict[str, Any]:
    requirement = {
        "requirement_id": requirement_id,
        "title": "Username minimum",
        "description": excerpt,
        "requirement_type": "functional",
        "priority": "high",
        "risk_level": "high",
        "business_rules": [excerpt],
        "acceptance_criteria": [excerpt],
        "tags": ["username"],
        "testability": "deterministic",
        "source_block_id": "BLK-L0001-L0001-0000000001",
        "source_excerpt": excerpt,
    }
    return {
        "requirement_id": requirement_id,
        "requirement_version": 1,
        "snapshot_hash": hashlib.sha256(requirement_id.encode()).hexdigest(),
        "source_block_id": requirement["source_block_id"],
        "source_excerpt": excerpt,
        "requirement": requirement,
    }


def test_seeded_requirement_is_resolved_from_semantics_not_a_foreign_canonical_id() -> None:
    actual = _snapshot(
        SEEDED_REQUIREMENT_ID,
        "Registration username must have a minimum of six characters.",
    )
    result = resolve_seeded_username_requirement({SEEDED_REQUIREMENT_ID: actual})
    assert result.resolved_requirement_id == SEEDED_REQUIREMENT_ID
    assert result.resolved_requirement_id != "REQ-AUTH-USERNAME-001"
    assert result.field == "username"
    assert result.operator == "greater_than_or_equal"
    assert result.value == 6
    assert result.unit == "characters"
    assert result.requirement_snapshot_hash == actual["snapshot_hash"]
    assert result.source_block_id == actual["source_block_id"]


def test_seeded_requirement_resolution_rejects_zero_or_multiple_matches() -> None:
    with pytest.raises(SeededRequirementResolutionError, match="SEEDED_REQUIREMENT_NOT_FOUND"):
        resolve_seeded_username_requirement(
            {"REQ-OTHER": _snapshot("REQ-OTHER", "Username is optional.")}
        )
    with pytest.raises(SeededRequirementResolutionError, match="REQUIREMENT_IDENTITY_COLLISION"):
        resolve_seeded_username_requirement(
            {
                "REQ-BAT-002-6": _snapshot(
                    "REQ-BAT-002-6", "Registration username must have at least six characters."
                ),
                "REQ-BAT-002-006": _snapshot(
                    "REQ-BAT-002-006", "Registration username must have a minimum of 6 characters."
                ),
            }
        )


def test_compact_projection_preserves_formal_semantics_and_trace() -> None:
    snapshot = _snapshot(
        SEEDED_REQUIREMENT_ID,
        "Registration username must have a minimum of six characters.",
    )
    projected = project_requirement_snapshot(snapshot)
    strings = projected["s"]
    restored = {
        "requirement_id": projected["id"],
        "requirement_version": projected["v"],
        "snapshot_hash": projected["h"],
        "source_block_id": projected["b"],
        "source_excerpt": strings[projected["e"]],
        "title": strings[projected["t"]],
        "description": strings[projected["d"]],
        "requirement_type": projected["k"],
        "priority": projected["p"],
        "risk_level": projected["r"],
        "business_rules": [strings[index] for index in projected["u"]],
        "acceptance_criteria": [strings[index] for index in projected["a"]],
        "tags": projected["g"],
        "testability": projected["x"],
    }
    assert restored["requirement_id"] == SEEDED_REQUIREMENT_ID
    assert restored["requirement_version"] == 1
    assert restored["snapshot_hash"] == snapshot["snapshot_hash"]
    assert restored["source_block_id"] == snapshot["source_block_id"]
    for field in (
        "source_excerpt",
        "title",
        "description",
        "requirement_type",
        "priority",
        "risk_level",
        "business_rules",
        "acceptance_criteria",
        "tags",
        "testability",
    ):
        assert restored[field] == snapshot["requirement"][field]


def test_conservative_token_estimator_reports_all_measures_and_margin() -> None:
    estimate = estimate_serialized_text("a" * 12)
    assert estimate.character_count == 12
    assert estimate.utf8_byte_count == 12
    assert estimate.chars_per_4_tokens == 3
    assert estimate.chars_per_3_tokens == 4
    assert estimate.base_tokens == 4
    assert estimate.budget_tokens == 5
    unicode_estimate = estimate_serialized_text("用户")
    assert unicode_estimate.character_count == 2
    assert unicode_estimate.utf8_byte_count == 6
    assert unicode_estimate.base_tokens == 2
    assert unicode_estimate.budget_tokens == 3


def test_decimal_cost_model_covers_cache_hit_miss_output_and_fallback() -> None:
    assert INPUT_CACHE_HIT_RATE == Decimal("0.003625")
    assert INPUT_CACHE_MISS_RATE == Decimal("0.435")
    assert OUTPUT_RATE == Decimal("0.87")
    split = calculate_cost(
        provider_mode="real",
        input_tokens=2_000_000,
        input_cache_hit_tokens=1_000_000,
        input_cache_miss_tokens=1_000_000,
        output_tokens=1_000_000,
    )
    assert split.actual_cost_microusd == 1_308_625
    fallback = calculate_cost(provider_mode="real", input_tokens=1_000_000, output_tokens=0)
    assert fallback.actual_cost_microusd == 435_000
    assert "all_input_counted_as_cache_miss" in fallback.calculation_assumption
    mock = calculate_cost(provider_mode="mock", input_tokens=999, output_tokens=999)
    assert mock.actual_cost_microusd == 0
    assert mock.estimated_cost_microusd == 0


def test_capacity_plan_is_deterministic_bounded_and_keeps_all_applicability(
    formal_database: PluginDatabase,
) -> None:
    service = GenerationService(formal_database)
    first = service.preflight(PROJECT_ID)
    second = service.preflight(PROJECT_ID)
    snapshots = service._load_requirement_snapshots(PROJECT_ID)
    capacities = capacity_report_for_plan(first, snapshots, service.prompts)
    assert first == second
    assert len(first["batches"]) == 13
    assert all(
        item["input_estimate"]["budget_tokens"] <= item["input_budget_tokens"]
        for item in capacities
    )
    assert all(item["output_estimate"]["budget_tokens"] <= 3072 for item in capacities)
    planned = {
        (requirement_id, batch["case_type"])
        for batch in first["batches"]
        for requirement_id in batch["requirement_ids"]
    }
    declared = {
        (item["requirement_id"], case_type)
        for item in first["requirements"]
        for case_type in item["applicable_case_types"]
    }
    assert planned == declared


def test_prompt_registry_version_and_hash_match_final_messages() -> None:
    prompts = GenerationPromptRegistry()
    assert TEST_GENERATION_PROMPT_VERSION == "test-generation@3.0.0"
    assert len(prompts.content_hash) == 64
    messages = prompts.generation_messages(
        case_type="api",
        batch_id="TGB-API-001",
        generation_run_id="TGR-" + "0" * 32,
        provider_mode="real",
        generation_slots=[
            project_generation_slot(
                make_generation_slot(SEEDED_REQUIREMENT_ID, "api"),
                _snapshot(
                    SEEDED_REQUIREMENT_ID,
                    "Registration username must have a minimum of six characters.",
                ),
            )
        ],
        max_cases=1,
        api_contract="POST /api/auth/register",
        ui_contract="",
    )
    assert messages
    assert prompts.content_hash == GenerationPromptRegistry().content_hash


def test_dry_run_uses_final_plan_without_provider_or_database_write(
    formal_database: PluginDatabase,
) -> None:
    database_path = Path(formal_database.url.removeprefix("sqlite:///"))
    before = hashlib.sha256(database_path.read_bytes()).hexdigest()
    report = build_dry_run_report(
        formal_database,
        project_id=PROJECT_ID,
        limits=AcceptanceLimits(
            max_calls=18,
            max_retries=1,
            budget_microusd=65_000,
            max_output_tokens=3072,
        ),
        resume_run_id=None,
    )
    after = hashlib.sha256(database_path.read_bytes()).hexdigest()
    assert before == after
    assert report["provider_calls"] == 0
    assert report["database_writes"] == 0
    assert report["planned_call_count"] == 13
    assert report["max_retries"] == 1
    assert report["worst_cost_microusd"] <= 65_000
    assert report["prompt_version"] == TEST_GENERATION_PROMPT_VERSION


def test_dry_run_rejects_call_and_budget_limits_before_any_call(
    formal_database: PluginDatabase,
) -> None:
    with pytest.raises(RealAcceptanceError, match="DRY_RUN_CALL_LIMIT_INSUFFICIENT"):
        build_dry_run_report(
            formal_database,
            project_id=PROJECT_ID,
            limits=AcceptanceLimits(0, 1, 65_000, 3072),
            resume_run_id=None,
        )
    with pytest.raises(RealAcceptanceError, match="DRY_RUN_BUDGET_INSUFFICIENT"):
        build_dry_run_report(
            formal_database,
            project_id=PROJECT_ID,
            limits=AcceptanceLimits(17, 0, 1, 3072),
            resume_run_id=None,
        )


class _NoCallRealProvider:
    def __init__(self) -> None:
        self.call_count = 0

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata("deepseek", "deepseek-v4-pro", "real")

    def validate_config(self) -> None:
        return

    def analyze_outline(self, _prd_text: str) -> ProviderResponse:
        raise AssertionError("Phase 5A call forbidden")

    def extract_requirements_batch(self, **_kwargs: Any) -> ProviderResponse:
        raise AssertionError("Phase 5A call forbidden")

    def generate_test_cases(self, **_kwargs: Any) -> ProviderResponse:
        self.call_count += 1
        raise AssertionError("underlying provider must not be called")


def test_budget_guard_hard_stops_at_zero_calls_and_insufficient_budget() -> None:
    snapshot = _snapshot(
        SEEDED_REQUIREMENT_ID,
        "Registration username must have a minimum of six characters.",
    )
    provider = _NoCallRealProvider()
    guard = BudgetGuardProvider(
        provider,
        limits=AcceptanceLimits(0, 1, 65_000, 3072),
        prompts=GenerationPromptRegistry(),
    )
    with pytest.raises(ProviderConfigurationError, match="REAL_INITIAL_CALL_RESERVATION_EXCEEDED"):
        guard.generate_test_cases(
            case_type="api",
            batch_id="TGB-API-001",
            generation_run_id="TGR-" + "0" * 32,
            generation_slots=[
                {**make_generation_slot(SEEDED_REQUIREMENT_ID, "api"), "snapshot": snapshot}
            ],
            max_cases=1,
            max_tokens=3072,
        )
    assert provider.call_count == 0
    guard = BudgetGuardProvider(
        provider,
        limits=AcceptanceLimits(1, 0, 1, 4096),
        prompts=GenerationPromptRegistry(),
    )
    with pytest.raises(ProviderConfigurationError, match="REAL_INITIAL_COST_RESERVATION_EXCEEDED"):
        guard.generate_test_cases(
            case_type="api",
            batch_id="TGB-API-001",
            generation_run_id="TGR-" + "0" * 32,
            generation_slots=[
                {**make_generation_slot(SEEDED_REQUIREMENT_ID, "api"), "snapshot": snapshot}
            ],
            max_cases=1,
            max_tokens=4096,
        )
    assert provider.call_count == 0


def test_migration_persists_cost_contract_without_phase6_entities(
    formal_database: PluginDatabase,
) -> None:
    run_columns = {
        row["name"] for row in formal_database.fetch_all("PRAGMA table_info(test_generation_runs)")
    }
    call_columns = {
        row["name"]
        for row in formal_database.fetch_all("PRAGMA table_info(test_generation_llm_calls)")
    }
    for field in (
        "pricing_provider",
        "pricing_model",
        "pricing_version",
        "pricing_checked_at",
        "input_cache_hit_rate_usd_per_million",
        "input_cache_miss_rate_usd_per_million",
        "output_rate_usd_per_million",
        "estimated_cost_microusd",
        "actual_cost_microusd",
        "currency",
        "cost_calculation_version",
        "calculation_assumption",
    ):
        assert field in run_columns
    for field in (
        "input_cache_hit_tokens",
        "input_cache_miss_tokens",
        "output_tokens",
        "actual_cost_microusd",
        "estimated_cost_microusd",
    ):
        assert field in call_columns
    tables = {
        row["name"]
        for row in formal_database.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "test_case_reviews",
        "approved_test_case_versions",
        "frozen_baselines",
        "immutable_execution_snapshots",
    } <= tables


def test_mock_persistence_records_zero_cost_per_call_and_run(
    formal_database: PluginDatabase,
) -> None:
    from plugin.backend.app.providers import MockLLMProvider

    result = GenerationService(formal_database).start(PROJECT_ID, MockLLMProvider(), "cost-zero")
    assert result.status == "validated_pending_review"
    run = formal_database.fetch_one(
        "SELECT estimated_cost_microusd,actual_cost_microusd,currency "
        "FROM test_generation_runs WHERE test_generation_run_id=:run",
        {"run": result.run_id},
    )
    assert run == {
        "estimated_cost_microusd": 0,
        "actual_cost_microusd": 0,
        "currency": "USD",
    }
    calls = formal_database.fetch_all(
        "SELECT estimated_cost_microusd,actual_cost_microusd "
        "FROM test_generation_llm_calls WHERE test_generation_run_id=:run",
        {"run": result.run_id},
    )
    assert len(calls) == 13
    assert all(
        row["estimated_cost_microusd"] == 0 and row["actual_cost_microusd"] == 0 for row in calls
    )


class _SuccessfulOfflineRealProvider(_NoCallRealProvider):
    def generate_test_cases(self, **_kwargs: Any) -> ProviderResponse:
        self.call_count += 1
        return ProviderResponse(
            content='{"intents":[]}',
            finish_reason="stop",
            input_tokens=10,
            output_tokens=3000,
            latency_ms=1,
            http_status=200,
            provider_request_id="offline-reservation",
            max_tokens=3072,
        )


def test_runtime_reserves_all_remaining_initial_calls_before_correction() -> None:
    snapshot = _snapshot(
        SEEDED_REQUIREMENT_ID, "Registration username must have a minimum of six characters."
    )
    slot = {**make_generation_slot(SEEDED_REQUIREMENT_ID, "api"), "snapshot": snapshot}
    provider = _SuccessfulOfflineRealProvider()
    guard = BudgetGuardProvider(
        provider,
        limits=AcceptanceLimits(3, 1, 100_000, 3072),
        prompts=GenerationPromptRegistry(),
        reservation_costs={"TGB-API-001": 1_000, "TGB-API-002": 1_000, "TGB-API-003": 1_000},
    )
    guard.generate_test_cases(
        case_type="api",
        batch_id="TGB-API-001",
        generation_run_id="TGR-" + "0" * 32,
        generation_slots=[slot],
        max_cases=1,
        max_tokens=3072,
    )
    with pytest.raises(ProviderConfigurationError, match="REAL_INITIAL_CALL_RESERVATION_EXCEEDED"):
        guard.generate_test_cases(
            case_type="api",
            batch_id="TGB-API-001",
            generation_run_id="TGR-" + "0" * 32,
            generation_slots=[slot],
            max_cases=1,
            max_tokens=3072,
            recovery=True,
            validation_error="SCHEMA_VALIDATION",
        )
    assert provider.call_count == 1


def test_runtime_reserves_remaining_initial_cost_and_matches_dry_run_calculator() -> None:
    costs = {"TGB-API-001": 4_000, "TGB-API-002": 4_000, "TGB-API-003": 4_000}
    limits = AcceptanceLimits(4, 1, 12_000, 3072)
    summary = _reservation_summary(costs, limits)
    assert summary["initial_call_count"] == 3
    assert summary["initial_worst_cost_microusd"] == 12_000
    assert summary["correction_call_slots"] == 0
    snapshot = _snapshot(
        SEEDED_REQUIREMENT_ID,
        "Registration username must have a minimum of six characters.",
    )
    slot = {**make_generation_slot(SEEDED_REQUIREMENT_ID, "api"), "snapshot": snapshot}
    provider = _SuccessfulOfflineRealProvider()
    guard = BudgetGuardProvider(
        provider,
        limits=limits,
        prompts=GenerationPromptRegistry(),
        reservation_costs=costs,
    )
    guard.generate_test_cases(
        case_type="api",
        batch_id="TGB-API-001",
        generation_run_id="TGR-" + "0" * 32,
        generation_slots=[slot],
        max_cases=1,
        max_tokens=3072,
    )
    with pytest.raises(
        ProviderConfigurationError,
        match="REAL_INITIAL_COST_RESERVATION_EXCEEDED",
    ):
        guard.generate_test_cases(
            case_type="api",
            batch_id="TGB-API-001",
            generation_run_id="TGR-" + "0" * 32,
            generation_slots=[slot],
            max_cases=1,
            max_tokens=3072,
            recovery=True,
            validation_error="SCHEMA_VALIDATION",
        )
    assert provider.call_count == 1
