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
from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.errors import ApiError, request_id
from plugin.backend.app.ids import new_id
from plugin.backend.app.prompts import PROMPT_VERSION, SCHEMA_VERSION, PromptRegistry
from plugin.backend.app.providers import DeepSeekProvider, LLMProvider, MockLLMProvider

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
