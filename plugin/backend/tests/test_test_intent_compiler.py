from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import pytest
from jsonschema import ValidationError

from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.providers import MockLLMProvider, ProviderMetadata, ProviderResponse
from plugin.backend.app.test_generation import TestGenerationService
from plugin.backend.app.test_generation_prompts import TestGenerationPromptRegistry
from plugin.backend.app.test_generation_schemas import TestCaseSchemas
from plugin.backend.app.test_intent_compiler import (
    CompilationContext,
    DeterministicCandidateCompiler,
    TestIntentCompilationError,
    compatibility_audit_records,
    normalize_intent_batch,
    structured_setup_to_api,
)
from plugin.backend.app.test_intent_contract import validate_test_intent_prompt_contract
from plugin.backend.app.test_intent_schemas import TestIntentSchemas
from plugin.backend.tests.test_test_generation import PROJECT_ID, _seed_formal_requirements

REQ_ID = "REQ-EXAMPLE-001"


def _example(case_type: str) -> dict[str, Any]:
    reports = validate_test_intent_prompt_contract(
        TestGenerationPromptRegistry(), TestIntentSchemas()
    )
    return deepcopy(reports[case_type]["example"])


def _context(case_type: str, intent: dict[str, Any]) -> CompilationContext:
    label = {"api": "API", "ui": "UI", "manual": "MAN"}[case_type]
    slot = {
        "generation_slot_id": intent["generation_slot_id"],
        "primary_requirement_id": REQ_ID,
        "requirement_ids": [REQ_ID],
        "case_type": case_type,
        "case_id": f"TC-{label}-EXAMPLE-001",
    }
    snapshot = {
        "requirement_id": REQ_ID,
        "requirement_version": 1,
        "snapshot_hash": "2" * 64,
        "source_block_id": "BLK-L0001-L0001-0000000001",
        "prd_document_id": "PRD-" + ("3" * 32),
        "prd_version_id": "PRDV-" + ("4" * 32),
    }
    return CompilationContext(
        run_id="TGR-" + ("1" * 32),
        project_id=PROJECT_ID,
        provider=ProviderMetadata("deepseek", "deepseek-v4-pro", "real"),
        snapshots={REQ_ID: snapshot},
        slots={intent["generation_slot_id"]: slot},
    )


def test_compiler_preserves_semantics_and_injects_only_system_metadata() -> None:
    intent = _example("api")
    candidate = DeterministicCandidateCompiler().compile(intent, _context("api", intent))
    assert candidate["objective"] == intent["objective"]
    assert candidate["expected_results"] == intent["expected_outcomes"]
    assert candidate["requirement_ids"] == [REQ_ID]
    assert candidate["primary_requirement_id"] == REQ_ID
    assert [item["name"] for item in candidate["test_data"]] == ["data_001", "data_002"]
    assert candidate["trace"]["generation_prompt_version"] == "test-generation@3.0.0"
    assert candidate["schema_version"] == "test-cases@1.8.0"
    assert candidate["review_status"] == "draft"
    assert candidate["lifecycle_status"] == "validated_pending_review"
    second = DeterministicCandidateCompiler().compile(intent, _context("api", intent))
    assert second["semantic_content_hash"] == candidate["semantic_content_hash"]


def test_compatibility_accepts_authorization_and_nullable_test_data_with_audit() -> None:
    intent = _example("api")
    intent["scenario_type"] = "authorization"
    intent["test_data"][0]["value"] = None
    TestIntentSchemas().validate("api_intent_batch.schema.json", {"intents": [intent]})

    candidate = DeterministicCandidateCompiler().compile(intent, _context("api", intent))

    assert candidate["test_category"] == "security"
    assert candidate["test_data"][0]["value"] is None
    assert compatibility_audit_records([intent]) == [
        {
            "generation_slot_id": intent["generation_slot_id"],
            "field": "scenario_type",
            "original": "authorization",
            "accepted_as": "security",
            "rule": "authorization_to_security",
            "compatibility_version": "test-intent-compatibility@1.29.0",
        },
        {
            "generation_slot_id": intent["generation_slot_id"],
            "field": "test_data/0/value",
            "original_type": "null",
            "accepted_type": "null",
            "rule": "nullable_test_data_value",
            "compatibility_version": "test-intent-compatibility@1.29.0",
        },
    ]


