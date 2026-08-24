# Run Artifact Bundle Contract

Status: design contract only; no new runtime Bundle is produced by this step.

## Layout

Every future formal execution Run owns one self-contained directory:

```text
artifacts/runs/<run-id>/
├── manifest.json
├── environment.json
├── execution.jsonl
├── action-tape.jsonl
├── results/
│   ├── api-results.json
│   └── ui-results.json
├── evidence/
│   ├── api/
│   ├── screenshots/
│   ├── traces/
│   ├── network/
│   └── console/
├── reproduction/
├── bugs/
└── reports/
```

Optional directories may be empty only when the manifest records an allowed omission. Files outside
the manifest invalidate a finalized Bundle. Absolute paths, drive letters, traversal segments,
symlink escapes, and paths outside the configured Artifact root are prohibited.

## Manifest responsibilities

`run-manifest@1.0.0` records:

- project, Run, environment, source commit, baseline, snapshot, case, executor, and protocol IDs;
- start/end time and finalization state;
- every Artifact's relative path, role, MIME, size, SHA-256, redaction and integrity state;
- authoritative Result IDs and optional source/reproduction Run relationship;
- whether Action Tape, Trace, screenshot, network and console evidence are required/present;
- the independently evaluated trust state;
- a bundle digest calculated after all member entries are finalized.

The bundle digest is calculated over canonical manifest content with `bundle_hash` omitted. It does
not replace member digests. Verification rejects duplicate paths, duplicate logical Artifact IDs,
unsupported schemas, missing/extra files, zero-byte mandatory evidence, or mismatched ownership.

## Atomic lifecycle

```text
create <run-id>.staging
→ write deterministic Result and evidence
→ redact and scan
→ validate member schemas
→ calculate member hashes
→ write canonical manifest
→ independently re-read and verify
→ atomically rename to <run-id>
→ persist finalized Bundle metadata
```

On failure, no formal `completed` Bundle is created. Staging data is quarantined or removed according
to policy and the execution becomes `ERROR`. A database commit and filesystem promotion must use a
recoverable protocol so neither side can falsely claim completion alone.

## Source and reproduction relationship

A reproduction Bundle is a new Run. It references the immutable source Run, Result, case version,
snapshot hash and Bug ID but owns new timestamps, evidence and hashes. It may not copy the original
Result or Evidence and call that reproduction.

## Privacy

Manifests never contain passwords, cookies, tokens, Authorization values, API keys, absolute local
paths or SQLite URLs. Sensitive input provenance records a logical source such as
`test_data.password` and the value `[REDACTED]`. Trace/HAR content requires dedicated scanning or is
blocked from formal export.
