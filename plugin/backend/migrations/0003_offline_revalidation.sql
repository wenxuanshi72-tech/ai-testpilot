ALTER TABLE requirements ADD COLUMN offline_revalidation_attempt_id TEXT;

CREATE TABLE aggregate_validator_versions (
  validator_version TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  description TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE offline_revalidation_attempts (
  offline_revalidation_attempt_id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  parent_analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(analysis_run_id),
  source_analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(analysis_run_id),
  source_llm_call_id TEXT NOT NULL REFERENCES llm_call_logs(llm_call_id),
  old_validator_version TEXT NOT NULL,
  new_validator_version TEXT NOT NULL REFERENCES aggregate_validator_versions(validator_version),
  provider_status TEXT NOT NULL CHECK(provider_status = 'offline_revalidation_of_real_result'),
  status TEXT NOT NULL,
  candidate_count INTEGER NOT NULL,
  llm_call_count INTEGER NOT NULL CHECK(llm_call_count = 0),
  false_negative_reason TEXT NOT NULL,
  error_type TEXT,
  redacted_error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT
);

CREATE TABLE offline_revalidation_candidate_links (
  offline_revalidation_attempt_id TEXT NOT NULL
    REFERENCES offline_revalidation_attempts(offline_revalidation_attempt_id),
  candidate_id TEXT NOT NULL REFERENCES requirement_candidates(candidate_id),
  PRIMARY KEY(offline_revalidation_attempt_id, candidate_id)
);

CREATE TABLE aggregate_constraint_audits (
  aggregate_constraint_audit_id TEXT PRIMARY KEY,
  offline_revalidation_attempt_id TEXT NOT NULL
    REFERENCES offline_revalidation_attempts(offline_revalidation_attempt_id),
  requirement_id TEXT NOT NULL,
  source_block_id TEXT NOT NULL,
  source_excerpt_hash TEXT NOT NULL,
  normalized_input TEXT NOT NULL,
  normalized_result_json TEXT,
  validation_status TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER offline_revalidation_attempts_no_update_after_complete
BEFORE UPDATE ON offline_revalidation_attempts
WHEN OLD.status IN ('succeeded', 'failed')
BEGIN SELECT RAISE(ABORT, 'completed offline revalidation attempts are immutable'); END;
CREATE TRIGGER offline_revalidation_attempts_no_delete
BEFORE DELETE ON offline_revalidation_attempts
BEGIN SELECT RAISE(ABORT, 'offline revalidation attempts are immutable'); END;
CREATE TRIGGER offline_revalidation_candidate_links_no_update
BEFORE UPDATE ON offline_revalidation_candidate_links
BEGIN SELECT RAISE(ABORT, 'offline revalidation links are immutable'); END;
CREATE TRIGGER offline_revalidation_candidate_links_no_delete
BEFORE DELETE ON offline_revalidation_candidate_links
BEGIN SELECT RAISE(ABORT, 'offline revalidation links are immutable'); END;
CREATE TRIGGER aggregate_constraint_audits_no_update
BEFORE UPDATE ON aggregate_constraint_audits
BEGIN SELECT RAISE(ABORT, 'aggregate constraint audits are immutable'); END;
CREATE TRIGGER aggregate_constraint_audits_no_delete
BEFORE DELETE ON aggregate_constraint_audits
BEGIN SELECT RAISE(ABORT, 'aggregate constraint audits are immutable'); END;

INSERT INTO aggregate_validator_versions(validator_version, status, description)
VALUES (
  'aggregate-domain-validator@2.0.1',
  'active',
  'Deterministic same-requirement username minimum-length constraint parser'
);
