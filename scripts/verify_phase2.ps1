[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:Failures = [System.Collections.Generic.List[string]]::new()

function Add-Result {
    param(
        [Parameter(Mandatory)][bool]$Passed,
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Message
    )
    if ($Passed) {
        Write-Output ("[PASS] {0}: {1}" -f $Name, $Message)
    } else {
        $script:Failures.Add($Name)
        Write-Output ("[FAIL] {0}: {1}" -f $Name, $Message)
    }
}

function Invoke-CheckedCommand {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$FilePath,
        [string[]]$Arguments = @()
    )
    Write-Output ("--- {0} ---" -f $Name)
    & $FilePath @Arguments
    $exitCode = $LASTEXITCODE
    Add-Result -Passed ($exitCode -eq 0) -Name $Name -Message ("Exit code: {0}" -f $exitCode)
}

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv/Scripts/python.exe"
$ruff = Join-Path $projectRoot ".venv/Scripts/ruff.exe"
$mypy = Join-Path $projectRoot ".venv/Scripts/mypy.exe"

Write-Output "AI TestPilot Phase 2 verification"
Write-Output ("Project root: {0}" -f $projectRoot)

$branch = (& git -C $projectRoot branch --show-current).Trim()
Add-Result -Passed ($branch -eq "feat/sut-backend-auth") -Name "Branch" -Message ("Current branch: {0}" -f $branch)

$requiredFiles = @(
    "docs/prd/login_register_prd.md",
    "docs/srs/login_register_srs.md",
    "docs/architecture/SUT_API_CONTRACT.md",
    "docs/internal/SEEDED_BUG_PLAN.md",
    "docs/testing/SUT_BACKEND_TEST_PLAN.md",
    "sut/backend/app/__init__.py",
    "sut/backend/app/config.py",
    "sut/backend/app/extensions.py",
    "sut/backend/app/models/user.py",
    "sut/backend/app/models/user_session.py",
    "sut/backend/app/routes/auth.py",
    "sut/backend/app/services/auth_service.py",
    "sut/backend/app/validation/auth.py",
    "sut/backend/migrations/versions/0001_sut_auth.py",
    "sut/backend/tests/test_registration.py",
    "sut/backend/wsgi.py",
    "scripts/verify_phase2.ps1"
)
$missingFiles = @($requiredFiles | Where-Object { -not (Test-Path -LiteralPath (Join-Path $projectRoot $_) -PathType Leaf) })
Add-Result -Passed ($missingFiles.Count -eq 0) -Name "Required files" -Message $(if ($missingFiles.Count -eq 0) { "All Phase 2 files exist." } else { "Missing: $($missingFiles -join ', ')" })

$prd = Get-Content -Raw -LiteralPath (Join-Path $projectRoot "docs/prd/login_register_prd.md")
$srs = Get-Content -Raw -LiteralPath (Join-Path $projectRoot "docs/srs/login_register_srs.md")
$bugPlan = Get-Content -Raw -LiteralPath (Join-Path $projectRoot "docs/internal/SEEDED_BUG_PLAN.md")
$contractsValid = $prd.Contains("minimum username length of six") -and $srs.Contains("REQ-AUTH-USERNAME-001") -and $bugPlan.Contains("BUG-AUTH-001") -and $bugPlan.Contains("z1234 / Test1234")
Add-Result -Passed $contractsValid -Name "Requirement contracts" -Message "Formal minimum-six requirement and protected defect trace IDs are present."

Invoke-CheckedCommand -Name "Ruff format" -FilePath $ruff -Arguments @("format", "--check", "sut/backend", "sut/__init__.py")
Invoke-CheckedCommand -Name "Ruff lint" -FilePath $ruff -Arguments @("check", "sut/backend", "sut/__init__.py")
Invoke-CheckedCommand -Name "mypy" -FilePath $mypy -Arguments @("sut/backend")
Invoke-CheckedCommand -Name "pytest coverage" -FilePath $python -Arguments @("-m", "pytest", "sut/backend/tests", "--cov=sut/backend/app", "--cov-report=term-missing", "--cov-branch", "--cov-fail-under=85")

$apiTests = @(
    "sut/backend/tests/test_registration.py::test_seeded_defect_allows_five_character_username",
    "sut/backend/tests/test_registration.py::test_duplicate_username_is_case_insensitive",
    "sut/backend/tests/test_authentication.py::test_login_and_current_user",
    "sut/backend/tests/test_authentication.py::test_me_requires_authentication",
    "sut/backend/tests/test_authentication.py::test_logout_revokes_session_and_is_idempotent"
)
Invoke-CheckedCommand -Name "Required API behaviors" -FilePath $python -Arguments (@("-m", "pytest", "-q") + $apiTests)
Invoke-CheckedCommand -Name "Migration upgrade" -FilePath $python -Arguments @("-m", "pytest", "-q", "sut/backend/tests/test_migrations.py")

$trackedDatabases = @(& git -C $projectRoot ls-files -- "*.db" "*.sqlite" "*.sqlite3")
Add-Result -Passed ($trackedDatabases.Count -eq 0) -Name "Tracked databases" -Message $(if ($trackedDatabases.Count -eq 0) { "No database is tracked." } else { "Tracked: $($trackedDatabases -join ', ')" })

$dotEnvExists = Test-Path -LiteralPath (Join-Path $projectRoot ".env")
Add-Result -Passed (-not $dotEnvExists) -Name ".env safety" -Message "No real .env exists."

$forbiddenPhaseChanges = @(& git -C $projectRoot diff --name-only main -- "sut/frontend" "plugin/backend" "plugin/frontend")
Add-Result -Passed ($forbiddenPhaseChanges.Count -eq 0) -Name "Phase boundary" -Message $(if ($forbiddenPhaseChanges.Count -eq 0) { "No frontend, Plugin, or Phase 3 implementation changed." } else { "Forbidden changes: $($forbiddenPhaseChanges -join ', ')" })

$candidateFiles = @(& git -C $projectRoot ls-files --cached --others --exclude-standard)
$secretPatterns = @(
    "sk-[A-Za-z0-9_-]{16,}",
    "AKIA[A-Z0-9]{16}",
    "-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
$secretMatches = @()
foreach ($relativePath in $candidateFiles) {
    $path = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { continue }
    if ((Get-Item -LiteralPath $path).Length -gt 2MB) { continue }
    $content = Get-Content -Raw -LiteralPath $path -ErrorAction SilentlyContinue
    foreach ($pattern in $secretPatterns) {
        if ($content -match $pattern) {
            $secretMatches += $relativePath
            break
        }
    }
}
Add-Result -Passed ($secretMatches.Count -eq 0) -Name "Secret scan" -Message $(if ($secretMatches.Count -eq 0) { "No high-confidence secret pattern was found." } else { "Potential secrets: $($secretMatches -join ', ')" })

if ($script:Failures.Count -gt 0) {
    Write-Output ("Phase 2 verification: FAIL ({0})" -f (($script:Failures | Select-Object -Unique) -join ", "))
    exit 1
}

Write-Output "Phase 2 verification: PASS"
exit 0
