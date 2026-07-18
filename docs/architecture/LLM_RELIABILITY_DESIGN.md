# LLM Reliability Design

Status: Phase 0 design and later acceptance requirements. No provider has been called in Phase 0.

## Reliability objective

Real-model output is probabilistic, length-limited, and untrusted. The system must convert it into complete, attributable, versioned candidate data without presenting truncation, invalid JSON, mock output, or partial recovery as success. One 8,192-token response is not a reliable strategy for a full structured PRD analysis.

Submitting an entire malformed JSON response to another model call for repair is not the primary solution. Reliability comes from small bounded units, deterministic validation, durable checkpoints, and retrying only the failed unit.

## Provider abstraction and separation

`LLMProvider` receives a normalized request containing provider mode, model, prompt messages, response/schema expectation, token budget, timeout, request/correlation/idempotency IDs, and redaction context. It returns raw content and transport/status/finish/token/timing metadata, or a typed provider failure.

`DeepSeekProvider` is the first planned real adapter. Its model ID is explicit configuration, not hard-coded policy. It never reads a key except from the environment and never logs it.

`MockProvider` is permitted only for unit, offline, contract, fault-injection, and stable regression tests. Mock records carry `provider_mode=mock` in the API, database, logs, UI, and exports. A real request cannot silently fall back to mock. A real outage/invalid response is recorded truthfully as failure.

## Prompt and schema versioning

Prompts are immutable named versions with semantic version, content hash, use case, compatible schema majors, status, and change rationale. Schemas are independently versioned and validated before provider use. A call records both exact versions and hashes. Prompt or schema changes require regression fixtures and cannot reinterpret historical calls.

## Call log and raw response policy

Every attempt records provider/mode/model, prompt/schema versions, internal and provider request IDs, batch/idempotency IDs, start/end/latency, requested maximum output tokens, token usage when supplied, retry number, HTTP/status, finish reason, extraction/schema/domain/promotion states, typed error, and redacted diagnostic.

Raw responses are restricted diagnostic evidence, never formal business data. They are encrypted/permission-restricted where supported, size-capped, assigned short configurable retention, excluded from normal UI/export, and redacted before diagnostic use. Keys, authorization headers, source credentials, and unnecessary personal data are never retained.

## PRD sizing, outline-first planning, and token budget

Deterministic preprocessing normalizes encoding, fingerprints content, measures characters/sections/tables, estimates input tokens with a conservative model-specific estimator plus safety margin, and classifies document size. It reserves budget for system instructions, schema, source excerpt, response, and provider overhead.

The first controlled task produces a document overview and section index, not all requirements. Subsequent tasks analyze stable source ranges by section or requirement batch. Default design limits are configurable and acceptance-tested:

- no more than 20 candidate requirements per requirement batch;
- no more than 25 candidate test cases per generation batch;
- input and expected output must remain below a configured fraction of context/output limits;
- one source section may be split further; unrelated sections are not combined merely to reduce calls.

Limits are operational guardrails, not proof of completeness. The aggregate is accepted only after coverage and reference checks.

## Resumable pipeline

1. Persist PRD version/hash and analysis configuration.
2. Estimate size and create a stable outline/section index.
3. Plan batches with stable IDs, source ranges, expected coverage, and content hashes.
4. For each pending batch, create an idempotent provider attempt.
5. Validate transport and truncation signals before parsing.
6. Extract exactly one bounded JSON value.
7. Run structural, schema, and domain validation.
8. Promote a valid batch to validated staging; quarantine an invalid batch.
9. Apply only allowlisted deterministic formatting repair.
10. Retry the current failed batch when policy permits; never regenerate already validated batches.
11. Normalize IDs, deduplicate, merge in stable order, and validate the full aggregate.
12. Promote only the complete aggregate to candidate business tables for human review.

Durable batch checkpoints allow continuation after process interruption. A resumed run compares input/config/prompt/schema hashes; incompatible changes create a new run rather than mixing versions.

