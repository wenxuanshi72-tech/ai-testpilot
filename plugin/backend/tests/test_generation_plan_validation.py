from __future__ import annotations

import copy
import hashlib
from typing import Any

import pytest

from plugin.backend.app.test_generation_plan_validation import (
    GenerationPlanValidationError,
    validate_generation_plan,
)
from plugin.backend.app.test_generation_planning import make_generation_slot
from plugin.backend.app.test_generation_trace import (
    SeededRequirementResolutionError,
    assert_unique_requirement_identities,
    normalize_requirement_identity,
    resolve_seeded_username_requirement,
)


def _snapshot(requirement_id: str) -> dict[str, Any]:
    excerpt = (
        "Registration username must have at least six characters."
        if normalize_requirement_identity(requirement_id) == "REQ-BAT-2-6"
        else "The system shall support an observable authentication behavior."
    )
    requirement = {
        "requirement_id": requirement_id,
        "title": "Authentication behavior",
        "description": excerpt,
        "requirement_type": "functional",
        "priority": "high",
        "risk_level": "high",
        "business_rules": [excerpt],
        "acceptance_criteria": [excerpt],
        "tags": ["authentication"],
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


def _plan(
    *, padded_seed: bool, api_batches: int, manual_slots: int
) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict[str, Any]]]:
    seeded_id = "REQ-BAT-002-006" if padded_seed else "REQ-BAT-002-6"
    requirement_ids = [seeded_id, *[f"REQ-AUTH-{index:03d}" for index in range(1, 19)]]
    snapshots = {item: _snapshot(item) for item in requirement_ids}
    applicability = {
        item: [
            "api",
            *(["ui"] if index < 15 else []),
            *(["manual"] if index < manual_slots else []),
        ]
        for index, item in enumerate(requirement_ids)
    }
    slots_by_type = {
        case_type: [
            make_generation_slot(item, case_type)
            for item in requirement_ids
            if case_type in applicability[item]
        ]
        for case_type in ("api", "ui", "manual")
    }
    requested_batches = {"api": api_batches, "ui": 6, "manual": 4}
    batches: list[dict[str, Any]] = []
    labels = {"api": "API", "ui": "UI", "manual": "MAN"}
    batch_index = 1
    for case_type, slots in slots_by_type.items():
        groups = [[] for _ in range(requested_batches[case_type])]
        for index, slot in enumerate(slots):
            groups[index % len(groups)].append(slot)
        for type_index, group in enumerate(groups, 1):
            batches.append(
                {
                    "batch_key": f"TGB-{labels[case_type]}-{type_index:03d}",
                    "batch_index": batch_index,
                    "case_type": case_type,
                    "requirement_ids": [slot["primary_requirement_id"] for slot in group],
                    "generation_slots": group,
                    "max_cases": len(group),
                    "max_tokens": 3072,
                    "input_hash": "a" * 64,
                }
            )
            batch_index += 1
    plan = {
        "requirements": [
            {
                "requirement_id": item,
                "requirement_version": 1,
                "snapshot_hash": snapshots[item]["snapshot_hash"],
                "applicable_case_types": applicability[item],
            }
            for item in requirement_ids
        ],
        "generation_slot_count": sum(len(items) for items in slots_by_type.values()),
        "batches": batches,
    }
    capacities = [
        {
            "batch_key": batch["batch_key"],
            "input_estimate": {"budget_tokens": 1000},
            "input_budget_tokens": 2400,
            "output_estimate": {"budget_tokens": 1000},
            "output_safe_limit_tokens": 2400,
        }
        for batch in batches
    ]
    return plan, snapshots, capacities


def _validate(
    plan: dict[str, Any], snapshots: dict[str, dict[str, Any]], capacities: list[dict[str, Any]]
):
    return validate_generation_plan(
        plan,
        snapshots,
        capacities,
        expected_requirement_count=19,
        maximum_structure_corrections=8,
        maximum_content_calls=len(plan["batches"]) + 8,
        maximum_provider_attempts=40,
        worst_case_cost_microusd=126_898,
        budget_microusd=250_000,
    )


