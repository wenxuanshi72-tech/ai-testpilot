from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest
from flask.testing import FlaskClient
from jsonschema import ValidationError
from sqlalchemy.exc import IntegrityError

from plugin.backend.app.database import PluginDatabase
from plugin.backend.app.prompts import PromptRegistry
from plugin.backend.app.providers import (
    DeepSeekProvider,
    MockLLMProvider,
    ProviderCallError,
    ProviderConfigurationError,
    ProviderResponse,
)
from plugin.backend.app.test_generation import (
    RunCallCounters,
    is_structure_correction_eligible,
)
from plugin.backend.app.test_generation import (
    TestGenerationError as GenerationError,
)
from plugin.backend.app.test_generation import (
    TestGenerationService as GenerationService,
)
from plugin.backend.app.test_generation_planning import capacity_report_for_plan
from plugin.backend.app.test_generation_prompts import (
    TEST_GENERATION_PROMPT_VERSION,
)
from plugin.backend.app.test_generation_prompts import (
    TestGenerationPromptRegistry as GenerationPromptRegistry,
)
from plugin.backend.app.test_generation_schemas import (
    TEST_CASE_SCHEMA_VERSION,
)
from plugin.backend.app.test_generation_schemas import (
    TestCaseSchemas as CaseSchemas,
)
from plugin.backend.app.test_review import (
    TestReviewError as ReviewError,
)
from plugin.backend.app.test_review import (
    TestReviewService as ReviewService,
)

PROJECT_ID = "PRJ-11111111111111111111111111111111"
PRD_DOCUMENT_ID = "PRD-22222222222222222222222222222222"
PRD_VERSION_ID = "PRDV-33333333333333333333333333333333"
ANALYSIS_RUN_ID = "ANR-44444444444444444444444444444444"
SEEDED_REQUIREMENT_ID = "REQ-BAT-002-6"


def _seed_formal_requirements(database: PluginDatabase) -> None:
    content = "# Authentication\n\nFormal authentication requirements."
    content_hash = hashlib.sha256(content.encode()).hexdigest()
    database.execute(
        "INSERT INTO projects(project_id,name,status) VALUES (:id,'Authentication','active')",
        {"id": PROJECT_ID},
    )
    database.execute(
        "INSERT INTO prd_documents(prd_document_id,project_id,title) "
        "VALUES (:id,:project,'Authentication PRD')",
        {"id": PRD_DOCUMENT_ID, "project": PROJECT_ID},
    )
    database.execute(
        "INSERT INTO prd_versions(version_id,prd_document_id,version_number,content,"
        "content_hash,media_type) VALUES (:id,:document,1,:content,:hash,'text/markdown')",
        {
            "id": PRD_VERSION_ID,
            "document": PRD_DOCUMENT_ID,
            "content": content,
            "hash": content_hash,
        },
    )
    database.execute(
        "INSERT INTO analysis_runs(analysis_run_id,project_id,prd_version_id,provider,model,"
        "provider_mode,prompt_version,schema_version,status,input_hash,idempotency_key,"
        "validation_status) VALUES (:id,:project,:prd,'deepseek','deepseek-v4-pro','real',"
        "'prd-analysis-recovery@2.0.0','requirements@2.0.0','succeeded',:hash,'formal-run',"
        "'valid')",
        {
            "id": ANALYSIS_RUN_ID,
            "project": PROJECT_ID,
            "prd": PRD_VERSION_ID,
            "hash": content_hash,
        },
    )
    definitions = [
        (
            SEEDED_REQUIREMENT_ID,
            "Username minimum length",
            "Registration username must have a minimum of six characters.",
            "functional",
            ["registration", "username", "seeded-defect"],
        ),
        (
            "REQ-AUTH-LOGIN-001",
            "Login credentials",
            "Login accepts valid username and password credentials.",
            "functional",
            ["login", "positive"],
        ),
        (
            "REQ-AUTH-LOGOUT-001",
            "Logout",
            "Logout invalidates the current session.",
            "functional",
            ["logout", "session"],
        ),
        (
            "REQ-AUTH-SESSION-001",
            "Current-user session",
            "The current-user endpoint reports authenticated session state.",
            "functional",
            ["current-user", "session"],
        ),
        (
            "REQ-AUTH-SECURITY-001",
            "Credential security",
            "Security controls prevent credential disclosure in responses and logging.",
            "security",
            ["security", "login"],
        ),
        (
            "REQ-AUTH-PRIVACY-001",
            "Cookie privacy",
            "Privacy controls restrict the authentication cookie.",
            "privacy",
            ["privacy", "cookie"],
        ),
        (
            "REQ-AUTH-QUALITY-001",
            "Authentication quality",
            "Quality controls provide understandable error handling.",
            "quality",
            ["quality", "error"],
        ),
    ]
    for index in range(8, 20):
        if index <= 15:
            title = f"Registration flow {index}"
            description = (
                f"Registration flow rule {index} is observable through the API and UI logging."
            )
            tags = ["registration", "positive", "logging"]
        elif index == 16:
            title = "Service logging"
            description = "Authentication logging behavior is observable through the API."
            tags = ["logging", "positive"]
        else:
            title = f"API rule {index}"
            description = f"Authentication API rule {index} is observable through its response."
            tags = ["api", "positive"]
        definitions.append(
            (
                f"REQ-AUTH-FLOW-{index:03d}",
                title,
                description,
                "functional",
                tags,
            )
        )
    for index, (requirement_id, title, description, requirement_type, tags) in enumerate(
        definitions, 1
    ):
        source_block_id = f"BLK-L{index:04d}-L{index:04d}-{index:010X}"
        payload = {
            "requirement_id": requirement_id,
            "title": title,
            "description": description,
            "requirement_type": requirement_type,
            "risk_level": "high" if index <= 7 else "medium",
            "tags": tags,
            "source_block_id": source_block_id,
            "source_excerpt": description,
            "priority": "high" if index <= 7 else "medium",
            "business_rules": [description],
            "acceptance_criteria": [f"The observable behavior satisfies: {description}"],
            "testability": "deterministic",
        }
        database.execute(
            "INSERT INTO requirements(row_id,requirement_id,project_id,prd_version_id,"
            "analysis_run_id,version_number,title,description,requirement_type,source_section,"
            "source_excerpt,payload_json,review_status) VALUES "
            "(:row,:requirement,:project,:prd,:run,1,:title,:description,:type,"
            "'Authentication',:excerpt,:payload,'approved')",
            {
                "row": f"REQROW-{index:032X}",
                "requirement": requirement_id,
                "project": PROJECT_ID,
                "prd": PRD_VERSION_ID,
                "run": ANALYSIS_RUN_ID,
                "title": title,
                "description": description,
                "type": requirement_type,
                "excerpt": description,
                "payload": database.encode_json(payload),
            },
        )