## Truncation detection

A response is incomplete if any independent signal indicates risk:

- HTTP/transport failure or missing body;
- provider `finish_reason` equivalent to length/max-token termination;
- output token use reaches or closely approaches the requested maximum;
- JSON cannot be closed by a strict parser;
- closing delimiter, required terminal marker, required field, or list entry is missing;
- declared counts disagree with items;
- a list/object ends suspiciously mid-field;
- schema, source-coverage, or reference-integrity validation fails.

`finish_reason=stop` is necessary when available but not sufficient. An apparently closed JSON object can still be semantically truncated.

## JSON extraction and validation

Extraction removes only a permitted Markdown fence and leading/trailing explanatory text when exactly one JSON value can be located within configured size/depth limits. It does not use `eval`, execute embedded content, or guess multiple competing objects.

Validation order is:

1. UTF-8/size/depth and JSON closure;
2. required fields, types, enums, lengths, counts, and additional-property policy;
3. versioned JSON Schema;
4. domain rules such as stable source references, unique IDs, valid priorities, and bounded items;
5. cross-item and cross-batch reference integrity;
6. aggregate source coverage and expected-count reconciliation.

## Quarantine and limited repair

Invalid raw and parsed candidates enter a quarantine record with failure stage and diagnostics; they do not enter approved/candidate business tables. Deterministic repair is limited to unambiguous envelope faults such as removing one recognized code fence or surrounding prose. It does not invent missing fields/items, change meaning, fabricate references, or close substantially truncated structures.

Optional model-assisted repair may be researched later only for a small isolated invalid fragment, with separate provenance and the same full validation. It never replaces bounded generation and cannot promote data directly.

## Retry, backoff, and failure states

Only retry typed transient failures (timeouts, selected `429`/`5xx`, transport interruption) or a small invalid batch under regeneration policy. Use configurable exponential backoff with jitter and provider hints, capped delay, and a default maximum of two retries after the first attempt. Authentication/configuration errors, unsafe input, and unsupported schemas are not blindly retried.

The idempotency key derives from run, batch, prompt/schema/config, and source hashes. A duplicate request reuses its durable result. Successfully validated batches are immutable and skipped on resume. Retry exhaustion produces explicit `failed`; environment/configuration/precondition absence may be `BLOCKED`, while an attempted provider/pipeline malfunction is `ERROR`. These orchestration states never become test verdicts.

## ID normalization, deduplication, and merge

The model proposes local candidate keys; deterministic code assigns or reconciles stable domain IDs from normalized source anchors and review history. Regeneration cannot arbitrarily drift an existing approved ID. Normalization standardizes whitespace, casing rules, enums, and source spans without changing semantics.

Deduplication combines exact fingerprints and reviewable similarity signals; AI similarity alone never deletes an item. Merge order follows outline/source position plus stable ID. Conflicts, duplicate IDs, missing batches, invalid references, orphaned relationships, count mismatches, or incompatible versions fail aggregate validation.

## Promotion rules

Data moves through `raw_response -> extracted_candidate -> quarantined_or_validated_batch -> validated_aggregate -> review_candidate -> approved_version`. Each promotion is an atomic transaction with source and provenance links. Only a complete, schema-valid, domain-valid, reference-complete aggregate enters candidate business tables; only human-approved versions become approved records.

Partial results may be visible in an explicitly labelled diagnostic progress view but cannot be exported or consumed as a complete requirement set.

## Honest failure and phase gate

A real DeepSeek failure records its real provider mode, error category, retry history, and redacted diagnostic. The UI and reports cannot display it as successful, substitute mock content, or claim a model capability was verified.

Phase 5A must demonstrate the real provider path, bounded pipeline, truncation detection, validation, recovery, aggregate integrity, provenance, and explicit failures before Phase 5B case generation begins. Phase 0 merely defines this gate.
