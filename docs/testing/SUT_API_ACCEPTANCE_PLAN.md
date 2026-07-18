# SUT Black-Box API Acceptance Plan

Status: Phase 3 approved execution plan

## Objective

Prove the Phase 2 SUT authentication backend through its public HTTP boundary and preserve a repeatable, redacted baseline showing that `REQ-AUTH-USERNAME-001` is violated by `BUG-AUTH-001`.

## Scope

- Real loopback service at `http://127.0.0.1:5001`.
- Health, registration, validation, login, cookie-backed session, current user, and logout.
- Stable success/error envelopes and request IDs.
- A migration-created isolated SQLite database for each verification run.
- Manual case baseline `test-specs/api/sut_auth_api_cases.yaml` executed by pytest black-box tests.

## Non-scope

No Flask test client, internal imports, database inspection, backend changes, React/Playwright tests, Plugin or AI functionality, formal bug artifact, formal report, or Phase 4 implementation.

## Environment and data

The verifier sets a temporary `SUT_DATABASE_URL`, migrates it to head, starts the real Flask process, and supplies `PHASE3_BASE_URL` to HTTPX. Tests generate unique non-personal usernames and use the documented non-production password fixture without logging request bodies.

## Black-box principles

Tests import neither `sut.backend` nor Flask. They use bounded HTTP timeouts, cookie-aware clients, public paths only, independent data, and no direct database access. Service readiness is polled through `/api/health`; a fixed sleep is not treated as readiness.

## Case classes

- Availability and transport: health, request ID, error envelope, content type, malformed JSON.
- Registration: valid, duplicate, missing fields, username bounds/characters, password policy.
- Authentication: successful and failed login, authenticated and unauthenticated current user.
- Session lifecycle: cookie continuity, logout, and post-logout denial.
- Protected requirement: five-character username rejection expectation.

## Known-defect strategy

`API-AUTH-SEED-001` asserts the formal expected `400`. It is marked `xfail(strict=True)` for `BUG-AUTH-001`. The request executes and currently observes `201`, producing exactly one XFAIL. XFAIL records a known requirement mismatch; it is not a pass. A future repair produces strict XPASS and blocks the suite until defect status and tests are reviewed. The Phase 2 internal sentinel remains separate because it protects the intentionally defective build by expecting `201`.

## Pass criteria

All ordinary black-box cases pass, exactly one test XFAILs for `BUG-AUTH-001`, and there are no other failures, errors, skips, or XFAILs. Migration, service startup, evidence persistence, redaction, process/database cleanup, quality tools, default pytest, and phase-boundary checks must also pass.

## Evidence, safety, and cleanup

Ignored evidence under `artifacts/logs/phase3/` contains statuses, paths, request IDs, durations, trace IDs, and classification only. It excludes passwords, bodies, cookies, tokens, hashes, and `.env` content. The verifier stops only the process it started, confirms port 5001 is released, and deletes only its uniquely named temporary database directory in `tmp/phase3/`, including failure paths.
