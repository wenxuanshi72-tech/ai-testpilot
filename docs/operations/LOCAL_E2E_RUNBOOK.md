# Local End-to-End Runbook

Status: Phase 13 dry-run available; paid execution not yet authorized

## Authorization-free preflight

From the repository root on `test/end-to-end-loop`:

```powershell
$env:PYTHONPATH='.'
.\.venv\Scripts\python.exe scripts\phase13_e2e.py dry-run
```

This command performs read-only checks and prints the PRD/provider/batch/cost/port plan. It does not
load `.env`, create a database or project, create an AI run, start services, or call a Provider.

## Execution checkpoints

After separate paid authorization, the future execute command must create a timestamped ignored
session directory and an append-only command journal. It must record tool versions, commit IDs,
start/end timestamps, durations, Provider request counts/usage/cost, every domain ID, result totals,
evidence and artifact hashes, database integrity, recovery decisions, and cleanup status.

The orchestrator must pause twice even when earlier steps pass:

1. before the first paid Provider request unless exact call and cost limits were explicitly approved;
2. after candidate export until a named human confirms the 46 review classifications and revisions.

It may then freeze, execute the pre-fix worktree, consolidate evidence, generate the local Bug/report,
switch to the accepted fixed SUT, run regression, close the Bug, and visually verify the Plugin UI.
It must never run arbitrary model-produced SQL, shell, code, or file paths.

## Failure and cleanup

On failure, keep the isolated session database, redacted logs, successful checkpoints, and manifest
for diagnosis. Do not alter `instance/plugin.db` or retry beyond the approved limits. Stop only PIDs
recorded in the session manifest and verify ports 5001, 5173, 5002, and 5174 are released. Runtime
outputs stay ignored and must not be staged in Git.
