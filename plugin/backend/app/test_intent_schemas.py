from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEST_INTENT_SCHEMA_ROOT = PROJECT_ROOT / "schemas" / "test-intents" / "v2.9"
TEST_INTENT_SCHEMA_VERSION = "test-intent@2.9.0"


class TestIntentSchemas:
    names = (
        "test_intent.schema.json",
        "api_intent_batch.schema.json",
        "ui_intent_batch.schema.json",
        "manual_intent_batch.schema.json",
    )

    def __init__(self, root: Path = TEST_INTENT_SCHEMA_ROOT) -> None:
        self.root = root
        self.schemas: dict[str, dict[str, Any]] = {
            name: json.loads((root / name).read_text(encoding="utf-8")) for name in self.names
        }
        resources = [
            (str(schema["$id"]), Resource.from_contents(schema)) for schema in self.schemas.values()
        ]
        self.registry = Registry().with_resources(resources)
        for schema in self.schemas.values():
            Draft202012Validator.check_schema(schema)

    @property
    def content_hash(self) -> str:
        canonical = "\n".join(
            json.dumps(self.schemas[name], sort_keys=True, separators=(",", ":"))
            for name in sorted(self.schemas)
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def validate(self, name: str, instance: Any) -> None:
        Draft202012Validator(
            self.schemas[name],
            registry=self.registry,
            format_checker=Draft202012Validator.FORMAT_CHECKER,
        ).validate(instance)
