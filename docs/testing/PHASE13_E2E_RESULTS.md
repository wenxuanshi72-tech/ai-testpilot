# Phase 13 End-to-End Results

## Portfolio MVP acceptance

**Result: PASS for the explicitly reduced portfolio MVP scope.** This is an evidence replay over
accepted real components, not a claim that the experimental 44-candidate collection regenerated.

The read-only verifier `scripts/verify_phase13_portfolio_mvp.py` produced the following evidence:

| Gate                      | Result                                                                                               |
| ------------------------- | ---------------------------------------------------------------------------------------------------- |
| Real Provider analysis    | `ANR-8D946E45913A418F899774282E8121C2`; DeepSeek Real; `deepseek-v4-pro`; 3 successful content calls |
| Structured Requirements   | 19                                                                                                   |
| Frozen execution input    | `FBL-5BCEA5DA11144E9BB47C545AD73919DD`; 10 immutable snapshots                                       |
| Pre-fix API Run           | `RUN-71ED569CD73643E5B19F48BCFCD0FBEF`                                                               |
| Pre-fix UI Run            | `UIR-7169E1697F86400EBAE8AFBBBD5675B4`                                                               |
| Canonical Bug             | `BUG-AUTH-001`; `BUGR-B4E714D0B26843EF912A65B224ACFC32`                                              |
| Canonical report          | `RPT-BE5D133ABFB54EF2A4AFEFC82D86A189`                                                               |
| Regression                | `RGR-5B1FD386A93B49658A7D3927B7F7C65A`                                                               |
| Seeded API transition     | `TC-API-AUTH-REG-005`: `FAIL→PASS`                                                                   |
| Seeded UI transition      | `TC-UI-AUTH-REG-005`: `FAIL→PASS`                                                                    |
| Effective Bug status      | `closed`, through append-only `open→closed` event                                                    |
| Hash verification         | snapshots, Bug, report, and regression trace PASS                                                    |
| SQLite                    | both databases `integrity_check=ok`; foreign-key violations 0                                        |
| New Provider calls / Runs | 0 / 0                                                                                                |

The accepted portfolio claim is therefore limited and precise: a real Provider produced the
structured Requirements, while the already reviewed and frozen ten-case MVP baseline supplied the
real deterministic execution, evidence, Bug/report, authorized fix, and regression chain. The
historical Sessions below remain FAIL and demonstrate bounded handling of unstable model output.
They were not relabelled, deleted, or used as a source of newly promoted Candidates.

### Final quality gates

- Portfolio verifier tests: 2 passed.
- Plugin backend: 319 passed, 1 deselected.
- Ruff format/check: PASS for Plugin, SUT, and scripts.
- mypy: 76 source files, PASS.
- SUT frontend Vitest: 27 passed.
- Plugin frontend Vitest: 12 passed.
- SUT and Plugin ESLint: PASS.
- SUT and Plugin TypeScript production builds: PASS. Both report advisory bundle-size warnings;
  neither build failed.
- Prettier: PASS for all Phase 13 files. The repository-wide check still identifies historical
  formatting debt outside this change set; those files were intentionally not rewritten.
- Sensitive/runtime files: `.env`, databases, `tmp/`, logs, screenshots, traces, and generated
  report bundles are absent from the change set.
- Ports 5001, 5173, 5002, and 5174: no listener remained after validation.

## Envelope recovery `E2E-20260824T152510Z`

Recovery Run `TGR-BCDAE28E315D46058E5ED9C8D830D1C6` revalidated nine checkpoints and
stopped at UI-002. Its initial HTTP 200 response used a JSON object where scalar `test_data.value`
allows only a string or `null`. The one bounded correction also returned HTTP 200, but emitted four
intents for three slots and repeated `GSL-UI-5CEAAD4B97E39AE2`; deterministic envelope validation
rejected it as `GENERATION_SLOT_DUPLICATE`. The two calls used 2,672 input and 3,549 output tokens
and cost US$0.004250. No Candidate collection was promoted.

The correction contract now states the exact expected count and requires every ID already listed in
the supplied immutable `slots_json` exactly once, with no missing, extra, or duplicate ID. The slot
list remains present verbatim in the user message rather than duplicated in the system message, so
the valid 44-slot/18-batch capacity plan and existing checkpoint boundaries remain unchanged.
Saved invalid responses remain rejected. Read-only recovery planning still reuses API-001 through
API-008 and UI-001, and schedules UI-002 through UI-006 plus four Manual batches: nine initial
calls, at most eight corrections, and at most seventeen content calls.

## UI recovery `E2E-20260824T141003Z`

Recovery Run `TGR-439D29BEC8684353823C26EF1B407569` reused API-001 through API-004,
validated API-005 through API-008 and UI-001, then stopped at UI-002. Eight successful HTTP calls
used 10,308 input and 8,739 output tokens and cost US$0.011424. The initial and corrected UI-002
responses each consumed one call; no Candidate collection was promoted.

