# Test Case Candidate Contracts

## Three boundaries

The system-owned generation slot contains all identity, requirement, type, run/batch, version, and deterministic case-ID data. DeepSeek returns only the compact semantic protocol `test-intent@2.5.0`: `generation_slot_id`, title, objective, priority/risk/scenario, preconditions, semantic test data, actions, expected outcomes, cleanup intent, tags, and type-specific semantics.

The local compiler produces strict `test-cases@1.5.0`. It injects formal requirement links, primary requirement, case/type/step/data IDs, trace metadata, `draft` review status, lifecycle state, timestamps, and semantic/full hashes. No model field can override system ownership. Semantic content is not guessed, fuzzily repaired, or rewritten to pass validation.

## Validation order

1. Strict JSON object parsing and truncation detection.
2. Exact `{"intents":[...]}` envelope and model-owned field boundary.
3. `test-intent@2.5.0` Schema.
4. Exact slot-set equality: no missing, duplicate, unknown, or cross-batch slot.
5. Deterministic compilation from the matched immutable slot.
6. `test-cases@1.5.0` Schema.
7. Candidate domain and protected-defect rules.
8. Aggregate coverage, duplicate, conflict, and traceability checks.
9. Atomic persistence of the complete collection.

The semantic hash is stable for the same slot and semantic Intent; the full content hash also binds injected system metadata. Candidates remain `draft` and collections remain `validated_pending_review`. Phase 5B cannot create APPROVED or FROZEN records.
