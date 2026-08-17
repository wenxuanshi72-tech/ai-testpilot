# Phase 8 Evidence and Classification Implementation

## Scope

Phase 8 consolidates the accepted Phase 7 API and UI execution evidence without changing the
executor verdicts. It verifies source hashes, artifact paths, redaction state, retention metadata,
and frozen-baseline context before persisting immutable evidence metadata.

The deterministic classifier is authoritative. It classifies the protected seeded defect as
`seeded_product_bug` linked to `BUG-AUTH-001`, distinguishes invalid test data from product
behavior mismatches, and preserves `PASS`, `BLOCKED`, `ERROR`, and `SKIPPED` semantics.

## Contracts

- Evidence policy: `evidence-policy@1.0.0`
- Failure classifier: `failure-classifier@1.0.0`
- Consolidated evidence schema: `consolidated-evidence@1.0.0`
- Advisory schema: `advisory-evidence-analysis@1.0.0`

Advisory AI analysis is optional, immutable, and explicitly non-authoritative. Phase 8 does not
authorize a real model call, and an advisory record cannot modify the persisted verdict or
classification.

## Security and retention

- Artifact paths must resolve under `artifacts/evidence` and cannot be symlinks.
- Canonical evidence, screenshots, and traces are re-hashed before consolidation.
- Redaction flags and sensitive frozen test-data values are verified.
- Canonical evidence is retained for 365 days, screenshots for 90 days, and traces for 30 days.
- Runtime artifacts, databases, logs, and secrets remain excluded from Git.

Phase 9 bug generation and Phase 10 report generation are intentionally not implemented here.
