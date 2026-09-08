# Action Tape Runtime Implementation

Status: authenticity hardening step 3 implemented and locally accepted.

Implementation: `plugin/backend/app/action_tape.py`, with deterministic executor integration in
`plugin/backend/app/api_execution.py` and `plugin/backend/app/ui_execution.py`.

## Runtime contract

Each Action Tape is canonical newline-delimited JSON. Every line independently validates against
`action-tape-event@1.0.0` and binds an ordered event to one Run, Result, case/version, frozen
snapshot and executor. Sequence numbers begin at one and remain contiguous. Event IDs are unique,
ownership fields cannot change within a Tape, and the finalized bytes receive a SHA-256 digest.

The writer accepts only protocol-enumerated actions. API execution records setup/test HTTP requests,
fixture operations when used, and the final deterministic assertion outcome. UI execution records
resolved `goto`, `fill`, and `click` actions with before/after routes, followed by the final
deterministic assertion outcome. The Tape observes the executor; it does not choose or change the
test verdict.

## Redaction boundary

Sensitive values are replaced by `[REDACTED]` inside the writer regardless of the caller-provided
display value. Logical sources such as `frozen_snapshot.request.body` are retained. API structured
bodies are represented by a non-secret marker, and UI password fields never persist their entered
value in the Tape. Finalized Tapes cannot be appended to or rewritten through the writer.

## Bundle relationship

Run Artifact Bundles accept Action Tape content through a dedicated method. Finalization and
standalone verification revalidate the canonical bytes, Run ownership, Result membership and all
Artifact references. Missing or invalid references fail Bundle finalization.

The current step stores newly generated executor Tape events and their digest inside each new
execution evidence record. It does not create a real formal Run Bundle, upgrade historical Runs,
claim independent reproduction, or assign `VERIFIED`. Those gates remain later work.
