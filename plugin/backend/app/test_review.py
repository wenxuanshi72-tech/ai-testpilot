from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any

from jsonschema import ValidationError as JsonSchemaError
from sqlalchemy import text

from plugin.backend.app.candidate_executability import (
    EXECUTABILITY_VALIDATOR_VERSION,
    compile_session_fixtures,
    validate_candidate_executability,
)
from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.ids import new_id
from plugin.backend.app.test_review_schemas import ReviewSchemas

PROTOCOL_VERSION = "unified-test-protocol@1.0.0"
REVIEW_WORKFLOW_VERSION = "test-case-review@1.0.0"
SNAPSHOT_SCHEMA_VERSION = "execution-snapshot@1.0.0"
DECISIONS = {"approve", "reject", "request_changes"}
ACTOR_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{1,79}$")


class TestReviewError(Exception):
    pass


@dataclass(frozen=True)
class FreezeResult:
    baseline_id: str
    baseline_version: int
    baseline_hash: str
    snapshot_count: int
    status: str


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _candidate_hash(payload: dict[str, Any]) -> str:
    candidate = dict(payload)
    candidate["content_hash"] = ""
    return _hash(candidate)


class TestReviewService:
    def __init__(self, database: PluginDatabase, schemas: ReviewSchemas | None = None) -> None:
        self.database = database
        self.schemas = schemas or ReviewSchemas()

    def collection(self, run_id: str) -> dict[str, Any]:
        run = self._ready_run(run_id)
        rows = self.database.fetch_all(
            "SELECT c.test_case_candidate_id,c.case_id,c.case_version,c.case_type,"
            "c.content_hash,c.payload_json,r.test_case_review_id,r.reviewer_id,r.decision,"
            "r.comment,r.created_at AS reviewed_at FROM test_case_candidates c "
            "LEFT JOIN test_case_reviews r ON r.test_case_review_id=("
            "SELECT r2.test_case_review_id FROM test_case_reviews r2 "
            "WHERE r2.test_case_candidate_id=c.test_case_candidate_id "
            "ORDER BY r2.rowid DESC LIMIT 1) "
            "WHERE c.test_generation_run_id=:run ORDER BY c.case_type,c.case_id",
            {"run": run_id},
        )
        self._verify_collection(run, rows)
        return {
            "generation_run_id": run_id,
            "collection_version": run["collection_version"],
            "collection_hash": run["collection_hash"],
            "candidate_count": len(rows),
            "workflow_version": REVIEW_WORKFLOW_VERSION,
            "candidates": [
                {key: value for key, value in row.items() if key != "payload_json"}
                | {"candidate": json.loads(str(row["payload_json"]))}
                for row in rows
            ],
        }

    def review(
        self,
        run_id: str,
        case_id: str,
        *,
        reviewer_id: str,
        decision: str,
        comment: str,
        expected_content_hash: str,
    ) -> dict[str, Any]:
        self._validate_actor(reviewer_id)
        try:
            self.schemas.validate_review(
                {
                    "schema_version": REVIEW_WORKFLOW_VERSION,
                    "reviewer_id": reviewer_id,
                    "decision": decision,
                    "comment": comment,
                    "expected_content_hash": expected_content_hash,
                }
            )
        except JsonSchemaError as error:
            raise TestReviewError("REVIEW_PAYLOAD_SCHEMA_INVALID") from error
        if decision not in DECISIONS:
            raise TestReviewError("REVIEW_DECISION_INVALID")
        if not 1 <= len(comment.strip()) <= 1000:
            raise TestReviewError("REVIEW_COMMENT_REQUIRED")
        run = self._ready_run(run_id)
        candidate = self.database.fetch_one(
            "SELECT * FROM test_case_candidates WHERE test_generation_run_id=:run "
            "AND case_id=:case",
            {"run": run_id, "case": case_id},
        )
        if not candidate:
            raise TestReviewError("CANDIDATE_NOT_FOUND")
        if candidate["content_hash"] != expected_content_hash:
            raise TestReviewError("CANDIDATE_HASH_CHANGED")
        payload = json.loads(str(candidate["payload_json"]))
        if _candidate_hash(payload) != candidate["content_hash"]:
            raise TestReviewError("CANDIDATE_INTEGRITY_INVALID")
        already_approved = self.database.fetch_one(
            "SELECT approved_test_case_version_id FROM approved_test_case_versions "
            "WHERE test_case_candidate_id=:candidate",
            {"candidate": candidate["test_case_candidate_id"]},
        )
        if already_approved and decision == "approve":
            raise TestReviewError("APPROVED_VERSION_IS_IMMUTABLE")
        findings = validate_candidate_executability(payload)
        if decision == "approve" and findings:
            raise TestReviewError("CANDIDATE_NOT_EXECUTABLE")
        review_id = new_id("TCR")
        approved_id: str | None = None
        approved_hash: str | None = None
        with self.database.transaction() as connection:
            connection.execute(
                text(
                    "INSERT INTO test_case_reviews(test_case_review_id,test_generation_run_id,"
                    "test_case_candidate_id,reviewer_id,decision,comment,candidate_content_hash) "
                    "VALUES (:id,:run,:candidate,:reviewer,:decision,:comment,:hash)"
                ),
                {
                    "id": review_id,
                    "run": run_id,
                    "candidate": candidate["test_case_candidate_id"],
                    "reviewer": reviewer_id,
                    "decision": decision,
                    "comment": comment.strip(),
                    "hash": expected_content_hash,
                },
            )
            if decision == "approve":
                approved_payload = dict(payload)
                approved_payload["review_status"] = "approved"
                approved_payload["approved_version"] = int(candidate["case_version"])
                approved_hash = _hash(approved_payload)
                approved_id = new_id("ATCV")
                connection.execute(
                    text(
                        "INSERT INTO approved_test_case_versions("
                        "approved_test_case_version_id,test_case_candidate_id,test_case_review_id,"
                        "case_id,case_version,schema_version,payload_json,content_hash,"
                        "approved_by) VALUES "
                        "(:id,:candidate,:review,:case,:version,:schema,:payload,:hash,:actor)"
                    ),
                    {
                        "id": approved_id,
                        "candidate": candidate["test_case_candidate_id"],
                        "review": review_id,
                        "case": case_id,
                        "version": candidate["case_version"],
                        "schema": payload["schema_version"],
                        "payload": _canonical(approved_payload),
                        "hash": approved_hash,
                        "actor": reviewer_id,
                    },
                )
            self._audit(
                connection,
                run_id,
                str(candidate["test_case_candidate_id"]),
                None,
                "candidate_reviewed",
                reviewer_id,
                {
                    "review_id": review_id,
                    "decision": decision,
                    "content_hash": expected_content_hash,
                },
            )
        return {
            "review_id": review_id,
            "decision": decision,
            "approved_test_case_version_id": approved_id,
            "approved_content_hash": approved_hash,
            "collection_hash": run["collection_hash"],
        }

    def executability_report(self, run_id: str) -> dict[str, Any]:
        collection = self.collection(run_id)
        results: list[dict[str, Any]] = []
        failed = 0
        for item in collection["candidates"]:
            findings = validate_candidate_executability(item["candidate"])
            if findings:
                failed += 1
            results.append(
                {
                    "case_id": item["case_id"],
                    "case_type": item["case_type"],
                    "status": "failed" if findings else "passed",
                    "findings": [finding.as_dict() for finding in findings],
                }
            )
        return {
            "generation_run_id": run_id,
            "validator_version": EXECUTABILITY_VALIDATOR_VERSION,
            "candidate_count": len(results),
            "passed_count": len(results) - failed,
            "failed_count": failed,
            "approval_ready": failed == 0,
            "results": results,
        }

    def freeze(
        self,
        run_id: str,
        *,
        frozen_by: str,
        environment_id: str,
        executor_contract_version: str,
    ) -> FreezeResult:
        self._validate_actor(frozen_by)
        try:
            self.schemas.validate_freeze(
                {
                    "schema_version": REVIEW_WORKFLOW_VERSION,
                    "frozen_by": frozen_by,
                    "environment_id": environment_id,
                    "executor_contract_version": executor_contract_version,
                }
            )
        except JsonSchemaError as error:
            raise TestReviewError("FREEZE_PAYLOAD_SCHEMA_INVALID") from error
        if not ACTOR_PATTERN.fullmatch(environment_id):
            raise TestReviewError("ENVIRONMENT_ID_INVALID")
        if not re.fullmatch(r"[a-z][a-z0-9-]+@[0-9]+\.[0-9]+\.[0-9]+", executor_contract_version):
            raise TestReviewError("EXECUTOR_CONTRACT_VERSION_INVALID")
        run = self._ready_run(run_id)
        existing = self.database.fetch_one(
            "SELECT * FROM frozen_baselines WHERE test_generation_run_id=:run", {"run": run_id}
        )
        if existing:
            if (
                existing["environment_id"] != environment_id
                or existing["executor_contract_version"] != executor_contract_version
                or existing["frozen_by"] != frozen_by
            ):
                raise TestReviewError("BASELINE_ALREADY_FROZEN_WITH_DIFFERENT_CONTRACT")
            count_row = self.database.fetch_one(
                "SELECT COUNT(*) AS count FROM immutable_execution_snapshots "
                "WHERE frozen_baseline_id=:id",
                {"id": existing["frozen_baseline_id"]},
            )
            if count_row is None:
                raise TestReviewError("BASELINE_SNAPSHOT_COUNT_UNAVAILABLE")
            return FreezeResult(
                str(existing["frozen_baseline_id"]),
                int(existing["baseline_version"]),
                str(existing["baseline_hash"]),
                int(count_row["count"]),
                str(existing["status"]),
            )
        approved = self.database.fetch_all(
            "SELECT a.*,c.case_type,c.content_hash AS candidate_hash "
            "FROM approved_test_case_versions a "
            "JOIN test_case_candidates c ON c.test_case_candidate_id=a.test_case_candidate_id "
            "WHERE c.test_generation_run_id=:run ORDER BY c.case_type,a.case_id",
            {"run": run_id},
        )
        if len(approved) != int(run["candidate_count"]):
            raise TestReviewError("COLLECTION_NOT_FULLY_APPROVED")
        latest = self.database.fetch_all(
            "SELECT c.case_id,(SELECT r.decision FROM test_case_reviews r "
            "WHERE r.test_case_candidate_id=c.test_case_candidate_id "
            "ORDER BY r.rowid DESC LIMIT 1) AS decision "
            "FROM test_case_candidates c WHERE c.test_generation_run_id=:run",
            {"run": run_id},
        )
        if any(row["decision"] != "approve" for row in latest):
            raise TestReviewError("COLLECTION_NOT_FULLY_APPROVED")
        links = self.database.fetch_all(
            "SELECT c.case_id,l.requirement_id,l.requirement_version,l.requirement_snapshot_hash,"
            "l.source_block_id,l.link_type FROM test_case_candidates c "
            "JOIN test_case_candidate_requirement_links l "
            "ON l.test_case_candidate_id=c.test_case_candidate_id "
            "WHERE c.test_generation_run_id=:run ORDER BY c.case_id,l.requirement_id,l.link_type",
            {"run": run_id},
        )
        links_by_case: dict[str, list[dict[str, Any]]] = {}
        for link in links:
            links_by_case.setdefault(str(link["case_id"]), []).append(link)
        baseline_id = new_id("FBL")
        members: list[dict[str, Any]] = []
        for ordinal, item in enumerate(approved, 1):
            case_id = str(item["case_id"])
            trace = links_by_case.get(case_id, [])
            if not trace:
                raise TestReviewError("REQUIREMENT_TRACE_MISSING")
            member_id = new_id("FBM")
            snapshot_id = new_id("IES")
            snapshot = {
                "schema_version": SNAPSHOT_SCHEMA_VERSION,
                "protocol_version": PROTOCOL_VERSION,
                "executor_contract_version": executor_contract_version,
                "environment_id": environment_id,
                "baseline_id": baseline_id,
                "case_id": case_id,
                "case_version": int(item["case_version"]),
                "approved_content_hash": item["content_hash"],
                "requirement_trace": trace,
                "fixtures": compile_session_fixtures(json.loads(str(item["payload_json"]))),
                "case": json.loads(str(item["payload_json"])),
            }
            self.schemas.validate_snapshot(snapshot)
            members.append(
                {
                    "member_id": member_id,
                    "snapshot_id": snapshot_id,
                    "approved_id": item["approved_test_case_version_id"],
                    "case_id": case_id,
                    "case_version": int(item["case_version"]),
                    "approved_hash": item["content_hash"],
                    "trace_hash": _hash(trace),
                    "ordinal": ordinal,
                    "snapshot": snapshot,
                    "snapshot_hash": _hash(snapshot),
                }
            )
        baseline_core = {
            "generation_run_id": run_id,
            "collection_hash": run["collection_hash"],
            "baseline_version": 1,
            "protocol_version": PROTOCOL_VERSION,
            "executor_contract_version": executor_contract_version,
            "environment_id": environment_id,
            "members": [
                {"case_id": item["case_id"], "content_hash": item["approved_hash"]}
                for item in members
            ],
        }
        baseline_hash = _hash(baseline_core)
        with self.database.transaction() as connection:
            connection.execute(
                text(
                    "INSERT INTO frozen_baselines(frozen_baseline_id,test_generation_run_id,"
                    "baseline_version,status,collection_hash,baseline_hash,frozen_by,environment_id,"
                    "protocol_version,executor_contract_version) VALUES "
                    "(:id,:run,1,'frozen',:collection,:hash,:actor,:environment,:protocol,:executor)"
                ),
                {
                    "id": baseline_id,
                    "run": run_id,
                    "collection": run["collection_hash"],
                    "hash": baseline_hash,
                    "actor": frozen_by,
                    "environment": environment_id,
                    "protocol": PROTOCOL_VERSION,
                    "executor": executor_contract_version,
                },
            )
            for item in members:
                connection.execute(
                    text(
                        "INSERT INTO frozen_baseline_members(frozen_baseline_member_id,"
                        "frozen_baseline_id,approved_test_case_version_id,case_id,case_version,"
                        "approved_content_hash,requirement_trace_hash,ordinal) VALUES "
                        "(:id,:baseline,:approved,:case,:version,:hash,:trace,:ordinal)"
                    ),
                    {
                        "id": item["member_id"],
                        "baseline": baseline_id,
                        "approved": item["approved_id"],
                        "case": item["case_id"],
                        "version": item["case_version"],
                        "hash": item["approved_hash"],
                        "trace": item["trace_hash"],
                        "ordinal": item["ordinal"],
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO immutable_execution_snapshots("
                        "immutable_execution_snapshot_id,frozen_baseline_id,"
                        "frozen_baseline_member_id,case_id,snapshot_json,snapshot_hash) "
                        "VALUES (:id,:baseline,:member,:case,:payload,:hash)"
                    ),
                    {
                        "id": item["snapshot_id"],
                        "baseline": baseline_id,
                        "member": item["member_id"],
                        "case": item["case_id"],
                        "payload": _canonical(item["snapshot"]),
                        "hash": item["snapshot_hash"],
                    },
                )
            self._audit(
                connection,
                run_id,
                None,
                baseline_id,
                "baseline_frozen",
                frozen_by,
                {"baseline_hash": baseline_hash, "snapshot_count": len(members)},
            )
        return FreezeResult(baseline_id, 1, baseline_hash, len(members), "frozen")

    def baseline(self, baseline_id: str) -> dict[str, Any]:
        baseline = self.database.fetch_one(
            "SELECT * FROM frozen_baselines WHERE frozen_baseline_id=:id", {"id": baseline_id}
        )
        if not baseline:
            raise TestReviewError("BASELINE_NOT_FOUND")
        snapshots = self.database.fetch_all(
            "SELECT s.immutable_execution_snapshot_id,s.case_id,s.snapshot_hash,s.snapshot_json "
            "FROM immutable_execution_snapshots s JOIN frozen_baseline_members m "
            "ON m.frozen_baseline_member_id=s.frozen_baseline_member_id "
            "WHERE s.frozen_baseline_id=:id ORDER BY m.ordinal",
            {"id": baseline_id},
        )
        for item in snapshots:
            payload = json.loads(str(item["snapshot_json"]))
            if _hash(payload) != item["snapshot_hash"]:
                raise TestReviewError("SNAPSHOT_INTEGRITY_INVALID")
            item["snapshot"] = payload
            del item["snapshot_json"]
        return {**baseline, "snapshots": snapshots}

    def _ready_run(self, run_id: str) -> dict[str, Any]:
        run = self.database.fetch_one(
            "SELECT * FROM test_generation_runs WHERE test_generation_run_id=:id", {"id": run_id}
        )
        if not run:
            raise TestReviewError("GENERATION_RUN_NOT_FOUND")
        if run["status"] != "validated_pending_review" or not run["collection_hash"]:
            raise TestReviewError("CANDIDATE_COLLECTION_NOT_READY")
        return run

    def _verify_collection(self, run: dict[str, Any], rows: list[dict[str, Any]]) -> None:
        if len(rows) != int(run["candidate_count"]):
            raise TestReviewError("CANDIDATE_COUNT_MISMATCH")
        payloads: list[dict[str, Any]] = []
        for row in rows:
            payload = json.loads(str(row["payload_json"]))
            payloads.append(payload)
            if payload.get("case_id") != row["case_id"]:
                raise TestReviewError("CANDIDATE_ID_MISMATCH")
            if _candidate_hash(payload) != row["content_hash"]:
                raise TestReviewError("CANDIDATE_INTEGRITY_INVALID")
            links = self.database.fetch_all(
                "SELECT requirement_id,requirement_version,requirement_snapshot_hash,"
                "source_block_id FROM test_case_candidate_requirement_links "
                "WHERE test_case_candidate_id=:candidate ORDER BY requirement_id",
                {"candidate": row["test_case_candidate_id"]},
            )
            trace = sorted(
                payload["trace"]["requirements"], key=lambda item: item["requirement_id"]
            )
            if [item["requirement_id"] for item in links] != [
                item["requirement_id"] for item in trace
            ]:
                raise TestReviewError("REQUIREMENT_LINK_SET_MISMATCH")
            for link, item in zip(links, trace, strict=True):
                if (
                    int(link["requirement_version"]) != int(item["requirement_version"])
                    or link["requirement_snapshot_hash"] != item["snapshot_hash"]
                    or link["source_block_id"] != item["source_block_id"]
                ):
                    raise TestReviewError("REQUIREMENT_LINK_TRACE_MISMATCH")
        if _hash(payloads) != run["collection_hash"]:
            raise TestReviewError("COLLECTION_HASH_MISMATCH")

    @staticmethod
    def _validate_actor(actor_id: str) -> None:
        if not ACTOR_PATTERN.fullmatch(actor_id):
            raise TestReviewError("REVIEWER_ID_INVALID")

    @staticmethod
    def _audit(
        connection: Any,
        run_id: str,
        candidate_id: str | None,
        baseline_id: str | None,
        event_type: str,
        actor_id: str,
        details: dict[str, Any],
    ) -> None:
        connection.execute(
            text(
                "INSERT INTO test_case_review_audit_events("
                "test_case_review_audit_event_id,test_generation_run_id,test_case_candidate_id,"
                "frozen_baseline_id,event_type,actor_id,details_json) VALUES "
                "(:id,:run,:candidate,:baseline,:event,:actor,:details)"
            ),
            {
                "id": new_id("RAE"),
                "run": run_id,
                "candidate": candidate_id,
                "baseline": baseline_id,
                "event": event_type,
                "actor": actor_id,
                "details": _canonical(details),
            },
        )
