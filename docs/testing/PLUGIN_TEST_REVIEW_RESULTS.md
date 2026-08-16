# Plugin Test Review and Freeze Results

## Current result

**PHASE 6 REAL MVP ACCEPTANCE: PASS**

The Phase 6 review, approval-version, frozen-baseline, immutable-snapshot, and audit capabilities are
implemented and accepted against the real Phase 5B collection. All 46 candidates have an
attributable latest classification. Eight human revisions passed Candidate Schema and
`candidate-executability@1.0.0`; ten approved automated versions were frozen into one immutable MVP
baseline. No test was executed during Phase 6.

## Implemented capabilities

- Attributable `approve`, `reject`, and `request_changes` decisions
- Optimistic candidate-hash concurrency control
- Immutable approved case versions
- Complete-collection-only freeze gate
- Frozen baseline version and canonical baseline hash
- One immutable execution snapshot per approved case
- Requirement trace and snapshot hash verification
- Append-only audit events and SQLite immutability triggers
- Versioned review, freeze-request, and execution-snapshot schemas
- Read-only baseline and snapshot retrieval boundary for Phase 7
- Deterministic candidate executability report and approval gate
- Enumerated anonymous, authenticated, expired, and revoked session fixtures
- Current-chain checkpoint executability revalidation before reuse
- Historical approval compatibility: immutable v1 retention, validated v2 human revisions, and
  latest-review-only baseline selection

## Verification evidence

| Gate | Result |
|---|---|
| Phase 6 focused generation/review tests | 80 passed |
| Plugin backend complete suite | 243 passed, 1 deselected |
| Full repository Python suite | 288 passed, 22 deselected |
| Ruff format | PASS |
| Ruff check | PASS |
| mypy | PASS, 32 Plugin application source files |
| Empty database migration | 0001 through 0007 PASS |
| Existing database upgrade tests | 0003 through 0007 and 0006 through 0007 PASS |
| SQLite integrity check | `ok` |
| SQLite foreign-key check | 0 findings |
| `git diff --check` | PASS |

Automated regression tests continue to use isolated Mock-provider data and the explicit test-only
reviewer `portfolio-owner`. The real classification and freeze described below were explicitly
confirmed by the project owner and are not represented as test execution results.

## Real collection audit

Run `TGR-0A4E9521B2B444DD8FA72C1FCB362EDF` has 46/46 real latest classifications:

- `approve + automated`: 10
- `approve + manual`: 12
- `approve + deferred`: 5
- `request_changes + deferred`: 19

The selected MVP contains eight immutable human revisions and two unchanged executable original
candidates (`TC-API-REQ-BAT-002-5` and `TC-API-REQ-REG-004`). Manual and deferred candidates are
reviewed design evidence only and are excluded from execution snapshots. The unsupported
`TC-UI-REQ-LOGOUT-001` remains `request_changes + deferred` and has no human revision.

The protected seeded-defect API case preserves its immutable historical approval v1
`ATCV-87E6BE70B91D44DD9AE34E5CA70158C8`. Its validated human revision was approved as v2
`ATCV-12436CC45EE54ACCB1B73CD0FD7B9FB1`; the formal oracle remains HTTP 400 for username `z1234`.
The corresponding UI v2 also retains the formal rejection oracle. The intentionally defective SUT
behavior remains unchanged for deterministic discovery in the execution phase.

## Real frozen MVP baseline

- Baseline ID: `FBL-5BCEA5DA11144E9BB47C545AD73919DD`
- Baseline version: 1
- Baseline hash: `142765b5e50464455161bfdb65520147251aebdde6479de5a25a16a0d1a7c722`
- Status: `frozen`
- Frozen by: `auroia`
- Environment: `local-windows-demo`
- Executor contract: `test-executor@1.0.0`
- Approved automated members: 10
- Immutable execution snapshots: 10

Snapshot cases:

1. `TC-API-AUTH-REG-005` v2
2. `TC-API-REQ-AUTH-001` v2
3. `TC-API-REQ-BAT-002-5` v1
4. `TC-API-REQ-LOGIN-001` v2
5. `TC-API-REQ-LOGOUT-001` v2
6. `TC-API-REQ-REG-003` v2
7. `TC-API-REQ-REG-004` v1
8. `TC-UI-AUTH-REG-005` v2
9. `TC-UI-REQ-LOGIN-001` v2
10. `TC-UI-REQ-REG-002` v2

The baseline contains no manual or deferred member. SQLite reported `integrity_check=ok` and zero
foreign-key violations after the single transactional freeze.

## Boundary

- DeepSeek calls: 0
- New generation runs: 0
- Real latest classifications: 46/46
- Human revisions: 8
- Approved automated versions selected for MVP: 10
- Frozen baselines: 1
- Immutable execution snapshots: 10
- Test execution: not implemented or performed
- API/UI verdicts: 0
- Evidence, bugs, and reports: 0
- Seeded defect: unchanged
- Phase 7: not started
