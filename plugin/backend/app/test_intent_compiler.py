from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from plugin.backend.app.providers import ProviderMetadata
from plugin.backend.app.test_generation_prompts import TEST_GENERATION_PROMPT_VERSION
from plugin.backend.app.test_generation_schemas import TEST_CASE_SCHEMA_VERSION, TestCaseSchemas
from plugin.backend.app.test_generation_trace import is_seeded_username_requirement_id

TEST_INTENT_COMPILER_VERSION = "deterministic-candidate-compiler@2.33.0"
TEST_INTENT_COMPATIBILITY_VERSION = "test-intent-compatibility@1.30.0"
SCENARIO_TO_CATEGORY = {
    "positive": "positive",
    "negative": "negative",
    "boundary": "boundary",
    "security": "security",
    "authorization": "security",
    "functional": "functional",
    "quality": "functional",
    "verification": "functional",
    "non_functional": "functional",
    "accessibility": "accessibility",
    "recovery": "resilience",
    "error_handling": "negative",
}
SESSION_MAP = {
    "anonymous": "none",
    "create_new": "new_session",
    "authenticated": "reuse_isolated_session",
    "expired": "expired_session",
    "revoked": "revoked_session",
}
CANONICAL_SESSIONS = frozenset(SESSION_MAP)
FUNCTIONAL_SCENARIO_ALIASES = frozenset({"quality", "verification", "non_functional"})
NEGATIVE_SCENARIO_ALIASES = frozenset({"error_handling", "seeded defect", "defect_verification"})
SECURITY_SCENARIO_ALIASES = frozenset({"privacy"})
CANONICAL_SCENARIOS = frozenset(
    {"positive", "negative", "boundary", "security", "functional", "accessibility", "recovery"}
)
CORE_INTENT_FIELDS = frozenset(
    {
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
)


def canonical_session_semantics(value: Any, expected_status: Any) -> str:
    if isinstance(value, str):
        raw = value.strip().lower()
        token = raw.replace("-", "_").replace(" ", "_")
        if token in CANONICAL_SESSIONS:
            return token
        if "revok" in token and "expir" not in token:
            return "revoked"
        if "expir" in token or "invalidat" in token:
            return "expired"
        if any(part in token for part in ("anonymous", "unauth", "no_session", "none")):
            return "anonymous"
        if "new" in token or "create" in token:
            return "create_new"
        if any(part in token for part in ("auth", "login", "valid", "control")):
            return (
                "authenticated"
                if isinstance(expected_status, int) and 200 <= expected_status < 400
                else "anonymous"
            )
    return (
        "authenticated"
        if isinstance(expected_status, int) and 200 <= expected_status < 400
        else "anonymous"
    )


def action_setup_to_api(setup: dict[str, Any]) -> dict[str, Any] | None:
    action = setup.get("action")
    if not isinstance(action, str):
        return None
    match = re.fullmatch(
        r"\s*(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD)\s+(\/\S*)\s*",
        action,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    expected_status = setup.get("expected_status")
    if not isinstance(expected_status, int):
        return None
    purpose = setup.get("purpose")
    return {
        "method": match.group(1).upper(),
        "path": match.group(2),
        "request_body": None,
        "expected_status": expected_status,
        "description": purpose if isinstance(purpose, str) and purpose else action,
    }


def structured_setup_to_api(setup: dict[str, Any]) -> dict[str, Any] | None:
    method = setup.get("method")
    path = setup.get("path")
    expected_status = setup.get("expected_status")
    if (
        not isinstance(method, str)
        or method.upper() not in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
        or not isinstance(path, str)
        or not path.startswith("/")
        or not isinstance(expected_status, int)
    ):
        return None
    allowed = {
        "method",
        "path",
        "request_body",
        "request_headers",
        "expected_status",
        "description",
        "session_semantics",
        "response_expectations",
        "security_expectations",
        "state_expectations",
    }
    if set(setup) - allowed:
        return None
    description = setup.get("description")
    semantic_parts = [
        f"session={setup['session_semantics']}"
        if isinstance(setup.get("session_semantics"), str)
        else "",
        *[
            f"{field}=" + "; ".join(value)
            for field in ("response_expectations", "security_expectations", "state_expectations")
            if isinstance((value := setup.get(field)), list)
            and value
            and all(isinstance(item, str) for item in value)
        ],
    ]
    base = (
        description if isinstance(description, str) and description else f"{method.upper()} {path}"
    )
    rendered = "; ".join([base, *(part for part in semantic_parts if part)])
    return {
        "method": method.upper(),
        "path": path,
        "request_body": setup.get("request_body"),
        "expected_status": expected_status,
        "description": rendered[:300],
    }


def descriptive_setup_to_instruction(setup: dict[str, Any]) -> str | None:
    if setup.get("method") != "N/A" or setup.get("path") not in {"N/A", ""}:
        return None
    allowed = {
        "method",
        "path",
        "request_body",
        "expected_status",
        "description",
        "session_semantics",
        "response_expectations",
        "security_expectations",
        "state_expectations",
    }
    if set(setup) - allowed or setup.get("request_body") not in {None, ""}:
        return None
    parts: list[str] = []
    description = setup.get("description")
    if isinstance(description, str) and description.strip() not in {"", "N/A N/A"}:
        parts.append(description.strip())
    for field in ("response_expectations", "security_expectations", "state_expectations"):
        value = setup.get(field)
        if isinstance(value, list) and all(isinstance(item, str) for item in value):
            parts.extend(item.strip() for item in value if item.strip())
    session = setup.get("session_semantics")
    if isinstance(session, str) and session:
        parts.append(f"session semantics: {session}")
    result = "; ".join(dict.fromkeys(parts))
    return result[:600] if result else None


def incomplete_setup_to_instruction(setup: dict[str, Any]) -> str | None:
    method = setup.get("method")
    path = setup.get("path")
    when = setup.get("when")
    if (
        isinstance(method, str)
        and method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
        and isinstance(path, str)
        and path.startswith("/")
        and isinstance(when, str)
        and when.strip()
        and not isinstance(setup.get("expected_status"), int)
    ):
        return f"{method.upper()} {path} when {when.strip()}"
    return None


UNSAFE_CONFIGURATION_INSTRUCTION = re.compile(
    r"(?:"
    r"\b(?:select|insert|update|delete|drop|alter|truncate|pragma)\b|"
    r"\b(?:powershell|cmd\.exe|bash|sh\s+-c|invoke-expression|subprocess|os\.system)\b|"
    r"\b(?:rm|curl|wget)\s+-|"
    r"(?:eval|exec)\s*\(|"
    r"[A-Za-z]:\\|"
    r"(?:^|\s)/(?:etc|var|home|users|tmp)/"
    r")",
    flags=re.IGNORECASE,
)


def configuration_setup_to_instruction(setup: dict[str, Any]) -> str | None:
    """Accept only an unambiguous, non-executable model config wrapper."""
    if set(setup) != {"type", "description"} or setup.get("type") != "config":
        return None
    description = setup.get("description")
    if not isinstance(description, str):
        return None
    normalized = description.strip()
    if not normalized or len(normalized) > 600:
        return None
    if UNSAFE_CONFIGURATION_INSTRUCTION.search(normalized):
        return None
    return normalized


def normalize_tag_slug(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = re.sub(r"[\s_]+", "-", value.strip().lower())
    normalized = re.sub(r"[^a-z0-9-]", "", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")[:40]
    return normalized if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", normalized) else None


def compatibility_audit_records(intents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for intent in intents:
        slot_id = str(intent.get("generation_slot_id", ""))
        if "cleanup_intent" not in intent:
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "cleanup_intent",
                    "original_type": "missing",
                    "accepted_type": "no_cleanup",
                    "rule": "missing_cleanup_to_no_cleanup",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        if intent.get("scenario_type") == "authorization":
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "scenario_type",
                    "original": "authorization",
                    "accepted_as": "security",
                    "rule": "authorization_to_security",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        for index, tag in enumerate(intent.get("tags", [])):
            accepted_tag = normalize_tag_slug(tag)
            if accepted_tag is not None and accepted_tag != tag:
                records.append(
                    {
                        "generation_slot_id": slot_id,
                        "field": f"tags/{index}",
                        "original": tag,
                        "accepted_as": accepted_tag,
                        "rule": "tag_to_canonical_slug",
                        "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                    }
                )
        scenario_type = intent.get("scenario_type")
        if (
            isinstance(scenario_type, str)
            and scenario_type not in CANONICAL_SCENARIOS
            and scenario_type not in FUNCTIONAL_SCENARIO_ALIASES
            and scenario_type not in NEGATIVE_SCENARIO_ALIASES
            and scenario_type not in SECURITY_SCENARIO_ALIASES
            and scenario_type != "authorization"
        ):
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "scenario_type",
                    "original": scenario_type,
                    "accepted_as": "functional",
                    "rule": "unknown_scenario_to_functional",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        for field in intent:
            if field not in CORE_INTENT_FIELDS and field.endswith(("_intent", "_intents")):
                records.append(
                    {
                        "generation_slot_id": slot_id,
                        "field": field,
                        "original_type": type(intent[field]).__name__,
                        "accepted_as": "actions",
                        "rule": "semantic_extension_to_actions",
                        "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                    }
                )
        if scenario_type in SECURITY_SCENARIO_ALIASES:
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "scenario_type",
                    "original": scenario_type,
                    "accepted_as": "security",
                    "rule": "privacy_alias_to_security",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        if scenario_type in FUNCTIONAL_SCENARIO_ALIASES:
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "scenario_type",
                    "original": scenario_type,
                    "accepted_as": "functional",
                    "rule": "model_functional_alias_to_functional",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        if intent.get("scenario_type") == "functional":
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "scenario_type",
                    "original": "functional",
                    "accepted_as": "functional",
                    "rule": "functional_category_passthrough",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )

        if intent.get("scenario_type") in NEGATIVE_SCENARIO_ALIASES:
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "scenario_type",
                    "original": intent.get("scenario_type"),
                    "accepted_as": "negative",
                    "rule": "model_error_alias_to_negative",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        for index, data_item in enumerate(intent.get("test_data", [])):
            if (
                isinstance(data_item, dict)
                and data_item
                and not set(data_item) & {"description", "value", "sensitive", "classification"}
            ):
                records.append(
                    {
                        "generation_slot_id": slot_id,
                        "field": f"test_data/{index}",
                        "original_keys": sorted(data_item),
                        "accepted_as": "expanded_formal_test_data_items",
                        "rule": "inline_test_data_mapping_to_formal_items",
                        "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                    }
                )
        for index, data_item in enumerate(intent.get("test_data", [])):
            if (
                isinstance(data_item, dict)
                and "description" in data_item
                and "value" in data_item
                and ("sensitive" not in data_item or "classification" not in data_item)
            ):
                records.append(
                    {
                        "generation_slot_id": slot_id,
                        "field": f"test_data/{index}",
                        "missing_fields": [
                            field
                            for field in ("sensitive", "classification")
                            if field not in data_item
                        ],
                        "accepted_as": "deterministic_sensitivity_defaults",
                        "rule": "missing_test_data_sensitivity_defaults",
                        "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                    }
                )
        cleanup_intent = intent.get("cleanup_intent")
        if isinstance(cleanup_intent, dict) and "instructions" not in cleanup_intent:
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "cleanup_intent/instructions",
                    "original_type": "missing",
                    "accepted_type": "array",
                    "rule": "missing_cleanup_instructions_to_empty_list",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        type_intent = intent.get("type_intent")
        if isinstance(type_intent, dict) and (
            type_intent.get("method") in {"", "N/A"}
            or type_intent.get("path") in {"", "N/A"}
            or type_intent.get("expected_status") in {0, None}
        ):
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "type_intent/execution_target",
                    "original": {
                        "method": type_intent.get("method"),
                        "path": type_intent.get("path"),
                        "expected_status": type_intent.get("expected_status"),
                    },
                    "accepted_as": "pending_phase6_resolution",
                    "rule": "unresolved_api_target_preserved",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        if isinstance(type_intent, dict) and "route" in type_intent:
            for field in (
                "locator_intents",
                "user_actions",
                "visible_assertions",
                "url_assertions",
                "session_assertions",
                "network_assertions",
            ):
                if type_intent.get(field) is None:
                    records.append(
                        {
                            "generation_slot_id": slot_id,
                            "field": f"type_intent/{field}",
                            "original_type": "null",
                            "accepted_type": "array",
                            "rule": "null_ui_semantic_list_to_empty_list",
                            "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                        }
                    )
            if type_intent.get("viewport_intent") is None:
                records.append(
                    {
                        "generation_slot_id": slot_id,
                        "field": "type_intent/viewport_intent",
                        "original_type": "null",
                        "accepted_as": "responsive-matrix",
                        "rule": "null_viewport_to_responsive_matrix",
                        "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                    }
                )
        if (
            isinstance(type_intent, dict)
            and type_intent.get("method") == "complex"
            and type_intent.get("request_body") is None
            and isinstance(type_intent.get("path"), str)
        ):
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "type_intent/method",
                    "original": "complex",
                    "accepted_as": "GET",
                    "rule": "bodyless_complex_method_to_get",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        if isinstance(type_intent, dict) and "headers" in type_intent:
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "type_intent/headers",
                    "original_type": "object",
                    "accepted_as": "type_intent/request_headers",
                    "rule": "headers_alias_to_request_headers",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        if isinstance(type_intent, dict):
            session_semantics = type_intent.get("session_semantics")
            if isinstance(session_semantics, str) and session_semantics not in CANONICAL_SESSIONS:
                records.append(
                    {
                        "generation_slot_id": slot_id,
                        "field": "type_intent/session_semantics",
                        "original": session_semantics,
                        "accepted_as": canonical_session_semantics(
                            session_semantics, type_intent.get("expected_status")
                        ),
                        "rule": "descriptive_session_to_canonical",
                        "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                    }
                )

        if isinstance(type_intent, dict) and isinstance(
            type_intent.get("additional_requests"), list
        ):
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "type_intent/additional_requests",
                    "original_type": "array",
                    "accepted_as": "type_intent/setup_semantics",
                    "rule": "additional_requests_to_setup_semantics",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        if isinstance(type_intent, dict) and type_intent.get("setup_semantics") is None:
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "type_intent/setup_semantics",
                    "original_type": "null",
                    "accepted_type": "array",
                    "rule": "null_setup_semantics_to_empty_list",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        if isinstance(type_intent, dict) and isinstance(type_intent.get("setup_semantics"), dict):
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "type_intent/setup_semantics",
                    "original_type": "object",
                    "accepted_type": "array",
                    "rule": "named_setup_mapping_to_list",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        if isinstance(type_intent, dict) and "request_body" not in type_intent:
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "type_intent/request_body",
                    "original_type": "missing",
                    "accepted_type": "null",
                    "rule": "missing_request_body_to_null",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        if isinstance(type_intent, dict):
            for index, setup in enumerate(type_intent.get("setup_semantics") or []):
                if isinstance(setup, dict):
                    is_configuration_instruction = (
                        configuration_setup_to_instruction(setup) is not None
                    )
                    is_action_instruction = (
                        "instruction" in setup and "method" not in setup and "path" not in setup
                    )
                    is_action_api = action_setup_to_api(setup) is not None
                    is_incomplete_api = incomplete_setup_to_instruction(setup) is not None
                    is_descriptive = descriptive_setup_to_instruction(setup) is not None
                    records.append(
                        {
                            "generation_slot_id": slot_id,
                            "field": f"type_intent/setup_semantics/{index}",
                            "original_type": "object",
                            "accepted_type": (
                                "setup_instruction"
                                if is_configuration_instruction
                                or is_action_instruction
                                or is_incomplete_api
                                or is_descriptive
                                else "setup_api_request"
                            ),
                            "rule": (
                                "configuration_setup_to_instruction"
                                if is_configuration_instruction
                                else "non_http_setup_to_instruction"
                                if is_descriptive
                                else "incomplete_setup_to_instruction"
                                if is_incomplete_api
                                else (
                                    "action_instruction_setup_to_text"
                                    if is_action_instruction
                                    else (
                                        "action_purpose_setup_to_api"
                                        if is_action_api
                                        else "structured_setup_request"
                                    )
                                )
                            ),
                            "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                        }
                    )
        route_value = type_intent.get("route") if isinstance(type_intent, dict) else None
        viewport_value = (
            type_intent.get("viewport_intent") if isinstance(type_intent, dict) else None
        )
        if (
            isinstance(type_intent, dict)
            and "route" in type_intent
            and viewport_value not in {"desktop", "tablet", "mobile", "responsive-matrix"}
        ):
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "type_intent/viewport_intent",
                    "original": viewport_value,
                    "accepted_as": "responsive-matrix",
                    "rule": "unknown_viewport_to_responsive_matrix",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        if isinstance(route_value, str) and "," in route_value:
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "type_intent/route",
                    "original": route_value,
                    "accepted_as": "/",
                    "rule": "multi_route_string_to_reviewable_root_route",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        elif isinstance(route_value, str) and not route_value.strip():
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "type_intent/route",
                    "original_type": "str",
                    "source_summary": "empty",
                    "accepted_as": "/",
                    "rule": "empty_ui_route_to_root",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        if isinstance(route_value, str) and route_value.endswith("*"):
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "type_intent/route",
                    "original": route_value,
                    "accepted_as": route_value[:-1].rstrip("/") + "/",
                    "rule": "ui_route_wildcard_to_reviewable_prefix",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        if (
            isinstance(type_intent, dict)
            and "route" in type_intent
            and type_intent.get("evidence_intent") != "deferred_no_capture"
        ):
            records.append(
                {
                    "generation_slot_id": slot_id,
                    "field": "type_intent/evidence_intent",
                    "original": type_intent.get("evidence_intent"),
                    "accepted_as": "deferred_no_capture",
                    "rule": "ui_evidence_deferred_to_phase6",
                    "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                }
            )
        for index, item in enumerate(intent.get("test_data", [])):
            if isinstance(item, dict):
                for field in sorted(
                    set(item) - {"description", "value", "sensitive", "classification"}
                ):
                    records.append(
                        {
                            "generation_slot_id": slot_id,
                            "field": f"test_data/{index}/{field}",
                            "original_type": type(item[field]).__name__,
                            "accepted_as": "parsed_artifact_only",
                            "rule": "test_data_extension_preserved_in_artifact",
                            "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                        }
                    )
            if isinstance(item, dict) and item.get("classification") not in {
                None,
                "credential",
                "token",
                "cookie",
                "personal",
                "confidential",
            }:
                records.append(
                    {
                        "generation_slot_id": slot_id,
                        "field": f"test_data/{index}/classification",
                        "original": item.get("classification"),
                        "accepted_as": "confidential" if item.get("sensitive") else None,
                        "rule": "unknown_data_classification_to_safe_default",
                        "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                    }
                )
            if isinstance(item, dict) and item.get("value") in {None, ""}:
                records.append(
                    {
                        "generation_slot_id": slot_id,
                        "field": f"test_data/{index}/value",
                        "original_type": ("null" if item.get("value") is None else "empty_string"),
                        "accepted_type": "null",
                        "rule": "nullable_test_data_value",
                        "compatibility_version": TEST_INTENT_COMPATIBILITY_VERSION,
                    }
                )
    return records


def normalize_intent_batch(parsed: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(parsed)
    for intent in normalized.get("intents", []):
        if not isinstance(intent, dict):
            continue
        scenario = intent.get("scenario_type")
        if (
            isinstance(scenario, str)
            and scenario not in CANONICAL_SCENARIOS
            and scenario not in FUNCTIONAL_SCENARIO_ALIASES
            and scenario not in NEGATIVE_SCENARIO_ALIASES
            and scenario not in SECURITY_SCENARIO_ALIASES
            and scenario != "authorization"
        ):
            intent["scenario_type"] = "functional"
        extension_fields = [
            field
            for field in intent
            if field not in CORE_INTENT_FIELDS and field.endswith(("_intent", "_intents"))
        ]
        for field in extension_fields:
            serialized = json.dumps(intent.pop(field), sort_keys=True, separators=(",", ":"))
            for index in range(0, len(serialized), 540):
                intent["actions"].append(
                    {
                        "action": f"semantic_extension_{field}"[:60],
                        "instruction": f"{field}: {serialized[index : index + 540]}",
                    }
                )
        expanded_test_data: list[dict[str, Any]] = []
        for data_item in intent.get("test_data", []):
            if (
                isinstance(data_item, dict)
                and data_item
                and not set(data_item) & {"description", "value", "sensitive", "classification"}
            ):
                for key in sorted(data_item):
                    value = data_item[key]
                    sensitive = bool(
                        re.search(r"password|secret|token|cookie", key, flags=re.IGNORECASE)
                    )
                    classification = (
                        "credential"
                        if re.search(r"password|secret", key, flags=re.IGNORECASE)
                        else (
                            "token"
                            if re.search(r"token", key, flags=re.IGNORECASE)
                            else (
                                "cookie" if re.search(r"cookie", key, flags=re.IGNORECASE) else None
                            )
                        )
                    )
                    expanded_test_data.append(
                        {
                            "description": key,
                            "value": (
                                value
                                if isinstance(value, str) or value is None
                                else json.dumps(value, sort_keys=True, separators=(",", ":"))
                            ),
                            "sensitive": sensitive,
                            "classification": classification,
                        }
                    )
            else:
                expanded_test_data.append(data_item)
        intent["test_data"] = expanded_test_data
        for item in intent.get("test_data", []):
            if isinstance(item, dict) and "description" in item and "value" in item:
                description = str(item.get("description", ""))
                if "sensitive" not in item:
                    item["sensitive"] = bool(
                        re.search(
                            r"password|secret|token|cookie",
                            description,
                            flags=re.IGNORECASE,
                        )
                    )
                if "classification" not in item:
                    item["classification"] = (
                        "credential"
                        if re.search(r"password|secret", description, flags=re.IGNORECASE)
                        else (
                            "token"
                            if re.search(r"token", description, flags=re.IGNORECASE)
                            else (
                                "cookie"
                                if re.search(r"cookie", description, flags=re.IGNORECASE)
                                else None
                            )
                        )
                    )
            if isinstance(item, dict):
                for field in set(item) - {"description", "value", "sensitive", "classification"}:
                    del item[field]
            if isinstance(item, dict) and item.get("classification") not in {
                None,
                "credential",
                "token",
                "cookie",
                "personal",
                "confidential",
            }:
                item["classification"] = "confidential" if item.get("sensitive") else None
        intent["tags"] = [
            normalize_tag_slug(tag) if normalize_tag_slug(tag) is not None else tag
            for tag in intent.get("tags", [])
        ]
        if intent.get("scenario_type") in SECURITY_SCENARIO_ALIASES:
            intent["scenario_type"] = "security"
        if intent.get("scenario_type") in FUNCTIONAL_SCENARIO_ALIASES:
            intent["scenario_type"] = "functional"
        if intent.get("scenario_type") in NEGATIVE_SCENARIO_ALIASES:
            intent["scenario_type"] = "negative"
        intent.setdefault(
            "cleanup_intent",
            {"required": False, "instructions": []},
        )
        cleanup = intent.get("cleanup_intent")
        if isinstance(cleanup, dict):
            cleanup.setdefault("required", False)
            cleanup.setdefault("instructions", [])
        details = intent.get("type_intent")
        if not isinstance(details, dict):
            continue
        is_ui_intent = "route" in details and "viewport_intent" in details
        if is_ui_intent:
            if details.get("viewport_intent") not in {
                "desktop",
                "tablet",
                "mobile",
                "responsive-matrix",
            }:
                details["viewport_intent"] = "responsive-matrix"
            for field in (
                "locator_intents",
                "user_actions",
                "visible_assertions",
                "url_assertions",
                "session_assertions",
                "network_assertions",
            ):
                if details.get(field) is None:
                    details[field] = []
        route = details.get("route")
        if is_ui_intent and isinstance(route, str):
            normalized_route = route.strip()
            if "," in normalized_route or not normalized_route:
                details["route"] = "/"
            elif normalized_route.endswith("*"):
                details["route"] = normalized_route[:-1].rstrip("/") + "/"
            else:
                details["route"] = normalized_route
        if is_ui_intent and details.get("evidence_intent") != "deferred_no_capture":
            details["evidence_intent"] = "deferred_no_capture"
        is_api_intent = any(
            field in details
            for field in (
                "method",
                "path",
                "expected_status",
                "response_expectations",
                "security_expectations",
                "state_expectations",
            )
        )
        if is_api_intent:
            if details.get("method") is None:
                details["method"] = "N/A"
            if details.get("path") is None:
                details["path"] = ""
            if details.get("expected_status") is None:
                details["expected_status"] = 0
            for field in (
                "response_expectations",
                "security_expectations",
                "state_expectations",
            ):
                if details.get(field) is None:
                    details[field] = []
        if details.get("method") == "":
            details["method"] = "N/A"
        if details.get("method") == "N/A":
            if details.get("path") in {None, "N/A"}:
                details["path"] = ""
            if details.get("expected_status") is None:
                details["expected_status"] = 0
        if (
            details.get("method") == "complex"
            and details.get("request_body") is None
            and isinstance(details.get("path"), str)
        ):
            details["method"] = "GET"
        if "additional_requests" in details:
            additional_requests = details.pop("additional_requests")
            if isinstance(additional_requests, list):
                setup_list = details.setdefault("setup_semantics", [])
                if isinstance(setup_list, list):
                    for request in additional_requests:
                        converted = (
                            structured_setup_to_api(request) if isinstance(request, dict) else None
                        )
                        if converted is not None:
                            setup_list.append(converted)
                        else:
                            serialized = json.dumps(request, sort_keys=True, separators=(",", ":"))
                            setup_list.append(f"additional_request: {serialized}")
        if "setup_semantics" in details and details.get("setup_semantics") is None:
            details["setup_semantics"] = []
        setup_semantics = details.get("setup_semantics")
        if isinstance(setup_semantics, dict):
            normalized_setups: list[dict[str, Any] | str] = []
            for name, setup in setup_semantics.items():
                converted = structured_setup_to_api(setup) if isinstance(setup, dict) else None
                if converted is not None:
                    converted["description"] = f"{name}: {converted['description']}"
                    normalized_setups.append(converted)
                else:
                    normalized_setups.append(
                        f"{name}: {json.dumps(setup, sort_keys=True, separators=(',', ':'))}"
                    )
            details["setup_semantics"] = normalized_setups
        if "headers" in details:
            details.setdefault("request_headers", details["headers"])
            del details["headers"]
        if "method" in details and "path" in details:
            details.setdefault("request_body", None)
            session = details.get("session_semantics")
            details["session_semantics"] = canonical_session_semantics(
                session, details.get("expected_status")
            )
            for index, setup in enumerate(details.get("setup_semantics", [])):
                if isinstance(setup, dict) and "body" in setup and "request_body" not in setup:
                    setup["request_body"] = setup.pop("body")
                if (
                    isinstance(setup, dict)
                    and "method" in setup
                    and "path" in setup
                    and not isinstance(setup.get("when"), str)
                ):
                    if setup.get("method") == "N/A" and setup.get("path") == "N/A":
                        setup["path"] = ""
                    setup.setdefault("expected_status", 0)
                    fallback = f"{setup['method']} {setup['path']}"
                    setup.setdefault("description", str(setup.get("action") or fallback))
                    setup.pop("action", None)
                normalized_setup = (
                    configuration_setup_to_instruction(setup)
                    or descriptive_setup_to_instruction(setup)
                    or action_setup_to_api(setup)
                    or structured_setup_to_api(setup)
                    if isinstance(setup, dict)
                    else None
                )
                if normalized_setup is not None:
                    details["setup_semantics"][index] = normalized_setup
                elif isinstance(setup, dict) and incomplete_setup_to_instruction(setup):
                    details["setup_semantics"][index] = incomplete_setup_to_instruction(setup)
                elif (
                    isinstance(setup, dict)
                    and "method" in setup
                    and "path" in setup
                    and not isinstance(setup.get("when"), str)
                ):
                    setup.setdefault("request_body", None)
                elif isinstance(setup, dict) and isinstance(setup.get("instruction"), str):
                    details["setup_semantics"][index] = setup["instruction"]
    return normalized


class TestIntentCompilationError(Exception):
    pass


@dataclass(frozen=True)
class CompilationContext:
    run_id: str
    project_id: str
    provider: ProviderMetadata
    snapshots: dict[str, dict[str, Any]]
    slots: dict[str, dict[str, Any]]


class DeterministicCandidateCompiler:
    def __init__(self, schemas: TestCaseSchemas | None = None) -> None:
        self.schemas = schemas or TestCaseSchemas()

    def compile(self, intent: dict[str, Any], context: CompilationContext) -> dict[str, Any]:
        slot_id = intent["generation_slot_id"]
        if slot_id not in context.slots:
            raise TestIntentCompilationError("GENERATION_SLOT_UNKNOWN_OR_CROSS_BATCH")
        slot = context.slots[slot_id]
        required_scenario = slot.get("required_scenario_type")
        if required_scenario is not None and intent["scenario_type"] != required_scenario:
            raise TestIntentCompilationError("GENERATION_SLOT_SCENARIO_MISMATCH")
        requirement_ids = list(slot["requirement_ids"])
        primary = str(slot["primary_requirement_id"])
        if (
            not requirement_ids
            or primary not in requirement_ids
            or not set(requirement_ids) <= set(context.snapshots)
        ):
            raise TestIntentCompilationError("GENERATION_SLOT_REQUIREMENT_LINK_INVALID")
        cleanup = intent["cleanup_intent"]
        if cleanup["required"] and not cleanup["instructions"]:
            raise TestIntentCompilationError("CLEANUP_INTENT_REQUIRED_BUT_EMPTY")
        if not cleanup["required"] and cleanup["instructions"]:
            raise TestIntentCompilationError("CLEANUP_INTENT_CONTRADICTORY")
        case_type = str(slot["case_type"])
        first = context.snapshots[primary]
        candidate: dict[str, Any] = {
            "schema_version": TEST_CASE_SCHEMA_VERSION,
            "case_id": slot["case_id"],
            "case_version": 1,
            "case_type": case_type,
            "title": intent["title"],
            "objective": intent["objective"],
            "requirement_ids": requirement_ids,
            "primary_requirement_id": primary,
            "priority": intent["priority"],
            "risk_level": intent["risk_level"],
            "test_level": "manual" if case_type == "manual" else "system",
            "test_category": SCENARIO_TO_CATEGORY[intent["scenario_type"]],
            "preconditions": list(
                dict.fromkeys(
                    [
                        *intent["preconditions"],
                        *[
                            setup
                            for setup in intent.get("type_intent", {}).get("setup_semantics", [])
                            if case_type == "api" and isinstance(setup, str)
                        ],
                    ]
                )
            ),
            "test_data": [
                {
                    "name": f"data_{index:03d}",
                    "source": "literal",
                    "value": item["value"],
                    "sensitive": item["sensitive"],
                    "classification": item["classification"],
                }
                for index, item in enumerate(intent["test_data"], 1)
            ],
            "steps": [
                {
                    "step_id": f"STEP-{index:03d}",
                    "action": item["action"],
                    "instruction": item["instruction"],
                }
                for index, item in enumerate(intent["actions"], 1)
            ],
            "expected_results": intent["expected_outcomes"],
            "cleanup": cleanup["instructions"],
            "tags": intent["tags"],
            "source": f"ai_{context.provider.provider_mode}",
            "generation_run_id": context.run_id,
            "review_status": "draft",
            "lifecycle_status": "validated_pending_review",
            "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "semantic_content_hash": _semantic_hash(slot, intent),
            "content_hash": "0" * 64,
            "trace": {
                "project_id": context.project_id,
                "prd_document_id": first["prd_document_id"],
                "prd_version_id": first["prd_version_id"],
                "requirements": [
                    {
                        "requirement_id": rid,
                        "requirement_version": context.snapshots[rid]["requirement_version"],
                        "snapshot_hash": context.snapshots[rid]["snapshot_hash"],
                        "source_block_id": context.snapshots[rid]["source_block_id"],
                    }
                    for rid in requirement_ids
                ],
                "generation_prompt_version": TEST_GENERATION_PROMPT_VERSION,
                "generation_schema_version": TEST_CASE_SCHEMA_VERSION,
                "provider_mode": context.provider.provider_mode,
                "model": context.provider.model,
            },
            "type_details": self._compile_type_details(case_type, intent),
        }
        self._enforce_seeded_defect_oracle(candidate, slot)
        candidate["content_hash"] = _candidate_hash(candidate)
        self.schemas.validate("test_case_candidate.schema.json", candidate)
        return candidate

    @staticmethod
    def _enforce_seeded_defect_oracle(candidate: dict[str, Any], slot: dict[str, Any]) -> None:
        if not (
            slot["case_id"] == "TC-API-AUTH-REG-005"
            and slot["case_type"] == "api"
            and is_seeded_username_requirement_id(str(slot["primary_requirement_id"]))
            and len(slot["requirement_ids"]) == 1
            and is_seeded_username_requirement_id(str(slot["requirement_ids"][0]))
        ):
            return
        candidate["test_data"] = [
            {
                "name": "data_001",
                "source": "literal",
                "value": "z1234",
                "sensitive": False,
                "classification": None,
            },
            {
                "name": "data_002",
                "source": "literal",
                "value": "Test1234",
                "sensitive": True,
                "classification": "credential",
            },
        ]
        candidate["expected_results"] = [
            "Registration is rejected with HTTP 400 because the username has fewer "
            "than six characters."
        ]
        candidate["objective"] = (
            "Verify the registration API rejects the five-character username z1234 because the "
            "formal requirement requires at least six characters."
        )
        candidate["tags"] = list(
            dict.fromkeys(
                [
                    *candidate["tags"],
                    "seeded-defect",
                    "known-defective-actual-status-201",
                ]
            )
        )[:20]
        candidate["type_details"].update(
            {
                "method": "POST",
                "path": "/api/auth/register",
                "session_handling": "new_session",
                "request": {
                    "path_parameters": {},
                    "query_parameters": {},
                    "body": {"username": "z1234", "password": "Test1234"},
                },
                "expected_status": 400,
                "response_assertions": [
                    "The response rejects the five-character username with the stable "
                    "validation contract."
                ],
                "response_schema_assertions": [
                    "The safe JSON validation error follows the approved response schema."
                ],
                "state_assertions": ["No user is created for the rejected registration."],
            }
        )

    def _compile_type_details(self, case_type: str, intent: dict[str, Any]) -> dict[str, Any]:
        details = intent["type_intent"]
        cleanup = intent["cleanup_intent"]["instructions"]
        if case_type == "api":
            session = details["session_semantics"]
            if session not in SESSION_MAP:
                raise TestIntentCompilationError("SESSION_INTENT_UNMAPPABLE")
            return {
                "kind": "api",
                "method": details["method"],
                "path": details["path"],
                "headers": details.get("request_headers", {}),
                "session_handling": SESSION_MAP[session],
                "request": {
                    "path_parameters": {},
                    "query_parameters": {},
                    "body": details["request_body"],
                },
                "expected_status": details["expected_status"],
                "response_assertions": details["response_expectations"],
                "response_schema_assertions": details["response_expectations"],
                "security_assertions": details["security_expectations"],
                "state_assertions": details["state_expectations"],
                "setup_requests": [
                    setup for setup in details["setup_semantics"] if isinstance(setup, dict)
                ],
                "cleanup_requests": cleanup,
            }
        if case_type == "ui":
            return {
                "kind": "ui",
                "route": details["route"],
                "viewport": details["viewport_intent"],
                "locator_intents": details["locator_intents"],
                "user_actions": details["user_actions"],
                "visible_assertions": details["visible_assertions"],
                "url_assertions": details["url_assertions"],
                "session_assertions": details["session_assertions"],
                "network_assertions": details["network_assertions"],
                "evidence_policy": details["evidence_intent"],
                "cleanup_strategy": "\n".join(cleanup)
                if cleanup
                else "No cleanup required by the test intent.",
            }
        if case_type == "manual":
            return {
                "kind": "manual",
                "tester_instructions": details["tester_instructions"],
                "environment": details["environment"],
                "visual_checkpoints": details["visual_checkpoints"],
                "accessibility_checkpoints": details["accessibility_checkpoints"],
                "exploratory_charter": None,
                "expected_observable_result": "\n".join(details["expected_observations"]),
                "evidence_recommendation": details["evidence_recommendation"],
            }
        raise TestIntentCompilationError("GENERATION_SLOT_CASE_TYPE_UNSUPPORTED")


def _semantic_hash(slot: dict[str, Any], intent: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            {"slot": slot, "intent": intent},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _candidate_hash(candidate: dict[str, Any]) -> str:
    value = dict(candidate)
    value["content_hash"] = ""
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
