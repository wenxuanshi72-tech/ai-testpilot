# Unified Test Case Protocol

Status: Phase 0 design. All payloads in this document are **Design examples — not executed**. They contain no PASS/FAIL result and prove no implemented behavior.

## Purpose

The protocol is the versioned, provider-neutral boundary between requirement/case generation, human review, and deterministic API, UI, or manual execution. Executors accept only schema-valid, approved, frozen snapshots. They never execute arbitrary Python, JavaScript, shell commands, or free-form model instructions.

## Case envelope

Every case contains:

| Field | Rule |
|---|---|
| `schema_version` | Semantic protocol version, e.g. `test-case@1.0.0` |
| `case_id` | Stable immutable identity such as `TC-API-AUTH-REG-005` |
| `case_version` | Positive version number; edits create a new immutable version |
| `title`, `description` | Human-readable intent, not executable code |
| `source_requirement_ids` | Non-empty stable requirement IDs |
| `test_type` | `api`, `ui`, or `manual` |
| `priority` | `P0` through `P3` |
| `severity_hint` | Advisory `critical`, `high`, `medium`, or `low`; not a verdict |
| `preconditions` | Structured conditions or approved setup references |
| `test_data` | Named values or generated-data specifications with sensitivity labels |
| `steps` | Typed, ordered, bounded step objects |
| `expected_results` | Human-readable outcomes tied to assertions |
| `assertions` | Typed deterministic checks at case or step scope |
| `tags` | Normalized search labels |
| `generation_source` | `human`, `ai_real`, or `ai_mock` |
| `provider`, `model`, `prompt_version` | Required for AI provenance; null only for human source |
| `review_status` | `draft`, `in_review`, `approved`, `rejected`, or `superseded` |
| `approved_version` | Equals `case_version` only after approval; otherwise null |
| `created_at` | UTC RFC 3339 timestamp |

Unknown fields are rejected by default. IDs, action types, assertion types, value sizes, step counts, and nesting depth are bounded by the schema and domain policy.

## Shared values, variables, and sensitive data

Test data entries use `{name, source, value/specification, sensitive, classification}`. `source` is `literal`, `fixture`, `generated`, `environment`, or `prior_extraction`. Secrets may only use `environment` or a secret-fixture reference; snapshots store the reference and redaction token, not the secret value.

References use the exact syntax `${variables.name}` and resolve from a scoped immutable map. A variable must be declared before use. Extraction specifies source, selector, destination name, required flag, sensitivity, and overwrite policy (`deny` by default). Cycles, unknown variables, and attempts to interpolate into action/locator types are invalid.

Sensitive classifications include `credential`, `token`, `cookie`, `personal`, and `confidential`. Executors redact marked values plus known sensitive header/body fields from logs, evidence, screenshots where feasible, and errors.

## API step

An API step has `step_id`, `action: http_request`, `description`, `request`, optional `extract`, `assertions`, and `continue_on_failure` (normally false).

`request` supports only:

- `method`: allowlisted HTTP method.
- `base_url_ref`: configured allowlisted target; never an arbitrary generated host.
- `path`: relative path with controlled variable interpolation.
- `headers`, `query`, and `body`: structured maps with sensitivity metadata.
- `content_type`, `timeout_ms`, and redirect policy within configured limits.

Response assertions include `status_equals`, `header_matches`, `content_type_equals`, `json_schema`, `json_path_exists`, `json_path_equals`, `json_path_matches`, `body_contains`, and bounded `duration_at_most_ms`. JSONPath uses a documented safe subset and cannot invoke script expressions. Type-aware comparisons are explicit.

Extraction supports response headers and safe JSONPath values. Authentication/session cookies are managed by the executor's isolated client and are never copied into the case snapshot.

## UI step

A UI step has `step_id`, one allowlisted `action`, optional `locator`, typed `value/options`, and optional assertions. Locator preference is:

1. `data-testid` for explicit automation contracts;
2. accessible `role` plus name;
3. associated `label`;
4. `placeholder` when stable.

CSS/XPath is exceptional, reviewed, and prohibited as the primary strategy when based on layout, generated classes, or fragile indexes.

Supported actions are `goto`, `click`, `fill`, `select`, `check`, `uncheck`, `wait_for`, and `screenshot`. Supported UI assertions are `expect_visible`, `expect_hidden`, `expect_text`, `expect_value`, `expect_url`, and reviewed accessibility checks. Waiting is condition-based; arbitrary long sleeps and model-written Playwright code are invalid.

`goto` accepts an allowlisted base URL reference plus relative path. `screenshot` requests evidence capture but cannot choose an arbitrary filesystem path.

## Manual step

A manual step contains `step_id`, `instruction`, optional structured `input_refs`, `expected_observation`, and `evidence_prompt`. It cannot contain executable snippets. A named reviewer records the outcome and evidence; automation never represents a manual case as automatically executed.

## Assertions and authoritative states

Assertions have `assertion_id`, `type`, structured `actual_source`, `operator` where relevant, `expected`, `required`, and a safe failure message template. Deterministic executor facts alone produce `PASS`, `FAIL`, `BLOCKED`, `ERROR`, or `SKIPPED`. `severity_hint` and AI analysis cannot change that state.

Required assertion mismatch is `FAIL`. Environment/precondition unavailability is `BLOCKED`; executor/infrastructure malfunction is `ERROR`; policy-based non-execution is `SKIPPED`. All required assertions succeeding is necessary for `PASS`.

