[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv/Scripts/python.exe"
$flask = Join-Path $projectRoot ".venv/Scripts/flask.exe"
$evidenceDir = Join-Path $projectRoot "artifacts/logs/phase3"
$tempRoot = Join-Path $projectRoot "tmp/phase3"
$runId = [guid]::NewGuid().ToString("N")
$runDir = Join-Path $tempRoot $runId
$databasePath = Join-Path $runDir "sut-phase3.db"
$junitPath = Join-Path $runDir "pytest-api.xml"
$serverLog = Join-Path $evidenceDir "server.log"
$migrationStdout = Join-Path $runDir "migration-stdout.log"
$migrationStderr = Join-Path $runDir "migration-stderr.log"
$serverStdout = Join-Path $runDir "server-stdout.log"
$serverStderr = Join-Path $runDir "server-stderr.log"
$pytestLog = Join-Path $evidenceDir "pytest_api.log"
$summaryPath = Join-Path $evidenceDir "verification_summary.json"
$httpEvidencePath = Join-Path $evidenceDir "http_evidence.json"
$serverProcess = $null
$verificationError = $null
$pytestExitCode = $null
$ordinaryPassed = 0
$xfailCount = 0
$failureCount = 0
$errorCount = 0
$seededActualStatus = $null
$serviceReady = $false
$migrationPassed = $false
$databaseCleaned = $false
$portReleased = $false

function Get-Port5001Listeners {
    return @(Get-NetTCPConnection -LocalPort 5001 -State Listen -ErrorAction SilentlyContinue)
}

function Assert-Phase3Preconditions {
    $branch = (& git -C $projectRoot branch --show-current).Trim()
    if ($branch -ne "test/sut-api-acceptance") {
        throw "Expected branch test/sut-api-acceptance; found $branch"
    }
    if (@(Get-Port5001Listeners).Count -ne 0) {
        throw "Port 5001 is already in use; no process was started or stopped."
    }
    foreach ($relativePath in @(
        "tests/api/test_sut_auth_api.py",
        "test-specs/api/sut_auth_api_cases.yaml",
        "docs/testing/SUT_API_ACCEPTANCE_PLAN.md"
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $relativePath) -PathType Leaf)) {
            throw "Missing Phase 3 file: $relativePath"
        }
    }
}

function Test-EvidenceRedaction {
    foreach ($path in @($serverLog, $pytestLog, $summaryPath, $httpEvidencePath)) {
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
            throw "Missing evidence file: $([IO.Path]::GetFileName($path))"
        }
        $content = Get-Content -Raw -LiteralPath $path
        foreach ($pattern in @(
            "Test1234",
            "Wrong1234",
            "sut_session=",
            '"password"\s*:',
            '"password_confirmation"\s*:',
            '"token_hash"\s*:',
            'Cookie:\s*[^\r\n]+'
        )) {
            if ($content -match $pattern) {
                throw "Sensitive content detected in $([IO.Path]::GetFileName($path))."
            }
        }
    }
}

Assert-Phase3Preconditions
[System.IO.Directory]::CreateDirectory($evidenceDir) | Out-Null
[System.IO.Directory]::CreateDirectory($runDir) | Out-Null

$env:SUT_DATABASE_URL = "sqlite:///D:/AI-TestPilot/ai-test-flow-prototype-v3/tmp/phase3/$runId/sut-phase3.db"
$env:SUT_SESSION_COOKIE_SECURE = "false"
$env:PHASE3_BASE_URL = "http://127.0.0.1:5001"
$env:PHASE3_EVIDENCE_DIR = $evidenceDir
$env:PYTHONUNBUFFERED = "1"

