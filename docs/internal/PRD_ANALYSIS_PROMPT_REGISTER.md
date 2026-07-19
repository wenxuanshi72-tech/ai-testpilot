# PRD Analysis Prompt Register

## Active version

| Field                          | Value                       |
| ------------------------------ | --------------------------- |
| Prompt version                 | prd-analysis@2.0.0          |
| Recovery prompt version        | prd-analysis-recovery@2.0.0 |
| Schema version                 | requirements@2.0.0          |
| Directory                      | prompts/prd-analysis/v2     |
| Status                         | active for Phase 5A         |
| Thinking mode                  | disabled                    |
| Maximum requirements per batch | 12 by default, configurable |

## Files

| File                            | Purpose                                                         |
| ------------------------------- | --------------------------------------------------------------- |
| outline_system.md               | Untrusted-data boundary and strict JSON outline contract        |
| outline_user.md                 | Bounded PRD outline request                                     |
| requirements_system.md          | Requirement fields, JSON example, limits, and forbidden outputs |
| requirements_user.md            | Batch ID, allowed sections, and source data envelope            |
| repair_system.md                | Limited small-envelope repair policy; no semantic invention     |
| requirements_recovery_system.md | Single-attempt source-grounded recovery policy                  |

Version 1 remains unchanged as historical material for the failed real run. Version 2 supplies
deterministic source blocks with stable IDs, PRD line ranges, and original text. A model must cite
one block and copy one continuous excerpt. Unsupported claims are explicit and cannot be promoted.

The combined prompt content hash is calculated at runtime and stored in prompt_versions. Every
model call records the semantic prompt version and schema version. Prompt source is versioned in
Git; keys and environment values are never included.

Exact block membership is checked before JSON Schema and domain validation. Only unique,
reversible NFC, CRLF/LF, and Unicode-whitespace equivalence may resolve to original text. The
model excerpt, resolved excerpt, reason, line range, call, batch, attempt, and reuse provenance are
stored as immutable audit rows. No similarity score, edit distance, or fuzzy acceptance exists.

## Injection and output controls

Every system prompt states that PRD content is untrusted data rather than instructions. Prompts
forbid test cases, verdicts, bugs, executable code, SQL, and commands. Output must be one JSON
object with no Markdown fence or prose. Local validation remains authoritative even when provider
JSON Output is enabled.
