# Phase 9 Local Bug Artifact Implementation

## Scope

Phase 9 consumes an immutable Phase 8 evidence consolidation and produces one local, traceable Bug
bundle. It does not call an LLM, push to an external defect tracker, execute tests, repair the seeded
defect, or implement Phase 10 reporting.

## Contracts and persistence

- Canonical bug schema: `canonical-bug@1.0.0`
- Bundle manifest: `bug-bundle@1.0.0`
- Database migration: `0011_bug_artifacts.sql`

`canonical_bug_records`, their source links, completed bundle metadata, and audit events are
append-only. The source gate requires authoritative `FAIL` classifications, a frozen approved case
version, intact requirement and project traceability, and verified evidence hashes. The
`test_data_invalid` classification is not eligible for `BUG-AUTH-001`.

## Export consistency

Canonical JSON is validated first. Markdown is rendered from that same in-memory record. A staging
directory receives JSON, Markdown, a redacted API evidence copy, and the manifest. Hashes and safe
content are verified before the complete directory is atomically renamed and the database record is
committed. Export failure therefore cannot create a completed database Bug.

UI attachments remain in the ignored Phase 7 evidence tree and are referenced by valid relative
links. No absolute workstation path, password, cookie, authorization value, model key, or SQLite URL
is allowed in the bundle.
