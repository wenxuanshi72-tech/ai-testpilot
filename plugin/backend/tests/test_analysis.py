from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import ValidationError
from sqlalchemy import event

from plugin.backend.app.analysis import (
    AnalysisService,
    AnalysisValidationError,
    BatchSpec,
    TruncationError,
    content_hash,
    normalize_prd,
    parse_json_object,
    plan_batches,
)
from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.offline_revalidation import OfflineRevalidationService
from plugin.backend.app.providers import (
    MockLLMProvider,
    ProviderMetadata,
    ProviderResponse,
)
from plugin.backend.app.schema_validation import RequirementSchemas
from plugin.backend.app.source_blocks import build_source_blocks


def _response(
    value: object | str,
    *,
    finish_reason: str = "stop",
    output_tokens: int = 10,
    max_tokens: int = 100,
) -> ProviderResponse:
    content = value if isinstance(value, str) else json.dumps(value)
    return ProviderResponse(
        content=content,
        finish_reason=finish_reason,
        input_tokens=10,
        output_tokens=output_tokens,
        latency_ms=2,
        http_status=200,
        provider_request_id="fixture",
        max_tokens=max_tokens,
    )


class OfflineRealFixtureProvider(MockLLMProvider):
    @property
    def metadata(self) -> ProviderMetadata:
        return ProviderMetadata("deepseek", "deepseek-v4-pro", "real")


def _outline() -> dict[str, object]:
    return {
        "document_summary": "Authentication requirements.",
        "sections": [{"section_id": "SEC-AUTH", "title": "Auth", "source_heading": "# Auth"}],
        "outline_complete": True,
    }


def _requirement(
    requirement_id: str,
    title: str,
    excerpt: str,
    tag: str,
    business_rules: list[str] | None = None,
) -> dict[str, Any]:
    normalized = normalize_prd(_short_prd())
    block = next(
        item for item in build_source_blocks(normalized, normalized.strip()) if excerpt in item.text
    )
    return {
        "requirement_id": requirement_id,
        "title": title,
        "description": f"The system shall provide the documented {title.lower()} behavior.",
        "requirement_type": "business_rule" if business_rules else "functional",
        "source_section": "# Auth",
        "source_block_id": block.block_id,
        "source_excerpt": excerpt,
        "acceptance_criteria": [f"The {title.lower()} behavior is observable."],
        "business_rules": business_rules or [],
        "actors": ["user"],
        "priority": "must",
        "risk_level": "medium",
        "ambiguities": [],
        "dependencies": [],
        "testability": "testable",
        "confidence": 1.0,
        "tags": ["authentication", tag],
    }


def _short_prd() -> str:
    return (
        "# Auth\n"
        "Usernames must contain at least 6 characters.\n"
        "A visitor can register an account.\n"
        "A returning user can login.\n"
        "An authenticated user can access the current-user endpoint.\n"
        "A user can logout.\n"
    )


def _batch() -> dict[str, object]:
    return {
        "batch_id": "BAT-001",
        "source_sections": ["# Auth"],
        "requirements": [
            _requirement(
                "REQ-AUTH-USERNAME-001",
                "Username minimum",
                "Usernames must contain at least 6 characters.",
                "username",
                ["A username must contain at least 6 characters."],
            ),
            _requirement(
                "REQ-AUTH-REGISTER-001",
                "Register account",
                "A visitor can register an account.",
                "register",
            ),
            _requirement(
                "REQ-AUTH-LOGIN-001",
                "Login",
                "A returning user can login.",
                "login",
            ),
            _requirement(
                "REQ-AUTH-ME-001",
                "Current-user lookup",
                "An authenticated user can access the current-user endpoint.",
                "current-user",
            ),
            _requirement(
                "REQ-AUTH-LOGOUT-001",
                "Logout",
                "A user can logout.",
                "logout",
            ),
        ],
        "unsupported": [],
        "reported_count": 5,
        "batch_complete": True,
    }


def _database(tmp_path: Path) -> PluginDatabase:
    database = PluginDatabase(f"sqlite:///{(tmp_path / 'plugin.db').as_posix()}")
    database.migrate()
    return database


def _import(database: PluginDatabase) -> str:
    project = database.create_project("Auth")
    content = normalize_prd(_short_prd())
    version = database.import_prd(
        str(project["project_id"]),
        "Auth",
        content,
        content_hash(content),
        "text/markdown",
    )
    return str(version["version_id"])


