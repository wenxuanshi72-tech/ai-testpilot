from __future__ import annotations

import json
import sqlite3
from copy import deepcopy
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError

from plugin.backend.app.database import MIGRATIONS_DIR, PluginDatabase
from plugin.backend.app.providers import MockLLMProvider
from plugin.backend.app.test_generation import TestGenerationService as GenerationService
from plugin.backend.app.test_review import TestReviewError as ReviewError
from plugin.backend.app.test_review import TestReviewService as ReviewService
from plugin.backend.app.test_review import _canonical, _hash
from plugin.backend.tests.test_test_generation import PROJECT_ID, _seed_formal_requirements


def _database_at_0006(path: Path) -> PluginDatabase:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE schema_migrations (version TEXT PRIMARY KEY, "
            "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )
        for migration in sorted(MIGRATIONS_DIR.glob("000[1-6]_*.sql")):
            connection.executescript(migration.read_text(encoding="utf-8"))
            connection.execute(
                "INSERT INTO schema_migrations(version) VALUES (?)", (migration.stem,)
            )
    return PluginDatabase(f"sqlite:///{path.as_posix()}")


def test_0006_upgrade_preserves_v1_and_freezes_only_latest_revision(tmp_path: Path) -> None:
    database = _database_at_0006(tmp_path / "upgrade-0006.db")
    _seed_formal_requirements(database)
    generation = GenerationService(database).start(PROJECT_ID, MockLLMProvider(), "upgrade-v1")
    candidate = database.fetch_one(
        "SELECT * FROM test_case_candidates WHERE test_generation_run_id=:run "
        "AND case_id='TC-API-AUTH-REG-005'",
        {"run": generation.run_id},
    )
    assert candidate is not None
    original = json.loads(str(candidate["payload_json"]))
    v1_payload = deepcopy(original)
    v1_payload["review_status"] = "approved"
    v1_payload["approved_version"] = 1
    v1_hash = _hash(v1_payload)
    database.execute(
        "INSERT INTO test_case_reviews(test_case_review_id,test_generation_run_id,"
        "test_case_candidate_id,reviewer_id,decision,comment,candidate_content_hash) "
        "VALUES ('TCR-OLD-APPROVE',:run,:candidate,'portfolio-owner','approve',"
        "'Historical v1 approval.',:hash)",
        {
            "run": generation.run_id,
            "candidate": candidate["test_case_candidate_id"],
            "hash": candidate["content_hash"],
        },
    )
    database.execute(
        "INSERT INTO approved_test_case_versions(approved_test_case_version_id,"
        "test_case_candidate_id,test_case_review_id,case_id,case_version,schema_version,"
        "payload_json,content_hash,approved_by) VALUES ('ATCV-OLD-V1',:candidate,"
        "'TCR-OLD-APPROVE','TC-API-AUTH-REG-005',1,:schema,:payload,:hash,'portfolio-owner')",
        {
            "candidate": candidate["test_case_candidate_id"],
            "schema": original["schema_version"],
            "payload": _canonical(v1_payload),
            "hash": v1_hash,
        },
    )
    database.execute(
        "INSERT INTO test_case_reviews(test_case_review_id,test_generation_run_id,"
        "test_case_candidate_id,reviewer_id,decision,comment,candidate_content_hash) "
        "VALUES ('TCR-OLD-CHANGES',:run,:candidate,'portfolio-owner','request_changes',"
        "'Executable revision required.',:hash)",
        {
            "run": generation.run_id,
            "candidate": candidate["test_case_candidate_id"],
            "hash": candidate["content_hash"],
        },
    )
    before = database.fetch_one(
        "SELECT * FROM approved_test_case_versions "
        "WHERE approved_test_case_version_id='ATCV-OLD-V1'"
    )

    database.migrate()
    service = ReviewService(database)
    revised = deepcopy(original)
    revised["objective"] += " Verify the formal rejection oracle."
    revision = service.create_human_revision(
        generation.run_id,
        "TC-API-AUTH-REG-005",
        revised_by="portfolio-owner",
        revision_reason="Make the seeded-defect objective executable and internally consistent.",
        expected_content_hash=str(candidate["content_hash"]),
        candidate=revised,
    )
    assert revision["executability_findings"] == []
    approved = service.review(
        generation.run_id,
        "TC-API-AUTH-REG-005",
        reviewer_id="portfolio-owner",
        decision="approve",
        automation_disposition="automated",
        disposition_reason="Latest valid executable revision.",
        comment="Approve v2 without changing historical v1.",
        expected_content_hash=revision["content_hash"],
        human_revision_id=revision["human_revision_id"],
    )
    after = database.fetch_one(
        "SELECT approved_test_case_version_id,test_case_candidate_id,test_case_review_id,"
        "case_id,case_version,schema_version,payload_json,content_hash,approved_by,approved_at "
        "FROM approved_test_case_versions WHERE approved_test_case_version_id='ATCV-OLD-V1'"
    )
    assert before is not None and after is not None
    assert {key: before[key] for key in after} == after
    with pytest.raises(IntegrityError, match="approved test case versions are immutable"):
        database.execute(
            "UPDATE approved_test_case_versions SET approved_by='changed' "
            "WHERE approved_test_case_version_id='ATCV-OLD-V1'"
        )
    with pytest.raises(IntegrityError, match="approved test case versions are immutable"):
        database.execute(
            "DELETE FROM approved_test_case_versions "
            "WHERE approved_test_case_version_id='ATCV-OLD-V1'"
        )
    assert database.fetch_one(
        "SELECT case_version FROM approved_test_case_versions "
        "WHERE approved_test_case_version_id=:id",
        {"id": approved["approved_test_case_version_id"]},
    ) == {"case_version": 2}

    plan = service.mvp_classification_plan(generation.run_id)
    collection = service.collection(generation.run_id)
    for item in collection["candidates"]:
        if item["case_id"] == "TC-API-AUTH-REG-005":
            continue
        disposition = next(
            row["proposed_disposition"]
            for row in plan["candidates"]
            if row["case_id"] == item["case_id"]
        )
        service.review(
            generation.run_id,
            item["case_id"],
            reviewer_id="portfolio-owner",
            decision="approve",
            automation_disposition=disposition,
            disposition_reason="Offline migration regression classification.",
            comment="Deterministic temporary-database regression review.",
            expected_content_hash=item["content_hash"],
        )
    frozen = service.freeze(
        generation.run_id,
        frozen_by="portfolio-owner",
        environment_id="local-test",
        executor_contract_version="test-executor@1.0.0",
    )
    selected = database.fetch_all(
        "SELECT m.approved_test_case_version_id,m.case_version FROM frozen_baseline_members m "
        "WHERE m.frozen_baseline_id=:baseline AND m.case_id='TC-API-AUTH-REG-005'",
        {"baseline": frozen.baseline_id},
    )
    snapshots = database.fetch_all(
        "SELECT immutable_execution_snapshot_id FROM immutable_execution_snapshots s "
        "JOIN frozen_baseline_members m ON m.frozen_baseline_member_id=s.frozen_baseline_member_id "
        "WHERE m.frozen_baseline_id=:baseline AND m.case_id='TC-API-AUTH-REG-005'",
        {"baseline": frozen.baseline_id},
    )
    assert selected == [
        {
            "approved_test_case_version_id": approved["approved_test_case_version_id"],
            "case_version": 2,
        }
    ]
    assert len(snapshots) == 1
    approved_foreign_keys = database.fetch_all("PRAGMA foreign_key_list(frozen_baseline_members)")
    assert any(row["table"] == "approved_test_case_versions" for row in approved_foreign_keys)
    assert database.fetch_one("PRAGMA integrity_check") == {"integrity_check": "ok"}
    assert database.fetch_all("PRAGMA foreign_key_check") == []


def test_latest_revision_and_hash_guards(database: PluginDatabase) -> None:
    _seed_formal_requirements(database)
    generation = GenerationService(database).start(PROJECT_ID, MockLLMProvider(), "revision-guards")
    service = ReviewService(database)
    item = next(
        row
        for row in service.collection(generation.run_id)["candidates"]
        if row["case_id"] == "TC-API-AUTH-REG-005"
    )
    first_payload = deepcopy(item["candidate"])
    first_payload["objective"] += " First safe revision."
    first = service.create_human_revision(
        generation.run_id,
        item["case_id"],
        revised_by="portfolio-owner",
        revision_reason="First revision retained for history.",
        expected_content_hash=item["content_hash"],
        candidate=first_payload,
    )
    second_payload = deepcopy(item["candidate"])
    second_payload["objective"] += " Second safe revision."
    second = service.create_human_revision(
        generation.run_id,
        item["case_id"],
        revised_by="portfolio-owner",
        revision_reason="Second revision supersedes the first.",
        expected_content_hash=item["content_hash"],
        candidate=second_payload,
    )
    with pytest.raises(ReviewError, match="HUMAN_REVISION_IS_NOT_LATEST"):
        service.review(
            generation.run_id,
            item["case_id"],
            reviewer_id="portfolio-owner",
            decision="approve",
            automation_disposition="automated",
            disposition_reason="Stale revision must not be approved.",
            comment="Reject the stale immutable revision.",
            expected_content_hash=first["content_hash"],
            human_revision_id=first["human_revision_id"],
        )
    with pytest.raises(ReviewError, match="CANDIDATE_HASH_CHANGED"):
        service.review(
            generation.run_id,
            item["case_id"],
            reviewer_id="portfolio-owner",
            decision="approve",
            automation_disposition="automated",
            disposition_reason="Incorrect hash must be rejected.",
            comment="Reject mismatched content identity.",
            expected_content_hash="0" * 64,
            human_revision_id=second["human_revision_id"],
        )
