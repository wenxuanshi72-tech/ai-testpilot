# SUT Frontend Test Plan

Status: Phase 4 approved execution plan

## Automated scope

- API unit tests: Axios defaults, response/error mapping, 401 handling, request IDs, and contract payloads.
- Component tests: registration, login, profile, logout, success/error/loading, field rules, duplicate submission, and storage safety.
- Router tests: root resolution, public routes, protected redirect with return target, authenticated profile, retry, and 404.
- Accessibility checks: headings, labels, autocomplete, explicit buttons/links, status copy, and protected data display.

Tests mock only authApi at the component boundary. They do not present mocks as backend integration evidence. scripts/verify_phase4.ps1 separately starts migrated Flask and Vite processes against isolated databases for real HTTP/CORS/cookie integration.

## Protected-defect test

The named test BUG-AUTH-001 allows a five-character username to reach the registration API enters z1234 / Test1234, proves client validation does not block it, and asserts the registration service receives it. The test protects the intentional mismatch; it does not claim that five characters satisfy REQ-AUTH-USERNAME-001.

## Real integration

The verifier checks backend health, Vite SPA access for register, login, profile, and not-exist routes, credentialed CORS, normal registration, current user, logout/session invalidation, and real z1234 registration returning 201. It then uses a fresh isolated database for the Phase 3 black-box baseline, expecting 20 PASS and one strict XFAIL.

## Manual browser acceptance

Chrome visual review remains a user-confirmed item: inspect desktop/mobile layout, keyboard traversal, focus visibility, password reveal behavior, success/error readability, reduced motion, and absence of overflow. Phase 4 does not add Playwright or claim browser-visual evidence.

## Exit criteria

Formatting, ESLint, strict TypeScript, all Vitest tests, both frontend builds, Python default tests, live API baseline, integration checks, redaction, cleanup, scope, and Git checks pass. Ports 5001/5173 and temporary databases must be released. No real .env, secret, token, cookie, database, log, build output, or coverage artifact may be tracked.