def _import_content(database: PluginDatabase, content: str) -> str:
    project = database.create_project("Two batches")
    normalized = normalize_prd(content)
    version = database.import_prd(
        str(project["project_id"]),
        "Two batches",
        normalized,
        content_hash(normalized),
        "text/markdown",
    )
    return str(version["version_id"])


def _two_batch_prd() -> str:
    return (
        "# Auth\n"
        "Usernames must contain at least 6 characters.\n"
        "A visitor can register an account.\n"
        "A returning user can login.\n"
        "An authenticated user can access the current-user endpoint.\n"
        "A user can logout.\n\n"
        "# Security\n"
        "Passwords are never stored in plaintext.\n"
        "Tokens are stored only as hashes.\n"
        "The formal product requirement remains a minimum username length of six.\n"
    )


def _security_batch() -> dict[str, object]:
    normalized = normalize_prd(_two_batch_prd())
    spec = plan_batches(normalized, 200)[1]
    block = next(
        item
        for item in build_source_blocks(normalized, spec.source_text)
        if "Passwords are never stored" in item.text
    )
    requirement = _requirement(
        "REQ-SEC-PASSWORD-001",
        "Password storage",
        "A user can logout.",
        "security",
    )
    requirement["requirement_type"] = "security"
    requirement["source_section"] = "# Security"
    requirement["source_block_id"] = block.block_id
    requirement["source_excerpt"] = "Passwords are never stored in plaintext."
    constraint = _requirement(
        "REQ-SEC-USERNAME-001",
        "Username minimum",
        "A user can logout.",
        "username",
    )
    constraint["requirement_type"] = "business_rule"
    constraint["source_section"] = "# Security"
    constraint["source_block_id"] = block.block_id
    constraint["source_excerpt"] = (
        "The formal product requirement remains a minimum username length of six."
    )
    constraint["business_rules"] = ["A username has a minimum length of six characters."]
    return {
        "batch_id": "BAT-002",
        "source_sections": ["# Security"],
        "requirements": [requirement, constraint],
        "unsupported": [],
        "reported_count": 2,
        "batch_complete": True,
    }


def _seed_failed_real_child(
    database: PluginDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[str, str]:
    version_id = _import_content(database, _two_batch_prd())
    invalid_second = _security_batch()
    invalid_second["unexpected"] = True
    first_provider = OfflineRealFixtureProvider(
        [_response(_outline()), _response(_batch()), _response(invalid_second)]
    )
    service = AnalysisService(database, batch_max_chars=200, max_retries=0)
    parent = service.start(version_id, first_provider, "offline-parent-fixture")
    assert parent["status"] == "failed"

    def legacy_false_negative(_aggregate: dict[str, Any]) -> list[object]:
        raise AnalysisValidationError("USERNAME_MINIMUM_SIX_MISSING")

    monkeypatch.setattr(service, "_validate_aggregate_domain", legacy_false_negative)
    child = service.start_recovery(
        str(parent["analysis_run_id"]),
        OfflineRealFixtureProvider([_response(_security_batch())]),
        "offline-child-fixture",
    )
    assert child["status"] == "failed"
    return str(parent["analysis_run_id"]), str(child["analysis_run_id"])


def test_normalization_hash_and_deterministic_batches() -> None:
    normalized = normalize_prd("# A\r\nline  \r\n\r\n\r\n# B\nvalue")
    assert normalized == "# A\nline\n\n# B\nvalue\n"
    assert content_hash(normalized) == content_hash(normalized)
    batches = plan_batches(normalized * 20, 200)
    assert len(batches) > 1
    assert [batch.index for batch in batches] == list(range(1, len(batches) + 1))
    assert all(len(batch.source_text) <= 200 for batch in batches)
    with pytest.raises(ValueError):
        plan_batches(normalized, 199)
    with pytest.raises(AnalysisValidationError):
        normalize_prd(" \r\n ")


def test_json_parser_allows_only_small_envelope_cleanup() -> None:
    assert parse_json_object(_response('prefix {"ok": true} suffix')) == {"ok": True}
    fenced = f'{chr(96) * 3}json\n{{"ok": true}}\n{chr(96) * 3}'
    assert parse_json_object(_response(fenced)) == {"ok": True}


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (_response(""), "EMPTY_CONTENT"),
        (_response("{}", finish_reason="length"), "ABNORMAL_FINISH_REASON"),
        (_response("{}", output_tokens=98), "OUTPUT_TOKEN_LIMIT_RISK"),
        (_response('{"open":'), "JSON_NOT_CLOSED"),
        (_response('{"bad":,}'), "MALFORMED_JSON"),
    ],
)
def test_json_parser_detects_truncation(response: ProviderResponse, message: str) -> None:
    with pytest.raises(TruncationError, match=message):
        parse_json_object(response)


