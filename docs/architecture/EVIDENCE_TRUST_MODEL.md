# Evidence Trust Model

Status: Authenticity hardening Step 1 contract. This document defines future evidence eligibility; it does
not upgrade historical Runs or claim that the contracts are already implemented.

## Purpose

AI TestPilot cannot prove truth by asserting that AI output is honest. It instead limits formal
claims to facts produced by deterministic executors and makes those facts independently
recheckable. A screenshot, database row, narrative report, or SHA-256 value on its own is not proof
of execution origin. Hashes prove only that bytes have not changed since the recorded digest was
created.

The trusted chain is:

```text
approved frozen snapshot
→ allowlisted deterministic executor
→ real HTTP or Playwright operation
→ action tape and raw evidence
→ deterministic assertion and Result
→ immutable Run manifest
→ deterministic reproduction
→ independent bundle verification
→ canonical Bug and Report
```

AI may propose test intent and provide clearly labelled advisory analysis. AI does not assign the
authoritative test verdict, evidence-integrity state, reproduction state, or trust level.

## Threats and non-goals

| Threat | Required control |
| --- | --- |
| A static screenshot is presented as execution evidence | Link it to Result, Action Tape sequence, Trace, manifest entry, byte size, and digest |
| JSON/database state is edited after execution | Immutable records, canonical serialization, per-file digest, bundle digest, append-only audit |
| A file digest is generated for fabricated content | Require executor provenance, frozen input, raw evidence, deterministic assertions, and reproduction |
| AI narrative changes a verdict | Store AI output only as non-authoritative advisory data |
| A Trace or screenshot belongs to another Run/case | Enforce Run, Result, snapshot, case/version, environment, and project ownership links |
| Secrets leak into evidence | Structured redaction, post-write scanning, restricted artifacts, and fail-closed export |
| An unsafe model action is executed | Execute only versioned protocol actions and fixtures; never execute model-authored SQL, shell, code, or paths |
| A partial artifact directory looks complete | Stage, validate, hash, and atomically promote a complete bundle |
| Historical evidence is retroactively upgraded | New contracts apply only to new Runs; historical records retain their original capabilities/status |

This portfolio contract does not attempt hardware attestation, a public transparency ledger, or a
claim that a machine owner cannot fabricate all local inputs. Optional CI attestation may later add
third-party timestamps, but local reproducibility remains the primary boundary.

## Trust states

### `UNVERIFIED`

One or more mandatory execution facts are absent or invalid. Examples include an AI-only claim, a
static sample, a screenshot without source Result, a missing file, a digest mismatch, an unsupported
executor, or an incomplete trace. `UNVERIFIED` content may be displayed for diagnosis but cannot
qualify a formal Bug or accepted test report.

### `EXECUTED`

A versioned deterministic executor consumed an immutable approved snapshot and persisted a valid
Result plus the evidence required for its executor type. Result status remains one of `PASS`,
`FAIL`, `BLOCKED`, `ERROR`, or `SKIPPED`. `EXECUTED` does not imply the failure is independently
reproduced.

Minimum gates:

- immutable snapshot ID/hash and case ID/version match;
- executor and protocol versions are supported;
- environment and source commit are recorded;
- action/request tape is complete and ordered;
- deterministic assertions own the verdict;
- required evidence files exist, are redacted, and match their manifest digests;
- Run Bundle is complete and atomically finalized.

### `VERIFIED`

`VERIFIED` is a stronger evidence state, not a synonym for `PASS`. It requires every `EXECUTED`
gate plus:

- an independent reproduction Run consumes the same approved case version and oracle;
- reproduction has its own Result, evidence, Action Tape, and manifest;
- the claimed behavior is observed again or the explicit `NOT_REPRODUCED` state is retained;
- source and reproduction manifests independently validate;
- all mandatory PRD → Requirement → snapshot → Result → Evidence → Bug/Report links resolve;
- a standalone verifier recomputes the complete bundle without trusting stored status labels.

A Bug may display `verification_status=verified` only when reproduction status is `REPRODUCED`.
An accepted regression closure uses new evidence but never overwrites the original verified failure.

## Authority matrix

| Fact | Authority |
| --- | --- |
| HTTP/browser operation | API or Playwright executor |
| PASS/FAIL/BLOCKED/ERROR/SKIPPED | Deterministic assertions and execution policy |
| Screenshot/Trace/network/console bytes | Executor evidence adapters |
| File integrity | Independent digest calculation against finalized manifest |
| Bug reproduction status | Deterministic reproduction runner |
| Severity explanation or suggested cause | Advisory AI or named human reviewer |
| Approval/freeze | Named human review plus deterministic eligibility gates |
| Trust state | Versioned trust-policy evaluator, never model output |

## Evidence requirements by executor

API execution requires a structured request/response exchange, redacted headers/body summary,
status, assertions, correlation/request ID where supported, timing, Action Tape, and manifest.
Portfolio formal acceptance uses a real local HTTP service; Flask Test Client remains suitable for
lower-level tests but must be labelled as in-process execution.

UI execution requires the resolved locator/action sequence, page/route transitions, assertion facts,
network observations, final or failure screenshot, Playwright Trace with snapshots, browser and
viewport metadata, Action Tape, and manifest. Console/page errors are required when captured by the
configured evidence policy. Missing mandatory evidence changes finalization to `ERROR`; it does not
silently downgrade the evidence requirement.

## Historical compatibility

Existing Phase 7–13 Runs remain truthful evidence under their recorded schema and executor versions.
They are not rewritten as `VERIFIED` merely because this contract now exists. The first Run eligible
for the new state must be created after the bundle, Action Tape, reproduction, and independent
verification implementations are accepted.

## Phase boundary

This step defines documentation and JSON contracts only. Browser tracing, Action Tape writers,
Artifact Bundle persistence, reproduction generators, verification services, UI views, migrations,
and new runtime evidence belong to later authenticity steps.
