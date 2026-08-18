from __future__ import annotations

import pytest

from plugin.backend.app.regression import RegressionGateError, RegressionService


def _row(status: str, *, version: int = 2, snapshot: str = "SNAP-1") -> dict[str, object]:
    return {
        "status": status,
        "case_version": version,
        "immutable_execution_snapshot_id": snapshot,
    }


def test_seeded_case_requires_real_fail_to_pass_transition() -> None:
    RegressionService._require_transition({"TC": _row("FAIL")}, {"TC": _row("PASS")}, "TC")
    with pytest.raises(RegressionGateError, match="SEEDED_CASE_NOT_FIXED"):
        RegressionService._require_transition({"TC": _row("FAIL")}, {"TC": _row("FAIL")}, "TC")


def test_regression_must_use_identical_frozen_case_versions() -> None:
    RegressionService._same_frozen_versions({"TC": _row("FAIL")}, {"TC": _row("PASS")})
    with pytest.raises(RegressionGateError, match="FROZEN_CASE_VERSION_CHANGED"):
        RegressionService._same_frozen_versions(
            {"TC": _row("FAIL")}, {"TC": _row("PASS", version=3)}
        )
