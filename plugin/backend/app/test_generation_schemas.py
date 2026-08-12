from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEST_CASE_SCHEMA_ROOT = PROJECT_ROOT / "schemas" / "test-cases" / "v1.8"
LEGACY_TEST_CASE_SCHEMA_ROOT = PROJECT_ROOT / "schemas" / "test-cases" / "v1"
TEST_CASE_SCHEMA_VERSION = "test-cases@1.8.0"


class TestCaseSchemas:
    names = (
        "test_case_candidate.schema.json",
        "raw_test_case_candidate.schema.json",
        "generation_plan.schema.json",
        "api_case_batch.schema.json",
        "ui_case_batch.schema.json",
        "manual_case_batch.schema.json",
        "test_case_candidate_aggregate.schema.json",
    )

    def __init__(self, root: Path = TEST_CASE_SCHEMA_ROOT) -> None:
        self.root = root
        self.schemas: dict[str, dict[str, Any]] = {
            name: json.loads((root / name).read_text(encoding="utf-8")) for name in self.names
        }
        resources = [
            (str(schema["$id"]), Resource.from_contents(schema)) for schema in self.schemas.values()
        ]
        legacy_candidate = json.loads(
            (LEGACY_TEST_CASE_SCHEMA_ROOT / "test_case_candidate.schema.json").read_text(
                encoding="utf-8"
            )
        )
        resources.append((str(legacy_candidate["$id"]), Resource.from_contents(legacy_candidate)))
        self.registry = Registry().with_resources(resources)
        for schema in self.schemas.values():
            Draft202012Validator.check_schema(schema)

    def validate(self, name: str, instance: Any) -> None:
        Draft202012Validator(
            self.schemas[name],
            registry=self.registry,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        ).validate(instance)
