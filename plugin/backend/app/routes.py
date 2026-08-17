from __future__ import annotations

import os
from typing import Any, cast

from flask import Blueprint, current_app, jsonify, request

from plugin.backend.app.analysis import (
    AnalysisService,
    AnalysisValidationError,
    content_hash,
    normalize_prd,
)
from plugin.backend.app.api_execution import ApiExecutionError, ApiExecutionService
from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.errors import ApiError, request_id
from plugin.backend.app.ids import new_id
from plugin.backend.app.prompts import PROMPT_VERSION, SCHEMA_VERSION, PromptRegistry
from plugin.backend.app.providers import DeepSeekProvider, LLMProvider, MockLLMProvider
from plugin.backend.app.test_generation import TestGenerationError, TestGenerationService
from plugin.backend.app.test_review import TestReviewError, TestReviewService
from plugin.backend.app.ui_execution import UiExecutionError, UiExecutionService

api = Blueprint("plugin_api", __name__, url_prefix="/api/v1")


def _database() -> PluginDatabase:
    return cast(PluginDatabase, current_app.extensions["plugin_database"])


def _json_object() -> dict[str, Any]:
    if not request.is_json:
        raise ApiError("UNSUPPORTED_MEDIA_TYPE", "A JSON request body is required.", 415)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ApiError("INVALID_JSON", "The JSON body must be an object.", 400)
    return payload


def _provider(mode: str) -> LLMProvider:
    if mode == "mock":
        return MockLLMProvider()
    if mode != "real":
        raise ApiError(
            "VALIDATION_ERROR",
            "provider_mode must be real or mock.",
            422,
            [{"field": "provider_mode", "code": "invalid_enum"}],
        )
    return DeepSeekProvider(
        base_url=current_app.config["DEEPSEEK_BASE_URL"],
        model=current_app.config["DEEPSEEK_MODEL"],
        timeout_seconds=current_app.config["LLM_TIMEOUT_SECONDS"],
        max_tokens=current_app.config["LLM_MAX_OUTPUT_TOKENS"],
        prompts=PromptRegistry(),
    )


def _analysis_service() -> AnalysisService:
    return AnalysisService(
        _database(),
        batch_max_chars=current_app.config["PRD_BATCH_MAX_CHARS"],
        batch_max_requirements=current_app.config["PRD_BATCH_MAX_REQUIREMENTS"],
        max_retries=current_app.config["LLM_MAX_RETRIES"],
        call_max_output_tokens=current_app.config["LLM_MAX_OUTPUT_TOKENS"],
        run_max_output_tokens=current_app.config["LLM_RUN_MAX_OUTPUT_TOKENS"],
    )


def _test_generation_service() -> TestGenerationService:
    return TestGenerationService(
        _database(),
        max_requirements_per_batch=current_app.config["TEST_GENERATION_MAX_REQUIREMENTS_PER_BATCH"],
        max_cases_per_batch=current_app.config["TEST_GENERATION_MAX_CASES_PER_BATCH"],
        max_tokens_per_batch=current_app.config["TEST_GENERATION_MAX_OUTPUT_TOKENS"],
        max_retries=current_app.config["TEST_GENERATION_MAX_RETRIES"],
        max_corrections_per_batch=current_app.config["TEST_GENERATION_MAX_CORRECTIONS_PER_BATCH"],
        max_corrections_per_run=current_app.config["TEST_GENERATION_MAX_CORRECTIONS_PER_RUN"],
        max_provider_retries_per_batch=current_app.config[
            "TEST_GENERATION_MAX_PROVIDER_RETRIES_PER_BATCH"
        ],
        max_provider_retries_per_run=current_app.config[
            "TEST_GENERATION_MAX_PROVIDER_RETRIES_PER_RUN"
        ],
        max_total_provider_calls=current_app.config["TEST_GENERATION_MAX_TOTAL_PROVIDER_CALLS"],
        max_run_cost_usd=current_app.config["TEST_GENERATION_MAX_COST_USD"],
    )


def _test_review_service() -> TestReviewService:
    return TestReviewService(_database())


def _api_execution_service() -> ApiExecutionService:
    return ApiExecutionService(_database())


def _ui_execution_service() -> UiExecutionService:
    return UiExecutionService(_database())


