from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Any

from plugin.backend.app.test_generation_trace import (
    SeededRequirementResolutionError,
    resolve_seeded_username_requirement,
)

CASE_TYPES = ("api", "ui", "manual")


class GenerationPlanValidationError(Exception):
    pass


@dataclass(frozen=True)
class GenerationPlanValidation:
    requirement_count: int
    slot_count: int
    batch_count: int
    slot_type_counts: dict[str, int]
    batch_type_counts: dict[str, int]
    seeded_requirement_id: str
    seeded_api_case_id: str
    seeded_ui_case_id: str
    maximum_content_calls: int
    maximum_provider_attempts: int
    worst_case_cost_microusd: int

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_generation_plan(
    plan: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
    capacities: list[dict[str, Any]],
    *,
    expected_requirement_count: int,
    maximum_structure_corrections: int,
    maximum_content_calls: int,
    maximum_provider_attempts: int,
    worst_case_cost_microusd: int,
    budget_microusd: int,
) -> GenerationPlanValidation:
    requirements = list(plan.get("requirements", []))
    batches = list(plan.get("batches", []))
    if (
        len(requirements) != expected_requirement_count
        or len(snapshots) != expected_requirement_count
    ):
        raise GenerationPlanValidationError("REQUIREMENT_COUNT_MISMATCH")

    requirement_ids = [str(item.get("requirement_id", "")) for item in requirements]
    if len(set(requirement_ids)) != len(requirement_ids) or set(requirement_ids) != set(snapshots):
        raise GenerationPlanValidationError("REQUIREMENT_ID_SET_MISMATCH")
    expected_slots: set[tuple[str, str]] = set()
    for requirement in requirements:
        requirement_id = str(requirement["requirement_id"])
        applicable = list(requirement.get("applicable_case_types", []))
        if not applicable or len(set(applicable)) != len(applicable):
            raise GenerationPlanValidationError(
                f"REQUIREMENT_APPLICABILITY_INVALID:{requirement_id}"
            )
        if not set(applicable).issubset(CASE_TYPES):
            raise GenerationPlanValidationError(f"CASE_TYPE_INVALID:{requirement_id}")
        expected_slots.update((requirement_id, case_type) for case_type in applicable)

    actual_slots: set[tuple[str, str]] = set()
    slot_ids: set[str] = set()
    case_ids: dict[tuple[str, str], str] = {}
    slot_type_counts: Counter[str] = Counter()
    batch_type_counts: Counter[str] = Counter()
    for batch in batches:
        case_type = str(batch.get("case_type", ""))
        if case_type not in CASE_TYPES:
            raise GenerationPlanValidationError("BATCH_CASE_TYPE_INVALID")
        batch_type_counts[case_type] += 1
        batch_slots = list(batch.get("generation_slots", []))
        if not batch_slots or int(batch.get("max_cases", 0)) != len(batch_slots):
            raise GenerationPlanValidationError(
                f"BATCH_SLOT_COUNT_INVALID:{batch.get('batch_key')}"
            )
        batch_requirement_ids = [str(item) for item in batch.get("requirement_ids", [])]
        if batch_requirement_ids != [
            str(slot.get("primary_requirement_id")) for slot in batch_slots
        ]:
            raise GenerationPlanValidationError(
                f"BATCH_REQUIREMENT_TRACE_INVALID:{batch.get('batch_key')}"
            )
        for slot in batch_slots:
            requirement_id = str(slot.get("primary_requirement_id", ""))
            pair = (requirement_id, case_type)
            slot_id = str(slot.get("generation_slot_id", ""))
            if pair in actual_slots or slot_id in slot_ids:
                raise GenerationPlanValidationError(f"DUPLICATE_GENERATION_SLOT:{slot_id}")
            if str(slot.get("case_type", "")) != case_type:
                raise GenerationPlanValidationError(f"SLOT_CASE_TYPE_MISMATCH:{slot_id}")
            if list(slot.get("requirement_ids", [])) != [requirement_id]:
                raise GenerationPlanValidationError(f"SLOT_REQUIREMENT_TRACE_INVALID:{slot_id}")
            actual_slots.add(pair)
            slot_ids.add(slot_id)
            slot_type_counts[case_type] += 1
            case_ids[pair] = str(slot.get("case_id", ""))

    if actual_slots != expected_slots:
        missing = sorted(expected_slots - actual_slots)
        extra = sorted(actual_slots - expected_slots)
        raise GenerationPlanValidationError(
            f"SLOT_COVERAGE_MISMATCH:missing={missing}:extra={extra}"
        )
    if int(plan.get("generation_slot_count", -1)) != len(actual_slots):
        raise GenerationPlanValidationError("SLOT_TYPE_STATISTICS_MISMATCH")
    if len(capacities) != len(batches):
        raise GenerationPlanValidationError("BATCH_CAPACITY_COUNT_MISMATCH")
    for capacity in capacities:
        if int(capacity["input_estimate"]["budget_tokens"]) > int(capacity["input_budget_tokens"]):
            raise GenerationPlanValidationError(
                f"BATCH_INPUT_CAPACITY_EXCEEDED:{capacity['batch_key']}"
            )
        if int(capacity["output_estimate"]["budget_tokens"]) > int(
            capacity["output_safe_limit_tokens"]
        ):
            raise GenerationPlanValidationError(
                f"BATCH_OUTPUT_CAPACITY_EXCEEDED:{capacity['batch_key']}"
            )

    try:
        seeded = resolve_seeded_username_requirement(snapshots)
    except SeededRequirementResolutionError as error:
        raise GenerationPlanValidationError(str(error)) from error
    seeded_id = seeded.resolved_requirement_id
    if case_ids.get((seeded_id, "api")) != "TC-API-AUTH-REG-005":
        raise GenerationPlanValidationError("SEEDED_API_SLOT_MISSING")
    if case_ids.get((seeded_id, "ui")) != "TC-UI-AUTH-REG-005":
        raise GenerationPlanValidationError("SEEDED_UI_SLOT_MISSING")

    required_content_calls = len(batches) + maximum_structure_corrections
    if required_content_calls > maximum_content_calls:
        raise GenerationPlanValidationError("CONTENT_CALL_LIMIT_EXCEEDED")
    if maximum_content_calls > maximum_provider_attempts:
        raise GenerationPlanValidationError("PROVIDER_ATTEMPT_LIMIT_EXCEEDED")
    if worst_case_cost_microusd > budget_microusd:
        raise GenerationPlanValidationError("GENERATION_BUDGET_EXCEEDED")
    return GenerationPlanValidation(
        requirement_count=len(requirements),
        slot_count=len(actual_slots),
        batch_count=len(batches),
        slot_type_counts={case_type: slot_type_counts[case_type] for case_type in CASE_TYPES},
        batch_type_counts={case_type: batch_type_counts[case_type] for case_type in CASE_TYPES},
        seeded_requirement_id=seeded_id,
        seeded_api_case_id=case_ids[(seeded_id, "api")],
        seeded_ui_case_id=case_ids[(seeded_id, "ui")],
        maximum_content_calls=maximum_content_calls,
        maximum_provider_attempts=maximum_provider_attempts,
        worst_case_cost_microusd=worst_case_cost_microusd,
    )
