CREATE TABLE canonical_test_reports (
  canonical_test_report_id TEXT PRIMARY KEY,
  report_version INTEGER NOT NULL CHECK(report_version > 0),
  project_id TEXT NOT NULL REFERENCES projects(project_id),
  frozen_baseline_id TEXT NOT NULL REFERENCES frozen_baselines(frozen_baseline_id),
  api_test_run_id TEXT NOT NULL REFERENCES api_test_runs(api_test_run_id),
  ui_test_run_id TEXT NOT NULL REFERENCES ui_test_runs(ui_test_run_id),
  evidence_consolidation_run_id TEXT NOT NULL
    REFERENCES evidence_consolidation_runs(evidence_consolidation_run_id),
  canonical_bug_record_id TEXT NOT NULL REFERENCES canonical_bug_records(canonical_bug_record_id),
  schema_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status = 'completed'),
  canonical_json TEXT NOT NULL,
  canonical_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(api_test_run_id, ui_test_run_id, evidence_consolidation_run_id, canonical_bug_record_id)
);

CREATE TABLE test_report_artifact_bundles (
  test_report_artifact_bundle_id TEXT PRIMARY KEY,
  canonical_test_report_id TEXT NOT NULL UNIQUE
    REFERENCES canonical_test_reports(canonical_test_report_id),
  format_version TEXT NOT NULL,
  bundle_path TEXT NOT NULL UNIQUE,
  json_path TEXT NOT NULL UNIQUE,
  json_hash TEXT NOT NULL,
  markdown_path TEXT NOT NULL UNIQUE,
  markdown_hash TEXT NOT NULL,
  html_path TEXT NOT NULL UNIQUE,
  html_hash TEXT NOT NULL,
  pdf_path TEXT NOT NULL UNIQUE,
  pdf_hash TEXT NOT NULL,
  manifest_path TEXT NOT NULL UNIQUE,
  manifest_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status = 'completed'),
  created_at TEXT NOT NULL
);

CREATE TABLE test_report_audit_events (
  test_report_audit_event_id TEXT PRIMARY KEY,
  canonical_test_report_id TEXT NOT NULL
    REFERENCES canonical_test_reports(canonical_test_report_id),
  event_type TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER canonical_report_no_update BEFORE UPDATE ON canonical_test_reports
BEGIN SELECT RAISE(ABORT, 'canonical test reports are immutable'); END;
CREATE TRIGGER canonical_report_no_delete BEFORE DELETE ON canonical_test_reports
BEGIN SELECT RAISE(ABORT, 'canonical test reports are immutable'); END;
CREATE TRIGGER report_bundle_no_update BEFORE UPDATE ON test_report_artifact_bundles
BEGIN SELECT RAISE(ABORT, 'test report bundles are immutable'); END;
CREATE TRIGGER report_bundle_no_delete BEFORE DELETE ON test_report_artifact_bundles
BEGIN SELECT RAISE(ABORT, 'test report bundles are immutable'); END;
CREATE TRIGGER report_audit_no_update BEFORE UPDATE ON test_report_audit_events
BEGIN SELECT RAISE(ABORT, 'test report audit events are immutable'); END;
CREATE TRIGGER report_audit_no_delete BEFORE DELETE ON test_report_audit_events
BEGIN SELECT RAISE(ABORT, 'test report audit events are immutable'); END;