Offline replay established that `fill:label:Username` is already the formal three-part executor
grammar: the last segment names the control, while the approved executor obtains its input from
`test_data` through a deterministic label mapping. The actual contract defects were `navigate`
instead of `goto`, generic `Submit` instead of the route's real accessible button name, and a
remaining `role=Content` locator that does not identify any React button. Compatibility `1.31.0`
maps only the first two unambiguous aliases and keeps `Content` rejected. Consequently UI-002 is
not a reusable checkpoint. Current read-only recovery planning revalidates API-001 through API-008
and UI-001, and requires Provider generation for UI-002 through UI-006 and Manual-001 through
Manual-004: nine initial content calls, at most eight corrections, and at most seventeen content
calls. The failed Session, Run, calls, cost, responses, and database remain unchanged.

## Generation recovery `E2E-20260824T132802Z`

The unique authorized recovery reused Analysis Run
`ANR-8D946E45913A418F899774282E8121C2` and created Test Generation Run
`TGR-241BCA9DF8544A8BB554A9B9B2694A26`. API-001 through API-004 validated; API-005 stopped the
run after its initial response and one same-batch correction both returned HTTP 200 with
`finish_reason=stop` but failed the Intent Schema. Eight content calls used 11,783 input and 10,156
output tokens and cost US$0.012636. No network retry, Candidate, requirement link, approval, or
baseline was created.

The corrected response wrapped two safe CORS configuration prerequisites as exact
`type=config`/`description` objects. Compatibility `1.30.0` deterministically retains their complete
descriptions as declarative preconditions, never executor actions. Strict replay also found a third
`type=setup` object describing a natural-language database prerequisite. That object is outside the
approved mapping and remains rejected; the saved API-005 checkpoint therefore cannot be promoted.
The next recovery may reuse API-001 through API-004, while API-005 and all ungenerated batches
require normal Provider generation. The failed Session, calls, cost, and artifacts remain immutable.

## Dynamic generation-plan offline remediation

The second isolated Analysis Run `ANR-8D946E45913A418F899774282E8121C2` and its 19 formal
Requirements remain immutable. A read-only replay derives 44 unique slots in 18 capacity-valid
batches: 19 API, 15 UI, and 10 Manual slots, grouped as 8 API, 6 UI, and 4 Manual batches.

The historical 46-slot/17-batch plan is retained as reference evidence only. Phase 13 now validates
complete Requirement/type coverage, unique slots, exact batch coverage without omission, token and
authorization bounds, and deterministic seeded-defect API/UI guards. Numeric Requirement-ID
segments are compared after removing leading zeroes, so `REQ-BAT-002-006` has the same comparison
identity as `REQ-BAT-002-6`; storage and traceability retain the original ID. Any identity collision
is rejected, and the formal username-minimum source constraint must also match.

The replay performed zero Provider calls and created zero Analysis Runs, Test Generation Runs, or
Candidates. The second database SHA-256 remained
`ed06689a56ab227f92dabe2a34869e09be4f0c447d57aa746ce46a4831d7fb2c`. A future recovery uses a
copy of this database, names the second Session as its manifest parent, and creates a new Test
Generation Run whose source analysis remains `ANR-8D946E45913A418F899774282E8121C2`; it never
rewrites the failed source Session.

Status: FAIL — stopped at the real PRD outline Schema gate

The authorized isolated run started on 2026-08-18 and stopped at its first mandatory validation
failure. It did not retry, fall back to Mock, start test generation, launch services, execute tests,
or enter Phase 14.

## Recorded result

- Session: `E2E-20260818T064345Z`
- Analysis run: `ANR-3FFB8BCFB5AF4F5B909080930B956ECB`
- Provider/model/mode: DeepSeek / `deepseek-v4-pro` / Real
- Prompt/Schema: `prd-analysis@2.0.0` / `requirements@2.0.0`
- HTTP status and finish reason: `200` / `stop`
- Calls: 1 outline call; 761 input tokens and 248 output tokens
- Calculated incremental cost: US$0.000547
- Failure: `SCHEMA_VALIDATION:sections/0/section_id:pattern`
- Formal requirements: 0
- Test-generation calls and candidates: 0 / 0
- SQLite integrity: `ok`; foreign-key violations: 0

The model returned a complete response, but the first outline section identifier did not satisfy
the versioned Schema pattern. The workflow correctly treated model output as untrusted candidate
data and stopped before promotion. Runtime databases and the pre-run backup remain under the
ignored session directory for diagnosis.

Phase 13 is not a PASS. Phase 14 has not started and remains blocked. Any correction or new paid
attempt requires a separate instruction; this failed run and its audit evidence must remain
unchanged.

## Offline remediation

The failure was replayed without a Provider call. The stored outline contained the unique IDs
`1`, `2`, `3`, `4`, `5`, and `6`; the unchanged Schema requires
`^SEC-[A-Za-z0-9_-]{1,64}$`. The deterministic normalizer maps this exact class of bare positive
integers to `SEC-001` through `SEC-006`, rejects empty, ambiguous, duplicate, and colliding values,
and validates the transformed object against the full `requirements@2.0.0` Schema. The original
response remains the authoritative raw artifact while normalized values and immutable conversion
audits provide provenance.

Offline replay passed Schema validation and formed two requirement-batch plans with zero Provider
calls, zero new runs, and zero formal requirements. The failed database SHA-256 remained
`fda9f713d5a270a06155090fe5047086ca5d437a260f393d183bc48d2133d623`; its status, one-call
history, US$0.000547 cost evidence, and zero requirements were unchanged. This remediation does not
authorize another paid attempt.
