from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

EXECUTABILITY_VALIDATOR_VERSION = "candidate-executability@1.0.0"
API_TARGETS = {
    ("GET", "/api/health"),
    ("POST", "/api/auth/register"),
    ("POST", "/api/auth/login"),
    ("GET", "/api/auth/me"),
    ("POST", "/api/auth/logout"),
}
UI_ROUTES = {"/", "/register", "/login", "/profile"}
SESSION_FIXTURES = {
    "none": (),
    "new_session": ({"action": "create_isolated_anonymous_session"},),
    "reuse_isolated_session": ({"action": "create_authenticated_session"},),
    "expired_session": ({"action": "create_authenticated_session", "state": "expired"},),
    "revoked_session": ({"action": "create_authenticated_session", "state": "revoked"},),
}
UI_ACTION_PATTERN = re.compile(
    r"^(goto|fill|click|select|check|uncheck|wait_for):[a-z0-9_-]+(?::[^:\r\n]{1,160}){0,2}$"
)


@dataclass(frozen=True)
class ExecutabilityFinding:
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


def validate_candidate_executability(candidate: dict[str, Any]) -> list[ExecutabilityFinding]:
    findings: list[ExecutabilityFinding] = []
    _find_na(candidate, "", findings)
    case_type = candidate.get("case_type")
    if case_type == "api":
        _validate_api(candidate, findings)
    elif case_type == "ui":
        _validate_ui(candidate, findings)
    elif case_type == "manual":
        _validate_manual(candidate, findings)
    else:
        findings.append(
            ExecutabilityFinding("CASE_TYPE_UNSUPPORTED", "/case_type", "Unsupported case type.")
        )
    _validate_sensitive_data(candidate, findings)
    return findings


def compile_session_fixtures(candidate: dict[str, Any]) -> list[dict[str, str]]:
    if candidate.get("case_type") != "api":
        return []
    session = candidate.get("type_details", {}).get("session_handling")
    fixtures = SESSION_FIXTURES.get(session)
    if fixtures is None:
        raise ValueError("SESSION_FIXTURE_UNSUPPORTED")
    return [dict(item) for item in fixtures]


def _validate_api(candidate: dict[str, Any], findings: list[ExecutabilityFinding]) -> None:
    details = candidate.get("type_details", {})
    target = (details.get("method"), details.get("path"))
    if target not in API_TARGETS:
        findings.append(
            ExecutabilityFinding(
                "API_TARGET_NOT_IN_CONTRACT",
                "/type_details",
                "Method and path must identify an implemented SUT API operation.",
            )
        )
    for field in ("setup_requests", "cleanup_requests"):
        for index, operation in enumerate(details.get(field, [])):
            path = f"/type_details/{field}/{index}"
            if not isinstance(operation, dict):
                findings.append(
                    ExecutabilityFinding(
                        "EXECUTION_OPERATION_UNSTRUCTURED",
                        path,
                        "Setup and cleanup operations must be structured allowlisted actions.",
                    )
                )
                continue
            operation_target = (operation.get("method"), operation.get("path"))
            if operation_target not in API_TARGETS:
                findings.append(
                    ExecutabilityFinding(
                        "SETUP_TARGET_NOT_IN_CONTRACT",
                        path,
                        "Structured setup must call an implemented SUT API operation.",
                    )
                )
    session = details.get("session_handling")
    if session not in SESSION_FIXTURES:
        findings.append(
            ExecutabilityFinding(
                "SESSION_FIXTURE_UNSUPPORTED",
                "/type_details/session_handling",
                "Session state has no deterministic fixture action.",
            )
        )
    objective = str(candidate.get("objective", "")).casefold()
    expected = " ".join(str(item) for item in candidate.get("expected_results", [])).casefold()
    status = details.get("expected_status")
    if status is not None and str(status) in objective and str(status) not in expected:
        findings.append(
            ExecutabilityFinding(
                "OBJECTIVE_EXPECTED_STATUS_CONFLICT",
                "/objective",
                "Objective status conflicts with the expected-result oracle.",
            )
        )
    if status == 400 and any(term in objective for term in ("accept", "success", "201")):
        findings.append(
            ExecutabilityFinding(
                "OBJECTIVE_EXPECTED_STATUS_CONFLICT",
                "/objective",
                "A rejection oracle cannot use an acceptance objective.",
            )
        )
    if candidate.get("case_id") == "TC-API-AUTH-REG-005":
        body = details.get("request", {}).get("body", {})
        if not (
            target == ("POST", "/api/auth/register")
            and status == 400
            and isinstance(body, dict)
            and body.get("username") == "z1234"
            and "reject" in objective
            and "six" in objective
        ):
            findings.append(
                ExecutabilityFinding(
                    "BUG_AUTH_001_ORACLE_SEMANTICS_INVALID",
                    "/objective",
                    "The seeded-defect objective and oracle must express the formal rejection.",
                )
            )


