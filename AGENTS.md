# AI TestPilot Repository Contract

## Mission

AI TestPilot is a portfolio-grade, enterprise-oriented prototype that demonstrates an auditable AI-assisted software-testing lifecycle. It pairs a React and Flask authentication system under test (SUT) with a separate testing product that imports a PRD, structures requirements, drafts and reviews API and UI test cases, executes deterministic checks, captures evidence, classifies failures, produces local bug and report artifacts, and traces fixes through regression.

## Authority and precedence

This file is the repository-wide operating contract. A more specific `AGENTS.md` may narrow rules for a subtree but may not weaken safety, evidence, known-bug, or phase-gate requirements. User instructions take precedence when they explicitly change scope. Conflicts must be surfaced before work continues.

## Phase boundaries

- Work must occur on one named phase and one dedicated branch at a time.
- Phase 0 is documentation and architecture only. It permits repository governance, `.gitignore`, `.env.example`, and files under `docs/`.
- Phase 0 forbids application scaffolding, business code, API routes, database files or migrations, executable tests, dependency installation, virtual environments, service startup, provider calls, deployment, and Phase 1 work.
- A phase may advance only after its acceptance criteria pass and its current changes are committed independently.
- Planned features must be labelled as planned; examples must be labelled as examples. Never present plans, mocks, or synthetic data as implemented or executed results.

## File-change discipline

- Modify only files explicitly allowed by the active phase and task.
- Preserve user-authored and already-correct files. Never manufacture success by deleting tests, evidence, or requirements.
- Use project-relative paths in repository documentation and configuration.
- Keep version-controlled sources (`docs/`, `schemas/`, `prompts/`, `test-specs/`, sample data, report templates, and `.env.example`) distinct from generated runtime artifacts.
- Inspect `git diff` and `git status` before every phase commit.

## Protected seeded defect

Requirement `REQ-AUTH-USERNAME-001` states that a username must contain at least six characters. Until the dedicated regression-fix phase, both SUT layers must intentionally omit the correct minimum-length enforcement so this deterministic reproduction remains possible:

- username: `z1234`
- password and confirmation: `Test1234`
- expected product behavior: registration is rejected with a clear minimum-six-character validation error
- intentionally defective behavior: `POST /api/auth/register` returns `201` and creates the user

The traceability chain uses `REQ-AUTH-USERNAME-001`, `TC-API-AUTH-REG-005`, `TC-UI-AUTH-REG-005`, and `BUG-AUTH-001`. Do not repair, hide, reclassify, or rewrite the requirement to accommodate this defect before the authorized fix phase.

## Real LLM and mock-provider rules

- Access a real model only through a provider interface; the initial planned provider is DeepSeek.
- Read secrets only from environment variables. Never place keys in source, Git, logs, databases, screenshots, evidence, or reports.
- Real and mock modes require explicit configuration and unmistakable UI, database, log, and report labels.
- Mocks are limited to unit, offline, and stable regression tests. Mock output must never be represented as a real provider result.
- Never silently fall back from a real provider to a mock. Record real failures truthfully.
- Record provider, model, prompt/schema versions, request ID, timing, latency, token usage, retries, finish reason, response status, validation status, error type, and redacted diagnostics.
- Treat all model output as untrusted candidate data. Only schema- and domain-valid, complete aggregate results may be promoted to approved business records.

## Deterministic test verdicts

AI may interpret requirements, identify risk, draft cases, explain evidence, and draft narrative artifacts. AI must not decide the final test verdict. Deterministic code owns HTTP and browser operations, assertions, status classification, evidence persistence, statistics, trace links, and machine-readable results. Supported execution states are `PASS`, `FAIL`, `BLOCKED`, `ERROR`, and `SKIPPED`.

Formal bug and report artifacts require persisted evidence. API automation must validate real requests, status codes, response fields, and domain rules. UI automation must use Playwright for Python, stable locators (`data-testid`, role, label, or placeholder), deterministic assertions, and failure evidence such as screenshots and traces.

## Git safety

- Use a dedicated branch and commit for each phase.
- Phase 0 branch: `feat/project-contract`.
- Phase 0 commit: `docs(project): define enterprise ai testing prototype contract`.
- Do not add remotes, push, force-push, open pull requests, or access external Git services unless a later explicit authorization permits it.
- Never use `git reset --hard` and never delete user work.
- Do not commit `.env`, secrets, databases, runtime evidence, logs, Playwright artifacts, or generated reports.

## Acceptance and truthfulness

- Acceptance is evidence-based. Missing evidence is not a pass.
- Report failures and blockers honestly; never fabricate model calls, test runs, screenshots, traces, defects, reports, or metrics.
- Validate required-file presence, non-empty/non-truncated content, cross-document consistency, secret hygiene, phase scope, branch, commit, and clean working tree.
- Failure of any mandatory phase gate keeps the phase open and blocks creation of the next phase branch.

## Windows D-drive authorization boundary

- All project writes must remain under `D:\AI-TestPilot\ai-test-flow-prototype-v3`.
- Prefer the native patch tool for file changes.
- If it fails specifically because of the Windows sandbox, request formal controlled execution permission naming the exact target file and reason.
- Do not use that permission outside the V3 root, touch the C drive or another project, change Windows/security settings, disable protection, run unknown scripts, install unauthorized software, or access external services.
- If an operation cannot be constrained to the V3 root, stop immediately.