@api.get("/health")
def health() -> tuple[Any, int]:
    database_ready = _database().fetch_one("SELECT 1 AS ready") == {"ready": 1}
    return jsonify(
        {
            "data": {
                "status": "ready" if database_ready else "degraded",
                "database": "plugin",
                "real_provider_configured": bool(os.getenv("DEEPSEEK_API_KEY", "").strip()),
            },
            "meta": {"request_id": request_id()},
        }
    ), 200


@api.post("/projects")
def create_project() -> tuple[Any, int]:
    payload = _json_object()
    name = str(payload.get("name", "")).strip()
    if not 1 <= len(name) <= 120:
        raise ApiError(
            "VALIDATION_ERROR",
            "Project name must contain 1 to 120 characters.",
            422,
            [{"field": "name", "code": "invalid_length"}],
        )
    project = _database().create_project(name)
    return jsonify({"data": project, "meta": {"request_id": request_id()}}), 201


@api.post("/projects/<project_id>/prds")
def import_prd(project_id: str) -> tuple[Any, int]:
    if not _database().fetch_one(
        "SELECT project_id FROM projects WHERE project_id=:id", {"id": project_id}
    ):
        raise ApiError("NOT_FOUND", "The project was not found.", 404)
    if request.is_json:
        payload = _json_object()
        title = str(payload.get("title", "")).strip()
        content = str(payload.get("content", ""))
        media_type = str(payload.get("media_type", "text/markdown"))
    elif "file" in request.files:
        uploaded = request.files["file"]
        title = str(request.form.get("title") or uploaded.filename or "").strip()
        media_type = uploaded.mimetype or "text/plain"
        try:
            content = uploaded.read().decode("utf-8")
        except UnicodeDecodeError as error:
            raise ApiError("INVALID_ENCODING", "PRD content must be UTF-8.", 422) from error
    else:
        raise ApiError(
            "UNSUPPORTED_MEDIA_TYPE",
            "Use JSON or a multipart file field named file.",
            415,
        )
    if media_type not in {"text/markdown", "text/plain"}:
        raise ApiError("INVALID_MEDIA_TYPE", "Only Markdown or plain text is accepted.", 415)
    if not 1 <= len(title) <= 200:
        raise ApiError("VALIDATION_ERROR", "PRD title is required.", 422)
    try:
        normalized = normalize_prd(content)
    except AnalysisValidationError as error:
        raise ApiError("VALIDATION_ERROR", "PRD content is empty.", 422) from error
    if len(normalized.encode("utf-8")) > 1_000_000:
        raise ApiError("PAYLOAD_TOO_LARGE", "PRD content exceeds the local limit.", 413)
    version = _database().import_prd(
        project_id, title, normalized, content_hash(normalized), media_type
    )
    return jsonify({"data": version, "meta": {"request_id": request_id()}}), 201


@api.post("/prd-versions/<version_id>/analysis-runs")
def create_analysis(version_id: str) -> tuple[Any, int]:
    payload = _json_object()
    mode = str(payload.get("provider_mode", "")).strip()
    provider = _provider(mode)
    key = (
        request.headers.get("Idempotency-Key")
        or str(payload.get("idempotency_key", "")).strip()
        or new_id("IDEM")
    )
    if len(key) > 160:
        raise ApiError("VALIDATION_ERROR", "Idempotency key is too long.", 422)
    try:
        run = _analysis_service().start(version_id, provider, key)
    except AnalysisValidationError as error:
        if str(error) == "PRD_VERSION_NOT_FOUND":
            raise ApiError("NOT_FOUND", "The PRD version was not found.", 404) from error
        raise ApiError("ANALYSIS_ERROR", "Analysis could not be created.", 422) from error
    return jsonify(
        {
            "data": run,
            "meta": {
                "request_id": request_id(),
                "provider": provider.metadata.provider,
                "provider_mode": provider.metadata.provider_mode,
                "prompt_version": PROMPT_VERSION,
                "schema_version": SCHEMA_VERSION,
            },
        }
    ), 202


