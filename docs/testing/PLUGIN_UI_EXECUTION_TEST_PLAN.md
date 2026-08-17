# Plugin UI Execution Test Plan

## Target

Execute the three UI snapshots in frozen baseline
`FBL-5BCEA5DA11144E9BB47C545AD73919DD` through the real React UI and Flask API using Playwright
Python and system Edge. The protected five-character username case must fail deterministically with
`suspected_product_bug` while retaining screenshots and Trace evidence.

## Gates

1. Validate immutable baseline/snapshot identities and require a loopback target.
2. Permit only route, exact label, and exact button-role locators.
3. Start isolated local SUT services and use a fresh SQLite database per run.
4. Assert final route, relevant API response status, and visible UI state.
5. Persist one immutable result, screenshot, Trace, metadata record, and verified hash per case.
6. Verify no password action enters Trace and no `.env`, database, or evidence artifact enters Git.
7. Run full Python tests with at least 85% Plugin branch coverage, Ruff, mypy, migrations, frontend
   Vitest/typecheck/lint/build, database integrity, foreign keys, and `git diff --check`.

Application-level FAIL is a valid executor outcome. Missing evidence, unstable/unsupported locator,
browser failure, wrong seeded-defect classification, or integrity failure blocks Phase 7B acceptance.
