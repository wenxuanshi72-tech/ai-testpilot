# Phase 10 Canonical Test Report Implementation

## Scope

Phase 10 reads persisted Phase 7 API/UI results, Phase 8 evidence and deterministic
classifications, and the Phase 9 canonical Bug. It does not recalculate a verdict, execute a test,
repair the seeded defect, start regression testing, invoke a model, or publish externally.

## Contracts

- Canonical report: `canonical-test-report@1.0.0`
- Report bundle: `test-report-bundle@1.0.0`
- Migration: `0012_test_reports.sql`

The immutable canonical record contains the complete result list, summary counts, classification
counts, evidence references, and formal Bug reference. Markdown, accessible HTML, and PDF are
rendered exclusively from that same record. Canonical JSON is also exported for machine use.

## Safety and consistency

- Source verdicts must equal the Phase 8 classification verdicts.
- Every result requires verified evidence with a revalidated SHA-256 hash.
- API evidence is copied into the ignored report bundle; UI evidence is referenced by a valid
  relative path.
- Dynamic HTML values are escaped. The page includes language metadata, a skip link, semantic
  sections, table caption and scoped headers, keyboard focus styling, and print styling.
- Passwords, cookies, Authorization values, model keys, SQLite URLs, and absolute local paths are
  rejected.
- Files are staged, hashed, moved as one directory, and only then committed to immutable database
  records. Export failure cannot create a completed report.

Runtime reports remain under ignored `artifacts/reports/`. Phase 11 regression work is outside this
phase.
