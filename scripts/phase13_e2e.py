from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import ssl
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from plugin.backend.app.analysis import AnalysisService, content_hash, normalize_prd, plan_batches
from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.prompts import PromptRegistry
from plugin.backend.app.providers import DeepSeekProvider, LLMProvider, ProviderResponse
from plugin.backend.app.test_generation import TestGenerationService
from plugin.backend.app.test_generation_budget import (
    PRICING_VERSION,
    calculate_cost,
    estimate_serialized_value,
)
from plugin.backend.app.test_generation_prompts import TestGenerationPromptRegistry
from plugin.backend.real_test_generation_acceptance import (
    AcceptanceLimits,
    BudgetGuardProvider,
    _load_real_process_environment,
    build_dry_run_report,
)

ROOT = Path(__file__).resolve().parents[1]
PRD_PATH = ROOT / "docs" / "prd" / "login_register_prd.md"
REFERENCE_DATABASE = ROOT / "instance" / "plugin.db"
PREFX_SUT_COMMIT = "bb24609"
PORTS = {"sut_backend": 5001, "sut_frontend": 5173, "plugin_backend": 5002, "plugin_frontend": 5174}
ANALYSIS_MAX_ATTEMPTS = 9
ANALYSIS_BUDGET_MICROUSD = 26_400
GENERATION_MAX_ATTEMPTS = 40
GENERATION_BUDGET_MICROUSD = 250_000


class PreflightError(RuntimeError):
    pass


class AnalysisBudgetProvider:
    def __init__(self, provider: DeepSeekProvider, prompts: PromptRegistry) -> None:
        self.provider = provider
        self.prompts = prompts
        self.call_count = 0
        self.actual_cost_microusd = 0

    @property
    def metadata(self):  # type: ignore[no-untyped-def]
        return self.provider.metadata

    def validate_config(self) -> None:
        self.provider.validate_config()

    def _call(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
        operation: Callable[[], ProviderResponse],
    ) -> ProviderResponse:
        if self.call_count >= ANALYSIS_MAX_ATTEMPTS:
            raise PreflightError("ANALYSIS_CALL_LIMIT_EXHAUSTED")
        estimate = estimate_serialized_value(messages)
        worst = calculate_cost(
            provider_mode="real",
            input_tokens=estimate.budget_tokens,
            output_tokens=max_tokens,
            estimated=True,
        )
        if self.actual_cost_microusd + worst.estimated_cost_microusd > ANALYSIS_BUDGET_MICROUSD:
            raise PreflightError("ANALYSIS_COST_RESERVATION_EXCEEDED")
        self.call_count += 1
        response = operation()
        actual = calculate_cost(
            provider_mode="real",
            input_tokens=int(response.input_tokens or 0),
            output_tokens=int(response.output_tokens or 0),
            input_cache_hit_tokens=response.input_cache_hit_tokens,
            input_cache_miss_tokens=response.input_cache_miss_tokens,
        )
        self.actual_cost_microusd += actual.actual_cost_microusd
        return response

    def analyze_outline(self, prd_text: str) -> ProviderResponse:
        maximum = min(self.provider.max_tokens, 2048)
        return self._call(
            self.prompts.outline_messages(prd_text),
            maximum,
            lambda: self.provider.analyze_outline(prd_text),
        )

    def correct_outline(
        self, prd_text: str, invalid_outline: dict[str, object], validation_error: str
    ) -> ProviderResponse:
        maximum = min(self.provider.max_tokens, 2048)
        return self._call(
            self.prompts.outline_correction_messages(prd_text, invalid_outline, validation_error),
            maximum,
            lambda: self.provider.correct_outline(prd_text, invalid_outline, validation_error),
        )

    def extract_requirements_batch(
        self,
        *,
        batch_id: str,
        source_sections: list[str],
        source_blocks: list[dict[str, object]],
        max_requirements: int,
        recovery: bool = False,
    ) -> ProviderResponse:
        messages = self.prompts.requirement_messages(
            batch_id=batch_id,
            source_sections=source_sections,
            source_blocks=source_blocks,
            max_requirements=max_requirements,
            recovery=recovery,
        )
        return self._call(
            messages,
            self.provider.max_tokens,
            lambda: self.provider.extract_requirements_batch(
                batch_id=batch_id,
                source_sections=source_sections,
                source_blocks=source_blocks,
                max_requirements=max_requirements,
                recovery=recovery,
            ),
        )

    def generate_test_cases(self, **_kwargs: Any) -> ProviderResponse:
        raise PreflightError("ANALYSIS_PROVIDER_GENERATION_FORBIDDEN")


