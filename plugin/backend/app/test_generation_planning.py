from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Any

from plugin.backend.app.test_generation_budget import (
    DEFAULT_INPUT_BUDGET_TOKENS,
    DEFAULT_OUTPUT_UTILIZATION_PERCENT,
    TokenEstimate,
    estimate_serialized_value,
    output_safe_token_limit,
)
from plugin.backend.app.test_generation_payloads import (
    contract_for_case_type,
    project_generation_slot,
)
from plugin.backend.app.test_generation_prompts import (
    TEST_GENERATION_PROMPT_VERSION,
    TestGenerationPromptRegistry,
)
from plugin.backend.app.test_intent_mock import build_mock_intent_batch
from plugin.backend.app.test_intent_schemas import TEST_INTENT_SCHEMA_VERSION

CAPACITY_PLANNER_VERSION = "test-generation-capacity-planner@2.0.0"
API_INPUT_BUDGET_TOKENS = 2400


class CapacityPlanningError(Exception):
    pass


@dataclass(frozen=True)
class BatchCapacity:
    batch_key: str
    case_type: str
    requirement_count: int
    slot_count: int
    max_cases: int
    max_tokens: int
    input_estimate: TokenEstimate
    output_estimate: TokenEstimate
    input_budget_tokens: int
    output_safe_limit_tokens: int
    compatible_recovery_key: str

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["input_estimate"] = self.input_estimate.as_dict()
        value["output_estimate"] = self.output_estimate.as_dict()
        return value


def make_generation_slot(requirement_id: str, case_type: str) -> dict[str, Any]:
    label = {"api": "API", "ui": "UI", "manual": "MAN"}[case_type]
    digest = hashlib.sha256(f"{case_type}:{requirement_id}".encode()).hexdigest()[:16].upper()
    if requirement_id == "REQ-BAT-002-6" and case_type in {"api", "ui"}:
        case_id = f"TC-{label}-AUTH-REG-005"
    else:
        suffix = re.sub(r"[^A-Z0-9]+", "-", requirement_id.upper()).strip("-")[:60]
        case_id = f"TC-{label}-{suffix}"
    return {
        "generation_slot_id": f"GSL-{label}-{digest}",
        "primary_requirement_id": requirement_id,
        "requirement_ids": [requirement_id],
        "case_type": case_type,
        "case_id": case_id,
    }


def build_capacity_bounded_batches(
    *,
    snapshots: dict[str, dict[str, Any]],
    applicability: dict[str, list[str]],
    prompts: TestGenerationPromptRegistry,
    max_requirements_per_batch: int,
    max_cases_per_batch: int,
    max_tokens_per_batch: int,
    input_budget_tokens: int = DEFAULT_INPUT_BUDGET_TOKENS,
    output_utilization_percent: int = DEFAULT_OUTPUT_UTILIZATION_PERCENT,
) -> tuple[list[dict[str, Any]], list[BatchCapacity]]:
    batches = []
    capacities = []
    batch_index = 1
    labels = {"api": "API", "ui": "UI", "manual": "MAN"}
    for case_type in ("api", "ui", "manual"):
        pending = [make_generation_slot(rid, case_type) for rid in applicability[case_type]]
        type_index = 1
        while pending:
            selected: list[dict[str, Any]] = []
            selected_capacity = None
            for slot in pending[:max_requirements_per_batch]:
                proposed = [*selected, slot]
                if len(proposed) > max_cases_per_batch:
                    break
                key = f"TGB-{labels[case_type]}-{type_index:03d}"
                capacity = analyze_batch_capacity(
                    batch_key=key,
                    case_type=case_type,
                    generation_slots=proposed,
                    snapshots=snapshots,
                    prompts=prompts,
                    max_tokens=max_tokens_per_batch,
                    max_cases=len(proposed),
                    input_budget_tokens=(
                        API_INPUT_BUDGET_TOKENS if case_type == "api" else input_budget_tokens
                    ),
                    output_utilization_percent=output_utilization_percent,
                )
                if (
                    capacity.input_estimate.budget_tokens > capacity.input_budget_tokens
                    or capacity.output_estimate.budget_tokens > capacity.output_safe_limit_tokens
                ):
                    break
                selected = proposed
                selected_capacity = capacity
            if not selected or selected_capacity is None:
                raise CapacityPlanningError(
                    f"SINGLE_SLOT_EXCEEDS_CAPACITY:{case_type}:{pending[0]['generation_slot_id']}"
                )
            batches.append(
                {
                    "batch_key": selected_capacity.batch_key,
                    "batch_index": batch_index,
                    "case_type": case_type,
                    "requirement_ids": [s["primary_requirement_id"] for s in selected],
                    "generation_slots": selected,
                    "max_cases": len(selected),
                    "max_tokens": max_tokens_per_batch,
                    "input_hash": selected_capacity.compatible_recovery_key,
                }
            )
            capacities.append(selected_capacity)
            pending = pending[len(selected) :]
            batch_index += 1
            type_index += 1
    return batches, capacities


