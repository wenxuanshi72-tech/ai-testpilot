from __future__ import annotations

import json

import pytest

from plugin.backend.app.action_tape import (
    ACTION_TAPE_MEDIA_TYPE,
    ACTION_TAPE_WRITER_VERSION,
    REDACTED_VALUE,
    ActionTapeError,
    ActionTapeWriter,
    action_tape_sha256,
    validate_action_tape,
)

RUN_ID = "RUN-" + "A" * 32
RESULT_ID = "RES-" + "B" * 32
SNAPSHOT_ID = "IES-" + "C" * 32


def _writer() -> ActionTapeWriter:
    return ActionTapeWriter(
        run_id=RUN_ID,
        result_id=RESULT_ID,
        case_id="TC-API-AUTH-REG-005",
        case_version=2,
        snapshot_id=SNAPSHOT_ID,
        executor="api",
        clock=lambda: "2026-09-08T10:00:00Z",
    )


def _content() -> bytes:
    writer = _writer()
    writer.record(
        phase="test",
        action="http_request",
        resolved_target={
            "strategy": "http",
            "role": None,
            "name": None,
            "path": "/api/auth/register",
            "method": "POST",
        },
        state_before_route=None,
        state_after_route=None,
        value_source="frozen_snapshot.request.body",
        value_sensitivity="sensitive",
        value_display="must-never-survive",
        evidence_artifact_ids=["ART-" + "D" * 32],
    )
    writer.record(
        phase="assertion",
        action="assert",
        resolved_target=None,
        state_before_route=None,
        state_after_route=None,
        status="failed",
    )
    return writer.finalize()


def test_writer_produces_canonical_redacted_action_tape() -> None:
    writer = _writer()
    writer.record(
        phase="test",
        action="http_request",
        resolved_target={"strategy": "http", "path": "/api/auth/register", "method": "POST"},
        state_before_route=None,
        state_after_route=None,
        value_source="frozen_snapshot.request.body",
        value_sensitivity="sensitive",
        value_display="Test1234",
    )
    content = writer.finalize()
    events = writer.events()

    assert ACTION_TAPE_WRITER_VERSION == "action-tape-writer@1.0.0"
    assert ACTION_TAPE_MEDIA_TYPE == "application/x-ndjson"
    assert b"Test1234" not in content
    assert events[0]["value_display"] == REDACTED_VALUE
    assert events[0]["sequence"] == 1
    assert validate_action_tape(content, expected_run_id=RUN_ID) == events
    assert len(action_tape_sha256(content)) == 64


def test_writer_is_fail_closed_after_finalization() -> None:
    writer = _writer()
    writer.record(
        phase="assertion",
        action="assert",
        resolved_target=None,
        state_before_route=None,
        state_after_route=None,
    )
    first = writer.finalize()
    assert writer.finalize() == first
    with pytest.raises(ActionTapeError, match="ALREADY_FINALIZED"):
        writer.record(
            phase="cleanup",
            action="discard_run_database",
            resolved_target=None,
            state_before_route=None,
            state_after_route=None,
        )


def test_validator_rejects_noncanonical_sequence_and_ownership_changes() -> None:
    content = _content()
    lines = content.splitlines()
    event = json.loads(lines[1])
    event["sequence"] = 3
    lines[1] = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(ActionTapeError, match="SEQUENCE_INVALID"):
        validate_action_tape(b"\n".join(lines) + b"\n")

    lines = content.splitlines()
    event = json.loads(lines[1])
    event["result_id"] = "RES-CHANGED"
    lines[1] = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(ActionTapeError, match="OWNERSHIP_MISMATCH"):
        validate_action_tape(b"\n".join(lines) + b"\n")


def test_validator_rejects_noncanonical_or_schema_invalid_content() -> None:
    content = _content()
    event = json.loads(content.splitlines()[0])
    noncanonical = json.dumps(event, ensure_ascii=False).encode() + b"\n"
    with pytest.raises(ActionTapeError, match="NOT_CANONICAL"):
        validate_action_tape(noncanonical)

    event["action"] = "execute_arbitrary_code"
    invalid = json.dumps(event, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(ActionTapeError, match="SCHEMA_INVALID"):
        validate_action_tape(invalid + b"\n")


def test_writer_rejects_display_for_non_value_action() -> None:
    with pytest.raises(ActionTapeError, match="VALUE_DISPLAY_INVALID"):
        _writer().record(
            phase="assertion",
            action="assert",
            resolved_target=None,
            state_before_route=None,
            state_after_route=None,
            value_display="unexpected",
        )
