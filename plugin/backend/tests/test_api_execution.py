from __future__ import annotations

import json
from copy import deepcopy

import pytest
from flask.testing import FlaskClient
from sqlalchemy.exc import IntegrityError

from plugin.backend.app.api_execution import (
    API_EXECUTOR_VERSION,
    ApiExecutionError,
    ApiExecutionService,
    _adapt_sut_request,
    _expected_response_envelope,
    _response_envelope,
)
from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.providers import MockLLMProvider
from plugin.backend.app.test_generation import TestGenerationService as GenerationService
from plugin.backend.app.test_review import TestReviewService as ReviewService
from plugin.backend.tests.test_test_generation import PROJECT_ID, _seed_formal_requirements


@pytest.fixture
def formal_database(database: PluginDatabase) -> PluginDatabase:
    _seed_formal_requirements(database)
    return database


def _frozen_api_baseline(database: PluginDatabase) -> str:
    generation = GenerationService(database).start(
        PROJECT_ID, MockLLMProvider(), "phase7-api-execution"
    )
    review = ReviewService(database)
    collection = review.collection(generation.run_id)
    plan = review.mvp_classification_plan(generation.run_id)
    for item in collection["candidates"]:
        plan_item = next(row for row in plan["candidates"] if row["case_id"] == item["case_id"])
        review.review(
            generation.run_id,
            item["case_id"],
            reviewer_id="phase7-test-reviewer",
            decision="approve",
            automation_disposition=plan_item["proposed_disposition"],
            disposition_reason=plan_item["disposition_reason"],
            comment="Reviewed for the isolated API executor test baseline.",
            expected_content_hash=item["content_hash"],
        )
    return review.freeze(
        generation.run_id,
        frozen_by="phase7-test-reviewer",
        environment_id="local-test",
        executor_contract_version="test-executor@1.0.0",
    ).baseline_id


def test_api_executor_runs_frozen_api_subset_and_exposes_seeded_bug(
    formal_database: PluginDatabase,
) -> None:
    baseline_id = _frozen_api_baseline(formal_database)
    result = ApiExecutionService(formal_database).execute(baseline_id, environment_id="local-test")

    assert result.status == "completed"
    assert result.total_count == 9
    assert result.fail_count >= 1
    assert result.pass_count + result.fail_count + result.blocked_count + result.error_count == 9
    run = ApiExecutionService(formal_database).run(result.run_id)
    assert run["executor_version"] == API_EXECUTOR_VERSION
    assert len(run["results"]) == 9
    seeded = next(item for item in run["results"] if item["case_id"] == "TC-API-AUTH-REG-005")
    assert seeded["status"] == "FAIL"
    assert seeded["failure_type"] == "suspected_product_bug"
    assert seeded["expected_status"] == 400
    assert seeded["actual_status"] == 201
    assertions = seeded["result"]["assertions"]
    assert next(item for item in assertions if item["assertion"] == "status_equals") == {
        "assertion": "status_equals",
        "passed": False,
        "expected": 400,
        "actual": 201,
    }
    assert (
        next(item for item in assertions if item["assertion"] == "rejected_user_not_created")[
            "passed"
        ]
        is False
    )

    evidence_rows = formal_database.fetch_all(
        "SELECT api_test_result_id,evidence_json,evidence_hash,redaction_applied "
        "FROM api_test_evidence ORDER BY api_test_result_id"
    )
    assert len(evidence_rows) == 9
    serialized = json.dumps(evidence_rows, ensure_ascii=False).casefold()
    assert "test1234" not in serialized
    assert "password_hash" not in serialized
    assert "authorization" not in serialized
    assert all(row["redaction_applied"] == 1 for row in evidence_rows)


def test_api_executor_enforces_baseline_and_snapshot_integrity(
    formal_database: PluginDatabase,
) -> None:
    baseline_id = _frozen_api_baseline(formal_database)
    service = ApiExecutionService(formal_database)
    with pytest.raises(ApiExecutionError, match="BASELINE_ENVIRONMENT_MISMATCH"):
        service.execute(baseline_id, environment_id="wrong-environment")

    snapshot = formal_database.fetch_one(
        "SELECT immutable_execution_snapshot_id FROM immutable_execution_snapshots LIMIT 1"
    )
    assert snapshot
    with pytest.raises(IntegrityError, match="execution snapshots are immutable"):
        formal_database.execute(
            "UPDATE immutable_execution_snapshots SET snapshot_hash=:hash "
            "WHERE immutable_execution_snapshot_id=:id",
            {"hash": "0" * 64, "id": snapshot["immutable_execution_snapshot_id"]},
        )


def test_api_execution_records_are_immutable(formal_database: PluginDatabase) -> None:
    baseline_id = _frozen_api_baseline(formal_database)
    result = ApiExecutionService(formal_database).execute(baseline_id, environment_id="local-test")
    with pytest.raises(IntegrityError, match="api test runs are immutable"):
        formal_database.execute(
            "UPDATE api_test_runs SET status='failed' WHERE api_test_run_id=:id",
            {"id": result.run_id},
        )
    row = formal_database.fetch_one(
        "SELECT api_test_result_id FROM api_test_results WHERE api_test_run_id=:run LIMIT 1",
        {"run": result.run_id},
    )
    assert row
    with pytest.raises(IntegrityError, match="api test results are immutable"):
        formal_database.execute(
            "DELETE FROM api_test_results WHERE api_test_result_id=:id",
            {"id": row["api_test_result_id"]},
        )


def test_registration_adapter_is_explicit_and_non_mutating() -> None:
    source = {"username": "valid-user", "password": "Secret123", "confirmation": "Secret123"}
    adapted, audit = _adapt_sut_request("/api/auth/register", source)
    assert source == {
        "username": "valid-user",
        "password": "Secret123",
        "confirmation": "Secret123",
    }
    assert adapted["password_confirmation"] == "Secret123"
    assert "confirmation" not in adapted
    assert audit == [
        {
            "adapter": "sut-auth-api-adapter@1.0.0",
            "rule": "confirmation_to_password_confirmation",
        }
    ]
    unchanged, no_audit = _adapt_sut_request("/api/auth/login", deepcopy(source))
    assert unchanged == source
    assert no_audit == []


def test_no_content_response_uses_empty_response_contract() -> None:
    assert _expected_response_envelope(204) == "empty"
    assert _response_envelope(None) == "empty"
    assert _expected_response_envelope(201) == "data"
    assert _expected_response_envelope(401) == "error"


def test_api_execution_http_routes(formal_database: PluginDatabase, client: FlaskClient) -> None:
    baseline_id = _frozen_api_baseline(formal_database)
    response = client.post(
        f"/api/v1/frozen-baselines/{baseline_id}/api-executions",
        json={"environment_id": "local-test"},
    )
    assert response.status_code == 201
    run_id = response.get_json()["data"]["run_id"]
    run_response = client.get(f"/api/v1/api-test-runs/{run_id}")
    assert run_response.status_code == 200
    first_result = run_response.get_json()["data"]["results"][0]
    evidence_response = client.get(
        f"/api/v1/api-test-results/{first_result['api_test_result_id']}/evidence"
    )
    assert evidence_response.status_code == 200
    assert evidence_response.get_json()["data"]["redaction_applied"] == 1
