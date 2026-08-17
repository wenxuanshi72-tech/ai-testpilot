from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import pytest
from playwright.sync_api import Browser
from sqlalchemy.exc import IntegrityError

from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.ids import new_id
from plugin.backend.app.ui_execution import (
    UiExecutionError,
    UiExecutionService,
    _expected_route,
    _parse_action,
    _ui_values,
)
from plugin.backend.tests.test_api_execution import _frozen_api_baseline
from plugin.backend.tests.test_test_generation import _seed_formal_requirements


@pytest.fixture
def formal_database(database: PluginDatabase) -> PluginDatabase:
    _seed_formal_requirements(database)
    return database


def _case(case_id: str, test_data: list[dict[str, Any]]) -> dict[str, Any]:
    return {"case_id": case_id, "test_data": test_data}


def test_action_protocol_accepts_only_stable_bounded_locators() -> None:
    assert _parse_action("goto:route:/register") == ("goto", "route", "/register")
    assert _parse_action("fill:label:Username") == ("fill", "label", "Username")
    assert _parse_action("click:role:Create account") == (
        "click",
        "role",
        "Create account",
    )
    with pytest.raises(UiExecutionError, match="UI_ACTION_LOCATOR_UNSUPPORTED"):
        _parse_action("click:css:#submit")
    with pytest.raises(UiExecutionError, match="UI_ACTION_UNSUPPORTED"):
        _parse_action("evaluate:script")


def test_seeded_and_login_data_mapping_preserves_frozen_values() -> None:
    seeded, audit = _ui_values(
        _case(
            "TC-UI-AUTH-REG-005",
            [
                {"value": "z1234", "sensitive": False},
                {"value": "Test1234", "sensitive": True},
            ],
        )
    )
    assert seeded == {
        "Username": "z1234",
        "Password": "Test1234",
        "Confirm password": "Test1234",
    }
    assert audit == []
    login, _ = _ui_values(
        _case(
            "TC-UI-REQ-LOGIN-001",
            [
                {"value": "missing", "sensitive": False},
                {"value": "Password123!", "sensitive": True},
            ],
        )
    )
    assert login == {"Username": "missing", "Password": "Password123!"}


def test_registration_data_adapter_is_deterministic_and_audited() -> None:
    values, audit = _ui_values(
        _case("TC-UI-REQ-REG-002", [{"value": "Test1234", "sensitive": False}])
    )
    assert values == {
        "Username": "phase7_reg_002",
        "Password": "Test1234",
        "Confirm password": "Test1234",
    }
    assert audit == [
        {
            "adapter": "ui-test-data-adapter@1.0.0",
            "rule": "deterministic_unique_username_for_registration_intent",
        }
    ]


def test_expected_routes_are_explicit() -> None:
    assert _expected_route("TC-UI-AUTH-REG-005") == "/register"
    assert _expected_route("TC-UI-REQ-LOGIN-001") == "/login"
    assert _expected_route("TC-UI-REQ-REG-002") == "/profile"


def test_ui_service_rejects_non_local_targets(database: Any) -> None:
    service = UiExecutionService(database)
    with pytest.raises(UiExecutionError, match="SUT_UI_BASE_URL_NOT_LOCAL"):
        service.execute(
            "FBL-MISSING",
            environment_id="local-windows-demo",
            base_url="https://example.com",
        )


class _FakeBrowser:
    def close(self) -> None:
        return None


class _FakeTracing:
    def start(self, **_kwargs: Any) -> None:
        return None

    def stop(self, *, path: str) -> None:
        Path(path).write_bytes(b"safe-playwright-trace")


class _FakeRequest:
    method = "POST"


class _FakeResponse:
    def __init__(self, path: str, status: int) -> None:
        self.url = f"http://127.0.0.1:5001{path}"
        self.status = status
        self.request = _FakeRequest()


class _FakeLocator:
    def __init__(self, page: _FakePage, value: str) -> None:
        self.page = page
        self.value = value

    def fill(self, value: str) -> None:
        self.page.values[self.value] = value

    def click(self) -> None:
        self.page.submit()

    def count(self) -> int:
        if self.value == "minimum":
            return 0
        return 1


class _FakePage:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.url = base_url
        self.values: dict[str, str] = {}
        self._response_listener: Any = None

    def on(self, _event: str, callback: Any) -> None:
        self._response_listener = callback

    def goto(self, route: str, **_kwargs: Any) -> None:
        self.url = self.base_url + route

    def get_by_label(self, value: str, **_kwargs: Any) -> _FakeLocator:
        return _FakeLocator(self, value)

    def get_by_role(self, _role: str, *, name: str, **_kwargs: Any) -> _FakeLocator:
        return _FakeLocator(self, name)

    def get_by_text(self, value: Any, **_kwargs: Any) -> _FakeLocator:
        marker = "minimum" if hasattr(value, "search") else str(value)
        return _FakeLocator(self, marker)

    def wait_for_load_state(self, _state: str) -> None:
        return None

    def wait_for_timeout(self, _milliseconds: int) -> None:
        return None

    def screenshot(self, *, path: str, **_kwargs: Any) -> None:
        Path(path).write_bytes(b"safe-png-evidence")

    def submit(self) -> None:
        route = self.url.removeprefix(self.base_url)
        if route == "/login":
            path, status = "/api/auth/login", 401
        else:
            path, status = "/api/auth/register", 201
            self.url = self.base_url + "/profile"
        self._response_listener(_FakeResponse(path, status))


