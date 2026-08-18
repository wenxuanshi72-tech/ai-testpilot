from __future__ import annotations

from scripts.phase13_e2e import PORTS, PRD_PATH, dry_run


def test_phase13_dry_run_is_non_mutating_and_requires_real_provider_gate() -> None:
    result = dry_run(require_clean=False)
    assert result["writes_performed"] == 0
    assert result["provider_calls_performed"] == 0
    assert result["formal_ai_runs_created"] == 0
    assert result["provider"]["mode"] == "real"
    assert result["provider"]["mock_fallback"] is False
    assert result["next_gate"] == "EXPLICIT_REAL_PROVIDER_COST_AUTHORIZATION"
    assert result["isolation"]["reuse_existing_provider_results"] is False


def test_phase13_plan_uses_fixed_local_ports_and_real_prd() -> None:
    result = dry_run(require_clean=False)
    assert PRD_PATH.is_file()
    assert {item["port"] for item in result["ports"].values()} == set(PORTS.values())
    assert result["generation_plan_reference"]["requirements"] == 19
    assert result["generation_plan_reference"]["slots"] == 46
    assert result["generation_plan_reference"]["batches"] == 17
