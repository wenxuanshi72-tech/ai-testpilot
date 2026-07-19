from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, text
from sqlalchemy.engine import Connection

from plugin.backend.app.ids import new_id

PROJECT_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS_DIR = PROJECT_ROOT / "plugin" / "backend" / "migrations"


class PluginDatabase:
    def __init__(self, url: str) -> None:
        self.url = url
        self.engine: Engine = create_engine(url, future=True)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", self._enable_foreign_keys)

    @staticmethod
    def _enable_foreign_keys(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    def migrate(self) -> None:
        if self.url.startswith("sqlite:///"):
            Path(self.url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS schema_migrations ("
                    "version TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
                )
            )
            applied = {
                row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))
            }
            for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if migration.stem in applied:
                    continue
                for statement in _split_sql(migration.read_text(encoding="utf-8")):
                    if statement:
                        connection.exec_driver_sql(statement)
                connection.execute(
                    text("INSERT INTO schema_migrations(version) VALUES (:version)"),
                    {"version": migration.stem},
                )

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        with self.engine.begin() as connection:
            yield connection

    def execute(self, statement: str, values: Mapping[str, Any] | None = None) -> None:
        with self.engine.begin() as connection:
            connection.execute(text(statement), values or {})

    def fetch_one(
        self, statement: str, values: Mapping[str, Any] | None = None
    ) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(text(statement), values or {}).mappings().first()
            return dict(row) if row else None

    def fetch_all(
        self, statement: str, values: Mapping[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(text(statement), values or {}).mappings().all()
            return [dict(row) for row in rows]

    def create_project(self, name: str) -> dict[str, Any]:
        project_id = new_id("PRJ")
        self.execute(
            "INSERT INTO projects(project_id, name, status) VALUES (:id, :name, 'active')",
            {"id": project_id, "name": name},
        )
        return (
            self.fetch_one("SELECT * FROM projects WHERE project_id=:id", {"id": project_id}) or {}
        )

    def import_prd(
        self, project_id: str, title: str, content: str, content_hash: str, media_type: str
    ) -> dict[str, Any]:
        existing = self.fetch_one(
            "SELECT prd_document_id FROM prd_documents WHERE project_id=:project AND title=:title",
            {"project": project_id, "title": title},
        )
        document_id = str(existing["prd_document_id"]) if existing else new_id("PRD")
        with self.transaction() as connection:
            if not existing:
                connection.execute(
                    text(
                        "INSERT INTO prd_documents(prd_document_id, project_id, title) "
                        "VALUES (:id, :project, :title)"
                    ),
                    {"id": document_id, "project": project_id, "title": title},
                )
            version_number = int(
                connection.execute(
                    text(
                        "SELECT COALESCE(MAX(version_number), 0) + 1 FROM prd_versions "
                        "WHERE prd_document_id=:document"
                    ),
                    {"document": document_id},
                ).scalar_one()
            )
            version_id = new_id("PRDV")
            connection.execute(
                text(
                    "INSERT INTO prd_versions(version_id, prd_document_id, version_number, "
                    "content, content_hash, media_type) VALUES "
                    "(:id, :document, :version, :content, :hash, :media_type)"
                ),
                {
                    "id": version_id,
                    "document": document_id,
                    "version": version_number,
                    "content": content,
                    "hash": content_hash,
                    "media_type": media_type,
                },
            )
        return (
            self.fetch_one("SELECT * FROM prd_versions WHERE version_id=:id", {"id": version_id})
            or {}
        )

    def insert_call_log(self, values: Mapping[str, Any]) -> str:
        payload = dict(values)
        payload.setdefault("llm_call_id", new_id("LLC"))
        self.execute(
            "INSERT INTO llm_call_logs("
            "llm_call_id, analysis_run_id, analysis_batch_id, call_type, provider, model, "
            "provider_mode, provider_request_id, prompt_version, schema_version, retry_count, "
            "http_status, finish_reason, input_tokens, output_tokens, max_tokens, latency_ms, "
            "validation_status, error_type, redacted_error) VALUES ("
            ":llm_call_id, :analysis_run_id, :analysis_batch_id, :call_type, :provider, :model, "
            ":provider_mode, :provider_request_id, :prompt_version, :schema_version, :retry_count, "
            ":http_status, :finish_reason, :input_tokens, :output_tokens, :max_tokens, "
            ":latency_ms, "
            ":validation_status, :error_type, :redacted_error)",
            payload,
        )
        return str(payload["llm_call_id"])

    def insert_response_artifact(
        self,
        llm_call_id: str,
        response_content: str,
        parsed: dict[str, Any] | None,
        *,
        redaction_applied: bool,
    ) -> None:
        self.execute(
            "INSERT INTO llm_response_artifacts("
            "llm_call_id, response_content, response_hash, parsed_json, redaction_applied) "
            "VALUES (:call, :content, :hash, :parsed, :redacted)",
            {
                "call": llm_call_id,
                "content": response_content,
                "hash": hashlib.sha256(response_content.encode("utf-8")).hexdigest(),
                "parsed": self.encode_json(parsed) if parsed is not None else None,
                "redacted": int(redaction_applied),
            },
        )

    def insert_source_audits(
        self,
        *,
        run_id: str,
        batch_id: str,
        call_id: str | None,
        audits: list[dict[str, Any]],
    ) -> None:
        with self.transaction() as connection:
            for audit in audits:
                connection.execute(
                    text(
                        "INSERT INTO source_reference_audits("
                        "source_reference_audit_id, analysis_run_id, analysis_batch_id, "
                        "llm_call_id, requirement_id, source_block_id, model_excerpt, "
                        "resolved_excerpt, resolution_type, reason, block_start_line, "
                        "block_end_line) VALUES "
                        "(:id, :run, :batch, :call, :requirement, :block, :model, :resolved, "
                        ":resolution, :reason, :start, :end)"
                    ),
                    {
                        "id": new_id("SRA"),
                        "run": run_id,
                        "batch": batch_id,
                        "call": call_id,
                        "requirement": audit.get("requirement_id") or None,
                        "block": audit.get("source_block_id") or None,
                        "model": str(audit.get("model_excerpt") or ""),
                        "resolved": audit.get("resolved_excerpt"),
                        "resolution": audit["resolution_type"],
                        "reason": audit["reason"],
                        "start": audit.get("block_start_line"),
                        "end": audit.get("block_end_line"),
                    },
                )

    @staticmethod
    def encode_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _split_sql(script: str) -> list[str]:
    statements: list[str] = []
    pending = ""
    for line in script.splitlines():
        pending += line + "\n"
        if sqlite3.complete_statement(pending):
            statements.append(pending.strip())
            pending = ""
    if pending.strip():
        raise ValueError("Incomplete SQL migration statement.")
    return statements
