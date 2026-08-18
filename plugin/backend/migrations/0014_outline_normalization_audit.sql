CREATE TABLE analysis_outline_normalization_audits (
  analysis_outline_normalization_audit_id TEXT PRIMARY KEY,
  llm_call_id TEXT NOT NULL,
  section_index INTEGER NOT NULL CHECK (section_index >= 0),
  original_section_id TEXT NOT NULL,
  normalized_section_id TEXT NOT NULL,
  reason TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (llm_call_id) REFERENCES llm_call_logs(llm_call_id)
);

CREATE INDEX idx_outline_normalization_call
  ON analysis_outline_normalization_audits(llm_call_id, section_index);

CREATE TRIGGER outline_normalization_audit_no_update
BEFORE UPDATE ON analysis_outline_normalization_audits
BEGIN SELECT RAISE(ABORT, 'analysis outline normalization audits are immutable'); END;

CREATE TRIGGER outline_normalization_audit_no_delete
BEFORE DELETE ON analysis_outline_normalization_audits
BEGIN SELECT RAISE(ABORT, 'analysis outline normalization audits are immutable'); END;
