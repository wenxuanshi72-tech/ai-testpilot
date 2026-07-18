# SUT Black-Box API Acceptance Results

Status: Phase 3 executed acceptance result

## Execution

- Executed at: `2026-07-18T09:11:54.7822363Z`
- SUT baseline commit: `5b71e5ebeb8adf650d8bc960d62ac62c39bd0682`
- Branch: `test/sut-api-acceptance`
- Environment: Windows, Python 3.11.9, pytest 8.4.2, HTTPX 0.28.1
- Public service boundary: `http://127.0.0.1:5001`
- Command: `powershell -NoProfile -ExecutionPolicy Bypass -File .\\scripts\\verify_phase3.ps1`
- Data isolation: Alembic migrated a uniquely named temporary SQLite database, which was removed after execution.

## Result counts

| Total | Ordinary PASS | Strict XFAIL | FAIL | ERROR | Other |
| ----: | ------------: | -----------: | ---: | ----: | ----: |
|    21 |            20 |            1 |    0 |     0 |     0 |

The Phase 3 acceptance gate passed. The XFAIL is a known requirement mismatch, not a passing product behavior.

## Protected seeded defect

`API-AUTH-SEED-001` tested `REQ-AUTH-USERNAME-001` through `POST /api/auth/register`. The formal expectation was HTTP `400`; the live SUT returned HTTP `201`. The strict XFAIL is classified as `BUG-AUTH-001`. The defect remains intentionally unfixed in this phase.

## Evidence and cleanup

- `artifacts/logs/phase3/verification_summary.json`: run metadata, counts, defect status, and cleanup result.
- `artifacts/logs/phase3/http_evidence.json`: one redacted HTTP evidence record per case.
- `artifacts/logs/phase3/pytest_api.log`: pytest black-box result log.
- `artifacts/logs/phase3/server.log`: migration and service log.

These runtime artifacts are ignored by Git. The verifier confirmed that the evidence does not contain the test password, cookies, tokens, request bodies, or token hashes. It stopped the exact process it started, removed its unique temporary database directory, and confirmed that port 5001 was released.

## Limits

The tests used public HTTP only. They did not import the SUT backend or Flask, use a Flask test client, inspect the database, alter backend behavior, test the React UI, create a formal bug artifact or report, or implement Plugin/AI functionality.

## Conclusion

Phase 3 live SUT backend black-box API acceptance is **PASS** with the protected `BUG-AUTH-001` evidence preserved as exactly one strict XFAIL.
