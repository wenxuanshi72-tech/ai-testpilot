# Plugin PRD Analysis Results

Status: PHASE 5A PASS; audited real result recovered by offline deterministic revalidation.

## Preserved real-provider history

| Field                | Result                                                                       |
| -------------------- | ---------------------------------------------------------------------------- |
| Original run         | `ANR-1D213C2DB5204CE7BAF3850BDD72DF21`                                       |
| Original state       | FAIL; immutable (`SOURCE_EXCERPT_NOT_FOUND`)                                 |
| Original calls       | 6; unchanged                                                                 |
| Recovery child       | `ANR-7CFC7036BF8449E68A018B32665AA69C`                                       |
| Recovery child state | FAIL; immutable (`USERNAME_MINIMUM_SIX_MISSING`)                             |
| Recovery child calls | 1 real batch-2 call; unchanged                                               |
| Provider/model       | DeepSeek real / `deepseek-v4-pro`                                            |
| Saved response       | `LLC-78BF69480F9340E0AB13668230463626`; parsed JSON retained; hash unchanged |

The child response passed HTTP, provider, model, finish, truncation, JSON, source-block,
continuous-excerpt, Schema, and batch-domain checks. Its 19 candidates include the evidenced text
"minimum username length of six". Validator 2.0.0 nevertheless required an Arabic digit after a
lower-bound phrase, so the aggregate failure was a deterministic false negative. Neither failed
run was rewritten as PASS and no historical call or audit row was deleted or replaced.

## Offline revalidation

| Field                     | Result                                                 |
| ------------------------- | ------------------------------------------------------ |
| Attempt                   | `ORV-99F3490B3C1C4A9991B00C86D932AE88`                 |
| Provider status           | `offline_revalidation_of_real_result`                  |
| Validator                 | `aggregate-domain-validator@2.0.1`                     |
| New LLM calls             | 0                                                      |
| Candidate links           | 19 unique candidates                                   |
| Source-reference audits   | 19 retained                                            |
| Constraint audit          | `REQ-BAT-002-6` / `BLK-L0044-L0047-6F45D0B0A0` / valid |
| Formal requirements       | 19 unique IDs, atomically inserted                     |
| PRD version               | `PRDV-953F98F3BDDA42D3AE054C015018DB95`                |
| Requirement relationships | 4, all within the promoted aggregate                   |

The offline service re-read the saved real response and existing candidates, then reran source,
requirements@2.0.0 Schema, batch-domain, aggregate-schema, and aggregate-domain validation. It
created immutable links from the offline attempt to all candidates and wrote the constraint audit,
requirements, and relationships in one transaction. The parent remains at six calls, the child at
one call, and this attempt records `llm_call_count=0`.

## Final quality gates

| Gate                           | Result                                          |
| ------------------------------ | ----------------------------------------------- |
| Ruff format/check              | PASS                                            |
| Plugin and SUT mypy            | PASS                                            |
| Python default tests           | 118 passed, 22 deselected                       |
| Plugin implementation tests    | 73 passed, 1 real test deselected               |
| Plugin branch coverage         | 86.74 percent                                   |
| Schema and Prompt validation   | PASS                                            |
| SUT frontend tests             | 27 passed                                       |
| Plugin frontend tests          | 1 passed                                        |
| Prettier, ESLint, TypeScript   | PASS                                            |
| SUT and Plugin frontend builds | PASS                                            |
| Phase 3 API regression         | 20 passed, 1 strict XFAIL                       |
| Exact API-key scan             | 0 hits across Git-visible files and `plugin.db` |
| `.env` state                   | ignored and untracked                           |
| `verify_phase5a.ps1` offline   | PASS                                            |

No DeepSeek call or other network access was made during offline revalidation. No fuzzy matching,
semantic similarity, edit distance, manual requirement content, or Mock fallback was used. Phase
5B remains outside this acceptance.
