# Phase 5B Test Generation Architecture

## Boundary

Phase 5B reads the 19 immutable Phase 5A requirements and may produce only a complete candidate collection in `validated_pending_review`. It does not review, approve, freeze, or execute candidates. Phase 6 alone owns human review and baseline freezing.

## Final C-lite pipeline

1. The deterministic planner snapshots requirement versions and hashes, determines API/UI/Manual applicability, and creates one immutable generation slot for each planned requirement/type pair.
2. Each slot owns `generation_slot_id`, formal requirement links, primary requirement, case type, deterministic case ID, and requirement snapshot. These fields never come from the model.
3. Explicit Real or isolated Mock returns `test-intent@2.9.0`: the exact slot ID plus semantic test content only. Real never falls back to Mock.
4. The response boundary rejects missing, duplicate, unknown, or cross-batch slots and any system-owned field.
5. `deterministic-candidate-compiler@2.29.0` injects IDs, trace/version metadata, draft lifecycle, timestamps, deterministic test-data names, and semantic/full hashes, then validates strict `test-cases@1.8.0`.
6. Existing domain, protected-defect, aggregate coverage, duplicate, conflict, and traceability checks run against the complete compiled collection.
7. Only a fully valid aggregate is saved atomically with links, validation/coverage results, findings, and audit events.

## Correction and completion reservation

One correction is eligible only after HTTP/JSON success and a parsed Intent Schema or deterministic compiler failure. It stays on the same batch and receives the exact redacted error. Before every paid call the guard reserves both call capacity and conservative cost for every unattempted initial batch. A correction cannot consume capacity needed to finish the initial plan. Network, authentication, truncation, budget, and sensitive-data failures are terminal.

The offline plan contains 46 slots in 17 initial batches (API 7, UI 6, Manual 4). With 18 calls, one correction per failed batch, 3,072 output tokens, and a US$0.065000 cap, the shared reservation calculation allows one global correction slot and caps conservative worst cost at US$0.062494.

## Protected seeded defect

`REQ-BAT-002-6` resolves deterministically to the username minimum-six rule. Its API/UI slots compile to `TC-API-AUTH-REG-005` and `TC-UI-AUTH-REG-005`, using `z1234` and `Test1234` and expecting rejection; the API oracle requires HTTP 400. The compiler does not repair the intentionally defective SUT.

## Active versions

- Prompt: `test-generation@3.0.0`
- Model-output Schema: `test-intent@2.9.0`
- Candidate Schema: `test-cases@1.8.0`
- Planner: `test-generation-capacity-planner@2.0.0`
- Compiler: `deterministic-candidate-compiler@2.33.0`
- Parser: `test-generation-json-parser@1.0.0`

阶段5B产物尚未经过人工审核，不得直接用于正式执行；必须在阶段6批准和冻结后才能成为执行基线。

Unresolved API targets are preserved explicitly as draft candidates with `N/A`, empty path, or status `0`, audited as pending Phase 6 resolution. They are not executable and must be completed or rejected before approval and freezing.
