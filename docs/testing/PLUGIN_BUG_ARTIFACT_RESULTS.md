# Plugin Local Bug Artifact Results

## Result

Phase 9 acceptance: **PASS**.

- Source consolidation: `ECR-9CAB97E4B01249E0B0C42CB56761F15A`
- Canonical record: `BUGR-B4E714D0B26843EF912A65B224ACFC32`
- Bug: `BUG-AUTH-001` v1
- API case/result: `TC-API-AUTH-REG-005` v2 / `RES-3F5ACD572FCA45E4BDE404A4AD14A66A`
- UI case/result: `TC-UI-AUTH-REG-005` v2 / `UIRES-EF3E3C900CA54F28AF39D5BB19E2CF8F`
- Requirement: `REQ-BAT-002-6`
- Evidence records: 3 (API exchange, UI screenshot, UI trace)
- Product Bugs generated: 1
- `test_data_invalid` sources included: 0
- DeepSeek calls: 0
- External pushes: 0

## Artifact bundle

- JSON SHA-256: `b898509d1d9473bae18af005a26674fae1af709bdabe9b2491a50286593287d1`
- Markdown SHA-256: `473ba14df5053d4db5dbfa388f0f23b4fd86e579ef6589d3e91c4b490de4d15b`
- Manifest SHA-256: `265281932bf652cd65d11bbd5a9935e162c787f335ac03011a46c0dd8a07d6ca`
- Manifest JSON hash verification: PASS
- Manifest Markdown hash verification: PASS
- Relative evidence-link verification: PASS

The runtime bundle is stored under ignored `artifacts/bugs/` and is not committed.

## Data and safety

- SQLite integrity: `ok`
- Foreign-key violations: 0
- Migrations: 11 (`0001` through `0011`)
- Sensitive-content scan: PASS
- The password, Cookie/session values, Authorization headers, API keys, absolute paths, and SQLite
  connection strings are absent from the Bug bundle.
- The protected seeded defect remains unfixed.

## Quality gates

- Phase 9 focused tests: 4 passed.
- Plugin backend: 266 passed, 1 deselected.
- Plugin backend coverage: 87.71% (required 80%).
- Phase-scoped Ruff and mypy: PASS.
- Phase 10 was not started.
