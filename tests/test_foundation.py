"""Non-business contract tests for the Phase 1 repository foundation."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_workspace_manifest_declares_both_frontends() -> None:
    manifest = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))

    assert manifest["private"] is True
    assert set(manifest["workspaces"]) == {"sut/frontend", "plugin/frontend"}


def test_python_configuration_targets_version_311() -> None:
    with (ROOT / "pyproject.toml").open("rb") as configuration_file:
        configuration = tomllib.load(configuration_file)

    assert configuration["project"]["requires-python"] == ">=3.11,<3.12"
    assert configuration["tool"]["ruff"]["target-version"] == "py311"
    assert configuration["tool"]["mypy"]["python_version"] == "3.11"


def test_safe_environment_template_is_versioned_without_real_environment() -> None:
    assert (ROOT / ".env.example").is_file()
    assert not (ROOT / ".env").exists()


def test_frontend_shells_remain_non_business_boundaries() -> None:
    for relative_path in ("sut/frontend/src/App.tsx", "plugin/frontend/src/App.tsx"):
        content = (ROOT / relative_path).read_text(encoding="utf-8")

        assert "/api/auth" not in content
        assert "axios." not in content
        assert "createBrowserRouter" not in content
