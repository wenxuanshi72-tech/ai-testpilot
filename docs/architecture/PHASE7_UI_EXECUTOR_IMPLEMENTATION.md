# Phase 7B Playwright UI Executor

## Scope

Phase 7B consumes only UI members from the Phase 6 immutable baseline and executes them with
Playwright Python. It does not call an LLM, alter approved snapshots, repair the protected username
defect, create bugs, or generate reports.

## Deterministic execution

`ui-executor@1.0.0` accepts only a local loopback UI target and validates the frozen baseline,
environment, executor contract, snapshot hash, and snapshot schema. The supported action protocol is
deliberately bounded to `goto:route`, `fill:label`, and `click:role`. Labels and role accessible names
are exact; CSS/XPath and arbitrary script evaluation are rejected.

The run coordinator starts the Flask SUT on port 5001 and Vite SUT UI on port 5173 against a fresh
temporary SQLite database. Every snapshot receives a fresh browser context. The registration-success
candidate omits a username value, so versioned adapter `ui-test-data-adapter@1.0.0` supplies the fixed
local value `phase7_reg_002` and records that transformation. No candidate SQL, shell, or code is run.

## Evidence and security

Each UI result stores deterministic route, network-status, and visible-state assertions. A full-page
PNG and Playwright Trace ZIP are written below ignored `artifacts/evidence/ui/{run_id}/{case_id}` and
their SHA-256 hashes are recorded in `plugin.db`. Password fills occur before tracing starts, so Trace
actions do not persist password arguments. Screenshots show password inputs only in their browser-
masked state. Runtime services and browser contexts are stopped after execution.

Migration `0009_ui_execution.sql` makes UI runs, results, and evidence append-only. Result payloads
conform to `ui-execution-result@1.0.0`. Phase 8 remains responsible for cross-executor evidence
consolidation; Phase 9 remains responsible for formal bug artifacts.
