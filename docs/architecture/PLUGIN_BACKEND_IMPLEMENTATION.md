# Plugin Backend Implementation

Status: Phase 5A accepted; audited real-provider result promoted by offline revalidation.

## Boundary

The Plugin backend is a Flask application under plugin/backend and owns only plugin.db. It never
imports the SUT backend or reads sut.db. Its current scope is project creation, PRD ingestion and
versioning, structured requirement analysis, validation, audit persistence, and requirement query.
Test generation, execution, bug creation, reporting, Plugin UI business features, and Phase 5B are
not implemented.

## Modules

- app/config.py reads non-secret configuration from process environment variables.
- app/database.py owns SQLAlchemy connections, foreign-key enforcement, migrations, and bounded
  repository operations.
- app/providers.py defines the provider protocol plus DeepSeekProvider and MockLLMProvider.
- app/prompts.py loads immutable prompt/recovery version 2 contracts and computes content hashes.
- app/source_blocks.py creates stable line-addressed source blocks and performs exact or uniquely
  reversible normalization checks without fuzzy matching.
- app/constraints.py deterministically parses same-requirement username minimum-length constraints
  from evidenced source excerpts and records a normalized field/operator/value/unit tuple.
- app/offline_revalidation.py revalidates saved real candidates without loading a provider and
  atomically promotes only a complete valid aggregate through an immutable zero-call attempt.
- app/schema_validation.py loads the local JSON Schema registry.
- app/analysis.py owns normalization, hashing, deterministic batching, parsing, truncation checks,
  retries, recovery, domain validation, aggregate validation, and atomic promotion.
- app/routes.py implements the Phase 5A API under /api/v1.
- real_acceptance.py performs the explicitly confirmed real-provider acceptance and emits only a
  redacted summary.

## Database and promotion

Migration 0001_initial.sql creates the analysis records. Additive migration
0002_source_reference_audit.sql links recovery attempts to immutable failed runs, stores source
blocks, redacted provider responses and parsed JSON, per-reference resolution audits, and explicit
outline/batch reuse links. Additive migration 0003_offline_revalidation.sql registers validator
versions and immutable offline attempts, candidate links, and aggregate constraint audits. Candidate
rows remain isolated until the complete aggregate is inserted into requirements in one transaction.

plugin.db is an ignored local runtime artifact. API keys, authorization headers, raw environment
dumps, request bodies, and reasoning content are never persisted. Provider response content is
retained locally after secret redaction, together with its hash and parsed candidate. The
pre-migration failed run has no recoverable response body; that absence is preserved.

## Reliability behavior

The pipeline normalizes and hashes the PRD, creates stable line-addressed source blocks, and
validates each response independently. Validation proves block existence, a unique continuous
excerpt in that block and the current PRD, strict Schema, domain rules, then aggregate rules. Empty
content, abnormal
finish reason, output near max_tokens, malformed or unclosed JSON, a false or missing completion
marker, count mismatch, schema failure, missing source excerpts, and invalid source sections block
the batch.

Transient provider failures retry only the current batch. Large truncated batches are divided into
two smaller source units. Terminal runs are immutable. Recovery creates a linked child attempt,
reuses the valid outline and deterministically revalidates prior valid batches without provider
calls. Real failures never switch to Mock. Aggregate checks enforce unique IDs, valid dependency
references, registration, login, current-user, logout, and the authoritative username minimum of
six characters. The minimum constraint is accepted only when one candidate's continuous evidenced
excerpt deterministically yields username / greater_than_or_equal / 6 / characters; descriptions
or text from other candidates cannot supply it.

## API

- GET /api/v1/health
- POST /api/v1/projects
- POST /api/v1/projects/{project_id}/prds
- POST /api/v1/prd-versions/{version_id}/analysis-runs
- GET /api/v1/analysis-runs/{analysis_run_id}
- GET /api/v1/analysis-runs/{analysis_run_id}/requirements
- GET /api/v1/projects/{project_id}/requirements

Analysis creation accepts provider_mode real or mock and an Idempotency-Key. Responses expose
provider provenance and request IDs but exclude secrets and stored provider response content.
