# Development Setup

Status: Phase 1 environment plan. Dependency installation and service startup require later explicit authorization.

## Supported local environment

The primary development environment is Windows 11 with Git, PowerShell 5.1 or PowerShell 7+, Python 3.11, Node.js/npm, and later Playwright-managed browsers. The project remains local-first and must not require a hosted service for its accepted end-to-end demonstration.

Run the read-only prerequisite check from any PowerShell location:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_prerequisites.ps1
```

The script reports versions and forbidden local artifacts. It does not install, upgrade, repair, delete, read `.env`, or print environment-variable values.

## Repository boundaries

- `sut/backend` and `sut/frontend` own the isolated authentication SUT.
- `plugin/backend` and `plugin/frontend` own the AI TestPilot product.
- `schemas`, `prompts`, and `test-specs` hold future reviewed, versioned sources.
- `artifacts` is the ignored local runtime root for reports, bugs, evidence, exports, and logs.
- `scripts` contains safe local developer/verification commands.
- `tests` is reserved for cross-system contract, integration, and acceptance tests.

SUT and plugin databases and processes remain separate. Do not import one backend's internal modules from the other.

## Python 3.11 isolation strategy

Do not modify the system Python or the existing Anaconda environment. When a later phase authorizes dependency installation, create a project-local `.venv` with the explicitly selected Python 3.11 interpreter and install only the required optional groups from the root `pyproject.toml`.

Planned groups:

- `sut-backend`: Flask, Flask-SQLAlchemy, Flask-Migrate, and Flask-CORS.
- `plugin-backend`: Flask, SQLAlchemy, Flask-CORS, Pydantic, and JSON Schema.
- `test`: pytest, pytest-cov, HTTPX, and Playwright for Python.
- `quality`: Ruff and mypy.

The root configuration centralizes Python version, Ruff formatting/lint/import sorting, strict mypy direction, pytest paths/markers, and branch coverage. Backend packages and migrations are intentionally absent in Phase 1.

Creating the virtual environment and installing groups are future commands, not Phase 1 actions. Never install these tools globally.

## Node and npm strategy

The root `package.json` is a private npm workspace for `sut/frontend` and `plugin/frontend`. Shared TypeScript, ESLint, Prettier, Vite, Vitest, and Testing Library development dependencies live at the root; product dependencies stay declared in each workspace.

No dependency is installed in Phase 1 and no lockfile is fabricated. Before the first authorized install, review version ranges and use the project root so npm creates one workspace lockfile and one ignored `node_modules`. Do not use global installs or change the system Node/npm installation.

The minimal frontend shells contain no router, API client call, Ant Design business component, authentication form, or plugin workflow. Later start commands are planned as workspace scripts:

```powershell
npm run dev --workspace @ai-testpilot/sut-frontend
npm run dev --workspace @ai-testpilot/plugin-frontend
```

These commands will work only after an authorized dependency installation.

## Planned service topology

| Service | Planned loopback address | Current Phase 1 state |
|---|---|---|
| SUT frontend | `http://127.0.0.1:5173` | Foundation shell only; not started |
| SUT backend | `http://127.0.0.1:5001` | Directory boundary only |
| Plugin frontend | `http://127.0.0.1:5174` | Foundation shell only; not started |
| Plugin backend | `http://127.0.0.1:5002` | Directory boundary only |

Later launch documentation must start each service explicitly, report health, and stop cleanly without changing global configuration.

## Environment variables

`.env.example` is committed and contains names plus safe placeholders. A real `.env` is local, ignored, and created only when a later phase needs it. Never copy an `.env` from another project or V1/V2.

Do not put a real key in a command argument, shell assignment, pasted transcript, or command history. Enter secrets through a trusted local editor or an approved secret-input mechanism that does not echo/store the value, then verify only that the variable exists—never print it. The DeepSeek API Key must not appear in Git, logs, databases, screenshots, evidence, reports, or test fixtures.

If `.env` already exists, scripts may check only its existence and Git-ignore status. They must not read it.

## Local quality commands

Available without installing dependencies:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\check_prerequisites.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\verify_phase1.ps1
git diff --check
git status
```

After a separately authorized project-local installation, the planned commands are:

```powershell
python -m pytest
python -m ruff check .
python -m ruff format --check .
python -m mypy sut/backend plugin/backend tests
npm run lint
npm run typecheck
npm run test
npm run build
```

Do not report these dependency-based commands as passing until they have actually run in the authorized environment.

## Git workflow

Start each phase from synchronized clean `main`, create the exact phase branch, modify only its allowlisted paths, run its full gate, inspect `git diff`/`git status`, and create one Conventional Commit. Never use `git reset --hard`, force push, delete failing tests, or mix phases. Pushing and external access require explicit authorization.

The protected username defect remains in place through its designated pre-fix phases. Foundation work must not add a six-character validator.

## Terminal notes

- Windows PowerShell 5.1 and PowerShell 7 differ in default encoding and native-command handling; repository text is UTF-8 with Git-managed line endings.
- Run scripts with `-NoProfile` for reproducibility. `-ExecutionPolicy Bypass` applies only to that process invocation and does not change Windows policy.
- Use PowerShell syntax in Windows instructions; do not paste Bash environment/export commands into PowerShell.
- Git normalizes repository text to LF; `.ps1` files are checked out as CRLF for Windows compatibility.
- Quote paths and use literal path APIs in scripts; never construct deletion commands from unvalidated input.

## Common issues

| Symptom | Safe response |
|---|---|
| Python is not 3.11 | Report the mismatch; select an existing 3.11 interpreter later without changing global/Conda environments |
| Node/npm outside declared range | Report it; do not self-upgrade or install globally |
| Browser not on PATH | Informational in Phase 1; later validate a project-local Playwright browser after authorization |
| `.env` exists | Do not open it; confirm Git ignores it and never stage it |
| `node_modules` or `.venv` appears | Treat Phase 1 verification as failed; investigate without deleting user data automatically |
| PowerShell script is blocked | Use the documented process-scoped invocation or ask the user; do not change machine policy |
| npm/pip needs network | Stop and request authorization with directory, packages, outputs, validation, and environment impact |
| Git line-ending warning | Verify `.gitattributes` and `git diff --check`; do not rewrite unrelated files |

## Security boundary

All local project writes remain under the V3 root. Scripts are read-only unless their name and documentation explicitly say otherwise. No Phase 1 step contacts DeepSeek, downloads templates, installs dependencies, starts services, creates databases, or generates formal evidence, bugs, or reports.