def test_versioned_schemas_are_strict() -> None:
    schemas = RequirementSchemas()
    schemas.validate("prd_outline.schema.json", _outline())
    schemas.validate("requirement_batch.schema.json", _batch())
    invalid = _batch()
    invalid["unexpected"] = True
    with pytest.raises(ValidationError):
        schemas.validate("requirement_batch.schema.json", invalid)


def test_failed_batch_retries_without_repeating_valid_work(tmp_path: Path) -> None:
    database = _database(tmp_path)
    version_id = _import(database)
    provider = MockLLMProvider(
        [
            _response(_outline()),
            _response('{"incomplete":'),
            _response(_batch()),
        ]
    )
    service = AnalysisService(
        database, batch_max_chars=1000, batch_max_requirements=12, max_retries=1
    )
    run = service.start(version_id, provider, "retry-once")
    assert run["status"] == "succeeded"
    assert provider.call_count == 3
    batch = database.fetch_one("SELECT * FROM analysis_batches")
    assert batch is not None
    assert batch["retry_count"] == 1
    requirement_count = database.fetch_one("SELECT COUNT(*) AS count FROM requirements")
    assert requirement_count is not None
    assert requirement_count["count"] == 5

    same = service.start(version_id, provider, "retry-once")
    assert same["analysis_run_id"] == run["analysis_run_id"]
    assert provider.call_count == 3


def test_validation_failure_never_promotes_partial_requirements(tmp_path: Path) -> None:
    database = _database(tmp_path)
    version_id = _import(database)
    invalid = _batch()
    invalid_requirements = invalid["requirements"]
    assert isinstance(invalid_requirements, list)
    invalid["requirements"] = invalid_requirements[1:]
    invalid["reported_count"] = 4
    provider = MockLLMProvider(
        [
            _response(_outline()),
            _response(invalid),
            _response(invalid),
        ]
    )
    service = AnalysisService(
        database, batch_max_chars=1000, batch_max_requirements=12, max_retries=1
    )
    run = service.start(version_id, provider, "invalid-aggregate")
    assert run["status"] == "failed"
    requirement_count = database.fetch_one("SELECT COUNT(*) AS count FROM requirements")
    assert requirement_count is not None
    assert requirement_count["count"] == 0


def test_failed_run_creates_linked_attempt_and_only_retries_failed_batch(tmp_path: Path) -> None:
    database = _database(tmp_path)
    version_id = _import(database)
    invalid = _batch()
    invalid["unexpected"] = True
    first_provider = MockLLMProvider(
        [
            _response(_outline()),
            _response(invalid),
        ]
    )
    service = AnalysisService(
        database, batch_max_chars=1000, batch_max_requirements=12, max_retries=0
    )
    failed = service.start(version_id, first_provider, "resume-run")
    assert failed["status"] == "failed"

    recovery_provider = MockLLMProvider(
        [
            _response(_batch()),
        ]
    )
    recovered = service.start_recovery(
        str(failed["analysis_run_id"]), recovery_provider, "recovery-attempt"
    )
    assert recovered["analysis_run_id"] != failed["analysis_run_id"]
    assert recovered["parent_analysis_run_id"] == failed["analysis_run_id"]
    assert recovered["status"] == "succeeded"
    assert recovery_provider.call_count == 1
    recovery_call = database.fetch_one(
        "SELECT call_type, prompt_version FROM llm_call_logs "
        "WHERE call_type='requirements_recovery'"
    )
    assert recovery_call == {
        "call_type": "requirements_recovery",
        "prompt_version": "prd-analysis-recovery@2.0.0",
    }

    original = database.fetch_one(
        "SELECT status, validation_status FROM analysis_runs WHERE analysis_run_id=:id",
        {"id": failed["analysis_run_id"]},
    )
    assert original == {"status": "failed", "validation_status": "invalid"}
    links = database.fetch_all(
        "SELECT artifact_type FROM analysis_reuse_links WHERE analysis_run_id=:id",
        {"id": recovered["analysis_run_id"]},
    )
    assert {row["artifact_type"] for row in links} == {"outline"}


