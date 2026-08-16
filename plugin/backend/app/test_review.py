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
from plugin.backend.app.mvp_baseline import (
    DISPOSITIONS,
    MVP_BASELINE_POLICY_VERSION,
    MVP_MAX_AUTOMATED,
    MVP_MIN_AUTOMATED,
    MVP_REQUIRED_CASE_IDS,
    propose_mvp_classification,
)
from plugin.backend.app.test_generation_schemas import TestCaseSchemas
from plugin.backend.app.test_review_schemas import ReviewSchemas

PROTOCOL_VERSION = "unified-test-protocol@1.0.0"
REVIEW_WORKFLOW_VERSION = "test-case-review@2.0.0"
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
        self.candidate_schemas = TestCaseSchemas()

    def create_human_revision(
        self,
        run_id: str,
        case_id: str,
        *,
        revised_by: str,
        revision_reason: str,
        expected_content_hash: str,
        candidate: dict[str, Any],
    ) -> dict[str, Any]:
        self._validate_actor(revised_by)
        request_payload = {
            "schema_version": REVIEW_WORKFLOW_VERSION,
            "revised_by": revised_by,
            "revision_reason": revision_reason,
            "expected_content_hash": expected_content_hash,
            "candidate": candidate,
        }
        try:
            self.schemas.validate_revision(request_payload)
        except JsonSchemaError as error:
            raise TestReviewError("HUMAN_REVISION_PAYLOAD_INVALID") from error
        self._ready_run(run_id)
        source = self.database.fetch_one(
            "SELECT * FROM test_case_candidates WHERE test_generation_run_id=:run "
            "AND case_id=:case",
            {"run": run_id, "case": case_id},
        )
        if not source:
            raise TestReviewError("CANDIDATE_NOT_FOUND")
        if source["content_hash"] != expected_content_hash:
            raise TestReviewError("CANDIDATE_HASH_CHANGED")
        original = json.loads(str(source["payload_json"]))
        revised = json.loads(json.dumps(candidate))
        for field in ("case_id", "case_type", "schema_version", "trace"):
            if revised.get(field) != original.get(field):
                raise TestReviewError("HUMAN_REVISION_IMMUTABLE_FIELD_CHANGED")
        revised["content_hash"] = ""
        revised["content_hash"] = _candidate_hash(revised)
        try:
            self.candidate_schemas.validate("test_case_candidate.schema.json", revised)
        except JsonSchemaError as error:
            raise TestReviewError("HUMAN_REVISION_CANDIDATE_SCHEMA_INVALID") from error
        latest = self.database.fetch_one(
            "SELECT COALESCE(MAX(revision_number),0) AS revision FROM test_case_human_revisions "
            "WHERE test_case_candidate_id=:candidate",
            {"candidate": source["test_case_candidate_id"]},
        )
        revision_number = int(latest["revision"] if latest else 0) + 1
        revision_id = new_id("TCHR")
        with self.database.transaction() as connection:
            connection.execute(
                text(
                    "INSERT INTO test_case_human_revisions(test_case_human_revision_id,"
                    "test_generation_run_id,test_case_candidate_id,revision_number,payload_json,"
                    "content_hash,revised_by,revision_reason) VALUES "
                    "(:id,:run,:candidate,:number,:payload,:hash,:actor,:reason)"
                ),
                {
                    "id": revision_id,
                    "run": run_id,
                    "candidate": source["test_case_candidate_id"],
                    "number": revision_number,
                    "payload": _canonical(revised),
                    "hash": revised["content_hash"],
                    "actor": revised_by,
                    "reason": revision_reason.strip(),
                },
            )
            self._audit(
                connection,
                run_id,
                str(source["test_case_candidate_id"]),
                None,
                "human_revision_created",
                revised_by,
                {
                    "revision_id": revision_id,
                    "revision_number": revision_number,
                    "source_content_hash": expected_content_hash,
                    "revised_content_hash": revised["content_hash"],
                },
            )
        return {
            "human_revision_id": revision_id,
            "revision_number": revision_number,
            "content_hash": revised["content_hash"],
            "executability_findings": [
                finding.as_dict() for finding in validate_candidate_executability(revised)
            ],
        }

    def collection(self, run_id: str) -> dict[str, Any]:
        run = self._ready_run(run_id)
        rows = self.database.fetch_all(
            "SELECT c.test_case_candidate_id,c.case_id,c.case_version,c.case_type,"
            "c.content_hash,c.payload_json,r.test_case_review_id,r.reviewer_id,r.decision,"
            "r.automation_disposition,r.disposition_reason,r.comment,"
            "r.created_at AS reviewed_at FROM test_case_candidates c "
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
        automation_disposition: str,
        disposition_reason: str,
        comment: str,
        expected_content_hash: str,
        human_revision_id: str | None = None,
    ) -> dict[str, Any]:
        self._validate_actor(reviewer_id)
        try:
            self.schemas.validate_review(
                {
                    "schema_version": REVIEW_WORKFLOW_VERSION,
                    "reviewer_id": reviewer_id,
                    "decision": decision,
                    "automation_disposition": automation_disposition,
                    "disposition_reason": disposition_reason,
                    "comment": comment,
                    "expected_content_hash": expected_content_hash,
                    "human_revision_id": human_revision_id,
                }
            )
        except JsonSchemaError as error:
            raise TestReviewError("REVIEW_PAYLOAD_SCHEMA_INVALID") from error
        if decision not in DECISIONS:
            raise TestReviewError("REVIEW_DECISION_INVALID")
        if automation_disposition not in DISPOSITIONS:
            raise TestReviewError("AUTOMATION_DISPOSITION_INVALID")
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
        reviewed_hash = str(candidate["content_hash"])
        payload = json.loads(str(candidate["payload_json"]))
        revision_number = 0
        if human_revision_id:
            revision = self.database.fetch_one(
                "SELECT * FROM test_case_human_revisions WHERE test_case_human_revision_id=:id "
                "AND test_case_candidate_id=:candidate",
                {"id": human_revision_id, "candidate": candidate["test_case_candidate_id"]},
            )
            if not revision:
                raise TestReviewError("HUMAN_REVISION_NOT_FOUND")
            payload = json.loads(str(revision["payload_json"]))
            reviewed_hash = str(revision["content_hash"])
            revision_number = int(revision["revision_number"])
            latest_revision = self.database.fetch_one(
                "SELECT MAX(revision_number) AS revision_number FROM test_case_human_revisions "
                "WHERE test_case_candidate_id=:candidate",
                {"candidate": candidate["test_case_candidate_id"]},
            )
            if not latest_revision or revision_number != int(latest_revision["revision_number"]):
                raise TestReviewError("HUMAN_REVISION_IS_NOT_LATEST")
        if reviewed_hash != expected_content_hash:
            raise TestReviewError("CANDIDATE_HASH_CHANGED")
        if _candidate_hash(payload) != reviewed_hash:
            raise TestReviewError("CANDIDATE_INTEGRITY_INVALID")
        duplicate_approval = self.database.fetch_one(
            "SELECT approved_test_case_version_id FROM approved_test_case_versions "
            "WHERE test_case_candidate_id=:candidate AND (content_hash=:hash OR "
            "(:revision IS NOT NULL AND test_case_human_revision_id=:revision))",
            {
                "candidate": candidate["test_case_candidate_id"],
                "hash": reviewed_hash,
                "revision": human_revision_id,
            },
        )
        if duplicate_approval and decision == "approve" and automation_disposition == "automated":
            raise TestReviewError("APPROVED_CONTENT_ALREADY_EXISTS")
        findings = validate_candidate_executability(payload)
        if decision == "approve" and automation_disposition == "automated" and findings:
            raise TestReviewError("CANDIDATE_NOT_EXECUTABLE")
        review_id = new_id("TCR")
        approved_id: str | None = None
        approved_hash: str | None = None
        with self.database.transaction() as connection:
            connection.execute(
                text(
                    "INSERT INTO test_case_reviews(test_case_review_id,test_generation_run_id,"
                    "test_case_candidate_id,reviewer_id,decision,automation_disposition,"
                    "disposition_reason,test_case_human_revision_id,comment,"
                    "candidate_content_hash) "
                    "VALUES (:id,:run,:candidate,:reviewer,:decision,:disposition,:reason,"
                    ":revision,:comment,:hash)"
                ),
                {
                    "id": review_id,
                    "run": run_id,
                    "candidate": candidate["test_case_candidate_id"],
                    "reviewer": reviewer_id,
                    "decision": decision,
                    "disposition": automation_disposition,
                    "reason": disposition_reason.strip(),
                    "revision": human_revision_id,
                    "comment": comment.strip(),
                    "hash": expected_content_hash,
                },
            )
            if decision == "approve" and automation_disposition == "automated":
                approved_payload = dict(payload)
                approved_payload["review_status"] = "approved"
                latest_approved = connection.execute(
                    text(
                        "SELECT COALESCE(MAX(case_version),0) FROM approved_test_case_versions "
                        "WHERE case_id=:case"
                    ),
                    {"case": case_id},
                ).scalar_one()
                approved_payload["approved_version"] = max(
                    int(candidate["case_version"]) + (1 if revision_number else 0),
                    int(latest_approved) + 1,
                )
                approved_hash = _hash(approved_payload)
                approved_id = new_id("ATCV")
                connection.execute(
                    text(
                        "INSERT INTO approved_test_case_versions("
                        "approved_test_case_version_id,test_case_candidate_id,test_case_review_id,"
                        "case_id,case_version,schema_version,payload_json,content_hash,"
                        "approved_by,automation_disposition,test_case_human_revision_id) VALUES "
                        "(:id,:candidate,:review,:case,:version,:schema,:payload,:hash,:actor,"
                        ":disposition,:revision)"
                    ),
                    {
                        "id": approved_id,
                        "candidate": candidate["test_case_candidate_id"],
                        "review": review_id,
                        "case": case_id,
                        "version": approved_payload["approved_version"],
                        "schema": payload["schema_version"],
                        "payload": _canonical(approved_payload),
                        "hash": approved_hash,
                        "actor": reviewer_id,
                        "disposition": automation_disposition,
                        "revision": human_revision_id,
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
                    "automation_disposition": automation_disposition,
                    "disposition_reason": disposition_reason.strip(),
                    "content_hash": expected_content_hash,
                },
            )
        return {
            "review_id": review_id,
            "decision": decision,
            "automation_disposition": automation_disposition,
            "approved_test_case_version_id": approved_id,
            "approved_content_hash": approved_hash,
            "collection_hash": run["collection_hash"],
        }

    def mvp_classification_plan(self, run_id: str) -> dict[str, Any]:
        return propose_mvp_classification(self.collection(run_id)["candidates"])

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
        latest = self.database.fetch_all(
            "SELECT c.case_id,c.test_case_candidate_id,r.test_case_review_id,r.decision,"
            "r.automation_disposition,r.disposition_reason "
            "FROM test_case_candidates c LEFT JOIN test_case_reviews r ON "
            "r.test_case_review_id=(SELECT r2.test_case_review_id FROM test_case_reviews r2 "
            "WHERE r2.test_case_candidate_id=c.test_case_candidate_id "
            "ORDER BY r2.rowid DESC LIMIT 1) WHERE c.test_generation_run_id=:run",
            {"run": run_id},
        )
        if len(latest) != int(run["candidate_count"]) or any(
            not row["automation_disposition"] or not row["disposition_reason"] for row in latest
        ):
            raise TestReviewError("COLLECTION_NOT_FULLY_CLASSIFIED")
        if any(
            row["automation_disposition"] == "automated" and row["decision"] != "approve"
            for row in latest
        ):
            raise TestReviewError("AUTOMATED_SUBSET_NOT_FULLY_APPROVED")
        automated_ids = {
            str(row["case_id"]) for row in latest if row["automation_disposition"] == "automated"
        }
        if not MVP_MIN_AUTOMATED <= len(automated_ids) <= MVP_MAX_AUTOMATED:
            raise TestReviewError("MVP_AUTOMATED_COUNT_OUT_OF_RANGE")
        if not MVP_REQUIRED_CASE_IDS <= automated_ids:
            raise TestReviewError("MVP_REQUIRED_CASES_MISSING")
        approved = self.database.fetch_all(
            "SELECT a.*,c.case_type,c.content_hash AS candidate_hash "
            "FROM approved_test_case_versions a "
            "JOIN test_case_candidates c ON c.test_case_candidate_id=a.test_case_candidate_id "
            "JOIN test_case_reviews r ON r.test_case_review_id=a.test_case_review_id "
            "WHERE c.test_generation_run_id=:run AND r.decision='approve' "
            "AND r.automation_disposition='automated' "
            "AND r.test_case_review_id=(SELECT r2.test_case_review_id FROM test_case_reviews r2 "
            "WHERE r2.test_case_candidate_id=c.test_case_candidate_id "
            "ORDER BY r2.rowid DESC LIMIT 1) ORDER BY c.case_type,a.case_id",
            {"run": run_id},
        )
        if len(approved) != len(automated_ids):
            raise TestReviewError("AUTOMATED_APPROVED_VERSION_MISSING")
        for item in approved:
            if validate_candidate_executability(json.loads(str(item["payload_json"]))):
                raise TestReviewError("AUTOMATED_CANDIDATE_NOT_EXECUTABLE")
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
                "isolation": {
                    "database": "fresh_database_per_run",
                    "cleanup": "discard_run_database",
                },
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
                {
                    "baseline_hash": baseline_hash,
                    "snapshot_count": len(members),
                    "policy_version": MVP_BASELINE_POLICY_VERSION,
                    "candidate_count": int(run["candidate_count"]),
                    "automated_count": len(members),
                    "manual_count": sum(
                        row["automation_disposition"] == "manual" for row in latest
                    ),
                    "deferred_count": sum(
                        row["automation_disposition"] == "deferred" for row in latest
                    ),
                },
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
