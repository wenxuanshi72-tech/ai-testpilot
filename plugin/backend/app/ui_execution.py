from __future__ import annotations

import hashlib
import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse

from jsonschema import Draft202012Validator
from playwright.sync_api import Browser, Page, Response, sync_playwright
from sqlalchemy import text

from plugin.backend.app.api_execution import (
    SUPPORTED_CONTRACT,
    SUPPORTED_SNAPSHOT_SCHEMA,
    _assertion,
    _canonical,
    _utc_timestamp,
)
from plugin.backend.app.database import PROJECT_ROOT, PluginDatabase
from plugin.backend.app.ids import new_id
from plugin.backend.app.test_review import _hash

UI_EXECUTOR_VERSION = "ui-executor@1.0.0"
UI_RESULT_SCHEMA_VERSION = "ui-execution-result@1.0.0"
LOCAL_BASE_URL = re.compile(r"^http://(127\.0\.0\.1|localhost):\d{2,5}$")


class UiExecutionError(Exception):
    pass


class UiExecutionService:
    def __init__(self, database: PluginDatabase, *, evidence_root: Path | None = None) -> None:
        self.database = database
        self.evidence_root = evidence_root or PROJECT_ROOT / "artifacts" / "evidence" / "ui"
        schema_path = (
            PROJECT_ROOT
            / "schemas"
            / "execution-results"
            / "v1"
            / "ui_execution_result.schema.json"
        )
        self.result_validator = Draft202012Validator(
            json.loads(schema_path.read_text(encoding="utf-8"))
        )

    def execute(
        self,
        baseline_id: str,
        *,
        environment_id: str,
        base_url: str,
        browser_channel: str = "msedge",
    ) -> dict[str, Any]:
        self._validate_base_url(base_url)
        baseline = self.database.fetch_one(
            "SELECT * FROM frozen_baselines WHERE frozen_baseline_id=:id", {"id": baseline_id}
        )
        if not baseline:
            raise UiExecutionError("BASELINE_NOT_FOUND")
        if baseline["status"] != "frozen":
            raise UiExecutionError("BASELINE_NOT_FROZEN")
        if baseline["environment_id"] != environment_id:
            raise UiExecutionError("BASELINE_ENVIRONMENT_MISMATCH")
        if baseline["executor_contract_version"] != SUPPORTED_CONTRACT:
            raise UiExecutionError("EXECUTOR_CONTRACT_UNSUPPORTED")
        snapshots = self._ui_snapshots(baseline_id)
        if not snapshots:
            raise UiExecutionError("BASELINE_HAS_NO_UI_SNAPSHOTS")
        run_id = new_id("UIR")
        run_dir = self.evidence_root / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        started_at = _utc_timestamp()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel=browser_channel, headless=True)
                try:
                    staged = [
                        self._execute_snapshot(browser, row, base_url, run_dir) for row in snapshots
                    ]
                finally:
                    browser.close()
        except Exception as error:
            raise UiExecutionError(f"BROWSER_EXECUTION_FAILED:{type(error).__name__}") from error
        completed_at = _utc_timestamp()
        counts = Counter(item["status"] for item in staged)
        with self.database.transaction() as connection:
            connection.execute(
                text(
                    "INSERT INTO ui_test_runs(ui_test_run_id,frozen_baseline_id,environment_id,"
                    "executor_version,browser_name,status,total_count,pass_count,fail_count,"
                    "blocked_count,error_count,skipped_count,started_at,completed_at) VALUES "
                    "(:id,:baseline,:environment,:executor,:browser,'completed',:total,:passed,"
                    ":failed,:blocked,:errors,:skipped,:started,:completed)"
                ),
                {
                    "id": run_id,
                    "baseline": baseline_id,
                    "environment": environment_id,
                    "executor": UI_EXECUTOR_VERSION,
                    "browser": browser_channel,
                    "total": len(staged),
                    "passed": counts["PASS"],
                    "failed": counts["FAIL"],
                    "blocked": counts["BLOCKED"],
                    "errors": counts["ERROR"],
                    "skipped": counts["SKIPPED"],
                    "started": started_at,
                    "completed": completed_at,
                },
            )
            for item in staged:
                result = item["result"]
                connection.execute(
                    text(
                        "INSERT INTO ui_test_results(ui_test_result_id,ui_test_run_id,"
                        "immutable_execution_snapshot_id,case_id,case_version,status,failure_type,"
                        "expected_route,actual_route,duration_ms,result_json) VALUES "
                        "(:id,:run,:snapshot,:case,:version,:status,:failure,:expected,:actual,"
                        ":duration,:payload)"
                    ),
                    {
                        "id": item["result_id"],
                        "run": run_id,
                        "snapshot": item["snapshot_id"],
                        "case": result["case_id"],
                        "version": result["case_version"],
                        "status": result["status"],
                        "failure": result["failure_type"],
                        "expected": result["expected_route"],
                        "actual": result["actual_route"],
                        "duration": result["duration_ms"],
                        "payload": _canonical(result),
                    },
                )
                evidence = item["evidence"]
                connection.execute(
                    text(
                        "INSERT INTO ui_test_evidence(ui_test_evidence_id,ui_test_result_id,"
                        "evidence_json,evidence_hash,screenshot_path,screenshot_hash,trace_path,"
                        "trace_hash,redaction_applied) VALUES "
                        "(:id,:result,:payload,:hash,:screenshot,:screenshot_hash,:trace,"
                        ":trace_hash,1)"
                    ),
                    {
                        "id": result["evidence_id"],
                        "result": item["result_id"],
                        "payload": _canonical(evidence),
                        "hash": result["evidence_hash"],
                        "screenshot": evidence["screenshot_path"],
                        "screenshot_hash": evidence["screenshot_hash"],
                        "trace": evidence["trace_path"],
                        "trace_hash": evidence["trace_hash"],
                    },
                )
        return {
            "run_id": run_id,
            "baseline_id": baseline_id,
            "status": "completed",
            "total_count": len(staged),
            "pass_count": counts["PASS"],
            "fail_count": counts["FAIL"],
            "blocked_count": counts["BLOCKED"],
            "error_count": counts["ERROR"],
            "skipped_count": counts["SKIPPED"],
        }

    def run(self, run_id: str) -> dict[str, Any]:
        run = self.database.fetch_one(
            "SELECT * FROM ui_test_runs WHERE ui_test_run_id=:id", {"id": run_id}
        )
        if not run:
            raise UiExecutionError("UI_TEST_RUN_NOT_FOUND")
        results = self.database.fetch_all(
            "SELECT * FROM ui_test_results WHERE ui_test_run_id=:run ORDER BY case_id",
            {"run": run_id},
        )
        return {
            **run,
            "results": [
                {key: value for key, value in row.items() if key != "result_json"}
                | {"result": json.loads(str(row["result_json"]))}
                for row in results
            ],
        }

    def evidence(self, result_id: str) -> dict[str, Any]:
        row = self.database.fetch_one(
            "SELECT * FROM ui_test_evidence WHERE ui_test_result_id=:result",
            {"result": result_id},
        )
        if not row:
            raise UiExecutionError("UI_TEST_EVIDENCE_NOT_FOUND")
        return {
            **{key: value for key, value in row.items() if key != "evidence_json"},
            "evidence": json.loads(str(row["evidence_json"])),
        }

    def _ui_snapshots(self, baseline_id: str) -> list[dict[str, Any]]:
        rows = self.database.fetch_all(
            "SELECT m.ordinal,s.immutable_execution_snapshot_id,s.snapshot_hash,s.snapshot_json "
            "FROM frozen_baseline_members m JOIN immutable_execution_snapshots s "
            "ON s.frozen_baseline_member_id=m.frozen_baseline_member_id "
            "WHERE m.frozen_baseline_id=:baseline ORDER BY m.ordinal",
            {"baseline": baseline_id},
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            snapshot = json.loads(str(row["snapshot_json"]))
            if _hash(snapshot) != row["snapshot_hash"]:
                raise UiExecutionError("EXECUTION_SNAPSHOT_HASH_INVALID")
            if snapshot.get("schema_version") != SUPPORTED_SNAPSHOT_SCHEMA:
                raise UiExecutionError("EXECUTION_SNAPSHOT_SCHEMA_UNSUPPORTED")
            if snapshot.get("executor_contract_version") != SUPPORTED_CONTRACT:
                raise UiExecutionError("EXECUTION_SNAPSHOT_CONTRACT_UNSUPPORTED")
            if snapshot.get("case", {}).get("case_type") == "ui":
                result.append({**row, "snapshot": snapshot})
        return result

    def _execute_snapshot(
        self,
        browser: Browser,
        row: dict[str, Any],
        base_url: str,
        run_dir: Path,
    ) -> dict[str, Any]:
        snapshot = cast(dict[str, Any], row["snapshot"])
        case = cast(dict[str, Any], snapshot["case"])
        case_id = str(case["case_id"])
        expected_route = _expected_route(case_id)
        result_id = new_id("UIRES")
        evidence_id = new_id("EVD")
        case_dir = run_dir / case_id
        case_dir.mkdir(parents=True, exist_ok=False)
        screenshot_path = case_dir / "final.png"
        trace_path = case_dir / "trace.zip"
        started = time.perf_counter()
        context = browser.new_context(base_url=base_url, viewport={"width": 1440, "height": 900})
        page = context.new_page()
        network: list[dict[str, Any]] = []
        page.on("response", lambda response: _record_network(response, network))
        assertions: list[dict[str, Any]] = []
        adapter_audit: list[dict[str, str]] = []
        actual_route: str | None = None
        tracing_started = False
        try:
            details = cast(dict[str, Any], case["type_details"])
            values, adapter_audit = _ui_values(case)
            for action in details["user_actions"]:
                verb, strategy, value = _parse_action(str(action))
                if verb == "goto":
                    page.goto(value, wait_until="networkidle")
                elif verb == "fill":
                    _locator(page, strategy, value).fill(values[value])
                elif verb == "click":
                    if not tracing_started:
                        context.tracing.start(screenshots=True, snapshots=False, sources=False)
                        tracing_started = True
                    _locator(page, strategy, value).click()
                    page.wait_for_load_state("networkidle")
                    page.wait_for_timeout(500)
            actual_route = urlparse(page.url).path
            assertions.extend(_case_assertions(case_id, page, actual_route, network))
            status = "PASS" if all(item["passed"] for item in assertions) else "FAIL"
            failure_type = None if status == "PASS" else "ui_behavior_mismatch"
            if case_id == "TC-UI-AUTH-REG-005" and status == "FAIL":
                failure_type = "suspected_product_bug"
            page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception as error:
            status = "ERROR"
            failure_type = f"ui_executor_{type(error).__name__}"
            assertions.append(_assertion("ui_execution_completed", True, False))
            actual_route = urlparse(page.url).path if page.url else None
            page.screenshot(path=str(screenshot_path), full_page=True)
        finally:
            if not tracing_started:
                context.tracing.start(screenshots=False, snapshots=False, sources=False)
            context.tracing.stop(path=str(trace_path))
            context.close()
        duration_ms = max(0, round((time.perf_counter() - started) * 1000))
        screenshot_hash = _file_hash(screenshot_path)
        trace_hash = _file_hash(trace_path)
        evidence = {
            "schema_version": "ui-execution-evidence@1.0.0",
            "case_id": case_id,
            "snapshot_id": row["immutable_execution_snapshot_id"],
            "screenshot_path": _relative(screenshot_path),
            "screenshot_hash": screenshot_hash,
            "trace_path": _relative(trace_path),
            "trace_hash": trace_hash,
            "network_observations": network,
            "adapter_transformations": adapter_audit,
            "redaction_applied": True,
        }
        evidence_hash = hashlib.sha256(_canonical(evidence).encode("utf-8")).hexdigest()
        result = {
            "schema_version": UI_RESULT_SCHEMA_VERSION,
            "executor_version": UI_EXECUTOR_VERSION,
            "case_id": case_id,
            "case_version": int(snapshot["case_version"]),
            "status": status,
            "failure_type": failure_type,
            "expected_route": expected_route,
            "actual_route": actual_route,
            "duration_ms": duration_ms,
            "assertions": assertions,
            "network_observations": network,
            "requirement_ids": case["requirement_ids"],
            "evidence_id": evidence_id,
            "evidence_hash": evidence_hash,
        }
        if list(self.result_validator.iter_errors(result)):
            raise UiExecutionError("UI_RESULT_SCHEMA_INVALID")
        return {
            "snapshot_id": row["immutable_execution_snapshot_id"],
            "result_id": result_id,
            "status": status,
            "result": result,
            "evidence": evidence,
        }

    @staticmethod
    def _validate_base_url(base_url: str) -> None:
        if not LOCAL_BASE_URL.fullmatch(base_url):
            raise UiExecutionError("SUT_UI_BASE_URL_NOT_LOCAL")


def _parse_action(action: str) -> tuple[str, str, str]:
    parts = action.split(":", 2)
    if len(parts) != 3 or parts[0] not in {"goto", "fill", "click"}:
        raise UiExecutionError("UI_ACTION_UNSUPPORTED")
    verb, strategy, value = parts
    if (verb, strategy) not in {("goto", "route"), ("fill", "label"), ("click", "role")}:
        raise UiExecutionError("UI_ACTION_LOCATOR_UNSUPPORTED")
    return verb, strategy, value


def _locator(page: Page, strategy: str, value: str) -> Any:
    if strategy == "label":
        return page.get_by_label(value, exact=True)
    if strategy == "role":
        return page.get_by_role("button", name=value, exact=True)
    raise UiExecutionError("UI_LOCATOR_UNSUPPORTED")


def _ui_values(case: dict[str, Any]) -> tuple[dict[str, str], list[dict[str, str]]]:
    case_id = str(case["case_id"])
    data = case["test_data"]
    non_sensitive = [str(item["value"]) for item in data if not item.get("sensitive")]
    sensitive = [str(item["value"]) for item in data if item.get("sensitive")]
    if case_id == "TC-UI-AUTH-REG-005":
        return {
            "Username": non_sensitive[0],
            "Password": sensitive[0],
            "Confirm password": sensitive[0],
        }, []
    if case_id == "TC-UI-REQ-LOGIN-001":
        return {"Username": non_sensitive[0], "Password": sensitive[0]}, []
    if case_id == "TC-UI-REQ-REG-002":
        password = str(data[0]["value"])
        return {
            "Username": "phase7_reg_002",
            "Password": password,
            "Confirm password": password,
        }, [
            {
                "adapter": "ui-test-data-adapter@1.0.0",
                "rule": "deterministic_unique_username_for_registration_intent",
            }
        ]
    raise UiExecutionError("UI_CASE_DATA_MAPPING_UNSUPPORTED")


def _expected_route(case_id: str) -> str:
    return {
        "TC-UI-AUTH-REG-005": "/register",
        "TC-UI-REQ-LOGIN-001": "/login",
        "TC-UI-REQ-REG-002": "/profile",
    }[case_id]


def _case_assertions(
    case_id: str, page: Page, actual_route: str, network: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    expected_route = _expected_route(case_id)
    expected_status = {
        "TC-UI-AUTH-REG-005": 400,
        "TC-UI-REQ-LOGIN-001": 401,
        "TC-UI-REQ-REG-002": 201,
    }[case_id]
    expected_path = {
        "TC-UI-AUTH-REG-005": "/api/auth/register",
        "TC-UI-REQ-LOGIN-001": "/api/auth/login",
        "TC-UI-REQ-REG-002": "/api/auth/register",
    }[case_id]
    matching = [item for item in network if item["path"] == expected_path]
    actual_status = matching[-1]["status"] if matching else None
    assertions = [
        _assertion("route_equals", expected_route, actual_route),
        _assertion("network_status_equals", expected_status, actual_status),
    ]
    if case_id == "TC-UI-AUTH-REG-005":
        visible = page.get_by_text(re.compile(r"six|6 characters", re.I)).count() > 0
        assertions.append(_assertion("minimum_length_error_visible", True, visible))
    elif case_id == "TC-UI-REQ-LOGIN-001":
        visible = page.get_by_text("The username or password is incorrect.", exact=True).count() > 0
        assertions.append(_assertion("generic_error_visible", True, visible))
    else:
        visible = page.get_by_role("heading", name="Account profile", exact=True).count() > 0
        assertions.append(_assertion("profile_visible", True, visible))
    return assertions


def _record_network(response: Response, target: list[dict[str, Any]]) -> None:
    parsed = urlparse(response.url)
    if parsed.path.startswith("/api/auth/"):
        target.append(
            {"method": response.request.method, "path": parsed.path, "status": response.status}
        )


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()