def test_functional_scenario_is_preserved_as_candidate_category() -> None:
    intent = _example("api")
    intent["scenario_type"] = "functional"
    TestIntentSchemas().validate("api_intent_batch.schema.json", {"intents": [intent]})

    candidate = DeterministicCandidateCompiler().compile(intent, _context("api", intent))

    assert candidate["test_category"] == "functional"
    assert compatibility_audit_records([intent]) == [
        {
            "generation_slot_id": intent["generation_slot_id"],
            "field": "scenario_type",
            "original": "functional",
            "accepted_as": "functional",
            "rule": "functional_category_passthrough",
            "compatibility_version": "test-intent-compatibility@1.29.0",
        }
    ]


def test_compiler_rejects_unknown_slot_without_guessing() -> None:
    intent = _example("api")
    context = _context("api", intent)
    intent["generation_slot_id"] = "GSL-API-FFFFFFFFFFFFFFFF"
    with pytest.raises(TestIntentCompilationError, match="GENERATION_SLOT_UNKNOWN_OR_CROSS_BATCH"):
        DeterministicCandidateCompiler().compile(intent, context)


def test_session_semantics_aliases_compile_to_anonymous_with_audit() -> None:
    for alias in ("no_session", "none_or_invalid"):
        intent = _example("api")
        intent["type_intent"]["session_semantics"] = alias

        normalized = normalize_intent_batch({"intents": [intent]})
        accepted = normalized["intents"][0]
        TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
        candidate = DeterministicCandidateCompiler().compile(accepted, _context("api", accepted))

        assert candidate["type_details"]["session_handling"] == "none"
        assert compatibility_audit_records([intent]) == [
            {
                "generation_slot_id": intent["generation_slot_id"],
                "field": "type_intent/session_semantics",
                "original": alias,
                "accepted_as": "anonymous",
                "rule": "descriptive_session_to_canonical",
                "compatibility_version": "test-intent-compatibility@1.29.0",
            }
        ]


def test_structural_compatibility_normalizes_real_response_shape_with_audit() -> None:
    raw = _example("api")
    raw["test_data"][0]["value"] = ""
    del raw["type_intent"]["request_body"]
    raw["type_intent"]["session_semantics"] = "existing_expired"
    raw["type_intent"]["setup_semantics"] = [
        {
            "method": "POST",
            "path": "/api/auth/logout",
            "expected_status": 204,
            "description": "Expire the current session",
        }
    ]

    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    candidate = DeterministicCandidateCompiler().compile(accepted, _context("api", accepted))

    assert accepted["type_intent"]["request_body"] is None
    assert accepted["type_intent"]["session_semantics"] == "expired"
    assert accepted["type_intent"]["setup_semantics"][0]["request_body"] is None
    assert candidate["test_data"][0]["value"] == ""
    assert candidate["type_details"]["session_handling"] == "expired_session"
    assert candidate["type_details"]["setup_requests"][0] == {
        "method": "POST",
        "path": "/api/auth/logout",
        "request_body": None,
        "expected_status": 204,
        "description": "Expire the current session",
    }
    records = compatibility_audit_records([raw])
    assert {record["rule"] for record in records} == {
        "missing_request_body_to_null",
        "nullable_test_data_value",
        "descriptive_session_to_canonical",
        "structured_setup_request",
    }
    assert raw["type_intent"].get("request_body") is None
    assert "request_body" not in raw["type_intent"]


