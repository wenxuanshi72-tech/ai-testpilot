from __future__ import annotations

import hashlib
import json
import re
import tempfile
import time
from collections import Counter
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Protocol, cast

from flask import Flask
from flask.testing import FlaskClient
from jsonschema import Draft202012Validator
from sqlalchemy import select, text
from sut.backend.app import create_app as create_sut_app
from sut.backend.app.extensions import db as sut_db
from sut.backend.app.models import User, UserSession
from sut.backend.app.time import utc_now

from plugin.backend.app.database import PROJECT_ROOT, PluginDatabase
from plugin.backend.app.ids import new_id
from plugin.backend.app.test_review import _hash

API_EXECUTOR_VERSION = "api-executor@1.0.0"
API_RESULT_SCHEMA_VERSION = "api-execution-result@1.0.0"
SUPPORTED_SNAPSHOT_SCHEMA = "execution-snapshot@1.0.0"
SUPPORTED_CONTRACT = "test-executor@1.0.0"
VARIABLE_PATTERN = re.compile(r"^\$\{([A-Za-z0-9_]+)\}$")
SENSITIVE_KEYS = {"password", "password_confirmation", "authorization", "cookie", "token"}


class ApiExecutionError(Exception):
    pass


@dataclass(frozen=True)
class RuntimeResponse:
    status_code: int
    headers: dict[str, str]
    body: Any
    body_text: str


class SutRuntime(Protocol):
    def request(
        self, method: str, path: str, *, headers: Mapping[str, str], body: Any
    ) -> RuntimeResponse: ...

    def expire_current_session(self) -> None: ...

    def user_count(self, username: str) -> int: ...


class RuntimeFactory(Protocol):
    def __call__(self, case_id: str) -> AbstractContextManager[SutRuntime]: ...


class LocalFlaskSutRuntime(AbstractContextManager["LocalFlaskSutRuntime"]):
    def __init__(self, case_id: str) -> None:
        self.case_id = case_id
        runtime_root = PROJECT_ROOT / "tmp" / "api-execution"
        runtime_root.mkdir(parents=True, exist_ok=True)
        self._temporary = tempfile.TemporaryDirectory(prefix="ai-testpilot-api-", dir=runtime_root)
        database_path = Path(self._temporary.name) / "sut-case.db"
        self.app: Flask = create_sut_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path.as_posix()}",
                "SESSION_COOKIE_SECURE": False,
                "CORS_ALLOWED_ORIGINS": ["http://127.0.0.1:5173"],
            }
        )
        with self.app.app_context():
            sut_db.create_all()
        self.client: FlaskClient = self.app.test_client()

    def __enter__(self) -> LocalFlaskSutRuntime:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        del exc_type, exc_value, traceback
        with self.app.app_context():
            sut_db.session.remove()
            sut_db.drop_all()
            sut_db.engine.dispose()
        self._temporary.cleanup()

    def request(
        self, method: str, path: str, *, headers: Mapping[str, str], body: Any
    ) -> RuntimeResponse:
        response = self.client.open(
            path=path,
            method=method,
            headers=dict(headers),
            json=body if body is not None else None,
        )
        payload = response.get_json(silent=True)
        return RuntimeResponse(
            response.status_code,
            {key: value for key, value in response.headers.items()},
            payload,
            response.get_data(as_text=True),
        )

    def expire_current_session(self) -> None:
        with self.app.app_context():
            session = sut_db.session.scalar(select(UserSession).order_by(UserSession.id.desc()))
            if session is None:
                raise ApiExecutionError("SESSION_FIXTURE_MISSING_AUTHENTICATED_SESSION")
            session.expires_at = utc_now() - timedelta(seconds=1)
            sut_db.session.commit()

    def user_count(self, username: str) -> int:
        with self.app.app_context():
            return len(
                list(sut_db.session.scalars(select(User).where(User.username == username)).all())
            )


@dataclass(frozen=True)
class ApiRunResult:
    run_id: str
    baseline_id: str
    status: str
    total_count: int
    pass_count: int
    fail_count: int
    blocked_count: int
    error_count: int
    skipped_count: int


