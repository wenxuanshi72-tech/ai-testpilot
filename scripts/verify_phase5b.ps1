[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv/Scripts/python.exe"
$flask = Join-Path $projectRoot ".venv/Scripts/flask.exe"
$runDir = Join-Path $projectRoot ("tmp/phase5b/" + [guid]::NewGuid().ToString("N"))
$backendProcess = $null

function Invoke-Step([string]$Label, [scriptblock]$Command) {
    Write-Output "== $Label =="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

function Test-PortReleased([int]$Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        return -not ($async.AsyncWaitHandle.WaitOne(300, $false) -and $client.Connected)
    } catch {
        return $true
    } finally {
        $client.Dispose()
    }
}

function Wait-Http([string]$Uri, [System.Diagnostics.Process]$Process) {
    for ($attempt = 0; $attempt -lt 80; $attempt++) {
        if ($Process.HasExited) {
            throw "Owned process $($Process.Id) exited before $Uri became ready."
        }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                return
            }
        } catch {
            # Bounded local readiness polling continues.
        }
        Start-Sleep -Milliseconds 250
    }
    throw "$Uri did not become ready within 20 seconds."
}

function Stop-OwnedProcess([System.Diagnostics.Process]$Process) {
    if ($null -ne $Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force
        Wait-Process -Id $Process.Id -ErrorAction SilentlyContinue
    }
}

function Assert-Preconditions {
    $branch = (& git -C $projectRoot branch --show-current).Trim()
    if ($branch -ne "feat/plugin-test-generation") {
        throw "Expected feat/plugin-test-generation; found $branch."
    }
    foreach ($relativePath in @(
        "plugin/backend/app/test_generation.py",
        "plugin/backend/app/test_generation_budget.py",
        "plugin/backend/app/test_generation_diagnostics.py",
        "plugin/backend/app/test_generation_payloads.py",
        "plugin/backend/app/test_generation_planning.py",
        "plugin/backend/app/test_generation_trace.py",
        "plugin/backend/real_test_generation_acceptance.py",
        "plugin/backend/app/test_generation_prompts.py",
        "plugin/backend/app/test_generation_schemas.py",
        "plugin/backend/app/test_intent_compiler.py",
        "plugin/backend/app/test_intent_contract.py",
        "plugin/backend/app/test_intent_mock.py",
        "plugin/backend/app/test_intent_schemas.py",
        "plugin/backend/migrations/0004_test_case_generation.sql",
        "plugin/backend/migrations/0005_test_generation_audit_recovery.sql",
        "schemas/test-cases/v1/test_case_candidate.schema.json",
        "schemas/test-cases/v1/test_case_candidate_aggregate.schema.json",
        "schemas/test-cases/v1.1/raw_test_case_candidate.schema.json",
        "schemas/test-cases/v1.1/test_case_candidate.schema.json",
        "schemas/test-cases/v1.2/test_case_candidate.schema.json",
        "schemas/test-intents/v1/test_intent.schema.json",
        "schemas/test-intents/v1/api_intent_batch.schema.json",
        "schemas/test-intents/v1/ui_intent_batch.schema.json",
        "schemas/test-intents/v1/manual_intent_batch.schema.json",
        "schemas/test-intents/v2/test_intent.schema.json",
        "schemas/test-intents/v2/api_intent_batch.schema.json",
        "schemas/test-intents/v2/ui_intent_batch.schema.json",
        "schemas/test-intents/v2/manual_intent_batch.schema.json",
        "prompts/test-generation/v1/api_cases_system.md",
        "prompts/test-generation/v1/ui_cases_system.md",
        "prompts/test-generation/v1/manual_cases_system.md",
        "prompts/test-generation/v1.2/api_cases_system.md",
        "prompts/test-generation/v1.2/ui_cases_system.md",
        "prompts/test-generation/v1.2/manual_cases_system.md",
        "prompts/test-generation/v2/api_cases_system.md",
        "prompts/test-generation/v2/ui_cases_system.md",
        "prompts/test-generation/v2/manual_cases_system.md",
        "prompts/test-generation/v3/api_cases_system.md",
        "prompts/test-generation/v3/ui_cases_system.md",
        "prompts/test-generation/v3/manual_cases_system.md",
        "schemas/test-cases/v1.3/test_case_candidate.schema.json",
        "schemas/test-cases/v1.3/test_case_candidate_aggregate.schema.json",
        "docs/architecture/PHASE6_CANDIDATE_INPUT_CONTRACT.md",
        "docs/testing/PLUGIN_TEST_GENERATION_RESULTS.md"
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $relativePath) -PathType Leaf)) {
            throw "Missing Phase 5B file: $relativePath"
        }
    }
    if (Test-Path -LiteralPath (Join-Path $projectRoot "plugin/backend/migrations/0006_requirement_scoped_generation_gaps.sql")) {
        throw "Unapproved migration 0006 must not exist."
    }
    & git -C $projectRoot diff --quiet main -- docs/ROADMAP.md
    if ($LASTEXITCODE -ne 0) {
        throw "ROADMAP.md must not change in Phase 5B."
    }
    & git -C $projectRoot diff --quiet main -- sut
    if ($LASTEXITCODE -ne 0) {
        throw "SUT files must not change in Phase 5B."
    }
    & git -C $projectRoot check-ignore -q -- ".env"
    if ($LASTEXITCODE -ne 0) {
        throw ".env is not ignored."
    }
    if (@(& git -C $projectRoot ls-files -- "*.db" "*.log").Count -ne 0) {
        throw "Database or log files must not be tracked."
    }
    $migration = Get-Content -Raw -LiteralPath (
        Join-Path $projectRoot "plugin/backend/migrations/0004_test_case_generation.sql"
    )
    foreach ($phase6Table in @(
        "test_case_reviews",
        "approved_test_case_versions",
        "frozen_baselines",
        "frozen_baseline_members",
        "immutable_execution_snapshots"
    )) {
        if ($migration.Contains($phase6Table)) {
            throw "Phase 6 table leaked into migration 0004: $phase6Table"
        }
    }
    if (-not (Test-PortReleased 5001)) {
        throw "Port 5001 is in use; no process was stopped."
    }
    if (-not (Test-PortReleased 5173)) {
        throw "Port 5173 is in use; no process was stopped."
    }
}

