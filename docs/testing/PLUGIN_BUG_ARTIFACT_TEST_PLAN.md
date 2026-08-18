# Plugin Local Bug Artifact Test Plan

## Required checks

1. Generate a canonical Bug only from authoritative product-Bug `FAIL` classifications.
2. Require frozen approved case versions, requirements, source results, and verified evidence.
3. Exclude `PASS` and `test_data_invalid` results from the product Bug.
4. Verify evidence files and canonical API evidence against persisted SHA-256 hashes.
5. Generate JSON and Markdown from one canonical record and validate the JSON Schema.
6. Generate and independently verify a bundle manifest.
7. Verify idempotency, immutable database records, relative attachment links, and secret redaction.
8. Prove an export failure leaves no completed Bug or bundle record.
9. Run migration, full backend, repository Python, Ruff, mypy, SQLite, foreign-key, Git-diff, and
   sensitive-content gates.

External Bug connectors, DeepSeek calls, seeded-defect repair, and Phase 10 are prohibited.
