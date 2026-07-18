[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv/Scripts/python.exe"
$flask = Join-Path $projectRoot ".venv/Scripts/flask.exe"
$node = (Get-Command node -ErrorAction Stop).Source
$vite = Join-Path $projectRoot "node_modules/vite/bin/vite.js"
$runId = [guid]::NewGuid().ToString("N")
$tempRoot = Join-Path $projectRoot "tmp/phase4"
$runDir = Join-Path $tempRoot $runId
$evidenceDir = Join-Path $projectRoot "artifacts/logs/phase4"
$summaryPath = Join-Path $evidenceDir "verification_summary.json"
$backendBase = "http://127.0.0.1:5001"
$frontendBase = "http://127.0.0.1:5173"
$origin = $frontendBase
$backendProcess = $null
$frontendProcess = $null
$verificationError = $null
$integrationPassed = $false
$apiBaselinePassed = $false
$seededStatus = $null
$corsPassed = $false
$cookiePassed = $false
$portsReleased = $false
$databaseCleaned = $false

function Get-PortListeners([int]$Port) {
    return @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Invoke-NativeStep([string]$Label, [scriptblock]$Command) {
    Write-Output "== $Label =="
    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Label failed with exit code $LASTEXITCODE."
    }
}

function Wait-Http([string]$Uri, [System.Diagnostics.Process]$Process) {
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if ($Process.HasExited) {
            throw "Process $($Process.Id) exited before $Uri became ready."
        }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                return
            }
        } catch {
            # Bounded readiness polling continues.
        }
        Start-Sleep -Milliseconds 250
    }
    throw "$Uri did not become ready within 15 seconds."
}

function Stop-OwnedProcess([System.Diagnostics.Process]$Process) {
    if ($null -ne $Process -and -not $Process.HasExited) {
        Stop-Process -Id $Process.Id -Force
        Wait-Process -Id $Process.Id -ErrorAction SilentlyContinue
    }
}

function Start-Backend([string]$DatabasePath, [string]$Label) {
    $env:SUT_DATABASE_URL = "sqlite:///$($DatabasePath.Replace('\\', '/'))"
    $migrationOut = Join-Path $runDir "$Label-migration-out.log"
    $migrationErr = Join-Path $runDir "$Label-migration-err.log"
    $migration = Start-Process -FilePath $flask -ArgumentList @("--app", "sut.backend.wsgi:app", "db", "upgrade") -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $migrationOut -RedirectStandardError $migrationErr -Wait -PassThru
    if ($migration.ExitCode -ne 0) {
        throw "$Label database migration failed."
    }
    $serverOut = Join-Path $runDir "$Label-server-out.log"
    $serverErr = Join-Path $runDir "$Label-server-err.log"
    $process = Start-Process -FilePath $python -ArgumentList @("-m", "sut.backend.wsgi") -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput $serverOut -RedirectStandardError $serverErr -PassThru
    Wait-Http "$backendBase/api/health" $process
    return $process
}

function Assert-Preconditions {
    $branch = (& git -C $projectRoot branch --show-current).Trim()
    if ($branch -ne "feat/sut-frontend-auth") {
        throw "Expected branch feat/sut-frontend-auth; found $branch."
    }
    if (@(Get-PortListeners 5001).Count -ne 0 -or @(Get-PortListeners 5173).Count -ne 0) {
        throw "Port 5001 or 5173 is already in use; no process was stopped."
    }
    foreach ($relativePath in @(
        "sut/frontend/src/pages/RegisterPage.tsx",
        "sut/frontend/src/pages/LoginPage.tsx",
        "sut/frontend/src/pages/ProfilePage.tsx",
        "sut/frontend/src/auth/AuthContext.tsx",
        "sut/frontend/src/auth/ProtectedRoute.tsx",
        "sut/frontend/src/api/authApi.ts",
        "docs/design/SUT_FRONTEND_DESIGN.md",
        "docs/testing/SUT_FRONTEND_TEST_PLAN.md"
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $relativePath) -PathType Leaf)) {
            throw "Missing Phase 4 file: $relativePath"
        }
    }
    $seedTest = Get-Content -Raw -LiteralPath (Join-Path $projectRoot "sut/frontend/src/authForms.test.tsx")
    if ($seedTest -notmatch "BUG-AUTH-001 allows a five-character username to reach the registration API") {
        throw "Protected frontend seeded-defect test is missing."
    }
}

