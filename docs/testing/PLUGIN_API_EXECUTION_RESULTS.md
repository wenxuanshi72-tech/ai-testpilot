# Plugin API Execution Results

## Result

Phase 7A API executor acceptance: **PASS**.

The accepted verification run is `RUN-71ED569CD73643E5B19F48BCFCD0FBEF`, consuming frozen baseline
`FBL-5BCEA5DA11144E9BB47C545AD73919DD` in `local-windows-demo` with
`api-executor@1.0.0`. Seven API snapshots produced seven immutable results and seven hashed,
redacted API evidence records.

| Case | Verdict | Expected | Actual | Classification |
|---|---:|---:|---:|---|
| `TC-API-AUTH-REG-005` | FAIL | 400 | 201 | `suspected_product_bug` |
| `TC-API-REQ-AUTH-001` | PASS | 401 | 401 | none |
| `TC-API-REQ-BAT-002-5` | PASS | 401 | 401 | none |
| `TC-API-REQ-LOGIN-001` | PASS | 401 | 401 | none |
| `TC-API-REQ-LOGOUT-001` | PASS | 204 | 204 | none |
| `TC-API-REQ-REG-003` | FAIL | 201 | 400 | `product_behavior_mismatch` |
| `TC-API-REQ-REG-004` | PASS | 409 | 409 | none |

The registration-success candidate failed because its frozen test password does not satisfy the
SUT password policy. This is retained as a truthful candidate/test-data finding; neither the frozen
snapshot nor SUT was modified to manufacture a pass. The protected defect reproduced exactly:
username `z1234` was expected to be rejected with 400 but the defective SUT returned 201.

## Quality evidence

- Plugin backend: 248 passed, 1 deselected; branch coverage 86.73%.
- Phase 7A targeted suite after the 204-response correction: 6 passed.
- Ruff format/check: PASS.
- mypy (Plugin backend): PASS across 59 source files.
- SQLite `integrity_check`: `ok`.
- Foreign-key violations: 0.
- Evidence count and SHA-256 recomputation: 7/7 valid.
- DeepSeek/model calls: 0.
- Seeded SUT defect fixes: 0.

An earlier immutable executor-development run,
`RUN-334FF74CE1D24519848C0D5B4A0D030A`, is retained. It exposed an executor-side mistake that treated
a valid HTTP 204 empty response as requiring a JSON data envelope. The accepted run uses the fixed
deterministic rule. No historical execution record was edited or deleted.

## Boundary

Phase 7B Playwright execution, Phase 8 evidence consolidation, bug generation, and report generation
have not started.
