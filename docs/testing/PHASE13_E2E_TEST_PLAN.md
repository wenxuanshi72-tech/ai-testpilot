# Phase 13 End-to-End Test Plan

Status: paid-provider authorization pending

## Objective and fixed inputs

Phase 13 repeats the accepted local lifecycle without adding business behavior. It uses
`docs/prd/login_register_prd.md`, creates a new project named
`Phase 13 E2E Authentication Loop <timestamp>`, and writes only to an ignored session directory
under `tmp/phase13-e2e/`. Existing Phase 5-12 runs, evidence, Bugs, reports, regression records,
`instance/plugin.db`, and runtime artifacts are read-only references and are never reused as this
run's results.

The pre-fix SUT is started from an isolated worktree at Phase 10 merge point `bb24609`; the
post-fix regression uses current accepted main. This produces a real HTTP 201 defect observation
before the authorized fix and a real HTTP 400 result after it without reverting current sources or
fabricating either verdict.

## Provider plan requiring separate authorization

- Provider: DeepSeek Real; model: `deepseek-v4-pro`
- Thinking: disabled; JSON response mode; no streaming
- Mock fallback: prohibited
- Existing Provider responses: not reused
- PRD analysis: 1 outline plus 2 requirement batches; maximum 9 attempts; US$0.026400 cap
- Test generation: 17 initial batches; up to 8 structural corrections; maximum 40 Provider
  attempts; US$0.250000 cap
- Combined hard limits proposed for explicit approval: 49 Provider attempts and US$0.276400
- A network attempt without usage is audited but does not permit exceeding the request cap.
- Any cost uncertainty, model mismatch, truncation, invalid aggregate, or exhausted correction
  budget stops the workflow. Real failure never falls back to Mock.

No API key is read until the paid authorization gate is approved. The key remains process-local and
must not enter commands, logs, databases, artifacts, screenshots, reports, or Git.

## Isolation and local services

The session directory contains `plugin.db`, `sut.db`, an Artifacts root, redacted logs, a manifest,
and a database backup with SHA-256. The isolated paths are Git-ignored. Before execution the
orchestrator verifies the backup can be opened, migrations apply, `integrity_check=ok`, and
`foreign_key_check` returns no rows.

| Service      | Address                 |
| ------------ | ----------------------- |
| SUT Flask    | `http://127.0.0.1:5001` |
| SUT React    | `http://127.0.0.1:5173` |
| Plugin Flask | `http://127.0.0.1:5002` |
| Plugin React | `http://127.0.0.1:5174` |

All four health/port checks must pass before browser or API execution. Only recorded session PIDs
may be stopped. Ports and temporary processes must be clean after the run.

## Ordered gates and success criteria

1. **Environment:** correct branch/commit, clean tree, supported Python/Node/npm/Git/browser,
   ignored secrets/runtime paths, four free ports, no external connector.
2. **Project/PRD:** exactly one new E2E project and one normalized PRD version with the expected
   content hash.
3. **Real analysis:** attributable provider/model/prompt/schema/calls; complete JSON; all batches
   validate; 19 formal requirements promote atomically.
4. **Real generation:** 46 slots in 17 batches (API 7, UI 6, Manual 4); complete validation,
   coverage, trace, cost, and audit; no partial candidate promotion.
5. **Human review pause:** export all 46 candidates and findings. A real person classifies every
   candidate and explicitly confirms revisions. No script invents the reviewer decision.
6. **Freeze:** only approved, automated, executable versions enter the immutable MVP baseline;
   required seeded API/UI cases are present.
7. **Pre-fix execution:** deterministic API and Playwright runs use the same frozen versions;
   `TC-API-AUTH-REG-005` and `TC-UI-AUTH-REG-005` genuinely fail for `BUG-AUTH-001`; adjacent
   guards retain truthful results.
8. **Evidence/Bug/report:** hashes and redaction pass; one canonical local Bug links both product
   failures; Markdown/JSON Bug and Markdown/HTML/PDF report reconcile and render.
9. **Authorized fix boundary:** switch only the isolated SUT runtime from pre-fix `bb24609` to the
   accepted fixed current commit. Test expectations and snapshots remain unchanged.
10. **Regression/closure:** both seeded cases change `FAIL -> PASS`; required authentication guards
    pass; old evidence remains immutable; append-only Bug closure and trace hash are created.
11. **Plugin UI:** all nine Phase 12 routes load the isolated E2E database and expose the new IDs,
    metrics, artifacts, and regression chain without secret or absolute-path leakage.
12. **Final integrity:** file/manifest hashes recompute, trace has no critical orphan, SQLite checks
    pass, quality gates pass, and all four ports are released.

Any failed mandatory gate stops later mutation. Partial AI batches cannot promote, incomplete human
classification cannot freeze, missing evidence cannot create a Bug/report, and a failed regression
cannot close the Bug. Phase 14 remains blocked until the final results document records a complete
PASS.