Assert-Preconditions
[IO.Directory]::CreateDirectory($runDir) | Out-Null
[IO.Directory]::CreateDirectory($evidenceDir) | Out-Null
$env:SUT_SESSION_COOKIE_SECURE = "false"
$env:SUT_CORS_ALLOWED_ORIGINS = $origin
$env:PHASE3_BASE_URL = $backendBase
$env:PHASE3_EVIDENCE_DIR = $evidenceDir
$env:PYTHONUNBUFFERED = "1"

try {
    Invoke-NativeStep "Prettier" { & npm.cmd run format:check }
    Invoke-NativeStep "ESLint" { & npm.cmd run lint }
    Invoke-NativeStep "TypeScript" { & npm.cmd run typecheck }
    Invoke-NativeStep "Vitest" { & npm.cmd run test }
    Invoke-NativeStep "SUT frontend build" { & npm.cmd run build --workspace @ai-testpilot/sut-frontend }
    Invoke-NativeStep "Plugin foundation build" { & npm.cmd run build --workspace @ai-testpilot/plugin-frontend }
    Invoke-NativeStep "Python default pytest" { & $python -m pytest -q }

    $frontendOut = Join-Path $runDir "frontend-out.log"
    $frontendErr = Join-Path $runDir "frontend-err.log"
    $frontendProcess = Start-Process -FilePath $node -ArgumentList @($vite, "--host", "127.0.0.1", "--port", "5173", "--strictPort") -WorkingDirectory (Join-Path $projectRoot "sut/frontend") -WindowStyle Hidden -RedirectStandardOutput $frontendOut -RedirectStandardError $frontendErr -PassThru
    Wait-Http $frontendBase $frontendProcess
    foreach ($route in @("register", "login", "profile", "not-exist")) {
        $page = Invoke-WebRequest -UseBasicParsing -Uri "$frontendBase/$route" -TimeoutSec 3
        if ($page.StatusCode -ne 200 -or $page.Content -notmatch '<div id="root"></div>') {
            throw "Vite SPA route /$route was not served correctly."
        }
    }

    $integrationDb = Join-Path $runDir "integration.db"
    $backendProcess = Start-Backend $integrationDb "integration"
    $normalSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $normalUsername = "phase4_$($runId.Substring(0, 8))"
    $normalBody = @{
        username = $normalUsername
        password = "Test1234"
        password_confirmation = "Test1234"
    } | ConvertTo-Json
    $registration = Invoke-WebRequest -UseBasicParsing -Uri "$backendBase/api/auth/register" -Method Post -ContentType "application/json" -Headers @{ Origin = $origin } -Body $normalBody -WebSession $normalSession
    if ($registration.StatusCode -ne 201) {
        throw "Normal registration did not return 201."
    }
    $corsPassed = (
        $registration.Headers["Access-Control-Allow-Origin"] -eq $origin -and
        $registration.Headers["Access-Control-Allow-Credentials"] -eq "true"
    )
    if (-not $corsPassed) {
        throw "Credentialed CORS headers are incorrect."
    }
    $cookiePassed = $normalSession.Cookies.GetCookies([uri]$backendBase).Count -gt 0
    if (-not $cookiePassed) {
        throw "Browser-style session did not retain a cookie."
    }
    $me = Invoke-WebRequest -UseBasicParsing -Uri "$backendBase/api/auth/me" -WebSession $normalSession
    if ($me.StatusCode -ne 200 -or $me.Content -notmatch $normalUsername) {
        throw "Authenticated current-user integration failed."
    }
    $logout = Invoke-WebRequest -UseBasicParsing -Uri "$backendBase/api/auth/logout" -Method Post -Headers @{ Origin = $origin } -WebSession $normalSession
    if ($logout.StatusCode -ne 204) {
        throw "Logout integration failed."
    }
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "$backendBase/api/auth/me" -WebSession $normalSession | Out-Null
        throw "The session remained usable after logout."
    } catch {
        if ($_.Exception.Response.StatusCode.value__ -ne 401) {
            throw
        }
    }

    $seedSession = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    $seedBody = @{
        username = "z1234"
        password = "Test1234"
        password_confirmation = "Test1234"
    } | ConvertTo-Json
    $seedResponse = Invoke-WebRequest -UseBasicParsing -Uri "$backendBase/api/auth/register" -Method Post -ContentType "application/json" -Headers @{ Origin = $origin } -Body $seedBody -WebSession $seedSession
    $seededStatus = $seedResponse.StatusCode
    if ($seededStatus -ne 201) {
        throw "Protected BUG-AUTH-001 integration did not return 201."
    }
    $integrationPassed = $true

    Stop-OwnedProcess $backendProcess
    $backendProcess = $null
    for ($attempt = 0; $attempt -lt 30 -and @(Get-PortListeners 5001).Count -ne 0; $attempt++) {
        Start-Sleep -Milliseconds 100
    }

    $apiDb = Join-Path $runDir "api-baseline.db"
    $backendProcess = Start-Backend $apiDb "api"
    $apiLog = Join-Path $evidenceDir "pytest_api.log"
    $apiOutput = @(& $python -m pytest -o "addopts=--strict-config --strict-markers -ra" -m black_box tests/api 2>&1)
    $apiExit = $LASTEXITCODE
    $apiOutput | Set-Content -LiteralPath $apiLog -Encoding utf8
    $apiOutput | Write-Output
    if ($apiExit -ne 0 -or ($apiOutput -join [Environment]::NewLine) -notmatch "20 passed, 1 xfailed") {
        throw "Phase 3 black-box baseline did not produce 20 passed and 1 xfailed."
    }
    $apiBaselinePassed = $true

    Invoke-NativeStep "Git diff check" { & git -C $projectRoot diff --check }
    $trackedRuntime = @(& git -C $projectRoot ls-files | Where-Object { $_ -match '(^|/)(dist|coverage|node_modules|tmp)(/|$)|\\.(db|sqlite|sqlite3|log)$|(^|/)\\.env$' })
    if ($trackedRuntime.Count -ne 0) {
        throw "Tracked runtime artifact detected."
    }
} catch {
    $verificationError = $_.Exception.Message
} finally {
    Stop-OwnedProcess $backendProcess
    Stop-OwnedProcess $frontendProcess

    $resolvedRunDir = [IO.Path]::GetFullPath($runDir)
    $resolvedTempRoot = [IO.Path]::GetFullPath($tempRoot).TrimEnd("\") + "\"
    if (-not $resolvedRunDir.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean an unexpected runtime path."
    }
    if (Test-Path -LiteralPath $runDir -PathType Container) {
        Remove-Item -LiteralPath $runDir -Recurse -Force
    }
    $databaseCleaned = -not (Test-Path -LiteralPath $runDir)
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        if (@(Get-PortListeners 5001).Count -eq 0 -and @(Get-PortListeners 5173).Count -eq 0) {
            $portsReleased = $true
            break
        }
        Start-Sleep -Milliseconds 100
    }
}

