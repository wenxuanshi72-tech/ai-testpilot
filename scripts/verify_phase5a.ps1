[CmdletBinding()]
param(
    [switch]$RealLLM,
    [switch]$ConfirmPaidCall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv/Scripts/python.exe"
$flask = Join-Path $projectRoot ".venv/Scripts/flask.exe"
$runId = [guid]::NewGuid().ToString("N")
$tempRoot = Join-Path $projectRoot "tmp/phase5a"
$runDir = Join-Path $tempRoot $runId
$backendProcess = $null

function Invoke-Step([string]$Label, [scriptblock]$Command) {
    Write-Output "== $Label =="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

function Test-PortReleased([int]$Port) {
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        $client = [System.Net.Sockets.TcpClient]::new()
        try {
            $async = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
            $connected = $async.AsyncWaitHandle.WaitOne(250, $false) -and $client.Connected
            if ($connected) {
                $client.EndConnect($async)
            } else {
                return $true
            }
        } catch {
            return $true
        } finally {
            $client.Dispose()
        }
        Start-Sleep -Milliseconds 250
    }
    return $false
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

function Import-AllowedEnvironment {
    $envPath = Join-Path $projectRoot ".env"
    if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
        throw "The ignored local .env file is required for real acceptance."
    }
    $allowed = @(
        "PLUGIN_DATABASE_URL",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "LLM_TIMEOUT_SECONDS",
        "LLM_MAX_RETRIES",
        "LLM_MAX_OUTPUT_TOKENS",
        "LLM_RUN_MAX_OUTPUT_TOKENS",
        "PRD_BATCH_MAX_CHARS",
        "PRD_BATCH_MAX_REQUIREMENTS"
        "PHASE5A_RECOVERY_SOURCE_RUN_ID"
    )
    foreach ($line in Get-Content -LiteralPath $envPath -Encoding UTF8) {
        if ($line -notmatch "^[ 	]*([A-Z][A-Z0-9_]*)[ 	]*=(.*)$") {
            continue
        }
        $name = $Matches[1]
        if ($name -notin $allowed) {
            continue
        }
        $value = $Matches[2].Trim()
        if ($value.Length -ge 2 -and (
            ($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'"))
        )) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
    if ([string]::IsNullOrWhiteSpace($env:DEEPSEEK_API_KEY)) {
        throw "DEEPSEEK_API_KEY is not configured."
    }
}

function Assert-Preconditions {
    $branch = (& git -C $projectRoot branch --show-current).Trim()
    if ($branch -ne "feat/plugin-prd-analysis") {
        throw "Expected feat/plugin-prd-analysis; found $branch."
    }
    if (-not (Test-PortReleased 5001)) {
        throw "Port 5001 is already in use; no process was stopped."
    }
    foreach ($relativePath in @(
        "plugin/backend/app/analysis.py",
        "plugin/backend/app/providers.py",
        "plugin/backend/migrations/0001_initial.sql",
        "plugin/backend/migrations/0002_source_reference_audit.sql",
        "plugin/backend/migrations/0003_offline_revalidation.sql",
        "plugin/backend/app/constraints.py",
        "plugin/backend/app/offline_revalidation.py",
        "schemas/requirements/v2/prd_outline.schema.json",
        "schemas/requirements/v2/requirement_batch.schema.json",
        "schemas/requirements/v2/requirement_aggregate.schema.json",
        "prompts/prd-analysis/v2/outline_system.md",
        "prompts/prd-analysis/v2/requirements_system.md",
        "docs/prd/login_register_prd.md"
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $relativePath) -PathType Leaf)) {
            throw "Missing Phase 5A file: $relativePath"
        }
    }
    & git -C $projectRoot check-ignore -q -- ".env"
    if ($LASTEXITCODE -ne 0) {
        throw ".env is not ignored."
    }
    $trackedDatabase = @(& git -C $projectRoot ls-files -- "*plugin.db")
    if ($trackedDatabase.Count -ne 0) {
        throw "plugin.db must not be tracked."
    }
    if ($RealLLM -and -not $ConfirmPaidCall) {
        throw "-RealLLM also requires -ConfirmPaidCall."
    }
}

function Assert-PhaseBoundary {
    $changed = @(& git -C $projectRoot diff --name-only main)
    $changed += @(& git -C $projectRoot ls-files --others --exclude-standard)
    $allowed = @(
        "plugin/backend/",
        "schemas/requirements/",
        "prompts/prd-analysis/",
        "docs/testing/PLUGIN_PRD_ANALYSIS_",
        "docs/architecture/PLUGIN_BACKEND_IMPLEMENTATION.md",
        "docs/development/DEEPSEEK_SETUP.md",
        "docs/internal/PRD_ANALYSIS_PROMPT_REGISTER.md",
        "scripts/verify_phase5a.ps1",
        "pyproject.toml",
        ".env.example",
        ".prettierignore",
        "README.md",
        "plugin/__init__.py",
        "tests/test_foundation.py"
    )
    foreach ($path in $changed) {
        if (-not ($allowed | Where-Object { $path.StartsWith($_) -or $path -eq $_ })) {
            throw "Out-of-scope Phase 5A path: $path"
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
    Invoke-Step "Schema and Prompt validation" {
        & $python -c "from plugin.backend.app.schema_validation import RequirementSchemas; from plugin.backend.app.prompts import PromptRegistry; RequirementSchemas(); p=PromptRegistry(); assert p.content_hash"
    }
    Invoke-Step "Python default tests" {
        & $python -m pytest -q
    }
    Invoke-Step "Plugin coverage" {
        & $python -m pytest -q plugin/backend/tests --cov=plugin.backend.app --cov-report=term-missing --cov-branch --cov-fail-under=85
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
    $migrationOut = Join-Path $runDir "sut-migration-out.log"
    $migrationErr = Join-Path $runDir "sut-migration-err.log"
    $migration = Start-Process -FilePath $flask -ArgumentList @(
        "--app", "sut.backend.wsgi:app", "db", "upgrade"
    ) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $migrationOut -RedirectStandardError $migrationErr -Wait -PassThru
    if ($migration.ExitCode -ne 0) {
        throw "SUT migration failed."
    }
    $backendOut = Join-Path $runDir "sut-backend-out.log"
    $backendErr = Join-Path $runDir "sut-backend-err.log"
    $backendProcess = Start-Process -FilePath $python -ArgumentList @(
        "-m", "sut.backend.wsgi"
    ) -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $backendOut -RedirectStandardError $backendErr -PassThru
    Wait-Http "http://127.0.0.1:5001/api/health" $backendProcess
    Invoke-Step "Phase 3 API black-box regression" {
        & $python -m pytest -o "addopts=--strict-config --strict-markers -ra" -m black_box tests/api -q
    }
    Stop-OwnedProcess $backendProcess
    $backendProcess = $null
    if (-not (Test-PortReleased 5001)) {
        throw "Owned SUT backend stopped but port 5001 remains in use."
    }

    Invoke-Step "Git diff check" { & git -C $projectRoot diff --check }
    $secretMatches = @(& git -C $projectRoot grep -n -E "sk-[A-Za-z0-9_-]{20,}" -- .)
    if ($LASTEXITCODE -notin @(0, 1)) {
        throw "Secret scan command failed."
    }
    if ($secretMatches.Count -ne 0) {
        throw "Potential tracked secret detected."
    }

    if ($RealLLM) {
        Import-AllowedEnvironment
        if ($env:DEEPSEEK_BASE_URL -ne "https://api.deepseek.com") {
            throw "DEEPSEEK_BASE_URL is not the official endpoint."
        }
        if ($env:DEEPSEEK_MODEL -ne "deepseek-v4-pro") {
            throw "DEEPSEEK_MODEL must be deepseek-v4-pro for this acceptance."
        }
        if ([string]::IsNullOrWhiteSpace($env:PHASE5A_RECOVERY_SOURCE_RUN_ID)) {
            throw "PHASE5A_RECOVERY_SOURCE_RUN_ID is required for paid recovery."
        }
        $env:PHASE5A_REAL_CONFIRM = "YES"
        Invoke-Step "Real DeepSeek acceptance" {
            & $python -m plugin.backend.real_acceptance
        }
        Invoke-Step "Real DeepSeek marked test" {
            & $python -m pytest -o "addopts=--strict-config --strict-markers -ra" -m real_llm plugin/backend/tests/test_real_llm.py -q
        }
    }

    Write-Output "Phase 5A verification: PASS"
} finally {
    Stop-OwnedProcess $backendProcess
    Remove-Item Env:PHASE5A_REAL_CONFIRM -ErrorAction SilentlyContinue
    $resolvedRunDir = [IO.Path]::GetFullPath($runDir)
    $resolvedTempRoot = [IO.Path]::GetFullPath($tempRoot).TrimEnd("\") + "\"
    if (-not $resolvedRunDir.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean an unexpected runtime path."
    }
    if (Test-Path -LiteralPath $runDir -PathType Container) {
        Remove-Item -LiteralPath $runDir -Recurse -Force
    }
}
