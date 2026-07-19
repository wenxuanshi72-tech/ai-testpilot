from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PROMPT_ROOT = PROJECT_ROOT / "prompts" / "prd-analysis" / "v2"
PROMPT_VERSION = "prd-analysis@2.0.0"
RECOVERY_PROMPT_VERSION = "prd-analysis-recovery@2.0.0"
SCHEMA_VERSION = "requirements@2.0.0"


class PromptRegistry:
    required_files = (
        "outline_system.md",
        "outline_user.md",
        "requirements_system.md",
        "requirements_user.md",
        "repair_system.md",
    )

    def __init__(self, root: Path = PROMPT_ROOT) -> None:
        self.root = root
        self._content = {
            name: (root / name).read_text(encoding="utf-8") for name in self.required_files
        }
        self._recovery_system = (root / "requirements_recovery_system.md").read_text(
            encoding="utf-8"
        )

    @property
    def content_hash(self) -> str:
        joined = "\n".join(f"{name}\n{self._content[name]}" for name in sorted(self._content))
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()

    def outline_messages(self, prd_text: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": self._content["outline_system.md"]},
            {
                "role": "user",
                "content": self._content["outline_user.md"].replace("{{prd_text}}", prd_text),
            },
        ]

    def requirement_messages(
        self,
        *,
        batch_id: str,
        source_sections: list[str],
        source_blocks: list[dict[str, object]],
        max_requirements: int,
        recovery: bool = False,
    ) -> list[dict[str, str]]:
        system = self._content["requirements_system.md"].replace(
            "{{max_requirements}}", str(max_requirements)
        )
        user = self._content["requirements_user.md"]
        user = user.replace("{{batch_id}}", batch_id)
        user = user.replace("{{source_sections}}", ", ".join(source_sections))
        user = user.replace(
            "{{source_blocks}}",
            json.dumps(source_blocks, ensure_ascii=False, separators=(",", ":")),
        )
        messages = [{"role": "system", "content": system}]
        if recovery:
            messages.append({"role": "system", "content": self._recovery_system})
        messages.append({"role": "user", "content": user})
        return messages

    @property
    def recovery_content_hash(self) -> str:
        joined = "\n".join(
            (
                self._content["requirements_system.md"],
                self._recovery_system,
                self._content["requirements_user.md"],
            )
        )
        return hashlib.sha256(joined.encode("utf-8")).hexdigest()
