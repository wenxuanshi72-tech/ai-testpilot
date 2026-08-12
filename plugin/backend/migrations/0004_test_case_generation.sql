CREATE TABLE test_generation_runs (
  test_generation_run_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id),
  prd_version_id TEXT NOT NULL REFERENCES prd_versions(version_id),
  source_analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(analysis_run_id),
  resume_source_run_id TEXT REFERENCES test_generation_runs(test_generation_run_id),
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  provider_mode TEXT NOT NULL CHECK(provider_mode IN ('real', 'mock')),
  prompt_version TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  requirement_snapshot_hash TEXT NOT NULL,
  plan_json TEXT NOT NULL,
  plan_hash TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN (
    'pending', 'running', 'blocked', 'failed', 'validated_pending_review'
  )),
  validation_status TEXT NOT NULL DEFAULT 'pending',
  collection_version INTEGER,
  collection_hash TEXT,
  candidate_count INTEGER NOT NULL DEFAULT 0,
  pricing_provider TEXT,
  pricing_model TEXT,
  pricing_version TEXT,
  pricing_checked_at TEXT,
  input_cache_hit_rate_usd_per_million TEXT,
  input_cache_miss_rate_usd_per_million TEXT,
  output_rate_usd_per_million TEXT,
  estimated_cost_microusd INTEGER NOT NULL DEFAULT 0 CHECK(estimated_cost_microusd >= 0),
  actual_cost_microusd INTEGER NOT NULL DEFAULT 0 CHECK(actual_cost_microusd >= 0),
  currency TEXT NOT NULL DEFAULT 'USD' CHECK(currency = 'USD'),
  cost_calculation_version TEXT,
  calculation_assumption TEXT,
  error_type TEXT,
  redacted_error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT
);

CREATE TABLE test_generation_batches (
  test_generation_batch_id TEXT PRIMARY KEY,
  test_generation_run_id TEXT NOT NULL
    REFERENCES test_generation_runs(test_generation_run_id),
  batch_key TEXT NOT NULL,
  batch_index INTEGER NOT NULL,
  case_type TEXT NOT NULL CHECK(case_type IN ('api', 'ui', 'manual')),
  requirement_ids_json TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  max_cases INTEGER NOT NULL CHECK(max_cases BETWEEN 1 AND 25),
  max_tokens INTEGER NOT NULL CHECK(max_tokens BETWEEN 256 AND 8192),
  status TEXT NOT NULL CHECK(status IN ('pending', 'running', 'validated', 'failed')),
  retry_count INTEGER NOT NULL DEFAULT 0,
  reported_count INTEGER,
  actual_count INTEGER,
  finish_reason TEXT,
  validation_status TEXT NOT NULL DEFAULT 'pending',
  error_type TEXT,
  redacted_error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT,
  UNIQUE(test_generation_run_id, batch_key),
  UNIQUE(test_generation_run_id, batch_index)
);

