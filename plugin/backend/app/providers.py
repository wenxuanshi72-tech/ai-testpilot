from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from plugin.backend.app.prompts import PromptRegistry
from plugin.backend.app.test_generation_payloads import (
    contract_for_case_type,
    project_generation_slot,
)
from plugin.backend.app.test_generation_prompts import TestGenerationPromptRegistry
from plugin.backend.app.test_intent_mock import build_mock_intent_batch


@dataclass(frozen=True)
class ProviderMetadata:
    provider: str
    model: str
    provider_mode: str


@dataclass(frozen=True)
class ProviderResponse:
    content: str
    finish_reason: str | None
    input_tokens: int | None
    output_tokens: int | None
    latency_ms: int
    http_status: int
    provider_request_id: str | None
    max_tokens: int
    input_cache_hit_tokens: int | None = None
    input_cache_miss_tokens: int | None = None


class ProviderConfigurationError(Exception):
    pass


class ProviderCallError(Exception):
    def __init__(self, error_type: str, *, retryable: bool, http_status: int | None = None) -> None:
        super().__init__(error_type)
        self.error_type = error_type
        self.retryable = retryable
        self.http_status = http_status


class LLMProvider(Protocol):
    @property
    def metadata(self) -> ProviderMetadata: ...

    def validate_config(self) -> None: ...

    def analyze_outline(self, prd_text: str) -> ProviderResponse: ...

    def extract_requirements_batch(
        self,
        *,
        batch_id: str,
        source_sections: list[str],
        source_blocks: list[dict[str, object]],
        max_requirements: int,
        recovery: bool = False,
    ) -> ProviderResponse: ...
    def generate_test_cases(
        self,
        *,
        case_type: str,
        batch_id: str,
        generation_run_id: str,
        generation_slots: list[dict[str, Any]],
        max_cases: int,
        max_tokens: int,
        recovery: bool = False,
        validation_error: str | None = None,
    ) -> ProviderResponse: ...


