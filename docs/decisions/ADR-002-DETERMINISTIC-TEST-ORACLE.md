# ADR-002: Deterministic Test Oracle

- Status: Accepted
- Date: 2026-07-18
- Decision owners: AI TestPilot project
- Scope: Test execution, classification, evidence, and reporting

## Context

Large language models are useful for interpreting ambiguous requirements, proposing cases, and summarizing complex evidence. Their outputs are probabilistic, sensitive to prompts/context, and can be incomplete or unsupported. Allowing a model to decide PASS/FAIL would make runs difficult to reproduce and audit and could hide the protected seeded defect.

## Decision

Authoritative test states are produced only by deterministic software operating on approved, versioned test snapshots. Supported states are `PASS`, `FAIL`, `BLOCKED`, `ERROR`, and `SKIPPED`.

Deterministic executors own HTTP requests, Playwright actions, variable extraction, status/header/JSON/DOM/URL assertions, precondition checks, timing, environment facts, failure-type rules, evidence persistence, statistics, and machine-readable results. AI cannot change those facts or states.

AI may draft requirements/cases, identify risk/ambiguity, and provide a separately attributed advisory analysis of already captured failures. Human review approves generated specifications and narrative artifacts where required.

## Rationale

- The same input, snapshot, environment, and facts lead to the same verdict.
- Assertion rules are versionable and testable.
- Reviewers can follow expected, actual, evidence, and rule without trusting model prose.
- Product failures remain distinct from environment blocks and executor errors.
- The seeded username defect cannot be explained away to make a dashboard green.
- Truthful deterministic evidence materially improves portfolio credibility.

## Consequences

### Positive

- Reproducible, auditable verdicts and metrics.
- Stable JUnit/JSON reporting and regression comparison.
- Clear responsibility between generation/analysis and execution.
- AI provider/model changes cannot silently change historical results.

### Trade-offs

- The protocol needs explicit action/assertion types and schema evolution.
- Novel cases sometimes require executor extensions and review rather than arbitrary code.
- Advisory AI conclusions may disagree with deterministic classification and must be presented separately.
- Evidence and environment capture require engineering effort.

## Oracle rules

- Required assertion mismatch is `FAIL`.
- Missing required environment/precondition is `BLOCKED`.
- Executor/framework/evidence-persistence malfunction is `ERROR`.
- Reviewed intentional non-execution is `SKIPPED`.
- Only executed cases with all required assertions satisfied and required evidence persisted are `PASS`.
- Task completion and file existence do not imply test PASS.

## AI analysis boundary

Advisory analysis receives redacted evidence summaries and returns schema-valid, provider-attributed content. It may suggest a suspected cause or next investigation but cannot execute code, alter a result, invent evidence, or create nonexistent trace relationships. Analysis failure leaves deterministic results intact.

## Validation

Later tests must cover every assertion/status rule, prove AI output cannot mutate results, reconcile reports to native result records, and reproduce the seeded defect through both API and UI deterministic checks. Phase 1 creates only configuration and policy, not an executor or result.