def test_non_http_na_setup_becomes_instruction_and_preserves_semantics() -> None:
    raw = _example("api")
    raw["type_intent"]["setup_semantics"] = [
        {
            "method": "N/A",
            "path": "N/A",
            "expected_status": 0,
            "session_semantics": "expired",
            "response_expectations": ["Expire the session server-side."],
            "security_expectations": [],
            "state_expectations": ["Session is expired."],
        }
    ]
    normalized = normalize_intent_batch({"intents": [raw]})
    setup = normalized["intents"][0]["type_intent"]["setup_semantics"][0]
    assert isinstance(setup, str)
    assert "Expire the session server-side" in setup
    assert "Session is expired" in setup
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    assert any(
        item["rule"] == "non_http_setup_to_instruction"
        for item in compatibility_audit_records([raw])
    )


def test_real_http_setup_with_na_path_remains_invalid() -> None:
    assert (
        structured_setup_to_api(
            {"method": "POST", "path": "N/A", "expected_status": 201, "description": "x"}
        )
        is None
    )
    raw = _example("api")
    raw["type_intent"]["setup_semantics"] = [
        {"method": "POST", "path": "N/A", "expected_status": 201, "description": "x"}
    ]
    normalized = normalize_intent_batch({"intents": [raw]})
    with pytest.raises(ValidationError):
        TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)


def test_unmapped_setup_extension_is_not_silently_dropped() -> None:
    raw = _example("api")
    raw["type_intent"]["setup_semantics"] = [
        {
            "method": "POST",
            "path": "/api/auth/login",
            "expected_status": 200,
            "description": "Login",
            "outcome_capture": {"variable_name": "session"},
        }
    ]
    normalized = normalize_intent_batch({"intents": [raw]})
    with pytest.raises(ValidationError):
        TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)


def test_descriptive_session_and_action_setup_are_deterministically_normalized() -> None:
    cases = [
        ("none, expired, or revoked", 401, "expired"),
        ("use_expired_or_revoked", 401, "expired"),
        ("control", 200, "authenticated"),
        ("control", 401, "anonymous"),
    ]
    for raw_value, status, expected in cases:
        raw = _example("api")
        raw["type_intent"]["session_semantics"] = raw_value
        raw["type_intent"]["expected_status"] = status
        raw["type_intent"]["setup_semantics"] = [
            {"action": "submit", "instruction": "Log in before the sub-test."}
        ]

        normalized = normalize_intent_batch({"intents": [raw]})

        assert normalized["intents"][0]["type_intent"]["session_semantics"] == expected
        assert normalized["intents"][0]["type_intent"]["setup_semantics"] == [
            "Log in before the sub-test."
        ]
        records = compatibility_audit_records([raw])
        assert any(
            record["rule"] == "descriptive_session_to_canonical"
            and record["accepted_as"] == expected
            for record in records
        )
        assert any(record["rule"] == "action_instruction_setup_to_text" for record in records)
        assert raw["type_intent"]["session_semantics"] == raw_value
        assert isinstance(raw["type_intent"]["setup_semantics"][0], dict)


def test_compiler_rejects_unmappable_session_without_guessing() -> None:
    intent = _example("api")
    intent["type_intent"]["session_semantics"] = "invented_session"
    with pytest.raises(TestIntentCompilationError, match="SESSION_INTENT_UNMAPPABLE"):
        DeterministicCandidateCompiler().compile(intent, _context("api", intent))


class _OneCorrectionProvider(MockLLMProvider):
    def __init__(self) -> None:
        super().__init__()
        self.validation_errors: list[str | None] = []

    def generate_test_cases(self, **kwargs: Any) -> ProviderResponse:
        self.validation_errors.append(kwargs.get("validation_error"))
        response = super().generate_test_cases(**kwargs)
        if self.call_count != 1:
            return response
        payload = json.loads(response.content)
        payload["intents"][0]["objective"] = ""
        return ProviderResponse(
            content=json.dumps(payload),
            finish_reason=response.finish_reason,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=response.latency_ms,
            http_status=response.http_status,
            provider_request_id=response.provider_request_id,
            max_tokens=response.max_tokens,
        )


