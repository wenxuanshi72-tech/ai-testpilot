# Phase 5B Test Plan

## Offline gates

1. Verify exactly 19 formal requirement snapshots and their aggregate hash.
2. Validate the API/UI/Manual v3 examples against `test-intent@2.5.0`.
3. Prove that the model cannot supply requirement, case/type, run/batch, state, version, timestamp, hash, link, or audit fields.
4. Reject missing, duplicate, unknown, and cross-batch generation slots.
5. Verify deterministic slot creation, primary requirement ownership, candidate/data/step IDs, draft state, and stable semantic hashes.
6. Validate every compiled candidate against strict `test-cases@1.5.0` and domain rules.
7. Verify protected API/UI cases for `REQ-BAT-002-6`, `z1234`, `Test1234`, rejection, and HTTP 400.
8. Verify aggregate coverage, duplicate/conflict detection, stable collection hash, atomic save, and database readback.
9. Verify one eligible same-batch correction, bounded Provider retry (3 per batch, 15 per run), no Real/Mock fallback, and shared call/cost reservation for all remaining initial batches.
10. Verify partial success never promotes candidates and exact compatible checkpoints alone may be reused.
11. Verify all five historical real FAIL runs, eleven calls, US$0.018991 cost, and zero candidates remain immutable.
12. Run Ruff, mypy, Python branch coverage, frontend formatting/lint/typecheck/Vitest/builds, Phase 3 regression, diff/secret scans, cleanup, and port checks.

## Next real acceptance plan (not authorized in this task)

- Initial batches: 17 (API 7, UI 6, Manual 4), covering 46 system-owned slots.
- Global limits: 18 calls, at most one correction for any failed batch and one correction total under current reservation, zero automatic provider retries.
- Maximum output: 3,072 tokens per call.
- New-cost hard cap: US$0.065000.
- Initial conservative worst cost: US$0.058922.
- One correction conservative worst total: US$0.062494.
- Capacity bounds: input 2,065/2,100; output 1,738/2,304.
- Any terminal failure stops later paid calls.

Phase 5B does not execute candidates and does not create review, APPROVED, FROZEN, baseline, snapshot, bug, or Phase 6 data.
