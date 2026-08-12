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
            "TEST_GENERATION_MAX_REQUIREMENTS_PER_BATCH": int(
                os.getenv("TEST_GENERATION_MAX_REQUIREMENTS_PER_BATCH", "10")
            ),
            "TEST_GENERATION_MAX_CASES_PER_BATCH": int(
                os.getenv("TEST_GENERATION_MAX_CASES_PER_BATCH", "12")
            ),
            "TEST_GENERATION_MAX_OUTPUT_TOKENS": int(
                os.getenv("TEST_GENERATION_MAX_OUTPUT_TOKENS", "3072")
            ),
            "TEST_GENERATION_MAX_RETRIES": int(os.getenv("TEST_GENERATION_MAX_RETRIES", "2")),
            "TEST_GENERATION_MAX_CORRECTIONS_PER_BATCH": int(
                os.getenv("TEST_GENERATION_MAX_CORRECTIONS_PER_BATCH", "1")
            ),
            "TEST_GENERATION_MAX_CORRECTIONS_PER_RUN": int(
                os.getenv("TEST_GENERATION_MAX_CORRECTIONS_PER_RUN", "8")
            ),
            "TEST_GENERATION_MAX_PROVIDER_RETRIES_PER_BATCH": int(
                os.getenv("TEST_GENERATION_MAX_PROVIDER_RETRIES_PER_BATCH", "1")
            ),
            "TEST_GENERATION_MAX_PROVIDER_RETRIES_PER_RUN": int(
                os.getenv("TEST_GENERATION_MAX_PROVIDER_RETRIES_PER_RUN", "3")
            ),
            "TEST_GENERATION_MAX_TOTAL_PROVIDER_CALLS": int(
                os.getenv("TEST_GENERATION_MAX_TOTAL_PROVIDER_CALLS", "28")
            ),
            "TEST_GENERATION_MAX_COST_USD": os.getenv("TEST_GENERATION_MAX_COST_USD", "0.25"),
            "TESTING": False,
        }
