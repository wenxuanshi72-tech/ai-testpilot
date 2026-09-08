# Playwright Evidence Enhancement

Status: authenticity hardening step 4 implemented and locally accepted.

Implementation: `plugin/backend/app/ui_execution.py` and
`schemas/evidence/v2/ui_execution_evidence.schema.json`.

## Evidence envelope

Every new UI Result receives a strict `ui-execution-evidence@2.0.0` envelope bound to its Run,
Result, case/version, immutable snapshot and executor version. It records the browser engine,
configured channel, browser version, headless mode, viewport and device scale factor.

The executor writes and hashes four evidence members per case:

- a full-page final or failure PNG;
- a Playwright Trace ZIP with screenshots and DOM snapshots enabled;
- a canonical JSON file containing allowlisted authentication network observations;
- a canonical JSON file containing captured console messages and page errors.

Each member receives a preallocated Artifact ID. The final deterministic assertion Action Tape
event references all four IDs. Route and click events reference the Trace and network IDs. A Run
Artifact Bundle can therefore register the same IDs and independently resolve every Tape reference.

## Credential boundary

Password fields are filled before tracing begins, so Playwright does not record password-bearing
`fill` action arguments. Trace source capture remains disabled. Trace screenshot/snapshot capture
starts immediately before the first submit click, preserving the resulting browser transition and
response evidence. Full-page screenshots rely on browser password masking.

Console and page-error text is bounded to 1,000 characters. Values used in password fields and
credential-like `password`, `token`, `cookie`, or `authorization` assignments are replaced with
`[REDACTED]`. Network evidence records method, path and status only; query strings, request bodies,
headers, cookies and response bodies are excluded.

## Failure behavior

Schema-invalid evidence, missing evidence bytes, hashing failures, browser failures or Trace
finalization failures prevent persistence as a completed UI Run. The exact uncommitted Run evidence
directory is removed on executor failure. Existing historical Runs and their evidence remain
unchanged and are not retroactively upgraded.

This step does not perform an independent real-browser reproduction, create a formal `VERIFIED`
Run, or change deterministic verdict ownership.
