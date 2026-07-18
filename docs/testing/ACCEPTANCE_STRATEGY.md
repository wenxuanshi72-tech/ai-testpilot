# Acceptance Strategy

Status: Phase 0 test and gate design. No implementation, provider call, automated run, evidence, bug, or report is claimed by this document.

## Acceptance principles

Acceptance is based on reproducible deterministic checks and preserved evidence, not file presence, model confidence, screenshots of static pages, or narrative claims. AI may draft inputs and explain failures but cannot decide authoritative state. A phase with any unmet mandatory gate does not advance; deleting tests, weakening assertions, changing requirements to fit defects, or relabelling failures cannot manufacture a pass.

Local end-to-end operation is the primary release target. Online deployment is a later optional gate.

## Authoritative states

| State | Definition |
|---|---|
| `PASS` | Execution occurred and every required deterministic assertion passed with required evidence |
| `FAIL` | Execution occurred and one or more product-facing deterministic assertions mismatched expected behavior |
| `BLOCKED` | A required precondition/environment/data/authorization is unavailable, so intended assertions cannot execute |
| `ERROR` | Test framework, executor, provider pipeline, evidence persistence, or unexpected infrastructure failed |
| `SKIPPED` | A reviewed policy/selection intentionally excluded execution; reason is recorded |

Environment failures are not product failures. Task `succeeded` is not test `PASS`. AI analysis and `severity_hint` never change status. Status assignment rules are versioned and tested.

## Test pyramid

The broad base is fast deterministic unit, schema, domain, redaction, and prompt-fixture tests. The middle contains database/repository, provider-adapter contract, Flask/API, evidence/export, and component integration tests. The narrower top contains real API/Playwright flows, a small real-provider acceptance set, report rendering, regression, and one repeatable local end-to-end demonstration.

Counts are driven by risk and contracts, not a cosmetic ratio. Critical boundaries—security, traceability, schema promotion, and seeded-defect detection—receive tests at multiple levels.

## Layer acceptance

### Unit tests

Cover domain state machines, stable IDs, normalization/deduplication, token/batch planning, truncation signals, deterministic repairs, assertions/classification, redaction, path containment, hashing/manifests, trace metrics, and status mapping. They are isolated, deterministic, and do not use network, clock, randomness, or filesystem without controlled adapters.

### Schema tests

Validate accepted and rejected fixtures for requirements, cases, LLM batches, results, evidence, bugs, reports, and exports. Test required fields, unknown properties, enums, size/depth/count boundaries, compatible versions, unsupported majors, references, and malicious payloads. Schema success is followed by domain validation; it is not sufficient alone.

### Database tests

Against isolated temporary SUT/plugin databases, prove migrations, constraints, unique/stable IDs, foreign keys, status transitions, immutable approved/run records, optimistic concurrency, rollback, cleanup, and trace queries. Confirm databases remain separate and secret fields cannot be persisted by supported paths.

### Integration tests

Exercise application services through real repositories/adapters where practical: upload-to-candidate promotion, case review/freeze, run orchestration, evidence atomic persistence, bug/report eligibility, export validation, and recovery checkpoints. External provider/browser behavior may use explicit fakes at this layer, labelled as such.

### SUT API tests

Execute real HTTP requests against a running local SUT for health, registration, duplicate/invalid input, login, `/me`, logout, session expiry/revocation, CSRF/CORS/error contracts, and 404 behavior. Validate status, headers/cookies, JSON, database effects through approved test seams, and redacted evidence. Pre-fix, the formal username-minimum case must fail for the product mismatch.

### Plugin API tests

Exercise project, PRD/version, analysis task, requirement, generation, review/freeze, run/result, evidence, bug, report, and regression endpoints. Validate pagination, filters, idempotency, optimistic concurrency, async state, error envelope, project isolation, authorization, redaction, target allowlists, and artifact eligibility.

### Playwright UI tests

Use Playwright for Python against real local frontends/backends. Cover keyboard-accessible registration/login/session/logout/404; plugin primary flow; review/freeze; run monitoring; evidence/bug/report navigation; loading/empty/error states; responsive layouts; and critical accessibility checks. Use `data-testid`, role, label, or placeholder; avoid fragile generated classes and arbitrary sleeps. Capture screenshot/trace on required failures under redaction/retention policy.

API and UI tests must both actually execute. Static pages, unit-only tests, or mocked network screenshots do not prove the closed loop.

## Prompt and provider acceptance

### Prompt regression

Versioned, de-identified PRD fixtures evaluate structure, required-rule extraction, ambiguity/risk, source references, batch limits, duplicate handling, and adversarial prompt-injection content. Deterministic schema/domain/reference metrics form the gate; exact prose equality is avoided. Golden changes require review and rationale.

### Mock Provider boundary

Mock proves orchestration, parsing, retries, faults, and stable regression only. Every mock record is labelled. Mock cannot satisfy real DeepSeek connectivity, token metadata, finish-reason, latency, or output-quality acceptance and cannot be shown as a real result.

### Real DeepSeek Provider

