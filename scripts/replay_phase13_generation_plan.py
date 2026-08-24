from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.test_generation import TestGenerationService
from plugin.backend.app.test_generation_budget import calculate_cost
from plugin.backend.app.test_generation_plan_validation import validate_generation_plan
from plugin.backend.app.test_generation_planning import capacity_report_for_plan

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE = ROOT / "tmp" / "phase13-e2e" / "E2E-20260818T072720Z" / "plugin.db"
EXPECTED_ANALYSIS_RUN = "ANR-8D946E45913A418F899774282E8121C2"
MAXIMUM_STRUCTURE_CORRECTIONS = 8
MAXIMUM_PROVIDER_ATTEMPTS = 40
GENERATION_BUDGET_MICROUSD = 250_000


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _counts(path: Path) -> dict[str, Any]:
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5) as connection:
        analysis = connection.execute(
            "SELECT COUNT(*) FROM analysis_runs WHERE analysis_run_id=?",
            (EXPECTED_ANALYSIS_RUN,),
        ).fetchone()[0]
        project = connection.execute(
            "SELECT project_id FROM requirements WHERE analysis_run_id=? LIMIT 1",
            (EXPECTED_ANALYSIS_RUN,),
        ).fetchone()
        if analysis != 1 or project is None:
            raise RuntimeError("PHASE13_SECOND_ANALYSIS_NOT_FOUND")
        values = {
            "analysis_runs": connection.execute("SELECT COUNT(*) FROM analysis_runs").fetchone()[0],
            "requirements": connection.execute("SELECT COUNT(*) FROM requirements").fetchone()[0],
            "generation_runs": connection.execute(
                "SELECT COUNT(*) FROM test_generation_runs"
            ).fetchone()[0],
            "candidates": connection.execute(
                "SELECT COUNT(*) FROM test_case_candidates"
            ).fetchone()[0],
        }
        values["project_id"] = str(project[0])
        return values


def replay(database_path: Path) -> dict[str, Any]:
    before_hash = _hash(database_path)
    before = _counts(database_path)
    database = PluginDatabase(
        f"sqlite:///file:{database_path.resolve().as_posix()}?mode=ro&uri=true"
    )
    service = TestGenerationService(database)
    project_id = str(before.pop("project_id"))
    plan = service.preflight(project_id)
    snapshots = service._load_requirement_snapshots(project_id)  # noqa: SLF001
    capacities = capacity_report_for_plan(plan, snapshots, service.prompts)
    reservations = [
        calculate_cost(
            provider_mode="real",
            input_tokens=int(item["input_estimate"]["budget_tokens"]),
            output_tokens=int(item["max_tokens"]),
            estimated=True,
        ).estimated_cost_microusd
        for item in capacities
    ]
    worst_cost = sum(reservations) + sum(
        sorted(reservations, reverse=True)[:MAXIMUM_STRUCTURE_CORRECTIONS]
    )
    maximum_content_calls = len(plan["batches"]) + MAXIMUM_STRUCTURE_CORRECTIONS
    validated = validate_generation_plan(
        plan,
        snapshots,
        capacities,
        expected_requirement_count=19,
        maximum_structure_corrections=MAXIMUM_STRUCTURE_CORRECTIONS,
        maximum_content_calls=maximum_content_calls,
        maximum_provider_attempts=MAXIMUM_PROVIDER_ATTEMPTS,
        worst_case_cost_microusd=worst_cost,
        budget_microusd=GENERATION_BUDGET_MICROUSD,
    )
    after = _counts(database_path)
    after.pop("project_id")
    after_hash = _hash(database_path)
    if before != after or before_hash != after_hash:
        raise RuntimeError("READ_ONLY_REPLAY_CHANGED_DATABASE")
    return {
        "mode": "offline_read_only_replay",
        "source_analysis_run_id": EXPECTED_ANALYSIS_RUN,
        "database_hash_before": before_hash,
        "database_hash_after": after_hash,
        "database_unchanged": True,
        "plan": validated.as_dict(),
        "initial_provider_calls": len(plan["batches"]),
        "maximum_structure_corrections": MAXIMUM_STRUCTURE_CORRECTIONS,
        "maximum_content_calls": maximum_content_calls,
        "maximum_provider_attempts": MAXIMUM_PROVIDER_ATTEMPTS,
        "generation_budget_microusd": GENERATION_BUDGET_MICROUSD,
        "worst_case_cost_microusd": worst_cost,
        "deltas": {
            "provider_calls": 0,
            "analysis_runs": 0,
            "test_generation_runs": 0,
            "candidates": 0,
        },
        "database_counts": after,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the Phase 13 generation plan offline.")
    parser.add_argument("--database", type=Path, default=DEFAULT_DATABASE)
    args = parser.parse_args()
    print(json.dumps(replay(args.database), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
