from __future__ import annotations

import json
from collections import Counter
from typing import Any

from plugin.backend.app.database import PluginDatabase


def _decode(value: Any, fallback: Any = None) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return fallback


class WorkspaceService:
    """Read-only, presentation-safe view over accepted Plugin records."""

    def __init__(self, database: PluginDatabase) -> None:
        self.database = database

    def snapshot(self) -> dict[str, Any]:
        project = self.database.fetch_one("SELECT * FROM projects ORDER BY created_at DESC LIMIT 1")
        if not project:
            return self._empty()
        project_id = str(project["project_id"])
        prd = self.database.fetch_one(
            "SELECT d.prd_document_id,d.title,v.version_id,v.version_number,v.content_hash,"
            "v.media_type,SUBSTR(v.content,1,800) AS content_preview,v.created_at FROM "
            "prd_documents d JOIN prd_versions v ON "
            "v.prd_document_id=d.prd_document_id WHERE d.project_id=:project "
            "ORDER BY v.created_at DESC LIMIT 1",
            {"project": project_id},
        )
        analysis = self.database.fetch_one(
            "SELECT a.* FROM analysis_runs a WHERE a.project_id=:project AND EXISTS "
            "(SELECT 1 FROM requirements r WHERE r.analysis_run_id=a.analysis_run_id) "
            "ORDER BY a.created_at DESC LIMIT 1",
            {"project": project_id},
        )
        analysis_id = str(analysis["analysis_run_id"]) if analysis else ""
        batches = (
            self.database.fetch_all(
                "SELECT analysis_batch_id,batch_index,source_section,status,retry_count,"
                "validation_status,error_type,created_at,completed_at FROM analysis_batches "
                "WHERE analysis_run_id=:run ORDER BY batch_index",
                {"run": analysis_id},
            )
            if analysis_id
            else []
        )
        requirements = self.database.fetch_all(
            "SELECT requirement_id,version_number,review_status,payload_json,created_at "
            "FROM requirements WHERE project_id=:project ORDER BY requirement_id",
            {"project": project_id},
        )
        requirement_rows = [
            {
                **{key: value for key, value in row.items() if key != "payload_json"},
                "requirement": _decode(row["payload_json"], {}),
            }
            for row in requirements
        ]
        generation = self.database.fetch_one(
            "SELECT g.* FROM test_generation_runs g WHERE g.project_id=:project AND EXISTS "
            "(SELECT 1 FROM frozen_baselines f WHERE f.test_generation_run_id="
            "g.test_generation_run_id) ORDER BY g.created_at DESC LIMIT 1",
            {"project": project_id},
        )
        generation_id = str(generation["test_generation_run_id"]) if generation else ""
        candidates = (
            self.database.fetch_all(
                "SELECT c.test_case_candidate_id,c.case_id,c.case_version,c.case_type,"
                "c.lifecycle_status,c.content_hash,c.payload_json,"
                "r.decision,r.automation_disposition,r.disposition_reason,r.created_at AS "
                "reviewed_at FROM test_case_candidates c LEFT JOIN test_case_reviews r ON "
                "r.test_case_review_id=(SELECT r2.test_case_review_id FROM test_case_reviews r2 "
                "WHERE r2.test_case_candidate_id=c.test_case_candidate_id ORDER BY "
                "r2.created_at DESC,r2.test_case_review_id DESC LIMIT 1) WHERE "
                "c.test_generation_run_id=:run ORDER BY c.case_type,c.case_id",
                {"run": generation_id},
            )
            if generation_id
            else []
        )
        candidate_rows = [
            {
                **{key: value for key, value in row.items() if key != "payload_json"},
                "candidate": _decode(row["payload_json"], {}),
            }
            for row in candidates
        ]
        revisions = (
            self.database.fetch_all(
                "SELECT h.test_case_human_revision_id,c.case_id,h.revision_number,"
                "h.content_hash,h.revised_by,h.revision_reason,h.created_at FROM "
                "test_case_human_revisions h JOIN test_case_candidates c ON "
                "c.test_case_candidate_id=h.test_case_candidate_id WHERE "
                "h.test_generation_run_id=:run ORDER BY c.case_id",
                {"run": generation_id},
            )
            if generation_id
            else []
        )
        baseline = (
            self.database.fetch_one(
                "SELECT * FROM frozen_baselines WHERE test_generation_run_id=:run "
                "ORDER BY baseline_version DESC LIMIT 1",
                {"run": generation_id},
            )
            if generation_id
            else None
        )
        baseline_id = str(baseline["frozen_baseline_id"]) if baseline else ""
        api_runs = (
            self.database.fetch_all(
                "SELECT * FROM api_test_runs WHERE frozen_baseline_id=:baseline "
                "ORDER BY created_at DESC",
                {"baseline": baseline_id},
            )
            if baseline_id
            else []
        )
        ui_runs = (
            self.database.fetch_all(
                "SELECT * FROM ui_test_runs WHERE frozen_baseline_id=:baseline "
                "ORDER BY created_at DESC",
                {"baseline": baseline_id},
            )
            if baseline_id
            else []
        )
        api_results = self._results("api", str(api_runs[0]["api_test_run_id"])) if api_runs else []
        ui_results = self._results("ui", str(ui_runs[0]["ui_test_run_id"])) if ui_runs else []
        evidence_run = (
            self.database.fetch_one(
                "SELECT * FROM evidence_consolidation_runs WHERE frozen_baseline_id=:baseline "
                "ORDER BY created_at DESC LIMIT 1",
                {"baseline": baseline_id},
            )
            if baseline_id
            else None
        )
        evidence = (
            self.database.fetch_all(
                "SELECT consolidated_evidence_id,source_executor,source_result_id,case_id,"
                "evidence_kind,content_hash,relative_path,redaction_status,integrity_status,"
                "mime_type,created_at FROM "
                "consolidated_evidence_records WHERE evidence_consolidation_run_id=:run "
                "ORDER BY case_id,evidence_kind",
                {"run": evidence_run["evidence_consolidation_run_id"]},
            )
            if evidence_run
            else []
        )
        bug = self.database.fetch_one(
            "SELECT * FROM canonical_bug_records WHERE project_id=:project "
            "ORDER BY bug_version DESC LIMIT 1",
            {"project": project_id},
        )
        bug_event = (
            self.database.fetch_one(
                "SELECT * FROM bug_status_events WHERE canonical_bug_record_id=:bug "
                "ORDER BY created_at DESC LIMIT 1",
                {"bug": bug["canonical_bug_record_id"]},
            )
            if bug
            else None
        )
        bug_bundle = (
            self.database.fetch_one(
                "SELECT format_version,json_path,json_hash,markdown_path,markdown_hash,"
                "manifest_path,manifest_hash,status FROM bug_artifact_bundles WHERE "
                "canonical_bug_record_id=:bug",
                {"bug": bug["canonical_bug_record_id"]},
            )
            if bug
            else None
        )
        report = self.database.fetch_one(
            "SELECT * FROM canonical_test_reports WHERE project_id=:project "
            "ORDER BY report_version DESC LIMIT 1",
            {"project": project_id},
        )
        regression = (
            self.database.fetch_one(
                "SELECT * FROM defect_regression_runs WHERE frozen_baseline_id=:baseline "
                "ORDER BY created_at DESC LIMIT 1",
                {"baseline": baseline_id},
            )
            if baseline_id
            else None
        )
        statuses = Counter(str(row["status"]) for row in api_results + ui_results)
        classifications = (
            self.database.fetch_all(
                "SELECT source_executor,case_id,verdict,classification_code,suspected_bug_id,"
                "created_at FROM deterministic_failure_classifications WHERE "
                "evidence_consolidation_run_id=:run ORDER BY case_id",
                {"run": evidence_run["evidence_consolidation_run_id"]},
            )
            if evidence_run
            else []
        )
        return {
            "project": project,
            "prd": prd,
            "analysis": {"run": analysis, "batches": batches},
            "requirements": requirement_rows,
            "test_forge": {
                "run": generation,
                "candidates": candidate_rows,
                "revisions": revisions,
            },
            "baseline": baseline,
            "execution": {
                "api_runs": api_runs,
                "ui_runs": ui_runs,
                "api_results": api_results,
                "ui_results": ui_results,
            },
            "evidence": {
                "run": evidence_run,
                "records": evidence,
                "classifications": classifications,
            },
            "bug": {
                "record": self._canonical_row(bug),
                "latest_status_event": bug_event,
                "bundle": bug_bundle,
            },
            "report": self._canonical_row(report),
            "regression": self._canonical_row(regression, "trace_json"),
            "metrics": {
                "requirements": len(requirement_rows),
                "candidates": len(candidate_rows),
                "snapshots": int(
                    (
                        self.database.fetch_one(
                            "SELECT COUNT(*) AS count FROM frozen_baseline_members WHERE "
                            "frozen_baseline_id=:baseline",
                            {"baseline": baseline_id},
                        )
                        or {"count": 0}
                    )["count"]
                )
                if baseline
                else 0,
                "result_statuses": dict(statuses),
                "evidence": len(evidence),
            },
            "meta": {
                "source": "plugin.db",
                "provider_mode": analysis.get("provider_mode") if analysis else None,
                "environment_id": baseline.get("environment_id") if baseline else None,
            },
        }

    def _results(self, kind: str, run_id: str) -> list[dict[str, Any]]:
        if kind == "api":
            statement = (
                "SELECT case_id,case_version,status,failure_type,duration_ms,created_at "
                "FROM api_test_results WHERE api_test_run_id=:run ORDER BY case_id"
            )
        else:
            statement = (
                "SELECT case_id,case_version,status,failure_type,duration_ms,created_at "
                "FROM ui_test_results WHERE ui_test_run_id=:run ORDER BY case_id"
            )
        return self.database.fetch_all(
            statement,
            {"run": run_id},
        )

    @staticmethod
    def _canonical_row(row: dict[str, Any] | None, payload_key: str = "canonical_json") -> Any:
        if not row:
            return None
        return {
            **{key: value for key, value in row.items() if key != payload_key},
            "payload": _decode(row.get(payload_key), {}),
        }

    @staticmethod
    def _empty() -> dict[str, Any]:
        return {
            "project": None,
            "prd": None,
            "analysis": {"run": None, "batches": []},
            "requirements": [],
            "test_forge": {"run": None, "candidates": [], "revisions": []},
            "baseline": None,
            "execution": {"api_runs": [], "ui_runs": [], "api_results": [], "ui_results": []},
            "evidence": {"run": None, "records": [], "classifications": []},
            "bug": {"record": None, "latest_status_event": None, "bundle": None},
            "report": None,
            "regression": None,
            "metrics": {
                "requirements": 0,
                "candidates": 0,
                "snapshots": 0,
                "result_statuses": {},
                "evidence": 0,
            },
            "meta": {"source": "plugin.db", "provider_mode": None, "environment_id": None},
        }
