CREATE TABLE defect_regression_runs (
  defect_regression_run_id TEXT PRIMARY KEY,
  canonical_bug_record_id TEXT NOT NULL REFERENCES canonical_bug_records(canonical_bug_record_id),
  baseline_report_id TEXT NOT NULL REFERENCES canonical_test_reports(canonical_test_report_id),
  frozen_baseline_id TEXT NOT NULL REFERENCES frozen_baselines(frozen_baseline_id),
  baseline_api_test_run_id TEXT NOT NULL REFERENCES api_test_runs(api_test_run_id),
  baseline_ui_test_run_id TEXT NOT NULL REFERENCES ui_test_runs(ui_test_run_id),
  regression_api_test_run_id TEXT NOT NULL UNIQUE REFERENCES api_test_runs(api_test_run_id),
  regression_ui_test_run_id TEXT NOT NULL UNIQUE REFERENCES ui_test_runs(ui_test_run_id),
  status TEXT NOT NULL CHECK(status = 'completed'),
  api_seeded_before TEXT NOT NULL CHECK(api_seeded_before = 'FAIL'),
  api_seeded_after TEXT NOT NULL CHECK(api_seeded_after = 'PASS'),
  ui_seeded_before TEXT NOT NULL CHECK(ui_seeded_before = 'FAIL'),
  ui_seeded_after TEXT NOT NULL CHECK(ui_seeded_after = 'PASS'),
  guard_case_count INTEGER NOT NULL CHECK(guard_case_count > 0),
  guard_pass_count INTEGER NOT NULL CHECK(guard_pass_count = guard_case_count),
  trace_json TEXT NOT NULL,
  trace_hash TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE bug_status_events (
  bug_status_event_id TEXT PRIMARY KEY,
  canonical_bug_record_id TEXT NOT NULL REFERENCES canonical_bug_records(canonical_bug_record_id),
  defect_regression_run_id TEXT NOT NULL UNIQUE
    REFERENCES defect_regression_runs(defect_regression_run_id),
  from_status TEXT NOT NULL CHECK(from_status = 'open'),
  to_status TEXT NOT NULL CHECK(to_status = 'closed'),
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(canonical_bug_record_id, to_status)
);

CREATE TRIGGER defect_regression_no_update BEFORE UPDATE ON defect_regression_runs
BEGIN SELECT RAISE(ABORT, 'defect regression runs are immutable'); END;
CREATE TRIGGER defect_regression_no_delete BEFORE DELETE ON defect_regression_runs
BEGIN SELECT RAISE(ABORT, 'defect regression runs are immutable'); END;
CREATE TRIGGER bug_status_event_no_update BEFORE UPDATE ON bug_status_events
BEGIN SELECT RAISE(ABORT, 'bug status events are immutable'); END;
CREATE TRIGGER bug_status_event_no_delete BEFORE DELETE ON bug_status_events
BEGIN SELECT RAISE(ABORT, 'bug status events are immutable'); END;
