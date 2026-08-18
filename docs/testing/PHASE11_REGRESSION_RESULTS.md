# Phase 11 Regression Results

Status: PASS

## Baseline and preservation

- Bug: `BUG-AUTH-001` v1 (`BUGR-B4E714D0B26843EF912A65B224ACFC32`)
- Baseline report: `RPT-BE5D133ABFB54EF2A4AFEFC82D86A189`
- Frozen baseline: `FBL-5BCEA5DA11144E9BB47C545AD73919DD`
- Historical API run: `RUN-71ED569CD73643E5B19F48BCFCD0FBEF`
- Historical UI run: `UIR-7169E1697F86400EBAE8AFBBBD5675B4`
- Historical seeded results remain `FAIL`; no historical row, evidence, Bug artifact, or report was
  modified or deleted.

## Real regression

- API run: `RUN-1CE1641BC37D44DD996410EB2BACA647`
- API result: 7 total, 6 PASS, 1 known test-data mismatch
- `TC-API-AUTH-REG-005` v2: `FAIL (201) -> PASS (400)`
- UI run: `UIR-E42BE51513AB4B27B6568DBDAB41BF66`
- UI result: 3 total, 3 PASS
- `TC-UI-AUTH-REG-005` v2: `FAIL (/profile, HTTP 201) -> PASS (/register, HTTP 400)`
- Adjacent deterministic guards: 7/7 PASS
- Non-guard `TC-API-REQ-REG-003` remains a truthful test-data mismatch (`expected 201`, `actual
400`) because its frozen username is shorter than the now-enforced requirement. It was not used
  to hide or weaken the product-fix result.

## Closure and integrity

- Regression record: `RGR-5B1FD386A93B49658A7D3927B7F7C65A`
- Bug status event: `BSE-EBE0D184D7F541C2A4BD6AA442D8C890`
- Effective Bug status: `closed`
- Trace hash: `4e143166dbeed7a1a575304ed66e95d40eade306ebb99d1a656aac0ca0977a60`
- Canonical Bug v1 remains immutable and retains its original `open` snapshot status.
- SQLite integrity: `ok`
- Foreign-key violations: `0`
- Python: `317 passed`, `22 deselected`
- Frontend Vitest: SUT `27 passed`; Plugin `1 passed`
- Ruff format/check: PASS (Phase 11 and application scopes)
- mypy: PASS (`65` source files)
- TypeScript, ESLint, and both production builds: PASS
- Prettier: Phase 11 files PASS; the repository-wide check continues to report pre-existing style
  warnings in earlier accepted documentation and schemas.
- Phase 12: not started
