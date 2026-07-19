from __future__ import annotations

import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATABASE_PATH = PROJECT_ROOT / "instance" / "plugin.db"


class PluginConfig:
    @staticmethod
    def as_mapping() -> dict[str, Any]:
        return {
            "PLUGIN_DATABASE_URL": os.getenv(
                "PLUGIN_DATABASE_URL", f"sqlite:///{DEFAULT_DATABASE_PATH.as_posix()}"
            ),
            "DEEPSEEK_BASE_URL": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            "DEEPSEEK_MODEL": os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro"),
            "LLM_TIMEOUT_SECONDS": float(os.getenv("LLM_TIMEOUT_SECONDS", "60")),
            "LLM_MAX_RETRIES": int(os.getenv("LLM_MAX_RETRIES", "2")),
            "LLM_MAX_OUTPUT_TOKENS": int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "4096")),
            "LLM_RUN_MAX_OUTPUT_TOKENS": int(os.getenv("LLM_RUN_MAX_OUTPUT_TOKENS", "26624")),
            "PRD_BATCH_MAX_CHARS": int(os.getenv("PRD_BATCH_MAX_CHARS", "1800")),
            "PRD_BATCH_MAX_REQUIREMENTS": int(os.getenv("PRD_BATCH_MAX_REQUIREMENTS", "12")),
            "TESTING": False,
        }
