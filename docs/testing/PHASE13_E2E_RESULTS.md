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
