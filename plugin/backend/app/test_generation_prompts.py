from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from plugin.backend.app.test_intent_schemas import TEST_INTENT_SCHEMA_VERSION, TestIntentSchemas

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEST_GENERATION_PROMPT_ROOT = PROJECT_ROOT / "prompts" / "test-generation" / "v3"
TEST_GENERATION_PROMPT_VERSION = "test-generation@3.0.0"


class TestGenerationPromptRegistry:
    required_files = (
        "generation_planner_system.md",
        "generation_planner_user.md",
        "api_cases_system.md",
        "api_cases_user.md",
        "ui_cases_system.md",
        "ui_cases_user.md",
        "manual_cases_system.md",
        "manual_cases_user.md",
        "recovery_system.md",
    )

    def __init__(self, root: Path = TEST_GENERATION_PROMPT_ROOT) -> None:
        self.root = root
        self._content = {
            name: (root / name).read_text(encoding="utf-8") for name in self.required_files
        }
        schema = TestIntentSchemas().schemas["test_intent.schema.json"]
        api_properties = schema["$defs"]["api_intent"]["properties"]
        setup = schema["$defs"]["setup_api_request"]
        self.api_methods = tuple(api_properties["method"]["enum"])
        self.api_sessions = tuple(api_properties["session_semantics"]["enum"])
        self.api_setup_contract = (
            "setup=string|object;"
            f"required={','.join(setup['required'])};"
            f"allowed={','.join(setup['properties'])};"
            f"method={','.join(setup['properties']['method']['enum'])};"
            f"path_pattern={setup['properties']['path']['pattern']};"
            f"additionalProperties={str(setup['additionalProperties']).lower()};"
            "non-HTTP=>string;path!=N/A."
        )

    @property
    def content_hash(self) -> str:
        canonical = "\n".join(f"{name}\n{self._content[name]}" for name in sorted(self._content))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def generation_messages(
        self,
        *,
        case_type: str,
        batch_id: str,
        generation_run_id: str,
        provider_mode: str,
        generation_slots: list[dict[str, Any]],
        max_cases: int,
        recovery: bool = False,
        validation_error: str | None = None,
        api_contract: str = "",
        ui_contract: str = "",
    ) -> list[dict[str, str]]:
        if case_type not in {"api", "ui", "manual"}:
            raise ValueError("Unsupported case type")
        system = self._content[f"{case_type}_cases_system.md"].replace(
            "{{max_cases}}", str(max_cases)
        )
        system = self._replace_api_contract_values(system)
        user = self._content[f"{case_type}_cases_user.md"]
        replacements = {
            "{{batch_id}}": batch_id,
            "{{generation_run_id}}": generation_run_id,
            "{{provider_mode}}": provider_mode,
            "{{slots_json}}": json.dumps(
                generation_slots, ensure_ascii=False, separators=(",", ":")
            ),
            "{{api_contract}}": api_contract,
            "{{ui_contract}}": ui_contract,
        }
        for marker, value in replacements.items():
            user = user.replace(marker, value)
        messages = [{"role": "system", "content": system}]
        if recovery:
            recovery_content = self._content["recovery_system.md"].replace(
                "{{validation_error}}", validation_error or "UNSPECIFIED_VALIDATION_ERROR"
            )
            recovery_content = recovery_content.replace(
                "{{intent_schema_version}}", TEST_INTENT_SCHEMA_VERSION
            )
            type_rules = ""
            if case_type == "api":
                type_rules = (
                    "Preserve auth/session prerequisites. Choose the asserted request as the sole "
                    "method/path/integer expected_status; move prerequisites to schema-valid "
                    "setup_semantics; keep cleanup_intent; remove sequence. "
                    "method={{api_methods}}; "
                    "session_semantics={{api_sessions}}. Never guess by position or emit "
                    "sequence/complex/empty/null method, null status, or sequence session. "
                    "Obey the setup contract in the API system message exactly."
                )
            recovery_content = recovery_content.replace("{{type_recovery_rules}}", type_rules)
            recovery_content = self._replace_api_contract_values(recovery_content)
            messages.append({"role": "system", "content": recovery_content})
        messages.append({"role": "user", "content": user})
        return messages

    def planner_messages(
        self, slots: list[dict[str, Any]], limits: dict[str, Any]
    ) -> list[dict[str, str]]:
        user = self._content["generation_planner_user.md"]
        user = user.replace(
            "{{slots_json}}",
            json.dumps(slots, ensure_ascii=False, separators=(",", ":")),
        ).replace("{{limits_json}}", json.dumps(limits, separators=(",", ":")))
        return [
            {"role": "system", "content": self._content["generation_planner_system.md"]},
            {"role": "user", "content": user},
        ]

    @property
    def schema_version(self) -> str:
        return TEST_INTENT_SCHEMA_VERSION

    def _replace_api_contract_values(self, content: str) -> str:
        return (
            content.replace("{{api_methods}}", ", ".join(self.api_methods))
            .replace("{{api_sessions}}", ", ".join(self.api_sessions))
            .replace("{{api_setup_contract}}", self.api_setup_contract)
        )
