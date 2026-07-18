# Contributing to AI TestPilot

## Branches and phase ownership

Work from synchronized, clean `main` and use one dedicated branch per approved phase. Examples include `chore/project-foundation`, `feat/sut-backend`, and `feat/sut-frontend`. A branch may change only the paths named by its phase contract. Do not create the next phase branch until the current gate passes and the user authorizes continuation.

Never commit directly to `main`, force push, use `git reset --hard`, mix phases, or delete user-authored work.

## Commits

Use Conventional Commits with a precise scope and imperative summary:

```text
<type>(<scope>): <description>
```

Common types are `feat`, `fix`, `test`, `docs`, `chore`, and `refactor`. A commit must be independently reviewable, contain one phase's intent, and follow a successful gate. Inspect `git diff --check`, the complete diff, staged paths, and `git status` before committing.

## Phase gates and testing

Each phase defines mandatory tests and evidence. Run the complete relevant suite after a fix; do not substitute file existence, a static page, mock output, or model confidence for real execution. `PASS`, `FAIL`, `BLOCKED`, `ERROR`, and `SKIPPED` are deterministic states with recorded reasons.

Do not delete/skip failing tests, reduce assertions, widen tolerances, change requirements, conceal evidence, or reclassify a product failure to manufacture PASS. If a gate fails, remain in that phase, report the cause, make only in-scope corrections, and rerun the gate.

## Code review

Review for scope, architecture direction, deterministic behavior, error/security boundaries, tests, evidence, traceability, migration/compatibility, accessibility, and truthful claims. Confirm AI-generated suggestions are treated as untrusted candidate content. Resolve high-risk findings before merge; do not self-approve a phase gate merely because automation is green.

## Documentation

Update durable Markdown sources with architecture, API/schema, operation, security, and acceptance changes. Use stable IDs and project-relative paths. Mark planned behavior and design examples explicitly; never describe an unimplemented feature or unexecuted result as complete. Keep terminology, versions, diagrams, and export contracts synchronized.

## Secret and privacy safety

Secrets come only from local environment variables or a later approved secret manager. Never commit/read/print `.env`, keys, passwords, tokens, cookies, authorization headers, personal data, or unredacted evidence. Do not paste real keys into commands or shell history. Run secret checks before every commit and revoke any suspected exposure.

Runtime databases, logs, Playwright artifacts, evidence, generated bugs/reports, and exports remain ignored. Examples use unmistakable placeholders and non-personal data.

## Protected seeded defect

`REQ-AUTH-USERNAME-001` requires usernames of at least six characters, while the pre-fix SUT must incorrectly accept `z1234` / `Test1234`. Do not add the missing validator, alter the requirement, weaken `TC-API-AUTH-REG-005` or `TC-UI-AUTH-REG-005`, hide the `201`, or relabel the future failure before the authorized regression-fix phase.

## AI/provider integrity

DeepSeek and Mock modes remain explicitly separate in configuration, UI, data, logs, and reports. Mock is for offline/testing purposes and cannot prove a real provider path. Never silently fall back or fabricate a successful call. AI can draft/analyze; deterministic code owns HTTP/browser actions, assertions, verdicts, evidence, and metrics.

## Pull/push boundary

Remote access, pushing, and pull requests occur only when explicitly authorized for the current phase. Never add/change a remote or upload artifacts as a convenience. Passing a phase means its local acceptance contract is met; it does not authorize the next phase automatically.
