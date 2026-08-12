ALTER TABLE test_generation_runs ADD COLUMN recovery_reason TEXT;

CREATE TABLE test_generation_parsed_artifacts (
  test_generation_parsed_artifact_id TEXT PRIMARY KEY,
  test_generation_llm_call_id TEXT NOT NULL
    REFERENCES test_generation_llm_calls(test_generation_llm_call_id),
  parsed_json TEXT NOT NULL,
  parsed_hash TEXT NOT NULL,
  validation_status TEXT NOT NULL CHECK(validation_status IN ('parsed', 'valid', 'invalid')),
  failure_stage TEXT,
  failure_code TEXT,
  parser_version TEXT NOT NULL,
  redaction_version TEXT NOT NULL,
  artifact_origin TEXT NOT NULL CHECK(artifact_origin IN ('runtime', 'runtime_validation', 'offline_audit_backfill')),
  derived_from_failed_call INTEGER NOT NULL CHECK(derived_from_failed_call IN (0, 1)),
  original_call_id TEXT,
  original_failure_code TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  backfilled_at TEXT,
  UNIQUE(test_generation_llm_call_id, artifact_origin)
);

CREATE TABLE test_generation_call_validation_outcomes (
  test_generation_call_validation_outcome_id TEXT PRIMARY KEY,
  test_generation_llm_call_id TEXT NOT NULL
    REFERENCES test_generation_llm_calls(test_generation_llm_call_id),
  validation_status TEXT NOT NULL CHECK(validation_status IN ('valid', 'invalid')),
  failure_stage TEXT,
  failure_code TEXT,
  validator_version TEXT NOT NULL,
  outcome_origin TEXT NOT NULL CHECK(outcome_origin IN ('runtime', 'offline_audit_backfill')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(test_generation_llm_call_id, outcome_origin)
);

CREATE INDEX ix_test_generation_parsed_artifacts_call
  ON test_generation_parsed_artifacts(test_generation_llm_call_id, artifact_origin);
CREATE INDEX ix_test_generation_validation_outcomes_call
  ON test_generation_call_validation_outcomes(test_generation_llm_call_id, outcome_origin);

CREATE TRIGGER test_generation_parsed_artifacts_no_update
BEFORE UPDATE ON test_generation_parsed_artifacts
BEGIN SELECT RAISE(ABORT, 'test generation parsed artifacts are immutable'); END;
CREATE TRIGGER test_generation_parsed_artifacts_no_delete
BEFORE DELETE ON test_generation_parsed_artifacts
BEGIN SELECT RAISE(ABORT, 'test generation parsed artifacts are immutable'); END;
CREATE TRIGGER test_generation_call_outcomes_no_update
BEFORE UPDATE ON test_generation_call_validation_outcomes
BEGIN SELECT RAISE(ABORT, 'test generation call outcomes are immutable'); END;
CREATE TRIGGER test_generation_call_outcomes_no_delete
BEFORE DELETE ON test_generation_call_validation_outcomes
BEGIN SELECT RAISE(ABORT, 'test generation call outcomes are immutable'); END;