def test_one_schema_failure_gets_exactly_one_same_batch_correction(tmp_path: Any) -> None:
    database = PluginDatabase(f"sqlite:///{(tmp_path / 'correction.db').as_posix()}")
    database.migrate()
    _seed_formal_requirements(database)
    provider = _OneCorrectionProvider()
    result = TestGenerationService(database, max_retries=1).start(
        PROJECT_ID, provider, "one-correction"
    )
    assert result.status == "validated_pending_review"
    batch_row = database.fetch_one("SELECT COUNT(*) AS count FROM test_generation_batches")
    assert batch_row is not None
    batch_count = batch_row["count"]
    assert provider.call_count == batch_count + 1
    assert provider.validation_errors[:2] == [
        None,
        "INTENT_SCHEMA_VALIDATION",
    ]
    corrected = database.fetch_all(
        "SELECT batch_key,retry_count FROM test_generation_batches WHERE retry_count=1"
    )
    assert corrected == [{"batch_key": "TGB-API-001", "retry_count": 1}]


def test_missing_cleanup_is_normalized_to_audited_no_cleanup() -> None:
    raw = _example("api")
    del raw["cleanup_intent"]

    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]

    assert "cleanup_intent" not in raw
    assert accepted["cleanup_intent"] == {
        "required": False,
        "instructions": [],
    }
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    assert compatibility_audit_records([raw]) == [
        {
            "generation_slot_id": raw["generation_slot_id"],
            "field": "cleanup_intent",
            "original_type": "missing",
            "accepted_type": "no_cleanup",
            "rule": "missing_cleanup_to_no_cleanup",
            "compatibility_version": "test-intent-compatibility@1.29.0",
        }
    ]


def test_quality_scenario_is_normalized_to_audited_functional() -> None:
    raw = _example("api")
    raw["scenario_type"] = "quality"

    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]

    assert raw["scenario_type"] == "quality"
    assert accepted["scenario_type"] == "functional"
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    assert compatibility_audit_records([raw]) == [
        {
            "generation_slot_id": raw["generation_slot_id"],
            "field": "scenario_type",
            "original": "quality",
            "accepted_as": "functional",
            "rule": "model_functional_alias_to_functional",
            "compatibility_version": "test-intent-compatibility@1.29.0",
        }
    ]


def test_action_purpose_setup_is_normalized_to_audited_api_request() -> None:
    raw = _example("api")
    raw["type_intent"]["setup_semantics"] = [
        {
            "action": "POST /api/auth/register",
            "purpose": "Create test user",
            "expected_status": 201,
        }
    ]

    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]

    assert raw["type_intent"]["setup_semantics"][0]["action"] == "POST /api/auth/register"
    assert accepted["type_intent"]["setup_semantics"] == [
        {
            "method": "POST",
            "path": "/api/auth/register",
            "request_body": None,
            "expected_status": 201,
            "description": "Create test user",
        }
    ]
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    records = compatibility_audit_records([raw])
    assert any(record["rule"] == "action_purpose_setup_to_api" for record in records)


@pytest.mark.parametrize("alias", ["verification", "non_functional"])
def test_model_functional_aliases_are_audited(alias: str) -> None:
    raw = _example("api")
    raw["scenario_type"] = alias

    normalized = normalize_intent_batch({"intents": [raw]})

    assert raw["scenario_type"] == alias
    assert normalized["intents"][0]["scenario_type"] == "functional"
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    assert compatibility_audit_records([raw]) == [
        {
            "generation_slot_id": raw["generation_slot_id"],
            "field": "scenario_type",
            "original": alias,
            "accepted_as": "functional",
            "rule": "model_functional_alias_to_functional",
            "compatibility_version": "test-intent-compatibility@1.29.0",
        }
    ]


def test_error_handling_and_structured_setup_are_projected_deterministically() -> None:
    raw = _example("api")
    raw["scenario_type"] = "error_handling"
    raw["type_intent"]["setup_semantics"] = [
        {
            "method": "POST",
            "path": "/api/auth/login",
            "request_body": {"username": "${data_001}"},
            "session_semantics": "create_new",
            "expected_status": 200,
            "response_expectations": ["Login succeeds"],
        }
    ]
    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    assert raw["scenario_type"] == "error_handling"
    assert accepted["scenario_type"] == "negative"
    assert accepted["type_intent"]["setup_semantics"] == [
        {
            "method": "POST",
            "path": "/api/auth/login",
            "request_body": {"username": "${data_001}"},
            "expected_status": 200,
            "description": (
                "POST /api/auth/login; session=create_new; response_expectations=Login succeeds"
            ),
        }
    ]
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    records = compatibility_audit_records([raw])
    assert any(record["rule"] == "model_error_alias_to_negative" for record in records)
    assert any(record["rule"] == "structured_setup_request" for record in records)


