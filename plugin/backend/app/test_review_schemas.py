from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from jsonschema import Draft202012Validator

REVIEW_SCHEMA_VERSION = "test-case-review@2.0.0"
EXECUTION_SNAPSHOT_SCHEMA_VERSION = "execution-snapshot@1.0.0"
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ReviewSchemas:
    def __init__(self) -> None:
        self.review = self._load("schemas/reviews/v2/review_decision.schema.json")
        self.freeze = self._load("schemas/reviews/v2/freeze_request.schema.json")
        self.revision = self._load("schemas/reviews/v2/human_revision.schema.json")
        self.snapshot = self._load("schemas/execution-snapshots/v1/execution_snapshot.schema.json")
        self._review_validator = Draft202012Validator(self.review)
        self._freeze_validator = Draft202012Validator(self.freeze)
        self._snapshot_validator = Draft202012Validator(self.snapshot)
        self._revision_validator = Draft202012Validator(self.revision)

    @staticmethod
    def _load(relative_path: str) -> dict[str, Any]:
        return cast(
            dict[str, Any],
            json.loads((PROJECT_ROOT / relative_path).read_text(encoding="utf-8")),
        )

    def validate_review(self, payload: dict[str, Any]) -> None:
        self._review_validator.validate(payload)

    def validate_freeze(self, payload: dict[str, Any]) -> None:
        self._freeze_validator.validate(payload)

    def validate_snapshot(self, payload: dict[str, Any]) -> None:
        self._snapshot_validator.validate(payload)

    def validate_revision(self, payload: dict[str, Any]) -> None:
        self._revision_validator.validate(payload)
