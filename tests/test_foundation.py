"""Non-business contract tests for the Phase 1 repository foundation."""

from __future__ import annotations

import json
import subprocess
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


def test_safe_environment_template_and_local_environment_git_hygiene() -> None:
    assert (ROOT / ".env.example").is_file()
    local_environment = ROOT / ".env"
    if local_environment.exists():
        ignored = subprocess.run(
            ["git", "check-ignore", "-q", "--", ".env"],
            cwd=ROOT,
            check=False,
        )
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", ".env"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        assert ignored.returncode == 0
        assert tracked.returncode != 0


def test_frontend_shells_remain_non_business_boundaries() -> None:
    for relative_path in ("sut/frontend/src/App.tsx", "plugin/frontend/src/App.tsx"):
        content = (ROOT / relative_path).read_text(encoding="utf-8")

        assert "/api/auth" not in content
        assert "axios." not in content
        assert "createBrowserRouter" not in content
