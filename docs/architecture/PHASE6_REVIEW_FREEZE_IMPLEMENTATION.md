# Phase 6 Review and Freeze Implementation

## Scope

Phase 6 treats all 46 Phase 5B candidates as test-design evidence, classifies every candidate as
`automated`, `manual`, or `deferred`, and freezes only an approved 8–12 case portfolio MVP subset.
It does not claim that every AI draft is automatable and does not execute tests or produce results.

## State flow

```text
validated_pending_review candidate
  -> deterministic executability preflight
  -> append-only human review and automation disposition
  -> optional immutable human-authored revision
  -> immutable approved version for approve + automated only
  -> all-candidates-classified MVP subset gate
  -> frozen 8-12 case baseline
  -> one immutable execution snapshot per approved automated case
```

Freezing is rejected unless all 46 candidates have an attributable latest classification, every
automated candidate is approved and executable, the subset contains 8–12 cases, and both seeded
defect API/UI cases are included. Manual and deferred cases never become execution snapshots.

## Integrity controls

- Review requests use optimistic concurrency through `expected_content_hash`.
- Approval requires `candidate-executability@1.0.0`: implemented API/UI targets, structured
  setup/cleanup and UI actions, deterministic session fixtures, consistent objective/oracle/status,
  marked sensitive test data, and the protected seeded-defect oracle. A failed preflight remains
  reviewable only through `request_changes` or `reject`.
- `expired_session` and `revoked_session` compile to enumerated authenticated-session fixtures;
  arbitrary database prose and `N/A` placeholders are never executable snapshot actions.
- Every execution snapshot uses `fresh_database_per_run` and `discard_run_database`; the executor
  never executes model-authored SQL or natural-language database cleanup.
- Human revisions are append-only, preserve candidate identity/type/trace, and require fresh schema
  and executability validation before automated approval.
- Candidate payload hashes are recomputed before a decision is persisted.
- Approved payloads are copied into immutable approved versions with their own hashes.
- A candidate may have multiple immutable approved versions, each bound one-to-one to its review.
  Approval rejects stale revisions and duplicate candidate/revision content, assigns a version above
  all historical versions, and freeze selects only the approved version bound to the latest review.
- Requirement links are copied into each snapshot and hashed independently.
- The baseline hash binds the Phase 5B collection hash, environment, protocol, executor contract,
  and the ordered approved member list.
- Every snapshot has a canonical SHA-256 hash and is validated against
  `execution-snapshot@1.0.0` before persistence.
- SQLite triggers reject updates and deletes for reviews, approved versions, frozen baselines,
  members, snapshots, and audit events.
- Baseline creation, all members, all snapshots, and the freeze audit event share one transaction.

## Versioned contracts

- Review workflow and request schemas: `test-case-review@2.0.0`
- MVP policy: `portfolio-mvp-baseline@1.0.0`
- Unified protocol: `unified-test-protocol@1.0.0`
- Execution snapshot: `execution-snapshot@1.0.0`

## HTTP boundary

- `GET /api/v1/test-generation-runs/{run_id}/reviews`
- `GET /api/v1/test-generation-runs/{run_id}/executability`
- `GET /api/v1/test-generation-runs/{run_id}/mvp-classification-plan`
- `POST /api/v1/test-generation-runs/{run_id}/candidates/{case_id}/human-revisions`
- `POST /api/v1/test-generation-runs/{run_id}/candidates/{case_id}/reviews`
- `POST /api/v1/test-generation-runs/{run_id}/frozen-baselines`
- `GET /api/v1/frozen-baselines/{baseline_id}`

The caller must supply a real reviewer identity. The service never invents a reviewer and never
automatically approves AI-generated content.

The same executability validator is applied when current generation assets revalidate a historical
checkpoint, before aggregate promotion, and at approval. A reviewed collection with append-only
`request_changes` decisions may be used as a recovery source, but only checkpoints that pass the
current complete generation and executability chain can be reused.

## Next-phase boundary

Phase 7 executors may consume only a schema-valid immutable snapshot from a frozen baseline. Phase
6 contains no HTTP executor, Playwright driver, deterministic verdict engine, or evidence writer.