CREATE TABLE test_generation_llm_calls (
  test_generation_llm_call_id TEXT PRIMARY KEY,
  test_generation_run_id TEXT NOT NULL
    REFERENCES test_generation_runs(test_generation_run_id),
  test_generation_batch_id TEXT NOT NULL
    REFERENCES test_generation_batches(test_generation_batch_id),
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  provider_mode TEXT NOT NULL CHECK(provider_mode IN ('real', 'mock')),
  provider_request_id TEXT,
  prompt_version TEXT NOT NULL,
  prompt_hash TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  retry_count INTEGER NOT NULL,
  http_status INTEGER,
  finish_reason TEXT,
  input_tokens INTEGER,
  input_cache_hit_tokens INTEGER,
  input_cache_miss_tokens INTEGER,
  output_tokens INTEGER,
  pricing_provider TEXT,
  pricing_model TEXT,
  pricing_version TEXT,
  pricing_checked_at TEXT,
  input_cache_hit_rate_usd_per_million TEXT,
  input_cache_miss_rate_usd_per_million TEXT,
  output_rate_usd_per_million TEXT,
  estimated_cost_microusd INTEGER NOT NULL DEFAULT 0 CHECK(estimated_cost_microusd >= 0),
  actual_cost_microusd INTEGER NOT NULL DEFAULT 0 CHECK(actual_cost_microusd >= 0),
  currency TEXT NOT NULL DEFAULT 'USD' CHECK(currency = 'USD'),
  cost_calculation_version TEXT,
  calculation_assumption TEXT,
  max_tokens INTEGER NOT NULL,
  latency_ms INTEGER NOT NULL,
  validation_status TEXT NOT NULL,
  error_type TEXT,
  redacted_error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE test_generation_response_artifacts (
  test_generation_llm_call_id TEXT PRIMARY KEY
    REFERENCES test_generation_llm_calls(test_generation_llm_call_id),
  response_content TEXT NOT NULL,
  response_hash TEXT NOT NULL,
  parsed_json TEXT,
  redaction_applied INTEGER NOT NULL CHECK(redaction_applied IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE test_case_candidates (
  test_case_candidate_id TEXT PRIMARY KEY,
  test_generation_run_id TEXT NOT NULL
    REFERENCES test_generation_runs(test_generation_run_id),
  test_generation_batch_id TEXT NOT NULL
    REFERENCES test_generation_batches(test_generation_batch_id),
  case_id TEXT NOT NULL,
  case_version INTEGER NOT NULL DEFAULT 1,
  case_type TEXT NOT NULL CHECK(case_type IN ('api', 'ui', 'manual')),
  payload_json TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  lifecycle_status TEXT NOT NULL CHECK(lifecycle_status = 'validated_pending_review'),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(test_generation_run_id, case_id, case_version)
);

CREATE TABLE test_case_candidate_requirement_links (
  test_case_candidate_requirement_link_id TEXT PRIMARY KEY,
  test_case_candidate_id TEXT NOT NULL REFERENCES test_case_candidates(test_case_candidate_id),
  requirement_id TEXT NOT NULL,
  requirement_version INTEGER NOT NULL,
  requirement_snapshot_hash TEXT NOT NULL,
  source_block_id TEXT NOT NULL,
  link_type TEXT NOT NULL CHECK(link_type IN (
    'verifies', 'guards', 'explores', 'negative_boundary'
  )),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(test_case_candidate_id, requirement_id, link_type)
);

CREATE TABLE test_case_validation_results (
  test_case_validation_result_id TEXT PRIMARY KEY,
  test_generation_run_id TEXT NOT NULL
    REFERENCES test_generation_runs(test_generation_run_id),
  test_case_candidate_id TEXT REFERENCES test_case_candidates(test_case_candidate_id),
  scope TEXT NOT NULL CHECK(scope IN ('batch', 'candidate', 'aggregate')),
  validator_version TEXT NOT NULL,
  rule_code TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('passed', 'failed', 'review_warning')),
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE test_case_coverage_results (
  test_case_coverage_result_id TEXT PRIMARY KEY,
  test_generation_run_id TEXT NOT NULL
    REFERENCES test_generation_runs(test_generation_run_id),
  requirement_id TEXT,
  dimension TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('covered', 'gap', 'not_applicable')),
  case_ids_json TEXT NOT NULL,
  rationale TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE test_case_generation_audit_events (
  test_case_generation_audit_event_id TEXT PRIMARY KEY,
  test_generation_run_id TEXT NOT NULL
    REFERENCES test_generation_runs(test_generation_run_id),
  test_generation_batch_id TEXT REFERENCES test_generation_batches(test_generation_batch_id),
  event_type TEXT NOT NULL,
  event_status TEXT NOT NULL,
  details_json TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX ix_test_generation_runs_project
  ON test_generation_runs(project_id, created_at);
CREATE INDEX ix_test_generation_batches_run
  ON test_generation_batches(test_generation_run_id, batch_index);
CREATE INDEX ix_test_case_candidates_run
  ON test_case_candidates(test_generation_run_id, case_type, case_id);
CREATE INDEX ix_test_case_candidate_links_requirement
  ON test_case_candidate_requirement_links(requirement_id);

CREATE TRIGGER test_generation_llm_calls_no_update
BEFORE UPDATE ON test_generation_llm_calls
BEGIN SELECT RAISE(ABORT, 'test generation LLM calls are immutable'); END;
CREATE TRIGGER test_generation_llm_calls_no_delete
BEFORE DELETE ON test_generation_llm_calls
BEGIN SELECT RAISE(ABORT, 'test generation LLM calls are immutable'); END;
CREATE TRIGGER test_generation_responses_no_update
BEFORE UPDATE ON test_generation_response_artifacts
BEGIN SELECT RAISE(ABORT, 'test generation responses are immutable'); END;
CREATE TRIGGER test_generation_responses_no_delete
BEFORE DELETE ON test_generation_response_artifacts
BEGIN SELECT RAISE(ABORT, 'test generation responses are immutable'); END;
CREATE TRIGGER test_case_candidates_no_update
BEFORE UPDATE ON test_case_candidates
BEGIN SELECT RAISE(ABORT, 'test case candidates are immutable'); END;
CREATE TRIGGER test_case_candidates_no_delete
BEFORE DELETE ON test_case_candidates
BEGIN SELECT RAISE(ABORT, 'test case candidates are immutable'); END;
CREATE TRIGGER test_case_candidate_links_no_update
BEFORE UPDATE ON test_case_candidate_requirement_links
BEGIN SELECT RAISE(ABORT, 'test case candidate links are immutable'); END;
CREATE TRIGGER test_case_candidate_links_no_delete
BEFORE DELETE ON test_case_candidate_requirement_links
BEGIN SELECT RAISE(ABORT, 'test case candidate links are immutable'); END;
CREATE TRIGGER test_generation_runs_terminal_no_update
BEFORE UPDATE ON test_generation_runs
WHEN OLD.status IN ('blocked', 'failed', 'validated_pending_review')
BEGIN SELECT RAISE(ABORT, 'terminal test generation runs are immutable'); END;
CREATE TRIGGER test_generation_runs_no_delete
BEFORE DELETE ON test_generation_runs
BEGIN SELECT RAISE(ABORT, 'test generation runs are immutable'); END;
