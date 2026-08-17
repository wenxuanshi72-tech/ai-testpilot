# Plugin Evidence and Classification Results

## Result

Phase 8 acceptance: **PASS**.

The accepted Phase 7 runs were consolidated without re-executing tests or changing their verdicts:

- Frozen baseline: `FBL-5BCEA5DA11144E9BB47C545AD73919DD`
- API run: `RUN-71ED569CD73643E5B19F48BCFCD0FBEF`
- UI run: `UIR-7169E1697F86400EBAE8AFBBBD5675B4`
- Evidence consolidation: `ECR-9CAB97E4B01249E0B0C42CB56761F15A`
- Results: 10
- Consolidated evidence records: 13
- Deterministic failures: 3
- Advisory model calls: 0

## Deterministic classifications

| Case | Verdict | Classification | Trace |
|---|---|---|---|
| `TC-API-AUTH-REG-005` | FAIL | `seeded_product_bug` | `BUG-AUTH-001` |
| `TC-UI-AUTH-REG-005` | FAIL | `seeded_product_bug` | `BUG-AUTH-001` |
| `TC-API-REQ-REG-003` | FAIL | `test_data_invalid` | Frozen password violates the product password policy |

The remaining seven results retain `PASS` with classification `none`. The seeded defect remains
present: the formal oracle expects rejection, while the intentionally defective SUT accepts the
five-character username.

## Evidence verification

- API canonical evidence: 7/7 hash and redaction checks passed.
- UI screenshots: 3/3 path, hash, and redaction checks passed.
- UI traces: 3/3 path, hash, and redaction checks passed.
- SQLite `integrity_check`: `ok`.
- Foreign-key violations: 0.
- Applied migrations: 10 (`0001` through `0010`).

## Quality gates

- Phase 8 focused tests: 4 passed.
- Plugin backend: 262 passed, 1 deselected.
- Plugin backend coverage: 87.67% (required 80%).
- Ruff: PASS.
- mypy: PASS.
- Sensitive runtime files remain ignored and untracked.

Advisory AI analysis is implemented only as a versioned, non-authoritative storage boundary. No
real or mock model was called during Phase 8 acceptance. Phase 9 was not started.
