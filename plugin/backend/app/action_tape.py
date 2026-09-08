from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, cast

from jsonschema import Draft202012Validator, FormatChecker

from plugin.backend.app.database import PROJECT_ROOT
from plugin.backend.app.ids import new_id

ACTION_TAPE_SCHEMA_VERSION = "action-tape-event@1.0.0"
ACTION_TAPE_WRITER_VERSION = "action-tape-writer@1.0.0"
ACTION_TAPE_MEDIA_TYPE = "application/x-ndjson"
REDACTED_VALUE = "[REDACTED]"


class ActionTapeError(Exception):
    pass


def _timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _canonical_line(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _validator() -> Draft202012Validator:
    schema_path = PROJECT_ROOT / "schemas" / "action-tape" / "v1" / "action_tape_event.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_action_tape(
    content: bytes,
    *,
    expected_run_id: str | None = None,
    expected_result_id: str | None = None,
) -> list[dict[str, Any]]:
    """Validate canonical Action Tape NDJSON without trusting database state."""
    if not content or not content.endswith(b"\n"):
        raise ActionTapeError("ACTION_TAPE_FORMAT_INVALID")
    raw_lines = content.splitlines()
    if not raw_lines or any(not line for line in raw_lines):
        raise ActionTapeError("ACTION_TAPE_FORMAT_INVALID")
    events: list[dict[str, Any]] = []
    validator = _validator()
    for raw_line in raw_lines:
        try:
            decoded = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ActionTapeError("ACTION_TAPE_JSON_INVALID") from error
        if not isinstance(decoded, dict):
            raise ActionTapeError("ACTION_TAPE_EVENT_INVALID")
        event = cast(dict[str, Any], decoded)
        if _canonical_line(event) != raw_line:
            raise ActionTapeError("ACTION_TAPE_NOT_CANONICAL")
        errors = sorted(validator.iter_errors(event), key=lambda item: list(item.path))
        if errors:
            raise ActionTapeError(f"ACTION_TAPE_SCHEMA_INVALID:{errors[0].json_path}")
        events.append(event)

    if [event["sequence"] for event in events] != list(range(1, len(events) + 1)):
        raise ActionTapeError("ACTION_TAPE_SEQUENCE_INVALID")
    if len({event["event_id"] for event in events}) != len(events):
        raise ActionTapeError("ACTION_TAPE_EVENT_ID_DUPLICATE")
    ownership = {
        (
            event["run_id"],
            event["result_id"],
            event["case_id"],
            event["case_version"],
            event["snapshot_id"],
            event["executor"],
        )
        for event in events
    }
    if len(ownership) != 1:
        raise ActionTapeError("ACTION_TAPE_OWNERSHIP_MISMATCH")
    if expected_run_id is not None and events[0]["run_id"] != expected_run_id:
        raise ActionTapeError("ACTION_TAPE_RUN_MISMATCH")
    if expected_result_id is not None and events[0]["result_id"] != expected_result_id:
        raise ActionTapeError("ACTION_TAPE_RESULT_MISMATCH")
    if any(
        event["value_sensitivity"] == "not_applicable" and event["value_display"] is not None
        for event in events
    ):
        raise ActionTapeError("ACTION_TAPE_VALUE_DISPLAY_INVALID")
    return deepcopy(events)


def action_tape_sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


class ActionTapeWriter:
    """Append schema-valid executor events and finalize immutable canonical NDJSON."""

    def __init__(
        self,
        *,
        run_id: str,
        result_id: str,
        case_id: str,
        case_version: int,
        snapshot_id: str,
        executor: str,
        clock: Callable[[], str] = _timestamp,
    ) -> None:
        self._identity = {
            "run_id": run_id,
            "result_id": result_id,
            "case_id": case_id,
            "case_version": case_version,
            "snapshot_id": snapshot_id,
            "executor": executor,
        }
        self._clock = clock
        self._events: list[dict[str, Any]] = []
        self._finalized: bytes | None = None

    def record(
        self,
        *,
        phase: str,
        action: str,
        resolved_target: dict[str, Any] | None,
        state_before_route: str | None,
        state_after_route: str | None,
        status: str = "completed",
        value_source: str | None = None,
        value_sensitivity: str = "not_applicable",
        value_display: str | None = None,
        evidence_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if self._finalized is not None:
            raise ActionTapeError("ACTION_TAPE_ALREADY_FINALIZED")
        if value_sensitivity == "sensitive":
            value_display = REDACTED_VALUE
        elif value_sensitivity == "not_applicable" and value_display is not None:
            raise ActionTapeError("ACTION_TAPE_VALUE_DISPLAY_INVALID")
        timestamp = self._clock()
        event = {
            "schema_version": ACTION_TAPE_SCHEMA_VERSION,
            "event_id": new_id("ATE"),
            "sequence": len(self._events) + 1,
            "timestamp": timestamp,
            **self._identity,
            "phase": phase,
            "action": action,
            "resolved_target": deepcopy(resolved_target),
            "value_source": value_source,
            "value_sensitivity": value_sensitivity,
            "value_display": value_display,
            "state_before": {"route": state_before_route, "captured_at": timestamp},
            "state_after": {"route": state_after_route, "captured_at": timestamp},
            "status": status,
            "evidence_artifact_ids": list(evidence_artifact_ids or []),
            "redaction_applied": True,
        }
        errors = sorted(_validator().iter_errors(event), key=lambda item: list(item.path))
        if errors:
            raise ActionTapeError(f"ACTION_TAPE_SCHEMA_INVALID:{errors[0].json_path}")
        self._events.append(event)
        return deepcopy(event)

    def finalize(self) -> bytes:
        if self._finalized is not None:
            return self._finalized
        if not self._events:
            raise ActionTapeError("ACTION_TAPE_EMPTY")
        content = b"\n".join(_canonical_line(event) for event in self._events) + b"\n"
        validate_action_tape(
            content,
            expected_run_id=str(self._identity["run_id"]),
            expected_result_id=str(self._identity["result_id"]),
        )
        self._finalized = content
        return content

    def events(self) -> list[dict[str, Any]]:
        if self._finalized is None:
            raise ActionTapeError("ACTION_TAPE_NOT_FINALIZED")
        return validate_action_tape(
            self._finalized,
            expected_run_id=str(self._identity["run_id"]),
            expected_result_id=str(self._identity["result_id"]),
        )
