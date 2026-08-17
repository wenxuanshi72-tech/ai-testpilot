CREATE TABLE evidence_consolidation_runs (
  evidence_consolidation_run_id TEXT PRIMARY KEY,
  frozen_baseline_id TEXT NOT NULL REFERENCES frozen_baselines(frozen_baseline_id),
  api_test_run_id TEXT NOT NULL REFERENCES api_test_runs(api_test_run_id),
  ui_test_run_id TEXT NOT NULL REFERENCES ui_test_runs(ui_test_run_id),
  policy_version TEXT NOT NULL,
  classifier_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('completed', 'failed')),
  result_count INTEGER NOT NULL,
  evidence_count INTEGER NOT NULL,
  failure_count INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(api_test_run_id, ui_test_run_id, policy_version, classifier_version)
);

CREATE TABLE consolidated_evidence_records (
  consolidated_evidence_id TEXT PRIMARY KEY,
  evidence_consolidation_run_id TEXT NOT NULL
    REFERENCES evidence_consolidation_runs(evidence_consolidation_run_id),
  source_executor TEXT NOT NULL CHECK(source_executor IN ('api', 'ui')),
  source_result_id TEXT NOT NULL,
  source_evidence_id TEXT NOT NULL,
  case_id TEXT NOT NULL,
  evidence_kind TEXT NOT NULL CHECK(evidence_kind IN ('api_exchange', 'screenshot', 'trace')),
  relative_path TEXT,
  content_hash TEXT NOT NULL,
  content_size INTEGER NOT NULL CHECK(content_size > 0),
  mime_type TEXT NOT NULL,
  redaction_status TEXT NOT NULL CHECK(redaction_status = 'verified'),
  integrity_status TEXT NOT NULL CHECK(integrity_status = 'verified'),
  retention_class TEXT NOT NULL CHECK(retention_class IN ('canonical', 'screenshot', 'trace')),
  expires_at TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(evidence_consolidation_run_id, source_evidence_id, evidence_kind)
);

CREATE TABLE deterministic_failure_classifications (
  failure_classification_id TEXT PRIMARY KEY,
  evidence_consolidation_run_id TEXT NOT NULL
    REFERENCES evidence_consolidation_runs(evidence_consolidation_run_id),
  source_executor TEXT NOT NULL CHECK(source_executor IN ('api', 'ui')),
  source_result_id TEXT NOT NULL,
  case_id TEXT NOT NULL,
  verdict TEXT NOT NULL CHECK(verdict IN ('PASS', 'FAIL', 'BLOCKED', 'ERROR', 'SKIPPED')),
  classification_code TEXT NOT NULL CHECK(classification_code IN (
    'none', 'seeded_product_bug', 'test_data_invalid', 'product_behavior_mismatch',
    'precondition_blocked', 'executor_error', 'skipped'
  )),
  suspected_bug_id TEXT,
  authoritative INTEGER NOT NULL CHECK(authoritative = 1),
  rule_version TEXT NOT NULL,
  facts_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(evidence_consolidation_run_id, source_executor, source_result_id)
);

CREATE TABLE advisory_ai_analyses (
  advisory_ai_analysis_id TEXT PRIMARY KEY,
  failure_classification_id TEXT NOT NULL
    REFERENCES deterministic_failure_classifications(failure_classification_id),
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  advisory_label TEXT NOT NULL CHECK(advisory_label = 'advisory_non_authoritative'),
  analysis_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE evidence_audit_events (
  evidence_audit_event_id TEXT PRIMARY KEY,
  evidence_consolidation_run_id TEXT NOT NULL
    REFERENCES evidence_consolidation_runs(evidence_consolidation_run_id),
  event_type TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_consolidated_evidence_result
  ON consolidated_evidence_records(source_executor, source_result_id);
CREATE INDEX ix_failure_classification_case
  ON deterministic_failure_classifications(case_id, verdict, classification_code);

CREATE TRIGGER evidence_consolidation_no_update BEFORE UPDATE ON evidence_consolidation_runs
BEGIN SELECT RAISE(ABORT, 'evidence consolidation runs are immutable'); END;
CREATE TRIGGER evidence_consolidation_no_delete BEFORE DELETE ON evidence_consolidation_runs
BEGIN SELECT RAISE(ABORT, 'evidence consolidation runs are immutable'); END;
CREATE TRIGGER consolidated_evidence_no_update BEFORE UPDATE ON consolidated_evidence_records
BEGIN SELECT RAISE(ABORT, 'consolidated evidence is immutable'); END;
CREATE TRIGGER consolidated_evidence_no_delete BEFORE DELETE ON consolidated_evidence_records
BEGIN SELECT RAISE(ABORT, 'consolidated evidence is immutable'); END;
CREATE TRIGGER failure_classification_no_update BEFORE UPDATE ON deterministic_failure_classifications
BEGIN SELECT RAISE(ABORT, 'failure classifications are immutable'); END;
CREATE TRIGGER failure_classification_no_delete BEFORE DELETE ON deterministic_failure_classifications
BEGIN SELECT RAISE(ABORT, 'failure classifications are immutable'); END;
CREATE TRIGGER advisory_analysis_no_update BEFORE UPDATE ON advisory_ai_analyses
BEGIN SELECT RAISE(ABORT, 'advisory analyses are immutable'); END;
CREATE TRIGGER advisory_analysis_no_delete BEFORE DELETE ON advisory_ai_analyses
BEGIN SELECT RAISE(ABORT, 'advisory analyses are immutable'); END;
CREATE TRIGGER evidence_audit_no_update BEFORE UPDATE ON evidence_audit_events
BEGIN SELECT RAISE(ABORT, 'evidence audit events are immutable'); END;
CREATE TRIGGER evidence_audit_no_delete BEFORE DELETE ON evidence_audit_events
BEGIN SELECT RAISE(ABORT, 'evidence audit events are immutable'); END;
