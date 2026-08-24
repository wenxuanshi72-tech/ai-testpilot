from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from plugin.backend.app.analysis import AnalysisService, content_hash, normalize_prd, plan_batches
from plugin.backend.app.database import MIGRATIONS_DIR, PluginDatabase
from plugin.backend.app.outline_normalization import (
    OutlineNormalizationError,
    normalize_outline_section_ids,
)
from plugin.backend.app.providers import MockLLMProvider, ProviderResponse
from plugin.backend.app.schema_validation import RequirementSchemas

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = Path(__file__).parent / "fixtures" / "phase13_outline_invalid_section_ids.json"


def _outline(*ids: object) -> dict[str, object]:
    return {
        "document_summary": "Outline",
        "sections": [
            {"section_id": value, "title": f"Title {index}", "source_heading": "# Auth"}
            for index, value in enumerate(ids, 1)
        ],
        "outline_complete": True,
    }


def _response(payload: dict[str, object]) -> ProviderResponse:
    return ProviderResponse(
        content=json.dumps(payload),
        finish_reason="stop",
        input_tokens=10,
        output_tokens=10,
        latency_ms=1,
        http_status=200,
        provider_request_id="offline",
        max_tokens=2048,
    )


def test_real_failure_fixture_normalizes_uniquely_and_passes_schema() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    accepted, audits = normalize_outline_section_ids(raw)
    assert [item["section_id"] for item in accepted["sections"]] == [
        "SEC-001",
        "SEC-002",
        "SEC-003",
        "SEC-004",
        "SEC-005",
        "SEC-006",
    ]
    assert [audit.original_section_id for audit in audits] == list("123456")
    RequirementSchemas().validate("prd_outline.schema.json", accepted)
    assert raw["sections"][0]["section_id"] == "1"


def test_legal_section_id_is_unchanged() -> None:
    accepted, audits = normalize_outline_section_ids(_outline("SEC-AUTH"))
    assert accepted["sections"][0]["section_id"] == "SEC-AUTH"
    assert audits == []


@pytest.mark.parametrize(
    ("original", "expected"),
    [
        ("sec-auth", "SEC-AUTH"),
        (" SEC auth flow ", "SEC-AUTH-FLOW"),
        ("auth_login", "SEC-AUTH-LOGIN"),
        ("SEC auth--login", "SEC-AUTH-LOGIN"),
    ],
)
def test_safe_ascii_formats_are_deterministic(original: str, expected: str) -> None:
    accepted, audits = normalize_outline_section_ids(_outline(original))
    assert accepted["sections"][0]["section_id"] == expected
    assert len(audits) == 1


@pytest.mark.parametrize("value", ["", "   ", None, "auth/login", "身份认证", "SEC-💥"])
def test_empty_or_ambiguous_section_ids_are_rejected(value: object) -> None:
    with pytest.raises(OutlineNormalizationError):
        normalize_outline_section_ids(_outline(value))


@pytest.mark.parametrize("values", [("1", "001"), ("SEC-AUTH", "sec auth"), ("1", "1")])
def test_normalized_collisions_and_duplicates_are_rejected(values: tuple[str, str]) -> None:
    with pytest.raises(OutlineNormalizationError, match="SECTION_ID_COLLISION"):
        normalize_outline_section_ids(_outline(*values))


def test_prompt_contract_contains_exact_schema_pattern() -> None:
    prompt = (ROOT / "prompts/prd-analysis/v2/outline_system.md").read_text(encoding="utf-8")
    assert "^SEC-[A-Za-z0-9_-]{1,64}$" in prompt


def test_ambiguous_initial_outline_uses_one_bounded_correction(tmp_path: Path) -> None:
    database = PluginDatabase(f"sqlite:///{(tmp_path / 'plugin.db').as_posix()}")
    database.migrate()
    project = database.create_project("Correction")
    prd_text = normalize_prd("# Auth\nA user can logout.\n")
    version = database.import_prd(
        str(project["project_id"]), "Auth", prd_text, content_hash(prd_text), "text/markdown"
    )
    provider = MockLLMProvider(
        [
            _response(_outline("auth/login")),
            _response(_outline("SEC-AUTH")),
        ]
    )
    run = AnalysisService(database, max_retries=1).start(
        str(version["version_id"]), provider, "outline-correction"
    )
    assert run["status"] in {"succeeded", "failed"}
    calls = database.fetch_all(
        "SELECT call_type,validation_status FROM llm_call_logs "
        "WHERE call_type LIKE 'outline%' ORDER BY retry_count"
    )
    assert calls[:2] == [
        {"call_type": "outline", "validation_status": "invalid"},
        {"call_type": "outline_correction", "validation_status": "valid"},
    ]
    artifacts = database.fetch_all(
        "SELECT a.response_content,a.parsed_json FROM llm_response_artifacts a "
        "JOIN llm_call_logs c ON c.llm_call_id=a.llm_call_id "
        "WHERE c.call_type LIKE 'outline%' ORDER BY c.retry_count"
    )
    assert '"auth/login"' in artifacts[0]["response_content"]
    assert '"SEC-AUTH"' in artifacts[1]["parsed_json"]


def test_batch_planning_remains_available_after_offline_normalization() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    accepted, _ = normalize_outline_section_ids(raw)
    RequirementSchemas().validate("prd_outline.schema.json", accepted)
    prd = normalize_prd((ROOT / "docs/prd/login_register_prd.md").read_text(encoding="utf-8"))
    batches = plan_batches(prd, 1800)
    assert len(batches) == 2


def test_existing_0013_database_upgrades_to_immutable_outline_audit(tmp_path: Path) -> None:
    database_path = tmp_path / "upgrade-from-0013.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, "
            "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        for migration in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if migration.name.startswith("0014_"):
                continue
            connection.executescript(migration.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)", (migration.stem,)
            )
    database = PluginDatabase(f"sqlite:///{database_path.as_posix()}")
    database.migrate()
    assert database.fetch_one("SELECT COUNT(*) AS count FROM schema_migrations") == {"count": 14}
    assert database.fetch_one(
        "SELECT COUNT(*) AS count FROM sqlite_master "
        "WHERE type='table' AND name='analysis_outline_normalization_audits'"
    ) == {"count": 1}
    assert database.fetch_one("PRAGMA integrity_check") == {"integrity_check": "ok"}
    assert database.fetch_all("PRAGMA foreign_key_check") == []
