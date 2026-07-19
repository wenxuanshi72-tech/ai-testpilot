from __future__ import annotations

from typing import Any

import httpx
import pytest

from plugin.backend.app.prompts import PromptRegistry
from plugin.backend.app.providers import (
    DeepSeekProvider,
    MockLLMProvider,
    ProviderCallError,
    ProviderConfigurationError,
)


def _provider(
    *,
    base_url: str = "https://api.deepseek.com",
    model: str = "deepseek-v4-pro",
) -> DeepSeekProvider:
    return DeepSeekProvider(
        base_url=base_url,
        model=model,
        timeout_seconds=5.0,
        max_tokens=1024,
        prompts=PromptRegistry(),
    )


def test_deepseek_configuration_is_strict(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(ProviderConfigurationError, match="not configured"):
        _provider().validate_config()
    monkeypatch.setenv("DEEPSEEK_API_KEY", "local-test-value")
    with pytest.raises(ProviderConfigurationError, match="deprecated"):
        _provider(model="deepseek-chat").validate_config()
    with pytest.raises(ProviderConfigurationError, match="official"):
        _provider(base_url="https://example.invalid").validate_config()
    with pytest.raises(ProviderConfigurationError, match="not approved"):
        _provider(model="unknown").validate_config()


def test_deepseek_request_uses_json_and_disables_thinking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "local-test-value")
    captured: dict[str, Any] = {}

    class Response:
        status_code = 200
        headers = {"x-request-id": "provider-request"}

        @staticmethod
        def json() -> dict[str, Any]:
            return {
                "id": "completion-id",
                "choices": [{"message": {"content": '{"ok":true}'}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            }

    def fake_post(url: str, **kwargs: Any) -> Response:
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr("plugin.backend.app.providers.httpx.post", fake_post)
    response = _provider().analyze_outline("# PRD")
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    body = captured["json"]
    assert body["model"] == "deepseek-v4-pro"
    assert body["response_format"] == {"type": "json_object"}
    assert body["thinking"] == {"type": "disabled"}
    assert response.provider_request_id == "provider-request"
    assert response.input_tokens == 12
    assert response.output_tokens == 3


def test_deepseek_errors_are_typed_and_redacted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "do-not-expose")

    def timeout(*_args: Any, **_kwargs: Any) -> None:
        request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
        raise httpx.ReadTimeout("secret upstream details", request=request)

    monkeypatch.setattr("plugin.backend.app.providers.httpx.post", timeout)
    with pytest.raises(ProviderCallError) as captured:
        _provider().analyze_outline("# PRD")
    assert captured.value.error_type == "PROVIDER_TIMEOUT"
    assert captured.value.retryable is True
    assert "do-not-expose" not in str(captured.value)


def test_mock_provider_is_explicit_and_deterministic() -> None:
    provider = MockLLMProvider()
    assert provider.metadata.provider == "mock"
    assert provider.metadata.provider_mode == "mock"
    first = provider.analyze_outline("# A\ntext")
    second = MockLLMProvider().analyze_outline("# A\ntext")
    assert first.content == second.content


def test_requirement_prompt_renders_batch_boundaries() -> None:
    messages = PromptRegistry().requirement_messages(
        batch_id="BAT-007",
        source_sections=["# Auth"],
        source_blocks=[
            {
                "block_id": "BLK-L0001-L0001-0123456789",
                "start_line": 1,
                "end_line": 1,
                "text": "A user can login.",
            }
        ],
        max_requirements=4,
    )
    rendered = "\n".join(message["content"] for message in messages)
    assert "BAT-007" in rendered
    assert "# Auth" in rendered
    assert "A user can login." in rendered
    assert "4 requirements" in rendered


def test_recovery_prompt_hash_covers_every_sent_template() -> None:
    prompts = PromptRegistry()
    original = prompts.recovery_content_hash
    prompts._content["requirements_user.md"] += "\naudit change"
    assert prompts.recovery_content_hash != original