@api.get("/analysis-runs/<analysis_run_id>")
def get_analysis(analysis_run_id: str) -> tuple[Any, int]:
    run = _database().fetch_one(
        "SELECT * FROM analysis_runs WHERE analysis_run_id=:id", {"id": analysis_run_id}
    )
    if not run:
        raise ApiError("NOT_FOUND", "The analysis run was not found.", 404)
    batches = _database().fetch_all(
        "SELECT analysis_batch_id, batch_index, source_section, input_hash, status, "
        "retry_count, reported_count, actual_count, finish_reason, validation_status, "
        "error_type, created_at, completed_at FROM analysis_batches "
        "WHERE analysis_run_id=:id ORDER BY batch_index",
        {"id": analysis_run_id},
    )
    calls = _database().fetch_all(
        "SELECT llm_call_id, analysis_batch_id, call_type, provider, model, provider_mode, "
        "provider_request_id, retry_count, http_status, finish_reason, input_tokens, "
        "output_tokens, max_tokens, latency_ms, validation_status, error_type, created_at "
        "FROM llm_call_logs WHERE analysis_run_id=:id ORDER BY created_at, llm_call_id",
        {"id": analysis_run_id},
    )
    return jsonify(
        {
            "data": {**run, "batches": batches, "llm_calls": calls},
            "meta": {
                "request_id": request_id(),
                "provider": run["provider"],
                "provider_mode": run["provider_mode"],
            },
        }
    ), 200


@api.get("/analysis-runs/<analysis_run_id>/requirements")
def analysis_requirements(analysis_run_id: str) -> tuple[Any, int]:
    run = _database().fetch_one(
        "SELECT project_id FROM analysis_runs WHERE analysis_run_id=:id",
        {"id": analysis_run_id},
    )
    if not run:
        raise ApiError("NOT_FOUND", "The analysis run was not found.", 404)
    return _requirements_response(str(run["project_id"]), analysis_run_id)


@api.get("/projects/<project_id>/requirements")
def project_requirements(project_id: str) -> tuple[Any, int]:
    return _requirements_response(project_id, None)


@api.get("/projects/<project_id>/test-generation-plan")
def test_generation_plan(project_id: str) -> tuple[Any, int]:
    try:
        plan = _test_generation_service().preflight(project_id)
    except TestGenerationError as error:
        raise ApiError("GENERATION_PREFLIGHT_ERROR", str(error), 422) from error
    return jsonify({"data": plan, "meta": {"request_id": request_id()}}), 200


@api.post("/projects/<project_id>/test-generation-runs")
def create_test_generation_run(project_id: str) -> tuple[Any, int]:
    payload = _json_object()
    provider = _provider(str(payload.get("provider_mode", "")).strip())
    key = (
        request.headers.get("Idempotency-Key")
        or str(payload.get("idempotency_key", "")).strip()
        or new_id("IDEM")
    )
    if len(key) > 160:
        raise ApiError("VALIDATION_ERROR", "Idempotency key is too long.", 422)
    try:
        result = _test_generation_service().start(project_id, provider, key)
    except TestGenerationError as error:
        raise ApiError("TEST_GENERATION_ERROR", str(error), 422) from error
    return jsonify({"data": result.__dict__, "meta": {"request_id": request_id()}}), 202


@api.get("/test-generation-runs/<run_id>")
def get_test_generation_run(run_id: str) -> tuple[Any, int]:
    run = _database().fetch_one(
        "SELECT * FROM test_generation_runs WHERE test_generation_run_id=:id", {"id": run_id}
    )
    if not run:
        raise ApiError("NOT_FOUND", "The test generation run was not found.", 404)
    batches = _database().fetch_all(
        "SELECT test_generation_batch_id,batch_key,batch_index,case_type,"
        "requirement_ids_json,input_hash,max_cases,max_tokens,status,retry_count,"
        "reported_count,actual_count,finish_reason,validation_status,error_type,created_at,"
        "completed_at FROM test_generation_batches WHERE test_generation_run_id=:run "
        "ORDER BY batch_index",
        {"run": run_id},
    )
    return jsonify({"data": {**run, "batches": batches}, "meta": {"request_id": request_id()}}), 200


@api.get("/test-generation-runs/<run_id>/candidate-collection")
def phase6_candidate_collection(run_id: str) -> tuple[Any, int]:
    try:
        collection = _test_generation_service().phase6_candidate_collection(run_id)
    except TestGenerationError as error:
        status = 404 if str(error) == "GENERATION_RUN_NOT_FOUND" else 409
        raise ApiError("CANDIDATE_COLLECTION_UNAVAILABLE", str(error), status) from error
    return jsonify({"data": collection, "meta": {"request_id": request_id()}}), 200


