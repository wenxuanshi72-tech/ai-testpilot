from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from plugin.backend.app.analysis import (
    AnalysisService,
    AnalysisValidationError,
    BatchSpec,
    normalize_prd,
)
from plugin.backend.app.constraints import (
    AGGREGATE_VALIDATOR_VERSION,
    LEGACY_AGGREGATE_VALIDATOR_VERSION,
    NormalizedConstraint,
    normalize_constraint_text,
)
from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.ids import new_id
from plugin.backend.app.schema_validation import RequirementSchemas
from plugin.backend.app.source_blocks import SourceBlock, validate_source_references


@dataclass(frozen=True)
class OfflineRevalidationResult:
    attempt_id: str
    status: str
    source_analysis_run_id: str
    parent_analysis_run_id: str
    candidate_count: int
    formal_requirement_count: int
    llm_call_count: int
    validator_version: str


class OfflineRevalidationService:
    def __init__(
        self,
        database: PluginDatabase,
        *,
        schemas: RequirementSchemas | None = None,
    ) -> None:
        self.database = database
        self.schemas = schemas or RequirementSchemas()

    def run(
        self,
        source_analysis_run_id: str,
        idempotency_key: str,
    ) -> OfflineRevalidationResult:
        existing = self.database.fetch_one(
            "SELECT * FROM offline_revalidation_attempts WHERE idempotency_key=:key",
            {"key": idempotency_key},
        )
        if existing:
            return self._result(existing)
        context = self._load_context(source_analysis_run_id)
        attempt_id = new_id("ORV")
        self._create_attempt(attempt_id, idempotency_key, context)
        try:
            aggregate, constraints = self._revalidate_candidates(attempt_id, context)
            self._promote(attempt_id, context, aggregate, constraints)
        except Exception as error:
            self.database.execute(
                "UPDATE offline_revalidation_attempts SET status='failed', "
                "error_type=:error, redacted_error=:error, completed_at=CURRENT_TIMESTAMP "
                "WHERE offline_revalidation_attempt_id=:id",
                {"id": attempt_id, "error": _safe_error(error)},
            )
        row = self.database.fetch_one(
            "SELECT * FROM offline_revalidation_attempts WHERE offline_revalidation_attempt_id=:id",
            {"id": attempt_id},
        )
        if row is None:
            raise AnalysisValidationError("OFFLINE_REVALIDATION_ATTEMPT_MISSING")
        return self._result(row)

    def _load_context(self, run_id: str) -> dict[str, Any]:
        run = self.database.fetch_one(
            "SELECT r.*, v.version_id, v.content, v.content_hash FROM analysis_runs r "
            "JOIN prd_versions v ON v.version_id=r.prd_version_id "
            "WHERE r.analysis_run_id=:run",
            {"run": run_id},
        )
        if not run or run["status"] != "failed":
            raise AnalysisValidationError("SOURCE_ATTEMPT_MUST_BE_FAILED")
        if not run["parent_analysis_run_id"]:
            raise AnalysisValidationError("SOURCE_ATTEMPT_HAS_NO_PARENT")
        calls = self.database.fetch_all(
            "SELECT * FROM llm_call_logs WHERE analysis_run_id=:run ORDER BY created_at",
            {"run": run_id},
        )
        if len(calls) != 1 or calls[0]["provider_mode"] != "real":
            raise AnalysisValidationError("SOURCE_REAL_CALL_PROVENANCE_INVALID")
        candidates = self.database.fetch_all(
            "SELECT c.*, b.batch_index, b.source_section, b.source_text, "
            "b.source_blocks_json, b.status AS batch_status "
            "FROM requirement_candidates c JOIN analysis_batches b "
            "ON b.analysis_batch_id=c.analysis_batch_id "
            "WHERE c.analysis_run_id=:run ORDER BY b.batch_index, c.requirement_id",
            {"run": run_id},
        )
        if not candidates:
            raise AnalysisValidationError("NO_SAVED_CANDIDATES")
        if any(row["batch_status"] != "validated" for row in candidates):
            raise AnalysisValidationError("SAVED_BATCH_NOT_VALIDATED")
        return {
            "run": run,
            "call": calls[0],
            "candidates": candidates,
        }

    def _create_attempt(
        self,
        attempt_id: str,
        idempotency_key: str,
        context: dict[str, Any],
    ) -> None:
        run = context["run"]
        candidates = context["candidates"]
        with self.database.transaction() as connection:
            connection.execute(
                text(
                    "INSERT INTO offline_revalidation_attempts("
                    "offline_revalidation_attempt_id,idempotency_key,parent_analysis_run_id,"
                    "source_analysis_run_id,source_llm_call_id,old_validator_version,"
                    "new_validator_version,provider_status,status,candidate_count,llm_call_count,"
                    "false_negative_reason) VALUES "
                    "(:id,:key,:parent,:source,:call,:old,:new,"
                    "'offline_revalidation_of_real_result','running',:count,0,:reason)"
                ),
                {
                    "id": attempt_id,
                    "key": idempotency_key,
                    "parent": run["parent_analysis_run_id"],
                    "source": run["analysis_run_id"],
                    "call": context["call"]["llm_call_id"],
                    "old": LEGACY_AGGREGATE_VALIDATOR_VERSION,
                    "new": AGGREGATE_VALIDATOR_VERSION,
                    "count": len(candidates),
                    "reason": (
                        "Legacy validator required an Arabic digit after a lower-bound phrase "
                        "and rejected an evidenced English number word."
                    ),
                },
            )
            for candidate in candidates:
                connection.execute(
                    text(
                        "INSERT INTO offline_revalidation_candidate_links("
                        "offline_revalidation_attempt_id,candidate_id) VALUES (:attempt,:candidate)"
                    ),
                    {"attempt": attempt_id, "candidate": candidate["candidate_id"]},
                )

    def _revalidate_candidates(
        self,
        attempt_id: str,
        context: dict[str, Any],
    ) -> tuple[dict[str, Any], list[NormalizedConstraint]]:
        run = context["run"]
        normalized_prd = normalize_prd(str(run["content"]))
        grouped: dict[int, list[dict[str, Any]]] = {}
        for candidate in context["candidates"]:
            grouped.setdefault(int(candidate["batch_index"]), []).append(candidate)
        validated: list[tuple[BatchSpec, dict[str, Any]]] = []
        service = AnalysisService(self.database, schemas=self.schemas)
        for batch_index, rows in sorted(grouped.items()):
            first = rows[0]
            blocks = [
                SourceBlock(**block) for block in json.loads(str(first["source_blocks_json"]))
            ]
            sections = json.loads(str(first["source_section"]))
            spec = BatchSpec(
                batch_id=f"BAT-{batch_index:03d}",
                index=batch_index,
                source_sections=sections,
                source_text=str(first["source_text"]),
            )
            requirements = [json.loads(str(row["payload_json"])) for row in rows]
            payload = {
                "batch_id": spec.batch_id,
                "source_sections": sections,
                "requirements": requirements,
                "unsupported": [],
                "reported_count": len(requirements),
                "batch_complete": True,
            }
            validate_source_references(payload, blocks, normalized_prd)
            self.schemas.validate("requirement_batch.schema.json", payload)
            service._validate_batch_domain(payload, spec)
            validated.append((spec, payload))
        aggregate = service._aggregate(str(run["content_hash"]), validated)
        self.schemas.validate("requirement_aggregate.schema.json", aggregate)
        constraints = service._validate_aggregate_domain(aggregate)
        if not any(constraint.value == 6 for constraint in constraints):
            raise AnalysisValidationError("USERNAME_MINIMUM_SIX_MISSING")
        return aggregate, constraints

    def _promote(
        self,
        attempt_id: str,
        context: dict[str, Any],
        aggregate: dict[str, Any],
        constraints: list[NormalizedConstraint],
    ) -> None:
        run = context["run"]
        with self.database.transaction() as connection:
            existing = connection.execute(
                text("SELECT COUNT(*) FROM requirements WHERE analysis_run_id=:run"),
                {"run": run["analysis_run_id"]},
            ).scalar_one()
            if existing:
                raise AnalysisValidationError("FORMAL_REQUIREMENTS_ALREADY_EXIST")
            for constraint in constraints:
                connection.execute(
                    text(
                        "INSERT INTO aggregate_constraint_audits("
                        "aggregate_constraint_audit_id,offline_revalidation_attempt_id,"
                        "requirement_id,source_block_id,source_excerpt_hash,normalized_input,"
                        "normalized_result_json,validation_status,reason) VALUES "
                        "(:id,:attempt,:requirement,:block,:hash,:input,:result,'valid',:reason)"
                    ),
                    {
                        "id": new_id("ACA"),
                        "attempt": attempt_id,
                        "requirement": constraint.source_requirement_id,
                        "block": constraint.source_block_id,
                        "hash": hashlib.sha256(
                            constraint.source_excerpt.encode("utf-8")
                        ).hexdigest(),
                        "input": normalize_constraint_text(constraint.source_excerpt),
                        "result": self.database.encode_json(constraint.as_dict()),
                        "reason": "DETERMINISTIC_SAME_REQUIREMENT_SOURCE_CONSTRAINT",
                    },
                )
            for requirement in aggregate["requirements"]:
                connection.execute(
                    text(
                        "INSERT INTO requirements("
                        "row_id,requirement_id,project_id,prd_version_id,analysis_run_id,"
                        "offline_revalidation_attempt_id,title,description,requirement_type,"
                        "source_section,source_excerpt,payload_json) VALUES "
                        "(:row,:requirement,:project,:prd,:run,:attempt,:title,:description,:type,"
                        ":section,:excerpt,:payload)"
                    ),
                    {
                        "row": new_id("REQV"),
                        "requirement": requirement["requirement_id"],
                        "project": run["project_id"],
                        "prd": run["version_id"],
                        "run": run["analysis_run_id"],
                        "attempt": attempt_id,
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
                            "relationship_id,analysis_run_id,source_requirement_id,"
                            "target_requirement_id,relationship_type) VALUES "
                            "(:id,:run,:source,:target,'depends_on')"
                        ),
                        {
                            "id": new_id("RRL"),
                            "run": run["analysis_run_id"],
                            "source": requirement["requirement_id"],
                            "target": dependency,
                        },
                    )
            connection.execute(
                text(
                    "UPDATE offline_revalidation_attempts SET status='succeeded',"
                    "completed_at=CURRENT_TIMESTAMP WHERE offline_revalidation_attempt_id=:id"
                ),
                {"id": attempt_id},
            )

    def _result(self, row: dict[str, Any]) -> OfflineRevalidationResult:
        count = self.database.fetch_one(
            "SELECT COUNT(*) AS count FROM requirements "
            "WHERE offline_revalidation_attempt_id=:attempt",
            {"attempt": row["offline_revalidation_attempt_id"]},
        )
        return OfflineRevalidationResult(
            attempt_id=str(row["offline_revalidation_attempt_id"]),
            status=str(row["status"]),
            source_analysis_run_id=str(row["source_analysis_run_id"]),
            parent_analysis_run_id=str(row["parent_analysis_run_id"]),
            candidate_count=int(row["candidate_count"]),
            formal_requirement_count=int(count["count"]) if count else 0,
            llm_call_count=int(row["llm_call_count"]),
            validator_version=str(row["new_validator_version"]),
        )


def _safe_error(error: Exception) -> str:
    if isinstance(error, AnalysisValidationError):
        return str(error)
    return type(error).__name__