## Review and version freeze

Generation creates `draft`. A reviewer may move a valid version to `in_review`, then `approved` or `rejected`, recording actor, timestamp, comment, and content hash. Approval sets `approved_version`; freezing captures the exact schema version, case version/hash, referenced requirement versions, test data references, environment ID, executor version, and locator/action/assertion definitions.

Edits after approval create a new draft version and mark dependent snapshots stale. Historical approved versions and execution snapshots remain immutable. Execution refuses draft, rejected, superseded, changed-hash, or unsupported-schema cases.

## Design example — API case, not executed

```json
{
  "schema_version": "test-case@1.0.0",
  "case_id": "TC-API-AUTH-REG-005",
  "case_version": 1,
  "title": "Reject a five-character username",
  "description": "Verify the formal six-character minimum through the registration API.",
  "source_requirement_ids": ["REQ-AUTH-USERNAME-001"],
  "test_type": "api",
  "priority": "P0",
  "severity_hint": "high",
  "preconditions": [{"type": "service_healthy", "target": "sut_backend"}],
  "test_data": [
    {"name": "username", "source": "literal", "value": "z1234", "sensitive": false, "classification": null},
    {"name": "password", "source": "literal", "value": "Test1234", "sensitive": true, "classification": "credential"}
  ],
  "steps": [{
    "step_id": "STEP-001",
    "action": "http_request",
    "description": "Submit registration with a five-character username.",
    "request": {
      "method": "POST",
      "base_url_ref": "sut_backend",
      "path": "/api/auth/register",
      "headers": {"Content-Type": "application/json"},
      "query": {},
      "body": {"username": "${variables.username}", "password": "${variables.password}", "password_confirmation": "${variables.password}"},
      "content_type": "application/json",
      "timeout_ms": 5000
    },
    "extract": [],
    "assertions": [
      {"assertion_id": "A-001", "type": "status_equals", "actual_source": "response.status", "expected": 422, "required": true},
      {"assertion_id": "A-002", "type": "json_path_equals", "actual_source": "$.error.details[0].code", "expected": "username_too_short", "required": true}
    ],
    "continue_on_failure": false
  }],
  "expected_results": ["Registration is rejected and identifies the six-character minimum."],
  "assertions": [],
  "tags": ["auth", "registration", "boundary", "seeded-defect"],
  "generation_source": "ai_real",
  "provider": "deepseek",
  "model": "planned-model-placeholder",
  "prompt_version": "test-generation@1.0.0",
  "review_status": "draft",
  "approved_version": null,
  "created_at": "2026-01-01T00:00:00Z"
}
```

## Design example — UI case, not executed

```json
{
  "schema_version": "test-case@1.0.0",
  "case_id": "TC-UI-AUTH-REG-005",
  "case_version": 1,
  "title": "Show validation for a five-character username",
  "description": "Verify the registration UI enforces the formal minimum without relying on fragile CSS.",
  "source_requirement_ids": ["REQ-AUTH-USERNAME-001"],
  "test_type": "ui",
  "priority": "P0",
  "severity_hint": "high",
  "preconditions": [{"type": "service_healthy", "target": "sut_frontend"}],
  "test_data": [
    {"name": "username", "source": "literal", "value": "z1234", "sensitive": false, "classification": null},
    {"name": "password", "source": "literal", "value": "Test1234", "sensitive": true, "classification": "credential"}
  ],
  "steps": [
    {"step_id": "STEP-001", "action": "goto", "value": {"base_url_ref": "sut_frontend", "path": "/register"}},
    {"step_id": "STEP-002", "action": "fill", "locator": {"strategy": "label", "value": "Username"}, "value": "${variables.username}"},
    {"step_id": "STEP-003", "action": "fill", "locator": {"strategy": "label", "value": "Password"}, "value": "${variables.password}"},
    {"step_id": "STEP-004", "action": "fill", "locator": {"strategy": "label", "value": "Confirm password"}, "value": "${variables.password}"},
    {"step_id": "STEP-005", "action": "click", "locator": {"strategy": "role", "role": "button", "name": "Register"}},
    {"step_id": "STEP-006", "action": "expect_text", "locator": {"strategy": "data-testid", "value": "username-error"}, "value": "at least 6 characters"}
  ],
  "expected_results": ["The form remains on registration and exposes an accessible minimum-length error."],
  "assertions": [{"assertion_id": "A-UI-001", "type": "expect_url", "actual_source": "page.url", "expected": "/register", "required": true}],
  "tags": ["auth", "registration", "ui", "seeded-defect"],
  "generation_source": "ai_real",
  "provider": "deepseek",
  "model": "planned-model-placeholder",
  "prompt_version": "test-generation@1.0.0",
  "review_status": "draft",
  "approved_version": null,
  "created_at": "2026-01-01T00:00:00Z"
}
```

The examples intentionally state the formal expected behavior and do not report the protected defective actual behavior as an execution result.

## Schema evolution

Patch versions clarify constraints without changing accepted meaning; minor versions add backward-compatible optional capabilities; major versions change required fields or semantics. Executors advertise supported versions and reject unknown majors. Migrations create new immutable case versions, preserve original payload/hash/provenance, and require re-review before execution. Deprecated actions receive a documented removal window and a deterministic migration path.
