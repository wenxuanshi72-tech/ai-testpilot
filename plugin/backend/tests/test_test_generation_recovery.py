from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import text

from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.providers import (
    MockLLMProvider,
    ProviderCallError,
    ProviderMetadata,
    ProviderResponse,
)
from plugin.backend.app.test_generation import TestGenerationService as GenerationService
from plugin.backend.app.test_generation_audit import parsed_hash
from plugin.backend.app.test_generation_prompts import (
    TEST_GENERATION_PROMPT_ROOT,
)
from plugin.backend.app.test_generation_prompts import (
    TestGenerationPromptRegistry as GenerationPromptRegistry,
)
from plugin.backend.app.test_intent_compiler import TEST_INTENT_COMPILER_VERSION
from plugin.backend.real_test_generation_acceptance import AcceptanceLimits, build_dry_run_report
from plugin.backend.tests.test_test_generation import (
    PROJECT_ID,
    _seed_formal_requirements,
)


@pytest.fixture
def formal_database(tmp_path: Path) -> PluginDatabase:
    database_path = tmp_path / "recovery.db"
    database = PluginDatabase(f"sqlite:///{database_path.as_posix()}")
    database.migrate()
    _seed_formal_requirements(database)
    return database


class StopOnAttemptProvider(MockLLMProvider):
    def __init__(self, stop_attempt: int) -> None:
        super().__init__()
        self.stop_attempt = stop_attempt
        self.attempt_count = 0

    def generate_test_cases(self, **kwargs: Any) -> ProviderResponse:
        self.attempt_count += 1
        if self.attempt_count == self.stop_attempt:
            raise ProviderCallError("INTERRUPTED_OFFLINE_FIXTURE", retryable=False)
        return super().generate_test_cases(**kwargs)


class RealLabeledStopProvider(StopOnAttemptProvider):
    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata("deepseek", "deepseek-v4-pro", "real")


class RealLabeledMockProvider(MockLLMProvider):
    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata("deepseek", "deepseek-v4-pro", "real")


def _replace_checkpoint_parsed(
    database: PluginDatabase, run_id: str, batch_key: str, mutate: Any
) -> None:
    row = database.fetch_one(
        "SELECT c.test_generation_llm_call_id,a.parsed_json "
        "FROM test_generation_batches b JOIN test_generation_llm_calls c "
        "ON c.test_generation_batch_id=b.test_generation_batch_id "
        "JOIN test_generation_response_artifacts a "
        "ON a.test_generation_llm_call_id=c.test_generation_llm_call_id "
        "WHERE b.test_generation_run_id=:run AND b.batch_key=:key "
        "ORDER BY c.created_at DESC LIMIT 1",
        {"run": run_id, "key": batch_key},
    )
    assert row
    parsed = json.loads(row["parsed_json"])
    mutate(parsed)
    encoded = database.encode_json(parsed)
    with database.transaction() as connection:
        connection.exec_driver_sql("DROP TRIGGER IF EXISTS test_generation_responses_no_update")
        connection.exec_driver_sql(
            "DROP TRIGGER IF EXISTS test_generation_parsed_artifacts_no_update"
        )
        connection.execute(
            text(
                "UPDATE test_generation_response_artifacts SET parsed_json=:parsed "
                "WHERE test_generation_llm_call_id=:call"
            ),
            {"parsed": encoded, "call": row["test_generation_llm_call_id"]},
        )
        connection.execute(
            text(
                "UPDATE test_generation_parsed_artifacts SET parsed_json=:parsed,parsed_hash=:hash "
                "WHERE test_generation_llm_call_id=:call AND artifact_origin='runtime'"
            ),
            {
                "parsed": encoded,
                "hash": parsed_hash(parsed),
                "call": row["test_generation_llm_call_id"],
            },
        )