@pytest.fixture
def formal_database(database: PluginDatabase) -> PluginDatabase:
    _seed_formal_requirements(database)
    return database


def _count(database: PluginDatabase, table: str) -> int:
    allowed = {
        "test_generation_runs",
        "test_generation_batches",
        "test_generation_llm_calls",
        "test_case_candidates",
        "test_case_candidate_requirement_links",
        "test_case_coverage_results",
    }
    assert table in allowed
    row = database.fetch_one(f"SELECT COUNT(*) AS count FROM {table}")  # noqa: S608
    assert row is not None
    return int(row["count"])


class MutatingMockProvider(MockLLMProvider):
    def __init__(self, mutation: Callable[[dict[str, Any], int], None]) -> None:
        super().__init__()
        self.mutation = mutation

    def generate_test_cases(self, **kwargs: Any) -> ProviderResponse:
        response = super().generate_test_cases(**kwargs)
        payload = json.loads(response.content)
        self.mutation(payload, self.call_count)
        return ProviderResponse(
            content=json.dumps(payload),
            finish_reason=response.finish_reason,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=response.latency_ms,
            http_status=response.http_status,
            provider_request_id=response.provider_request_id,
            max_tokens=response.max_tokens,
        )


def _inject_unstructured_cleanup(payload: dict[str, Any], call_count: int) -> None:
    if call_count == 1:
        payload["intents"][0]["cleanup_intent"] = {
            "required": True,
            "instructions": ["Delete the created user and session records from the database."],
        }


def test_candidate_executability_failure_corrects_only_current_batch(
    formal_database: PluginDatabase,
) -> None:
    provider = MutatingMockProvider(_inject_unstructured_cleanup)
    result = GenerationService(formal_database, max_retries=1).start(
        PROJECT_ID, provider, "executability-correction"
    )
    assert result.status == "validated_pending_review"
    assert provider.call_count == 14
    first = formal_database.fetch_one(
        "SELECT status,retry_count FROM test_generation_batches "
        "WHERE test_generation_run_id=:run AND batch_key='TGB-API-001'",
        {"run": result.run_id},
    )
    assert first == {"status": "validated", "retry_count": 1}
    finding = formal_database.fetch_one(
        "SELECT details_json FROM test_case_generation_audit_events "
        "WHERE test_generation_run_id=:run "
        "AND event_type='candidate_executability_failed'",
        {"run": result.run_id},
    )
    assert finding
    details = json.loads(finding["details_json"])
    assert details["case_id"].startswith("TC-API-")
    assert details["findings"][0]["code"] == "EXECUTION_OPERATION_UNSTRUCTURED"
    assert details["findings"][0]["path"].endswith("/cleanup_requests/0")


def test_candidate_executability_failure_without_budget_stops_at_batch(
    formal_database: PluginDatabase,
) -> None:
    provider = MutatingMockProvider(_inject_unstructured_cleanup)
    result = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID, provider, "executability-no-correction"
    )
    assert result.status == "failed"
    assert provider.call_count == 1
    assert _count(formal_database, "test_case_candidates") == 0
    statuses = formal_database.fetch_all(
        "SELECT batch_key,status FROM test_generation_batches "
        "WHERE test_generation_run_id=:run ORDER BY batch_index",
        {"run": result.run_id},
    )
    assert statuses[0] == {"batch_key": "TGB-API-001", "status": "failed"}
    assert all(item["status"] == "pending" for item in statuses[1:])


class TruncatedMockProvider(MockLLMProvider):
    def generate_test_cases(self, **kwargs: Any) -> ProviderResponse:
        response = super().generate_test_cases(**kwargs)
        return ProviderResponse(
            content=response.content[:-1],
            finish_reason="length",
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=response.latency_ms,
            http_status=response.http_status,
            provider_request_id=response.provider_request_id,
            max_tokens=response.max_tokens,
        )


class OneTransientFailureProvider(MockLLMProvider):
    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    def generate_test_cases(self, **kwargs: Any) -> ProviderResponse:
        self.attempts += 1
        if self.attempts == 1:
            raise ProviderCallError("PROVIDER_TIMEOUT", retryable=True)
        return super().generate_test_cases(**kwargs)


class ScriptedNetworkFailureProvider(MockLLMProvider):
    def __init__(self, failures_by_batch: dict[str, int]) -> None:
        super().__init__()
        self.remaining = dict(failures_by_batch)
        self.attempts: dict[str, int] = {}

    def generate_test_cases(self, **kwargs: Any) -> ProviderResponse:
        batch = str(kwargs["batch_id"])
        self.attempts[batch] = self.attempts.get(batch, 0) + 1
        if self.remaining.get(batch, 0) > 0:
            self.remaining[batch] -= 1
            raise ProviderCallError("PROVIDER_NETWORK", retryable=True)
        return super().generate_test_cases(**kwargs)