def test_tag_case_and_incomplete_setup_are_normalized_without_inventing_status() -> None:
    raw = _example("api")
    raw["tags"] = ["api", "CORS"]
    raw["type_intent"]["setup_semantics"] = [
        {"method": "POST", "path": "/api/auth/register", "when": "no user exists"}
    ]
    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    assert raw["tags"] == ["api", "CORS"]
    assert accepted["tags"] == ["api", "cors"]
    assert accepted["type_intent"]["setup_semantics"] == [
        "POST /api/auth/register when no user exists"
    ]
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    records = compatibility_audit_records([raw])
    assert any(record["rule"] == "tag_to_canonical_slug" for record in records)
    assert any(record["rule"] == "incomplete_setup_to_instruction" for record in records)


def test_request_header_alias_is_preserved_in_compiled_candidate_with_audit() -> None:
    raw = _example("api")
    raw["type_intent"]["headers"] = {"Origin": "https://example.test"}
    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    assert "headers" in raw["type_intent"]
    assert "headers" not in accepted["type_intent"]
    assert accepted["type_intent"]["request_headers"] == {"Origin": "https://example.test"}
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    candidate = DeterministicCandidateCompiler().compile(accepted, _context("api", accepted))
    assert candidate["type_details"]["headers"] == {"Origin": "https://example.test"}
    records = compatibility_audit_records([raw])
    assert any(record["rule"] == "headers_alias_to_request_headers" for record in records)


def test_named_setup_mapping_and_seeded_defect_are_normalized_with_audit() -> None:
    raw = _example("api")
    raw["scenario_type"] = "seeded defect"
    raw["type_intent"]["setup_semantics"] = {
        "prerequisite": {
            "method": "POST",
            "path": "/api/auth/register",
            "request_body": {"username": "seeded"},
            "expected_status": 201,
        },
        "allowed_origin": "http://localhost:3000",
    }
    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    assert raw["scenario_type"] == "seeded defect"
    assert accepted["scenario_type"] == "negative"
    assert accepted["type_intent"]["setup_semantics"][0]["method"] == "POST"
    assert accepted["type_intent"]["setup_semantics"][1] == (
        'allowed_origin: "http://localhost:3000"'
    )
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    records = compatibility_audit_records([raw])
    assert any(record["rule"] == "model_error_alias_to_negative" for record in records)
    assert any(record["rule"] == "named_setup_mapping_to_list" for record in records)


def test_privacy_and_bodyless_complex_method_are_narrowly_normalized() -> None:
    raw = _example("api")
    raw["scenario_type"] = "privacy"
    raw["type_intent"]["method"] = "complex"
    raw["type_intent"]["request_body"] = None
    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    assert raw["scenario_type"] == "privacy"
    assert raw["type_intent"]["method"] == "complex"
    assert accepted["scenario_type"] == "security"
    assert accepted["type_intent"]["method"] == "GET"
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    records = compatibility_audit_records([raw])
    assert any(record["rule"] == "privacy_alias_to_security" for record in records)
    assert any(record["rule"] == "bodyless_complex_method_to_get" for record in records)


def test_defect_verification_and_additional_requests_are_normalized() -> None:
    raw = _example("api")
    raw["scenario_type"] = "defect_verification"
    raw["type_intent"]["additional_requests"] = [
        {
            "method": "POST",
            "path": "/api/auth/register",
            "request_body": {"username": "second"},
            "expected_status": 400,
            "response_expectations": ["Rejected"],
        }
    ]
    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    assert accepted["scenario_type"] == "negative"
    assert "additional_requests" not in accepted["type_intent"]
    assert accepted["type_intent"]["setup_semantics"][0]["method"] == "POST"
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    records = compatibility_audit_records([raw])
    assert any(record["rule"] == "model_error_alias_to_negative" for record in records)
    assert any(record["rule"] == "additional_requests_to_setup_semantics" for record in records)


