from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from sqlalchemy import text
from sut.backend.app.time import utc_now

from plugin.backend.app.api_execution import _canonical
from plugin.backend.app.database import PROJECT_ROOT, PluginDatabase
from plugin.backend.app.ids import new_id

EVIDENCE_POLICY_VERSION = "evidence-policy@1.0.0"
CLASSIFIER_VERSION = "failure-classifier@1.0.0"
ADVISORY_SCHEMA_VERSION = "advisory-evidence-analysis@1.0.0"
FORBIDDEN_TEXT_MARKERS = (
    "authorization: bearer ",
    "password_hash",
    "sqlite:///",
    "traceback (most recent call last)",
)


class EvidenceError(Exception):
    pass


class EvidenceService:
    def __init__(self, database: PluginDatabase) -> None:
        self.database = database
        schema_root = PROJECT_ROOT / "schemas" / "evidence" / "v1"
        self.evidence_validator = Draft202012Validator(
            json.loads((schema_root / "consolidated_evidence.schema.json").read_text("utf-8"))
        )
        self.advisory_validator = Draft202012Validator(
            json.loads((schema_root / "advisory_analysis.schema.json").read_text("utf-8"))
        )

    def consolidate(self, api_run_id: str, ui_run_id: str) -> dict[str, Any]:
        existing = self.database.fetch_one(
            "SELECT evidence_consolidation_run_id FROM evidence_consolidation_runs "
            "WHERE api_test_run_id=:api AND ui_test_run_id=:ui AND policy_version=:policy "
            "AND classifier_version=:classifier",
            {
                "api": api_run_id,
                "ui": ui_run_id,
                "policy": EVIDENCE_POLICY_VERSION,
                "classifier": CLASSIFIER_VERSION,
            },
        )
        if existing:
            return self.get(str(existing["evidence_consolidation_run_id"]))
        api_run = self._run("api_test_runs", "api_test_run_id", api_run_id)
        ui_run = self._run("ui_test_runs", "ui_test_run_id", ui_run_id)
        if api_run["status"] != "completed" or ui_run["status"] != "completed":
            raise EvidenceError("SOURCE_RUN_NOT_COMPLETED")
        if (
            api_run["frozen_baseline_id"] != ui_run["frozen_baseline_id"]
            or api_run["environment_id"] != ui_run["environment_id"]
        ):
            raise EvidenceError("SOURCE_RUN_CONTEXT_MISMATCH")
        api_items = self._api_items(api_run_id)
        ui_items = self._ui_items(ui_run_id)
        if (
            len(api_items) != int(api_run["total_count"])
            or len(ui_items) != int(ui_run["total_count"])
            or not api_items
            or not ui_items
        ):
            raise EvidenceError("SOURCE_RESULT_SET_INCOMPLETE")
        records: list[dict[str, Any]] = []
        classifications: list[dict[str, Any]] = []
        for item in api_items:
            records.extend(self._api_evidence_records(item))
            classifications.append(self._classification("api", item))
        for item in ui_items:
            records.extend(self._ui_evidence_records(item))
            classifications.append(self._classification("ui", item))
        run_id = new_id("ECR")
        failures = sum(item["verdict"] == "FAIL" for item in classifications)
        with self.database.transaction() as connection:
            connection.execute(
                text(
                    "INSERT INTO evidence_consolidation_runs("
                    "evidence_consolidation_run_id,frozen_baseline_id,api_test_run_id,"
                    "ui_test_run_id,policy_version,classifier_version,status,result_count,"
                    "evidence_count,failure_count) VALUES "
                    "(:id,:baseline,:api,:ui,:policy,:classifier,'completed',:results,:evidence,"
                    ":failures)"
                ),
                {
                    "id": run_id,
                    "baseline": api_run["frozen_baseline_id"],
                    "api": api_run_id,
                    "ui": ui_run_id,
                    "policy": EVIDENCE_POLICY_VERSION,
                    "classifier": CLASSIFIER_VERSION,
                    "results": len(classifications),
                    "evidence": len(records),
                    "failures": failures,
                },
            )
            for record in records:
                connection.execute(
                    text(
                        "INSERT INTO consolidated_evidence_records("
                        "consolidated_evidence_id,evidence_consolidation_run_id,source_executor,"
                        "source_result_id,source_evidence_id,case_id,evidence_kind,relative_path,"
                        "content_hash,content_size,mime_type,redaction_status,integrity_status,"
                        "retention_class,expires_at,metadata_json) VALUES "
                        "(:id,:run,:executor,:result,:source_evidence,:case,:kind,:path,:hash,:size,"
                        ":mime,'verified','verified',:retention,:expires,:metadata)"
                    ),
                    {
                        "id": new_id("EVM"),
                        "run": run_id,
                        "executor": record["source_executor"],
                        "result": record["source_result_id"],
                        "source_evidence": record["source_evidence_id"],
                        "case": record["case_id"],
                        "kind": record["evidence_kind"],
                        "path": record["relative_path"],
                        "hash": record["content_hash"],
                        "size": record["content_size"],
                        "mime": record["mime_type"],
                        "retention": record["retention_class"],
                        "expires": record["expires_at"],
                        "metadata": _canonical(record),
                    },
                )
            for classification in classifications:
                connection.execute(
                    text(
                        "INSERT INTO deterministic_failure_classifications("
                        "failure_classification_id,evidence_consolidation_run_id,source_executor,"
                        "source_result_id,case_id,verdict,classification_code,suspected_bug_id,"
                        "authoritative,rule_version,facts_json) VALUES "
                        "(:id,:run,:executor,:result,:case,:verdict,:code,:bug,1,:rule,:facts)"
                    ),
                    {
                        "id": new_id("CLS"),
                        "run": run_id,
                        "executor": classification["source_executor"],
                        "result": classification["source_result_id"],
                        "case": classification["case_id"],
                        "verdict": classification["verdict"],
                        "code": classification["classification_code"],
                        "bug": classification["suspected_bug_id"],
                        "rule": CLASSIFIER_VERSION,
                        "facts": _canonical(classification["facts"]),
                    },
                )
            connection.execute(
                text(
                    "INSERT INTO evidence_audit_events(evidence_audit_event_id,"
                    "evidence_consolidation_run_id,event_type,details_json) VALUES "
                    "(:id,:run,'evidence_consolidated',:details)"
                ),
                {
                    "id": new_id("EAU"),
                    "run": run_id,
                    "details": _canonical(
                        {
                            "result_count": len(classifications),
                            "evidence_count": len(records),
                            "failure_count": failures,
                            "advisory_analysis_count": 0,
                        }
                    ),
                },
            )
        return self.get(run_id)

    def get(self, run_id: str) -> dict[str, Any]:
        run = self.database.fetch_one(
            "SELECT * FROM evidence_consolidation_runs WHERE evidence_consolidation_run_id=:id",
            {"id": run_id},
        )
        if not run:
            raise EvidenceError("EVIDENCE_CONSOLIDATION_NOT_FOUND")
        evidence = self.database.fetch_all(
            "SELECT * FROM consolidated_evidence_records "
            "WHERE evidence_consolidation_run_id=:run ORDER BY case_id,evidence_kind",
            {"run": run_id},
        )
        classifications = self.database.fetch_all(
            "SELECT * FROM deterministic_failure_classifications "
            "WHERE evidence_consolidation_run_id=:run ORDER BY case_id",
            {"run": run_id},
        )
        return {**run, "evidence": evidence, "classifications": classifications}

    def record_advisory(
        self,
        classification_id: str,
        *,
        provider: str,
        model: str,
        prompt_version: str,
        analysis: dict[str, Any],
    ) -> dict[str, Any]:
        if list(self.advisory_validator.iter_errors(analysis)):
            raise EvidenceError("ADVISORY_ANALYSIS_SCHEMA_INVALID")
        classification = self.database.fetch_one(
            "SELECT failure_classification_id,verdict,classification_code "
            "FROM deterministic_failure_classifications WHERE failure_classification_id=:id",
            {"id": classification_id},
        )
        if not classification:
            raise EvidenceError("FAILURE_CLASSIFICATION_NOT_FOUND")
        advisory_id = new_id("AIA")
        self.database.execute(
            "INSERT INTO advisory_ai_analyses(advisory_ai_analysis_id,failure_classification_id,"
            "provider,model,prompt_version,advisory_label,analysis_json) VALUES "
            "(:id,:classification,:provider,:model,:prompt,'advisory_non_authoritative',:analysis)",
            {
                "id": advisory_id,
                "classification": classification_id,
                "provider": provider,
                "model": model,
                "prompt": prompt_version,
                "analysis": _canonical(analysis),
            },
        )
        return {
            "advisory_ai_analysis_id": advisory_id,
            "advisory_label": "advisory_non_authoritative",
            "authoritative_verdict": classification["verdict"],
            "authoritative_classification": classification["classification_code"],
        }

    def _api_items(self, run_id: str) -> list[dict[str, Any]]:
        return self.database.fetch_all(
            "SELECT r.*,e.api_test_evidence_id,e.evidence_json,e.evidence_hash,"
            "e.redaction_applied,s.snapshot_json FROM api_test_results r "
            "JOIN api_test_evidence e ON e.api_test_result_id=r.api_test_result_id "
            "JOIN immutable_execution_snapshots s ON "
            "s.immutable_execution_snapshot_id=r.immutable_execution_snapshot_id "
            "WHERE r.api_test_run_id=:run ORDER BY r.case_id",
            {"run": run_id},
        )

    def _ui_items(self, run_id: str) -> list[dict[str, Any]]:
        return self.database.fetch_all(
            "SELECT r.*,e.ui_test_evidence_id,e.evidence_json,e.evidence_hash,"
            "e.screenshot_path,e.screenshot_hash,e.trace_path,e.trace_hash,e.redaction_applied,"
            "s.snapshot_json FROM ui_test_results r JOIN ui_test_evidence e "
            "ON e.ui_test_result_id=r.ui_test_result_id JOIN immutable_execution_snapshots s ON "
            "s.immutable_execution_snapshot_id=r.immutable_execution_snapshot_id "
            "WHERE r.ui_test_run_id=:run ORDER BY r.case_id",
            {"run": run_id},
        )

    def _api_evidence_records(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        payload = json.loads(str(item["evidence_json"]))
        encoded = _canonical(payload).encode("utf-8")
        if hashlib.sha256(encoded).hexdigest() != item["evidence_hash"]:
            raise EvidenceError("SOURCE_EVIDENCE_HASH_INVALID")
        self._verify_redaction(encoded, item)
        return [
            self._record(
                "api",
                str(item["api_test_result_id"]),
                str(item["api_test_evidence_id"]),
                str(item["case_id"]),
                "api_exchange",
                None,
                str(item["evidence_hash"]),
                len(encoded),
                "application/json",
                "canonical",
                365,
            )
        ]

    def _ui_evidence_records(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        payload = json.loads(str(item["evidence_json"]))
        encoded = _canonical(payload).encode()
        if hashlib.sha256(encoded).hexdigest() != item["evidence_hash"]:
            raise EvidenceError("SOURCE_EVIDENCE_HASH_INVALID")
        self._verify_redaction(encoded, item)
        records: list[dict[str, Any]] = []
        for kind, path_key, hash_key, mime, retention, days in (
            ("screenshot", "screenshot_path", "screenshot_hash", "image/png", "screenshot", 90),
            ("trace", "trace_path", "trace_hash", "application/zip", "trace", 30),
        ):
            path = self._safe_artifact_path(str(item[path_key]))
            content = path.read_bytes()
            if hashlib.sha256(content).hexdigest() != item[hash_key]:
                raise EvidenceError("SOURCE_ARTIFACT_HASH_INVALID")
            self._verify_redaction(content, item)
            records.append(
                self._record(
                    "ui",
                    str(item["ui_test_result_id"]),
                    str(item["ui_test_evidence_id"]),
                    str(item["case_id"]),
                    kind,
                    str(item[path_key]),
                    str(item[hash_key]),
                    len(content),
                    mime,
                    retention,
                    days,
                )
            )
        return records

    def _classification(self, executor: str, item: dict[str, Any]) -> dict[str, Any]:
        verdict = str(item["status"])
        case_id = str(item["case_id"])
        code = {
            "PASS": "none",
            "BLOCKED": "precondition_blocked",
            "ERROR": "executor_error",
            "SKIPPED": "skipped",
        }.get(verdict, "product_behavior_mismatch")
        bug_id: str | None = None
        facts: dict[str, Any] = {"verdict": verdict}
        result = json.loads(str(item["result_json"]))
        if verdict == "FAIL" and case_id in {
            "TC-API-AUTH-REG-005",
            "TC-UI-AUTH-REG-005",
        }:
            if not self._seeded_facts_valid(executor, result):
                raise EvidenceError("SEEDED_DEFECT_FACTS_INVALID")
            code = "seeded_product_bug"
            bug_id = "BUG-AUTH-001"
        elif executor == "api" and verdict == "FAIL" and case_id == "TC-API-REQ-REG-003":
            evidence = str(item["evidence_json"])
            if item["actual_status"] == 400 and "password_policy" in evidence:
                code = "test_data_invalid"
        facts.update(
            {
                "executor_failure_type": item["failure_type"],
                "expected": item.get("expected_status", item.get("expected_route")),
                "actual": item.get("actual_status", item.get("actual_route")),
            }
        )
        return {
            "source_executor": executor,
            "source_result_id": item[f"{executor}_test_result_id"],
            "case_id": case_id,
            "verdict": verdict,
            "classification_code": code,
            "suspected_bug_id": bug_id,
            "facts": facts,
        }

    @staticmethod
    def _seeded_facts_valid(executor: str, result: dict[str, Any]) -> bool:
        if executor == "api":
            return bool(result["expected_status"] == 400 and result["actual_status"] == 201)
        network = result["network_observations"]
        return bool(
            result["expected_route"] == "/register"
            and result["actual_route"] == "/profile"
            and any(
                item["path"] == "/api/auth/register" and item["status"] == 201 for item in network
            )
        )

    def _verify_redaction(self, content: bytes, item: dict[str, Any]) -> None:
        if item["redaction_applied"] != 1:
            raise EvidenceError("SOURCE_EVIDENCE_NOT_REDACTED")
        lowered = content.lower()
        if any(marker.encode() in lowered for marker in FORBIDDEN_TEXT_MARKERS):
            raise EvidenceError("SOURCE_EVIDENCE_SENSITIVE_MARKER")
        snapshot = json.loads(str(item["snapshot_json"]))
        secrets = [
            str(value["value"]).encode()
            for value in snapshot["case"].get("test_data", [])
            if value.get("sensitive") and value.get("value")
        ]
        if any(secret in content for secret in secrets):
            raise EvidenceError("SOURCE_EVIDENCE_SECRET_PRESENT")

    @staticmethod
    def _safe_artifact_path(relative: str) -> Path:
        candidate = PROJECT_ROOT / relative
        if candidate.is_symlink():
            raise EvidenceError("SOURCE_ARTIFACT_PATH_INVALID")
        path = candidate.resolve()
        root = (PROJECT_ROOT / "artifacts" / "evidence").resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise EvidenceError("SOURCE_ARTIFACT_PATH_INVALID")
        return path

    def _record(
        self,
        executor: str,
        result_id: str,
        evidence_id: str,
        case_id: str,
        kind: str,
        path: str | None,
        content_hash: str,
        size: int,
        mime: str,
        retention: str,
        days: int,
    ) -> dict[str, Any]:
        record = {
            "schema_version": "consolidated-evidence@1.0.0",
            "source_executor": executor,
            "source_result_id": result_id,
            "source_evidence_id": evidence_id,
            "case_id": case_id,
            "evidence_kind": kind,
            "relative_path": path,
            "content_hash": content_hash,
            "content_size": size,
            "mime_type": mime,
            "redaction_status": "verified",
            "integrity_status": "verified",
            "retention_class": retention,
            "expires_at": (utc_now() + timedelta(days=days)).isoformat().replace("+00:00", "Z"),
        }
        if list(self.evidence_validator.iter_errors(record)):
            raise EvidenceError("CONSOLIDATED_EVIDENCE_SCHEMA_INVALID")
        return record

    def _run(self, table: str, id_column: str, run_id: str) -> dict[str, Any]:
        if (table, id_column) not in {
            ("api_test_runs", "api_test_run_id"),
            ("ui_test_runs", "ui_test_run_id"),
        }:
            raise EvidenceError("SOURCE_RUN_TYPE_INVALID")
        row = self.database.fetch_one(
            f"SELECT * FROM {table} WHERE {id_column}=:id",  # noqa: S608 - strict allowlist above
            {"id": run_id},
        )
        if not row:
            raise EvidenceError("SOURCE_RUN_NOT_FOUND")
        return row
