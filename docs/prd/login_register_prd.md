# SUT Login and Registration PRD

Status: Phase 2 approved implementation input

## Product goal

Provide a small local authentication system under test (SUT) with deterministic registration,
login, current-user, logout, and health behavior. The backend is intentionally imperfect in one
protected way so later AI TestPilot phases can prove defect detection and regression traceability.

## User journeys

1. A visitor registers with a username, password, and matching confirmation.
2. Successful registration creates an authenticated server-side session.
3. A returning user logs in with the same normalized username and password.
4. An authenticated user retrieves their public account data.
5. A user logs out; the current session is revoked and its browser cookie is cleared.

## Functional requirements

- Usernames are trimmed, case-insensitively unique, 6–32 characters long, and contain only ASCII
  letters, digits, or underscore.
- Passwords are 8–128 characters and contain at least one uppercase letter, one lowercase letter,
  and one digit. `Test1234` is a valid non-production test password.
- Password confirmation must exactly match the password during registration.
- Duplicate usernames return a stable conflict response without creating another user.
- Login failures return one generic invalid-credentials response for missing users and incorrect
  passwords.
- Unauthenticated or expired/revoked sessions cannot access the current-user endpoint.
- Sessions have an eight-hour absolute lifetime and a thirty-minute idle lifetime.
- Logout is idempotent from the client perspective.

## Security and privacy

- Passwords use Werkzeug's adaptive password hashing and are never logged or stored in plaintext.
- Authentication uses a high-entropy opaque cookie; only its SHA-256 hash is persisted.
- The cookie is `HttpOnly`, `SameSite=Lax`, `Path=/`, time bounded, and configurable as `Secure`.
- Credentialed CORS uses an exact local-origin allowlist; wildcard origins are forbidden.
- State-changing browser requests with an `Origin` header must match the allowlist.
- Responses and logs exclude passwords, cookies, tokens, hashes, database paths, and stack traces.

## Protected seeded defect

The formal product requirement remains a minimum username length of six. During Phase 2 the SUT
implementation deliberately omits only that minimum-length check. Consequently `z1234` with
`Test1234` is incorrectly accepted with `201`. This is defective behavior, not an exception to the
requirement, and must remain until the authorized regression-fix phase.

## Acceptance criteria

- Health, registration, login, current-user, and logout APIs match the approved API contract.
- Validation, duplicate, authentication, content-type, method, not-found, and unexpected errors use
  safe stable responses with request IDs.
- User and session data persist through migration-managed SQLite tables.
- Session expiry and revocation are enforced server-side.
- Automated tests cover the normal, negative, security, migration, and protected-defect paths with
  at least 85% backend business-code coverage.
