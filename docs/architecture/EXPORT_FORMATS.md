# Export Formats and Artifact Packaging

Status: Phase 0 design. No formal PRD, test result, bug, evidence, or report artifact is generated in this phase.

## Format policy

Each deliverable has a version-controlled or canonical source, an appropriate human-readable view, and a machine-readable representation where automation needs one. Every generated artifact records `schema_version`, `artifact_version`, generation time, source IDs/versions, MIME type, byte size, SHA-256, redaction status, and generator version in a manifest.

File existence alone never means generation succeeded. Writers render to a staging name, validate and hash the complete output, then atomically promote it and its manifest entry. Failed generation removes/quarantines staging files and records an explicit failure; it must not leave an incomplete file that looks formal.

## Deliverable matrix

| Deliverable | Canonical/source format | Human/review format | Required notes |
|---|---|---|---|
| PRD | Markdown (`text/markdown`) | PDF (`application/pdf`) | Markdown remains version-control source; PDF is formal presentation/archive |
| SRS | Markdown | PDF | Generated from approved structured requirements with source/version links |
| Structured requirements | JSON | CSV and/or XLSX | JSON is machine canonical; tabular views flatten without losing IDs |
| Test cases | JSON (preferred first implementation) or YAML | XLSX | Executable source uses unified protocol; XLSX supports review, not execution authority |
| Execution results | JSON | JUnit XML, redacted logs, evidence tree | JSON preserves native states/details; JUnit mapping is documented and lossy |
| Bug | JSON | Markdown plus evidence references | First release writes local files only; no external defect push |
| Test report | Markdown/canonical report model | HTML primary interactive view and PDF archive | All formats reconcile to the same immutable run data |
| Traceability matrix | JSON/canonical relationships | Markdown plus CSV/XLSX | Denominators, versions, orphan/stale state included |
| Playwright evidence | Evidence manifest | PNG, Trace ZIP; optional video/HAR | Redacted, size/retention controlled, linked by evidence ID/hash |

## Machine-format requirements

JSON is UTF-8, deterministic in field semantics, validated by a named schema version, and emits timestamps in UTC RFC 3339. YAML, if later supported for authored test specifications, uses a safe parser, forbids custom tags/anchors that create unsafe or ambiguous behavior, and normalizes to the JSON data model before validation.

CSV uses UTF-8 with a header row and RFC 4180-compatible quoting. Multi-value cells have documented JSON-string or joined representations and never replace the canonical JSON. XLSX uses frozen headers, filters, stable ID columns, validation lists for review fields, a legend/schema sheet, no macros, no external links, and escaped formula-leading user data.

JUnit XML maps `PASS` to a testcase without child failure, `FAIL` to `<failure>`, `ERROR` to `<error>`, and `SKIPPED` to `<skipped>`. `BLOCKED` maps to `<skipped>` with a typed property/message because JUnit lacks an equivalent; native JSON remains authoritative. XML is safely escaped and carries run/case IDs as properties.

HTML is self-contained or package-relative, applies Content Security Policy-compatible generation, escapes all untrusted content, and offers keyboard-readable tables behind charts. PDF is rendered from the validated report model and visually checked for missing pages, clipped tables, unreadable contrast, and broken evidence references.

## Naming convention

Portable lowercase kebab-case names use stable ID, artifact kind, version, and basic UTC timestamp where needed:

```text
<stable-id>--<artifact-kind>--v<artifact-version>--<YYYYMMDDThhmmssZ>.<ext>
```

Design examples:

```text
run-auth-001--results--v1--20260101T000000Z.json
bug-auth-001--bug--v1--20260101T000000Z.md
rpt-auth-001--report--v1--20260101T000000Z.html
evd-auth-001--screenshot--v1--20260101T000000Z.png
```

Names are display aids, not identity. Collision-resistant IDs and manifest hashes are authoritative. Filenames exclude usernames, secrets, free-form titles, drive letters, and unsafe/reserved characters.

## Version rules

`schema_version` identifies the data contract (for example `test-result@1.0.0`). `artifact_version` is a positive revision of a particular rendered artifact. Re-rendering byte-identical content may reuse a version; changed canonical data or presentation creates a new version and supersession link. Historical manifests remain immutable.

Breaking schema semantics increment major, backward-compatible additions increment minor, and corrections increment patch. Readers reject unsupported majors and never guess fields.

## Evidence directory

Runtime evidence is ignored by Git and addressed with project-relative POSIX-style manifest paths:

```text
artifacts/evidence/<project-id>/<run-id>/<result-id>/
├── manifest.json
├── api/
│   ├── request-summary.json
│   └── response-summary.json
├── ui/
│   ├── screenshot.png
│   └── trace.zip
└── logs/
    └── execution.log
```

Video (`video.webm`) and HAR (`network.har`) are optional and disabled unless their evidence value justifies privacy/size cost. Manifest paths use `/` regardless of host; code converts them safely under the configured root. Absolute paths, `..`, symlink escapes, and paths outside the root are rejected.

## Export package

```text
ai-testpilot-export--<project-id>--<timestamp>/
├── manifest.json
├── source/
│   ├── prd/
│   └── srs/
├── requirements/
├── test-cases/
├── runs/
│   └── <run-id>/
│       ├── results.json
│       ├── junit.xml
│       ├── logs/
│       └── evidence/
├── bugs/
├── reports/
└── traceability/
```

The package manifest lists every relative path, MIME type, byte size, SHA-256, schema/artifact versions, source record IDs, creation time, redaction state, and any intentionally omitted optional artifact. Validation rejects missing, extra, path-escaping, hash-mismatched, or incomplete files before the package becomes downloadable.

## Report and trace relationships

Markdown is the version-control-friendly narrative source; HTML is the primary interactive report; PDF is the formal snapshot. Tables, totals, statuses, trace IDs, and source run versions must reconcile across all three. Charts supplement rather than replace accessible tables.

Traceability Markdown is readable review material; CSV/XLSX supports filtering and audit. Rows include source/target IDs and versions, relationship type/state, approval, staleness, and evidence coverage rather than only titles.

## Redaction and privacy

Before serialization, structured redaction removes API keys, passwords, confirmations, session/token/cookie values, authorization headers, secret variables, and unnecessary personal information. Logs and text receive defense-in-depth pattern scanning after structured redaction. Screenshots, Trace, HAR, video, and PDFs follow dedicated redaction/review policy. Manifests never contain absolute local paths or secret values.

If safe redaction cannot be guaranteed, the artifact is blocked or restricted rather than exported as formal output.

## Local-only bug boundary

The first bug capability generates canonical JSON, readable Markdown, and relative evidence references on the local filesystem. It does not connect to Jira, GitHub Issues, chat tools, or any external system. A later connector requires separate scope, credentials, mapping, privacy, idempotency, and failure-design approval.
