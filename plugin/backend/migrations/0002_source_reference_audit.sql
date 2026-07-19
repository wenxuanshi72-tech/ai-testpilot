ALTER TABLE analysis_runs ADD COLUMN parent_analysis_run_id TEXT REFERENCES analysis_runs(analysis_run_id);
ALTER TABLE analysis_batches ADD COLUMN source_blocks_json TEXT;

CREATE TABLE llm_response_artifacts (
  llm_call_id TEXT PRIMARY KEY REFERENCES llm_call_logs(llm_call_id),
  response_content TEXT NOT NULL,
  response_hash TEXT NOT NULL,
  parsed_json TEXT,
  redaction_applied INTEGER NOT NULL CHECK(redaction_applied IN (0, 1)),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE source_reference_audits (
  source_reference_audit_id TEXT PRIMARY KEY,
  analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(analysis_run_id),
  analysis_batch_id TEXT NOT NULL REFERENCES analysis_batches(analysis_batch_id),
  llm_call_id TEXT REFERENCES llm_call_logs(llm_call_id),
  requirement_id TEXT,
  source_block_id TEXT,
  model_excerpt TEXT NOT NULL,
  resolved_excerpt TEXT,
  resolution_type TEXT NOT NULL,
  reason TEXT NOT NULL,
  block_start_line INTEGER,
  block_end_line INTEGER,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE analysis_reuse_links (
  analysis_reuse_link_id TEXT PRIMARY KEY,
  analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(analysis_run_id),
  source_analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(analysis_run_id),
  artifact_type TEXT NOT NULL,
  source_entity_id TEXT NOT NULL,
  target_entity_id TEXT,
  content_hash TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(analysis_run_id, artifact_type, source_entity_id)
);

CREATE TRIGGER llm_call_logs_no_update
BEFORE UPDATE ON llm_call_logs BEGIN SELECT RAISE(ABORT, 'llm_call_logs are immutable'); END;
CREATE TRIGGER llm_call_logs_no_delete
BEFORE DELETE ON llm_call_logs BEGIN SELECT RAISE(ABORT, 'llm_call_logs are immutable'); END;
CREATE TRIGGER llm_response_artifacts_no_update
BEFORE UPDATE ON llm_response_artifacts BEGIN SELECT RAISE(ABORT, 'llm responses are immutable'); END;
CREATE TRIGGER llm_response_artifacts_no_delete
BEFORE DELETE ON llm_response_artifacts BEGIN SELECT RAISE(ABORT, 'llm responses are immutable'); END;
CREATE TRIGGER source_reference_audits_no_update
BEFORE UPDATE ON source_reference_audits BEGIN SELECT RAISE(ABORT, 'source audits are immutable'); END;
CREATE TRIGGER source_reference_audits_no_delete
BEFORE DELETE ON source_reference_audits BEGIN SELECT RAISE(ABORT, 'source audits are immutable'); END;
CREATE TRIGGER analysis_reuse_links_no_update
BEFORE UPDATE ON analysis_reuse_links BEGIN SELECT RAISE(ABORT, 'reuse links are immutable'); END;
CREATE TRIGGER analysis_reuse_links_no_delete
BEFORE DELETE ON analysis_reuse_links BEGIN SELECT RAISE(ABORT, 'reuse links are immutable'); END;
