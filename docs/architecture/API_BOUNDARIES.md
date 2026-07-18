# API Boundaries

Status: Phase 0 design only. The routes and payloads below are contracts to implement and validate in later phases; none is implemented or executed now.

## Purpose and boundary

This document separates the SUT authentication API from the AI TestPilot plugin API, defines representative resources and lifecycle operations, and establishes consistent transport behavior. The plugin must test the SUT through public HTTP/UI boundaries and must never read `sut.db`. Browser clients access each backend through its own typed API client.

## Design principles

- Resource-oriented JSON under `/api/v1` for the plugin and `/api` for the deliberately small SUT.
- HTTPS is required outside loopback development; JSON uses UTF-8 and timestamps use UTC RFC 3339.
- Validate at the boundary, apply domain rules in application services, and return one stable error envelope.
- Stable IDs are opaque strings. Clients do not derive meaning from database keys.
- Long work is asynchronous and observable; create operations return a task resource rather than holding a connection.
- Approved versions, results, and evidence are immutable. Changes create new versions.
- AI produces candidates only. Deterministic executors own assertions and final test states.
- Server-side opaque sessions remain the SUT authentication mechanism; no JWT is introduced.

## SUT API

The SUT owns authentication behavior only. A successful login/registration creates an opaque high-entropy server-side session and returns a `Set-Cookie` header. The cookie is `HttpOnly`, `SameSite=Lax`, scoped narrowly, and `Secure` when HTTPS is used. The database stores only a token hash.

| Method and path | Purpose | Expected success | Important boundary |
|---|---|---|---|
| `GET /api/health` | Liveness/readiness summary | `200` | No secrets or dependency internals |
| `POST /api/auth/register` | Create user and session | `201` | Username/password/confirmation input; protected defect remains until fix phase |
| `POST /api/auth/login` | Authenticate and create session | `200` | Generic invalid-credential response |
| `GET /api/auth/me` | Return current user | `200` | Requires valid session cookie; otherwise `401` |
| `POST /api/auth/logout` | Revoke current session | `204` | Idempotent from the client perspective |

Design example — registration request (not implemented or executed):

```json
{
  "username": "example_user",
  "password": "example-only-not-a-real-secret",
  "password_confirmation": "example-only-not-a-real-secret"
}
```

Design example — user response (not implemented or executed):

```json
{
  "data": {
    "user_id": "USR-01JEXAMPLE",
    "username": "example_user",
    "created_at": "2026-01-01T00:00:00Z"
  },
  "meta": { "request_id": "REQ-01JEXAMPLE" }
}
```

The formal rule requires six username characters. Until the authorized regression fix, `z1234` is intentionally accepted by both SUT validation layers. API documentation must describe the formal requirement while tests preserve and expose the mismatch.

## Plugin API

### Health and projects

- `GET /api/v1/health`: process health; optional readiness fields remain non-sensitive.
- `POST /api/v1/projects`: create a testing project.
- `GET /api/v1/projects/{project_id}` and `PATCH ...`: read/update allowed project metadata.
- `GET /api/v1/projects`: paginated project query.

### PRD ingestion and versions

- `POST /api/v1/projects/{project_id}/prds`: multipart Markdown/plain-text upload with type, size, and filename validation; returns `201` for stored source metadata.
- `GET /api/v1/prds/{prd_id}`: metadata and latest-version reference.
- `GET /api/v1/prds/{prd_id}/versions`: immutable version history.
- `GET /api/v1/prd-versions/{version_id}`: version metadata and permitted source view.

### Analysis and structured requirements

- `POST /api/v1/prd-versions/{version_id}/analysis-runs`: enqueue real or explicitly configured mock analysis; returns `202` with task/run IDs.
- `GET /api/v1/analysis-runs/{analysis_run_id}`: task, batch, provider-mode, validation, and promotion status.
- `GET /api/v1/analysis-runs/{analysis_run_id}/requirements`: candidate or approved structured requirements, filtered by review state/risk.
- `GET /api/v1/requirements/{requirement_id}/versions`: requirement history and source locations.

Design example — asynchronous analysis creation (not implemented or executed):

```json
{
  "prompt_version": "requirement-analysis@1.0.0",
  "schema_version": "requirement-set@1.0.0",
  "provider_mode": "real"
}
```

```json
{
  "data": {
    "analysis_run_id": "ANR-01JEXAMPLE",
    "task_id": "TSK-01JEXAMPLE",
    "status": "queued"
  },
  "meta": { "request_id": "REQ-01JEXAMPLE" }
}
```

### Case generation, review, and freeze

- `POST /api/v1/analysis-runs/{id}/test-generation-runs`: enqueue bounded API/UI/manual draft generation.
- `GET /api/v1/test-generation-runs/{id}`: generation and validation status.
- `GET /api/v1/projects/{id}/test-cases`: filtered, paginated stable case identities.
- `GET /api/v1/test-cases/{case_id}/versions`: immutable versions.
- `POST /api/v1/test-case-versions/{id}/reviews`: record approve/reject/revision decision.
- `POST /api/v1/test-case-versions/{id}/freeze`: freeze an approved version; reject unapproved or stale versions.

