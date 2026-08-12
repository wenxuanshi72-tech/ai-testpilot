# Plugin Test Generation Results

## Current verdict

**PHASE 5B FINAL PRE-REAL HARDENING: PASS; ONE AUTHORIZED REAL RUN PENDING**

The C-lite generation-slot architecture, semantic Intent boundary, deterministic compiler, and completion-reserving budget guard are implemented offline. This task did not call DeepSeek, migrate or write the real database, promote candidates, commit, push, or enter Phase 6. A later separately authorized real acceptance is still required for Phase 5B PASS.

## Immutable failed real history (selected lineage)

| Run                                    | Parent     | Prompt                  | Calls |        Cost | Result               |
| -------------------------------------- | ---------- | ----------------------- | ----: | ----------: | -------------------- |
| `TGR-4D22911C1E834A96A0B8E5698B8F361D` | none       | `test-generation@1.1.0` |     1 | US$0.001272 | failed, 0 candidates |
| `TGR-9DEB7862E2A74334BCF410CD9BDF33F4` | first run  | `test-generation@1.2.0` |     1 | US$0.002285 | failed, 0 candidates |
| `TGR-DAEE71B0D35B40E69B4E4D6977A20203` | second run | `test-generation@2.0.0` |     5 | US$0.008120 | failed, 0 candidates |
| `TGR-935E45F6F0C54D168164ED7624AC2BCE` | third run  | `test-generation@3.0.0` |     2 | US$0.003617 | failed, 0 candidates |
| `TGR-321AFADB60824411A88EE515067C5C98` | fourth run | `test-generation@3.0.0` |     2 | US$0.003697 | failed, 0 candidates |
| `TGR-AF476B12F88D4E1FA364DD71248051CE` | fifth run  | `test-generation@3.0.0` |     2 | US$0.002472 | failed, 0 candidates |
| `TGR-FF93F9BB2709494887F7664F9C8D9E62` | sixth run  | `test-generation@3.0.0` |     2 | US$0.002938 | failed, 0 candidates |
| `TGR-46639D1B2D434E96B7939F79EAE53BE7` | seventh run | `test-generation@3.0.0` |     1 | US$0.000000 | failed, provider network |
| `TGR-70CEAFDD92F745129EEFAA16B6C90AB9` | eighth run  | `test-generation@3.0.0` |     2 | US$0.003210 | failed, intent schema |
| `TGR-D061A0FF4EA84BBCB88186457FBEDF4B` | ninth run   | `test-generation@3.0.0` |     1 | US$0.000000 | failed, provider network |
| `TGR-5CF97692E19044D9904B28CE77065D22` | tenth run   | `test-generation@3.0.0` |     2 | US$0.001350 | failed, schema then timeout |
| `TGR-3DF2DF8350504E53B8A6E95E04EA1DDC` | eleventh run | `test-generation@3.0.0` |     3 | US$0.005432 | failed, API-002 terminology |

Current read-only database total is thirty-three failed Real runs, one hundred sixty-five recorded Real-call attempts, and US$0.224759. All statuses, response/parsed records, usage, errors, lineage, and audit events remain immutable. No old run is relabelled or reused as a successful candidate set. The latest run is `TGR-C3E5F6A2E51E4F198ED8D85B2C227116`, linked to `TGR-C6053F1621D943E3B0FCE8D9B15AEA96`.

## Active offline architecture

- Prompt: `test-generation@3.0.0`, hash `00f264ae89c4f8724469a249b57893b2e17c1d0717e604f87719cf2837425e55`
- Model output: `test-intent@2.9.0`, hash `44058ea133f732a54a8c1b6e68dbbe84743cb473d613730fc558e3eb65efa657`
- Candidate: `test-cases@1.8.0`, hash `2261d9996b5bada0e95f6bbf58a6443b05373d99ec05fdc8d0f81272e82437d1`
- Compiler: `deterministic-candidate-compiler@2.29.0`, file SHA-256 `8238cee269bc75344c46090b9009d8fc807dff80f12853d7b8ee8cc96725e75d`
- Compatibility: `authorization` compiles deterministically to candidate category `security`; `functional` remains the independent candidate category `functional`; nullable semantic test-data values remain `null`; canonical and descriptive API session semantics, missing request bodies, empty values, and structured or action/instruction API setup semantics are normalized deterministically; UI and Manual intents are not given API-only fields; a completely missing cleanup intent is deterministically represented as no cleanup, and the model term `quality` is deterministically categorized as `functional`. All decisions produce field-level compatibility audit records under `test-intent-compatibility@1.28.0` without rewriting the parsed artifact.
- Model owns semantics only; the exact immutable slot owns every identity, requirement, case/type, trace, lifecycle, timestamp, and hash field.
- Exact slot-set validation forbids omissions, duplicates, unknown/cross-batch IDs, and model-owned system metadata.
- Promotion remains complete-aggregate-only and atomic.

## Read-only real dry-run

- Requirement count/hash: 19 / `bd9b20e687aadc6ccd5b17ad75f9e7ea52e5b32fe566509711142988dd1dbb0e`
- Slots/batches: 46 / 17 (API 7, UI 6, Manual 4)
- Limits: 18 calls, one correction total under reservation, 3,072 output tokens, US$0.065000
- Initial conservative worst cost: US$0.058922
- Conservative worst with one correction: US$0.062494
- Capacity: input 2,065/2,100; output 1,738/2,304
- Side effects: provider calls 0; database writes 0

## Offline evidence