@api.get("/test-generation-runs/<run_id>/reviews")
def phase6_review_collection(run_id: str) -> tuple[Any, int]:
    try:
        collection = _test_review_service().collection(run_id)
    except TestReviewError as error:
        status = 404 if str(error) == "GENERATION_RUN_NOT_FOUND" else 409
        raise ApiError("REVIEW_COLLECTION_UNAVAILABLE", str(error), status) from error
    return jsonify({"data": collection, "meta": {"request_id": request_id()}}), 200


@api.get("/test-generation-runs/<run_id>/executability")
def phase6_executability_report(run_id: str) -> tuple[Any, int]:
    try:
        report = _test_review_service().executability_report(run_id)
    except TestReviewError as error:
        status = 404 if str(error) == "GENERATION_RUN_NOT_FOUND" else 409
        raise ApiError("EXECUTABILITY_REPORT_UNAVAILABLE", str(error), status) from error
    return jsonify({"data": report, "meta": {"request_id": request_id()}}), 200


@api.get("/test-generation-runs/<run_id>/mvp-classification-plan")
def phase6_mvp_classification_plan(run_id: str) -> tuple[Any, int]:
    try:
        plan = _test_review_service().mvp_classification_plan(run_id)
    except TestReviewError as error:
        status = 404 if str(error) == "GENERATION_RUN_NOT_FOUND" else 409
        raise ApiError("MVP_CLASSIFICATION_PLAN_UNAVAILABLE", str(error), status) from error
    return jsonify({"data": plan, "meta": {"request_id": request_id()}}), 200


@api.post("/test-generation-runs/<run_id>/candidates/<case_id>/reviews")
def phase6_review_candidate(run_id: str, case_id: str) -> tuple[Any, int]:
    payload = _json_object()
    try:
        result = _test_review_service().review(
            run_id,
            case_id,
            reviewer_id=str(payload.get("reviewer_id", "")),
            decision=str(payload.get("decision", "")),
            automation_disposition=str(payload.get("automation_disposition", "")),
            disposition_reason=str(payload.get("disposition_reason", "")),
            comment=str(payload.get("comment", "")),
            expected_content_hash=str(payload.get("expected_content_hash", "")),
            human_revision_id=(
                str(payload["human_revision_id"]) if payload.get("human_revision_id") else None
            ),
        )
    except TestReviewError as error:
        status = 404 if str(error) == "CANDIDATE_NOT_FOUND" else 409
        raise ApiError("TEST_CASE_REVIEW_ERROR", str(error), status) from error
    return jsonify({"data": result, "meta": {"request_id": request_id()}}), 201


@api.post("/test-generation-runs/<run_id>/candidates/<case_id>/human-revisions")
def phase6_create_human_revision(run_id: str, case_id: str) -> tuple[Any, int]:
    payload = _json_object()
    revised_candidate: dict[str, Any] = (
        payload["candidate"] if isinstance(payload.get("candidate"), dict) else {}
    )
    try:
        result = _test_review_service().create_human_revision(
            run_id,
            case_id,
            revised_by=str(payload.get("revised_by", "")),
            revision_reason=str(payload.get("revision_reason", "")),
            expected_content_hash=str(payload.get("expected_content_hash", "")),
            candidate=revised_candidate,
        )
    except TestReviewError as error:
        status = 404 if str(error) == "CANDIDATE_NOT_FOUND" else 409
        raise ApiError("HUMAN_REVISION_ERROR", str(error), status) from error
    return jsonify({"data": result, "meta": {"request_id": request_id()}}), 201


@api.post("/test-generation-runs/<run_id>/frozen-baselines")
def phase6_freeze_baseline(run_id: str) -> tuple[Any, int]:
    payload = _json_object()
    try:
        result = _test_review_service().freeze(
            run_id,
            frozen_by=str(payload.get("frozen_by", "")),
            environment_id=str(payload.get("environment_id", "")),
            executor_contract_version=str(payload.get("executor_contract_version", "")),
        )
    except TestReviewError as error:
        raise ApiError("BASELINE_FREEZE_ERROR", str(error), 409) from error
    return jsonify({"data": result.__dict__, "meta": {"request_id": request_id()}}), 201


@api.get("/frozen-baselines/<baseline_id>")
def phase6_frozen_baseline(baseline_id: str) -> tuple[Any, int]:
    try:
        baseline = _test_review_service().baseline(baseline_id)
    except TestReviewError as error:
        status = 404 if str(error) == "BASELINE_NOT_FOUND" else 409
        raise ApiError("FROZEN_BASELINE_UNAVAILABLE", str(error), status) from error
    return jsonify({"data": baseline, "meta": {"request_id": request_id()}}), 200


