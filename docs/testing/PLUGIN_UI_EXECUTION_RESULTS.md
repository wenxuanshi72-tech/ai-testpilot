# Plugin UI Execution Results

## Acceptance

Phase 7B Playwright UI executor: **PASS**.

- Frozen baseline: `FBL-5BCEA5DA11144E9BB47C545AD73919DD`
- Accepted run: `UIR-7169E1697F86400EBAE8AFBBBD5675B4`
- Executor: `ui-executor@1.0.0`
- Browser: system Microsoft Edge through Playwright Python
- Environment: `local-windows-demo`
- Results: 3 total, 2 PASS, 1 FAIL, 0 BLOCKED, 0 ERROR
- Evidence: 3 screenshots and 3 Trace ZIPs; all stored hashes recomputed successfully

| Case | Verdict | Final route | API observation | Classification |
|---|---:|---|---|---|
| `TC-UI-AUTH-REG-005` | FAIL | `/profile` | register returned 201 instead of required 400 | `suspected_product_bug` |
| `TC-UI-REQ-LOGIN-001` | PASS | `/login` | login returned 401 and generic error was visible | none |
| `TC-UI-REQ-REG-002` | PASS | `/profile` | registration returned 201 and profile was visible | none |

The seeded UI case proves the protected defect through the real browser: the five-character username
`z1234` was accepted, an authenticated session was created, and the UI navigated to `/profile` rather
than remaining on `/register` with a minimum-length error. The SUT defect was not fixed or hidden.

The first immutable development run, `UIR-BF361DCBE2E9447391FD9F079BD420D8`, remains in the local
database. It exposed an executor defect that selected the last authentication network response (the
post-navigation `/me` request) and asserted UI state too early. The accepted run uses endpoint-specific
network selection and a bounded post-action stabilization wait. No historical run was edited.

SQLite reported `integrity_check=ok` and zero foreign-key violations. No DeepSeek call occurred.
Formal bug/report generation and the protected SUT fix remain outside Phase 7B.

## Quality gates

- Plugin backend: 258 passed, 1 deselected; branch coverage 86.32%.
- Phase 7B focused tests: 9 passed; `ui_execution.py` branch coverage 85.24%.
- SUT frontend Vitest: 27 passed across 3 files.
- SUT frontend TypeScript, ESLint, and production build: PASS.
- Ruff format/check: PASS.
- mypy: PASS across 63 source files.
- Migration chain through `0009`, `git diff --check`, sensitive-file scan, SQLite integrity,
  foreign keys, evidence-file hashes, and evidence-metadata hashes: PASS.
- Ports 5001 and 5173 and temporary service runtime directory: cleaned.