With explicit later authorization and environment key, run a small controlled suite through the real adapter. Verify provider/model/mode/prompt/schema/request IDs, status, timing, tokens/finish reason where supplied, redaction, schema/domain validity, and honest error behavior. No real-to-mock fallback is allowed. Costs and retries are bounded.

### Truncation and recovery

Inject/observe length finish reasons, near-max token usage, incomplete JSON, closed-but-incomplete lists, missing fields/references, timeouts, `429`, `5xx`, and interruption. Prove quarantine, limited deterministic repair, failed-batch-only retry, exponential backoff, idempotent resume, retention of passed batches, retry exhaustion, aggregate completeness, and prohibition on partial promotion. Phase 5A must pass before 5B.

## Protected seeded-defect acceptance

`REQ-AUTH-USERNAME-001` requires username length at least six. Before the authorized fix:

- real API case `TC-API-AUTH-REG-005` submits `z1234` / `Test1234`, expects validation rejection, observes erroneous `201` creation, and deterministically yields `FAIL` with product-bug classification/evidence;
- real UI case `TC-UI-AUTH-REG-005` expects an accessible minimum-length error but observes erroneous registration, yielding the corresponding deterministic `FAIL` with screenshot/trace evidence.

The defect must be stable, not hidden or fixed early. `BUG-AUTH-001` is eligible only after those real results and evidence exist. During the authorized regression fix, rerun the same approved case versions (or explicitly reviewed compatible versions) and preserve baseline evidence. Both checks plus guardrails must pass before closure.

These are future acceptance expectations, not Phase 0 results.

## Evidence acceptance

For each finalized result, validate required evidence by type/state: stable IDs and links, relative safe path, existing complete file where applicable, supported MIME, nonzero/bounded size, SHA-256 match, creation time, source/environment metadata, redaction state, and retention policy. API failures require request/response summaries and status; UI failures require URL/browser context and configured screenshot/trace. Evidence persistence failure makes the operation `ERROR` and blocks formal artifacts.

## Bug artifact acceptance

Canonical JSON and Markdown must reconcile on bug ID/title, requirement/case/result/evidence links, severity/priority, environment, preconditions, steps, expected/actual, advisory AI statement, timestamps, and status. Validate schema, readable rendering, relative evidence links, redaction, hashes/manifest, and local-only behavior. File existence without eligible failed result/evidence is invalid.

## Report acceptance

HTML, Markdown, and PDF derive from one canonical finalized run set. Reconcile totals/statuses/durations, environment/provider mode, included bugs, evidence and trace links, caveats, and schema/artifact versions. Validate HTML accessibility/escaping, PDF page rendering/clipping/contrast, manifest hashes, and secret scanning. No real execution means no formal report; a static sample must be unmistakably labelled.

## Traceability acceptance

Validate the chain from PRD version through regression with correct entity versions and project ownership. Calculate requirement/API/UI coverage, trace completeness, evidence completeness, orphan count, invalid-reference count, and stale-edge count with explicit denominators. Critical formal chains require 100% mandatory links; unresolved orphan/invalid links block artifact acceptance.

## Regression acceptance

Regression uses an immutable baseline, linked fix authorization/change, equivalent environment, same approved test versions unless reviewed, new real execution/evidence, and deterministic comparison. It preserves the original failure, checks nearby authentication guardrails, distinguishes blocked/error from fail, and updates bug status only through an audited transition.

## Local end-to-end demonstration

From a documented clean local setup: start SUT/plugin frontends/backends; import the sample PRD; execute real DeepSeek analysis; validate/review requirements and generated API/UI cases; freeze versions; run real API and Playwright tests; expose the seeded defect; persist evidence; produce local bug and HTML/Markdown/PDF report; display traceability; apply the authorized fix; and run regression. Record commands/configuration (without secrets), versions, timing, IDs, results, and artifact manifests. Repeatability on a fresh local environment is required.

## Optional online deployment acceptance

Only after the local loop passes and separate authorization exists, test HTTPS/security headers, identity/authorization/tenant isolation, managed secrets, CSRF/CORS, upload and egress/SSRF controls, isolated browsers, persistence/migrations/backups, concurrency, rate/cost limits, monitoring, retention/deletion, rollback, and local-mode preservation. Hosted availability does not compensate for a broken local loop.

## Phase gates and evidence truthfulness

- Every phase lists mandatory checks and allowed paths before implementation.
- A mandatory `FAIL`, `BLOCKED`, or `ERROR` blocks advancement until resolved and the complete phase gate reruns; an approved nonmandatory `SKIPPED` needs a reason.
- Never delete a test, lower an assertion, enlarge tolerance, alter the requirement, fabricate evidence, or reclassify a product failure to obtain PASS.
- Files and documentation prove design/packaging only; they do not prove working behavior.
- Formal bugs require real failed results and evidence. Formal reports require real finalized runs.
- Results, screenshots, traces, model calls, and metrics are never fabricated.

Phase 0 passes only when its 16 required files are complete and consistent, contain no implementation claims/secrets/runtime artifacts, are committed on `feat/project-contract` with the required message, and the working tree is clean. Passing Phase 0 does not itself authorize Phase 1 work.
