# Phase 13 End-to-End Results

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
