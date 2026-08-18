from __future__ import annotations

import argparse
import json
import shutil
import socket
import sqlite3
import subprocess
from pathlib import Path
from typing import Any

from plugin.backend.app.analysis import plan_batches
from plugin.backend.app.test_generation_budget import PRICING_VERSION

ROOT = Path(__file__).resolve().parents[1]
PRD_PATH = ROOT / "docs" / "prd" / "login_register_prd.md"
REFERENCE_DATABASE = ROOT / "instance" / "plugin.db"
PREFX_SUT_COMMIT = "bb24609"
PORTS = {"sut_backend": 5001, "sut_frontend": 5173, "plugin_backend": 5002, "plugin_frontend": 5174}


class PreflightError(RuntimeError):
    pass


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
    parser.add_argument("command", choices=["dry-run"])
    arguments = parser.parse_args()
    if arguments.command == "dry-run":
        print(json.dumps(dry_run(), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    raise PreflightError("UNSUPPORTED_COMMAND")


if __name__ == "__main__":
    raise SystemExit(main())
