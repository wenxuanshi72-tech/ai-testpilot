from __future__ import annotations

import hashlib
from collections import deque

from jsonschema import ValidationError

from plugin.backend.app.test_generation_diagnostics import (
    generation_payload_diagnostics,
    safe_schema_error_details,
)
from plugin.backend.app.test_generation_prompts import (
    TestGenerationPromptRegistry as GenerationPromptRegistry,
)


def test_field_level_payload_diagnostics_match_final_serialized_messages() -> None:
    excerpt = "Registration username must have a minimum of six characters."
    snapshot = {
        "requirement_id": "REQ-BAT-002-6",
        "requirement_version": 1,
        "snapshot_hash": hashlib.sha256(excerpt.encode()).hexdigest(),
        "source_block_id": "BLK-L0001-L0001-0000000001",
        "source_excerpt": excerpt,
        "requirement": {
            "requirement_id": "REQ-BAT-002-6",
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
        },
    }
    report = generation_payload_diagnostics(
        case_type="api",
        batch_id="TGB-API-001",
        requirement_snapshots=[snapshot],
        prompts=GenerationPromptRegistry(),
    )
    assert report["system_prompt_characters"] > report["json_example_characters"] > 0
    assert report["user_prompt_fixed_template_characters"] > 0
    assert report["schema_description_characters"] == len("schema=test-cases@1.5.0")
    assert report["requirement_payload_characters"] > 0
    assert report["api_or_ui_contract_characters"] > 0
    assert report["final_serialized_character_count"] > (
        report["system_prompt_characters"] + report["rendered_user_prompt_characters"]
    )
    assert report["conservative_budget_tokens"] > 0


def test_schema_diagnostics_expand_ui_route_leaf_and_redact_sensitive_values() -> None:
    leaf = ValidationError(
        "'' does not match the route pattern",
        validator="pattern",
        validator_value="^/[A-Za-z0-9_./{}-]*$",
        instance="",
        path=deque(["route"]),
        schema_path=deque([1, "properties", "route", "pattern"]),
    )
    parent = ValidationError(
        "candidate does not match exactly one branch",
        validator="oneOf",
        validator_value=[],
        instance={"authorization": "Bearer synthetic-secret-token"},
        path=deque(["type_details"]),
        schema_path=deque(["properties", "type_details", "oneOf"]),
        context=[leaf],
    )
    details = safe_schema_error_details(parent, validation_stage="candidate_schema")
    assert details == [
        {
            "validation_stage": "candidate_schema",
            "branch": "ui",
            "instance_path": "/type_details/route",
            "schema_path": "/properties/type_details/oneOf/1/properties/route/pattern",
            "validator": "pattern",
            "expected": "^/[A-Za-z0-9_./{}-]*$",
            "actual_type": "str",
            "actual": "",
            "message": "'' does not match the route pattern",
            "parent_validator": "oneOf",
        }
    ]
