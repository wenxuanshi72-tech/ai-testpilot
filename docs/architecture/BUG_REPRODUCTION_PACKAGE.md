# Bug Reproduction Package

Status: authenticity hardening step 5 implemented and locally accepted.

Implementation: `plugin/backend/app/bug_reproduction.py`.

## Purpose

A reproduction claim must be derived from a second deterministic Run, not from copying the original
failure or restating a Bug narrative. `BugReproductionPackageWriter` consumes two finalized Run
Artifact Bundles: the source failure and an independently identified reproduction Run.

The reproduction Bundle must contain an exact `source_run` link to the source Run ID, Result ID and
Manifest hash. Both Bundles are independently verified before comparison. The selected Result
artifacts use `reproduction-observation@1.0.0`, which records executor-owned status, expected and
actual facts, case/version, snapshot ID/hash and deterministic authority.

## Deterministic status

The runner requires the source observation to be `FAIL` and requires executor, case, case version,
snapshot ID/hash and expected oracle to remain identical.

- `REPRODUCED`: the second Run is also `FAIL` with the same actual observation.
- `NOT_REPRODUCED`: the second Run completes without the same failure, including `PASS` or a
  different actual observation.
- `BLOCKED`: the second execution is `BLOCKED` or `SKIPPED`.
- `ERROR`: the second execution is `ERROR`.

AI output cannot supply or override these states.

## Package layout and hash boundary

```text
<bug-id>--<reproduction-run-id>/
|-- package-manifest.json
|-- reproduction-result.json
|-- source-run/
`-- reproduction-run/
```

The outer `bug-reproduction-package@1.0.0` Manifest lists every member except itself with its byte
size and SHA-256, plus a canonical package hash calculated with `package_hash` omitted. Excluding the
outer Manifest from its own member list avoids a circular digest. The reproduction Result remains
outside the reproduction Run Bundle because it contains that Bundle's finalized Manifest hash.

Standalone verification checks the exact file set, member hashes, both nested Bundles, source link,
observation schemas, unchanged oracle/version, reproduction Action Tape hash, evidence Artifact
references and final deterministic status. Known portfolio secret markers fail closed. Creation uses
same-root staging, atomic promotion and a second post-promotion verification; failure removes both
staging and promoted output.

This step implements the package and verifier. It does not execute a new real reproduction Run,
alter historical evidence, update Bug lifecycle state, or claim that an existing Bug is verified.
