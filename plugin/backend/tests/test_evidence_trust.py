from __future__ import annotations

from pathlib import Path

from plugin.backend.app.evidence_trust import evaluate_evidence_trust
from plugin.backend.tests.test_bug_reproduction import REPRODUCTION_RESULT_ID, _pair, _writer


def test_invalid_bundle_is_unverified(tmp_path: Path) -> None:
    report = evaluate_evidence_trust(tmp_path / "missing")

    assert report["state"] == "UNVERIFIED"
    assert report["reason"].startswith("RUN_BUNDLE_INVALID:")
    assert report["run_id"] is None


def test_valid_bundle_is_executed_without_reproduction(tmp_path: Path) -> None:
    source, _ = _pair(tmp_path)

    report = evaluate_evidence_trust(source)

    assert report["state"] == "EXECUTED"
    assert report["reason"] == "VALID_RUN_BUNDLE"
    assert report["run_id"].startswith("RUN-")
    assert len(report["bundle_hash"]) == 64


def test_independent_reproduced_package_is_verified(tmp_path: Path) -> None:
    source, reproduction = _pair(tmp_path)
    package = _writer(tmp_path, source, reproduction).write()

    report = evaluate_evidence_trust(source, reproduction_package_dir=package["package_path"])

    assert report["state"] == "VERIFIED"
    assert report["reason"] == "INDEPENDENT_REPRODUCTION_CONFIRMED"
    assert report["reproduction_result_id"] == REPRODUCTION_RESULT_ID


def test_not_reproduced_retains_executed_state(tmp_path: Path) -> None:
    source, reproduction = _pair(
        tmp_path,
        reproduction_status="PASS",
        reproduction_actual={"status": 400, "user_created": False},
    )
    package = _writer(tmp_path, source, reproduction).write()

    report = evaluate_evidence_trust(source, reproduction_package_dir=package["package_path"])

    assert report["state"] == "EXECUTED"
    assert report["reason"] == "REPRODUCTION_NOT_CONFIRMED:NOT_REPRODUCED"


def test_tampered_reproduction_retains_executed_state(tmp_path: Path) -> None:
    source, reproduction = _pair(tmp_path)
    package = _writer(tmp_path, source, reproduction).write()
    result_path = package["package_path"] / "reproduction-result.json"
    result_path.write_bytes(b"tampered")

    report = evaluate_evidence_trust(source, reproduction_package_dir=package["package_path"])

    assert report["state"] == "EXECUTED"
    assert report["reason"].startswith("REPRODUCTION_PACKAGE_INVALID:")


def test_package_for_other_source_cannot_verify_bundle(tmp_path: Path) -> None:
    source, reproduction = _pair(tmp_path / "first")
    package = _writer(tmp_path / "first", source, reproduction).write()
    other_source, _ = _pair(tmp_path / "other")

    report = evaluate_evidence_trust(other_source, reproduction_package_dir=package["package_path"])

    assert report["state"] == "EXECUTED"
    assert report["reason"] == "REPRODUCTION_SOURCE_MISMATCH"
