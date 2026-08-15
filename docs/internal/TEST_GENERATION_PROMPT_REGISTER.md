# Test Generation Prompt Register

## Active contract

- Prompt: `test-generation@3.0.0`
- Prompt hash: `00f264ae89c4f8724469a249b57893b2e17c1d0717e604f87719cf2837425e55`
- Model-output Schema: `test-intent@2.9.0`
- Intent Schema hash: `44058ea133f732a54a8c1b6e68dbbe84743cb473d613730fc558e3eb65efa657`
- Candidate Schema: `test-cases@1.8.0`
- Candidate Schema hash: `2261d9996b5bada0e95f6bbf58a6443b05373d99ec05fdc8d0f81272e82437d1`
- Compiler: `deterministic-candidate-compiler@2.29.0`
- Compiler file SHA-256: `964cbdca256b942a81a60106dd3c6783a74073e7b351408f0888ff92dcadbf3c`
- Provider/model: explicit DeepSeek Real / `deepseek-v4-pro`, or explicit Mock for offline tests
- Compatibility policy: `authorization` is accepted and deterministically compiled as `security`; `functional` is preserved as the independent candidate category `functional`; `test_data[].value` accepts string or `null`; canonical and descriptive API session semantics, missing request bodies, empty semantic values, and structured or action/instruction setup requests are normalized deterministically with field-level audit; API-only fields are not injected into UI or Manual intents.
- Compatibility audit: the parsed artifact retains the model value, while `intent_batch_compiled` records the slot, field, rule, original type/value category, accepted category/type, and `test-intent-compatibility@1.28.0`.

API, UI, and Manual prompts each contain one complete legal semantic example. The only identifier the model may return is an allowed `generation_slot_id`; requirement IDs, case/type IDs, run/batch metadata, states, timestamps, hashes, links, and audit fields are forbidden. Corrections replace the complete same-batch Intent response and receive only an exact redacted error.

## Immutable history

Thirty-three real runs remain failed and unchanged. The entries below document the early compatibility lineage; the immutable database is the authoritative complete run ledger:

- `TGR-4D22911C1E834A96A0B8E5698B8F361D`: `test-generation@1.1.0`, one call, US$0.001272.
- `TGR-9DEB7862E2A74334BCF410CD9BDF33F4`: `test-generation@1.2.0`, one call, US$0.002285.
- `TGR-DAEE71B0D35B40E69B4E4D6977A20203`: `test-generation@2.0.0`, five calls, US$0.008120.
- `TGR-935E45F6F0C54D168164ED7624AC2BCE`: `test-generation@3.0.0`, two calls, US$0.003617; initial `null` test data and corrected `authorization` scenario remained invalid under the historical `test-intent@2.0.0` contract.
- `TGR-321AFADB60824411A88EE515067C5C98`: `test-generation@3.0.0`, two calls, US$0.003697; the corrected response returned `scenario_type=functional`, which remained invalid under the historical `test-intent@2.1.0` contract.

- `TGR-AF476B12F88D4E1FA364DD71248051CE`: `test-generation@3.0.0`, two calls, US$0.002472; both parsed responses used unrecognized historical `session_semantics` aliases under `test-intent@2.2.0`.

- `TGR-FF93F9BB2709494887F7664F9C8D9E62`: `test-generation@3.0.0`, two calls, US$0.002938; historical Intent 2.3 rejected missing request bodies, an empty semantic value, additional session aliases, and structured setup requests.

- `TGR-46639D1B2D434E96B7939F79EAE53BE7`: `test-generation@3.0.0`, one zero-cost provider-network attempt; no candidates.

- `TGR-70CEAFDD92F745129EEFAA16B6C90AB9`: `test-generation@3.0.0`, two calls, US$0.003210; historical Intent 2.4 rejected descriptive session values and action/instruction setup objects.

- `TGR-D061A0FF4EA84BBCB88186457FBEDF4B`: one zero-cost provider-network attempt; no HTTP response and no candidates.

- `TGR-5CF97692E19044D9904B28CE77065D22`: one HTTP 200 response costing US$0.001350 failed because `cleanup_intent` was missing; the single correction attempt timed out at zero cost.

- `TGR-3DF2DF8350504E53B8A6E95E04EA1DDC`: API-001 validated; API-002 initial and correction responses cost US$0.005432 and failed on the model term `quality`, followed by an invalid `N/A` API correction.

Historical total is US$0.034393 across twenty-four recorded real-call attempts. Responses, parsed data, usage, errors, lineage, and audit records are not rewritten or represented as successful output.

Unresolved API targets are preserved explicitly as draft candidates with `N/A`, empty path, or status `0`, audited as pending Phase 6 resolution. They are not executable and must be completed or rejected before approval and freezing.
