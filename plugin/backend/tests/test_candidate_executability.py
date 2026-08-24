from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from plugin.backend.app.candidate_executability import (
    compile_session_fixtures,
    validate_candidate_executability,
)


def _api_candidate() -> dict[str, Any]:
    return {
        "case_id": "TC-API-AUTH-REG-005",
        "case_type": "api",
        "objective": (
            "Verify the registration API rejects z1234 because usernames require at least six "
            "characters."
        ),
        "expected_results": ["Registration is rejected with HTTP 400."],
        "test_data": [
            {"name": "username", "value": "z1234", "sensitive": False, "classification": None},
            {
                "name": "password",
                "value": "Test1234",
                "sensitive": True,
                "classification": "credential",
            },
        ],
        "type_details": {
            "method": "POST",
            "path": "/api/auth/register",
            "session_handling": "new_session",
            "request": {"body": {"username": "z1234", "password": "Test1234"}},
            "expected_status": 400,
            "setup_requests": [],
            "cleanup_requests": [],
        },
    }


def test_seeded_defect_requires_requirement_oracle_not_defective_actual_behavior() -> None:
    candidate = _api_candidate()
    assert validate_candidate_executability(candidate) == []
    candidate["objective"] = "Verify z1234 is accepted with 201."
    codes = {finding.code for finding in validate_candidate_executability(candidate)}
    assert "OBJECTIVE_EXPECTED_STATUS_CONFLICT" in codes
    assert "BUG_AUTH_001_ORACLE_SEMANTICS_INVALID" in codes


def test_na_and_natural_language_database_operations_are_not_approvable() -> None:
    candidate = _api_candidate()
    candidate["type_details"]["setup_requests"] = ["N/A", "Delete the user from the database."]
    codes = {finding.code for finding in validate_candidate_executability(candidate)}
    assert "PLACEHOLDER_NA_FORBIDDEN" in codes
    assert "EXECUTION_OPERATION_UNSTRUCTURED" in codes


def test_expired_and_revoked_sessions_compile_to_bounded_fixtures() -> None:
    candidate = _api_candidate()
    candidate["type_details"]["session_handling"] = "expired_session"
    assert compile_session_fixtures(candidate) == [
        {"action": "create_authenticated_session", "state": "expired"}
    ]
    candidate["type_details"]["session_handling"] = "revoked_session"
    assert compile_session_fixtures(candidate) == [
        {"action": "create_authenticated_session", "state": "revoked"}
    ]


def test_nonexistent_api_and_ui_targets_are_rejected() -> None:
    api = _api_candidate()
    api["type_details"]["path"] = "/api/nonexistent"
    assert "API_TARGET_NOT_IN_CONTRACT" in {
        finding.code for finding in validate_candidate_executability(api)
    }
    ui = {
        "case_id": "TC-UI-X",
        "case_type": "ui",
        "test_data": [],
        "type_details": {
            "route": "/current-user",
            "locator_intents": [{"strategy": "role", "value": "button"}],
            "user_actions": ["Click the button."],
        },
    }
    codes = {finding.code for finding in validate_candidate_executability(ui)}
    assert {
        "UI_ROUTE_NOT_IN_CONTRACT",
        "UI_ROLE_LOCATOR_MISSING_ACCESSIBLE_NAME",
        "UI_ACTION_UNSTRUCTURED",
    } <= codes


def test_ui_action_contract_matches_executor_and_real_route_controls() -> None:
    candidate = {
        "case_id": "TC-UI-X",
        "case_type": "ui",
        "test_data": [{"name": "username", "value": "user", "sensitive": False}],
        "type_details": {
            "route": "/login",
            "locator_intents": [
                {"strategy": "label", "value": "Username"},
                {"strategy": "role", "value": "Sign in"},
            ],
            "user_actions": ["fill:label:Username", "click:role:Sign in"],
        },
    }
    assert validate_candidate_executability(candidate) == []
    candidate["type_details"]["user_actions"][0] = "navigate:route:/login"
    candidate["type_details"]["locator_intents"][1]["value"] = "Content"
    codes = {finding.code for finding in validate_candidate_executability(candidate)}
    assert "UI_ACTION_UNSTRUCTURED" in codes
    assert "UI_ROLE_LOCATOR_NOT_IN_ROUTE_CONTRACT" in codes


def test_non_seeded_api_case_is_not_rewritten_by_seeded_rules() -> None:
    candidate = deepcopy(_api_candidate())
    candidate["case_id"] = "TC-API-OTHER"
    candidate["objective"] = "Verify registration succeeds with valid input."
    candidate["expected_results"] = ["Registration succeeds with HTTP 201."]
    candidate["type_details"]["expected_status"] = 201
    candidate["type_details"]["request"]["body"]["username"] = "valid-user"
    assert validate_candidate_executability(candidate) == []


def test_real_failure_shapes_remain_rejected_without_guessing_or_deletion() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "phase6_executability_failures.json"
    fixtures = json.loads(fixture_path.read_text(encoding="utf-8"))
    observed: dict[tuple[str, str], set[str]] = {}
    for fixture in fixtures:
        findings = validate_candidate_executability(fixture["candidate"])
        codes = {finding.code for finding in findings}
        observed[(fixture["batch_key"], fixture["case_id"])] = codes
        assert set(fixture["expected_findings"]) <= codes
    assert observed[("TGB-API-005", "TC-API-REQ-BAT-002-9")] == {"EXECUTION_OPERATION_UNSTRUCTURED"}
    assert observed[("TGB-UI-001", "TC-UI-REQ-AUTH-001")] == {"UI_ROUTE_NOT_IN_CONTRACT"}
    assert observed[("TGB-UI-001", "TC-UI-REQ-BAT-002-10")] == {"UI_ROUTE_NOT_IN_CONTRACT"}
    assert observed[("TGB-UI-004", "TC-UI-REQ-LOGOUT-001")] == {"UI_ROUTE_NOT_IN_CONTRACT"}
