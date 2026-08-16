from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.providers import MockLLMProvider, ProviderResponse
from plugin.backend.app.test_generation import TestGenerationService
from plugin.backend.app.test_generation_audit import redact_parsed_json
from plugin.backend.app.test_generation_prompts import (
    TEST_GENERATION_PROMPT_VERSION,
    TestGenerationPromptRegistry,
)
from plugin.backend.app.test_generation_schemas import TEST_CASE_SCHEMA_VERSION
from plugin.backend.app.test_intent_compiler import TEST_INTENT_COMPILER_VERSION
from plugin.backend.app.test_intent_contract import (
    FORBIDDEN_MODEL_FIELDS,
    INTENT_FIELDS,
    TestIntentContractError,
    validate_test_intent_prompt_contract,
)
from plugin.backend.app.test_intent_mock import build_mock_intent_batch
from plugin.backend.app.test_intent_schemas import TEST_INTENT_SCHEMA_VERSION, TestIntentSchemas
from plugin.backend.tests.test_test_generation import PROJECT_ID, _seed_formal_requirements


class OneResponseProvider(MockLLMProvider):
    def __init__(self, payload: dict[str, Any] | str) -> None:
        content = payload if isinstance(payload, str) else json.dumps(payload)
        super().__init__(
            [
                ProviderResponse(
                    content=content,
                    finish_reason="stop",
                    input_tokens=10,
                    output_tokens=10,
                    latency_ms=1,
                    http_status=200,
                    provider_request_id="offline-slot-contract",
                    max_tokens=3072,
                )
            ]
        )


@pytest.fixture
def formal_database(tmp_path: Path) -> PluginDatabase:
    database = PluginDatabase(f"sqlite:///{(tmp_path / 'contract-audit.db').as_posix()}")
    database.migrate()
    _seed_formal_requirements(database)
    return database


def _batch_fixture(
    service: TestGenerationService, index: int = 0
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, Any]]:
    snapshots = service._load_requirement_snapshots(PROJECT_ID)
    plan = service._build_plan(snapshots)
    api = [item for item in plan["batches"] if item["case_type"] == "api"]
    batch = api[index]
    intents = build_mock_intent_batch(
        "api", batch["generation_slots"], snapshots, batch["max_cases"]
    )
    return batch, snapshots, {"intents": intents}


def _run_payload(database: PluginDatabase, payload: dict[str, Any], key: str) -> str:
    return (
        TestGenerationService(database, max_retries=0)
        .start(PROJECT_ID, OneResponseProvider(payload), key)
        .run_id
    )


def _error(database: PluginDatabase, run_id: str) -> str:
    row = database.fetch_one(
        "SELECT error_type FROM test_generation_runs WHERE test_generation_run_id=:run",
        {"run": run_id},
    )
    assert row is not None
    return str(row["error_type"])


def test_prompt_contract_and_examples_are_final_semantic_protocol() -> None:
    reports = validate_test_intent_prompt_contract(
        TestGenerationPromptRegistry(), TestIntentSchemas()
    )
    assert TEST_GENERATION_PROMPT_VERSION == "test-generation@3.0.0"
    assert TEST_INTENT_SCHEMA_VERSION == "test-intent@2.9.0"
    assert TEST_CASE_SCHEMA_VERSION == "test-cases@1.8.0"
    assert TEST_INTENT_COMPILER_VERSION == "deterministic-candidate-compiler@2.32.0"
    assert set(reports) == {"api", "ui", "manual"}
    assert all(set(item["example"]) == INTENT_FIELDS for item in reports.values())
    assert all(not set(item["example"]) & FORBIDDEN_MODEL_FIELDS for item in reports.values())


