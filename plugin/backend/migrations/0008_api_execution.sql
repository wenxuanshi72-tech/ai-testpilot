CREATE TABLE api_test_runs (
  api_test_run_id TEXT PRIMARY KEY,
  frozen_baseline_id TEXT NOT NULL REFERENCES frozen_baselines(frozen_baseline_id),
  environment_id TEXT NOT NULL,
  executor_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('completed', 'failed')),
  total_count INTEGER NOT NULL,
  pass_count INTEGER NOT NULL,
  fail_count INTEGER NOT NULL,
  blocked_count INTEGER NOT NULL,
  error_count INTEGER NOT NULL,
  skipped_count INTEGER NOT NULL,
  started_at TEXT NOT NULL,
  completed_at TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE api_test_results (
  api_test_result_id TEXT PRIMARY KEY,
  api_test_run_id TEXT NOT NULL REFERENCES api_test_runs(api_test_run_id),
  immutable_execution_snapshot_id TEXT NOT NULL
    REFERENCES immutable_execution_snapshots(immutable_execution_snapshot_id),
  case_id TEXT NOT NULL,
  case_version INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('PASS', 'FAIL', 'BLOCKED', 'ERROR', 'SKIPPED')),
  failure_type TEXT,
  expected_status INTEGER,
  actual_status INTEGER,
  duration_ms INTEGER NOT NULL CHECK(duration_ms >= 0),
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(api_test_run_id, immutable_execution_snapshot_id),
  UNIQUE(api_test_run_id, case_id)
);

CREATE TABLE api_test_evidence (
  api_test_evidence_id TEXT PRIMARY KEY,
  api_test_result_id TEXT NOT NULL UNIQUE REFERENCES api_test_results(api_test_result_id),
  evidence_kind TEXT NOT NULL CHECK(evidence_kind = 'api_exchange'),
  evidence_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL UNIQUE,
  redaction_applied INTEGER NOT NULL CHECK(redaction_applied = 1),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_api_test_runs_baseline ON api_test_runs(frozen_baseline_id, created_at);
CREATE INDEX ix_api_test_results_run ON api_test_results(api_test_run_id, case_id);

CREATE TRIGGER api_test_runs_no_update BEFORE UPDATE ON api_test_runs
BEGIN SELECT RAISE(ABORT, 'api test runs are immutable'); END;
CREATE TRIGGER api_test_runs_no_delete BEFORE DELETE ON api_test_runs
BEGIN SELECT RAISE(ABORT, 'api test runs are immutable'); END;
CREATE TRIGGER api_test_results_no_update BEFORE UPDATE ON api_test_results
BEGIN SELECT RAISE(ABORT, 'api test results are immutable'); END;
CREATE TRIGGER api_test_results_no_delete BEFORE DELETE ON api_test_results
BEGIN SELECT RAISE(ABORT, 'api test results are immutable'); END;
CREATE TRIGGER api_test_evidence_no_update BEFORE UPDATE ON api_test_evidence
BEGIN SELECT RAISE(ABORT, 'api test evidence is immutable'); END;
CREATE TRIGGER api_test_evidence_no_delete BEFORE DELETE ON api_test_evidence
BEGIN SELECT RAISE(ABORT, 'api test evidence is immutable'); END;
