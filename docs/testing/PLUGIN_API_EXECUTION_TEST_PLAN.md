# Plugin API Execution Test Plan

## Acceptance target

Execute the seven API snapshots in frozen baseline
`FBL-5BCEA5DA11144E9BB47C545AD73919DD` against isolated real Flask SUT instances. Persist one
machine-readable result and one redacted evidence record per snapshot. The protected defect must be
`FAIL` with `suspected_product_bug`, expected status 400, and actual status 201.

## Gates

1. Validate baseline status, environment, contract, snapshot schema, and snapshot hash.
2. Verify clean-database and upgrade migrations through `0008`.
3. Exercise successful, negative, expired-session, logout, duplicate-registration, and seeded-defect
   API paths without network or LLM access.
4. Verify deterministic assertions, result Schema, evidence hashing/redaction, and immutable records.
5. Run Plugin backend tests with branch coverage of at least 85%, Ruff format/check, mypy, migration
   regression, `git diff --check`, SQLite integrity, and foreign-key checks.

An application failure does not make the executor acceptance fail when the persisted verdict and
evidence truthfully match the observed SUT behavior. Missing evidence, an executor error, invalid
snapshot, incorrect seeded-defect verdict, or database-integrity failure blocks Phase 7A.
