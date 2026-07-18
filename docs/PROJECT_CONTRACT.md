# AI TestPilot Project Contract

Status: Phase 0 approved design baseline
Scope: contracts and architecture only; no implementation claim

## Positioning and target users

AI TestPilot is a local-first, portfolio-grade testing workbench that demonstrates an auditable AI-assisted quality lifecycle against a purpose-built authentication SUT. It is intended for QA engineers, SDETs, full-stack engineers, test leads, and reviewers assessing practical AI application engineering.

The product addresses a common gap in AI testing demos: generated prose is often disconnected from executable assertions, real evidence, deterministic verdicts, and regression traceability. AI TestPilot instead makes AI a constrained drafting and analysis component inside a reproducible engineering system.

## Goals

1. Build a React/Flask login and registration SUT with a deliberately protected validation defect.
2. Import Markdown or plain-text PRDs and derive versioned structured requirements through a real provider.
3. Generate, review, freeze, and execute unified API and UI test specifications.
4. Produce verdicts through deterministic assertions, never model opinion.
5. Preserve a redacted, hashable evidence chain from source requirement through regression.
6. Generate local Markdown/JSON bug files and HTML/Markdown/PDF reports from validated results.
7. Deliver a repeatable local demonstration with professional, accessible, moderately game-inspired presentation.

## Non-goals for the first release

- Enterprise identity, email verification, password recovery, social login, or complex authorization.
- Autonomous model control of a browser, test verdicts, or production changes.
- Jira, GitHub Issues, chat, or other external defect-system integration.
- Mandatory cloud deployment, distributed execution, or production multi-tenancy.
- Silent real-to-mock provider fallback or synthetic evidence represented as real.

## MVP scope

The SUT contains registration, login, current-user lookup, logout, authentication protection, a 404 experience, SQLite user/session persistence, and health checks. The plugin contains project creation; PRD ingestion; real-model structured analysis; requirement risk and testability views; API/UI case generation and review; deterministic API/Playwright execution; evidence collection; failure classification and AI-assisted explanation; local bug files; reports; traceability; and post-fix regression.

Server-side opaque sessions are the selected authentication direction. The browser receives an `HttpOnly`, `SameSite=Lax` cookie; only a hash of the opaque session token is stored. Production-like local settings add `Secure` where HTTPS is available. This avoids browser token storage while keeping revocation explicit.

## Final target and success definition

Success is a live, repeatable local workflow that imports the sample PRD, calls a clearly identified real provider, yields schema-valid requirements and reviewed tests, executes real HTTP and browser checks, reliably exposes `BUG-AUTH-001`, stores redacted evidence, produces traceable bug/report artifacts, then passes the same checks after an explicitly authorized fix. Success also requires documented failure behavior, no fabricated outputs, no leaked secrets, and usable keyboard-accessible interfaces.

Online deployment is an optional Phase 15 challenge and cannot substitute for the local closed loop.

## Protected seeded-defect contract

`REQ-AUTH-USERNAME-001` requires usernames of at least six characters. Until the regression-fix phase, the SUT intentionally accepts `z1234` / `Test1234`; `POST /api/auth/register` incorrectly returns `201` and persists the user. The expected result is a validation rejection that states the six-character minimum.

The defect must remain observable by `TC-API-AUTH-REG-005` and `TC-UI-AUTH-REG-005`, and later become `BUG-AUTH-001`. Do not fix it early, weaken its tests, alter the requirement, hide the response, or classify the deterministic failure as test-script error.

## AI responsibility boundary

AI may summarize PRDs, propose requirement decomposition, identify ambiguity and risk, draft test cases, explain already-captured failures, and draft bug/report narratives. AI output is untrusted candidate content until schema and domain validation plus required human review succeed.

Deterministic software sends requests, drives Playwright, performs assertions, assigns execution status, records timing, saves evidence, computes metrics, maintains trace relationships, and emits machine-readable results. The model never assigns the authoritative pass/fail verdict.

## Local-first and provider principles

- DeepSeek is the first planned real provider behind a replaceable interface.
- Real and mock modes are explicit and permanently attributable.
- Keys come only from environment variables and are always redacted.
- A real-provider failure remains a recorded failure; it never silently becomes a mock success.
- Long PRDs use outline-first, bounded batches, per-batch validation, resumable retries, deterministic merge/deduplication, and aggregate completeness checks.

## Risk register

| ID | Risk | Consequence | Primary control | Gate |
|---|---|---|---|---|
| RSK-001 | Model output truncation | Missing or malformed requirements | Token budget, bounded batches, finish-reason and closure checks | 5A |
| RSK-002 | Mock/real confusion | False product claims | Explicit mode, immutable provenance, no fallback | 5A |
| RSK-003 | Flaky UI automation | Untrustworthy verdicts | Stable locators, controlled waits, trace evidence | 7B |
| RSK-004 | Secret or personal-data leakage | Security/privacy breach | Environment-only keys and layered redaction | Every phase |
| RSK-005 | Evidence/record drift | Broken audit chain | Stable IDs, hashes, immutable execution snapshots | 8 |
| RSK-006 | Premature seeded-defect repair | Demo cannot prove detection | Protected IDs, acceptance checks, phase gate | 3 through 11 |
| RSK-007 | AI verdict authority | Non-reproducible results | Deterministic assertion engine | 6 onward |
| RSK-008 | Scope creep | Incomplete core loop | Phase-specific allowlists and acceptance | Every phase |
| RSK-009 | Local resource pressure | Failed repeatability | Size/retention limits and bounded concurrency | 13 |
| RSK-010 | Visual novelty harms usability | Poor professional utility | Accessibility and information-first review | 12 |

## Change control

Architecture decisions, schemas, prompt versions, status semantics, IDs, and phase gates are versioned. A change proposal records rationale, alternatives, compatibility effect, migration or replay impact, test impact, and approving reviewer. Breaking protocol changes require a new major schema version; historical execution snapshots remain immutable.

No change may retrospectively rewrite evidence or provider provenance. Corrections are appended as new versions or linked superseding records.

## Phase gates

- Phase 0: all contract documents are complete, consistent, secret-safe, committed on `feat/project-contract`, and the tree is clean.
- Phases 1-4: foundations and SUT must pass their own tests while the seeded defect remains demonstrably present.
- Phase 5A must pass real-provider and structured-output acceptance before 5B.
- Phase 6 must freeze an approved executable protocol before any execution engine claims.
- API execution must pass before the automation loop is described as complete; UI execution must pass before browser automation is claimed.
- Formal bug/report generation requires persisted evidence.
- Online deployment is blocked until the local end-to-end and regression loop passes.

Passing a gate authorizes planning of the next phase only. It does not authorize implementation outside the next explicit instruction.