@api.post("/frozen-baselines/<baseline_id>/api-executions")
def phase7_execute_api_baseline(baseline_id: str) -> tuple[Any, int]:
    payload = _json_object()
    environment_id = str(payload.get("environment_id", "")).strip()
    if not environment_id:
        raise ApiError("VALIDATION_ERROR", "environment_id is required.", 422)
    try:
        result = _api_execution_service().execute(
            baseline_id,
            environment_id=environment_id,
        )
    except ApiExecutionError as error:
        status = 404 if str(error) == "BASELINE_NOT_FOUND" else 409
        raise ApiError("API_EXECUTION_ERROR", str(error), status) from error
    return jsonify({"data": result.__dict__, "meta": {"request_id": request_id()}}), 201


@api.get("/api-test-runs/<run_id>")
def phase7_api_test_run(run_id: str) -> tuple[Any, int]:
    try:
        result = _api_execution_service().run(run_id)
    except ApiExecutionError as error:
        raise ApiError("API_TEST_RUN_UNAVAILABLE", str(error), 404) from error
    return jsonify({"data": result, "meta": {"request_id": request_id()}}), 200


@api.get("/api-test-results/<result_id>/evidence")
def phase7_api_test_evidence(result_id: str) -> tuple[Any, int]:
    try:
        result = _api_execution_service().evidence(result_id)
    except ApiExecutionError as error:
        raise ApiError("API_TEST_EVIDENCE_UNAVAILABLE", str(error), 404) from error
    return jsonify({"data": result, "meta": {"request_id": request_id()}}), 200


@api.post("/frozen-baselines/<baseline_id>/ui-executions")
def phase7_execute_ui_baseline(baseline_id: str) -> tuple[Any, int]:
    payload = _json_object()
    environment_id = str(payload.get("environment_id", "")).strip()
    if not environment_id:
        raise ApiError("VALIDATION_ERROR", "environment_id is required.", 422)
    try:
        result = _ui_execution_service().execute(
            baseline_id,
            environment_id=environment_id,
            base_url=current_app.config["SUT_UI_BASE_URL"],
            browser_channel=current_app.config["PLAYWRIGHT_BROWSER_CHANNEL"],
        )
    except UiExecutionError as error:
        status = 404 if str(error) == "BASELINE_NOT_FOUND" else 409
        raise ApiError("UI_EXECUTION_ERROR", str(error), status) from error
    return jsonify({"data": result, "meta": {"request_id": request_id()}}), 201


@api.get("/ui-test-runs/<run_id>")
def phase7_ui_test_run(run_id: str) -> tuple[Any, int]:
    try:
        result = _ui_execution_service().run(run_id)
    except UiExecutionError as error:
        raise ApiError("UI_TEST_RUN_UNAVAILABLE", str(error), 404) from error
    return jsonify({"data": result, "meta": {"request_id": request_id()}}), 200


@api.get("/ui-test-results/<result_id>/evidence")
def phase7_ui_test_evidence(result_id: str) -> tuple[Any, int]:
    try:
        result = _ui_execution_service().evidence(result_id)
    except UiExecutionError as error:
        raise ApiError("UI_TEST_EVIDENCE_UNAVAILABLE", str(error), 404) from error
    return jsonify({"data": result, "meta": {"request_id": request_id()}}), 200


def _requirements_response(project_id: str, analysis_run_id: str | None) -> tuple[Any, int]:
    if analysis_run_id:
        rows = _database().fetch_all(
            "SELECT requirement_id, analysis_run_id, version_number, payload_json, "
            "review_status, created_at FROM requirements WHERE project_id=:project "
            "AND analysis_run_id=:run ORDER BY requirement_id",
            {"project": project_id, "run": analysis_run_id},
        )
    else:
        rows = _database().fetch_all(
            "SELECT requirement_id, analysis_run_id, version_number, payload_json, "
            "review_status, created_at FROM requirements WHERE project_id=:project "
            "ORDER BY requirement_id",
            {"project": project_id},
        )
    requirements = [
        {
            **{key: value for key, value in row.items() if key != "payload_json"},
            "requirement": __import__("json").loads(row["payload_json"]),
        }
        for row in rows
    ]
    return jsonify(
        {
            "data": requirements,
            "meta": {"request_id": request_id(), "count": len(requirements)},
        }
    ), 200