def test_migration_has_phase5b_and_phase6_tables(database: PluginDatabase) -> None:
    tables = {
        str(row["name"])
        for row in database.fetch_all("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "test_generation_runs",
        "test_generation_batches",
        "test_generation_llm_calls",
        "test_generation_response_artifacts",
        "test_case_candidates",
        "test_case_candidate_requirement_links",
        "test_case_validation_results",
        "test_case_coverage_results",
        "test_case_generation_audit_events",
    } <= tables
    assert {
        "test_case_reviews",
        "approved_test_case_versions",
        "frozen_baselines",
        "frozen_baseline_members",
        "immutable_execution_snapshots",
        "test_case_review_audit_events",
    } <= tables
    migration = database.fetch_one("SELECT COUNT(*) AS count FROM schema_migrations")
    assert migration == {"count": 12}


def test_versioned_schemas_and_prompts_are_complete() -> None:
    schemas = CaseSchemas()
    prompts = GenerationPromptRegistry()
    assert TEST_CASE_SCHEMA_VERSION == "test-cases@1.8.0"
    assert TEST_GENERATION_PROMPT_VERSION == "test-generation@3.0.0"
    assert len(schemas.schemas) == 7
    assert len(prompts.required_files) == 9
    assert len(prompts.content_hash) == 64
    messages = prompts.generation_messages(
        case_type="api",
        batch_id="TGB-API-001",
        generation_run_id="TGR-11111111111111111111111111111111",
        provider_mode="mock",
        generation_slots=[],
        max_cases=1,
        recovery=False,
    )
    serialized = json.dumps(messages).lower()
    assert "json" in serialized
    assert "generation_slot_id" in serialized
    assert "requirement_ids" in serialized


def test_preflight_snapshots_exactly_19_requirements(
    formal_database: PluginDatabase,
) -> None:
    plan = GenerationService(formal_database).preflight(PROJECT_ID)
    service = GenerationService(formal_database)
    snapshots = service._load_requirement_snapshots(PROJECT_ID)
    capacities = capacity_report_for_plan(plan, snapshots, service.prompts)
    assert plan["requirement_count"] == 19
    assert len(plan["requirements"]) == 19
    assert len(plan["requirement_snapshot_hash"]) == 64
    assert plan["estimated_call_count"] == 13
    assert [batch["case_type"] for batch in plan["batches"]] == [
        *(["api"] * 6),
        *(["ui"] * 4),
        *(["manual"] * 3),
    ]
    assert all(batch["max_tokens"] == 3072 for batch in plan["batches"])
    assert all(len(batch["requirement_ids"]) <= 4 for batch in plan["batches"])
    assert all(
        capacity["input_estimate"]["budget_tokens"] <= capacity["input_budget_tokens"]
        for capacity in capacities
    )
    assert all(capacity["output_estimate"]["budget_tokens"] <= 2304 for capacity in capacities)


def test_mock_generation_atomically_saves_complete_pending_review_collection(
    formal_database: PluginDatabase,
) -> None:
    provider = MockLLMProvider()
    service = GenerationService(formal_database)
    result = service.start(PROJECT_ID, provider, "mock-complete")
    assert result.status == "validated_pending_review"
    assert result.provider_mode == "mock"
    assert result.candidate_count == 46
    assert result.collection_version == 1
    assert result.collection_hash is not None and len(result.collection_hash) == 64
    assert provider.call_count == 13
    assert _count(formal_database, "test_generation_batches") == 13
    assert _count(formal_database, "test_generation_llm_calls") == 13
    assert _count(formal_database, "test_case_candidates") == 46
    assert _count(formal_database, "test_case_candidate_requirement_links") == 46
    assert _count(formal_database, "test_case_coverage_results") == 19
    states = formal_database.fetch_all("SELECT DISTINCT lifecycle_status FROM test_case_candidates")
    assert states == [{"lifecycle_status": "validated_pending_review"}]
    payloads = [
        json.loads(str(row["payload_json"]))
        for row in formal_database.fetch_all("SELECT payload_json FROM test_case_candidates")
    ]
    assert {case["case_type"] for case in payloads} == {"api", "ui", "manual"}
    assert {case["review_status"] for case in payloads} == {"draft"}
    assert {case["source"] for case in payloads} == {"ai_mock"}


def test_seeded_defect_api_and_ui_guards_are_preserved(
    formal_database: PluginDatabase,
) -> None:
    result = GenerationService(formal_database).start(
        PROJECT_ID, MockLLMProvider(), "seeded-defect"
    )
    rows = formal_database.fetch_all(
        "SELECT case_id,payload_json FROM test_case_candidates "
        "WHERE case_id IN ('TC-API-AUTH-REG-005','TC-UI-AUTH-REG-005') ORDER BY case_id"
    )
    assert result.status == "validated_pending_review"
    assert [row["case_id"] for row in rows] == [
        "TC-API-AUTH-REG-005",
        "TC-UI-AUTH-REG-005",
    ]
    api = json.loads(str(rows[0]["payload_json"]))
    ui = json.loads(str(rows[1]["payload_json"]))
    assert api["requirement_ids"] == [SEEDED_REQUIREMENT_ID]
    assert ui["requirement_ids"] == [SEEDED_REQUIREMENT_ID]
    assert api["type_details"]["method"] == "POST"
    assert api["type_details"]["path"] == "/api/auth/register"
    assert api["type_details"]["expected_status"] == 400
    assert api["type_details"]["request"]["body"]["username"] == "z1234"
    assert "z1234" in json.dumps(api)
    assert "Test1234" in json.dumps(api)
    assert "z1234" in json.dumps(ui)

    snapshots = GenerationService(formal_database)._load_requirement_snapshots(PROJECT_ID)
    bad_cases = [deepcopy(api), deepcopy(ui)]
    bad_api = next(case for case in bad_cases if case["case_id"] == "TC-API-AUTH-REG-005")
    bad_api["type_details"]["expected_status"] = 201
    with pytest.raises(GenerationError, match="BUG_AUTH_001_ORACLE_INVALID"):
        GenerationService(formal_database)._validate_seeded_defect(bad_cases, snapshots)

    actual_status = 201
    execution_result = "PASS" if actual_status == api["type_details"]["expected_status"] else "FAIL"
    linked_bug_id = "BUG-AUTH-001" if execution_result == "FAIL" else None
    assert execution_result == "FAIL"
    assert linked_bug_id == "BUG-AUTH-001"


def test_phase6_contract_is_read_only_and_not_reviewed(
    formal_database: PluginDatabase,
) -> None:
    service = GenerationService(formal_database)
    with pytest.raises(GenerationError, match="GENERATION_RUN_NOT_FOUND"):
        service.phase6_candidate_collection("TGR-MISSING")
    result = service.start(PROJECT_ID, MockLLMProvider(), "phase6-input")
    before = _count(formal_database, "test_case_candidates")
    collection = service.phase6_candidate_collection(result.run_id)
    assert collection["status"] == "validated_pending_review"
    assert collection["review_disposition"] == "not_reviewed_phase6_required"
    assert collection["candidate_count"] == len(collection["cases"]) == 46
    assert _count(formal_database, "test_case_candidates") == before


def test_phase6_review_rejects_stale_hash_and_freeze_requires_all_approved(
    formal_database: PluginDatabase,
) -> None:
    generation = GenerationService(formal_database).start(
        PROJECT_ID, MockLLMProvider(), "phase6-review-guards"
    )
    review = ReviewService(formal_database)
    collection = review.collection(generation.run_id)
    first = collection["candidates"][0]
    with pytest.raises(ReviewError, match="CANDIDATE_HASH_CHANGED"):
        review.review(
            generation.run_id,
            first["case_id"],
            reviewer_id="portfolio-owner",
            decision="approve",
            automation_disposition="automated",
            disposition_reason="Selected for the MVP baseline.",
            comment="Reviewed against the formal requirement.",
            expected_content_hash="0" * 64,
        )
    review.review(
        generation.run_id,
        first["case_id"],
        reviewer_id="portfolio-owner",
        decision="request_changes",
        automation_disposition="deferred",
        disposition_reason="Requires revision before MVP automation.",
        comment="Clarify this candidate before approval.",
        expected_content_hash=first["content_hash"],
    )
    with pytest.raises(ReviewError, match="COLLECTION_NOT_FULLY_CLASSIFIED"):
        review.freeze(
            generation.run_id,
            frozen_by="portfolio-owner",
            environment_id="local-test",
            executor_contract_version="test-executor@1.0.0",
        )


def test_phase6_approves_complete_collection_and_atomically_freezes_snapshots(
    formal_database: PluginDatabase,
) -> None:
    generation = GenerationService(formal_database).start(
        PROJECT_ID, MockLLMProvider(), "phase6-freeze"
    )
    service = ReviewService(formal_database)
    collection = service.collection(generation.run_id)
    classification_plan = service.mvp_classification_plan(generation.run_id)
    assert classification_plan["counts"] == {"automated": 10, "manual": 12, "deferred": 24}
    versioned_case_id = "TC-API-AUTH-REG-005"
    versioned_approval_ids: list[str] = []
    for item in collection["candidates"]:
        plan_item = next(
            row for row in classification_plan["candidates"] if row["case_id"] == item["case_id"]
        )
        if item["case_id"] == versioned_case_id:
            original_approval = service.review(
                generation.run_id,
                item["case_id"],
                reviewer_id="portfolio-owner",
                decision="approve",
                automation_disposition="automated",
                disposition_reason="Initial immutable MVP approval.",
                comment="This v1 approval remains historical evidence.",
                expected_content_hash=item["content_hash"],
            )
            versioned_approval_ids.append(original_approval["approved_test_case_version_id"])
            service.review(
                generation.run_id,
                item["case_id"],
                reviewer_id="portfolio-owner",
                decision="request_changes",
                automation_disposition="deferred",
                disposition_reason="A later executability review requires human revision.",
                comment="Preserve v1 and request an executable revision.",
                expected_content_hash=item["content_hash"],
            )
            revised = deepcopy(item["candidate"])
            revised["objective"] = (
                str(revised["objective"])
                + " Verify the requirement oracle, not defective behavior."
            )
            revision = service.create_human_revision(
                generation.run_id,
                item["case_id"],
                revised_by="portfolio-owner",
                revision_reason="Align the executable objective while preserving the original.",
                expected_content_hash=item["content_hash"],
                candidate=revised,
            )
            assert revision["executability_findings"] == []
            result = service.review(
                generation.run_id,
                item["case_id"],
                reviewer_id="portfolio-owner",
                decision="approve",
                automation_disposition="automated",
                disposition_reason="Latest executable human revision selected for MVP.",
                comment="Approve immutable v2 after deterministic validation.",
                expected_content_hash=revision["content_hash"],
                human_revision_id=revision["human_revision_id"],
            )
            versioned_approval_ids.append(result["approved_test_case_version_id"])
            with pytest.raises(ReviewError, match="APPROVED_CONTENT_ALREADY_EXISTS"):
                service.review(
                    generation.run_id,
                    item["case_id"],
                    reviewer_id="portfolio-owner",
                    decision="approve",
                    automation_disposition="automated",
                    disposition_reason="Duplicate approval must be rejected.",
                    comment="Duplicate immutable revision approval.",
                    expected_content_hash=revision["content_hash"],
                    human_revision_id=revision["human_revision_id"],
                )
            continue
        result = service.review(
            generation.run_id,
            item["case_id"],
            reviewer_id="portfolio-owner",
            decision="approve",
            automation_disposition=plan_item["proposed_disposition"],
            disposition_reason=plan_item["disposition_reason"],
            comment="Approved after deterministic contract and trace review.",
            expected_content_hash=item["content_hash"],
        )
        if plan_item["proposed_disposition"] == "automated":
            assert result["approved_test_case_version_id"]
            assert len(result["approved_content_hash"]) == 64
        else:
            assert result["approved_test_case_version_id"] is None
    frozen = service.freeze(
        generation.run_id,
        frozen_by="portfolio-owner",
        environment_id="local-test",
        executor_contract_version="test-executor@1.0.0",
    )
    assert frozen.status == "frozen"
    assert frozen.snapshot_count == 10
    assert len(frozen.baseline_hash) == 64
    baseline = service.baseline(frozen.baseline_id)
    assert baseline["collection_hash"] == generation.collection_hash
    assert len(baseline["snapshots"]) == 10
    versions = formal_database.fetch_all(
        "SELECT approved_test_case_version_id,case_version FROM approved_test_case_versions "
        "WHERE case_id=:case ORDER BY case_version",
        {"case": versioned_case_id},
    )
    assert [row["case_version"] for row in versions] == [1, 2]
    assert [row["approved_test_case_version_id"] for row in versions] == versioned_approval_ids
    selected = [
        item for item in baseline["snapshots"] if item["snapshot"]["case_id"] == versioned_case_id
    ]
    assert len(selected) == 1
    assert selected[0]["snapshot"]["case_version"] == 2
    assert {item["snapshot"]["case"]["review_status"] for item in baseline["snapshots"]} == {
        "approved"
    }
    assert all(item["snapshot"]["requirement_trace"] for item in baseline["snapshots"])
    again = service.freeze(
        generation.run_id,
        frozen_by="portfolio-owner",
        environment_id="local-test",
        executor_contract_version="test-executor@1.0.0",
    )
    assert again == frozen


def test_phase6_records_reject_without_approval_and_preserves_immutable_history(
    formal_database: PluginDatabase,
) -> None:
    generation = GenerationService(formal_database).start(
        PROJECT_ID, MockLLMProvider(), "phase6-reject"
    )
    service = ReviewService(formal_database)
    first = service.collection(generation.run_id)["candidates"][0]
    result = service.review(
        generation.run_id,
        first["case_id"],
        reviewer_id="portfolio-owner",
        decision="reject",
        automation_disposition="deferred",
        disposition_reason="Not selected for MVP automation.",
        comment="Rejected with an explicit review rationale.",
        expected_content_hash=first["content_hash"],
    )
    assert result["approved_test_case_version_id"] is None
    review_id = result["review_id"]
    with pytest.raises(IntegrityError, match="reviews are immutable"):
        formal_database.execute(
            "UPDATE test_case_reviews SET comment='changed' WHERE test_case_review_id=:id",
            {"id": review_id},
        )


def test_phase6_executability_blocks_approval_but_allows_later_request_changes(
    formal_database: PluginDatabase,
) -> None:
    generation = GenerationService(formal_database).start(
        PROJECT_ID, MockLLMProvider(), "phase6-executability"
    )
    service = ReviewService(formal_database)
    first = service.collection(generation.run_id)["candidates"][0]
    service.review(
        generation.run_id,
        first["case_id"],
        reviewer_id="portfolio-owner",
        decision="approve",
        automation_disposition="automated",
        disposition_reason="Selected for the MVP baseline.",
        comment="Initial review decision retained as audit history.",
        expected_content_hash=first["content_hash"],
    )
    changed = service.review(
        generation.run_id,
        first["case_id"],
        reviewer_id="portfolio-owner",
        decision="request_changes",
        automation_disposition="deferred",
        disposition_reason="Requires revision before automation.",
        comment="A later review can supersede approval without deleting it.",
        expected_content_hash=first["content_hash"],
    )
    assert changed["decision"] == "request_changes"
    reviews = formal_database.fetch_one(
        "SELECT COUNT(*) AS count FROM test_case_reviews WHERE test_case_candidate_id=:candidate",
        {"candidate": first["test_case_candidate_id"]},
    )
    assert reviews == {"count": 2}


def test_phase6_executability_report_covers_complete_collection(
    formal_database: PluginDatabase,
) -> None:
    generation = GenerationService(formal_database).start(
        PROJECT_ID, MockLLMProvider(), "phase6-executability-report"
    )
    report = ReviewService(formal_database).executability_report(generation.run_id)
    assert report["candidate_count"] == 46
    assert report["passed_count"] == 46
    assert report["failed_count"] == 0


def test_phase6_human_revision_preserves_original_and_gates_automation(
    formal_database: PluginDatabase,
) -> None:
    generation = GenerationService(formal_database).start(
        PROJECT_ID, MockLLMProvider(), "phase6-human-revision"
    )
    service = ReviewService(formal_database)
    item = next(
        row
        for row in service.collection(generation.run_id)["candidates"]
        if row["case_id"] == "TC-UI-AUTH-REG-005"
    )
    invalid = deepcopy(item["candidate"])
    invalid["type_details"]["route"] = "/logout"
    invalid_revision = service.create_human_revision(
        generation.run_id,
        item["case_id"],
        revised_by="portfolio-owner",
        revision_reason="Preserve the invalid route as reviewed revision evidence.",
        expected_content_hash=item["content_hash"],
        candidate=invalid,
    )
    assert invalid_revision["executability_findings"][0]["code"] == "UI_ROUTE_NOT_IN_CONTRACT"
    with pytest.raises(ReviewError, match="CANDIDATE_NOT_EXECUTABLE"):
        service.review(
            generation.run_id,
            item["case_id"],
            reviewer_id="portfolio-owner",
            decision="approve",
            automation_disposition="automated",
            disposition_reason="Attempted automated classification.",
            comment="This must be rejected by the executable gate.",
            expected_content_hash=invalid_revision["content_hash"],
            human_revision_id=invalid_revision["human_revision_id"],
        )
    revised = deepcopy(item["candidate"])
    revised["type_details"].update(
        {
            "route": "/profile",
            "locator_intents": [{"strategy": "role", "value": "Logout"}],
            "user_actions": ["click:role:Logout"],
        }
    )
    valid_revision = service.create_human_revision(
        generation.run_id,
        item["case_id"],
        revised_by="portfolio-owner",
        revision_reason="Use the implemented profile route and accessible Logout control.",
        expected_content_hash=item["content_hash"],
        candidate=revised,
    )
    assert valid_revision["executability_findings"] == []
    approved = service.review(
        generation.run_id,
        item["case_id"],
        reviewer_id="portfolio-owner",
        decision="approve",
        automation_disposition="automated",
        disposition_reason="Deterministic MVP UI protocol is now satisfied.",
        comment="Approved only after the human revision passed executability.",
        expected_content_hash=valid_revision["content_hash"],
        human_revision_id=valid_revision["human_revision_id"],
    )
    assert approved["approved_test_case_version_id"]
    original = service.collection(generation.run_id)["candidates"]
    assert (
        next(row for row in original if row["case_id"] == item["case_id"])["content_hash"]
        == item["content_hash"]
    )


def test_phase6_http_boundary_exposes_review_and_freeze_without_execution(
    formal_database: PluginDatabase, client: FlaskClient
) -> None:
    generation = GenerationService(formal_database).start(
        PROJECT_ID, MockLLMProvider(), "phase6-api"
    )
    response = client.get(f"/api/v1/test-generation-runs/{generation.run_id}/reviews")
    assert response.status_code == 200
    candidates = response.get_json()["data"]["candidates"]
    first = candidates[0]
    reviewed = client.post(
        f"/api/v1/test-generation-runs/{generation.run_id}/candidates/{first['case_id']}/reviews",
        json={
            "reviewer_id": "portfolio-owner",
            "decision": "approve",
            "automation_disposition": "automated",
            "disposition_reason": "Selected for the MVP baseline.",
            "comment": "Approved through the versioned review API.",
            "expected_content_hash": first["content_hash"],
        },
    )
    assert reviewed.status_code == 201
    blocked = client.post(
        f"/api/v1/test-generation-runs/{generation.run_id}/frozen-baselines",
        json={
            "frozen_by": "portfolio-owner",
            "environment_id": "local-test",
            "executor_contract_version": "test-executor@1.0.0",
        },
    )
    assert blocked.status_code == 409
    assert "COLLECTION_NOT_FULLY_CLASSIFIED" in blocked.get_json()["error"]["message"]


def test_idempotency_never_repeats_successful_batches(
    formal_database: PluginDatabase,
) -> None:
    service = GenerationService(formal_database)
    first_provider = MockLLMProvider()
    first = service.start(PROJECT_ID, first_provider, "same-key")
    second_provider = MockLLMProvider()
    second = service.start(PROJECT_ID, second_provider, "same-key")
    assert first == second
    assert first_provider.call_count == 13
    assert second_provider.call_count == 0
    assert _count(formal_database, "test_generation_runs") == 1
    assert _count(formal_database, "test_generation_llm_calls") == 13


def test_transient_network_failure_is_retried_once_without_mock_fallback(
    formal_database: PluginDatabase,
) -> None:
    provider = OneTransientFailureProvider()
    result = GenerationService(formal_database, max_retries=1).start(
        PROJECT_ID, provider, "network-failure-one-retry"
    )
    assert result.status == "validated_pending_review"
    assert provider.attempts == 14
    assert provider.call_count == 13
    assert _count(formal_database, "test_generation_llm_calls") == 14


@pytest.mark.parametrize("failure_count", [1, 2, 3])
def test_batch_recovers_after_up_to_three_network_failures(
    formal_database: PluginDatabase,
    failure_count: int,
) -> None:
    waits: list[float] = []
    provider = ScriptedNetworkFailureProvider({"TGB-API-001": failure_count})
    service = GenerationService(
        formal_database,
        provider_retry_wait=waits.append,
        provider_retry_jitter=lambda: 0.5,
    )
    result = service.start(PROJECT_ID, provider, f"network-{failure_count}")
    assert result.status == "validated_pending_review"
    assert provider.attempts["TGB-API-001"] == failure_count + 1
    assert waits == [2.5, 4.5, 8.5][:failure_count]


def test_fourth_same_batch_network_failure_stops_without_infinite_retry(
    formal_database: PluginDatabase,
) -> None:
    waits: list[float] = []
    provider = ScriptedNetworkFailureProvider({"TGB-API-001": 4})
    result = GenerationService(
        formal_database,
        provider_retry_wait=waits.append,
        provider_retry_jitter=lambda: 0.0,
    ).start(PROJECT_ID, provider, "network-four-failures")
    assert result.status == "failed"
    assert provider.attempts["TGB-API-001"] == 4
    assert waits == [2.0, 4.0, 8.0]
    assert _count(formal_database, "test_case_candidates") == 0


def test_latest_real_network_pattern_recovers_and_continues_all_batches(
    formal_database: PluginDatabase,
) -> None:
    provider = ScriptedNetworkFailureProvider(
        {"TGB-API-001": 1, "TGB-API-003": 1, "TGB-API-006": 1, "TGB-UI-001": 1}
    )
    waits: list[float] = []
    result = GenerationService(
        formal_database,
        provider_retry_wait=waits.append,
        provider_retry_jitter=lambda: 0.0,
    ).start(PROJECT_ID, provider, "latest-network-pattern")
    assert result.status == "validated_pending_review"
    assert waits == [2.0, 2.0, 2.0, 2.0]
    assert provider.attempts["TGB-UI-001"] == 2
    assert provider.call_count == 13


def test_real_provider_without_key_is_blocked_without_mock_fallback(
    formal_database: PluginDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    provider = DeepSeekProvider(
        base_url="https://api.deepseek.com",
        model="deepseek-v4-pro",
        timeout_seconds=1,
        max_tokens=4096,
        prompts=PromptRegistry(),
    )
    result = GenerationService(formal_database).start(PROJECT_ID, provider, "real-no-key")
    assert result.status == "blocked"
    assert result.provider_mode == "real"
    assert result.candidate_count == 0
    assert _count(formal_database, "test_generation_llm_calls") == 0
    assert _count(formal_database, "test_case_candidates") == 0
    run = formal_database.fetch_one("SELECT provider,model,provider_mode FROM test_generation_runs")
    assert run == {
        "provider": "deepseek",
        "model": "deepseek-v4-pro",
        "provider_mode": "real",
    }


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        (
            lambda payload, _call: payload["intents"][0].update(
                {"requirement_ids": ["REQ-UNKNOWN-001"]}
            ),
            "INTENT_FIELD_BOUNDARY_INVALID",
        ),
        (
            lambda payload, _call: payload["intents"][0].update({"intent_id": "INT-UI-WRONG-TYPE"}),
            "INTENT_FIELD_BOUNDARY_INVALID",
        ),
        (
            lambda payload, _call: payload["intents"][0]["actions"][0].update({"instruction": ""}),
            "INTENT_SCHEMA_VALIDATION",
        ),
        (
            lambda payload, _call: payload["intents"][0].update(
                {"objective": "DEEPSEEK_API_KEY=synthetic-fixture"}
            ),
            "SENSITIVE_VALUE_DETECTED",
        ),
    ],
)
def test_invalid_model_candidates_fail_without_partial_promotion(
    formal_database: PluginDatabase,
    mutation: Callable[[dict[str, Any], int], None],
    expected_error: str,
) -> None:
    provider = MutatingMockProvider(mutation)
    result = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID, provider, f"invalid-{expected_error}"
    )
    assert result.status == "failed"
    assert result.candidate_count == 0
    assert _count(formal_database, "test_case_candidates") == 0
    run = formal_database.fetch_one(
        "SELECT error_type FROM test_generation_runs WHERE test_generation_run_id=:id",
        {"id": result.run_id},
    )
    assert run == {"error_type": expected_error}


