# Phase 7A API Executor Implementation

## Scope

Phase 7A consumes only API members from an immutable Phase 6 frozen baseline. It does not execute
UI snapshots, call an LLM, repair the SUT, create bugs, or generate reports. The protected username
minimum-length defect remains deliberately present.

## Execution boundary

`ApiExecutionService` validates the frozen baseline, environment, executor contract, snapshot JSON,
and snapshot hash before execution. Each API case receives a fresh temporary SQLite SUT database
under the ignored `tmp/` directory and a real Flask test client. Setup requests and the test request
therefore traverse the SUT's public Flask routes while remaining isolated and reproducible.

The versioned `sut-auth-api-adapter@1.0.0` maps the candidate protocol's `confirmation` field to the
SUT's `password_confirmation` field. If a registration intent omits confirmation, it supplies the
same password only for non-confirmation-focused cases. Every transformation is recorded in evidence.
Expired-session setup uses a trusted local fixture after a real register/login setup; arbitrary SQL,
shell commands, and candidate-provided database instructions are never executed.

## Verdict and evidence

`api-executor@1.0.0` deterministically evaluates status, response envelope, sensitive-value absence,
and the protected defect's non-creation oracle. Results conform to
`api-execution-result@1.0.0`. Request bodies, response bodies, request IDs, assertions, adapter audit,
and SHA-256 evidence hashes are persisted atomically in migration `0008_api_execution.sql`.
Passwords, cookies, authorization values, and tokens are redacted. Runs, results, and evidence are
append-only through SQLite immutability triggers.

## HTTP and CLI interfaces

- `POST /api/v1/frozen-baselines/{baseline_id}/api-executions`
- `GET /api/v1/api-test-runs/{run_id}`
- `GET /api/v1/api-test-results/{result_id}/evidence`
- `python -m scripts.run_api_baseline --database ... --baseline-id ... --environment-id ...`
- `python -m scripts.verify_phase7a --database ... --run-id ...`

Phase 7B remains a separate gated phase and is not implemented here.
