# AI TestPilot

> A local-first, auditable AI-assisted software-testing workbench paired with a purpose-built React and Flask authentication system under test.

## Why this project exists

Many AI testing demos stop after generating plausible prose. They do not prove that requirements become reviewable executable specifications, that real HTTP/browser assertions determine results, or that evidence remains traceable through a defect fix. AI TestPilot is designed to demonstrate that full engineering chain without allowing a model to manufacture a verdict.

The project is intended as a portfolio-grade reference for QA engineers, SDETs, full-stack engineers, test leads, and reviewers evaluating practical AI application engineering.

## System composition

AI TestPilot contains two separate local systems:

- **SUT** 鈥?a React/Vite/TypeScript frontend and Python 3.11/Flask backend for registration, login, current-user lookup, logout, session protection, and 404 behavior.
- **Testing plugin** 鈥?a React frontend and Flask-based backend that will manage PRDs, structured requirements, reviewed test specifications, deterministic execution, evidence, local bug/report artifacts, and regression traceability.

The SUT and plugin own separate SQLite databases (`sut.db` and `plugin.db`). They do not join across database boundaries. The plugin reaches the SUT only through its public API and UI.

## Planned end-to-end lifecycle

```text
PRD import
  -> real-provider structured analysis
  -> requirement risk and testability review
  -> API/UI/manual case generation and approval
  -> deterministic API and Playwright execution
  -> evidence persistence and failure classification
  -> advisory AI failure analysis
  -> local Markdown/JSON bug artifacts
  -> HTML/Markdown/PDF reports
  -> traceability and post-fix regression
```

This is the approved target architecture, not a claim that the lifecycle is implemented today.

## Protected seeded defect

Requirement `REQ-AUTH-USERNAME-001` says usernames must contain at least six characters. Until the authorized regression-fix phase, both SUT layers must intentionally omit that minimum-length validation, so `z1234` with `Test1234` is incorrectly accepted and `POST /api/auth/register` returns `201`.

The future API/UI cases `TC-API-AUTH-REG-005` and `TC-UI-AUTH-REG-005` must expose the mismatch, which later becomes `BUG-AUTH-001`. Contributors must not fix, hide, reclassify, or weaken this defect early.

## AI and deterministic execution

AI may interpret PRDs, identify risks, draft requirements and tests, and assist with failure narratives. AI output remains untrusted candidate data until schema/domain validation and required human review succeed.

Deterministic code alone sends HTTP requests, drives Playwright, evaluates assertions, assigns `PASS`, `FAIL`, `BLOCKED`, `ERROR`, or `SKIPPED`, saves evidence, computes metrics, and creates machine-readable results. A model cannot decide the authoritative test state.

## Real DeepSeek and Mock modes

DeepSeek is the first planned real provider behind a provider-neutral interface. Real calls will record model, prompt/schema versions, request metadata, finish reason, timing, token usage, retries, validation, and redacted failures.

Mock mode is limited to unit, offline, fault-injection, and stable regression tests. It must be explicitly labelled in the UI, database, logs, and reports. The system must never silently replace a failed real call with mock output or present mock output as real.

## Technology direction

| Area            | Planned technologies                                                            |
| --------------- | ------------------------------------------------------------------------------- |
| SUT frontend    | React, Vite, TypeScript, Axios, React Router, Ant Design                        |
| SUT backend     | Python 3.11, Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-CORS, pytest         |
| Plugin frontend | React, Vite, TypeScript, Axios, React Router, Ant Design; ECharts when required |
| Plugin backend  | Python 3.11, Flask, SQLAlchemy, Pydantic/JSON Schema, pytest                    |
| Test execution  | pytest, HTTPX/requests, Playwright for Python, JSON Schema, JUnit XML           |
| Quality         | Ruff, mypy, ESLint, Prettier, TypeScript, coverage                              |

Phase 1 supplemental acceptance installed the declared dependencies locally, recorded the npm lockfile, and validated the foundation shells without implementing business behavior. Phase 2 implemented the SUT Flask authentication backend. Phase 3 now verifies that backend through a live HTTP boundary.

## Current phase

**Phase 3 — live SUT black-box API acceptance and protected-defect verification.**

