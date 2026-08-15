# Phase 6 Review and Freeze Implementation

## Scope

Phase 6 turns a complete Phase 5B `validated_pending_review` collection into reviewed,
versioned, immutable execution input. It does not execute API, UI, or manual tests and it does not
produce verdicts, evidence, bugs, or reports.

## State flow

```text
validated_pending_review candidate
  -> append-only human review (approve | reject | request_changes)
  -> immutable approved case version (approve only)
  -> complete-collection freeze gate
  -> frozen baseline
  -> one immutable execution snapshot per approved case
```

Freezing is rejected unless every candidate in the collection has a latest `approve` decision and
an approved version. A rejection or change request therefore cannot be bypassed by partial
freezing.

## Integrity controls

- Review requests use optimistic concurrency through `expected_content_hash`.
- Candidate payload hashes are recomputed before a decision is persisted.
- Approved payloads are copied into immutable approved versions with their own hashes.
- Requirement links are copied into each snapshot and hashed independently.
- The baseline hash binds the Phase 5B collection hash, environment, protocol, executor contract,
  and the ordered approved member list.
- Every snapshot has a canonical SHA-256 hash and is validated against
  `execution-snapshot@1.0.0` before persistence.
- SQLite triggers reject updates and deletes for reviews, approved versions, frozen baselines,
  members, snapshots, and audit events.
- Baseline creation, all members, all snapshots, and the freeze audit event share one transaction.

## Versioned contracts

- Review workflow and request schemas: `test-case-review@1.0.0`
- Unified protocol: `unified-test-protocol@1.0.0`
- Execution snapshot: `execution-snapshot@1.0.0`

## HTTP boundary

- `GET /api/v1/test-generation-runs/{run_id}/reviews`
- `POST /api/v1/test-generation-runs/{run_id}/candidates/{case_id}/reviews`
- `POST /api/v1/test-generation-runs/{run_id}/frozen-baselines`
- `GET /api/v1/frozen-baselines/{baseline_id}`

The caller must supply a real reviewer identity. The service never invents a reviewer and never
automatically approves AI-generated content.

## Next-phase boundary

Phase 7 executors may consume only a schema-valid immutable snapshot from a frozen baseline. Phase
6 contains no HTTP executor, Playwright driver, deterministic verdict engine, or evidence writer.
