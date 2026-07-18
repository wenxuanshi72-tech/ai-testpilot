# ADR-003: Real and Mock Provider Separation

- Status: Accepted
- Date: 2026-07-18
- Decision owners: AI TestPilot project
- Scope: LLM provider configuration, execution, provenance, and acceptance

## Context

AI TestPilot must prove a real structured-analysis path while retaining deterministic offline tests and fault injection. A mock is valuable for fast unit/regression work but cannot demonstrate authentication, network behavior, model limits, finish reasons, token metadata, latency, output quality, or cost. Silent fallback would make evidence and portfolio claims untrustworthy.

## Decision

DeepSeek is the first planned real provider behind a provider-neutral interface. Mock is a separate explicit adapter limited to unit, offline, fault-injection, and stable regression testing. Provider mode is selected deliberately and stored as `real` or `mock`; it is never inferred after the call.

A real call never silently falls back to Mock. A real timeout, authentication error, rate limit, invalid/truncated response, or validation failure remains a real failed/blocked/error attempt according to deterministic policy.

## Required provenance

UI, API data, database records, structured logs, evidence metadata, bugs, and reports must visibly identify provider mode. Real calls additionally record provider, model, prompt/schema versions, internal/provider request IDs, batch/idempotency IDs, start/completion/latency, token usage when supplied, retry count, finish reason, transport/response/validation/promotion states, and redacted errors.

Mock output uses unmistakable test provider/model identifiers and cannot be included in a report claiming real-provider acceptance.

## Offline test boundary

Mock may return valid fixtures and typed faults for orchestration, extraction, Schema/domain validation, batching, truncation detection, retry/backoff, idempotency, quarantine, merge, and UI-state tests. Fixtures are de-identified, versioned, and labelled. They do not satisfy the real-provider phase gate.

No test may patch provenance after execution or make mock data indistinguishable from real data.

## Real-call acceptance

Phase 5A requires separately authorized network access and an environment-supplied key. A bounded controlled suite must prove the real adapter, explicit model/config, metadata capture, redaction, schema/domain/reference validation, small-batch recovery, truncation handling, retry exhaustion, honest failure, and complete aggregate promotion. Cost and retry limits are configured before execution.

Phase 5A must pass before Phase 5B test generation. Mock success cannot unblock that gate.

## Consequences

### Positive

- Honest portfolio claims and explainable failures.
- Fast deterministic offline tests coexist with a real integration gate.
- Provider replacement does not change orchestration/domain contracts.
- UI/report users can assess data provenance immediately.

### Trade-offs

- More configuration, schema fields, UI badges, fixtures, and acceptance tests.
- Real tests incur network variability, cost, credentials, and rate limits.
- Developers cannot mask provider outages with a convenient fallback.

## Security

Keys come only from environment variables and never enter source, Git, prompts, databases, logs, screenshots, evidence, or reports. Raw responses are restricted, redacted, size/retention limited, and never automatically promoted. PRDs and model output are untrusted data; no model-authored code is executed.

## Validation

Later automated checks must prove mode immutability, explicit labelling across every surface, no fallback path, correct fault/state mapping, secret redaction, and refusal to treat mock records as real acceptance evidence. Phase 1 performs no provider call and implements neither adapter.