def test_unknown_scenario_and_semantic_extensions_are_audited_and_compiled() -> None:
    raw = _example("api")
    raw["scenario_type"] = "validation"
    raw["negative_type_intent"] = {"method": "POST", "expected_status": 400}
    raw["time_based_intents"] = ["after eight hours"]
    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    assert accepted["scenario_type"] == "functional"
    assert "negative_type_intent" not in accepted
    assert "time_based_intents" not in accepted
    assert len(accepted["actions"]) == len(raw["actions"]) + 2
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    records = compatibility_audit_records([raw])
    assert any(record["rule"] == "unknown_scenario_to_functional" for record in records)
    assert sum(record["rule"] == "semantic_extension_to_actions" for record in records) == 2


def test_unknown_data_classification_uses_safe_defaults_with_audit() -> None:
    raw = _example("api")
    raw["test_data"] = [
        {
            "description": "session",
            "value": "opaque",
            "sensitive": True,
            "classification": "session",
        },
        {
            "description": "username",
            "value": "user",
            "sensitive": False,
            "classification": "username",
        },
    ]
    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    assert accepted["test_data"][0]["classification"] == "confidential"
    assert accepted["test_data"][1]["classification"] is None
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    records = compatibility_audit_records([raw])
    assert (
        sum(record["rule"] == "unknown_data_classification_to_safe_default" for record in records)
        == 2
    )


def test_unresolved_api_target_and_test_data_extension_remain_audited_draft() -> None:
    raw = _example("api")
    raw["test_data"][0]["variable_name"] = "model_name"
    raw["type_intent"].update({"method": "", "path": "", "expected_status": 0})
    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    assert "variable_name" not in accepted["test_data"][0]
    assert accepted["type_intent"]["method"] == "N/A"
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    candidate = DeterministicCandidateCompiler().compile(accepted, _context("api", accepted))
    assert candidate["type_details"]["method"] == "N/A"
    assert candidate["type_details"]["path"] == ""
    assert candidate["type_details"]["expected_status"] == 0
    assert candidate["review_status"] == "draft"
    records = compatibility_audit_records([raw])
    assert any(record["rule"] == "test_data_extension_preserved_in_artifact" for record in records)
    assert any(record["rule"] == "unresolved_api_target_preserved" for record in records)


def test_na_target_and_spaced_tag_are_normalized_without_fabrication() -> None:
    raw = _example("api")
    raw["tags"] = ["sensitive data", "CORS"]
    raw["type_intent"].update({"method": "N/A", "path": "N/A", "expected_status": None})
    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    assert accepted["tags"] == ["sensitive-data", "cors"]
    assert accepted["type_intent"]["method"] == "N/A"
    assert accepted["type_intent"]["path"] == ""
    assert accepted["type_intent"]["expected_status"] == 0
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    records = compatibility_audit_records([raw])
    assert sum(record["rule"] == "tag_to_canonical_slug" for record in records) == 2
    assert any(record["rule"] == "unresolved_api_target_preserved" for record in records)


def test_scalar_request_body_reference_is_preserved_end_to_end() -> None:
    raw = _example("api")
    raw["type_intent"]["request_body"] = "${data_002}"
    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    assert accepted["type_intent"]["request_body"] == "${data_002}"
    assert raw["type_intent"]["request_body"] == "${data_002}"
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)
    candidate = DeterministicCandidateCompiler().compile(accepted, _context("api", accepted))
    assert candidate["type_details"]["request"]["body"] == "${data_002}"


