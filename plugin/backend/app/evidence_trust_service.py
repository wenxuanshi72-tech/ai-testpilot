from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from plugin.backend.app.evidence_trust import evaluate_evidence_trust

_RUN_ID = re.compile(r"^[A-Z][A-Z0-9]*-[A-F0-9]{32}$")
_PACKAGE_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,199}$")


class EvidenceTrustRequestError(Exception):
    pass


class EvidenceTrustService:
    """Resolve logical identifiers beneath fixed roots and run read-only evaluation."""

    def __init__(self, run_bundle_root: Path, reproduction_root: Path) -> None:
        self.run_bundle_root = run_bundle_root
        self.reproduction_root = reproduction_root

    def evaluate(self, run_id: str, reproduction_package_name: str | None = None) -> dict[str, Any]:
        if not _RUN_ID.fullmatch(run_id):
            raise EvidenceTrustRequestError("RUN_ID_INVALID")
        package_dir = None
        if reproduction_package_name is not None:
            if not _PACKAGE_NAME.fullmatch(reproduction_package_name):
                raise EvidenceTrustRequestError("REPRODUCTION_PACKAGE_NAME_INVALID")
            package_dir = self.reproduction_root / reproduction_package_name
        return evaluate_evidence_trust(
            self.run_bundle_root / run_id,
            reproduction_package_dir=package_dir,
        )