class _FakeContext:
    def __init__(self, base_url: str) -> None:
        self.page = _FakePage(base_url)
        self.tracing = _FakeTracing()

    def new_page(self) -> _FakePage:
        return self.page

    def close(self) -> None:
        return None


class _ExecutionBrowser:
    def new_context(self, *, base_url: str, **_kwargs: Any) -> _FakeContext:
        return _FakeContext(base_url)


class _FakeChromium:
    def launch(self, **_kwargs: Any) -> _FakeBrowser:
        return _FakeBrowser()


class _FakePlaywright:
    chromium = _FakeChromium()

    def __enter__(self) -> _FakePlaywright:
        return self

    def __exit__(self, *_args: Any) -> None:
        return None


def test_ui_service_atomically_persists_results_and_evidence(
    formal_database: PluginDatabase,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    baseline_id = _frozen_api_baseline(formal_database)
    service = UiExecutionService(formal_database, evidence_root=tmp_path / "evidence")
    monkeypatch.setattr("plugin.backend.app.ui_execution.sync_playwright", _FakePlaywright)

    def staged(_browser: Any, row: dict[str, Any], _base: str, _run_dir: Any) -> dict[str, Any]:
        snapshot = row["snapshot"]
        case_id = snapshot["case_id"]
        evidence_id = new_id("EVD")
        result_id = "UIRES-" + case_id.replace("TC-UI-", "")
        evidence = {
            "screenshot_path": f"artifacts/evidence/ui/{case_id}/final.png",
            "screenshot_hash": "1" * 64,
            "trace_path": f"artifacts/evidence/ui/{case_id}/trace.zip",
            "trace_hash": "2" * 64,
        }
        result = {
            "case_id": case_id,
            "case_version": snapshot["case_version"],
            "status": "FAIL" if case_id.endswith("005") else "PASS",
            "failure_type": "suspected_product_bug" if case_id.endswith("005") else None,
            "expected_route": "/register",
            "actual_route": "/profile" if case_id.endswith("005") else "/register",
            "duration_ms": 1,
            "evidence_id": evidence_id,
            "evidence_hash": hashlib.sha256(case_id.encode()).hexdigest(),
        }
        return {
            "snapshot_id": row["immutable_execution_snapshot_id"],
            "result_id": result_id,
            "status": result["status"],
            "result": result,
            "evidence": evidence,
        }

    monkeypatch.setattr(service, "_execute_snapshot", staged)
    result = service.execute(
        baseline_id,
        environment_id="local-test",
        base_url="http://127.0.0.1:5173",
    )
    assert result["total_count"] == 1
    assert result["fail_count"] == 1
    assert result["pass_count"] == 0
    run = service.run(result["run_id"])
    assert len(run["results"]) == 1
    evidence = service.evidence(run["results"][0]["ui_test_result_id"])
    assert evidence["redaction_applied"] == 1
    with pytest.raises(IntegrityError, match="ui test runs are immutable"):
        formal_database.execute(
            "UPDATE ui_test_runs SET status='failed' WHERE ui_test_run_id=:run",
            {"run": result["run_id"]},
        )


@pytest.mark.parametrize(
    ("case_id", "actions", "test_data", "expected_status", "failure_type"),
    [
        (
            "TC-UI-AUTH-REG-005",
            [
                "goto:route:/register",
                "fill:label:Username",
                "fill:label:Password",
                "fill:label:Confirm password",
                "click:role:Create account",
            ],
            [
                {"value": "z1234", "sensitive": False},
                {"value": "Test1234", "sensitive": True},
            ],
            201,
            "suspected_product_bug",
        ),
        (
            "TC-UI-REQ-LOGIN-001",
            [
                "goto:route:/login",
                "fill:label:Username",
                "fill:label:Password",
                "click:role:Sign in",
            ],
            [
                {"value": "missing", "sensitive": False},
                {"value": "Password123!", "sensitive": True},
            ],
            401,
            None,
        ),
        (
            "TC-UI-REQ-REG-002",
            [
                "goto:route:/register",
                "fill:label:Username",
                "fill:label:Password",
                "fill:label:Confirm password",
                "click:role:Create account",
            ],
            [{"value": "Test1234", "sensitive": False}],
            201,
            None,
        ),
    ],
)
def test_ui_snapshot_execution_records_deterministic_verdict_and_artifacts(
    database: PluginDatabase,
    tmp_path: Path,
    case_id: str,
    actions: list[str],
    test_data: list[dict[str, Any]],
    expected_status: int,
    failure_type: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("plugin.backend.app.ui_execution._relative", lambda path: path.name)
    service = UiExecutionService(database, evidence_root=tmp_path)
    row = {
        "immutable_execution_snapshot_id": "IES-" + "A" * 32,
        "snapshot": {
            "case_version": 2,
            "case": {
                "case_id": case_id,
                "requirement_ids": ["REQ-TEST-001"],
                "test_data": test_data,
                "type_details": {"user_actions": actions},
            },
        },
    }
    staged = service._execute_snapshot(
        cast(Browser, _ExecutionBrowser()), row, "http://127.0.0.1:5173", tmp_path
    )
    result = staged["result"]
    assert result["network_observations"][-1]["status"] == expected_status
    assert result["failure_type"] == failure_type
    assert Path(tmp_path / case_id / "final.png").is_file()
    assert Path(tmp_path / case_id / "trace.zip").is_file()