class ApiExecutionService:
    def __init__(
        self,
        database: PluginDatabase,
        runtime_factory: RuntimeFactory | None = None,
    ) -> None:
        self.database = database
        self.runtime_factory = runtime_factory or LocalFlaskSutRuntime
        schema_path = (
            PROJECT_ROOT
            / "schemas"
            / "execution-results"
            / "v1"
            / "api_execution_result.schema.json"
        )
        self.result_validator = Draft202012Validator(
            json.loads(schema_path.read_text(encoding="utf-8"))
        )

    def execute(self, baseline_id: str, *, environment_id: str) -> ApiRunResult:
        baseline = self.database.fetch_one(
            "SELECT * FROM frozen_baselines WHERE frozen_baseline_id=:id", {"id": baseline_id}
        )
        if not baseline:
            raise ApiExecutionError("BASELINE_NOT_FOUND")
        if baseline["status"] != "frozen":
            raise ApiExecutionError("BASELINE_NOT_FROZEN")
        if baseline["environment_id"] != environment_id:
            raise ApiExecutionError("BASELINE_ENVIRONMENT_MISMATCH")
        if baseline["executor_contract_version"] != SUPPORTED_CONTRACT:
            raise ApiExecutionError("EXECUTOR_CONTRACT_UNSUPPORTED")
        snapshots = self._api_snapshots(baseline_id)
        if not snapshots:
            raise ApiExecutionError("BASELINE_HAS_NO_API_SNAPSHOTS")
        started_at = _utc_timestamp()
        staged = [self._execute_snapshot(row) for row in snapshots]
        completed_at = _utc_timestamp()
        counts = Counter(item["status"] for item in staged)
        run_id = new_id("RUN")
        with self.database.transaction() as connection:
            connection.execute(
                text(
                    "INSERT INTO api_test_runs(api_test_run_id,frozen_baseline_id,environment_id,"
                    "executor_version,status,total_count,pass_count,fail_count,blocked_count,"
                    "error_count,skipped_count,started_at,completed_at) VALUES "
                    "(:id,:baseline,:environment,:executor,'completed',:total,:passed,:failed,"
                    ":blocked,:errors,:skipped,:started,:completed)"
                ),
                {
                    "id": run_id,
                    "baseline": baseline_id,
                    "environment": environment_id,
                    "executor": API_EXECUTOR_VERSION,
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
                        "INSERT INTO api_test_results(api_test_result_id,api_test_run_id,"
                        "immutable_execution_snapshot_id,case_id,case_version,status,failure_type,"
                        "expected_status,actual_status,duration_ms,result_json) VALUES "
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
                        "expected": result["expected_status"],
                        "actual": result["actual_status"],
                        "duration": result["duration_ms"],
                        "payload": _canonical(result),
                    },
                )
                connection.execute(
                    text(
                        "INSERT INTO api_test_evidence(api_test_evidence_id,api_test_result_id,"
                        "evidence_kind,evidence_json,evidence_hash,redaction_applied) VALUES "
                        "(:id,:result,'api_exchange',:payload,:hash,1)"
                    ),
                    {
                        "id": result["evidence_id"],
                        "result": item["result_id"],
                        "payload": _canonical(item["evidence"]),
                        "hash": result["evidence_hash"],
                    },
                )
        return ApiRunResult(
            run_id,
            baseline_id,
            "completed",
            len(staged),
            counts["PASS"],
            counts["FAIL"],
            counts["BLOCKED"],
            counts["ERROR"],
            counts["SKIPPED"],
        )

    def run(self, run_id: str) -> dict[str, Any]:
        run = self.database.fetch_one(
            "SELECT * FROM api_test_runs WHERE api_test_run_id=:id", {"id": run_id}
        )
        if not run:
            raise ApiExecutionError("API_TEST_RUN_NOT_FOUND")
        results = self.database.fetch_all(
            "SELECT api_test_result_id,immutable_execution_snapshot_id,case_id,case_version,"
            "status,failure_type,expected_status,actual_status,duration_ms,result_json,created_at "
            "FROM api_test_results WHERE api_test_run_id=:run ORDER BY case_id",
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
        evidence = self.database.fetch_one(
            "SELECT e.* FROM api_test_evidence e WHERE e.api_test_result_id=:result",
            {"result": result_id},
        )
        if not evidence:
            raise ApiExecutionError("API_TEST_EVIDENCE_NOT_FOUND")
        return {
            **{key: value for key, value in evidence.items() if key != "evidence_json"},
            "evidence": json.loads(str(evidence["evidence_json"])),
        }

    def _api_snapshots(self, baseline_id: str) -> list[dict[str, Any]]:
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
                raise ApiExecutionError("EXECUTION_SNAPSHOT_HASH_INVALID")
            if snapshot.get("schema_version") != SUPPORTED_SNAPSHOT_SCHEMA:
                raise ApiExecutionError("EXECUTION_SNAPSHOT_SCHEMA_UNSUPPORTED")
            if snapshot.get("executor_contract_version") != SUPPORTED_CONTRACT:
                raise ApiExecutionError("EXECUTION_SNAPSHOT_CONTRACT_UNSUPPORTED")
            if snapshot.get("case", {}).get("case_type") == "api":
                result.append({**row, "snapshot": snapshot})
        return result

    def _execute_snapshot(self, row: dict[str, Any]) -> dict[str, Any]:
        snapshot = cast(dict[str, Any], row["snapshot"])
        candidate = cast(dict[str, Any], snapshot["case"])
        case_id = str(candidate["case_id"])
        result_id = new_id("RES")
        evidence_id = new_id("EVD")
        started = time.perf_counter()
        exchanges: list[dict[str, Any]] = []
        expected_status = int(candidate["type_details"]["expected_status"])
        actual_status: int | None = None
        status = "ERROR"
        failure_type: str | None = "executor_error"
        assertions: list[dict[str, Any]] = []
        sensitive_values = _sensitive_values(candidate)
        transformations: list[dict[str, str]] = []
        try:
            variables = _variables(candidate)
            details = cast(dict[str, Any], candidate["type_details"])
            with self.runtime_factory(case_id) as runtime:
                setup_ok = True
                for index, setup in enumerate(details.get("setup_requests", [])):
                    body = _resolve(setup.get("request_body"), variables)
                    body, applied = _adapt_sut_request(str(setup["path"]), body)
                    transformations.extend(applied)
                    response = runtime.request(
                        str(setup["method"]),
                        str(setup["path"]),
                        headers={},
                        body=body,
                    )
                    exchanges.append(
                        _exchange(
                            f"setup-{index + 1}",
                            str(setup["method"]),
                            str(setup["path"]),
                            body,
                            response,
                            sensitive_values,
                        )
                    )
                    if response.status_code != int(setup["expected_status"]):
                        setup_ok = False
                        assertions.append(
                            _assertion(
                                "setup_status_equals",
                                int(setup["expected_status"]),
                                response.status_code,
                            )
                        )
                        break
                if not setup_ok:
                    status = "BLOCKED"
                    failure_type = "precondition_failed"
                else:
                    if details.get("session_handling") == "expired_session":
                        runtime.expire_current_session()
                    request_body = _resolve(details["request"].get("body"), variables)
                    request_body, applied = _adapt_sut_request(str(details["path"]), request_body)
                    transformations.extend(applied)
                    username = (
                        str(request_body.get("username"))
                        if isinstance(request_body, dict) and request_body.get("username")
                        else ""
                    )
                    before_count = runtime.user_count(username) if username else 0
                    response = runtime.request(
                        str(details["method"]),
                        str(details["path"]),
                        headers=cast(dict[str, str], details.get("headers", {})),
                        body=request_body,
                    )
                    actual_status = response.status_code
                    exchanges.append(
                        _exchange(
                            "test",
                            str(details["method"]),
                            str(details["path"]),
                            request_body,
                            response,
                            sensitive_values,
                        )
                    )
                    assertions.append(
                        _assertion("status_equals", expected_status, response.status_code)
                    )
                    assertions.append(
                        _assertion(
                            "response_contract",
                            _expected_response_envelope(expected_status),
                            _response_envelope(response.body),
                        )
                    )
                    assertions.append(
                        _assertion(
                            "sensitive_values_absent",
                            True,
                            not _contains_sensitive(response.body_text, sensitive_values),
                        )
                    )
                    if case_id == "TC-API-AUTH-REG-005" and username:
                        assertions.append(
                            _assertion(
                                "rejected_user_not_created",
                                before_count,
                                runtime.user_count(username),
                            )
                        )
                    passed = all(item["passed"] for item in assertions)
                    status = "PASS" if passed else "FAIL"
                    failure_type = None if passed else "product_behavior_mismatch"
                    if case_id == "TC-API-AUTH-REG-005" and not passed:
                        failure_type = "suspected_product_bug"
        except ApiExecutionError as error:
            status = "BLOCKED"
            failure_type = str(error)
            assertions.append(_assertion("fixture_available", True, False))
        except Exception as error:  # noqa: BLE001 - converted to safe deterministic ERROR
            status = "ERROR"
            failure_type = f"executor_{type(error).__name__}"
            assertions.append(_assertion("executor_completed", True, False))
        duration_ms = max(0, round((time.perf_counter() - started) * 1000))
        evidence = {
            "schema_version": "api-execution-evidence@1.0.0",
            "case_id": case_id,
            "snapshot_id": row["immutable_execution_snapshot_id"],
            "exchanges": exchanges,
            "adapter_transformations": transformations,
            "redaction_applied": True,
        }
        evidence_hash = hashlib.sha256(_canonical(evidence).encode("utf-8")).hexdigest()
        result = {
            "schema_version": API_RESULT_SCHEMA_VERSION,
            "executor_version": API_EXECUTOR_VERSION,
            "case_id": case_id,
            "case_version": int(snapshot["case_version"]),
            "status": status,
            "failure_type": failure_type,
            "expected_status": expected_status,
            "actual_status": actual_status,
            "duration_ms": duration_ms,
            "assertions": assertions or [_assertion("execution_completed", True, False)],
            "requirement_ids": candidate["requirement_ids"],
            "evidence_id": evidence_id,
            "evidence_hash": evidence_hash,
        }
        errors = sorted(self.result_validator.iter_errors(result), key=lambda item: list(item.path))
        if errors:
            raise ApiExecutionError("API_RESULT_SCHEMA_INVALID")
        return {
            "snapshot_id": row["immutable_execution_snapshot_id"],
            "result_id": result_id,
            "status": status,
            "result": result,
            "evidence": evidence,
        }


def _variables(candidate: dict[str, Any]) -> dict[str, Any]:
    return {str(item["name"]): item.get("value") for item in candidate.get("test_data", [])}


def _resolve(value: Any, variables: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        match = VARIABLE_PATTERN.fullmatch(value)
        if match:
            name = match.group(1)
            if name not in variables:
                raise ApiExecutionError("TEST_VARIABLE_UNRESOLVED")
            return variables[name]
        return value
    if isinstance(value, list):
        return [_resolve(item, variables) for item in value]
    if isinstance(value, dict):
        return {key: _resolve(item, variables) for key, item in value.items()}
    return value


def _adapt_sut_request(path: str, body: Any) -> tuple[Any, list[dict[str, str]]]:
    if path != "/api/auth/register" or not isinstance(body, dict):
        return body, []
    adapted = dict(body)
    transformations: list[dict[str, str]] = []
    if "confirmation" in adapted and "password_confirmation" not in adapted:
        adapted["password_confirmation"] = adapted.pop("confirmation")
        transformations.append(
            {
                "adapter": "sut-auth-api-adapter@1.0.0",
                "rule": "confirmation_to_password_confirmation",
            }
        )
    elif "password_confirmation" not in adapted and isinstance(adapted.get("password"), str):
        adapted["password_confirmation"] = adapted["password"]
        transformations.append(
            {
                "adapter": "sut-auth-api-adapter@1.0.0",
                "rule": "matching_confirmation_for_non_confirmation_intent",
            }
        )
    return adapted, transformations


def _sensitive_values(candidate: dict[str, Any]) -> set[str]:
    return {
        str(item["value"])
        for item in candidate.get("test_data", [])
        if item.get("sensitive") and item.get("value")
    }


def _redact(value: Any, sensitive_values: set[str], key: str = "") -> Any:
    if key.casefold() in SENSITIVE_KEYS:
        return "<redacted>"
    if isinstance(value, str):
        redacted = value
        for secret in sensitive_values:
            redacted = redacted.replace(secret, "<redacted>")
        return redacted
    if isinstance(value, list):
        return [_redact(item, sensitive_values) for item in value]
    if isinstance(value, dict):
        return {
            item_key: _redact(item, sensitive_values, item_key) for item_key, item in value.items()
        }
    return value


def _exchange(
    phase: str,
    method: str,
    path: str,
    body: Any,
    response: RuntimeResponse,
    sensitive_values: set[str],
) -> dict[str, Any]:
    return {
        "phase": phase,
        "request": {"method": method, "path": path, "body": _redact(body, sensitive_values)},
        "response": {
            "status": response.status_code,
            "content_type": response.headers.get("Content-Type"),
            "request_id": response.headers.get("X-Request-ID"),
            "body": _redact(response.body, sensitive_values),
        },
    }


def _response_envelope(body: Any) -> str:
    if body is None:
        return "empty"
    if isinstance(body, dict) and "error" in body:
        return "error"
    if isinstance(body, dict) and "data" in body:
        return "data"
    return "unknown"


def _expected_response_envelope(expected_status: int) -> str:
    if expected_status in {204, 205}:
        return "empty"
    return "error" if expected_status >= 400 else "data"


def _contains_sensitive(text_value: str, sensitive_values: set[str]) -> bool:
    lowered = text_value.casefold()
    return any(value and value.casefold() in lowered for value in sensitive_values) or any(
        marker in lowered for marker in ("traceback", "password_hash", "sqlite:///")
    )


def _assertion(name: str, expected: Any, actual: Any) -> dict[str, Any]:
    return {"assertion": name, "passed": expected == actual, "expected": expected, "actual": actual}


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _utc_timestamp() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")