@pytest.mark.parametrize(
    ("batch_key", "mutate"),
    [
        (
            "TGB-API-001",
            lambda value: value["intents"][0]["type_intent"].update(
                {"setup_semantics": [{"method": "POST", "path": "/setup", "expected_status": 201}]}
            ),
        ),
        ("TGB-API-002", lambda value: value["intents"][0].update({"tags": ["CORS"]})),
        ("TGB-API-004", lambda value: value["intents"][0].update({"scenario_type": "defect"})),
        ("TGB-API-005", lambda value: value["intents"][0].update({"scenario_type": "error"})),
    ],
)
def test_legacy_checkpoint_is_rejected_and_falls_back_without_correction(
    formal_database: PluginDatabase, batch_key: str, mutate: Any
) -> None:
    parent_provider = RealLabeledStopProvider(stop_attempt=8)
    parent = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID, parent_provider, f"legacy-parent-{batch_key}"
    )
    _replace_checkpoint_parsed(formal_database, parent.run_id, batch_key, mutate)
    provider = RealLabeledMockProvider()
    child = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID,
        provider,
        f"legacy-child-{batch_key}",
        resume_run_id=parent.run_id,
        recovery_reason="TEST_INTENT_COMPILER_REDESIGN",
    )
    assert child.status == "validated_pending_review"
    assert provider.call_count == 7
    rejected = formal_database.fetch_one(
        "SELECT details_json FROM test_case_generation_audit_events "
        "WHERE test_generation_run_id=:run AND event_type='checkpoint_reuse_rejected' "
        "AND details_json LIKE :key",
        {"run": child.run_id, "key": f'%"batch_key":"{batch_key}"%'},
    )
    assert rejected
    details = json.loads(rejected["details_json"])
    assert details["fallback"] == "provider_generation"
    assert details["structure_correction_consumed"] is False


def test_dry_run_and_runtime_reject_all_legacy_checkpoints(
    formal_database: PluginDatabase,
) -> None:
    parent_provider = RealLabeledStopProvider(stop_attempt=7)
    parent = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID, parent_provider, "seven-legacy-parent"
    )
    for index in range(1, 7):
        _replace_checkpoint_parsed(
            formal_database,
            parent.run_id,
            f"TGB-API-{index:03d}",
            lambda value: value["intents"][0].update({"tags": ["CORS"]}),
        )
    report = build_dry_run_report(
        formal_database,
        project_id=PROJECT_ID,
        limits=AcceptanceLimits(40, 8, 250_000, 3072, 15),
        resume_run_id=parent.run_id,
        recovery_reason="PROVIDER_NETWORK_RECOVERY",
    )
    assert report["reusable_batch_count"] == 0
    assert report["planned_call_count"] == 13
    provider = RealLabeledMockProvider()
    child = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID,
        provider,
        "seven-legacy-child",
        resume_run_id=parent.run_id,
        recovery_reason="PROVIDER_NETWORK_RECOVERY",
    )
    assert child.status == "validated_pending_review"
    assert provider.call_count == 13
    rejected = formal_database.fetch_one(
        "SELECT COUNT(*) AS count FROM test_case_generation_audit_events "
        "WHERE test_generation_run_id=:run AND event_type='checkpoint_reuse_rejected'",
        {"run": child.run_id},
    )
    assert rejected == {"count": 13}


def test_checkpoint_schema_system_error_terminates_recovery(
    formal_database: PluginDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent_provider = RealLabeledStopProvider(stop_attempt=2)
    parent = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID, parent_provider, "schema-system-parent"
    )
    provider = RealLabeledMockProvider()
    service = GenerationService(formal_database, max_retries=0)

    def fail_schema_load(_name: str, _instance: Any) -> None:
        raise RuntimeError("OFFLINE_SCHEMA_SYSTEM_ERROR")

    monkeypatch.setattr(service.intent_schemas, "validate", fail_schema_load)
    child = service.start(
        PROJECT_ID,
        provider,
        "schema-system-child",
        resume_run_id=parent.run_id,
        recovery_reason="PROVIDER_NETWORK_RECOVERY",
    )
    assert child.status == "failed"
    assert provider.call_count == 0