def test_recovery_reuses_outline_and_first_batch_without_provider_calls(tmp_path: Path) -> None:
    database = _database(tmp_path)
    version_id = _import_content(database, _two_batch_prd())
    invalid_second = _security_batch()
    invalid_second["unexpected"] = True
    first_provider = MockLLMProvider(
        [_response(_outline()), _response(_batch()), _response(invalid_second)]
    )
    service = AnalysisService(database, batch_max_chars=200, max_retries=0)
    failed = service.start(version_id, first_provider, "two-batch-failure")
    assert failed["status"] == "failed"
    assert database.fetch_one("SELECT COUNT(*) AS count FROM requirements") == {"count": 0}

    recovery_provider = MockLLMProvider([_response(_security_batch())])
    recovered = service.start_recovery(
        str(failed["analysis_run_id"]), recovery_provider, "two-batch-recovery"
    )
    assert recovered["status"] == "succeeded"
    assert recovery_provider.call_count == 1
    links = database.fetch_all(
        "SELECT artifact_type FROM analysis_reuse_links WHERE analysis_run_id=:run",
        {"run": recovered["analysis_run_id"]},
    )
    assert {row["artifact_type"] for row in links} == {"outline", "validated_batch"}
    calls = database.fetch_all(
        "SELECT call_type FROM llm_call_logs WHERE analysis_run_id=:run",
        {"run": recovered["analysis_run_id"]},
    )
    assert calls == [{"call_type": "requirements_recovery"}]
    assert database.fetch_one(
        "SELECT COUNT(*) AS count FROM requirements WHERE analysis_run_id=:run",
        {"run": recovered["analysis_run_id"]},
    ) == {"count": 7}


def test_terminal_failure_is_immutable_and_provider_modes_cannot_cross(
    tmp_path: Path,
) -> None:
    database = _database(tmp_path)
    version_id = _import(database)
    invalid = _batch()
    invalid["unexpected"] = True
    service = AnalysisService(database, batch_max_chars=1000, max_retries=0)
    failed = service.start(
        version_id,
        MockLLMProvider([_response(_outline()), _response(invalid)]),
        "immutable-failure",
    )
    before = database.fetch_one(
        "SELECT * FROM analysis_runs WHERE analysis_run_id=:run",
        {"run": failed["analysis_run_id"]},
    )
    unused = MockLLMProvider([_response(_outline()), _response(_batch())])
    same = service.start(version_id, unused, "immutable-failure")
    after = database.fetch_one(
        "SELECT * FROM analysis_runs WHERE analysis_run_id=:run",
        {"run": failed["analysis_run_id"]},
    )
    assert same == before == after
    assert unused.call_count == 0
    with pytest.raises(AnalysisValidationError, match="RECOVERY_PROVIDER_MISMATCH"):
        service.start_recovery(
            str(failed["analysis_run_id"]),
            MockLLMProvider(model="different-mock"),
            "wrong-provider",
        )


def test_api_key_is_redacted_from_response_and_parsed_audit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "local-secret-value-that-must-not-persist"
    monkeypatch.setenv("DEEPSEEK_API_KEY", secret)
    database = _database(tmp_path)
    version_id = _import(database)
    outline = _outline()
    outline["document_summary"] = f"Authentication {secret}"
    service = AnalysisService(database, batch_max_chars=1000, max_retries=0)
    run = service.start(
        version_id,
        MockLLMProvider([_response(outline), _response(_batch())]),
        "redacted-response",
    )
    assert run["status"] == "succeeded"
    artifacts = database.fetch_all(
        "SELECT response_content, parsed_json, redaction_applied FROM llm_response_artifacts"
    )
    assert any(row["redaction_applied"] == 1 for row in artifacts)
    assert all(secret not in str(row) for row in artifacts)


