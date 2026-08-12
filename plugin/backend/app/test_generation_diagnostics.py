from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from jsonschema import ValidationError

from plugin.backend.app.test_generation_budget import estimate_serialized_value
from plugin.backend.app.test_generation_payloads import (
    contract_for_case_type,
    project_generation_slot,
)
from plugin.backend.app.test_generation_planning import make_generation_slot
from plugin.backend.app.test_generation_prompts import TestGenerationPromptRegistry
from plugin.backend.app.test_generation_schemas import TEST_CASE_SCHEMA_VERSION

DIAGNOSTICS_VERSION = "test-generation-payload-diagnostics@1.0.0"
_SENSITIVE_PATTERN = re.compile(r"(?i)(password|secret|token|cookie|authorization|api[_ -]?key)")


def safe_schema_error_details(
    error: ValidationError,
    *,
    validation_stage: str,
    limit: int = 160,
) -> list[dict[str, Any]]:
    """Expand jsonschema leaf errors without exposing model payloads or credentials."""

    def summarize(value: Any) -> Any:
        if isinstance(value, str):
            if _SENSITIVE_PATTERN.search(value):
                return "[REDACTED_SENSITIVE]"
            return value[:limit]
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, list):
            return {"type": "array", "length": len(value)}
        if isinstance(value, dict):
            safe_keys = [
                "[REDACTED_SENSITIVE]" if _SENSITIVE_PATTERN.search(str(key)) else str(key)[:limit]
                for key in value
            ]
            return {"type": "object", "keys": sorted(safe_keys)[:30]}
        return type(value).__name__

    def leaves(item: ValidationError) -> list[ValidationError]:
        if not item.context:
            return [item]
        return [leaf for child in item.context for leaf in leaves(child)]

    details: list[dict[str, Any]] = []
    for leaf in leaves(error):
        schema_path = list(leaf.absolute_schema_path)
        branch = "unknown"
        if "oneOf" in schema_path:
            branch_index = schema_path[schema_path.index("oneOf") + 1]
            if isinstance(branch_index, int):
                branch = {0: "api", 1: "ui", 2: "manual"}.get(branch_index, "unknown")
        details.append(
            {
                "validation_stage": validation_stage,
                "branch": branch,
                "instance_path": "/" + "/".join(map(str, leaf.absolute_path)),
                "schema_path": "/" + "/".join(map(str, schema_path)),
                "validator": str(leaf.validator),
                "expected": summarize(leaf.validator_value),
                "actual_type": type(leaf.instance).__name__,
                "actual": summarize(leaf.instance),
                "message": (
                    "[REDACTED_SENSITIVE]"
                    if _SENSITIVE_PATTERN.search(leaf.message)
                    else leaf.message[:limit]
                ),
                "parent_validator": str(error.validator),
            }
        )
    return details


def generation_payload_diagnostics(
    *,
    case_type: str,
    batch_id: str,
    requirement_snapshots: list[dict[str, Any]],
    prompts: TestGenerationPromptRegistry,
) -> dict[str, Any]:
    slots = [
        make_generation_slot(str(item["requirement_id"]), case_type)
        for item in requirement_snapshots
    ]
    projected = [
        project_generation_slot(slot, snapshot)
        for slot, snapshot in zip(slots, requirement_snapshots, strict=True)
    ]
    api_contract, ui_contract = contract_for_case_type(case_type)
    contract = api_contract or ui_contract
    messages = prompts.generation_messages(
        case_type=case_type,
        batch_id=batch_id,
        generation_run_id="TGR-" + ("0" * 32),
        provider_mode="real",
        generation_slots=projected,
        max_cases=len(projected),
        api_contract=api_contract,
        ui_contract=ui_contract,
    )
    system = messages[0]["content"]
    user = messages[-1]["content"]
    prefix = "manual" if case_type == "manual" else case_type
    user_template = (prompts.root / f"{prefix}_cases_user.md").read_text(encoding="utf-8")
    fixed_user = user_template
    for marker in (
        "{{batch_id}}",
        "{{generation_run_id}}",
        "{{provider_mode}}",
        "{{slots_json}}",
        "{{api_contract}}",
        "{{ui_contract}}",
    ):
        fixed_user = fixed_user.replace(marker, "")
    example = next(
        (line for line in system.splitlines() if line.startswith(('{"generation_slot_id"',))),
        "",
    )
    requirement_json = json.dumps(projected, ensure_ascii=False, separators=(",", ":"))
    schema_marker = f"schema={TEST_CASE_SCHEMA_VERSION}"
    estimate = estimate_serialized_value(messages)
    return {
        "diagnostics_version": DIAGNOSTICS_VERSION,
        "batch_id": batch_id,
        "case_type": case_type,
        "system_prompt_characters": len(system),
        "user_prompt_fixed_template_characters": len(fixed_user),
        "json_example_characters": len(example),
        "schema_description_characters": len(schema_marker),
        "requirement_payload_characters": len(requirement_json),
        "api_or_ui_contract_characters": len(contract),
        "repeated_json_field_characters": _repeated_json_field_characters(projected),
        "rendered_user_prompt_characters": len(user),
        "final_serialized_character_count": estimate.character_count,
        "final_serialized_utf8_byte_count": estimate.utf8_byte_count,
        "conservative_budget_tokens": estimate.budget_tokens,
    }


def _repeated_json_field_characters(value: Any) -> int:
    keys: Counter[str] = Counter()

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                keys[str(key)] += 1
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return sum((count - 1) * len(key) for key, count in keys.items() if count > 1)
