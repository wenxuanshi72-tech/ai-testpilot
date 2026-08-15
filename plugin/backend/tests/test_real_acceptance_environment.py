from __future__ import annotations

import os
from pathlib import Path

import pytest

import plugin.backend.real_test_generation_acceptance as acceptance


def test_real_environment_loader_allows_only_three_values_in_current_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = "sk-" + ("A" * 24)
    (tmp_path / ".env").write_text(
        "\n".join(
            (
                f"DEEPSEEK_API_KEY={key}",
                "DEEPSEEK_BASE_URL=https://api.deepseek.com",
                "DEEPSEEK_MODEL=deepseek-v4-pro",
                "UNRELATED_SECRET=must-not-load",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(acceptance, "PROJECT_ROOT", tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL", raising=False)
    monkeypatch.delenv("UNRELATED_SECRET", raising=False)
    acceptance._load_real_process_environment("deepseek-v4-pro")
    assert os.environ["DEEPSEEK_API_KEY"] == key
    assert os.environ["DEEPSEEK_BASE_URL"] == "https://api.deepseek.com"
    assert os.environ["DEEPSEEK_MODEL"] == "deepseek-v4-pro"
    assert "UNRELATED_SECRET" not in os.environ


@pytest.mark.parametrize(
    ("key", "base_url", "model", "error"),
    [
        ("placeholder", "https://api.deepseek.com", "deepseek-v4-pro", "API_KEY_INVALID"),
        ("valid", "https://example.invalid", "deepseek-v4-pro", "BASE_URL_NOT_OFFICIAL"),
        ("valid", "https://api.deepseek.com", "other-model", "MODEL_MISMATCH"),
    ],
)
def test_real_environment_loader_rejects_invalid_configuration_without_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    key: str,
    base_url: str,
    model: str,
    error: str,
) -> None:
    value = "sk-" + ("B" * 24) if key == "valid" else key
    (tmp_path / ".env").write_text(
        f"DEEPSEEK_API_KEY={value}\nDEEPSEEK_BASE_URL={base_url}\nDEEPSEEK_MODEL={model}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(acceptance, "PROJECT_ROOT", tmp_path)
    with pytest.raises(acceptance.RealAcceptanceError, match=error):
        acceptance._load_real_process_environment("deepseek-v4-pro")