function Assert-PhaseBoundary {
    $changed = @(& git -C $projectRoot diff --name-only main)
    $changed += @(& git -C $projectRoot ls-files --others --exclude-standard)
    $allowed = @(
        "plugin/backend/",
        "schemas/test-cases/",
        "schemas/test-intents/",
        "prompts/test-generation/",
        "docs/architecture/PLUGIN_TEST_GENERATION_IMPLEMENTATION.md",
        "docs/architecture/TEST_CASE_CANDIDATE_SCHEMA.md",
        "docs/architecture/PHASE6_CANDIDATE_INPUT_CONTRACT.md",
        "docs/internal/TEST_GENERATION_PROMPT_REGISTER.md",
        "docs/testing/PLUGIN_TEST_GENERATION_",
        "docs/testing/REQUIREMENT_CANDIDATE_TRACEABILITY.md",
        "scripts/verify_phase5b.ps1"
    )
    foreach ($path in $changed) {
        if (-not ($allowed | Where-Object { $path.StartsWith($_) -or $path -eq $_ })) {
            throw "Out-of-scope Phase 5B path: $path"
        }
    }
}

Assert-Preconditions
Assert-PhaseBoundary
[IO.Directory]::CreateDirectory($runDir) | Out-Null

try {
    Invoke-Step "Ruff format" {
        & $python -m ruff format --check plugin/backend plugin/__init__.py
    }
    Invoke-Step "Ruff lint" {
        & $python -m ruff check plugin/backend plugin/__init__.py
    }
    Invoke-Step "Plugin mypy" {
        & $python -m mypy --explicit-package-bases plugin/backend
    }
    Invoke-Step "SUT mypy" {
        & $python -m mypy sut/backend
    }
    Invoke-Step "Schema and prompt registry" {
        & $python -c (
            "from plugin.backend.app.test_generation_schemas import TestCaseSchemas;" +
            "from plugin.backend.app.test_intent_schemas import TestIntentSchemas;" +
            "from plugin.backend.app.test_generation_prompts import TestGenerationPromptRegistry;" +
            "assert len(TestCaseSchemas().schemas)==7;" +
            "assert len(TestIntentSchemas().schemas)==4;" +
            "assert len(TestGenerationPromptRegistry().content_hash)==64"
        )
    }
    Invoke-Step "Real acceptance dry-run" {
        & $python -m plugin.backend.real_test_generation_acceptance `
            --provider real --model deepseek-v4-pro --max-calls 18 --max-retries 1 `
            --budget-usd 0.065000 --max-output-tokens 3072 --thinking disabled --dry-run
    }
    Invoke-Step "Python default tests" {
        & $python -m pytest -q --basetemp (Join-Path $runDir "pytest-default")
    }
    Invoke-Step "Plugin branch coverage" {
        & $python -m pytest -q plugin/backend/tests `
            --basetemp (Join-Path $runDir "pytest-plugin") --cov=plugin.backend.app `
            --cov-report=term-missing --cov-branch --cov-fail-under=85
    }
    Invoke-Step "Prettier" { & npm.cmd run format:check }
    Invoke-Step "ESLint" { & npm.cmd run lint }
    Invoke-Step "TypeScript" { & npm.cmd run typecheck }
    Invoke-Step "Frontend tests" { & npm.cmd run test }
    Invoke-Step "SUT frontend build" {
        & npm.cmd run build --workspace @ai-testpilot/sut-frontend
    }
    Invoke-Step "Plugin frontend build" {
        & npm.cmd run build --workspace @ai-testpilot/plugin-frontend
    }

    $sutDatabase = Join-Path $runDir "sut-api.db"
    $env:SUT_DATABASE_URL = "sqlite:///$($sutDatabase.Replace('\', '/'))"
    $env:SUT_SESSION_COOKIE_SECURE = "false"
    $env:SUT_CORS_ALLOWED_ORIGINS = "http://127.0.0.1:5173"
    $env:PHASE3_BASE_URL = "http://127.0.0.1:5001"
    $env:PHASE3_EVIDENCE_DIR = Join-Path $runDir "api-evidence"
    $migration = Start-Process -FilePath $flask -ArgumentList @(
        "--app", "sut.backend.wsgi:app", "db", "upgrade"
    ) -WorkingDirectory $projectRoot -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $runDir "migration-out.log") `
        -RedirectStandardError (Join-Path $runDir "migration-err.log") -Wait -PassThru
    if ($migration.ExitCode -ne 0) {
        throw "SUT migration failed."
    }
    $backendProcess = Start-Process -FilePath $python -ArgumentList @(
        "-m", "sut.backend.wsgi"
    ) -WorkingDirectory $projectRoot -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $runDir "backend-out.log") `
        -RedirectStandardError (Join-Path $runDir "backend-err.log") -PassThru
    Wait-Http "http://127.0.0.1:5001/api/health" $backendProcess
    Invoke-Step "Phase 3 API regression" {
        & $python -m pytest -o "addopts=--strict-config --strict-markers -ra" `
            --basetemp (Join-Path $runDir "pytest-phase3") -m black_box tests/api -q
    }
    Stop-OwnedProcess $backendProcess
    $backendProcess = $null
    if (-not (Test-PortReleased 5001)) {
        throw "Owned SUT process stopped but port 5001 remains in use."
    }

    Invoke-Step "Git diff check" { & git -C $projectRoot diff --check }
    $secretMatches = @(& git -C $projectRoot grep -n -E "sk-[A-Za-z0-9_-]{20,}" -- .)
    if ($LASTEXITCODE -notin @(0, 1)) {
        throw "Secret scan command failed."
    }
    if ($secretMatches.Count -ne 0) {
        throw "Potential tracked secret detected."
    }
    $workingSecretMatches = @(& rg -n --hidden `
        --glob "!.git/**" --glob "!.env" --glob "!instance/**" `
        --glob "!node_modules/**" --glob "!tmp/**" `
        "sk-[A-Za-z0-9_-]{20,}" .)
    if ($LASTEXITCODE -notin @(0, 1)) {
        throw "Working-tree secret scan command failed."
    }
    if ($workingSecretMatches.Count -ne 0) {
        throw "Potential working-tree secret detected."
    }
    if (-not (Test-PortReleased 5173)) {
        throw "Port 5173 remains in use; no process was stopped."
    }
    Write-Output "Phase 5B offline verification: PASS"
} finally {
    Stop-OwnedProcess $backendProcess
    $resolvedRunDir = [IO.Path]::GetFullPath($runDir)
    $resolvedTempRoot = [IO.Path]::GetFullPath(
        (Join-Path $projectRoot "tmp/phase5b")
    ).TrimEnd("\") + "\"
    if (-not $resolvedRunDir.StartsWith(
        $resolvedTempRoot,
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Refusing to clean an unexpected runtime path."
    }
    if (Test-Path -LiteralPath $runDir -PathType Container) {
        Remove-Item -LiteralPath $runDir -Recurse -Force
    }
}
