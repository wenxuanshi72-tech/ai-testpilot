from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

import pytest

from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.providers import (
    MockLLMProvider,
    ProviderCallError,
    ProviderResponse,
)
from plugin.backend.app.test_generation import TestGenerationService as GenerationService
from plugin.backend.app.test_generation_prompts import (
    TEST_GENERATION_PROMPT_ROOT,
)
from plugin.backend.app.test_generation_prompts import (
    TestGenerationPromptRegistry as GenerationPromptRegistry,
)
from plugin.backend.app.test_intent_compiler import TEST_INTENT_COMPILER_VERSION
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
