from __future__ import annotations

from typing import Any

from plugin.backend.app.candidate_executability import validate_candidate_executability

MVP_BASELINE_POLICY_VERSION = "portfolio-mvp-baseline@1.0.0"
MVP_MIN_AUTOMATED = 8
MVP_MAX_AUTOMATED = 12
MVP_PREFERRED_CASE_IDS = frozenset(
    {
        "TC-API-AUTH-REG-005",
        "TC-API-REQ-AUTH-001",
        "TC-API-REQ-BAT-002-5",
        "TC-API-REQ-LOGIN-001",
        "TC-API-REQ-LOGOUT-001",
        "TC-API-REQ-REG-003",
        "TC-UI-AUTH-REG-005",
        "TC-UI-REQ-LOGIN-001",
        "TC-UI-REQ-LOGOUT-001",
        "TC-UI-REQ-REG-002",
    }
)
MVP_REQUIRED_CASE_IDS = frozenset({"TC-API-AUTH-REG-005", "TC-UI-AUTH-REG-005"})
DISPOSITIONS = frozenset({"automated", "manual", "deferred"})


def propose_mvp_classification(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    payloads = [item.get("candidate", item) for item in candidates]
    findings_by_case = {
        str(payload["case_id"]): validate_candidate_executability(payload) for payload in payloads
    }
    automated = {
        str(payload["case_id"])
        for payload in payloads
        if str(payload["case_id"]) in MVP_PREFERRED_CASE_IDS
    }
    fallback = sorted(
        (
            payload
            for payload in payloads
            if payload["case_type"] in {"api", "ui"} and str(payload["case_id"]) not in automated
        ),
        key=lambda payload: (
            bool(findings_by_case[str(payload["case_id"])]),
            0 if payload["case_type"] == "api" else 1,
            str(payload["case_id"]),
        ),
    )
    automated.update(str(payload["case_id"]) for payload in fallback[: max(0, 10 - len(automated))])
    rows: list[dict[str, Any]] = []
    counts = {item: 0 for item in DISPOSITIONS}
    for item in candidates:
        payload = item.get("candidate", item)
        case_id = str(payload["case_id"])
        findings = findings_by_case[case_id]
        if case_id in automated:
            disposition = "automated"
            reason = "Selected for the portfolio MVP end-to-end authentication baseline."
        elif payload["case_type"] == "manual":
            disposition = "manual"
            reason = "Retained as reviewed manual test design; never sent to an automated executor."
        else:
            disposition = "deferred"
            reason = "Outside the 8-12 case MVP automation scope; retained as test-design evidence."
        counts[disposition] += 1
        rows.append(
            {
                "case_id": case_id,
                "case_type": payload["case_type"],
                "proposed_disposition": disposition,
                "disposition_reason": reason,
                "executability_status": "passed" if not findings else "revision_required",
                "findings": [finding.as_dict() for finding in findings],
            }
        )
    automated = {item["case_id"] for item in rows if item["proposed_disposition"] == "automated"}
    return {
        "policy_version": MVP_BASELINE_POLICY_VERSION,
        "candidate_count": len(rows),
        "counts": counts,
        "required_automated_case_ids": sorted(MVP_REQUIRED_CASE_IDS),
        "preferred_automated_case_ids": sorted(MVP_PREFERRED_CASE_IDS),
        "required_cases_selected": MVP_REQUIRED_CASE_IDS <= automated,
        "automated_count_within_policy": MVP_MIN_AUTOMATED <= len(automated) <= MVP_MAX_AUTOMATED,
        "ready_for_human_classification": len(rows) == 46,
        "ready_to_freeze": all(
            item["executability_status"] == "passed"
            for item in rows
            if item["proposed_disposition"] == "automated"
        ),
        "candidates": rows,
    }
