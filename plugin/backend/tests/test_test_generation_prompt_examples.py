from __future__ import annotations

from plugin.backend.app.providers import ProviderMetadata
from plugin.backend.app.test_generation_prompts import TestGenerationPromptRegistry
from plugin.backend.app.test_generation_schemas import TestCaseSchemas
from plugin.backend.app.test_intent_compiler import (
    CompilationContext,
    DeterministicCandidateCompiler,
)
from plugin.backend.app.test_intent_contract import (
    FORBIDDEN_MODEL_FIELDS,
    INTENT_FIELDS,
    validate_test_intent_prompt_contract,
)
from plugin.backend.app.test_intent_schemas import TestIntentSchemas


def test_prompt_examples_compile_to_complete_candidate_schema() -> None:
    intent_schemas = TestIntentSchemas()
    candidate_schemas = TestCaseSchemas()
    reports = validate_test_intent_prompt_contract(TestGenerationPromptRegistry(), intent_schemas)
    compiler = DeterministicCandidateCompiler(candidate_schemas)
    for case_type, report in reports.items():
        example = report["example"]
        assert set(example) == INTENT_FIELDS
        assert not set(example) & FORBIDDEN_MODEL_FIELDS
        requirement_id = "REQ-EXAMPLE-001"
        label = {"api": "API", "ui": "UI", "manual": "MAN"}[case_type]
        slot = {
            "generation_slot_id": example["generation_slot_id"],
            "primary_requirement_id": requirement_id,
            "requirement_ids": [requirement_id],
            "case_type": case_type,
            "case_id": f"TC-{label}-EXAMPLE-001",
        }
        snapshot = {
            "requirement_id": requirement_id,
            "requirement_version": 1,
            "snapshot_hash": "0" * 64,
            "source_block_id": "BLK-EXAMPLE-001",
            "prd_document_id": "PRD-" + ("0" * 32),
            "prd_version_id": "PRDV-" + ("0" * 32),
        }
        candidate = compiler.compile(
            example,
            CompilationContext(
                run_id="TGR-" + ("0" * 32),
                project_id="PRJ-" + ("0" * 32),
                provider=ProviderMetadata("mock", "deterministic-example", "mock"),
                snapshots={requirement_id: snapshot},
                slots={example["generation_slot_id"]: slot},
            ),
        )
        candidate_schemas.validate("test_case_candidate.schema.json", candidate)
        assert candidate["case_type"] == case_type


def test_api_setup_prompt_contract_is_derived_from_current_schema() -> None:
    prompts = TestGenerationPromptRegistry()
    setup = TestIntentSchemas().schemas["test_intent.schema.json"]["$defs"]["setup_api_request"]
    messages = prompts.generation_messages(
        case_type="api",
        batch_id="TGB-API-001",
        generation_run_id="TGR-" + ("0" * 32),
        provider_mode="real",
        generation_slots=[],
        max_cases=1,
        recovery=True,
        validation_error="INTENT_SCHEMA_VALIDATION",
    )
    rendered = "\n".join(item["content"] for item in messages)
    assert "required=" + ",".join(setup["required"]) in rendered
    assert "allowed=" + ",".join(setup["properties"]) in rendered
    assert "path_pattern=" + setup["properties"]["path"]["pattern"] in rendered
    assert "path!=N/A" in rendered