def _validate_ui(candidate: dict[str, Any], findings: list[ExecutabilityFinding]) -> None:
    details = candidate.get("type_details", {})
    if details.get("route") not in UI_ROUTES:
        findings.append(
            ExecutabilityFinding(
                "UI_ROUTE_NOT_IN_CONTRACT",
                "/type_details/route",
                "UI route must exist in the React SUT.",
            )
        )
    locators = details.get("locator_intents", [])
    actions = details.get("user_actions", [])
    if actions and not locators:
        findings.append(
            ExecutabilityFinding(
                "UI_ACTION_WITHOUT_LOCATOR",
                "/type_details/locator_intents",
                "UI actions require stable locator contracts.",
            )
        )
    for index, locator in enumerate(locators):
        if not isinstance(locator, dict) or locator.get("strategy") not in {
            "role",
            "label",
            "name",
            "test-id",
            "placeholder",
        }:
            findings.append(
                ExecutabilityFinding(
                    "UI_LOCATOR_UNSUPPORTED",
                    f"/type_details/locator_intents/{index}",
                    "UI locator strategy is not supported.",
                )
            )
        elif locator.get("strategy") == "role" and str(locator.get("value", "")).casefold() in {
            "button",
            "heading",
        }:
            findings.append(
                ExecutabilityFinding(
                    "UI_ROLE_LOCATOR_MISSING_ACCESSIBLE_NAME",
                    f"/type_details/locator_intents/{index}",
                    "Role-only locators require an accessible name.",
                )
            )
    for index, action in enumerate(actions):
        if not isinstance(action, str) or not UI_ACTION_PATTERN.fullmatch(action):
            findings.append(
                ExecutabilityFinding(
                    "UI_ACTION_UNSTRUCTURED",
                    f"/type_details/user_actions/{index}",
                    "UI actions must use the bounded action:locator:value grammar.",
                )
            )


def _validate_manual(candidate: dict[str, Any], findings: list[ExecutabilityFinding]) -> None:
    details = candidate.get("type_details", {})
    if not details.get("tester_instructions") or not details.get("expected_observable_result"):
        findings.append(
            ExecutabilityFinding(
                "MANUAL_PROTOCOL_INCOMPLETE",
                "/type_details",
                "Manual cases require instructions and an observable result.",
            )
        )


def _validate_sensitive_data(
    candidate: dict[str, Any], findings: list[ExecutabilityFinding]
) -> None:
    for index, item in enumerate(candidate.get("test_data", [])):
        text = f"{item.get('name', '')} {item.get('classification', '')}".casefold()
        if any(
            term in text for term in ("password", "credential", "token", "cookie")
        ) and not item.get("sensitive"):
            findings.append(
                ExecutabilityFinding(
                    "SENSITIVE_TEST_DATA_UNMARKED",
                    f"/test_data/{index}",
                    "Credential, token, and cookie data must be marked sensitive.",
                )
            )


def _find_na(value: Any, path: str, findings: list[ExecutabilityFinding]) -> None:
    if isinstance(value, str) and value.strip().casefold() == "n/a":
        findings.append(
            ExecutabilityFinding(
                "PLACEHOLDER_NA_FORBIDDEN",
                path or "/",
                "N/A placeholders are not executable protocol values.",
            )
        )
    elif isinstance(value, dict):
        for key, item in value.items():
            _find_na(item, f"{path}/{key}", findings)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _find_na(item, f"{path}/{index}", findings)
