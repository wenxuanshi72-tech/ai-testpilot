from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.providers import (
    MockLLMProvider,
    ProviderCallError,
    ProviderMetadata,
    ProviderResponse,
)
from plugin.backend.app.test_generation import TestGenerationService as GenerationService
from plugin.backend.app.test_intent_compiler import TEST_INTENT_COMPILER_VERSION
from plugin.backend.real_test_generation_acceptance import (
    AcceptanceLimits,
    _parser,
    build_dry_run_report,
)
from plugin.backend.tests.test_test_generation import (
    PROJECT_ID,
    _seed_formal_requirements,
)


@pytest.fixture
def formal_database(tmp_path: Path) -> PluginDatabase:
    database_path = tmp_path / "real-offline.db"
    database = PluginDatabase(f"sqlite:///{database_path.as_posix()}")
    database.migrate()
    _seed_formal_requirements(database)
    return database


class RealLabeledOfflineProvider(MockLLMProvider):
    def __init__(self, stop_attempt: int | None = None) -> None:
        super().__init__(model="deepseek-v4-pro")
        self.stop_attempt = stop_attempt
        self.attempt_count = 0

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata("deepseek", "deepseek-v4-pro", "real")

    def generate_test_cases(self, **kwargs: Any) -> ProviderResponse:
        self.attempt_count += 1
        if self.stop_attempt == self.attempt_count:
            raise ProviderCallError("OFFLINE_INTERRUPTION", retryable=False)
        response = super().generate_test_cases(**kwargs)
        return ProviderResponse(
            content=response.content,
            finish_reason=response.finish_reason,
            input_tokens=1000,
            output_tokens=500,
            latency_ms=response.latency_ms,
            http_status=response.http_status,
            provider_request_id=f"offline-real-{self.attempt_count}",
            max_tokens=response.max_tokens,
            input_cache_hit_tokens=250,
            input_cache_miss_tokens=750,
        )


def test_real_entry_accepts_provider_network_recovery_reason() -> None:
    args = _parser().parse_args(
        [
            "--provider",
            "real",
            "--model",
            "deepseek-v4-pro",
            "--max-calls",
            "18",
            "--max-retries",
            "1",
            "--budget-usd",
            "0.065000",
            "--max-output-tokens",
            "3072",
            "--resume-run-id",
            "TGR-PARENT",
            "--recovery-reason",
            "PROVIDER_NETWORK_RECOVERY",
            "--thinking",
            "disabled",
            "--dry-run",
        ]
    )

    assert args.recovery_reason == "PROVIDER_NETWORK_RECOVERY"


def test_real_usage_cost_is_persisted_per_call_and_accumulated_per_run(
    formal_database: PluginDatabase,
) -> None:
    provider = RealLabeledOfflineProvider()
    result = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID, provider, "offline-real-cost"
    )
    assert result.status == "validated_pending_review"
    calls = formal_database.fetch_all(
        "SELECT input_cache_hit_tokens,input_cache_miss_tokens,output_tokens,"
        "actual_cost_microusd,calculation_assumption "
        "FROM test_generation_llm_calls WHERE test_generation_run_id=:run",
        {"run": result.run_id},
    )
    assert len(calls) == 13
    assert all(row["input_cache_hit_tokens"] == 250 for row in calls)
    assert all(row["input_cache_miss_tokens"] == 750 for row in calls)
    assert all(row["output_tokens"] == 500 for row in calls)
    assert all(row["actual_cost_microusd"] == 762 for row in calls)
    run = formal_database.fetch_one(
        "SELECT actual_cost_microusd FROM test_generation_runs WHERE test_generation_run_id=:run",
        {"run": result.run_id},
    )
    assert run == {"actual_cost_microusd": 9_906}


def test_resume_dry_run_counts_only_compatible_unfinished_real_batches(
    formal_database: PluginDatabase,
) -> None:
    provider = RealLabeledOfflineProvider(stop_attempt=4)
    parent = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID, provider, "offline-real-interrupted"
    )
    assert parent.status == "failed"
    report = build_dry_run_report(
        formal_database,
        project_id=PROJECT_ID,
        limits=AcceptanceLimits(13, 1, 65_000, 3072),
        resume_run_id=parent.run_id,
        recovery_reason="TEST_INTENT_COMPILER_REDESIGN",
    )
    assert report["total_batch_count"] == 13
    assert report["reusable_batch_count"] == 3
    assert report["planned_call_count"] == 10
    assert report["reusable_batch_keys"] == [
        "TGB-API-001",
        "TGB-API-002",
        "TGB-API-003",
    ]


def test_dry_run_does_not_count_different_compiler_checkpoint(
    formal_database: PluginDatabase,
) -> None:
    provider = RealLabeledOfflineProvider(stop_attempt=4)
    parent = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID, provider, "dry-run-compiler-parent"
    )
    assert parent.status == "failed"
    formal_database.execute(
        "UPDATE test_case_generation_audit_events "
        "SET details_json=REPLACE(details_json,:current,:old) "
        "WHERE test_generation_run_id=:run AND event_type='intent_batch_compiled'",
        {
            "current": TEST_INTENT_COMPILER_VERSION,
            "old": "deterministic-candidate-compiler@2.8.0",
            "run": parent.run_id,
        },
    )

    report = build_dry_run_report(
        formal_database,
        project_id=PROJECT_ID,
        limits=AcceptanceLimits(14, 1, 65_000, 3072),
        resume_run_id=parent.run_id,
        recovery_reason="TEST_INTENT_COMPILER_REDESIGN",
    )

    assert report["reusable_batch_count"] == 0
    assert report["planned_call_count"] == 13
