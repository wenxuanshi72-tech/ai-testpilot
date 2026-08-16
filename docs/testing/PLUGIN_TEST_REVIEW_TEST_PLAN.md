# Plugin Test Review and Freeze Test Plan

## Objective

Verify that Phase 6 preserves all 46 drafts as review evidence, records attributable classifications
and human revisions, and freezes only an approved executable 8–12 case MVP subset atomically.

## Required checks

1. Migration 0006 creates only Phase 6 review, approval, baseline, snapshot, and audit entities.
2. Missing, incomplete, or hash-changed candidate collections are rejected.
3. `approve`, `reject`, and `request_changes` are attributable and append-only.
4. Reject and request-changes decisions do not create approved versions.
5. Stale candidate hashes cannot be approved.
6. Missing candidate classifications cannot be frozen.
7. Only `approve + automated` creates an approved version and execution snapshot.
8. Requirement traces, collection hash, baseline hash, and snapshot hashes are preserved.
9. A repeated freeze request is idempotent.
10. Database triggers prevent review, approval, baseline, member, snapshot, and audit mutation.
11. API errors are deterministic and do not leak candidate or secret data.
12. No test executor, result, evidence, bug, or report record is created.
13. Approval rejects `N/A`, natural-language execution operations, nonexistent API/UI targets,
    unusable UI locators/actions, unmarked sensitive data, and objective/oracle/status conflicts.
14. Expired and revoked sessions compile only to enumerated deterministic fixtures.
15. A later `request_changes` decision is append-only and supersedes an earlier approval for the
    latest-decision freeze gate without deleting either record.
16. All 46 candidates can be preflighted in one read-only report before approval.
17. Checkpoint dry-run and runtime reuse apply the same current executability validator; ordinary
    incompatibility falls back to Provider generation and cannot be promoted.
18. The deterministic offline plan classifies 46 candidates as 10 automated, 12 manual, and 24
    deferred for the sample portfolio collection.
19. Manual and deferred candidates never enter an execution snapshot.
20. The automated subset contains 8–12 cases and both seeded defect cases.
21. Human revisions preserve original candidates and immutable trace fields.
22. Invalid human revisions cannot be approved for automation.
23. Snapshot isolation is `fresh_database_per_run` with `discard_run_database`; no arbitrary SQL,
    shell, code, or model-authored cleanup is executed.
24. Upgrade from 0006 preserves an immutable v1 approval, permits an executable human revision to
    create v2, and freezes exactly one snapshot for the case using v2.
25. Duplicate approvals, stale revisions, wrong hashes, and non-executable revisions are rejected.

## Gates

- Plugin backend pytest
- Ruff format/check
- mypy
- migrations 0001 through 0007 and upgrades from 0003 and 0006
- SQLite `integrity_check` and `foreign_key_check`
- `git diff --check`
- sensitive-file and phase-boundary review