def test_null_api_semantics_become_explicit_unresolved_draft() -> None:
    raw = _example("api")
    raw["type_intent"].update(
        {
            "method": None,
            "path": None,
            "expected_status": None,
            "response_expectations": None,
            "security_expectations": None,
            "state_expectations": None,
            "setup_semantics": None,
        }
    )
    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    assert accepted["type_intent"]["method"] == "N/A"
    assert accepted["type_intent"]["path"] == ""
    assert accepted["type_intent"]["expected_status"] == 0
    assert accepted["type_intent"]["setup_semantics"] == []
    assert accepted["type_intent"]["response_expectations"] == []
    TestIntentSchemas().validate("api_intent_batch.schema.json", normalized)


def test_ui_evidence_is_deterministically_deferred_to_phase6() -> None:
    raw = _example("ui")
    raw["type_intent"]["evidence_intent"] = "capture_screenshot"
    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    assert raw["type_intent"]["evidence_intent"] == "capture_screenshot"
    assert accepted["type_intent"]["evidence_intent"] == "deferred_no_capture"
    TestIntentSchemas().validate("ui_intent_batch.schema.json", normalized)
    records = compatibility_audit_records([raw])
    assert any(record["rule"] == "ui_evidence_deferred_to_phase6" for record in records)


def test_ui_route_wildcard_becomes_root_route() -> None:
    raw = _example("ui")
    raw["type_intent"]["route"] = "/*"
    normalized = normalize_intent_batch({"intents": [raw]})
    assert raw["type_intent"]["route"] == "/*"
    assert normalized["intents"][0]["type_intent"]["route"] == "/"
    TestIntentSchemas().validate("ui_intent_batch.schema.json", normalized)
    records = compatibility_audit_records([raw])
    assert any(record["rule"] == "ui_route_wildcard_to_reviewable_prefix" for record in records)


@pytest.mark.parametrize(
    ("route", "expected"),
    [
        ("", "/"),
        ("   ", "/"),
        ("/*", "/"),
        ("/register/*", "/register/"),
        ("/register", "/register"),
    ],
)
def test_ui_route_normalization(route: str, expected: str) -> None:
    raw = _example("ui")
    raw["type_intent"]["route"] = route
    normalized = normalize_intent_batch({"intents": [raw]})
    assert normalized["intents"][0]["type_intent"]["route"] == expected


def test_empty_ui_route_has_safe_compatibility_audit() -> None:
    raw = _example("ui")
    raw["type_intent"]["route"] = "   "
    record = next(
        item
        for item in compatibility_audit_records([raw])
        if item["rule"] == "empty_ui_route_to_root"
    )
    assert record["source_summary"] == "empty"
    assert record["accepted_as"] == "/"
    assert "   " not in json.dumps(record)


def test_invalid_nonempty_ui_route_is_not_silently_rewritten() -> None:
    raw = _example("ui")
    raw["type_intent"]["route"] = "not-a-rooted-route"
    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    assert accepted["type_intent"]["route"] == "not-a-rooted-route"
    with pytest.raises(ValidationError):
        DeterministicCandidateCompiler().compile(accepted, _context("ui", accepted))


def test_ui_route_rule_does_not_modify_api_or_manual_intents() -> None:
    api = _example("api")
    api["type_intent"]["route"] = ""
    manual = _example("manual")
    manual["type_intent"]["route"] = ""
    normalized = normalize_intent_batch({"intents": [api, manual]})["intents"]
    assert normalized[0]["type_intent"]["route"] == ""
    assert normalized[0]["type_intent"]["path"] != "/"
    assert normalized[1]["type_intent"]["route"] == ""


def test_ui_002_shape_replays_through_candidate_schema() -> None:
    first = _example("ui")
    first["type_intent"].update(
        {
            "route": "/*",
            "viewport_intent": "any",
            "locator_intents": [],
            "user_actions": ["Trigger HTTP responses from the SUT."],
            "visible_assertions": [],
            "url_assertions": [],
            "session_assertions": [],
            "network_assertions": [
                "No HTTP response body contains passwords, cookies, tokens, hashes, "
                "database paths, or stack traces."
            ],
            "evidence_intent": "deferred_no_capture",
        }
    )
    normalized = normalize_intent_batch({"intents": [first]})
    accepted = normalized["intents"][0]
    candidate = DeterministicCandidateCompiler().compile(accepted, _context("ui", accepted))
    assert candidate["type_details"]["route"] == "/"
    assert candidate["type_details"]["viewport"] == "responsive-matrix"
    assert candidate["type_details"]["user_actions"] == ["Trigger HTTP responses from the SUT."]
    assert candidate["type_details"]["network_assertions"] == [
        "No HTTP response body contains passwords, cookies, tokens, hashes, "
        "database paths, or stack traces."
    ]