def _git(*arguments: str) -> str:
    git_executable = shutil.which("git")
    if git_executable is None:
        raise PreflightError("GIT_NOT_FOUND")
    result = subprocess.run(  # noqa: S603 - fixed executable and internal arguments only
        [git_executable, *arguments], cwd=ROOT, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        return connection.connect_ex(("127.0.0.1", port)) != 0


def _network_preflight() -> dict[str, Any]:
    addresses = socket.getaddrinfo("api.deepseek.com", 443, type=socket.SOCK_STREAM)
    if not addresses:
        raise PreflightError("DEEPSEEK_DNS_FAILED")
    with socket.create_connection(("api.deepseek.com", 443), timeout=10) as connection:
        with ssl.create_default_context().wrap_socket(
            connection, server_hostname="api.deepseek.com"
        ) as secured:
            tls_version = secured.version()
    try:
        response = httpx.get("https://api.deepseek.com", timeout=10, follow_redirects=False)
    except httpx.HTTPError as error:
        raise PreflightError("DEEPSEEK_HTTPS_FAILED") from error
    return {
        "dns": True,
        "tcp_443": True,
        "tls": bool(tls_version),
        "safe_http_status": response.status_code,
    }


def _database_checks(database: PluginDatabase) -> dict[str, Any]:
    integrity = database.fetch_one("PRAGMA integrity_check")
    foreign_keys = database.fetch_all("PRAGMA foreign_key_check")
    return {
        "integrity": integrity == {"integrity_check": "ok"},
        "foreign_key_violations": len(foreign_keys),
    }


def _prepare_session() -> tuple[Path, PluginDatabase, dict[str, str]]:
    session_id = datetime.now(UTC).strftime("E2E-%Y%m%dT%H%M%SZ")
    session = ROOT / "tmp" / "phase13-e2e" / session_id
    if session.exists():
        raise PreflightError("E2E_SESSION_COLLISION")
    session.mkdir(parents=True)
    (session / "artifacts").mkdir()
    database_path = session / "plugin.db"
    database = PluginDatabase(f"sqlite:///{database_path.as_posix()}")
    database.migrate()
    checks = _database_checks(database)
    if not checks["integrity"] or checks["foreign_key_violations"]:
        raise PreflightError("ISOLATED_DATABASE_INVALID")
    backup = session / "plugin-before-e2e.db"
    shutil.copy2(database_path, backup)
    digest = hashlib.sha256(database_path.read_bytes()).hexdigest()
    if hashlib.sha256(backup.read_bytes()).hexdigest() != digest:
        raise PreflightError("ISOLATED_DATABASE_BACKUP_HASH_MISMATCH")
    with sqlite3.connect(f"file:{backup.as_posix()}?mode=ro", uri=True, timeout=5) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise PreflightError("ISOLATED_DATABASE_BACKUP_INVALID")
    return session, database, {"database_backup_sha256": digest}


def execute_ai() -> dict[str, Any]:
    preflight = dry_run(require_clean=True)
    if not all(item["available"] for item in preflight["ports"].values()):
        raise PreflightError("PHASE13_PORT_IN_USE")
    network = _network_preflight()
    _load_real_process_environment("deepseek-v4-pro")
    session: Path | None = None
    try:
        session, database, backup = _prepare_session()
        normalized = normalize_prd(PRD_PATH.read_text(encoding="utf-8"))
        project = database.create_project(
            "Phase 13 E2E Authentication Loop " + datetime.now(UTC).isoformat()
        )
        prd = database.import_prd(
            str(project["project_id"]),
            "Login and registration PRD",
            normalized,
            content_hash(normalized),
            "text/markdown",
        )
        prompts = PromptRegistry()
        provider = DeepSeekProvider(
            base_url=os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-pro"),
            timeout_seconds=60,
            max_tokens=4096,
            prompts=prompts,
        )
        analysis_provider = AnalysisBudgetProvider(provider, prompts)
        analysis = AnalysisService(
            database,
            prompts=prompts,
            batch_max_chars=1800,
            batch_max_requirements=12,
            max_retries=2,
            call_max_output_tokens=4096,
            run_max_output_tokens=26624,
        ).start(
            str(prd["version_id"]),
            analysis_provider,
            f"phase13:{content_hash(normalized)}:analysis",
        )
        analysis_id = str(analysis["analysis_run_id"])
        requirement_row = database.fetch_one(
            "SELECT COUNT(*) AS count FROM requirements WHERE analysis_run_id=:run",
            {"run": analysis_id},
        )
        if requirement_row is None:
            raise PreflightError("PHASE13_REQUIREMENT_COUNT_UNAVAILABLE")
        requirement_count = int(requirement_row["count"])
        if analysis["status"] != "succeeded" or requirement_count != 19:
            raise PreflightError(
                f"PHASE13_ANALYSIS_FAILED:{analysis_id}:{analysis['status']}:{requirement_count}"
            )
        generation_service = TestGenerationService(
            database,
            max_tokens_per_batch=3072,
            max_retries=1,
            max_corrections_per_run=8,
            max_provider_retries_per_run=0,
            max_total_provider_calls=40,
            max_run_cost_usd=Decimal("0.250000"),
        )
        generation_plan = generation_service.preflight(str(project["project_id"]))
        generation_limits = AcceptanceLimits(
            max_calls=GENERATION_MAX_ATTEMPTS,
            max_retries=8,
            budget_microusd=GENERATION_BUDGET_MICROUSD,
            max_output_tokens=3072,
            max_provider_retries=0,
        )
        generation_report = build_dry_run_report(
            database,
            project_id=str(project["project_id"]),
            limits=generation_limits,
            resume_run_id=None,
        )
        if (
            len(generation_plan["requirements"]) != 19
            or int(generation_plan["generation_slot_count"]) != 46
            or len(generation_plan["batches"]) != 17
            or generation_report["planned_call_count"] != 17
        ):
            raise PreflightError("PHASE13_GENERATION_PLAN_MISMATCH")
        generation_prompts = TestGenerationPromptRegistry()
        generation_provider: LLMProvider = BudgetGuardProvider(
            provider,
            limits=generation_limits,
            prompts=generation_prompts,
            reservation_costs={
                str(key): int(value)
                for key, value in generation_report["reservation_costs"].items()
            },
        )
        generation = generation_service.start(
            str(project["project_id"]),
            generation_provider,
            f"phase13:{analysis_id}:generation",
        )
        generation_calls = int(generation_provider.call_count)  # type: ignore[attr-defined]
        generation_cost = int(generation_provider.actual_cost_microusd)  # type: ignore[attr-defined]
        if generation.status != "validated_pending_review" or generation.candidate_count != 46:
            raise PreflightError(
                f"PHASE13_GENERATION_FAILED:{generation.run_id}:{generation.status}:"
                f"{generation.candidate_count}"
            )
        checks = _database_checks(database)
        result = {
            "status": "AWAITING_REAL_HUMAN_REVIEW",
            "session": session.relative_to(ROOT).as_posix(),
            "project_id": project["project_id"],
            "prd_version_id": prd["version_id"],
            "analysis_run_id": analysis_id,
            "analysis_calls": analysis_provider.call_count,
            "analysis_cost_microusd": analysis_provider.actual_cost_microusd,
            "requirements": requirement_count,
            "generation_run_id": generation.run_id,
            "generation_calls": generation_calls,
            "generation_cost_microusd": generation_cost,
            "candidates": generation.candidate_count,
            "combined_calls": analysis_provider.call_count + generation_calls,
            "combined_cost_microusd": analysis_provider.actual_cost_microusd + generation_cost,
            "network": network,
            "database": checks,
            **backup,
            "next_gate": "NAMED_HUMAN_REVIEW_AND_CLASSIFICATION",
        }
        if result["combined_calls"] > 49 or result["combined_cost_microusd"] > 276_400:
            raise PreflightError("PHASE13_COMBINED_AUTHORIZATION_EXCEEDED")
        (session / "ai-stage-summary.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return result
    finally:
        for name in ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "DEEPSEEK_MODEL"):
            os.environ.pop(name, None)


def _reference_generation_plan() -> dict[str, Any]:
    if not REFERENCE_DATABASE.is_file():
        raise PreflightError("REFERENCE_DATABASE_NOT_FOUND")
    uri = f"file:{REFERENCE_DATABASE.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT plan_json FROM test_generation_runs WHERE status="
            "'validated_pending_review' ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        requirements = connection.execute("SELECT COUNT(*) FROM requirements").fetchone()[0]
    if not row:
        raise PreflightError("ACCEPTED_REFERENCE_PLAN_NOT_FOUND")
    plan = json.loads(str(row["plan_json"]))
    batches = list(plan.get("batches", []))
    return {
        "reference_only": True,
        "requirements": int(requirements),
        "slots": int(plan.get("generation_slot_count", 0)),
        "batches": len(batches),
        "batch_mix": {
            case_type: sum(1 for batch in batches if batch.get("case_type") == case_type)
            for case_type in ("api", "ui", "manual")
        },
    }


def dry_run(*, require_clean: bool = True) -> dict[str, Any]:
    branch = _git("branch", "--show-current")
    status = _git("status", "--porcelain")
    if branch != "test/end-to-end-loop":
        raise PreflightError(f"WRONG_BRANCH:{branch}")
    if require_clean and status:
        raise PreflightError("WORKTREE_NOT_CLEAN")
    required = [
        PRD_PATH,
        ROOT / "plugin" / "backend" / "app" / "analysis.py",
        ROOT / "plugin" / "backend" / "app" / "test_generation.py",
        ROOT / "scripts" / "run_api_baseline.py",
        ROOT / "scripts" / "run_ui_baseline.py",
    ]
    missing = [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()]
    if missing:
        raise PreflightError("REQUIRED_FILES_MISSING:" + ",".join(missing))
    if _git("check-ignore", "--", ".env") == "":
        raise PreflightError("ENV_NOT_IGNORED")
    if _git("ls-files", "--", ".env"):
        raise PreflightError("ENV_TRACKED")
    content = PRD_PATH.read_text(encoding="utf-8")
    analysis_batches = plan_batches(content, 1800)
    generation = _reference_generation_plan()
    tools = {
        "python": shutil.which("python") is not None,
        "node": shutil.which("node") is not None,
        "git": shutil.which("git") is not None,
    }
    return {
        "status": "READY_FOR_PAID_AUTHORIZATION",
        "writes_performed": 0,
        "provider_calls_performed": 0,
        "formal_ai_runs_created": 0,
        "branch": branch,
        "prd": PRD_PATH.relative_to(ROOT).as_posix(),
        "new_project": "Phase 13 E2E Authentication Loop <timestamp>",
        "isolation": {
            "database": "tmp/phase13-e2e/<session>/plugin.db",
            "artifacts": "tmp/phase13-e2e/<session>/artifacts",
            "sut_database": "tmp/phase13-e2e/<session>/sut.db",
            "pre_fix_sut_commit": PREFX_SUT_COMMIT,
            "reuse_existing_provider_results": False,
        },
        "provider": {
            "mode": "real",
            "provider": "deepseek",
            "model": "deepseek-v4-pro",
            "thinking": "disabled",
            "mock_fallback": False,
            "pricing_version": PRICING_VERSION,
        },
        "analysis_plan": {
            "outline_calls": 1,
            "requirement_batches": len(analysis_batches),
            "initial_calls": 1 + len(analysis_batches),
            "maximum_attempts": 9,
            "maximum_cost_usd": "0.026400",
        },
        "generation_plan_reference": generation,
        "generation_limits": {
            "initial_calls": generation["batches"],
            "structure_corrections": 8,
            "provider_attempts": 40,
            "maximum_cost_usd": "0.250000",
        },
        "combined_authorization_request": {
            "maximum_provider_attempts": 49,
            "maximum_content_calls": 34,
            "maximum_cost_usd": "0.276400",
        },
        "ports": {
            name: {"port": port, "available": _port_available(port)} for name, port in PORTS.items()
        },
        "tools": tools,
        "next_gate": "EXPLICIT_REAL_PROVIDER_COST_AUTHORIZATION",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 13 isolated local E2E orchestrator.")
    parser.add_argument("command", choices=["dry-run", "execute-ai"])
    arguments = parser.parse_args()
    if arguments.command == "dry-run":
        print(json.dumps(dry_run(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    if arguments.command == "execute-ai":
        print(json.dumps(execute_ai(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    raise PreflightError("UNSUPPORTED_COMMAND")


if __name__ == "__main__":
    raise SystemExit(main())