def analyze_batch_capacity(
    *,
    batch_key: str,
    case_type: str,
    generation_slots: list[dict[str, Any]],
    snapshots: dict[str, dict[str, Any]],
    prompts: TestGenerationPromptRegistry,
    max_tokens: int,
    max_cases: int,
    input_budget_tokens: int = DEFAULT_INPUT_BUDGET_TOKENS,
    output_utilization_percent: int = DEFAULT_OUTPUT_UTILIZATION_PERCENT,
) -> BatchCapacity:
    projected = [
        project_generation_slot(slot, snapshots[slot["primary_requirement_id"]])
        for slot in generation_slots
    ]
    api_contract, ui_contract = contract_for_case_type(case_type)
    initial = estimate_serialized_value(
        prompts.generation_messages(
            case_type=case_type,
            batch_id=batch_key,
            generation_run_id="TGR-" + ("0" * 32),
            provider_mode="real",
            generation_slots=projected,
            max_cases=max_cases,
            api_contract=api_contract,
            ui_contract=ui_contract,
        )
    )
    recovery = estimate_serialized_value(
        prompts.generation_messages(
            case_type=case_type,
            batch_id=batch_key,
            generation_run_id="TGR-" + ("0" * 32),
            provider_mode="real",
            generation_slots=projected,
            max_cases=max_cases,
            recovery=True,
            validation_error="SCHEMA_VALIDATION:TEST_INTENT",
            api_contract=api_contract,
            ui_contract=ui_contract,
        )
    )
    input_estimate = max((initial, recovery), key=lambda x: x.budget_tokens)
    mock_intents = build_mock_intent_batch(case_type, generation_slots, snapshots, max_cases)
    output_estimate = estimate_serialized_value({"intents": mock_intents})
    recovery_value = {
        "slots": generation_slots,
        "snapshot_hashes": [
            snapshots[s["primary_requirement_id"]]["snapshot_hash"] for s in generation_slots
        ],
        "prompt_hash": prompts.content_hash,
        "prompt_version": TEST_GENERATION_PROMPT_VERSION,
        "schema_version": TEST_INTENT_SCHEMA_VERSION,
    }
    recovery_key = hashlib.sha256(
        json.dumps(
            recovery_value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    ).hexdigest()
    return BatchCapacity(
        batch_key,
        case_type,
        len(generation_slots),
        len(generation_slots),
        max_cases,
        max_tokens,
        input_estimate,
        output_estimate,
        input_budget_tokens,
        output_safe_token_limit(max_tokens, output_utilization_percent),
        recovery_key,
    )


def capacity_report_for_plan(
    plan: dict[str, Any],
    snapshots: dict[str, dict[str, Any]],
    prompts: TestGenerationPromptRegistry,
) -> list[dict[str, Any]]:
    return [
        analyze_batch_capacity(
            batch_key=b["batch_key"],
            case_type=b["case_type"],
            generation_slots=list(b["generation_slots"]),
            snapshots=snapshots,
            prompts=prompts,
            max_tokens=int(b["max_tokens"]),
            max_cases=int(b["max_cases"]),
            input_budget_tokens=(
                API_INPUT_BUDGET_TOKENS if b["case_type"] == "api" else DEFAULT_INPUT_BUDGET_TOKENS
            ),
        ).as_dict()
        for b in plan["batches"]
    ]