Phase 0 established the approved contract and architecture, Phase 1 added the engineering foundation, and Phase 2 implemented the Flask authentication backend. Phase 3 adds a manual API case baseline, real HTTP pytest acceptance, redacted runtime evidence, and strict XFAIL proof of the protected seeded defect. The SUT frontend business UI, Plugin, AI providers, general execution engine, formal bug/report artifacts, and later-phase workflows remain unimplemented.

## Repository map

```text
sut/                 SUT backend and frontend boundaries
plugin/              Plugin backend and frontend boundaries
docs/                Architecture, design, testing, development, and ADRs
schemas/             Future versioned machine contracts
prompts/             Future versioned prompt sources
test-specs/          Future reviewed API/UI/manual specifications
artifacts/           Ignored local runtime outputs; structure only in Git
scripts/             Read-only prerequisite and phase verification commands
tests/               Future cross-system and acceptance tests
```

See [Project Contract](docs/PROJECT_CONTRACT.md), [Roadmap](docs/ROADMAP.md), and [Development Setup](docs/development/DEVELOPMENT_SETUP.md).

## Local prerequisites

- Windows 11 and PowerShell 5.1 or PowerShell 7+
- Git
- Python 3.11 with pip
- Node.js and npm suitable for the declared frontend toolchain
- A supported browser later installed through the approved Playwright workflow

Run the read-only prerequisite check:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_prerequisites.ps1
```

Run the Phase 1 structural verifier:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_phase1.ps1
```

Run the Phase 3 live API verifier:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_phase3.ps1
```

The Phase 3 verifier starts a migrated SUT on loopback, runs 20 ordinary black-box cases plus one strict known-defect XFAIL, saves redacted ignored evidence under `artifacts/logs/phase3/`, and cleans up its exact process and temporary database.

The prerequisite and Phase 1 scripts do not install, delete, repair, or print environment-variable values. The Phase 3 verifier deletes only the unique temporary database directory it creates for its own run.

## Environment and security

`.env.example` is a versioned list of safe placeholders. A real `.env`, when explicitly needed in a later phase, is created locally and remains ignored. API keys must come only from the environment; never commit, echo, paste into command history, store in a database, or include them in logs, screenshots, evidence, or reports.

The planned SUT authentication mechanism is a server-side opaque session delivered through an `HttpOnly`, `SameSite=Lax` cookie鈥攏ot JWT. Uploaded PRDs and model output are untrusted. Future executors will use allowlisted targets and protocol-enumerated operations; arbitrary model-authored code is forbidden.

## API and UI testing targets

Phase 3 API acceptance issues real local HTTP requests and validates status codes, headers, JSON fields, session behavior, and the protected requirement mismatch with a fixed pytest baseline. It is not yet the Plugin's general execution engine. Future UI automation will use Playwright for Python with stable `data-testid`, role, label, or placeholder locators and deterministic assertions. Required UI failure evidence will include screenshots and traces under the approved retention policy.

UI automation is not implemented or executed in Phase 3.

## Planned exports

- PRD/SRS: Markdown source and PDF presentation/archive.
- Structured requirements: JSON plus CSV/XLSX review views.
- Test cases: JSON or YAML machine source plus XLSX review view.
- Results: JSON, JUnit XML, redacted logs, and evidence directories.
- Bugs: local Markdown/JSON with evidence references only.
- Reports: interactive HTML, versionable Markdown, and PDF archive.
- Traceability: Markdown plus CSV/XLSX.

## Local-first delivery

The first release must complete a stable, repeatable local demonstration. Online deployment is an optional later challenge and cannot replace or weaken local operation. No remote service or real model is called during Phase 1.

## Roadmap summary

The approved roadmap progresses from foundation, through SUT backend/API verification and frontend, to reliable real-model analysis, test generation/review, deterministic API/UI execution, evidence and advisory analysis, local bug/report artifacts, regression, professional UI, and final local demonstration. Each phase uses a dedicated branch and cannot start before its gate passes.

See [docs/ROADMAP.md](docs/ROADMAP.md) for phase-by-phase inputs, outputs, acceptance, branches, and blockers.

## Truthfulness statement

Current committed foundation and SUT backend files, together with local Phase 3 runtime evidence, prove dependency/tooling acceptance, live SUT API execution, and detection of the protected seeded defect for the documented run. They do not prove that DeepSeek responds, the SUT UI works, the Plugin executes tests, or formal bugs and reports are generated. Such claims require their corresponding later phases and real evidence. Results, model calls, screenshots, traces, bugs, reports, and metrics must never be fabricated.