def test_failed_run_can_resume_only_compatible_successful_batches(
    formal_database: PluginDatabase,
) -> None:
    interrupted = StopOnAttemptProvider(stop_attempt=4)
    parent = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID, interrupted, "recovery-parent"
    )
    assert parent.status == "failed"
    assert interrupted.attempt_count == 4
    assert interrupted.call_count == 3
    parent_before = formal_database.fetch_one(
        "SELECT * FROM test_generation_runs WHERE test_generation_run_id=:run",
        {"run": parent.run_id},
    )

    resumed_provider = MockLLMProvider()
    child = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID,
        resumed_provider,
        "recovery-child",
        resume_run_id=parent.run_id,
        recovery_reason="TEST_INTENT_COMPILER_REDESIGN",
    )
    assert child.status == "validated_pending_review"
    assert resumed_provider.call_count == 10
    reused = formal_database.fetch_all(
        "SELECT details_json FROM test_case_generation_audit_events "
        "WHERE test_generation_run_id=:run AND event_type='validated_batch_reused'",
        {"run": child.run_id},
    )
    assert len(reused) == 3
    parent_after = formal_database.fetch_one(
        "SELECT * FROM test_generation_runs WHERE test_generation_run_id=:run",
        {"run": parent.run_id},
    )
    assert parent_after == parent_before


def test_provider_network_recovery_reason_is_allowed(
    formal_database: PluginDatabase,
) -> None:
    interrupted = StopOnAttemptProvider(stop_attempt=1)
    parent = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID, interrupted, "network-recovery-parent"
    )
    assert parent.status == "failed"

    child = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID,
        MockLLMProvider(),
        "network-recovery-child",
        resume_run_id=parent.run_id,
        recovery_reason="PROVIDER_NETWORK_RECOVERY",
    )

    assert child.status == "validated_pending_review"
    persisted = formal_database.fetch_one(
        "SELECT resume_source_run_id,recovery_reason "
        "FROM test_generation_runs WHERE test_generation_run_id=:run",
        {"run": child.run_id},
    )
    assert persisted == {
        "resume_source_run_id": parent.run_id,
        "recovery_reason": "PROVIDER_NETWORK_RECOVERY",
    }


def test_changed_prompt_hash_forces_regeneration_instead_of_checkpoint_reuse(
    formal_database: PluginDatabase,
    tmp_path: Path,
) -> None:
    interrupted = StopOnAttemptProvider(stop_attempt=3)
    parent = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID, interrupted, "hash-parent"
    )
    assert parent.status == "failed"
    assert interrupted.call_count == 2

    alternate_root = tmp_path / "alternate-prompts"
    shutil.copytree(TEST_GENERATION_PROMPT_ROOT, alternate_root)
    prompt = alternate_root / "api_cases_system.md"
    prompt.write_text(
        prompt.read_text(encoding="utf-8") + "\nCompatibility test marker.\n",
        encoding="utf-8",
    )
    alternate = GenerationPromptRegistry(alternate_root)
    provider = MockLLMProvider()
    child = GenerationService(
        formal_database,
        prompts=alternate,
        max_retries=0,
    ).start(
        PROJECT_ID,
        provider,
        "hash-child",
        resume_run_id=parent.run_id,
        recovery_reason="TEST_INTENT_COMPILER_REDESIGN",
    )
    assert child.status == "validated_pending_review"
    assert provider.call_count == 13
    reused = formal_database.fetch_one(
        "SELECT COUNT(*) AS count FROM test_case_generation_audit_events "
        "WHERE test_generation_run_id=:run AND event_type='validated_batch_reused'",
        {"run": child.run_id},
    )
    assert reused == {"count": 0}


def test_checkpoint_from_different_compiler_version_is_not_reused(
    formal_database: PluginDatabase,
) -> None:
    interrupted = StopOnAttemptProvider(stop_attempt=3)
    parent = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID, interrupted, "compiler-version-parent"
    )
    assert parent.status == "failed"
    assert interrupted.call_count == 2
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

    provider = MockLLMProvider()
    child = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID,
        provider,
        "compiler-version-child",
        resume_run_id=parent.run_id,
        recovery_reason="TEST_INTENT_COMPILER_REDESIGN",
    )

    assert child.status == "validated_pending_review"
    assert provider.call_count == 13
    reused = formal_database.fetch_one(
        "SELECT COUNT(*) AS count FROM test_case_generation_audit_events "
        "WHERE test_generation_run_id=:run AND event_type='validated_batch_reused'",
        {"run": child.run_id},
    )
    assert reused == {"count": 0}
