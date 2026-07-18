from __future__ import annotations

import json
import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

TEST_PASSWORD = "Test1234"
EVIDENCE_RECORDS: list[dict[str, Any]] = []


@pytest.fixture
def api_client() -> Iterator[httpx.Client]:
    base_url = os.environ.get("PHASE3_BASE_URL", "http://127.0.0.1:5001")
    with httpx.Client(
        base_url=base_url,
        timeout=3.0,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        yield client


def unique_username(prefix: str = "api") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def registration_payload(username: str) -> dict[str, str]:
    return {
        "username": username,
        "password": TEST_PASSWORD,
        "password_confirmation": TEST_PASSWORD,
    }


def response_json(response: httpx.Response) -> dict[str, Any]:
    payload = response.json()
    assert isinstance(payload, dict)
    return payload


def record_evidence(
    *,
    case_id: str,
    response: httpx.Response,
    expected_status: int,
    requirement_ids: list[str],
    bug_id: str | None = None,
    classification: str | None = None,
) -> None:
    actual_status = response.status_code
    result = "PASS" if actual_status == expected_status else "FAIL"
    if classification == "known_seeded_product_defect" and actual_status != expected_status:
        result = "XFAIL"
    EVIDENCE_RECORDS.append(
        {
            "case_id": case_id,
            "method": response.request.method,
            "path": response.request.url.path,
            "status": actual_status,
            "expected_status": expected_status,
            "result": result,
            "request_id": response.headers.get("X-Request-ID"),
            "duration_ms": round(response.elapsed.total_seconds() * 1000, 3),
            "linked_requirement_ids": requirement_ids,
            "linked_bug_id": bug_id,
            "classification": classification,
        }
    )


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del session, exitstatus
    evidence_value = os.environ.get("PHASE3_EVIDENCE_DIR")
    if not evidence_value:
        return
    evidence_dir = Path(evidence_value).resolve()
    evidence_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = evidence_dir / "http_evidence.json"
    evidence_path.write_text(
        json.dumps(
            {"schema_version": "1.0", "records": EVIDENCE_RECORDS},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
