from __future__ import annotations

from typing import Any


def build_mock_intent_batch(
    case_type: str,
    generation_slots: list[dict[str, Any]],
    snapshots: dict[str, dict[str, Any]],
    max_cases: int,
) -> list[dict[str, Any]]:
    return [
        _intent(slot, snapshots[slot["primary_requirement_id"]])
        for slot in generation_slots[:max_cases]
    ]


def _intent(slot: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    case_type = str(slot["case_type"])
    requirement = snapshot["requirement"]
    seeded = slot["primary_requirement_id"] == "REQ-BAT-002-6"
    expected = [str(requirement["description"])]
    data = []
    if seeded:
        data = [
            {
                "description": "Five-character username",
                "value": "z1234",
                "sensitive": False,
                "classification": None,
            },
            {
                "description": "Valid password",
                "value": "Test1234",
                "sensitive": True,
                "classification": "credential",
            },
        ]
        expected = [
            "Registration is rejected with HTTP 400 because the username "
            "has fewer than six characters."
            if case_type == "api"
            else "Registration fails with accessible minimum-length feedback."
        ]
    scenario = (
        str(slot["required_scenario_type"])
        if "required_scenario_type" in slot
        else "boundary"
        if seeded
        else _scenario(requirement, case_type)
    )
    return {
        "generation_slot_id": slot["generation_slot_id"],
        "title": f"{case_type.upper()} intent: {requirement['title']}"[:180],
        "objective": f"Verify {requirement['description']}",
        "priority": "P0" if seeded else "P1",
        "risk_level": requirement.get("risk_level", "medium"),
        "scenario_type": scenario,
        "preconditions": ["Use an isolated local test environment."],
        "test_data": data,
        "actions": [
            {
                "action": "exercise",
                "instruction": f"Exercise the observable behavior for {requirement['title']}.",
            }
        ],
        "expected_outcomes": expected,
        "cleanup_intent": {
            "required": False,
            "instructions": [],
        },
        "tags": list(dict.fromkeys([case_type, scenario, *requirement.get("tags", [])]))[:20],
        "type_intent": {"api": _api(seeded), "ui": _ui(seeded), "manual": _manual(requirement)}[
            case_type
        ],
    }


def _api(seeded: bool) -> dict[str, Any]:
    return {
        "method": "POST" if seeded else "GET",
        "path": "/api/auth/register" if seeded else "/api/auth/me",
        "request_body": {"username": "${data_001}", "password": "${data_002}"} if seeded else None,
        "session_semantics": "create_new" if seeded else "anonymous",
        "expected_status": 400 if seeded else 200,
        "response_expectations": ["Response status and safe JSON match the approved contract."],
        "security_expectations": ["No credential, token, cookie, hash, or stack trace is exposed."],
        "state_expectations": ["State changes only when the formal requirement permits it."],
        "setup_semantics": [],
    }


def _ui(seeded: bool) -> dict[str, Any]:
    route = "/register" if seeded else "/login"
    return {
        "route": route,
        "viewport_intent": "responsive-matrix",
        "locator_intents": [
            {"strategy": "label", "value": "Username"},
            {"strategy": "role", "value": "Submit"},
        ],
        "user_actions": ["fill:label:Username", "click:role:Submit"],
        "visible_assertions": ["Accessible requirement-aligned feedback is visible."],
        "url_assertions": [f"Navigation from {route} follows the approved requirement."],
        "session_assertions": ["Authentication state is not stored in browser storage."],
        "network_assertions": ["Only approved relative authentication APIs are contacted."],
        "evidence_intent": "deferred_no_capture",
    }


def _manual(requirement: dict[str, Any]) -> dict[str, Any]:
    return {
        "environment": "Local isolated SUT environment.",
        "tester_instructions": [
            "Observe the requirement-defined behavior without recording a verdict."
        ],
        "visual_checkpoints": ["Compare the behavior with the immutable requirement snapshot."],
        "accessibility_checkpoints": ["Check labels, focus, and understandable feedback."],
        "expected_observations": [str(requirement["description"])],
        "evidence_recommendation": "Capture redacted evidence when authorized.",
    }


def _scenario(requirement: dict[str, Any], case_type: str) -> str:
    value = str(requirement).lower()
    if case_type == "ui" and any(
        term in value for term in ("accessible", "error", "username", "login")
    ):
        return "accessibility"
    if requirement.get("requirement_type") in {"security", "privacy"}:
        return "security"
    return "positive"
