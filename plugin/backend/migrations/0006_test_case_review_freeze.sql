CREATE TABLE test_case_reviews (
  test_case_review_id TEXT PRIMARY KEY,
  test_generation_run_id TEXT NOT NULL REFERENCES test_generation_runs(test_generation_run_id),
  test_case_candidate_id TEXT NOT NULL REFERENCES test_case_candidates(test_case_candidate_id),
  reviewer_id TEXT NOT NULL,
  decision TEXT NOT NULL CHECK(decision IN ('approve', 'reject', 'request_changes')),
  comment TEXT NOT NULL,
  candidate_content_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE approved_test_case_versions (
  approved_test_case_version_id TEXT PRIMARY KEY,
  test_case_candidate_id TEXT NOT NULL UNIQUE REFERENCES test_case_candidates(test_case_candidate_id),
  test_case_review_id TEXT NOT NULL UNIQUE REFERENCES test_case_reviews(test_case_review_id),
  case_id TEXT NOT NULL,
  case_version INTEGER NOT NULL,
  schema_version TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  approved_by TEXT NOT NULL,
  approved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(case_id, case_version)
);

CREATE TABLE frozen_baselines (
  frozen_baseline_id TEXT PRIMARY KEY,
  test_generation_run_id TEXT NOT NULL UNIQUE REFERENCES test_generation_runs(test_generation_run_id),
  baseline_version INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status = 'frozen'),
  collection_hash TEXT NOT NULL,
  baseline_hash TEXT NOT NULL UNIQUE,
  frozen_by TEXT NOT NULL,
  environment_id TEXT NOT NULL,
  protocol_version TEXT NOT NULL,
  executor_contract_version TEXT NOT NULL,
  frozen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(test_generation_run_id, baseline_version)
);

CREATE TABLE frozen_baseline_members (
  frozen_baseline_member_id TEXT PRIMARY KEY,
  frozen_baseline_id TEXT NOT NULL REFERENCES frozen_baselines(frozen_baseline_id),
  approved_test_case_version_id TEXT NOT NULL REFERENCES approved_test_case_versions(approved_test_case_version_id),
  case_id TEXT NOT NULL,
  case_version INTEGER NOT NULL,
  approved_content_hash TEXT NOT NULL,
  requirement_trace_hash TEXT NOT NULL,
  ordinal INTEGER NOT NULL,
  UNIQUE(frozen_baseline_id, case_id),
  UNIQUE(frozen_baseline_id, ordinal)
);

CREATE TABLE immutable_execution_snapshots (
  immutable_execution_snapshot_id TEXT PRIMARY KEY,
  frozen_baseline_id TEXT NOT NULL REFERENCES frozen_baselines(frozen_baseline_id),
  frozen_baseline_member_id TEXT NOT NULL UNIQUE REFERENCES frozen_baseline_members(frozen_baseline_member_id),
  case_id TEXT NOT NULL,
  snapshot_json TEXT NOT NULL,
  snapshot_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE test_case_review_audit_events (
  test_case_review_audit_event_id TEXT PRIMARY KEY,
  test_generation_run_id TEXT NOT NULL REFERENCES test_generation_runs(test_generation_run_id),
  test_case_candidate_id TEXT REFERENCES test_case_candidates(test_case_candidate_id),
  frozen_baseline_id TEXT REFERENCES frozen_baselines(frozen_baseline_id),
  event_type TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_test_case_reviews_candidate
  ON test_case_reviews(test_case_candidate_id, created_at, test_case_review_id);
CREATE INDEX ix_frozen_baseline_members_baseline
  ON frozen_baseline_members(frozen_baseline_id, ordinal);

CREATE TRIGGER test_case_reviews_no_update BEFORE UPDATE ON test_case_reviews
BEGIN SELECT RAISE(ABORT, 'test case reviews are immutable'); END;
CREATE TRIGGER test_case_reviews_no_delete BEFORE DELETE ON test_case_reviews
BEGIN SELECT RAISE(ABORT, 'test case reviews are immutable'); END;
CREATE TRIGGER approved_versions_no_update BEFORE UPDATE ON approved_test_case_versions
BEGIN SELECT RAISE(ABORT, 'approved test case versions are immutable'); END;
CREATE TRIGGER approved_versions_no_delete BEFORE DELETE ON approved_test_case_versions
BEGIN SELECT RAISE(ABORT, 'approved test case versions are immutable'); END;
CREATE TRIGGER frozen_baselines_no_update BEFORE UPDATE ON frozen_baselines
BEGIN SELECT RAISE(ABORT, 'frozen baselines are immutable'); END;
CREATE TRIGGER frozen_baselines_no_delete BEFORE DELETE ON frozen_baselines
BEGIN SELECT RAISE(ABORT, 'frozen baselines are immutable'); END;
CREATE TRIGGER frozen_members_no_update BEFORE UPDATE ON frozen_baseline_members
BEGIN SELECT RAISE(ABORT, 'frozen baseline members are immutable'); END;
CREATE TRIGGER frozen_members_no_delete BEFORE DELETE ON frozen_baseline_members
BEGIN SELECT RAISE(ABORT, 'frozen baseline members are immutable'); END;
CREATE TRIGGER execution_snapshots_no_update BEFORE UPDATE ON immutable_execution_snapshots
BEGIN SELECT RAISE(ABORT, 'execution snapshots are immutable'); END;
CREATE TRIGGER execution_snapshots_no_delete BEFORE DELETE ON immutable_execution_snapshots
BEGIN SELECT RAISE(ABORT, 'execution snapshots are immutable'); END;
CREATE TRIGGER review_audit_no_update BEFORE UPDATE ON test_case_review_audit_events
BEGIN SELECT RAISE(ABORT, 'review audit events are immutable'); END;
CREATE TRIGGER review_audit_no_delete BEFORE DELETE ON test_case_review_audit_events
BEGIN SELECT RAISE(ABORT, 'review audit events are immutable'); END;
