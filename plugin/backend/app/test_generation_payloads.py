from __future__ import annotations

from typing import Any

PAYLOAD_PROJECTION_VERSION = "requirement-generation-projection@1.1.0"

API_CONTRACT = (
    "API: POST /api/auth/register=>201; username under six=>400; "
    "POST /api/auth/login=>200; GET /api/auth/me=>200 or 401; POST /api/auth/logout=>204. "
    "Relative paths, cookie session, safe JSON only."
)

UI_CONTRACT = (
    "UI: /register,/login,/profile; role|label|name|test-id|placeholder locators. "
    "Minimum-username failure is accessible and never navigates as success; cookie session only."
)


def project_requirement_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    requirement = snapshot["requirement"]
    strings: list[str] = []

    def intern(value: Any) -> int:
        text_value = str(value)
        if text_value not in strings:
            strings.append(text_value)
        return strings.index(text_value)

    projected = {
        "pv": PAYLOAD_PROJECTION_VERSION,
        "id": snapshot["requirement_id"],
        "v": snapshot["requirement_version"],
        "h": snapshot["snapshot_hash"],
        "b": snapshot["source_block_id"],
        "s": strings,
        "e": intern(snapshot["source_excerpt"]),
        "t": intern(requirement["title"]),
        "d": intern(requirement["description"]),
        "k": requirement["requirement_type"],
        "p": requirement.get("priority", "medium"),
        "r": requirement.get("risk_level", "medium"),
        "u": [intern(value) for value in requirement.get("business_rules", [])],
        "a": [intern(value) for value in requirement.get("acceptance_criteria", [])],
        "g": requirement.get("tags", []),
        "x": requirement.get("testability", "deterministic"),
    }
    _assert_semantics_preserved(snapshot, requirement, projected)
    return projected


def contract_for_case_type(case_type: str) -> tuple[str, str]:
    if case_type == "api":
        return API_CONTRACT, ""
    if case_type == "ui":
        return "", UI_CONTRACT
    if case_type == "manual":
        return "", ""
    raise ValueError("Unsupported case type")


def _assert_semantics_preserved(
    snapshot: dict[str, Any],
    requirement: dict[str, Any],
    projected: dict[str, Any],
) -> None:
    strings = projected["s"]
    restored = {
        "requirement_id": projected["id"],
        "requirement_version": projected["v"],
        "snapshot_hash": projected["h"],
        "source_block_id": projected["b"],
        "source_excerpt": strings[projected["e"]],
        "title": strings[projected["t"]],
        "description": strings[projected["d"]],
        "requirement_type": projected["k"],
        "priority": projected["p"],
        "risk_level": projected["r"],
        "business_rules": [strings[index] for index in projected["u"]],
        "acceptance_criteria": [strings[index] for index in projected["a"]],
        "tags": projected["g"],
        "testability": projected["x"],
    }
    expected = {
        "requirement_id": snapshot["requirement_id"],
        "requirement_version": snapshot["requirement_version"],
        "snapshot_hash": snapshot["snapshot_hash"],
        "source_block_id": snapshot["source_block_id"],
        "source_excerpt": snapshot["source_excerpt"],
        "title": requirement["title"],
        "description": requirement["description"],
        "requirement_type": requirement["requirement_type"],
        "priority": requirement.get("priority", "medium"),
        "risk_level": requirement.get("risk_level", "medium"),
        "business_rules": requirement.get("business_rules", []),
        "acceptance_criteria": requirement.get("acceptance_criteria", []),
        "tags": requirement.get("tags", []),
        "testability": requirement.get("testability", "deterministic"),
    }
    if restored != expected:
        raise ValueError("REQUIREMENT_PROJECTION_SEMANTICS_CHANGED")


def project_generation_slot(slot: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Project one immutable system-owned slot plus its formal requirement context."""
    projected = {
        "generation_slot_id": slot["generation_slot_id"],
        "primary_requirement_id": slot["primary_requirement_id"],
        "requirement_ids": list(slot["requirement_ids"]),
        "requirement": project_requirement_snapshot(snapshot),
    }
    if "required_scenario_type" in slot:
        projected["required_scenario_type"] = slot["required_scenario_type"]
    return projected
