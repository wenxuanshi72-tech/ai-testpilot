# SUT Authentication Software Requirements Specification

Status: Phase 2 approved implementation specification

## Stable requirements

| ID                      | Requirement                                                                                | Verification                    |
| ----------------------- | ------------------------------------------------------------------------------------------ | ------------------------------- |
| `AUTH-HEALTH-001`       | `GET /api/health` returns a non-sensitive readiness response.                              | API test                        |
| `AUTH-REG-001`          | Valid registration creates one unique normalized user and returns `201`.                   | API/database test               |
| `REQ-AUTH-USERNAME-001` | A username must contain at least 6 and at most 32 characters.                              | Future formal API/UI acceptance |
| `AUTH-REG-002`          | Username permits only ASCII letters, digits, and underscore after trimming.                | Validation test                 |
| `AUTH-REG-003`          | Password is 8–128 characters with uppercase, lowercase, and digit.                         | Validation test                 |
| `AUTH-REG-004`          | Password confirmation is required and must match.                                          | Validation test                 |
| `AUTH-REG-005`          | A duplicate normalized username returns `409` and creates no user.                         | API/database test               |
| `AUTH-LOGIN-001`        | Valid credentials return `200` and create a new opaque session.                            | API/database test               |
| `AUTH-LOGIN-002`        | Missing user and wrong password both return generic `401` responses.                       | API test                        |
| `AUTH-SESSION-001`      | Authentication uses a cryptographically random opaque token; only its hash is stored.      | Unit/database test              |
| `AUTH-SESSION-002`      | The session cookie is HttpOnly, SameSite=Lax, Path=/, bounded, and Secure when configured. | Header test                     |
| `AUTH-SESSION-003`      | Absolute expiry is eight hours and idle expiry is thirty minutes.                          | Clock-controlled test           |
| `AUTH-ME-001`           | A valid active session returns only public current-user fields.                            | API test                        |
| `AUTH-ME-002`           | Missing, expired, revoked, or unknown sessions return `401`.                               | API test                        |
| `AUTH-LOGOUT-001`       | Logout revokes the presented active session and clears the cookie.                         | API/database test               |
| `AUTH-LOGOUT-002`       | Repeated or unauthenticated logout remains an idempotent `204`.                            | API test                        |
| `AUTH-HTTP-001`         | JSON mutation endpoints reject unsupported media types with `415`.                         | API test                        |
| `AUTH-HTTP-002`         | Malformed JSON and non-object JSON return stable `400` errors.                             | API test                        |
| `AUTH-ERROR-001`        | Errors contain code, safe message, details, and request ID without sensitive data.         | Contract/security test          |
| `AUTH-CORS-001`         | Credentialed CORS and browser origins use only configured exact origins.                   | CORS/origin test                |
| `AUTH-DATA-001`         | Development and tests use isolated databases; no database file is tracked.                 | Migration/repository test       |

## Deliberate requirement-to-implementation mismatch

`REQ-AUTH-USERNAME-001` is authoritative. Phase 2 deliberately omits its minimum-length enforcement
while retaining maximum-length and character checks. The internal sentinel test therefore expects
`z1234 / Test1234` to return `201`. That sentinel protects the seeded defective implementation; it
is not formal requirement acceptance. Future generated `TC-API-AUTH-REG-005` and
`TC-UI-AUTH-REG-005` must expect rejection and must fail until `BUG-AUTH-001` is fixed.