def test_candidate_schema_failure_is_not_classified_as_provider_error(
    formal_database: PluginDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = GenerationService(formal_database, max_retries=0)

    def reject_candidate(name: str, instance: Any) -> None:
        if name == "test_case_candidate.schema.json":
            raise ValidationError(
                "invalid candidate route",
                validator="pattern",
                validator_value="^/",
                instance="",
            )
        CaseSchemas().validate(name, instance)

    monkeypatch.setattr(service.compiler.schemas, "validate", reject_candidate)
    result = service.start(PROJECT_ID, MockLLMProvider(), "candidate-schema-classification")
    assert result.status == "failed"
    run = formal_database.fetch_one(
        "SELECT error_type FROM test_generation_runs WHERE test_generation_run_id=:id",
        {"id": result.run_id},
    )
    assert run == {"error_type": "CANDIDATE_SCHEMA_VALIDATION"}
    assert _count(formal_database, "test_case_candidates") == 0


@pytest.mark.parametrize(
    ("error_type", "eligible"),
    [
        ("INTENT_SCHEMA_VALIDATION", True),
        (
            "CANDIDATE_EXECUTABILITY_INVALID:UI_ROUTE_NOT_IN_CONTRACT:/type_details/route",
            True,
        ),
        ("JSON_PARSE_ERROR", False),
        ("OUTPUT_TRUNCATED", False),
        ("COMPILATION_ERROR", False),
        ("CANDIDATE_SCHEMA_VALIDATION", False),
        ("PROVIDER_CONFIGURATION_ERROR", False),
        ("PROVIDER_REQUEST_ERROR", False),
        ("BUDGET_EXCEEDED", False),
    ],
)
def test_structure_correction_eligibility_is_explicit(error_type: str, eligible: bool) -> None:
    assert is_structure_correction_eligible(error_type) is eligible


def test_complete_json_parse_error_is_correction_eligible() -> None:
    response = ProviderResponse(
        content='{"intents": [}',
        finish_reason="stop",
        input_tokens=10,
        output_tokens=10,
        http_status=200,
        latency_ms=1,
        provider_request_id="req-json",
        max_tokens=3072,
    )
    assert is_structure_correction_eligible("JSON_PARSE_ERROR", response)


@pytest.mark.parametrize("content", ["", "<html>bad gateway</html>"])
def test_unsafe_json_parse_error_is_not_correction_eligible(content: str) -> None:
    response = ProviderResponse(
        content=content,
        finish_reason="stop",
        input_tokens=10,
        output_tokens=10,
        http_status=200,
        latency_ms=1,
        provider_request_id="req-json",
        max_tokens=3072,
    )
    assert not is_structure_correction_eligible("JSON_PARSE_ERROR", response)


def test_call_and_cost_budgets_are_not_provider_errors(
    formal_database: PluginDatabase,
) -> None:
    service = GenerationService(
        formal_database,
        max_total_provider_calls=21,
        max_run_cost_usd="0.10",
    )
    result = service.start(PROJECT_ID, MockLLMProvider(), "budget-source")
    counters = RunCallCounters(total_provider_call_count=21)
    with pytest.raises(GenerationError, match="CALL_BUDGET_EXCEEDED"):
        service._check_call_budget(result.run_id, "TGB-API-001", 0, counters)
    zero_cost_service = GenerationService(formal_database, max_run_cost_usd="0")
    with pytest.raises(GenerationError, match="BUDGET_EXCEEDED"):
        zero_cost_service._check_call_budget(result.run_id, "TGB-API-001", 0, RunCallCounters())


def test_run_budget_excludes_historical_run_cost(
    formal_database: PluginDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = GenerationService(formal_database, max_run_cost_usd="0.25")
    historical = service.start(PROJECT_ID, MockLLMProvider(), "historical-cost")
    current = service.start(PROJECT_ID, MockLLMProvider(), "current-cost")
    original_fetch_one = formal_database.fetch_one
    observed: list[dict[str, object]] = []

    def scoped_fetch(
        statement: str, values: dict[str, object] | None = None
    ) -> dict[str, object] | None:
        if "SELECT actual_cost_microusd FROM test_generation_runs" in statement:
            observed.append(dict(values or {}))
            return {"actual_cost_microusd": 0}
        return original_fetch_one(statement, values)

    monkeypatch.setattr(formal_database, "fetch_one", scoped_fetch)
    service._check_call_budget(current.run_id, "TGB-API-001", 0, RunCallCounters())
    assert observed == [{"run": current.run_id}]
    assert historical.run_id != current.run_id

    def exhausted_fetch(
        statement: str, values: dict[str, object] | None = None
    ) -> dict[str, object] | None:
        if "SELECT actual_cost_microusd FROM test_generation_runs" in statement:
            assert values == {"run": current.run_id}
            return {"actual_cost_microusd": 250000}
        return original_fetch_one(statement, values)

    monkeypatch.setattr(formal_database, "fetch_one", exhausted_fetch)
    with pytest.raises(GenerationError, match="BUDGET_EXCEEDED"):
        service._check_call_budget(current.run_id, "TGB-API-001", 0, RunCallCounters())


def test_run_correction_budget_blocks_ninth_batch(
    formal_database: PluginDatabase,
) -> None:
    service = GenerationService(formal_database, max_corrections_per_run=8)
    result = service.start(PROJECT_ID, MockLLMProvider(), "correction-budget-source")
    counters = RunCallCounters(correction_call_count=8, total_provider_call_count=16)
    with pytest.raises(GenerationError, match="CORRECTION_BUDGET_EXCEEDED"):
        service._check_call_budget(result.run_id, "TGB-UI-002", 1, counters)


def test_provider_retry_and_total_call_run_limits_are_enforced(
    formal_database: PluginDatabase,
) -> None:
    service = GenerationService(formal_database)
    result = service.start(PROJECT_ID, MockLLMProvider(), "provider-budget-source")
    allowed = RunCallCounters(provider_retry_count=14, total_provider_call_count=39)
    service._check_call_budget(result.run_id, "TGB-UI-001", 0, allowed)
    with pytest.raises(GenerationError, match="CALL_BUDGET_EXCEEDED"):
        service._check_call_budget(
            result.run_id,
            "TGB-UI-001",
            0,
            RunCallCounters(provider_retry_count=15, total_provider_call_count=40),
        )


def test_truncated_json_is_rejected_without_partial_promotion(
    formal_database: PluginDatabase,
) -> None:
    provider = TruncatedMockProvider()
    result = GenerationService(formal_database, max_retries=0).start(
        PROJECT_ID, provider, "truncated"
    )
    assert result.status == "failed"
    assert result.candidate_count == 0
    assert provider.call_count == 1
    assert _count(formal_database, "test_case_candidates") == 0
    call = formal_database.fetch_one(
        "SELECT finish_reason,validation_status,error_type FROM test_generation_llm_calls"
    )
    assert call is not None
    assert call["finish_reason"] == "length"
    assert call["validation_status"] == "invalid"
    assert call["error_type"] == "OUTPUT_TRUNCATED"


def test_aggregate_rejects_duplicates_and_conflicts(
    formal_database: PluginDatabase,
) -> None:
    service = GenerationService(formal_database)
    result = service.start(PROJECT_ID, MockLLMProvider(), "aggregate-fixture")
    rows = formal_database.fetch_all(
        "SELECT payload_json FROM test_case_candidates "
        "WHERE test_generation_run_id=:run ORDER BY case_id",
        {"run": result.run_id},
    )
    cases = [json.loads(str(row["payload_json"])) for row in rows]
    snapshots = service._load_requirement_snapshots(PROJECT_ID)
    with pytest.raises(GenerationError, match="DUPLICATE_CASE_ID"):
        service._validate_aggregate(result.run_id, snapshots, [*cases, dict(cases[0])])
    first = dict(cases[0])
    second = dict(cases[1])
    for field in (
        "case_type",
        "requirement_ids",
        "primary_requirement_id",
        "preconditions",
        "test_data",
        "type_details",
    ):
        second[field] = first[field]
    second["expected_results"] = ["A conflicting deterministic oracle."]
    with pytest.raises(GenerationError, match="CONFLICTING_EXPECTED_RESULT"):
        service._validate_aggregate(result.run_id, snapshots, [first, second])


def test_atomic_promotion_rolls_back_all_candidates_on_failure(
    formal_database: PluginDatabase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = GenerationService(formal_database)

    def fail_validation(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("simulated transaction failure")

    monkeypatch.setattr(service, "_validation_tx", fail_validation)
    result = service.start(PROJECT_ID, MockLLMProvider(), "atomic-rollback")
    assert result.status == "failed"
    assert result.candidate_count == 0
    assert _count(formal_database, "test_case_candidates") == 0
    assert _count(formal_database, "test_case_candidate_requirement_links") == 0
    assert _count(formal_database, "test_case_coverage_results") == 0


def test_requirement_count_gate_rejects_incomplete_snapshot(
    database: PluginDatabase,
) -> None:
    _seed_formal_requirements(database)
    database.execute("DELETE FROM requirements WHERE requirement_id='REQ-AUTH-FLOW-019'")
    with pytest.raises(GenerationError, match="FORMAL_REQUIREMENT_COUNT_MISMATCH"):
        GenerationService(database).preflight(PROJECT_ID)


def test_generation_http_boundary_exposes_plan_status_and_read_only_collection(
    client: FlaskClient,
    database: PluginDatabase,
) -> None:
    _seed_formal_requirements(database)
    plan_response = client.get(f"/api/v1/projects/{PROJECT_ID}/test-generation-plan")
    assert plan_response.status_code == 200
    assert plan_response.get_json()["data"]["requirement_count"] == 19

    create_response = client.post(
        f"/api/v1/projects/{PROJECT_ID}/test-generation-runs",
        json={"provider_mode": "mock"},
        headers={"Idempotency-Key": "route-mock-generation"},
    )
    assert create_response.status_code == 202
    result = create_response.get_json()["data"]
    assert result["status"] == "validated_pending_review"

    status_response = client.get(f"/api/v1/test-generation-runs/{result['run_id']}")
    assert status_response.status_code == 200
    assert len(status_response.get_json()["data"]["batches"]) == 13

    collection_response = client.get(
        f"/api/v1/test-generation-runs/{result['run_id']}/candidate-collection"
    )
    assert collection_response.status_code == 200
    collection = collection_response.get_json()["data"]
    assert collection["review_disposition"] == "not_reviewed_phase6_required"
    assert collection["candidate_count"] == 46

    assert client.get("/api/v1/test-generation-runs/TGR-MISSING").status_code == 404
    missing_collection = client.get("/api/v1/test-generation-runs/TGR-MISSING/candidate-collection")
    assert missing_collection.status_code == 404


class InvalidThenConfigurationProvider(MockLLMProvider):
    def __init__(self) -> None:
        super().__init__()
        self.attempt_count = 0

    def generate_test_cases(self, **kwargs: Any) -> ProviderResponse:
        self.attempt_count += 1
        if self.attempt_count == 2:
            raise ProviderConfigurationError("CORRECTION_RESERVATION_BLOCKED")
        response = super().generate_test_cases(**kwargs)
        payload = json.loads(response.content)
        payload["intents"][0]["scenario_type"] = "unsupported-fixture"
        return ProviderResponse(
            content=json.dumps(payload),
            finish_reason=response.finish_reason,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            latency_ms=response.latency_ms,
            http_status=response.http_status,
            provider_request_id=response.provider_request_id,
            max_tokens=response.max_tokens,
            input_cache_hit_tokens=response.input_cache_hit_tokens,
            input_cache_miss_tokens=response.input_cache_miss_tokens,
        )


def test_configuration_failure_during_correction_does_not_duplicate_previous_response(
    formal_database: PluginDatabase,
) -> None:
    provider = InvalidThenConfigurationProvider()
    result = GenerationService(formal_database, max_retries=1).start(
        PROJECT_ID, provider, "no-stale-response"
    )

    assert result.status == "failed"
    assert provider.attempt_count == 2
    calls = formal_database.fetch_one(
        "SELECT COUNT(*) AS count FROM test_generation_llm_calls WHERE test_generation_run_id=:run",
        {"run": result.run_id},
    )
    assert calls == {"count": 1}
