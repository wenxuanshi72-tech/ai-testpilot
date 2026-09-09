from __future__ import annotations

from pathlib import Path
from typing import Any

from plugin.backend.app.bug_reproduction import (
    BugReproductionError,
    verify_bug_reproduction_package,
)
from plugin.backend.app.run_artifact_bundles import (
    BUNDLE_VERIFIER_VERSION,
    RunArtifactBundleError,
    verify_run_artifact_bundle,
)

TRUST_POLICY_VERSION = "evidence-trust-policy@1.0.0"
TRUST_EVALUATOR_VERSION = "deterministic-trust-evaluator@1.0.0"


def _report(
    state: str,
    reason: str,
    *,
    run_id: str | None = None,
    bundle_hash: str | None = None,
    reproduction_result_id: str | None = None,
) -> dict[str, Any]:
    return {
        "policy_version": TRUST_POLICY_VERSION,
        "evaluator_version": TRUST_EVALUATOR_VERSION,
        "bundle_verifier_version": BUNDLE_VERIFIER_VERSION,
        "state": state,
        "reason": reason,
        "run_id": run_id,
        "bundle_hash": bundle_hash,
        "reproduction_result_id": reproduction_result_id,
    }


def evaluate_evidence_trust(
    bundle_dir: Path, *, reproduction_package_dir: Path | None = None
) -> dict[str, Any]:
    """Recompute trust from portable artifacts without trusting stored status labels."""
    try:
        manifest = verify_run_artifact_bundle(bundle_dir)
    except (OSError, RunArtifactBundleError) as error:
        return _report("UNVERIFIED", f"RUN_BUNDLE_INVALID:{error}")

    executed = {
        "run_id": str(manifest["run_id"]),
        "bundle_hash": str(manifest["bundle_hash"]),
    }
    if reproduction_package_dir is None:
        return _report("EXECUTED", "VALID_RUN_BUNDLE", **executed)

    try:
        package = verify_bug_reproduction_package(reproduction_package_dir)
    except (OSError, BugReproductionError, RunArtifactBundleError) as error:
        return _report("EXECUTED", f"REPRODUCTION_PACKAGE_INVALID:{error}", **executed)

    package_manifest = package["manifest"]
    reproduction = package["reproduction_result"]
    if (
        package_manifest["source_run_id"] != manifest["run_id"]
        or reproduction["source_manifest_hash"] != manifest["bundle_hash"]
    ):
        return _report("EXECUTED", "REPRODUCTION_SOURCE_MISMATCH", **executed)
    if reproduction["status"] != "REPRODUCED":
        return _report(
            "EXECUTED",
            f"REPRODUCTION_NOT_CONFIRMED:{reproduction['status']}",
            reproduction_result_id=str(reproduction["reproduction_result_id"]),
            **executed,
        )
    return _report(
        "VERIFIED",
        "INDEPENDENT_REPRODUCTION_CONFIRMED",
        reproduction_result_id=str(reproduction["reproduction_result_id"]),
        **executed,
    )