def test_intent_schema_required_field_drift_breaks_prompt_contract() -> None:
    schemas = TestIntentSchemas()
    schemas.schemas["test_intent.schema.json"]["required"].append("future_field")
    with pytest.raises(TestIntentContractError, match="INTENT_SCHEMA_FIELD_DRIFT"):
        validate_test_intent_prompt_contract(TestGenerationPromptRegistry(), schemas)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda intent: intent.pop("objective"),
        lambda intent: intent.pop("type_intent"),
        lambda intent: intent.update({"requirement_ids": ["REQ-FORBIDDEN"]}),
        lambda intent: intent.update({"intent_id": "INT-API-FORBIDDEN"}),
        lambda intent: intent.update({"case_type": "api"}),
        lambda intent: intent.update({"unexpected": True}),
    ],
)
def test_model_system_fields_missing_and_extra_fields_fail(
    formal_database: PluginDatabase, mutation: Callable[[dict[str, Any]], Any]
) -> None:
    service = TestGenerationService(formal_database, max_retries=0)
    _, _, payload = _batch_fixture(service)
    mutation(payload["intents"][0])
    run = _run_payload(
        formal_database,
        payload,
        "boundary-" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
    )
    assert _error(formal_database, run) == "INTENT_FIELD_BOUNDARY_INVALID"


def test_duplicate_generation_slot_fails(formal_database: PluginDatabase) -> None:
    service = TestGenerationService(formal_database, max_retries=0)
    _, _, payload = _batch_fixture(service)
    payload["intents"][1]["generation_slot_id"] = payload["intents"][0]["generation_slot_id"]
    run = _run_payload(formal_database, payload, "duplicate-slot")
    assert _error(formal_database, run) == "GENERATION_SLOT_DUPLICATE"


def test_missing_generation_slot_fails(formal_database: PluginDatabase) -> None:
    service = TestGenerationService(formal_database, max_retries=0)
    _, _, payload = _batch_fixture(service)
    payload["intents"].pop()
    run = _run_payload(formal_database, payload, "missing-slot")
    assert _error(formal_database, run) == "GENERATION_SLOT_MISSING"


def test_unknown_generation_slot_fails(formal_database: PluginDatabase) -> None:
    service = TestGenerationService(formal_database, max_retries=0)
    _, _, payload = _batch_fixture(service)
    payload["intents"][0]["generation_slot_id"] = "GSL-API-FFFFFFFFFFFFFFFF"
    run = _run_payload(formal_database, payload, "unknown-slot")
    assert _error(formal_database, run) == "GENERATION_SLOT_UNKNOWN_OR_CROSS_BATCH"


def test_cross_batch_generation_slot_fails(formal_database: PluginDatabase) -> None:
    service = TestGenerationService(formal_database, max_retries=0)
    _, _, payload = _batch_fixture(service)
    other, _, _ = _batch_fixture(service, 1)
    payload["intents"][0]["generation_slot_id"] = other["generation_slots"][0]["generation_slot_id"]
    run = _run_payload(formal_database, payload, "cross-slot")
    assert _error(formal_database, run) == "GENERATION_SLOT_UNKNOWN_OR_CROSS_BATCH"


def test_parsed_intent_artifact_survives_compiler_failure(formal_database: PluginDatabase) -> None:
    service = TestGenerationService(formal_database, max_retries=0)
    _, _, payload = _batch_fixture(service)
    payload["intents"][0]["cleanup_intent"] = {"required": False, "instructions": ["contradiction"]}
    run = _run_payload(formal_database, payload, "compiler-failure")
    assert _error(formal_database, run) == "COMPILATION_ERROR"
    assert formal_database.fetch_one("SELECT COUNT(*) AS count FROM test_case_candidates") == {
        "count": 0
    }


def test_invalid_json_has_no_parsed_artifact(formal_database: PluginDatabase) -> None:
    result = TestGenerationService(formal_database, max_retries=0).start(
        PROJECT_ID, OneResponseProvider('{"intents":'), "invalid-json"
    )
    assert result.status == "failed"
    assert _error(formal_database, result.run_id) == "JSON_PARSE_ERROR"
    assert formal_database.fetch_one(
        "SELECT COUNT(*) AS count FROM test_generation_parsed_artifacts"
    ) == {"count": 0}


def test_parsed_artifact_redacts_sensitive_values() -> None:
    clean, applied = redact_parsed_json(
        {
            "Authorization": "Bearer hidden-value",
            "Cookie": "session=hidden",
            "note": "access_token=hidden-value",
            "safe": "token validation is planned",
        }
    )
    serialized = json.dumps(clean)
    assert applied
    assert "hidden-value" not in serialized
    assert "session=hidden" not in serialized
    assert clean["safe"] == "token validation is planned"