$passed = (
    $null -eq $verificationError -and
    $integrationPassed -and
    $apiBaselinePassed -and
    $seededStatus -eq 201 -and
    $corsPassed -and
    $cookiePassed -and
    $databaseCleaned -and
    $portsReleased
)
$summary = [ordered]@{
    schema_version = "1.0"
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    branch = (& git -C $projectRoot branch --show-current).Trim()
    integration_passed = $integrationPassed
    api_baseline_passed = $apiBaselinePassed
    seeded_bug_id = "BUG-AUTH-001"
    seeded_status = $seededStatus
    cors_passed = $corsPassed
    cookie_session_passed = $cookiePassed
    database_cleaned = $databaseCleaned
    ports_released = $portsReleased
    result = $(if ($passed) { "PASS" } else { "FAIL" })
    failure_message = $verificationError
}
$summary | ConvertTo-Json | Set-Content -LiteralPath $summaryPath -Encoding utf8

$evidencePaths = @(
    $summaryPath,
    (Join-Path $evidenceDir "pytest_api.log"),
    (Join-Path $evidenceDir "http_evidence.json")
)
foreach ($evidencePath in $evidencePaths) {
    if (-not (Test-Path -LiteralPath $evidencePath -PathType Leaf)) {
        Write-Output "Phase 4 verification: FAIL (missing evidence file)"
        exit 1
    }
    $evidenceText = Get-Content -Raw -LiteralPath $evidencePath
    if ($evidenceText -match 'Test1234|Wrong1234|sut_session=|"password"\\s*:|"token_hash"\\s*:|Cookie:') {
        Write-Output "Phase 4 verification: FAIL (sensitive content detected)"
        exit 1
    }
}
if (-not $passed) {
    Write-Output "Phase 4 verification: FAIL ($verificationError)"
    exit 1
}
Write-Output "Phase 4 verification: PASS"
exit 0