try {
    $migrationProcess = Start-Process `
        -FilePath $flask `
        -ArgumentList @("--app", "sut.backend.wsgi:app", "db", "upgrade") `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $migrationStdout `
        -RedirectStandardError $migrationStderr `
        -Wait `
        -PassThru
    if ($migrationProcess.ExitCode -ne 0) {
        throw "Database migration failed."
    }
    $migrationPassed = $true

    $serverProcess = Start-Process `
        -FilePath $python `
        -ArgumentList @("-m", "sut.backend.wsgi") `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput $serverStdout `
        -RedirectStandardError $serverStderr `
        -PassThru

    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if ($serverProcess.HasExited) {
            throw "SUT process exited before readiness."
        }
        try {
            $health = Invoke-WebRequest `
                -UseBasicParsing `
                -Uri "http://127.0.0.1:5001/api/health" `
                -TimeoutSec 2
            if ($health.StatusCode -eq 200) {
                $serviceReady = $true
                break
            }
        } catch {
            # Readiness polling continues until the bounded deadline.
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $serviceReady) {
        throw "SUT did not become healthy within 10 seconds."
    }

    $pytestArguments = @(
        "-m", "pytest",
        "-o", "addopts=--strict-config --strict-markers -ra",
        "-m", "black_box",
        "tests/api",
        "--junitxml=$junitPath"
    )
    $pytestOutput = @(& $python @pytestArguments 2>&1)
    $pytestExitCode = $LASTEXITCODE
    $pytestOutput | Set-Content -LiteralPath $pytestLog -Encoding utf8
    $pytestOutput | Write-Output

    if (-not (Test-Path -LiteralPath $junitPath -PathType Leaf)) {
        throw "pytest did not produce JUnit results."
    }
    $junitSummaryJson = & $python tests/api/summarize_junit.py $junitPath
    if ($LASTEXITCODE -ne 0) {
        throw "JUnit result parsing failed."
    }
    $suite = $junitSummaryJson | ConvertFrom-Json
    $total = [int]$suite.tests
    $failureCount = [int]$suite.failures
    $errorCount = [int]$suite.errors
    $xfailCount = [int]$suite.skipped
    $ordinaryPassed = $total - $failureCount - $errorCount - $xfailCount

    if ($pytestExitCode -ne 0) {
        throw "Black-box pytest returned exit code $pytestExitCode."
    }
    if ($ordinaryPassed -ne 20 -or $xfailCount -ne 1 -or $failureCount -ne 0 -or $errorCount -ne 0) {
        throw "Unexpected result counts: pass=$ordinaryPassed xfail=$xfailCount fail=$failureCount error=$errorCount"
    }
    if (-not (Test-Path -LiteralPath $httpEvidencePath -PathType Leaf)) {
        throw "HTTP evidence was not produced."
    }
    $httpEvidence = Get-Content -Raw -LiteralPath $httpEvidencePath | ConvertFrom-Json
    $records = @($httpEvidence.records)
    $seededRecords = @($records | Where-Object { $_.case_id -eq "API-AUTH-SEED-001" })
    if ($records.Count -ne 21 -or $seededRecords.Count -ne 1) {
        throw "HTTP evidence does not contain exactly 21 cases and one seeded record."
    }
    $seeded = $seededRecords[0]
    $seededActualStatus = [int]$seeded.status
    if (
        $seeded.expected_status -ne 400 -or
        $seeded.status -ne 201 -or
        $seeded.result -ne "XFAIL" -or
        $seeded.classification -ne "known_seeded_product_defect" -or
        $seeded.linked_bug_id -ne "BUG-AUTH-001"
    ) {
        throw "Seeded-defect evidence is inconsistent."
    }
} catch {
    $verificationError = $_.Exception.Message
} finally {
    if ($null -ne $serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force
        Wait-Process -Id $serverProcess.Id -ErrorAction SilentlyContinue
    }
    Set-Content -LiteralPath $serverLog -Value "" -Encoding utf8
    foreach ($logPart in @($migrationStdout, $migrationStderr, $serverStdout, $serverStderr)) {
        if (Test-Path -LiteralPath $logPart -PathType Leaf) {
            Get-Content -LiteralPath $logPart | Add-Content -LiteralPath $serverLog -Encoding utf8
        }
    }

    $resolvedRunDir = [IO.Path]::GetFullPath($runDir)
    $resolvedTempRoot = [IO.Path]::GetFullPath($tempRoot).TrimEnd("\") + "\"
    if (-not $resolvedRunDir.StartsWith($resolvedTempRoot, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean an unexpected runtime path."
    }
    if (Test-Path -LiteralPath $runDir -PathType Container) {
        Remove-Item -LiteralPath $runDir -Recurse -Force
    }
    $databaseCleaned = -not (Test-Path -LiteralPath $databasePath)

    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if (@(Get-Port5001Listeners).Count -eq 0) {
            $portReleased = $true
            break
        }
        Start-Sleep -Milliseconds 100
    }
}

$verificationPassed = (
    $null -eq $verificationError -and
    $migrationPassed -and
    $serviceReady -and
    $pytestExitCode -eq 0 -and
    $ordinaryPassed -eq 20 -and
    $xfailCount -eq 1 -and
    $failureCount -eq 0 -and
    $errorCount -eq 0 -and
    $databaseCleaned -and
    $portReleased
)
$summary = [ordered]@{
    schema_version = "1.0"
    generated_at_utc = [DateTime]::UtcNow.ToString("o")
    git_commit = (& git -C $projectRoot rev-parse HEAD).Trim()
    branch = (& git -C $projectRoot branch --show-current).Trim()
    base_url = "http://127.0.0.1:5001"
    migration_passed = $migrationPassed
    service_ready = $serviceReady
    ordinary_passed = $ordinaryPassed
    xfail = $xfailCount
    failures = $failureCount
    errors = $errorCount
    seeded_case_id = "API-AUTH-SEED-001"
    seeded_expected_status = 400
    seeded_actual_status = $seededActualStatus
    seeded_bug_id = "BUG-AUTH-001"
    database_cleaned = $databaseCleaned
    port_released = $portReleased
    result = $(if ($verificationPassed) { "PASS" } else { "FAIL" })
    failure_message = $verificationError
}
$summary | ConvertTo-Json | Set-Content -LiteralPath $summaryPath -Encoding utf8

try {
    Test-EvidenceRedaction
} catch {
    $verificationPassed = $false
    if ($null -eq $verificationError) {
        $verificationError = $_.Exception.Message
    } else {
        $verificationError = "$verificationError; $($_.Exception.Message)"
    }
}

if (-not $verificationPassed) {
    Write-Output ("Phase 3 verification: FAIL ({0})" -f $verificationError)
    exit 1
}

Write-Output "Phase 3 verification: PASS (20 passed, 1 xfailed, 0 failed, 0 errors)"
exit 0
