CREATE TABLE test_case_human_revisions (
  test_case_human_revision_id TEXT PRIMARY KEY,
  test_generation_run_id TEXT NOT NULL REFERENCES test_generation_runs(test_generation_run_id),
  test_case_candidate_id TEXT NOT NULL REFERENCES test_case_candidates(test_case_candidate_id),
  revision_number INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  revised_by TEXT NOT NULL,
  revision_reason TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(test_case_candidate_id, revision_number),
  UNIQUE(test_case_candidate_id, content_hash)
);

ALTER TABLE test_case_reviews ADD COLUMN automation_disposition TEXT
  CHECK(automation_disposition IN ('automated', 'manual', 'deferred'));
ALTER TABLE test_case_reviews ADD COLUMN disposition_reason TEXT;
ALTER TABLE test_case_reviews ADD COLUMN test_case_human_revision_id TEXT
  REFERENCES test_case_human_revisions(test_case_human_revision_id);

DROP TRIGGER approved_versions_no_update;
DROP TRIGGER approved_versions_no_delete;

PRAGMA legacy_alter_table=ON;
ALTER TABLE approved_test_case_versions RENAME TO approved_test_case_versions_0006;

CREATE TABLE approved_test_case_versions (
  approved_test_case_version_id TEXT PRIMARY KEY,
  test_case_candidate_id TEXT NOT NULL REFERENCES test_case_candidates(test_case_candidate_id),
  test_case_review_id TEXT NOT NULL UNIQUE REFERENCES test_case_reviews(test_case_review_id),
  case_id TEXT NOT NULL,
  case_version INTEGER NOT NULL,
  schema_version TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  approved_by TEXT NOT NULL,
  approved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  test_case_human_revision_id TEXT REFERENCES test_case_human_revisions(test_case_human_revision_id),
  automation_disposition TEXT
    CHECK(automation_disposition IN ('automated', 'manual', 'deferred')),
  UNIQUE(case_id, case_version),
  UNIQUE(test_case_candidate_id, content_hash),
  UNIQUE(test_case_candidate_id, test_case_human_revision_id)
);

INSERT INTO approved_test_case_versions(
  approved_test_case_version_id,test_case_candidate_id,test_case_review_id,case_id,
  case_version,schema_version,payload_json,content_hash,approved_by,approved_at,
  test_case_human_revision_id,automation_disposition
)
SELECT approved_test_case_version_id,test_case_candidate_id,test_case_review_id,case_id,
  case_version,schema_version,payload_json,content_hash,approved_by,approved_at,NULL,'automated'
FROM approved_test_case_versions_0006;

DROP TABLE approved_test_case_versions_0006;
PRAGMA legacy_alter_table=OFF;

CREATE INDEX ix_approved_versions_candidate
  ON approved_test_case_versions(test_case_candidate_id, case_version);

CREATE TRIGGER approved_versions_no_update BEFORE UPDATE ON approved_test_case_versions
BEGIN SELECT RAISE(ABORT, 'approved test case versions are immutable'); END;
CREATE TRIGGER approved_versions_no_delete BEFORE DELETE ON approved_test_case_versions
BEGIN SELECT RAISE(ABORT, 'approved test case versions are immutable'); END;

CREATE INDEX ix_human_revisions_candidate
  ON test_case_human_revisions(test_case_candidate_id, revision_number);
CREATE INDEX ix_reviews_disposition
  ON test_case_reviews(test_generation_run_id, automation_disposition, created_at);

CREATE TRIGGER human_revisions_no_update BEFORE UPDATE ON test_case_human_revisions
BEGIN SELECT RAISE(ABORT, 'human test case revisions are immutable'); END;
CREATE TRIGGER human_revisions_no_delete BEFORE DELETE ON test_case_human_revisions
BEGIN SELECT RAISE(ABORT, 'human test case revisions are immutable'); END;
