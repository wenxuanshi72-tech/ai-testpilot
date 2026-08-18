# Plugin Canonical Test Report Results

## Result

Phase 10 acceptance: **PASS**.

- Report record: `RPT-BE5D133ABFB54EF2A4AFEFC82D86A189`
- Source API run: `RUN-71ED569CD73643E5B19F48BCFCD0FBEF`
- Source UI run: `UIR-7169E1697F86400EBAE8AFBBBD5675B4`
- Evidence consolidation: `ECR-9CAB97E4B01249E0B0C42CB56761F15A`
- Canonical Bug: `BUGR-B4E714D0B26843EF912A65B224ACFC32` / `BUG-AUTH-001` v1
- Results: 10 (7 PASS, 3 FAIL; API 7, UI 3)
- Other statuses: 0 BLOCKED, 0 ERROR, 0 SKIPPED
- Classifications: 7 `none`, 2 `seeded_product_bug`, 1 `test_data_invalid`
- Evidence: 13

## Runtime artifact hashes

- Canonical JSON: `f6db440e4585e2200461a5b81b394001c8e5024ebfb82e45be12a52bbd2db26e`
- Markdown: `f579e77064e309be9723ed488dd4daea42c0031c8524486d5a57dce8bb41b1fc`
- HTML: `4eafa78c70f53d40b410043ed7d0d1b7543f6c6a1cca6edb4cecfaf7e7fd52a5`
- PDF: `253881fd554dafc703130093cd6aef338ed05669e52656adee15312922fddbfd`
- Manifest: `edb8263c1ced667db416b2856b076e87f5e9e03ec55c12ecc0538ae3c78d532b`
- Manifest recomputation for JSON/Markdown/HTML/PDF: PASS

The runtime bundle is ignored under `artifacts/reports/` and is not committed.

## PDF and accessibility review

- PDF pages: 3
- Text extraction: PASS
- All pages rendered at 1072 x 1516 pixels for visual QA.
- Visual inspection: PASS; no clipping, overlap, missing page, unreadable text, or corrupt glyph.
- Header hierarchy, result table, evidence index, footer, and page numbers are visible.
- HTML escaping and accessibility structure: PASS.

## Data and phase boundaries

- SQLite integrity: `ok`
- Foreign-key violations: 0
- Migrations: 12 (`0001` through `0012`)
- DeepSeek calls: 0
- External publication: 0
- Verdict recalculation: 0
- Seeded defect repair: 0
- Regression execution: 0

- Phase 10 focused tests: 4 passed.
- Plugin backend: 270 passed, 1 deselected.
- Plugin backend coverage: 87.93% (required 80%).
- Phase 11 was not started.
