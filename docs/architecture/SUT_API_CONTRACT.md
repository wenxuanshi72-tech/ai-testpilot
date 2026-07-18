# SUT Authentication API Contract

Status: Phase 2 implementation contract

## Transport conventions

- Base path is `/api`, matching `API_BOUNDARIES.md`; no `/api/v1` prefix is used by the SUT.
- Requests and responses use UTF-8 JSON except successful logout, which has no response body.
- Every response returns `X-Request-ID`. JSON responses also include `meta.request_id`.
- A valid constrained `X-Request-ID` is propagated; otherwise a new opaque request ID is generated.
- Credentialed CORS reflects only configured exact origins and never returns wildcard origin.
- Mutation requests carrying an `Origin` header are accepted only from the configured allowlist.

## Endpoints

### `GET /api/health`

Returns `200` with `data.status = "ok"`; it exposes no database path or secret.

### `POST /api/auth/register`

Requires `application/json` and an object containing `username`, `password`, and
`password_confirmation`. Success returns `201`, public user data, and a new session cookie.
Duplicate username returns `409`. Malformed/invalid input returns `400`; unsupported media type
returns `415`.

Formal username rules are 6–32 characters and `[A-Za-z0-9_]+` after trimming. The Phase 2 seeded
implementation intentionally enforces only the maximum and character rules, so `z1234` is wrongly
accepted.

### `POST /api/auth/login`

Requires `application/json` with `username` and `password`. Success returns `200`, public user data,
and a newly generated session cookie. Any invalid credentials return the same `401` code and message.

### `GET /api/auth/me`

Requires the configured opaque session cookie. Success returns `200` with public user data. Missing,
unknown, expired, revoked, or inactive-user sessions return `401`.

### `POST /api/auth/logout`

Returns idempotent `204`, revokes the presented current session when one exists, and clears the
session cookie. An allowed or absent Origin is required; an untrusted Origin returns `403`.

## Success envelope

```json
{
  "data": {
    "user_id": "USR-example",
    "username": "example_user",
    "created_at": "2026-01-01T00:00:00Z"
  },
  "meta": { "request_id": "REQ-example" }
}
```

## Error envelope

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request is invalid.",
    "details": [{ "field": "username", "code": "invalid_format" }],
    "retryable": false
  },
  "meta": { "request_id": "REQ-example" }
}
```

Defined status coverage includes `200`, `201`, `204`, `400`, `401`, `403`, `404`, `405`, `409`,
`415`, and safe `500`.

## Cookie and session contract

The cookie name is configurable and defaults to `sut_session`. It contains a URL-safe random opaque
token. The database contains only SHA-256 of that token. Cookie attributes are `HttpOnly`,
`SameSite=Lax`, `Path=/`, `Max-Age` aligned with absolute session lifetime, and `Secure` when enabled.
The token never appears in JSON, logs, or source control.

## CORS and CSRF boundary

Default allowed origins are the exact local SUT frontend origins configured by environment. CORS
allows credentials plus only required methods/headers. Origin validation is the Phase 2 CSRF control
for browser state-changing requests. Requests without `Origin` remain available to same-origin and
non-browser local clients; deployed configurations must use HTTPS and a strict explicit allowlist.

## Security limits

Request bodies are capped, username/password lengths are bounded, credentials are never logged,
password hashes and session token hashes are never serialized, and unexpected exceptions return no
stack trace, absolute path, SQL detail, or secret.