def test_candidate_schema_still_rejects_empty_ui_route() -> None:
    intent = _example("ui")
    candidate = DeterministicCandidateCompiler().compile(intent, _context("ui", intent))
    candidate["type_details"]["route"] = ""
    with pytest.raises(ValidationError) as captured:
        TestCaseSchemas().validate("test_case_candidate.schema.json", candidate)
    route_errors = [
        child
        for branch in captured.value.context
        for child in branch.context or [branch]
        if list(child.absolute_path) == ["type_details", "route"]
    ]
    assert any(error.validator == "pattern" for error in route_errors)


def test_null_ui_fields_and_missing_cleanup_instructions_are_audited() -> None:
    raw = _example("ui")
    raw["cleanup_intent"] = {"required": False}
    raw["type_intent"]["viewport_intent"] = None
    raw["type_intent"]["visible_assertions"] = None
    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    assert accepted["cleanup_intent"]["instructions"] == []
    assert accepted["type_intent"]["viewport_intent"] == "responsive-matrix"
    assert accepted["type_intent"]["visible_assertions"] == []
    TestIntentSchemas().validate("ui_intent_batch.schema.json", normalized)
    rules = {record["rule"] for record in compatibility_audit_records([raw])}
    assert "missing_cleanup_instructions_to_empty_list" in rules
    assert "null_viewport_to_responsive_matrix" in rules
    assert "null_ui_semantic_list_to_empty_list" in rules


def test_unknown_viewport_and_multi_route_are_reviewable() -> None:
    raw = _example("ui")
    raw["type_intent"]["viewport_intent"] = "none"
    raw["type_intent"]["route"] = "/register,/login,/profile"
    normalized = normalize_intent_batch({"intents": [raw]})
    accepted = normalized["intents"][0]
    assert accepted["type_intent"]["viewport_intent"] == "responsive-matrix"
    assert accepted["type_intent"]["route"] == "/"
    TestIntentSchemas().validate("ui_intent_batch.schema.json", normalized)
    rules = {record["rule"] for record in compatibility_audit_records([raw])}
    assert "unknown_viewport_to_responsive_matrix" in rules
    assert "multi_route_string_to_reviewable_root_route" in rules


def test_inline_test_data_mapping_expands_with_sensitive_classification() -> None:
    raw = _example("manual")
    raw["test_data"] = [{"username": "user", "password": "secret", "expected_status": 200}]
    normalized = normalize_intent_batch({"intents": [raw]})
    data = normalized["intents"][0]["test_data"]
    assert len(data) == 3
    password = next(item for item in data if item["description"] == "password")
    assert password["sensitive"] is True
    assert password["classification"] == "credential"
    TestIntentSchemas().validate("manual_intent_batch.schema.json", normalized)
    rules = {record["rule"] for record in compatibility_audit_records([raw])}
    assert "inline_test_data_mapping_to_formal_items" in rules


def test_missing_test_data_sensitivity_fields_get_audited_defaults() -> None:
    raw = _example("manual")
    raw["test_data"] = [{"description": "password", "value": "secret"}]
    normalized = normalize_intent_batch({"intents": [raw]})
    item = normalized["intents"][0]["test_data"][0]
    assert item["sensitive"] is True
    assert item["classification"] == "credential"
    TestIntentSchemas().validate("manual_intent_batch.schema.json", normalized)
    rules = {record["rule"] for record in compatibility_audit_records([raw])}
    assert "missing_test_data_sensitivity_defaults" in rules
