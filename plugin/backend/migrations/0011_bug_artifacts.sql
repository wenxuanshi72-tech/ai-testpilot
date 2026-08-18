CREATE TABLE canonical_bug_records (
  canonical_bug_record_id TEXT PRIMARY KEY,
  bug_id TEXT NOT NULL,
  bug_version INTEGER NOT NULL CHECK(bug_version > 0),
  project_id TEXT NOT NULL REFERENCES projects(project_id),
  evidence_consolidation_run_id TEXT NOT NULL
    REFERENCES evidence_consolidation_runs(evidence_consolidation_run_id),
  schema_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('open', 'resolved', 'closed')),
  severity TEXT NOT NULL,
  priority TEXT NOT NULL,
  defect_type TEXT NOT NULL,
  canonical_json TEXT NOT NULL,
  canonical_hash TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(bug_id, bug_version),
  UNIQUE(evidence_consolidation_run_id, bug_id)
);

CREATE TABLE canonical_bug_sources (
  canonical_bug_source_id TEXT PRIMARY KEY,
  canonical_bug_record_id TEXT NOT NULL
    REFERENCES canonical_bug_records(canonical_bug_record_id),
  failure_classification_id TEXT NOT NULL
    REFERENCES deterministic_failure_classifications(failure_classification_id),
  source_executor TEXT NOT NULL CHECK(source_executor IN ('api', 'ui')),
  source_result_id TEXT NOT NULL,
  source_evidence_id TEXT NOT NULL,
  case_id TEXT NOT NULL,
  case_version INTEGER NOT NULL,
  approved_test_case_version_id TEXT NOT NULL
    REFERENCES approved_test_case_versions(approved_test_case_version_id),
  requirement_id TEXT NOT NULL,
  evidence_kind TEXT NOT NULL,
  evidence_hash TEXT NOT NULL,
  relative_path TEXT,
  UNIQUE(canonical_bug_record_id, failure_classification_id, evidence_kind)
);

CREATE TABLE bug_artifact_bundles (
  bug_artifact_bundle_id TEXT PRIMARY KEY,
  canonical_bug_record_id TEXT NOT NULL UNIQUE
    REFERENCES canonical_bug_records(canonical_bug_record_id),
  format_version TEXT NOT NULL,
  bundle_path TEXT NOT NULL UNIQUE,
  json_path TEXT NOT NULL UNIQUE,
  json_hash TEXT NOT NULL,
  markdown_path TEXT NOT NULL UNIQUE,
  markdown_hash TEXT NOT NULL,
  manifest_path TEXT NOT NULL UNIQUE,
  manifest_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status = 'completed'),
  created_at TEXT NOT NULL
);

CREATE TABLE bug_artifact_audit_events (
  bug_artifact_audit_event_id TEXT PRIMARY KEY,
  canonical_bug_record_id TEXT NOT NULL
    REFERENCES canonical_bug_records(canonical_bug_record_id),
  event_type TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_bug_sources_result ON canonical_bug_sources(source_executor, source_result_id);
CREATE INDEX ix_bug_sources_requirement ON canonical_bug_sources(requirement_id, case_id);

CREATE TRIGGER canonical_bug_no_update BEFORE UPDATE ON canonical_bug_records
BEGIN SELECT RAISE(ABORT, 'canonical bug records are immutable'); END;
CREATE TRIGGER canonical_bug_no_delete BEFORE DELETE ON canonical_bug_records
BEGIN SELECT RAISE(ABORT, 'canonical bug records are immutable'); END;
CREATE TRIGGER canonical_bug_source_no_update BEFORE UPDATE ON canonical_bug_sources
BEGIN SELECT RAISE(ABORT, 'canonical bug sources are immutable'); END;
CREATE TRIGGER canonical_bug_source_no_delete BEFORE DELETE ON canonical_bug_sources
BEGIN SELECT RAISE(ABORT, 'canonical bug sources are immutable'); END;
CREATE TRIGGER bug_bundle_no_update BEFORE UPDATE ON bug_artifact_bundles
BEGIN SELECT RAISE(ABORT, 'bug artifact bundles are immutable'); END;
CREATE TRIGGER bug_bundle_no_delete BEFORE DELETE ON bug_artifact_bundles
BEGIN SELECT RAISE(ABORT, 'bug artifact bundles are immutable'); END;
CREATE TRIGGER bug_artifact_audit_no_update BEFORE UPDATE ON bug_artifact_audit_events
BEGIN SELECT RAISE(ABORT, 'bug artifact audit events are immutable'); END;
CREATE TRIGGER bug_artifact_audit_no_delete BEFORE DELETE ON bug_artifact_audit_events
BEGIN SELECT RAISE(ABORT, 'bug artifact audit events are immutable'); END;