- Ruff format/check: PASS.
- mypy: PASS, 50 Plugin source files.
- Plugin backend after compatibility update: PASS, 144 passed and 1 paid real-provider test skipped in 36.23 seconds.
- SUT frontend Vitest: PASS, 27/27; Plugin frontend Vitest: PASS, 1/1.
- TypeScript, ESLint, and Prettier check: PASS.
- SUT and Plugin production builds: PASS.
- Phase 3 API black-box regression: PASS, 20 passed and `BUG-AUTH-001` remained the expected XFAIL.
- Empty 0001-to-0005 migration and 0003-to-0005 upgrade: PASS; integrity `ok`, zero foreign-key findings, no Phase 6 tables.
- Real database read-only audit: PASS. Actual parent column is `resume_source_run_id`; thirty-three immutable FAIL runs, one hundred sixty-five Real calls, 224,759 microusd, 19 requirements, zero candidates/links, migrations 0001-0005, integrity `ok`, and zero foreign-key findings.
- Plugin backend after the 2.19 compatibility update: PASS, 168 passed and 1 paid real-provider test deselected.
- Read-only recovery dry-run against the latest failed run: PASS; 46 slots, 17 initial batches, zero reusable batches, 18-call cap, one correction slot, US$0.062494 conservative worst cost, provider calls 0, database writes 0.
- Disk/Registry/dry-run hashes, tests, and document register: PASS.
- Secret scan, `.env` ignore/untracked, `git diff --check`, scope, ROADMAP/SUT boundary, ports, process, and temporary cleanup: PASS.

## Phase boundary

## Final pre-real hardening evidence (2026-08-12)

- Current-version replay of all 175 historical call records: 22 direct passes, 131 deterministic-normalization passes, 10 structure-correction cases, 9 deterministic rejects, and 3 provider attempts with no response artifact. No historical artifact has the current Prompt+Intent-Schema hash pair, so none is promoted or treated as a current result.
- Current-version replay of the latest three runs requires one structure correction per run. The run limit of eight corrections is evidence-backed and leaves margin; each batch remains limited to one correction.
- Provider transient retry is independent: one retry per batch, three per run, only for 429/500/502/503/504 and recognized timeout/network interruption classes. Authentication, configuration, deterministic 400, schema, compiler, candidate, database, and budget failures are not retried.
- A complete HTTP-200, `finish_reason=stop`, non-truncated, bounded, non-HTML malformed JSON response may consume the batch's sole structure-correction slot. Empty, truncated, abnormal-finish, HTML/provider-error, or oversized responses cannot.
- Token evidence keeps `max_tokens=3072`: output-token P95 plus 20 percent is API 2,499, UI 2,298, and Manual 1,948; the observed successful maximum is 2,607.
- Deterministic plan: 19 requirements, 46 slots, 17 batches (API 7, UI 6, Manual 4). Hard limits are 17 initial calls + 8 structure corrections + 3 Provider retries = 28 calls and US$0.250000. Conservative dry-run worst cost is US$0.099365, so initial-batch reservation cannot prematurely exhaust the hard budget.
- Fixed assets: Prompt `test-generation@3.0.0` / `7b884c9d3b23484462dedd4963bc4189c3c898e7d5419b5bb9f1d377d3d933e5`; Intent Schema `test-intent@2.9.0` / `44058ea133f732a54a8c1b6e68dbbe84743cb473d613730fc558e3eb65efa657`; Candidate Schema `test-cases@1.8.0` / `2261d9996b5bada0e95f6bbf58a6443b05373d99ec05fdc8d0f81272e82437d1`; Compiler `deterministic-candidate-compiler@2.29.0` / `8238cee269bc75344c46090b9009d8fc807dff80f12853d7b8ee8cc96725e75d`; Compatibility `test-intent-compatibility@1.28.0`.
- Minimal empty-route patch: the UI-003 model artifact supplied `/register, /login`; the former compatibility path produced an empty route. The UI-only normalizer now produces `/`, all three UI-003 candidates pass the full offline chain, and UI-002/API-005 regressions remain passing. Safe audit rules are `empty_ui_route_to_root` and `multi_route_string_to_reviewable_root_route`.
- Budget scope is per run: the guard starts at zero and the service queries only the current `test_generation_run_id`. Historical and parent costs remain audit-only; a current run is blocked when its own cost reaches US$0.250000.
- Patch gates: 194 passed, 1 paid-provider test deselected; Ruff and mypy PASS; SQLite remained 35 runs, 186 calls, zero candidates/links, integrity `ok`, and zero foreign-key findings. DeepSeek, run, and database-write increments were zero.
- Final offline gates: Plugin backend 188 passed and 1 paid-provider test deselected; Ruff format/check PASS; mypy 27 application source files PASS; dry-run PASS with zero Provider calls and zero database writes; SQLite integrity `ok`, zero foreign-key findings, 34 historical runs, 175 calls, zero candidates, and zero links; `git diff --check` and secret/file-ignore checks PASS.

Formal candidates: 0. APPROVED records: 0. FROZEN baselines: 0. No candidate was executed. ROADMAP, SUT, migrations 0001-0005, and the real Phase 5A/5B database history remain unchanged. Migration 0006 does not exist. Phase 6 has not started.

阶段5B产物尚未经过人工审核，不得直接用于正式执行；必须在阶段6批准和冻结后才能成为执行基线。

Unresolved API targets are preserved explicitly as draft candidates with `N/A`, empty path, or status `0`, audited as pending Phase 6 resolution. They are not executable and must be completed or rejected before approval and freezing.
