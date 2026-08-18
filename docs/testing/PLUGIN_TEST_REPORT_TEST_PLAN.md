# Plugin Canonical Test Report Test Plan

## Acceptance checks

1. Require completed API, UI, evidence-consolidation, and canonical-Bug sources from one trace.
2. Preserve all persisted `PASS`, `FAIL`, `BLOCKED`, `ERROR`, and `SKIPPED` values verbatim.
3. Produce one canonical summary and use it for JSON, Markdown, HTML, PDF, and Manifest.
4. Verify result, classification, Bug, and evidence counts across every format.
5. Recompute every output and evidence SHA-256 hash against the Manifest.
6. Validate HTML escaping, semantic structure, keyboard focus, table labels, and relative links.
7. Extract PDF text, render every PDF page to PNG, and inspect for clipping, overlap, missing pages,
   unreadable text, or corrupt characters.
8. Prove idempotency, immutable persistence, sensitive-data rejection, and honest export failure.
9. Run migrations, focused tests, full backend/repository tests, Ruff, mypy, SQLite integrity,
   foreign keys, Git diff, ignored-runtime, and sensitive-content checks.

The seeded defect remains open. No new execution or regression run is authorized.