class DeepSeekProvider:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        timeout_seconds: float,
        max_tokens: int,
        prompts: PromptRegistry,
        generation_prompts: TestGenerationPromptRegistry | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_tokens = max_tokens
        self.prompts = prompts
        self.generation_prompts = generation_prompts or TestGenerationPromptRegistry()

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata("deepseek", self.model, "real")

    def validate_config(self) -> None:
        if self.base_url != "https://api.deepseek.com":
            raise ProviderConfigurationError("DEEPSEEK_BASE_URL is not the approved official URL.")
        if self.model in {"deepseek-chat", "deepseek-reasoner"}:
            raise ProviderConfigurationError("A deprecated DeepSeek model alias is configured.")
        if self.model not in {"deepseek-v4-pro", "deepseek-v4-flash"}:
            raise ProviderConfigurationError("The configured DeepSeek model is not approved.")
        if not os.getenv("DEEPSEEK_API_KEY", "").strip():
            raise ProviderConfigurationError("DEEPSEEK_API_KEY is not configured.")

    def analyze_outline(self, prd_text: str) -> ProviderResponse:
        return self._call(self.prompts.outline_messages(prd_text), min(self.max_tokens, 2048))

    def extract_requirements_batch(
        self,
        *,
        batch_id: str,
        source_sections: list[str],
        source_blocks: list[dict[str, object]],
        max_requirements: int,
        recovery: bool = False,
    ) -> ProviderResponse:
        messages = self.prompts.requirement_messages(
            batch_id=batch_id,
            source_sections=source_sections,
            source_blocks=source_blocks,
            max_requirements=max_requirements,
            recovery=recovery,
        )
        return self._call(messages, self.max_tokens)

    def generate_test_cases(
        self,
        *,
        case_type: str,
        batch_id: str,
        generation_run_id: str,
        generation_slots: list[dict[str, Any]],
        max_cases: int,
        max_tokens: int,
        recovery: bool = False,
        validation_error: str | None = None,
    ) -> ProviderResponse:
        api_contract, ui_contract = contract_for_case_type(case_type)
        projected = [project_generation_slot(item, item["snapshot"]) for item in generation_slots]
        messages = self.generation_prompts.generation_messages(
            case_type=case_type,
            batch_id=batch_id,
            generation_run_id=generation_run_id,
            provider_mode="real",
            generation_slots=projected,
            max_cases=max_cases,
            recovery=recovery,
            validation_error=validation_error,
            api_contract=api_contract,
            ui_contract=ui_contract,
        )
        return self._call(messages, min(max_tokens, self.max_tokens))

    def _call(self, messages: list[dict[str, str]], max_tokens: int) -> ProviderResponse:
        self.validate_config()
        started = time.perf_counter()
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                    "thinking": {"type": "disabled"},
                    "max_tokens": max_tokens,
                    "stream": False,
                },
                timeout=self.timeout_seconds,
            )
        except httpx.TimeoutException as error:
            raise ProviderCallError("PROVIDER_TIMEOUT", retryable=True) from error
        except httpx.RequestError as error:
            raise ProviderCallError("PROVIDER_NETWORK", retryable=True) from error
        latency_ms = round((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            retryable = response.status_code == 429 or response.status_code >= 500
            category = {
                401: "PROVIDER_AUTHENTICATION",
                402: "PROVIDER_BALANCE",
                429: "PROVIDER_RATE_LIMIT",
            }.get(response.status_code, "PROVIDER_HTTP_ERROR")
            raise ProviderCallError(category, retryable=retryable, http_status=response.status_code)
        try:
            payload = response.json()
            choice = payload["choices"][0]
            content = choice["message"].get("content") or ""
            usage = payload.get("usage") or {}
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ProviderCallError(
                "PROVIDER_RESPONSE_SHAPE", retryable=False, http_status=response.status_code
            ) from error
        return ProviderResponse(
            content=str(content),
            finish_reason=choice.get("finish_reason"),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=latency_ms,
            http_status=response.status_code,
            provider_request_id=response.headers.get("x-request-id") or payload.get("id"),
            max_tokens=max_tokens,
            input_cache_hit_tokens=usage.get("prompt_cache_hit_tokens"),
            input_cache_miss_tokens=usage.get("prompt_cache_miss_tokens"),
        )


class MockLLMProvider:
    def __init__(
        self,
        responses: list[ProviderResponse] | None = None,
        *,
        model: str = "deterministic-fixture-v1",
    ) -> None:
        self.responses = list(responses or [])
        self.model = model
        self.call_count = 0

    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata("mock", self.model, "mock")

    def validate_config(self) -> None:
        return

    def analyze_outline(self, prd_text: str) -> ProviderResponse:
        if self.responses:
            return self._next()
        headings = [line for line in prd_text.splitlines() if line.startswith("#")]
        payload = {
            "document_summary": "Deterministic offline PRD outline.",
            "sections": [
                {
                    "section_id": f"SEC-{index:03d}",
                    "title": heading.lstrip("#").strip(),
                    "source_heading": heading,
                }
                for index, heading in enumerate(headings, 1)
            ],
            "outline_complete": True,
        }
        return self._response(payload, 512)

    def extract_requirements_batch(
        self,
        *,
        batch_id: str,
        source_sections: list[str],
        source_blocks: list[dict[str, object]],
        max_requirements: int,
        recovery: bool = False,
    ) -> ProviderResponse:
        if self.responses:
            return self._next()
        source_text = "\n\n".join(str(block["text"]) for block in source_blocks)
        requirements = self._requirements(source_text, source_sections[0], source_blocks)[
            :max_requirements
        ]
        return self._response(
            {
                "batch_id": batch_id,
                "source_sections": source_sections,
                "requirements": requirements,
                "unsupported": [],
                "reported_count": len(requirements),
                "batch_complete": True,
            },
            1024,
        )

    def generate_test_cases(
        self,
        *,
        case_type: str,
        batch_id: str,
        generation_run_id: str,
        generation_slots: list[dict[str, Any]],
        max_cases: int,
        max_tokens: int,
        recovery: bool = False,
        validation_error: str | None = None,
    ) -> ProviderResponse:
        if self.responses:
            return self._next()
        slot_defs = [
            {key: value for key, value in item.items() if key != "snapshot"}
            for item in generation_slots
        ]
        snapshots = {item["primary_requirement_id"]: item["snapshot"] for item in generation_slots}
        intents = build_mock_intent_batch(case_type, slot_defs, snapshots, max_cases)
        return self._response(
            {"intents": intents},
            max_tokens,
        )

    def _next(self) -> ProviderResponse:
        self.call_count += 1
        return self.responses.pop(0)

    def _response(self, value: object, max_tokens: int) -> ProviderResponse:
        self.call_count += 1
        return ProviderResponse(
            content=json.dumps(value),
            finish_reason="stop",
            input_tokens=100,
            output_tokens=100,
            latency_ms=1,
            http_status=200,
            provider_request_id=f"mock-{self.call_count}",
            max_tokens=max_tokens,
        )

    @staticmethod
    def _requirements(
        source: str, section: str, source_blocks: list[dict[str, object]]
    ) -> list[dict[str, object]]:
        lowered = source.lower()
        definitions = [
            (
                "username",
                "REQ-AUTH-USERNAME-001",
                "Username length",
                "minimum username length",
            ),
            ("register", "REQ-AUTH-REGISTRATION-001", "User registration", "register"),
            ("login", "REQ-AUTH-LOGIN-001", "User login", "login"),
            ("current-user", "REQ-AUTH-ME-001", "Current user lookup", "current-user"),
            ("logout", "REQ-AUTH-LOGOUT-001", "User logout", "logout"),
        ]
        output: list[dict[str, object]] = []
        lines = [line.strip() for line in source.splitlines() if len(line.strip()) >= 3]
        for tag, requirement_id, title, needle in definitions:
            if needle not in lowered:
                continue
            if tag != "username":
                suffix = hashlib.sha256(f"{source}|{needle}".encode()).hexdigest()[:8].upper()
                requirement_id = f"{requirement_id}-{suffix}"
            excerpt = next((line for line in lines if needle in line.lower()), lines[0])
            block_id = next(
                str(block["block_id"]) for block in source_blocks if excerpt in str(block["text"])
            )
            business_rules = (
                ["A username must contain at least 6 characters."] if tag == "username" else []
            )
            output.append(
                {
                    "requirement_id": requirement_id,
                    "title": title,
                    "description": (
                        f"The system shall support {title.lower()} as specified by the PRD."
                    ),
                    "requirement_type": "business_rule" if tag == "username" else "functional",
                    "source_section": section,
                    "source_block_id": block_id,
                    "source_excerpt": excerpt,
                    "acceptance_criteria": [
                        f"The documented {title.lower()} behavior is observable."
                    ],
                    "business_rules": business_rules,
                    "actors": ["user"],
                    "priority": "must",
                    "risk_level": "high" if tag == "username" else "medium",
                    "ambiguities": [],
                    "dependencies": [],
                    "testability": "testable",
                    "confidence": 1.0,
                    "tags": ["authentication", tag],
                }
            )
        return output
