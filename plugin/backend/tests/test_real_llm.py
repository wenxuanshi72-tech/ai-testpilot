from __future__ import annotations

import os

import pytest

from plugin.backend.real_acceptance import run_real_acceptance


@pytest.mark.real_llm
def test_real_deepseek_prd_acceptance() -> None:
    if os.getenv("PHASE5A_REAL_CONFIRM") != "YES":
        pytest.skip("Paid real-provider acceptance requires explicit confirmation.")
    summary = run_real_acceptance()
    assert summary["result"] == "PASS"
    assert summary["provider_mode"] == "real"
    assert summary["database_contains_api_key"] is False
