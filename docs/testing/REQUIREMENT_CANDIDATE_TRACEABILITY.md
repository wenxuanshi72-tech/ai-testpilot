# Requirement to Candidate Traceability

## Formal snapshot and slots

- Formal requirements: 19 unique IDs from one PRD version and one successful Phase 5A analysis.
- Snapshot hash: `bd9b20e687aadc6ccd5b17ad75f9e7ea52e5b32fe566509711142988dd1dbb0e`.
- Planned slots: 46 across API, UI, and Manual applicability.

Each deterministic slot binds one primary formal requirement ID/version/snapshot hash to one case type and deterministic case ID. The model may echo only the slot ID. The compiler derives all candidate requirement links from that exact slot, and aggregate coverage stores candidate IDs per formal requirement. Candidate semantic/full hashes and the collection hash allow Phase 6 to detect any change before review.

## BUG-AUTH-001 protection

The early trace name `REQ-AUTH-USERNAME-001` is not invented as a database foreign key. Runtime requires exactly one formal source-backed constraint where field is `username`, operator is `greater_than_or_equal`, value is `6`, and unit is `characters`. The current formal ID is `REQ-BAT-002-6`.

Its API/UI slots compile to `TC-API-AUTH-REG-005` and `TC-UI-AUTH-REG-005`, with username `z1234`, password `Test1234`, and rejection oracles; the API case requires HTTP 400. Zero or multiple constraint matches block promotion.

阶段5B产物尚未经过人工审核，不得直接用于正式执行；必须在阶段6批准和冻结后才能成为执行基线。
