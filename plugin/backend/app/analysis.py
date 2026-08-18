from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any

from jsonschema import ValidationError as JsonSchemaError
from sqlalchemy import text

from plugin.backend.app.constraints import (
    NormalizedConstraint,
    extract_username_minimum_constraint,
)
from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.ids import new_id
from plugin.backend.app.outline_normalization import (
    OutlineNormalizationError,
    SectionIdNormalizationAudit,
    normalize_outline_section_ids,
)
from plugin.backend.app.prompts import (
    PROMPT_VERSION,
    RECOVERY_PROMPT_VERSION,
    SCHEMA_VERSION,
    PromptRegistry,
)
from plugin.backend.app.providers import (
    LLMProvider,
    ProviderCallError,
    ProviderConfigurationError,
    ProviderResponse,
)
from plugin.backend.app.schema_validation import RequirementSchemas
from plugin.backend.app.source_blocks import (
    SourceBlock,
    SourceBlockError,
    build_source_blocks,
    locate_existing_excerpt,
    validate_source_references,
)


class AnalysisValidationError(Exception):
    pass


class TruncationError(AnalysisValidationError):
    pass


@dataclass(frozen=True)
class BatchSpec:
    batch_id: str
    index: int
    source_sections: list[str]
    source_text: str

    @property
    def input_hash(self) -> str:
        return content_hash(self.source_text)