Review endpoints require optimistic concurrency data. Approval does not execute a case.

### Runs and deterministic execution

- `POST /api/v1/test-runs`: create a run from frozen case versions and an allowlisted environment; returns `202`.
- `GET /api/v1/test-runs/{run_id}`: authoritative aggregate state and timestamps.
- `GET /api/v1/test-runs/{run_id}/results`: deterministic case results.
- `POST /api/v1/test-runs/{run_id}/cancel`: cooperative cancellation.

The API executor accepts protocol-defined HTTP steps only; it cannot run model-authored code. The UI executor accepts allowlisted Playwright actions/locators/assertions only and runs in an isolated browser context. Both emit evidence before terminal result finalization. Plugin HTTP endpoints orchestrate these components but do not expose arbitrary URL fetch, Python evaluation, shell execution, or unrestricted filesystem paths.

### Evidence, bugs, reports, and regression

- `GET /api/v1/evidence/{evidence_id}`: redacted metadata; content access is separately authorized and content-type constrained.
- `GET /api/v1/test-results/{result_id}/evidence`: evidence metadata for one result.
- `POST /api/v1/bugs`: generate a canonical local bug from eligible failed results; returns local artifact metadata, never pushes externally.
- `GET /api/v1/bugs/{bug_id}`: bug record and trace links.
- `POST /api/v1/reports`: enqueue HTML/Markdown/PDF export from canonical run data.
- `GET /api/v1/reports/{report_id}` and `/artifacts`: status and safe relative artifact references.
- `POST /api/v1/bugs/{bug_id}/regression-runs`: create a run linked to baseline evidence and frozen cases.
- `GET /api/v1/regression-runs/{id}`: before/after links and deterministic outcome.

Formal bugs require failed results plus required persisted evidence. Formal reports require real finalized runs. Export failure cannot create an apparently complete artifact.

## Error response

All errors use one envelope. Field details are safe and machine-readable; internal stack traces, credentials, cookies, raw provider responses, and local absolute paths are excluded.

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request is invalid.",
    "details": [{ "field": "username", "code": "too_short" }],
    "retryable": false
  },
  "meta": {
    "request_id": "REQ-01JEXAMPLE",
    "correlation_id": "COR-01JEXAMPLE"
  }
}
```

Design example only; it is not an observed response.

## HTTP status principles

- `200` read/update or synchronous command success; `201` resource created; `202` accepted async work; `204` successful no-content command.
- `400` malformed request, `401` unauthenticated, `403` unauthorized, `404` hidden/absent resource, `409` state/version conflict, `413` too large, `415` unsupported media type, `422` structurally valid but domain-invalid input, `429` rate limited.
- `500` unexpected server failure, `502` provider/upstream invalid response, `503` dependency unavailable, `504` upstream timeout.
- Product test failures remain result resources and do not turn a successful result-query API call into an HTTP error.

## Pagination, filtering, and sorting

Collections use opaque cursor pagination with `page_size` capped by endpoint. Responses include `next_cursor` and no fabricated total. Filters use documented allowlists (for example `status`, `test_type`, `risk`); sorting uses stable fields and always adds stable ID as a tie-breaker. Unknown filters/sorts are rejected.

## Idempotency and concurrency

Resource-creating commands that may be retried accept `Idempotency-Key`, scoped to actor, endpoint, and canonical request hash. Reuse with a different payload returns `409`. Task and artifact creation returns the original resource for an identical retry. Review/freeze updates require a version/ETag to prevent lost updates. Executors also use stable run/case-attempt keys.

## Asynchronous task states

Tasks use `queued`, `running`, `retry_wait`, `succeeded`, `failed`, or `cancelled`. Execution results separately use `PASS`, `FAIL`, `BLOCKED`, `ERROR`, or `SKIPPED`. Task success means orchestration completed; it does not imply tests passed. Status resources expose progress counts, current stage, timestamps, retry count, and a redacted failure code.

## Request and correlation IDs

The boundary accepts a syntactically valid `X-Request-ID` or generates one; it returns the canonical ID. One `correlation_id` connects upload, analysis, generation, execution, evidence, and export events. Provider request IDs are recorded separately. Untrusted IDs are length/character constrained before logging.

## Security and redaction

CORS is restricted to configured local frontends. State-changing session-authenticated SUT requests use the planned CSRF defense. Upload paths, test targets, content types, and sizes are allowlisted. Logs and responses redact secrets, `Authorization`, `Cookie`, password fields, provider keys, and sensitive variables. Evidence content requires project-scoped authorization and never exposes an arbitrary path.

## Phase 0 declaration

This document defines route and payload boundaries only. Phase 0 creates no Flask routes, React clients, SQLAlchemy models, tasks, provider calls, executors, evidence, or observed API results.
