# SUT Backend Test Plan

Status: Phase 2 executable test plan

## Scope and strategy

Use pytest with isolated temporary SQLite databases and the Flask application factory. Tests exercise
validation, repositories/services, real Flask request handling, session persistence, migration, and
security boundaries without network access or real credentials.

## Required coverage

- Factory/configuration: explicit injection, database isolation, no import-time server startup.
- Health and errors: health, request ID propagation/generation, 404, 405, 415, malformed JSON, safe
  500 envelope.
- Registration: success, normalization, duplicate, missing fields, mismatch, illegal characters,
  maximum length, password rules, password hash confidentiality.
- Login: success, missing user, wrong password, generic failure response.
- Sessions: token hash storage, cookie attributes, authenticated/unauthenticated `me`, absolute and
  idle expiry, revocation, logout, repeated logout.
- Browser boundary: exact credentialed CORS and rejection of untrusted mutation origins.
- Privacy: logs and responses do not contain passwords, cookie values, token hashes, or database paths.
- Migration: a blank temporary SQLite database upgrades to head with `users` and `user_sessions`.
- Protected defect sentinel: `z1234 / Test1234` returns `201` and is clearly labelled non-acceptance.

## Gate

All Phase 2 tests pass, backend business-code branch coverage is at least 85%, Ruff format/lint and
mypy pass, migration upgrade succeeds, and a separately started loopback server proves health,
register, login, me, logout, and the seeded five-character path. Runtime databases, logs, coverage,
cookies, and tokens remain ignored and untracked.