def normalize_prd(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip() for line in normalized.splitlines())
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if not normalized:
        raise AnalysisValidationError("PRD content is empty.")
    return normalized + "\n"


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def split_sections(content: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    heading = "# Document"
    lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("#"):
            if lines:
                sections.append((heading, lines))
            heading = line
            lines = [line]
        else:
            lines.append(line)
    if lines:
        sections.append((heading, lines))
    return [(name, "\n".join(body).strip()) for name, body in sections if "\n".join(body).strip()]


def plan_batches(content: str, max_chars: int) -> list[BatchSpec]:
    if max_chars < 200:
        raise ValueError("max_chars must be at least 200")
    chunks: list[tuple[list[str], str]] = []
    pending_sections: list[str] = []
    pending_text = ""
    for section, section_text in split_sections(content):
        for piece in _bounded_pieces(section_text, max_chars):
            addition = piece if not pending_text else f"\n\n{piece}"
            if pending_text and len(pending_text) + len(addition) > max_chars:
                chunks.append((pending_sections, pending_text))
                pending_sections = []
                pending_text = ""
            if section not in pending_sections:
                pending_sections.append(section)
            pending_text += piece if not pending_text else f"\n\n{piece}"
    if pending_text:
        chunks.append((pending_sections, pending_text))
    return [
        BatchSpec(f"BAT-{index:03d}", index, sections, source)
        for index, (sections, source) in enumerate(chunks, 1)
    ]


def _bounded_pieces(text_value: str, max_chars: int) -> list[str]:
    if len(text_value) <= max_chars:
        return [text_value]
    paragraphs = text_value.split("\n\n")
    pieces: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(
                paragraph[index : index + max_chars]
                for index in range(0, len(paragraph), max_chars)
            )
        elif current and len(current) + len(paragraph) + 2 > max_chars:
            pieces.append(current)
            current = paragraph
        else:
            current += paragraph if not current else f"\n\n{paragraph}"
    if current:
        pieces.append(current)
    return pieces


def parse_json_object(response: ProviderResponse) -> dict[str, Any]:
    if not response.content.strip():
        raise TruncationError("EMPTY_CONTENT")
    if response.finish_reason != "stop":
        raise TruncationError("ABNORMAL_FINISH_REASON")
    if (
        response.output_tokens is not None
        and response.max_tokens > 0
        and response.output_tokens >= int(response.max_tokens * 0.98)
    ):
        raise TruncationError("OUTPUT_TOKEN_LIMIT_RISK")
    value = response.content.strip()
    fence = chr(96) * 3
    if value.startswith(fence):
        lines = value.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == fence:
            value = "\n".join(lines[1:-1]).strip()
            if value.lower().startswith("json\n"):
                value = value[5:].strip()
    start = value.find("{")
    end = value.rfind("}")
    if start < 0 or end < start:
        raise TruncationError("JSON_NOT_CLOSED")
    try:
        parsed = json.loads(value[start : end + 1])
    except json.JSONDecodeError as error:
        raise TruncationError("MALFORMED_JSON") from error
    if not isinstance(parsed, dict):
        raise AnalysisValidationError("JSON_ROOT_NOT_OBJECT")
    return parsed


class AnalysisService:
    def __init__(
        self,
        database: PluginDatabase,
        *,
        schemas: RequirementSchemas | None = None,
        prompts: PromptRegistry | None = None,
        batch_max_chars: int = 1800,
        batch_max_requirements: int = 12,
        max_retries: int = 2,
        call_max_output_tokens: int = 4096,
        run_max_output_tokens: int = 26624,
    ) -> None:
        self.database = database
        self.schemas = schemas or RequirementSchemas()
        self.prompts = prompts or PromptRegistry()
        self.batch_max_chars = batch_max_chars
        self.batch_max_requirements = batch_max_requirements
        self.max_retries = max_retries
        self.call_max_output_tokens = call_max_output_tokens
        self.run_max_output_tokens = run_max_output_tokens

    def start(
        self, prd_version_id: str, provider: LLMProvider, idempotency_key: str
    ) -> dict[str, Any]:
        existing = self.database.fetch_one(
            "SELECT * FROM analysis_runs WHERE idempotency_key=:key",
            {"key": idempotency_key},
        )
        metadata = provider.metadata
        if existing and (
            existing["prd_version_id"] != prd_version_id
            or existing["provider"] != metadata.provider
            or existing["model"] != metadata.model
            or existing["provider_mode"] != metadata.provider_mode
        ):
            raise AnalysisValidationError("IDEMPOTENCY_KEY_CONFLICT")
        if existing and existing["status"] in {"succeeded", "failed", "blocked"}:
            return existing
        prd = self.database.fetch_one(
            "SELECT v.*, d.project_id FROM prd_versions v "
            "JOIN prd_documents d ON d.prd_document_id=v.prd_document_id "
            "WHERE v.version_id=:id",
            {"id": prd_version_id},
        )
        if not prd:
            raise AnalysisValidationError("PRD_VERSION_NOT_FOUND")
        if existing:
            run_id = str(existing["analysis_run_id"])
        else:
            run_id = new_id("ANR")
            self._register_prompt()
            self.database.execute(
                "INSERT INTO analysis_runs(analysis_run_id, project_id, prd_version_id, "
                "provider, model, provider_mode, prompt_version, schema_version, status, "
                "input_hash, idempotency_key) VALUES "
                "(:id, :project, :prd, :provider, :model, :mode, :prompt, :schema, "
                "'running', :hash, :key)",
                {
                    "id": run_id,
                    "project": prd["project_id"],
                    "prd": prd_version_id,
                    "provider": metadata.provider,
                    "model": metadata.model,
                    "mode": metadata.provider_mode,
                    "prompt": PROMPT_VERSION,
                    "schema": SCHEMA_VERSION,
                    "hash": prd["content_hash"],
                    "key": idempotency_key,
                },
            )
        try:
            provider.validate_config()
            self._run_pipeline(run_id, prd, provider)
        except ProviderConfigurationError:
            self._fail_run(run_id, "blocked", "PROVIDER_CONFIGURATION")
        except (
            ProviderCallError,
            AnalysisValidationError,
            JsonSchemaError,
            SourceBlockError,
        ) as error:
            error_type = error.error_type if isinstance(error, ProviderCallError) else str(error)
            self._fail_run(run_id, "failed", error_type)
        return (
            self.database.fetch_one(
                "SELECT * FROM analysis_runs WHERE analysis_run_id=:id", {"id": run_id}
            )
            or {}
        )

    def start_recovery(
        self,
        source_run_id: str,
        provider: LLMProvider,
        idempotency_key: str,
    ) -> dict[str, Any]:
        source = self.database.fetch_one(
            "SELECT r.*, v.version_id AS version_id, v.content, v.content_hash, "
            "d.project_id FROM analysis_runs r "
            "JOIN prd_versions v ON v.version_id=r.prd_version_id "
            "JOIN prd_documents d ON d.prd_document_id=v.prd_document_id "
            "WHERE r.analysis_run_id=:id",
            {"id": source_run_id},
        )
        if not source or source["status"] != "failed":
            raise AnalysisValidationError("RECOVERY_SOURCE_MUST_BE_FAILED")
        metadata = provider.metadata
        if (
            source["provider"] != metadata.provider
            or source["model"] != metadata.model
            or source["provider_mode"] != metadata.provider_mode
        ):
            raise AnalysisValidationError("RECOVERY_PROVIDER_MISMATCH")
        existing = self.database.fetch_one(
            "SELECT * FROM analysis_runs WHERE idempotency_key=:key",
            {"key": idempotency_key},
        )
        if existing:
            return existing
        run_id = new_id("ANR")
        self._register_recovery_prompt()
        self.database.execute(
            "INSERT INTO analysis_runs(analysis_run_id, project_id, prd_version_id, provider, "
            "model, provider_mode, prompt_version, schema_version, status, input_hash, "
            "idempotency_key, parent_analysis_run_id) VALUES "
            "(:id, :project, :prd, :provider, :model, :mode, :prompt, :schema, 'running', "
            ":hash, :key, :parent)",
            {
                "id": run_id,
                "project": source["project_id"],
                "prd": source["prd_version_id"],
                "provider": metadata.provider,
                "model": metadata.model,
                "mode": metadata.provider_mode,
                "prompt": RECOVERY_PROMPT_VERSION,
                "schema": SCHEMA_VERSION,
                "hash": source["content_hash"],
                "key": idempotency_key,
                "parent": source_run_id,
            },
        )
        try:
            provider.validate_config()
            self._run_pipeline(run_id, source, provider, reuse_run_id=source_run_id)
        except ProviderConfigurationError:
            self._fail_run(run_id, "blocked", "PROVIDER_CONFIGURATION")
        except (
            ProviderCallError,
            AnalysisValidationError,
            JsonSchemaError,
            SourceBlockError,
        ) as error:
            error_type = error.error_type if isinstance(error, ProviderCallError) else str(error)
            self._fail_run(run_id, "failed", error_type)
        return (
            self.database.fetch_one(
                "SELECT * FROM analysis_runs WHERE analysis_run_id=:id", {"id": run_id}
            )
            or {}
        )

    def _run_pipeline(
        self,
        run_id: str,
        prd: dict[str, Any],
        provider: LLMProvider,
        *,
        reuse_run_id: str | None = None,
    ) -> None:
        normalized = normalize_prd(str(prd["content"]))
        outline_source_run = reuse_run_id or run_id
        valid_outline = self.database.fetch_one(
            "SELECT llm_call_id FROM llm_call_logs WHERE analysis_run_id=:run "
            "AND call_type IN ('outline','outline_correction') "
            "AND validation_status='valid' ORDER BY retry_count DESC LIMIT 1",
            {"run": outline_source_run},
        )
        if reuse_run_id:
            if not valid_outline:
                raise AnalysisValidationError("VALID_OUTLINE_NOT_AVAILABLE_FOR_REUSE")
            self._insert_reuse_link(
                run_id,
                reuse_run_id,
                "outline",
                str(valid_outline["llm_call_id"]),
                None,
                content_hash(str(valid_outline["llm_call_id"])),
            )
        if not valid_outline:
            self._assert_call_budget(run_id, min(self.call_max_output_tokens, 2048))
            try:
                outline_response = provider.analyze_outline(normalized)
            except ProviderCallError as error:
                self._log_error(run_id, None, "outline", provider, 0, error)
                raise
            try:
                raw_outline = parse_json_object(outline_response)
            except AnalysisValidationError as error:
                self._log_response(
                    run_id, None, "outline", provider, outline_response, 0, "invalid", str(error)
                )
                raise
            try:
                outline, normalization_audits = normalize_outline_section_ids(raw_outline)
                self.schemas.validate("prd_outline.schema.json", outline)
            except (JsonSchemaError, OutlineNormalizationError) as error:
                diagnostic = (
                    _schema_diagnostic(error) if isinstance(error, JsonSchemaError) else str(error)
                )
                self._log_response(
                    run_id,
                    None,
                    "outline",
                    provider,
                    outline_response,
                    0,
                    "invalid",
                    diagnostic,
                    parsed=raw_outline,
                )
                if self.max_retries < 1:
                    raise AnalysisValidationError(diagnostic) from error
                self._assert_call_budget(run_id, min(self.call_max_output_tokens, 2048))
                try:
                    correction = getattr(provider, "correct_outline", None)
                    if not callable(correction):
                        raise AnalysisValidationError("OUTLINE_CORRECTION_UNAVAILABLE")
                    correction_response = correction(normalized, raw_outline, diagnostic)
                except ProviderCallError as provider_error:
                    self._log_error(run_id, None, "outline_correction", provider, 1, provider_error)
                    raise
                try:
                    corrected_raw = parse_json_object(correction_response)
                    outline, normalization_audits = normalize_outline_section_ids(corrected_raw)
                    self.schemas.validate("prd_outline.schema.json", outline)
                except (
                    AnalysisValidationError,
                    JsonSchemaError,
                    OutlineNormalizationError,
                ) as repair:
                    repair_diagnostic = (
                        _schema_diagnostic(repair)
                        if isinstance(repair, JsonSchemaError)
                        else str(repair)
                    )
                    self._log_response(
                        run_id,
                        None,
                        "outline_correction",
                        provider,
                        correction_response,
                        1,
                        "invalid",
                        repair_diagnostic,
                        parsed=corrected_raw if "corrected_raw" in locals() else None,
                    )
                    raise AnalysisValidationError(repair_diagnostic) from repair
                call_id = self._log_response(
                    run_id,
                    None,
                    "outline_correction",
                    provider,
                    correction_response,
                    1,
                    "valid",
                    parsed=outline,
                )
                self._record_outline_normalizations(call_id, normalization_audits)
            else:
                call_id = self._log_response(
                    run_id,
                    None,
                    "outline",
                    provider,
                    outline_response,
                    0,
                    "valid",
                    parsed=outline,
                )
                self._record_outline_normalizations(call_id, normalization_audits)
        queue = plan_batches(normalized, self.batch_max_chars)
        next_index = len(queue) + 1
        validated: list[tuple[BatchSpec, dict[str, Any]]] = []
        while queue:
            spec = queue.pop(0)
            blocks = build_source_blocks(normalized, spec.source_text)
            stored = self.database.fetch_one(
                "SELECT * FROM analysis_batches WHERE analysis_run_id=:run AND input_hash=:hash",
                {"run": run_id, "hash": spec.input_hash},
            )
            if stored and stored["status"] == "validated":
                candidates = self.database.fetch_all(
                    "SELECT payload_json FROM requirement_candidates "
                    "WHERE analysis_batch_id=:batch ORDER BY requirement_id",
                    {"batch": stored["analysis_batch_id"]},
                )
                validated.append(
                    (
                        spec,
                        {
                            "requirements": [json.loads(row["payload_json"]) for row in candidates],
                            "reported_count": len(candidates),
                        },
                    )
                )
                continue
            reusable = None
            if reuse_run_id:
                reusable = self.database.fetch_one(
                    "SELECT * FROM analysis_batches WHERE analysis_run_id=:run "
                    "AND input_hash=:hash",
                    {"run": reuse_run_id, "hash": spec.input_hash},
                )
            if reusable and reusable["status"] == "validated":
                if reuse_run_id is None:
                    raise AnalysisValidationError("REUSE_RUN_ID_MISSING")
                reused = self._reuse_validated_batch(
                    run_id, reuse_run_id, reusable, spec, blocks, normalized
                )
                validated.append((spec, reused))
                continue
            batch_db_id = str(stored["analysis_batch_id"]) if stored else new_id("ABT")
            if not stored:
                self.database.execute(
                    "INSERT INTO analysis_batches(analysis_batch_id, analysis_run_id, batch_index, "
                    "source_section, source_text, source_blocks_json, input_hash, status) VALUES "
                    "(:id, :run, :index, :section, :source, :blocks, :hash, 'pending')",
                    {
                        "id": batch_db_id,
                        "run": run_id,
                        "index": spec.index,
                        "section": self.database.encode_json(spec.source_sections),
                        "source": spec.source_text,
                        "blocks": self.database.encode_json([block.as_dict() for block in blocks]),
                        "hash": spec.input_hash,
                    },
                )
            recovery = bool(reuse_run_id or (stored and stored["status"] == "failed_validation"))
            result, replacement = self._process_batch(
                run_id,
                batch_db_id,
                spec,
                blocks,
                normalized,
                provider,
                next_index,
                recovery=recovery,
            )
            if replacement:
                queue = replacement + queue
                next_index += len(replacement)
            elif result is not None:
                validated.append((spec, result))
        aggregate = self._aggregate(str(prd["content_hash"]), validated)
        self.schemas.validate("requirement_aggregate.schema.json", aggregate)
        self._validate_aggregate_domain(aggregate)
        self._promote(run_id, prd, aggregate)

    def _process_batch(
        self,
        run_id: str,
        batch_db_id: str,
        spec: BatchSpec,
        blocks: list[SourceBlock],
        prd_text: str,
        provider: LLMProvider,
        next_index: int,
        *,
        recovery: bool = False,
    ) -> tuple[dict[str, Any] | None, list[BatchSpec]]:
        retry_offset = self.max_retries + 1 if recovery else 0
        if recovery:
            self._register_recovery_prompt()
        attempt_limit = 1 if recovery else self.max_retries + 1
        for retry in range(attempt_limit):
            attempt = retry + retry_offset
            self._assert_call_budget(run_id, self.call_max_output_tokens)
            try:
                response = provider.extract_requirements_batch(
                    batch_id=spec.batch_id,
                    source_sections=spec.source_sections,
                    source_blocks=[block.as_dict() for block in blocks],
                    max_requirements=self.batch_max_requirements,
                    recovery=recovery,
                )
            except ProviderCallError as error:
                self._log_error(
                    run_id,
                    batch_db_id,
                    "requirements_recovery" if recovery else "requirements",
                    provider,
                    attempt,
                    error,
                    prompt_version=RECOVERY_PROMPT_VERSION if recovery else PROMPT_VERSION,
                )
                if not error.retryable or retry >= attempt_limit - 1:
                    raise
                continue
            parsed: dict[str, Any] | None = None
            audits: list[dict[str, Any]] = []
            try:
                parsed = parse_json_object(response)
                if parsed.get("batch_complete") is not True:
                    raise TruncationError("BATCH_INCOMPLETE")
                if parsed.get("reported_count") != len(parsed.get("requirements", [])):
                    raise TruncationError("REPORTED_COUNT_MISMATCH")
                audits = validate_source_references(parsed, blocks, prd_text)
                self.schemas.validate("requirement_batch.schema.json", parsed)
                self._validate_batch_domain(parsed, spec)
            except TruncationError as error:
                self._log_response(
                    run_id,
                    batch_db_id,
                    "requirements_recovery" if recovery else "requirements",
                    provider,
                    response,
                    attempt,
                    "truncated",
                    type(error).__name__,
                    prompt_version=RECOVERY_PROMPT_VERSION if recovery else PROMPT_VERSION,
                    parsed=parsed,
                    audits=audits,
                )
                if len(spec.source_text) > 600:
                    self._update_batch(batch_db_id, "truncated", attempt, response, "TRUNCATED")
                    return None, self._split_failed_batch(spec, next_index)
                if retry >= attempt_limit - 1:
                    self._update_batch(batch_db_id, "failed", attempt, response, "TRUNCATED")
                    raise
                continue
            except (AnalysisValidationError, JsonSchemaError, SourceBlockError) as error:
                diagnostic = (
                    _schema_diagnostic(error) if isinstance(error, JsonSchemaError) else str(error)
                )
                if isinstance(error, SourceBlockError):
                    audits = error.audits
                self._log_response(
                    run_id,
                    batch_db_id,
                    "requirements_recovery" if recovery else "requirements",
                    provider,
                    response,
                    attempt,
                    "invalid",
                    diagnostic,
                    prompt_version=RECOVERY_PROMPT_VERSION if recovery else PROMPT_VERSION,
                    parsed=parsed,
                    audits=audits,
                )
                if retry >= attempt_limit - 1:
                    self._update_batch(
                        batch_db_id, "failed_validation", attempt, response, diagnostic
                    )
                    raise
                continue
            self._log_response(
                run_id,
                batch_db_id,
                "requirements_recovery" if recovery else "requirements",
                provider,
                response,
                attempt,
                "valid",
                prompt_version=RECOVERY_PROMPT_VERSION if recovery else PROMPT_VERSION,
                parsed=parsed,
                audits=audits,
            )
            self._save_valid_batch(run_id, batch_db_id, parsed, attempt, response)
            return parsed, []
        raise AnalysisValidationError("RETRY_EXHAUSTED")

    def _validate_batch_domain(self, parsed: dict[str, Any], spec: BatchSpec) -> None:
        if parsed["batch_id"] != spec.batch_id:
            raise AnalysisValidationError("BATCH_ID_MISMATCH")
        if set(parsed["source_sections"]) != set(spec.source_sections):
            raise AnalysisValidationError("SOURCE_SECTION_MISMATCH")
        ids: set[str] = set()
        canonical_source = _canonical(spec.source_text)
        for requirement in parsed["requirements"]:
            requirement_id = requirement["requirement_id"]
            if requirement_id in ids:
                raise AnalysisValidationError("DUPLICATE_REQUIREMENT_ID")
            ids.add(requirement_id)
            if requirement["source_section"] not in spec.source_sections:
                raise AnalysisValidationError("UNKNOWN_SOURCE_SECTION")
            if _canonical(requirement["source_excerpt"]) not in canonical_source:
                raise AnalysisValidationError("SOURCE_EXCERPT_NOT_FOUND")

    def _reuse_validated_batch(
        self,
        run_id: str,
        source_run_id: str,
        source_batch: dict[str, Any],
        spec: BatchSpec,
        blocks: list[SourceBlock],
        prd_text: str,
    ) -> dict[str, Any]:
        source_batch_id = str(source_batch["analysis_batch_id"])
        batch_id = new_id("ABT")
        rows = self.database.fetch_all(
            "SELECT requirement_id, payload_json FROM requirement_candidates "
            "WHERE analysis_batch_id=:batch ORDER BY requirement_id",
            {"batch": source_batch_id},
        )
        requirements: list[dict[str, Any]] = []
        audits: list[dict[str, Any]] = []
        for row in rows:
            requirement = json.loads(str(row["payload_json"]))
            model_excerpt = str(requirement["source_excerpt"])
            block, resolution = locate_existing_excerpt(blocks, model_excerpt, prd_text)
            if resolution.resolved_excerpt is None:
                raise AnalysisValidationError("REUSED_EXCERPT_NOT_RESOLVED")
            requirement["source_block_id"] = block.block_id
            requirement["source_excerpt"] = resolution.resolved_excerpt
            requirements.append(requirement)
            audits.append(
                {
                    "requirement_id": requirement["requirement_id"],
                    "source_block_id": block.block_id,
                    "model_excerpt": model_excerpt,
                    "resolved_excerpt": resolution.resolved_excerpt,
                    "resolution_type": f"reused_{resolution.resolution_type}",
                    "reason": "REVALIDATED_FROM_IMMUTABLE_SOURCE_BATCH",
                    "block_start_line": block.start_line,
                    "block_end_line": block.end_line,
                }
            )
        parsed = {
            "batch_id": spec.batch_id,
            "source_sections": spec.source_sections,
            "requirements": requirements,
            "unsupported": [],
            "reported_count": len(requirements),
            "batch_complete": True,
        }
        self.schemas.validate("requirement_batch.schema.json", parsed)
        self._validate_batch_domain(parsed, spec)
        with self.database.transaction() as connection:
            connection.execute(
                text(
                    "INSERT INTO analysis_batches(analysis_batch_id, analysis_run_id, batch_index, "
                    "source_section, source_text, source_blocks_json, input_hash, status, "
                    "retry_count, reported_count, actual_count, finish_reason, validation_status, "
                    "completed_at) VALUES (:id, :run, :index, :section, :source, :blocks, :hash, "
                    "'validated', 0, :count, :count, 'reused', 'valid', CURRENT_TIMESTAMP)"
                ),
                {
                    "id": batch_id,
                    "run": run_id,
                    "index": spec.index,
                    "section": self.database.encode_json(spec.source_sections),
                    "source": spec.source_text,
                    "blocks": self.database.encode_json([block.as_dict() for block in blocks]),
                    "hash": spec.input_hash,
                    "count": len(requirements),
                },
            )
            for requirement in requirements:
                connection.execute(
                    text(
                        "INSERT INTO requirement_candidates(candidate_id, analysis_run_id, "
                        "analysis_batch_id, requirement_id, payload_json, validation_status) "
                        "VALUES (:id, :run, :batch, :requirement, :payload, 'valid')"
                    ),
                    {
                        "id": new_id("RQC"),
                        "run": run_id,
                        "batch": batch_id,
                        "requirement": requirement["requirement_id"],
                        "payload": self.database.encode_json(requirement),
                    },
                )
        self.database.insert_source_audits(
            run_id=run_id, batch_id=batch_id, call_id=None, audits=audits
        )
        self._insert_reuse_link(
            run_id,
            source_run_id,
            "validated_batch",
            source_batch_id,
            batch_id,
            spec.input_hash,
        )
        return parsed

    def _insert_reuse_link(
        self,
        run_id: str,
        source_run_id: str,
        artifact_type: str,
        source_entity_id: str,
        target_entity_id: str | None,
        artifact_hash: str,
    ) -> None:
        self.database.execute(
            "INSERT INTO analysis_reuse_links(analysis_reuse_link_id, analysis_run_id, "
            "source_analysis_run_id, artifact_type, source_entity_id, target_entity_id, "
            "content_hash) VALUES (:id, :run, :source_run, :type, :source, :target, :hash)",
            {
                "id": new_id("ARL"),
                "run": run_id,
                "source_run": source_run_id,
                "type": artifact_type,
                "source": source_entity_id,
                "target": target_entity_id,
                "hash": artifact_hash,
            },
        )

    def _aggregate(
        self,
        prd_hash: str,
        validated: list[tuple[BatchSpec, dict[str, Any]]],
    ) -> dict[str, Any]:
        by_id: dict[str, dict[str, Any]] = {}
        source_sections: list[str] = []
        for spec, batch in validated:
            for section in spec.source_sections:
                if section not in source_sections:
                    source_sections.append(section)
            for requirement in batch["requirements"]:
                existing = by_id.get(requirement["requirement_id"])
                if existing and existing != requirement:
                    raise AnalysisValidationError("CONFLICTING_REQUIREMENT_ID")
                by_id[requirement["requirement_id"]] = requirement
        requirements = list(by_id.values())
        if not requirements:
            raise AnalysisValidationError("NO_REQUIREMENTS")
        return {
            "schema_version": SCHEMA_VERSION,
            "prd_content_hash": prd_hash,
            "source_sections": source_sections,
            "requirements": requirements,
            "total_reported_count": len(requirements),
            "aggregate_complete": True,
        }

    def _validate_aggregate_domain(self, aggregate: dict[str, Any]) -> list[NormalizedConstraint]:
        requirements = aggregate["requirements"]
        ids = {item["requirement_id"] for item in requirements}
        for requirement in requirements:
            if any(dependency not in ids for dependency in requirement["dependencies"]):
                raise AnalysisValidationError("UNKNOWN_DEPENDENCY")
        searchable = " ".join(
            json.dumps(requirement, ensure_ascii=False).lower() for requirement in requirements
        )
        constraints = [
            constraint
            for requirement in requirements
            if (constraint := extract_username_minimum_constraint(requirement)) is not None
        ]
        checks = {
            "USERNAME_MINIMUM_SIX_MISSING": any(
                constraint.field == "username"
                and constraint.operator == "greater_than_or_equal"
                and constraint.value == 6
                and constraint.unit == "characters"
                for constraint in constraints
            ),
            "REGISTRATION_MISSING": "register" in searchable,
            "LOGIN_MISSING": "login" in searchable,
            "CURRENT_USER_MISSING": any(
                term in searchable
                for term in ("current user", "current-user", "account data", "/me")
            ),
            "LOGOUT_MISSING": "logout" in searchable,
        }
        for error, passed in checks.items():
            if not passed:
                raise AnalysisValidationError(error)
        return constraints

    def _save_valid_batch(
        self,
        run_id: str,
        batch_db_id: str,
        parsed: dict[str, Any],
        retry: int,
        response: ProviderResponse,
    ) -> None:
        with self.database.transaction() as connection:
            connection.execute(
                text(
                    "UPDATE analysis_batches SET status='validated', retry_count=:retry, "
                    "reported_count=:count, actual_count=:count, finish_reason=:finish, "
                    "validation_status='valid', completed_at=CURRENT_TIMESTAMP "
                    "WHERE analysis_batch_id=:id"
                ),
                {
                    "retry": retry,
                    "count": len(parsed["requirements"]),
                    "finish": response.finish_reason,
                    "id": batch_db_id,
                },
            )
            for requirement in parsed["requirements"]:
                connection.execute(
                    text(
                        "INSERT OR IGNORE INTO requirement_candidates("
                        "candidate_id, analysis_run_id, "
                        "analysis_batch_id, requirement_id, payload_json, validation_status) "
                        "VALUES (:id, :run, :batch, :requirement, :payload, 'valid')"
                    ),
                    {
                        "id": new_id("RQC"),
                        "run": run_id,
                        "batch": batch_db_id,
                        "requirement": requirement["requirement_id"],
                        "payload": self.database.encode_json(requirement),
                    },
                )

    def _promote(self, run_id: str, prd: dict[str, Any], aggregate: dict[str, Any]) -> None:
        with self.database.transaction() as connection:
            existing = connection.execute(
                text("SELECT COUNT(*) FROM requirements WHERE analysis_run_id=:run"),
                {"run": run_id},
            ).scalar_one()
            if existing:
                raise AnalysisValidationError("FORMAL_REQUIREMENTS_ALREADY_EXIST")
            for requirement in aggregate["requirements"]:
                connection.execute(
                    text(
                        "INSERT INTO requirements("
                        "row_id, requirement_id, project_id, prd_version_id, "
                        "analysis_run_id, title, description, requirement_type, source_section, "
                        "source_excerpt, payload_json) VALUES "
                        "(:row, :requirement, :project, :prd, :run, :title, :description, :type, "
                        ":section, :excerpt, :payload)"
                    ),
                    {
                        "row": new_id("REQV"),
                        "requirement": requirement["requirement_id"],
                        "project": prd["project_id"],
                        "prd": prd["version_id"],
                        "run": run_id,
                        "title": requirement["title"],
                        "description": requirement["description"],
                        "type": requirement["requirement_type"],
                        "section": requirement["source_section"],
                        "excerpt": requirement["source_excerpt"],
                        "payload": self.database.encode_json(requirement),
                    },
                )
                for dependency in requirement["dependencies"]:
                    connection.execute(
                        text(
                            "INSERT INTO requirement_relationships("
                            "relationship_id, analysis_run_id, "
                            "source_requirement_id, target_requirement_id, relationship_type) "
                            "VALUES (:id, :run, :source, :target, 'depends_on')"
                        ),
                        {
                            "id": new_id("RRL"),
                            "run": run_id,
                            "source": requirement["requirement_id"],
                            "target": dependency,
                        },
                    )
            connection.execute(
                text(
                    "UPDATE analysis_runs SET status='succeeded', validation_status='valid', "
                    "completed_at=CURRENT_TIMESTAMP WHERE analysis_run_id=:id"
                ),
                {"id": run_id},
            )

    def _register_prompt(self) -> None:
        self.database.execute(
            "INSERT OR IGNORE INTO prompt_versions(prompt_version_id, semantic_version, "
            "content_hash, schema_version, status) VALUES "
            "(:id, :version, :hash, :schema, 'active')",
            {
                "id": new_id("PMT"),
                "version": PROMPT_VERSION,
                "hash": self.prompts.content_hash,
                "schema": SCHEMA_VERSION,
            },
        )

    def _register_recovery_prompt(self) -> None:
        self.database.execute(
            "INSERT OR IGNORE INTO prompt_versions(prompt_version_id, semantic_version, "
            "content_hash, schema_version, status) VALUES "
            "(:id, :version, :hash, :schema, 'active')",
            {
                "id": new_id("PMT"),
                "version": RECOVERY_PROMPT_VERSION,
                "hash": self.prompts.recovery_content_hash,
                "schema": SCHEMA_VERSION,
            },
        )

    def _split_failed_batch(self, spec: BatchSpec, next_index: int) -> list[BatchSpec]:
        midpoint = len(spec.source_text) // 2
        boundary = spec.source_text.rfind("\n", 0, midpoint)
        if boundary < 200:
            boundary = midpoint
        left = spec.source_text[:boundary].strip()
        right = spec.source_text[boundary:].strip()
        return [
            BatchSpec(f"BAT-{next_index:03d}", next_index, spec.source_sections, left),
            BatchSpec(f"BAT-{next_index + 1:03d}", next_index + 1, spec.source_sections, right),
        ]

    def _update_batch(
        self,
        batch_id: str,
        status: str,
        retry: int,
        response: ProviderResponse,
        error_type: str,
    ) -> None:
        self.database.execute(
            "UPDATE analysis_batches SET status=:status, retry_count=:retry, "
            "finish_reason=:finish, validation_status='invalid', error_type=:error, "
            "redacted_error=:redacted, completed_at=CURRENT_TIMESTAMP "
            "WHERE analysis_batch_id=:id",
            {
                "status": status,
                "retry": retry,
                "finish": response.finish_reason,
                "error": error_type,
                "redacted": error_type,
                "id": batch_id,
            },
        )

    def _log_response(
        self,
        run_id: str,
        batch_id: str | None,
        call_type: str,
        provider: LLMProvider,
        response: ProviderResponse,
        retry: int,
        validation: str,
        error_type: str | None = None,
        *,
        prompt_version: str = PROMPT_VERSION,
        parsed: dict[str, Any] | None = None,
        audits: list[dict[str, Any]] | None = None,
    ) -> str:
        metadata = provider.metadata
        call_id = self.database.insert_call_log(
            {
                "analysis_run_id": run_id,
                "analysis_batch_id": batch_id,
                "call_type": call_type,
                "provider": metadata.provider,
                "model": metadata.model,
                "provider_mode": metadata.provider_mode,
                "provider_request_id": response.provider_request_id,
                "prompt_version": prompt_version,
                "schema_version": SCHEMA_VERSION,
                "retry_count": retry,
                "http_status": response.http_status,
                "finish_reason": response.finish_reason,
                "input_tokens": response.input_tokens,
                "output_tokens": response.output_tokens,
                "max_tokens": response.max_tokens,
                "latency_ms": response.latency_ms,
                "validation_status": validation,
                "error_type": error_type,
                "redacted_error": error_type,
            }
        )
        response_content, redacted = _redact_response(response.content)
        stored_parsed = parsed
        if parsed is not None and redacted:
            parsed_content, _ = _redact_response(
                json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
            )
            stored_parsed = json.loads(parsed_content)
        self.database.insert_response_artifact(
            call_id,
            response_content,
            stored_parsed,
            redaction_applied=redacted,
        )
        if batch_id and audits:
            self.database.insert_source_audits(
                run_id=run_id,
                batch_id=batch_id,
                call_id=call_id,
                audits=audits,
            )
        return call_id

    def _log_error(
        self,
        run_id: str,
        batch_id: str | None,
        call_type: str,
        provider: LLMProvider,
        retry: int,
        error: ProviderCallError,
        *,
        prompt_version: str = PROMPT_VERSION,
    ) -> None:
        metadata = provider.metadata
        self.database.insert_call_log(
            {
                "analysis_run_id": run_id,
                "analysis_batch_id": batch_id,
                "call_type": call_type,
                "provider": metadata.provider,
                "model": metadata.model,
                "provider_mode": metadata.provider_mode,
                "provider_request_id": None,
                "prompt_version": prompt_version,
                "schema_version": SCHEMA_VERSION,
                "retry_count": retry,
                "http_status": error.http_status,
                "finish_reason": None,
                "input_tokens": None,
                "output_tokens": None,
                "max_tokens": (
                    min(self.call_max_output_tokens, 2048)
                    if call_type == "outline"
                    else self.call_max_output_tokens
                ),
                "latency_ms": 0,
                "validation_status": "provider_error",
                "error_type": error.error_type,
                "redacted_error": error.error_type,
            }
        )

    def _record_outline_normalizations(
        self, call_id: str, audits: list[SectionIdNormalizationAudit]
    ) -> None:
        for audit in audits:
            self.database.execute(
                "INSERT INTO analysis_outline_normalization_audits("
                "analysis_outline_normalization_audit_id,llm_call_id,section_index,"
                "original_section_id,normalized_section_id,reason) VALUES "
                "(:id,:call,:index,:original,:normalized,:reason)",
                {
                    "id": new_id("ONA"),
                    "call": call_id,
                    "index": audit.section_index,
                    "original": audit.original_section_id,
                    "normalized": audit.normalized_section_id,
                    "reason": audit.reason,
                },
            )

    def _assert_call_budget(self, run_id: str, requested_tokens: int) -> None:
        row = self.database.fetch_one(
            "SELECT COALESCE(SUM(max_tokens), 0) AS used FROM llm_call_logs "
            "WHERE analysis_run_id=:run",
            {"run": run_id},
        )
        used = int(row["used"]) if row else 0
        if used + requested_tokens > self.run_max_output_tokens:
            raise AnalysisValidationError("COST_BUDGET_EXCEEDED")

    def _fail_run(self, run_id: str, status: str, error_type: str) -> None:
        self.database.execute(
            "UPDATE analysis_runs SET status=:status, validation_status='invalid', "
            "error_type=:error, redacted_error=:error, completed_at=CURRENT_TIMESTAMP "
            "WHERE analysis_run_id=:id",
            {"status": status, "error": error_type, "id": run_id},
        )


def _canonical(value: str) -> str:
    return " ".join(value.split()).casefold()


def _schema_diagnostic(error: JsonSchemaError) -> str:
    path = "/".join(str(part) for part in error.absolute_path) or "$"
    return f"SCHEMA_VALIDATION:{path}:{error.validator}"


def _redact_response(content: str) -> tuple[str, bool]:
    redacted = content
    applied = False
    for name in ("DEEPSEEK_API_KEY",):
        secret = os.getenv(name, "")
        if secret and secret in redacted:
            redacted = redacted.replace(secret, "[REDACTED_SECRET]")
            applied = True
    return redacted, applied
