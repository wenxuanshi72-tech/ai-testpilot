from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.ids import new_id

API_SEEDED_CASE = "TC-API-AUTH-REG-005"
UI_SEEDED_CASE = "TC-UI-AUTH-REG-005"
API_GUARD_CASES = {
    "TC-API-REQ-AUTH-001",
    "TC-API-REQ-BAT-002-5",
    "TC-API-REQ-LOGIN-001",
    "TC-API-REQ-LOGOUT-001",
    "TC-API-REQ-REG-004",
}
UI_GUARD_CASES = {"TC-UI-REQ-LOGIN-001", "TC-UI-REQ-REG-002"}


class RegressionGateError(Exception):
    pass


@dataclass(frozen=True)
class RegressionClosure:
    regression_run_id: str
    bug_status_event_id: str
    effective_bug_status: str
    trace_hash: str
    guard_case_count: int


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class RegressionService:
    def __init__(self, database: PluginDatabase) -> None:
        self.database = database

    def close_bug(
        self,
        *,
        bug_id: str,
        baseline_report_id: str,
        regression_api_run_id: str,
        regression_ui_run_id: str,
    ) -> RegressionClosure:
        bug = self.database.fetch_one(
            "SELECT * FROM canonical_bug_records WHERE bug_id=:bug ORDER BY bug_version DESC",
            {"bug": bug_id},
        )
        report = self.database.fetch_one(
            "SELECT * FROM canonical_test_reports WHERE canonical_test_report_id=:id",
            {"id": baseline_report_id},
        )
        if not bug or not report:
            raise RegressionGateError("BASELINE_TRACE_NOT_FOUND")
        if str(report["canonical_bug_record_id"]) != str(bug["canonical_bug_record_id"]):
            raise RegressionGateError("BASELINE_BUG_REPORT_MISMATCH")
        self._verify_immutable_hash(bug, "canonical_json", "canonical_hash", "BUG_HASH_INVALID")
        self._verify_immutable_hash(
            report, "canonical_json", "canonical_hash", "REPORT_HASH_INVALID"
        )
        baseline_id = str(report["frozen_baseline_id"])
        baseline_api = str(report["api_test_run_id"])
        baseline_ui = str(report["ui_test_run_id"])
        self._validate_run("api", baseline_api, baseline_id)
        self._validate_run("ui", baseline_ui, baseline_id)
        self._validate_run("api", regression_api_run_id, baseline_id)
        self._validate_run("ui", regression_ui_run_id, baseline_id)
        before_api = self._result_map("api", baseline_api)
        before_ui = self._result_map("ui", baseline_ui)
        after_api = self._result_map("api", regression_api_run_id)
        after_ui = self._result_map("ui", regression_ui_run_id)
        self._same_frozen_versions(before_api, after_api)
        self._same_frozen_versions(before_ui, after_ui)
        self._require_transition(before_api, after_api, API_SEEDED_CASE)
        self._require_transition(before_ui, after_ui, UI_SEEDED_CASE)
        api_seeded = after_api[API_SEEDED_CASE]
        ui_seeded = after_ui[UI_SEEDED_CASE]
        if api_seeded["expected_status"] != 400 or api_seeded["actual_status"] != 400:
            raise RegressionGateError("API_SEEDED_ORACLE_NOT_SATISFIED")
        ui_payload = json.loads(str(ui_seeded["result_json"]))
        observations = ui_payload.get("network_observations", [])
        if ui_seeded["actual_route"] != "/register" or not any(
            item.get("method") == "POST"
            and item.get("path") == "/api/auth/register"
            and item.get("status") == 400
            for item in observations
        ):
            raise RegressionGateError("UI_SEEDED_ORACLE_NOT_SATISFIED")
        guard_ids = API_GUARD_CASES | UI_GUARD_CASES
        missing = API_GUARD_CASES - after_api.keys() | UI_GUARD_CASES - after_ui.keys()
        if missing:
            raise RegressionGateError("REGRESSION_GUARD_MISSING:" + ",".join(sorted(missing)))
        guard_rows = {
            **{case_id: after_api[case_id] for case_id in API_GUARD_CASES},
            **{case_id: after_ui[case_id] for case_id in UI_GUARD_CASES},
        }
        failed = [case_id for case_id, row in guard_rows.items() if row["status"] != "PASS"]
        if failed:
            raise RegressionGateError("REGRESSION_GUARD_FAILED:" + ",".join(failed))
        trace = {
            "schema_version": "defect-regression-trace@1.0.0",
            "bug": {
                "bug_id": bug_id,
                "bug_version": bug["bug_version"],
                "canonical_bug_record_id": bug["canonical_bug_record_id"],
                "baseline_status": bug["status"],
            },
            "baseline_report_id": baseline_report_id,
            "frozen_baseline_id": baseline_id,
            "baseline_runs": {"api": baseline_api, "ui": baseline_ui},
            "regression_runs": {"api": regression_api_run_id, "ui": regression_ui_run_id},
            "seeded_transitions": {
                API_SEEDED_CASE: "FAIL->PASS",
                UI_SEEDED_CASE: "FAIL->PASS",
            },
            "guard_cases": sorted(guard_ids),
        }
        trace_json = _canonical(trace)
        trace_hash = _hash_text(trace_json)
        regression_id = new_id("RGR")
        event_id = new_id("BSE")
        with self.database.transaction() as connection:
            connection.execute(
                text(
                    "INSERT INTO defect_regression_runs(defect_regression_run_id,"
                    "canonical_bug_record_id,baseline_report_id,frozen_baseline_id,"
                    "baseline_api_test_run_id,baseline_ui_test_run_id,regression_api_test_run_id,"
                    "regression_ui_test_run_id,status,api_seeded_before,api_seeded_after,"
                    "ui_seeded_before,ui_seeded_after,guard_case_count,guard_pass_count,"
                    "trace_json,trace_hash) VALUES (:id,:bug,:report,:baseline,:before_api,"
                    ":before_ui,:after_api,:after_ui,'completed','FAIL','PASS','FAIL','PASS',"
                    ":guards,:guards,:trace,:hash)"
                ),
                {
                    "id": regression_id,
                    "bug": bug["canonical_bug_record_id"],
                    "report": baseline_report_id,
                    "baseline": baseline_id,
                    "before_api": baseline_api,
                    "before_ui": baseline_ui,
                    "after_api": regression_api_run_id,
                    "after_ui": regression_ui_run_id,
                    "guards": len(guard_ids),
                    "trace": trace_json,
                    "hash": trace_hash,
                },
            )
            connection.execute(
                text(
                    "INSERT INTO bug_status_events(bug_status_event_id,canonical_bug_record_id,"
                    "defect_regression_run_id,from_status,to_status,reason) VALUES "
                    "(:id,:bug,:run,'open','closed',:reason)"
                ),
                {
                    "id": event_id,
                    "bug": bug["canonical_bug_record_id"],
                    "run": regression_id,
                    "reason": (
                        "Both seeded frozen cases passed and all authentication guards passed."
                    ),
                },
            )
        return RegressionClosure(regression_id, event_id, "closed", trace_hash, len(guard_ids))

    @staticmethod
    def _verify_immutable_hash(
        row: dict[str, Any], payload_key: str, hash_key: str, error: str
    ) -> None:
        if _hash_text(str(row[payload_key])) != row[hash_key]:
            raise RegressionGateError(error)

    def _validate_run(self, kind: str, run_id: str, baseline_id: str) -> None:
        table, column = {
            "api": ("api_test_runs", "api_test_run_id"),
            "ui": ("ui_test_runs", "ui_test_run_id"),
        }[kind]
        row = self.database.fetch_one(
            f"SELECT * FROM {table} WHERE {column}=:id",  # noqa: S608 - fixed allowlist
            {"id": run_id},
        )
        if not row or row["status"] != "completed" or row["frozen_baseline_id"] != baseline_id:
            raise RegressionGateError(f"{kind.upper()}_RUN_INVALID")

    def _result_map(self, kind: str, run_id: str) -> dict[str, dict[str, Any]]:
        table, column = {
            "api": ("api_test_results", "api_test_run_id"),
            "ui": ("ui_test_results", "ui_test_run_id"),
        }[kind]
        rows = self.database.fetch_all(
            f"SELECT * FROM {table} WHERE {column}=:run",  # noqa: S608 - fixed allowlist
            {"run": run_id},
        )
        return {str(row["case_id"]): row for row in rows}

    @staticmethod
    def _same_frozen_versions(
        before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]]
    ) -> None:
        before_signature = {
            (case_id, row["case_version"], row["immutable_execution_snapshot_id"])
            for case_id, row in before.items()
        }
        after_signature = {
            (case_id, row["case_version"], row["immutable_execution_snapshot_id"])
            for case_id, row in after.items()
        }
        if before_signature != after_signature:
            raise RegressionGateError("FROZEN_CASE_VERSION_CHANGED")

    @staticmethod
    def _require_transition(
        before: dict[str, dict[str, Any]], after: dict[str, dict[str, Any]], case_id: str
    ) -> None:
        if case_id not in before or case_id not in after:
            raise RegressionGateError("SEEDED_CASE_MISSING:" + case_id)
        if before[case_id]["status"] != "FAIL" or after[case_id]["status"] != "PASS":
            raise RegressionGateError("SEEDED_CASE_NOT_FIXED:" + case_id)