def test_historical_46_17_and_real_44_18_plans_pass_dynamic_contract() -> None:
    historical = _plan(padded_seed=False, api_batches=7, manual_slots=12)
    current = _plan(padded_seed=True, api_batches=8, manual_slots=10)
    assert _validate(*historical).slot_count == 46
    result = _validate(*current)
    assert result.slot_count == 44
    assert result.batch_count == 18
    assert result.slot_type_counts == {"api": 19, "ui": 15, "manual": 10}
    assert result.seeded_requirement_id == "REQ-BAT-002-006"
    assert result.seeded_api_case_id == "TC-API-AUTH-REG-005"
    assert result.seeded_ui_case_id == "TC-UI-AUTH-REG-005"


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "uncovered", "type_stats"])
def test_dynamic_contract_rejects_slot_and_coverage_defects(mutation: str) -> None:
    plan, snapshots, capacities = _plan(padded_seed=True, api_batches=8, manual_slots=10)
    if mutation == "missing":
        plan["batches"][0]["generation_slots"].pop()
        plan["batches"][0]["requirement_ids"].pop()
        plan["batches"][0]["max_cases"] -= 1
    elif mutation == "duplicate":
        slot = copy.deepcopy(plan["batches"][0]["generation_slots"][0])
        plan["batches"][1]["generation_slots"].append(slot)
        plan["batches"][1]["requirement_ids"].append(slot["primary_requirement_id"])
        plan["batches"][1]["max_cases"] += 1
    elif mutation == "uncovered":
        plan["requirements"][0]["applicable_case_types"].append("manual")
    else:
        plan["generation_slot_count"] += 1
    with pytest.raises(GenerationPlanValidationError):
        _validate(plan, snapshots, capacities)


def test_dynamic_contract_rejects_capacity_call_and_cost_limits() -> None:
    plan, snapshots, capacities = _plan(padded_seed=True, api_batches=8, manual_slots=10)
    capacities[0]["input_estimate"]["budget_tokens"] = 2401
    with pytest.raises(GenerationPlanValidationError, match="BATCH_INPUT_CAPACITY_EXCEEDED"):
        _validate(plan, snapshots, capacities)
    capacities[0]["input_estimate"]["budget_tokens"] = 1000
    with pytest.raises(GenerationPlanValidationError, match="CONTENT_CALL_LIMIT_EXCEEDED"):
        validate_generation_plan(
            plan,
            snapshots,
            capacities,
            expected_requirement_count=19,
            maximum_structure_corrections=8,
            maximum_content_calls=25,
            maximum_provider_attempts=40,
            worst_case_cost_microusd=126_898,
            budget_microusd=250_000,
        )
    with pytest.raises(GenerationPlanValidationError, match="GENERATION_BUDGET_EXCEEDED"):
        validate_generation_plan(
            plan,
            snapshots,
            capacities,
            expected_requirement_count=19,
            maximum_structure_corrections=8,
            maximum_content_calls=26,
            maximum_provider_attempts=40,
            worst_case_cost_microusd=250_001,
            budget_microusd=250_000,
        )


def test_requirement_identity_is_exact_except_for_numeric_leading_zeroes() -> None:
    assert normalize_requirement_identity("REQ-BAT-002-6") == "REQ-BAT-2-6"
    assert normalize_requirement_identity("REQ-BAT-002-006") == "REQ-BAT-2-6"
    assert normalize_requirement_identity("REQ-BAT-003-006") != "REQ-BAT-2-6"
    assert normalize_requirement_identity("REQ-BAT-002-6A") != "REQ-BAT-2-6"
    with pytest.raises(SeededRequirementResolutionError, match="REQUIREMENT_IDENTITY_COLLISION"):
        assert_unique_requirement_identities(["REQ-BAT-002-6", "REQ-BAT-002-006"])


def test_seeded_resolution_preserves_original_id_and_requires_formal_constraint() -> None:
    padded = _snapshot("REQ-BAT-002-006")
    result = resolve_seeded_username_requirement({"REQ-BAT-002-006": padded})
    assert result.resolved_requirement_id == "REQ-BAT-002-006"
    invalid = _snapshot("REQ-BAT-002-006")
    invalid["requirement"]["description"] = "Registration is supported."
    invalid["requirement"]["business_rules"] = ["Registration is supported."]
    invalid["requirement"]["acceptance_criteria"] = ["Registration is supported."]
    invalid["source_excerpt"] = "Registration is supported."
    invalid["requirement"]["source_excerpt"] = "Registration is supported."
    with pytest.raises(SeededRequirementResolutionError, match="SEEDED_REQUIREMENT_NOT_FOUND"):
        resolve_seeded_username_requirement({"REQ-BAT-002-006": invalid})
