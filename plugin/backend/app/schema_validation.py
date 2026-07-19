from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_ROOT = PROJECT_ROOT / "schemas" / "requirements" / "v2"


class RequirementSchemas:
    names = (
        "prd_outline.schema.json",
        "requirement_batch.schema.json",
        "requirement_aggregate.schema.json",
    )

    def __init__(self, root: Path = SCHEMA_ROOT) -> None:
        self.schemas: dict[str, dict[str, Any]] = {
            name: json.loads((root / name).read_text(encoding="utf-8")) for name in self.names
        }
        resources = [
            (str(schema["$id"]), Resource.from_contents(schema)) for schema in self.schemas.values()
        ]
        self.registry = Registry().with_resources(resources)
        for schema in self.schemas.values():
            Draft202012Validator.check_schema(schema)

    def validate(self, name: str, instance: Any) -> None:
        validator = Draft202012Validator(self.schemas[name], registry=self.registry)
        validator.validate(instance)
