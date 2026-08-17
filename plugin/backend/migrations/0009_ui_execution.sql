CREATE TABLE ui_test_runs (
  ui_test_run_id TEXT PRIMARY KEY,
  frozen_baseline_id TEXT NOT NULL REFERENCES frozen_baselines(frozen_baseline_id),
  environment_id TEXT NOT NULL,
  executor_version TEXT NOT NULL,
  browser_name TEXT NOT NULL,
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

CREATE TABLE ui_test_results (
  ui_test_result_id TEXT PRIMARY KEY,
  ui_test_run_id TEXT NOT NULL REFERENCES ui_test_runs(ui_test_run_id),
  immutable_execution_snapshot_id TEXT NOT NULL
    REFERENCES immutable_execution_snapshots(immutable_execution_snapshot_id),
  case_id TEXT NOT NULL,
  case_version INTEGER NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('PASS', 'FAIL', 'BLOCKED', 'ERROR', 'SKIPPED')),
  failure_type TEXT,
  expected_route TEXT,
  actual_route TEXT,
  duration_ms INTEGER NOT NULL CHECK(duration_ms >= 0),
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(ui_test_run_id, immutable_execution_snapshot_id),
  UNIQUE(ui_test_run_id, case_id)
);

CREATE TABLE ui_test_evidence (
  ui_test_evidence_id TEXT PRIMARY KEY,
  ui_test_result_id TEXT NOT NULL UNIQUE REFERENCES ui_test_results(ui_test_result_id),
  evidence_json TEXT NOT NULL,
  evidence_hash TEXT NOT NULL UNIQUE,
  screenshot_path TEXT NOT NULL,
  screenshot_hash TEXT NOT NULL,
  trace_path TEXT NOT NULL,
  trace_hash TEXT NOT NULL,
  redaction_applied INTEGER NOT NULL CHECK(redaction_applied = 1),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_ui_test_runs_baseline ON ui_test_runs(frozen_baseline_id, created_at);
CREATE INDEX ix_ui_test_results_run ON ui_test_results(ui_test_run_id, case_id);

CREATE TRIGGER ui_test_runs_no_update BEFORE UPDATE ON ui_test_runs
BEGIN SELECT RAISE(ABORT, 'ui test runs are immutable'); END;
CREATE TRIGGER ui_test_runs_no_delete BEFORE DELETE ON ui_test_runs
BEGIN SELECT RAISE(ABORT, 'ui test runs are immutable'); END;
CREATE TRIGGER ui_test_results_no_update BEFORE UPDATE ON ui_test_results
BEGIN SELECT RAISE(ABORT, 'ui test results are immutable'); END;
CREATE TRIGGER ui_test_results_no_delete BEFORE DELETE ON ui_test_results
BEGIN SELECT RAISE(ABORT, 'ui test results are immutable'); END;
CREATE TRIGGER ui_test_evidence_no_update BEFORE UPDATE ON ui_test_evidence
BEGIN SELECT RAISE(ABORT, 'ui test evidence is immutable'); END;
CREATE TRIGGER ui_test_evidence_no_delete BEFORE DELETE ON ui_test_evidence
BEGIN SELECT RAISE(ABORT, 'ui test evidence is immutable'); END;
