from __future__ import annotations

import json
from typing import Any

from plugin.backend.app.test_generation_prompts import TestGenerationPromptRegistry
from plugin.backend.app.test_intent_schemas import TestIntentSchemas

INTENT_FIELDS = {
    "generation_slot_id",
    "title",
    "objective",
    "priority",
    "risk_level",
    "scenario_type",
    "preconditions",
    "test_data",
    "actions",
    "expected_outcomes",
    "cleanup_intent",
    "tags",
    "type_intent",
}
FORBIDDEN_MODEL_FIELDS = {
    "requirement_ids",
    "primary_requirement_id",
    "intent_id",
    "case_id",
    "case_type",
    "generation_run_id",
    "batch_id",
    "schema_version",
    "case_version",
    "source",
    "review_status",
    "lifecycle_status",
    "created_at",
    "content_hash",
    "trace",
}


class TestIntentContractError(Exception):
    pass


def validate_test_intent_prompt_contract(
    prompts: TestGenerationPromptRegistry,
    schemas: TestIntentSchemas,
) -> dict[str, Any]:
    schema = schemas.schemas["test_intent.schema.json"]
    if set(schema["required"]) != INTENT_FIELDS:
        raise TestIntentContractError("INTENT_SCHEMA_FIELD_DRIFT")
    reports: dict[str, Any] = {}
    for case_type in ("api", "ui", "manual"):
        system = prompts._content[f"{case_type}_cases_system.md"]
        line = next(
            (item for item in system.splitlines() if item.startswith('{"generation_slot_id"')), None
        )
        if line is None:
            raise TestIntentContractError(f"INTENT_PROMPT_EXAMPLE_MISSING:{case_type}")
        example = json.loads(line)
        if set(example) != INTENT_FIELDS:
            raise TestIntentContractError(f"INTENT_PROMPT_EXAMPLE_FIELD_DRIFT:{case_type}")
        if set(example) & FORBIDDEN_MODEL_FIELDS:
            raise TestIntentContractError(f"INTENT_PROMPT_SYSTEM_FIELDS_PRESENT:{case_type}")
        schemas.validate("test_intent.schema.json", example)
        schemas.validate(f"{case_type}_intent_batch.schema.json", {"intents": [example]})
        reports[case_type] = {"example": example, "intent_fields": sorted(INTENT_FIELDS)}
    return reports
