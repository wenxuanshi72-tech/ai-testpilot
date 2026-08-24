# Local End-to-End Runbook

Status: Phase 13 portfolio MVP evidence replay available; no paid call required

## Accepted portfolio verification

From the repository root on `test/end-to-end-loop`:

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe scripts\verify_phase13_portfolio_mvp.py
```

The verifier opens the accepted Analysis and Plugin databases read-only. It recomputes the real
Provider identity, 19-Requirement count, ten immutable snapshot hashes, canonical Bug/report
hashes, seeded `FAIL→PASS` transitions, regression trace, Bug closure, SQLite integrity, and foreign
keys. It creates no Provider call, Session, Run, Candidate, approval, baseline, result, or artifact.

## Historical full-generation experiment

The original diagnostic dry-run remains available:

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe scripts\phase13_e2e.py dry-run
```

This command performs read-only checks and prints the PRD/provider/batch/cost/port plan. It does not
load `.env`, create a database or project, create an AI run, start services, or call a Provider.
`execute-ai` is not required by the accepted portfolio MVP path and still requires a new explicit
paid authorization if it is ever used for further experimentation.

## Execution checkpoints

After separate paid authorization, any future experimental execute command must create a timestamped ignored
session directory and an append-only command journal. It must record tool versions, commit IDs,
start/end timestamps, durations, Provider request counts/usage/cost, every domain ID, result totals,
evidence and artifact hashes, database integrity, recovery decisions, and cleanup status.

The orchestrator must pause twice even when earlier steps pass:

1. before the first paid Provider request unless exact call and cost limits were explicitly approved;
2. after candidate export until a named human confirms every dynamically generated candidate's
   review classification and any required revisions. Neither 46 nor 44 is a fixed portfolio
   acceptance count.

Such an experiment may then freeze, execute the pre-fix worktree, consolidate evidence, generate the local Bug/report,
switch to the accepted fixed SUT, run regression, close the Bug, and visually verify the Plugin UI.
It must never run arbitrary model-produced SQL, shell, code, or file paths.

## Failure and cleanup

On failure, keep the isolated session database, redacted logs, successful checkpoints, and manifest
for diagnosis. Do not alter `instance/plugin.db` or retry beyond the approved limits. Stop only PIDs
recorded in the session manifest and verify ports 5001, 5173, 5002, and 5174 are released. Runtime
outputs stay ignored and must not be staged in Git.
