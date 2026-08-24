# Evidence Authenticity Contract Test Plan

Status: Step 1 contract acceptance; no runtime authenticity implementation is claimed.

## Scope

Validate the trust-model documents and three Draft 2020-12 JSON Schemas introduced for future Run
Bundles, Action Tape events and reproduction results. Tests are offline and create no database Run,
browser evidence, Bug, report, Provider call or network request.

## Required checks

1. Every Schema passes `Draft202012Validator.check_schema`.
2. A complete Run manifest with relative paths, provenance, required evidence and 64-character
   lowercase SHA-256 values passes.
3. Manifests reject absolute Windows/POSIX paths, traversal, unknown properties, duplicate Artifact
   paths, invalid hashes, missing provenance and an AI-owned trust decision.
4. A valid Action Tape event records ordered sequence, executor, case/snapshot, resolved action,
   before/after state, redaction and evidence references.
5. Action Tape rejects sequence zero, unsupported arbitrary actions, raw sensitive values, missing
   case ownership and unknown fields.
6. A valid reproduction result binds source and reproduction Runs, the same case version/snapshot,
   deterministic status, evidence and manifest hashes.
7. Reproduction rejects model verdicts, invalid status, missing source Result, malformed hashes and
   version drift.
8. Documentation defines `UNVERIFIED`, `EXECUTED`, and `VERIFIED` and explicitly states that hashes
   do not prove execution origin.
9. Documentation states that historical Runs are not retroactively upgraded.
10. `git diff --check`, formatting, sensitive-file scan and repository scope checks pass.

## Acceptance

Step 1 passes when all contract tests and existing quality gates pass, only documentation, schemas
and their tests change, and the work is committed independently. Later steps must implement these
contracts before creating the first eligible `VERIFIED` Run.