def test_offline_revalidation_is_zero_llm_idempotent_and_preserves_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _database(tmp_path)
    parent_id, child_id = _seed_failed_real_child(database, monkeypatch)
    calls_before = database.fetch_one(
        "SELECT COUNT(*) AS count FROM llm_call_logs WHERE analysis_run_id=:run",
        {"run": child_id},
    )
    service = OfflineRevalidationService(database)
    result = service.run(child_id, "offline-revalidation-success")
    assert result.status == "succeeded"
    assert result.llm_call_count == 0
    assert result.formal_requirement_count == 7
    assert result.candidate_count == 7

    repeated = service.run(child_id, "offline-revalidation-success")
    assert repeated == result
    assert database.fetch_one("SELECT COUNT(*) AS count FROM offline_revalidation_attempts") == {
        "count": 1
    }
    assert database.fetch_one(
        "SELECT COUNT(*) AS count FROM requirements WHERE offline_revalidation_attempt_id=:attempt",
        {"attempt": result.attempt_id},
    ) == {"count": 7}
    assert database.fetch_one(
        "SELECT status FROM analysis_runs WHERE analysis_run_id=:run", {"run": parent_id}
    ) == {"status": "failed"}
    assert database.fetch_one(
        "SELECT status, error_type FROM analysis_runs WHERE analysis_run_id=:run",
        {"run": child_id},
    ) == {"status": "failed", "error_type": "USERNAME_MINIMUM_SIX_MISSING"}
    assert (
        database.fetch_one(
            "SELECT COUNT(*) AS count FROM llm_call_logs WHERE analysis_run_id=:run",
            {"run": child_id},
        )
        == calls_before
    )
    attempt = database.fetch_one(
        "SELECT provider_status,llm_call_count,old_validator_version,new_validator_version "
        "FROM offline_revalidation_attempts WHERE offline_revalidation_attempt_id=:attempt",
        {"attempt": result.attempt_id},
    )
    assert attempt == {
        "provider_status": "offline_revalidation_of_real_result",
        "llm_call_count": 0,
        "old_validator_version": "aggregate-domain-validator@2.0.0",
        "new_validator_version": "aggregate-domain-validator@2.0.1",
    }
    assert database.fetch_one(
        "SELECT COUNT(*) AS count FROM offline_revalidation_candidate_links "
        "WHERE offline_revalidation_attempt_id=:attempt",
        {"attempt": result.attempt_id},
    ) == {"count": 7}
    assert database.fetch_one(
        "SELECT COUNT(*) AS count FROM aggregate_constraint_audits "
        "WHERE offline_revalidation_attempt_id=:attempt",
        {"attempt": result.attempt_id},
    ) == {"count": 2}


def test_offline_revalidation_promotion_failure_is_atomic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _database(tmp_path)
    _parent_id, child_id = _seed_failed_real_child(database, monkeypatch)
    inserts = 0

    def fail_on_second_requirement(
        _conn: object,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        nonlocal inserts
        if statement.lstrip().upper().startswith("INSERT INTO REQUIREMENTS("):
            inserts += 1
            if inserts == 2:
                raise RuntimeError("synthetic atomic rollback")

    event.listen(database.engine, "before_cursor_execute", fail_on_second_requirement)
    try:
        result = OfflineRevalidationService(database).run(child_id, "offline-revalidation-rollback")
    finally:
        event.remove(database.engine, "before_cursor_execute", fail_on_second_requirement)
    assert result.status == "failed"
    assert result.formal_requirement_count == 0
    assert result.llm_call_count == 0
    assert database.fetch_one("SELECT COUNT(*) AS count FROM requirements") == {"count": 0}
    assert database.fetch_one("SELECT COUNT(*) AS count FROM aggregate_constraint_audits") == {
        "count": 0
    }
    repeated = OfflineRevalidationService(database).run(child_id, "offline-revalidation-rollback")
    assert repeated == result


def test_truncated_large_batch_is_split_into_smaller_units(tmp_path: Path) -> None:
    service = AnalysisService(_database(tmp_path))
    source = ("first section line\n" * 50) + ("second section line\n" * 50)
    original = BatchSpec("BAT-001", 1, ["# Auth"], source)
    replacements = service._split_failed_batch(original, 2)
    assert [item.batch_id for item in replacements] == ["BAT-002", "BAT-003"]
    assert all(len(item.source_text) < len(source) for item in replacements)
    assert "".join(item.source_text for item in replacements).replace("\n", "") == source.replace(
        "\n", ""
    )


def test_call_budget_blocks_before_an_extra_provider_call(tmp_path: Path) -> None:
    database = _database(tmp_path)
    version_id = _import(database)
    provider = MockLLMProvider([_response(_outline()), _response(_batch())])
    service = AnalysisService(
        database,
        batch_max_chars=1000,
        max_retries=0,
        call_max_output_tokens=4096,
        run_max_output_tokens=2048,
    )
    run = service.start(version_id, provider, "budget-stop")
    assert run["status"] == "failed"
    assert run["error_type"] == "COST_BUDGET_EXCEEDED"
    assert provider.call_count == 1
    assert database.fetch_one("SELECT COUNT(*) AS count FROM requirements") == {"count": 0}
