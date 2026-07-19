CREATE TABLE projects (
  project_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('active', 'archived')),
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE prd_documents (
  prd_document_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id),
  title TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(project_id, title)
);
CREATE TABLE prd_versions (
  version_id TEXT PRIMARY KEY,
  prd_document_id TEXT NOT NULL REFERENCES prd_documents(prd_document_id),
  version_number INTEGER NOT NULL,
  content TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  media_type TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(prd_document_id, version_number)
);
CREATE TABLE prompt_versions (
  prompt_version_id TEXT PRIMARY KEY,
  semantic_version TEXT NOT NULL UNIQUE,
  content_hash TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE analysis_runs (
  analysis_run_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL REFERENCES projects(project_id),
  prd_version_id TEXT NOT NULL REFERENCES prd_versions(version_id),
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  provider_mode TEXT NOT NULL CHECK(provider_mode IN ('real', 'mock')),
  prompt_version TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  status TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  validation_status TEXT NOT NULL DEFAULT 'pending',
  error_type TEXT,
  redacted_error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT
);
CREATE TABLE analysis_batches (
  analysis_batch_id TEXT PRIMARY KEY,
  analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(analysis_run_id),
  batch_index INTEGER NOT NULL,
  source_section TEXT NOT NULL,
  source_text TEXT NOT NULL,
  input_hash TEXT NOT NULL,
  status TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  reported_count INTEGER,
  actual_count INTEGER,
  finish_reason TEXT,
  validation_status TEXT NOT NULL DEFAULT 'pending',
  error_type TEXT,
  redacted_error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  completed_at TEXT,
  UNIQUE(analysis_run_id, input_hash)
);
CREATE TABLE llm_call_logs (
  llm_call_id TEXT PRIMARY KEY,
  analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(analysis_run_id),
  analysis_batch_id TEXT REFERENCES analysis_batches(analysis_batch_id),
  call_type TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  provider_mode TEXT NOT NULL CHECK(provider_mode IN ('real', 'mock')),
  provider_request_id TEXT,
  prompt_version TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  retry_count INTEGER NOT NULL,
  http_status INTEGER,
  finish_reason TEXT,
  input_tokens INTEGER,
  output_tokens INTEGER,
  max_tokens INTEGER NOT NULL,
  latency_ms INTEGER NOT NULL,
  validation_status TEXT NOT NULL,
  error_type TEXT,
  redacted_error TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE requirement_candidates (
  candidate_id TEXT PRIMARY KEY,
  analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(analysis_run_id),
  analysis_batch_id TEXT NOT NULL REFERENCES analysis_batches(analysis_batch_id),
  requirement_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  validation_status TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(analysis_run_id, requirement_id)
);
CREATE TABLE requirements (
  row_id TEXT PRIMARY KEY,
  requirement_id TEXT NOT NULL,
  project_id TEXT NOT NULL REFERENCES projects(project_id),
  prd_version_id TEXT NOT NULL REFERENCES prd_versions(version_id),
  analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(analysis_run_id),
  version_number INTEGER NOT NULL DEFAULT 1,
  title TEXT NOT NULL,
  description TEXT NOT NULL,
  requirement_type TEXT NOT NULL,
  source_section TEXT NOT NULL,
  source_excerpt TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'candidate',
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(analysis_run_id, requirement_id)
);
CREATE TABLE requirement_relationships (
  relationship_id TEXT PRIMARY KEY,
  analysis_run_id TEXT NOT NULL REFERENCES analysis_runs(analysis_run_id),
  source_requirement_id TEXT NOT NULL,
  target_requirement_id TEXT NOT NULL,
  relationship_type TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(analysis_run_id, source_requirement_id, target_requirement_id, relationship_type)
);
CREATE INDEX ix_prd_versions_document ON prd_versions(prd_document_id);
CREATE INDEX ix_analysis_runs_project ON analysis_runs(project_id);
CREATE INDEX ix_analysis_batches_run ON analysis_batches(analysis_run_id, batch_index);
CREATE INDEX ix_llm_call_logs_run ON llm_call_logs(analysis_run_id);
CREATE INDEX ix_requirements_project ON requirements(project_id, requirement_id);
