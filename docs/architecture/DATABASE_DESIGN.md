# Database Design

Status: logical design only. Phase 0 creates no database, migration, or model implementation.

## Storage boundary

The local release uses two independent SQLite databases:

- `sut.db`: owned exclusively by the SUT backend.
- `plugin.db`: owned exclusively by the plugin backend.

Neither application reads the other's tables. The plugin addresses the SUT through public APIs/UI and stores only environment and external-reference metadata. API keys, raw passwords, browser cookies, bearer tokens, and plaintext session tokens are forbidden in both databases.

## Common field principles

- Internal primary keys may be integer or UUID, but external/audit relationships use immutable, case-insensitive stable IDs with entity prefixes (for example `REQ-...`, `TC-...`, `RUN-...`).
- Timestamps are timezone-aware UTC ISO-8601 values in application contracts; databases store a consistently sortable UTC representation.
- Mutable aggregates use an integer `row_version` for optimistic concurrency.
- Domain revisions use explicit immutable `version`/`schema_version`; update-in-place is prohibited for approved requirements, cases, prompts, run snapshots, results, and evidence metadata.
- Enumerated state is constrained in the application and database where portable.
- Required audit fields are `created_at`, `created_by`, `updated_at`, and `updated_by`; automated actors use a service identity.
- Text lengths, uniqueness, nullability, indexes, and foreign-key behavior are explicit in migrations during implementation.

## SUT database

### `users`

Planned fields: internal ID, stable `user_id`, normalized unique `username`, display/original username if needed, `password_hash`, active status, created/updated timestamps, and concurrency version. Password hashing uses a framework-approved adaptive algorithm. Passwords and test confirmations are never stored.

The formal minimum username rule is six characters, but implementation phases must preserve the protected omission until the authorized regression fix.

### `sessions`

Planned fields: internal ID, stable `session_id`, `user_id` foreign key, one-way hash of a high-entropy opaque token, issued/last-seen/expires/revoked timestamps, revocation reason, and limited redacted client metadata if justified. Cookie values are never persisted. Expired/revoked sessions are denied and later purged.

Relationship: one user to many sessions, with restrictive deletion and explicit session revocation.

## Plugin database entities

| Entity | Stable ID / purpose | Key relationships and version/state fields |
|---|---|---|
| `projects` | `PRJ-*`; test workspace | active environment, lifecycle state, audit fields |
| `prd_documents` | `PRD-*`; immutable source revision | project; content hash, source version, media type, storage reference |
| `prompt_versions` | `PMT-*`; immutable prompt contract | use case, semantic version, hash, status (`draft/active/retired`) |
| `analysis_runs` | `ANR-*`; PRD analysis attempt | project, PRD, prompt/schema versions; provider mode; task state |
| `llm_call_logs` | `LLC-*`; one provider attempt | analysis/batch; provider/model, timing, tokens, finish/validation/error state |
| `requirements` | `REQ-*`; versioned structured requirement | analysis run, source spans; version, review status, risk/testability |
| `requirement_relationships` | `RRL-*`; typed requirement edge | source/target requirement versions, relation type, validity state |
| `test_cases` | `TC-*`; stable case identity | project, type, latest approved version pointer |
| `test_case_versions` | `TCV-*`; immutable protocol document | case, requirement links, schema version, review/approval state |
| `test_steps` | `TST-*`; ordered normalized step | case version, position, action type, structured payload |
| `test_runs` | `RUN-*`; execution snapshot | project/environment, approved case versions, task/status timestamps |
| `test_results` | `RES-*`; authoritative case outcome | run, case version; status, failure type, expected/actual, duration |
| `evidence` | `EVD-*`; immutable artifact metadata | result; kind, relative path, hash, size, redaction/retention state |
| `bug_records` | `BUG-*`; canonical local defect record | failed results, requirements, evidence; severity/priority/status/version |
| `report_records` | `RPT-*`; canonical report/export record | run(s), bug set, format, hash, generation status/version |
| `regression_links` | `RGL-*`; before/after comparison | bug, baseline result/run, regression result/run, outcome |

Additional normalized association tables are expected for requirement-to-case, result-to-evidence, bug-to-result/evidence, and report-to-run/bug many-to-many relationships. The implementation must not hide these links inside opaque JSON when they need referential queries.

## State model

Asynchronous work uses `queued`, `running`, `succeeded`, `failed`, and `cancelled`, with optional `retry_wait`; execution results separately use `PASS`, `FAIL`, `BLOCKED`, `ERROR`, and `SKIPPED`. Review uses `draft`, `in_review`, `approved`, `rejected`, and `superseded`. Provider mode is `real` or `mock`, never inferred from provider name.

States include timestamps and a machine-readable reason/error code. Terminal transitions are append-only or guarded by optimistic concurrency. A task's success cannot imply that its business payload was validated; validation and promotion states are separate.

## Relationships and trace query

The schema must answer this chain without parsing narrative text:

`Project -> PRD revision -> Analysis Run -> Requirement version -> Test Case Version -> Test Run -> Test Result -> Evidence -> Bug -> Regression Result`.

Foreign keys protect intra-database relationships. Cross-file relationships include both evidence ID and relative path/hash. Supersession edges preserve history. A trace scan reports orphaned required nodes and stale downstream versions.

## Deletion and retention

Projects and mutable catalog objects use soft deletion (`deleted_at`, `deleted_by`) only where recovery is useful. Immutable audit records—provider calls, approved versions, runs, results, evidence metadata, bugs, reports, regression links—are not silently soft-deleted; retention transitions mark them expired/purged with an audit event.

Raw provider responses and high-volume logs have the shortest configurable retention. Screenshots/traces and generated exports use size and age limits. Canonical metadata and trace links are retained longer. Purging a file preserves its hash, type, original size, purge timestamp, and reason so lineage remains explainable.

## Sensitive-data exclusions

Never store API keys, `.env` content, plaintext passwords, password confirmations, plaintext session tokens, complete `Authorization`/`Cookie` headers, unredacted request bodies, unnecessary personal data, or provider credentials. Redacted summaries should be minimized; hashes must not be used as a pretext to retain secrets.

## SQLite-to-PostgreSQL boundary

Domain and repository ports avoid SQLite-specific query semantics. Use SQLAlchemy-supported types, explicit UTC handling, portable constraints, deterministic ordering, and migration-managed schemas. Do not depend on SQLite's permissive typing, disabled foreign keys, connection-global state, or JSON behavior for core invariants.

PostgreSQL migration may add native UUID/JSONB, stronger constraints, row locking, concurrent workers, and indexes, but stable IDs, domain versions, statuses, trace semantics, and exported formats remain compatible. Migration rehearsal must reconcile row counts, IDs, hashes, and trace completeness.
