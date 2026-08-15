# Plugin Test Review and Freeze Test Plan

## Objective

Verify that Phase 6 accepts only an intact Phase 5B collection, records attributable human
decisions, creates approved versions only for approvals, and freezes only a complete collection in
one transaction.

## Required checks

1. Migration 0006 creates only Phase 6 review, approval, baseline, snapshot, and audit entities.
2. Missing, incomplete, or hash-changed candidate collections are rejected.
3. `approve`, `reject`, and `request_changes` are attributable and append-only.
4. Reject and request-changes decisions do not create approved versions.
5. Stale candidate hashes cannot be approved.
6. Partial approval cannot be frozen.
7. Complete approval creates exactly one approved version and snapshot per candidate.
8. Requirement traces, collection hash, baseline hash, and snapshot hashes are preserved.
9. A repeated freeze request is idempotent.
10. Database triggers prevent review, approval, baseline, member, snapshot, and audit mutation.
11. API errors are deterministic and do not leak candidate or secret data.
12. No test executor, result, evidence, bug, or report record is created.

## Gates

- Plugin backend pytest
- Ruff format/check
- mypy
- migration from an empty database and upgrade from 0005
- SQLite `integrity_check` and `foreign_key_check`
- `git diff --check`
- sensitive-file and phase-boundary review
