# Evidence Trust Evaluator

Status: authenticity hardening step 6 implemented and locally accepted.

## Boundary

The versioned deterministic evaluator recomputes evidence trust from portable filesystem artifacts.
It does not trust a Run Manifest's stored `trust_state`, query mutable database status, call an AI
provider, execute a test, or mutate a historical Run, Bug, Result, or evidence file.

## Policy

- `UNVERIFIED`: the Run Artifact Bundle fails independent verification.
- `EXECUTED`: the Run Artifact Bundle independently verifies, but no matching successful
  reproduction package is supplied.
- `VERIFIED`: the Run Artifact Bundle verifies and a self-contained, independently verified Bug
  reproduction package is bound to its exact Run and Manifest hash with status `REPRODUCED`.

An invalid, mismatched, `NOT_REPRODUCED`, `BLOCKED`, or `ERROR` reproduction does not erase the
independently established execution fact. It retains `EXECUTED` and returns a machine-readable
reason. Only the deterministic evaluator owns these states; model output has no authority.

This step exposes an in-process pure evaluation boundary only. Database persistence, HTTP/UI
presentation, historical upgrades, and real execution remain outside scope.
