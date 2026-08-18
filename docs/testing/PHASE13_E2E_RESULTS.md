# Phase 13 End-to-End Results

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
