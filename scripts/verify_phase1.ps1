[CmdletBinding()]
param(
    [switch]$Toolchain
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:Failures = [System.Collections.Generic.List[string]]::new()

function Add-Result {
    param(
        [Parameter(Mandatory)]
        [bool]$Passed,

        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$Message
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
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$FilePath,

        [string[]]$Arguments = @()
    )

    Write-Output ("--- {0} ---" -f $Name)
    & $FilePath @Arguments
    $exitCode = $LASTEXITCODE
    Add-Result -Passed ($exitCode -eq 0) -Name $Name -Message ("Exit code: {0}" -f $exitCode)
}
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$phase0Commit = "62330a2be3949fde13fa310377c14144fa633b2f"

Write-Output "AI TestPilot Phase 1 verification (read-only)"
Write-Output ("Project root: {0}" -f $projectRoot)

$requiredDirectories = @(
    "sut/backend", "sut/frontend", "plugin/backend", "plugin/frontend",
    "docs/architecture", "docs/design", "docs/testing", "docs/development", "docs/decisions", "docs/prd", "docs/srs", "docs/internal",
    "schemas/requirements", "schemas/test-cases", "schemas/results", "schemas/bugs",
    "prompts/prd-analysis", "prompts/test-generation", "prompts/failure-analysis", "prompts/reporting",
    "test-specs/api", "test-specs/ui", "test-specs/manual",
    "artifacts/reports", "artifacts/bugs", "artifacts/evidence", "artifacts/exports", "artifacts/logs",
    "scripts", "tests"
)

$missingDirectories = @($requiredDirectories | Where-Object { -not (Test-Path -LiteralPath (Join-Path $projectRoot $_) -PathType Container) })
Add-Result -Passed ($missingDirectories.Count -eq 0) -Name "Required directories" -Message $(if ($missingDirectories.Count -eq 0) { "All required Phase 1 directories exist." } else { "Missing: $($missingDirectories -join ', ')" })

$requiredFiles = @(
    "AGENTS.md", ".env.example", ".gitignore", ".editorconfig", ".gitattributes", ".prettierignore",
    "README.md", "package.json", "package-lock.json", "pyproject.toml", "tsconfig.base.json", "eslint.config.mjs", "prettier.config.mjs",
    "sut/backend/README.md", "sut/frontend/package.json", "sut/frontend/tsconfig.json", "sut/frontend/vite.config.ts", "sut/frontend/vitest.config.ts", "sut/frontend/index.html", "sut/frontend/src/main.tsx", "sut/frontend/src/App.tsx",
    "plugin/backend/README.md", "plugin/frontend/package.json", "plugin/frontend/tsconfig.json", "plugin/frontend/vite.config.ts", "plugin/frontend/vitest.config.ts", "plugin/frontend/index.html", "plugin/frontend/src/main.tsx", "plugin/frontend/src/App.tsx",
    "scripts/check_prerequisites.ps1", "scripts/verify_phase1.ps1", "tests/test_foundation.py",
    "docs/PROJECT_CONTRACT.md", "docs/ROADMAP.md", "docs/architecture/SYSTEM_ARCHITECTURE.md", "docs/architecture/DATABASE_DESIGN.md", "docs/architecture/API_BOUNDARIES.md", "docs/architecture/SECURITY_AND_PRIVACY.md", "docs/testing/ACCEPTANCE_STRATEGY.md",
    "docs/development/DEVELOPMENT_SETUP.md", "docs/development/CONTRIBUTING.md",
    "docs/decisions/ADR-001-LOCAL-FIRST-MODULAR-MONOLITH.md", "docs/decisions/ADR-002-DETERMINISTIC-TEST-ORACLE.md", "docs/decisions/ADR-003-REAL-AND-MOCK-PROVIDER-SEPARATION.md"
)

$missingFiles = @()
$emptyFiles = @()
foreach ($relativePath in $requiredFiles) {
    $path = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        $missingFiles += $relativePath
    } elseif ((Get-Item -LiteralPath $path).Length -eq 0) {
        $emptyFiles += $relativePath
    }
}
Add-Result -Passed ($missingFiles.Count -eq 0) -Name "Required files" -Message $(if ($missingFiles.Count -eq 0) { "All required files exist." } else { "Missing: $($missingFiles -join ', ')" })
Add-Result -Passed ($emptyFiles.Count -eq 0) -Name "Non-empty files" -Message $(if ($emptyFiles.Count -eq 0) { "All required files are non-empty." } else { "Empty: $($emptyFiles -join ', ')" })

$branch = (& git -C $projectRoot branch --show-current).Trim()
Add-Result -Passed ($branch -eq "chore/project-foundation") -Name "Branch" -Message ("Current branch: {0}" -f $branch)

& git -C $projectRoot merge-base --is-ancestor $phase0Commit HEAD
Add-Result -Passed ($LASTEXITCODE -eq 0) -Name "Phase 0 commit" -Message "The approved Phase 0 commit remains an ancestor."

$protectedPhase0Files = @(
    "AGENTS.md", ".env.example", "docs/PROJECT_CONTRACT.md", "docs/ROADMAP.md",
    "docs/architecture/SYSTEM_ARCHITECTURE.md", "docs/architecture/DATA_FLOW.md", "docs/architecture/DATABASE_DESIGN.md",
    "docs/architecture/API_BOUNDARIES.md", "docs/architecture/TEST_CASE_PROTOCOL.md", "docs/architecture/LLM_RELIABILITY_DESIGN.md",
    "docs/architecture/TRACEABILITY_DESIGN.md", "docs/architecture/EXPORT_FORMATS.md", "docs/architecture/SECURITY_AND_PRIVACY.md",
    "docs/design/DESIGN_DIRECTION.md", "docs/testing/ACCEPTANCE_STRATEGY.md"
)
& git -C $projectRoot diff --quiet $phase0Commit -- $protectedPhase0Files
Add-Result -Passed ($LASTEXITCODE -eq 0) -Name "Phase 0 documents" -Message "Approved Phase 0 contracts are unchanged."

$agentContract = Get-Content -Raw -LiteralPath (Join-Path $projectRoot "AGENTS.md")
$bugContractValid = $agentContract.Contains("REQ-AUTH-USERNAME-001") -and $agentContract.Contains("z1234") -and $agentContract.Contains("Test1234") -and $agentContract.Contains('returns `201`')
Add-Result -Passed $bugContractValid -Name "Seeded defect contract" -Message "The protected requirement, data, and intentionally defective 201 behavior remain documented."

$dotEnvPath = Join-Path $projectRoot ".env"
if (Test-Path -LiteralPath $dotEnvPath) {
    & git -C $projectRoot check-ignore --quiet -- .env
    $dotEnvIgnored = $LASTEXITCODE -eq 0
} else {
    $dotEnvIgnored = $true
}
$dotEnvTracked = $null -ne (& git -C $projectRoot ls-files -- .env)
Add-Result -Passed (-not $dotEnvTracked -and $dotEnvIgnored) -Name ".env safety" -Message ".env is not tracked; existing content, if any, was not read."

$templateTracked = $null -ne (& git -C $projectRoot ls-files -- .env.example)
Add-Result -Passed $templateTracked -Name ".env.example" -Message "The safe environment template remains tracked."

$generatedDirectoryNames = @("node_modules", ".venv", "venv", "__pycache__")
$generatedDirectories = @(
    Get-ChildItem -LiteralPath $projectRoot -Recurse -Force -Directory |
        Where-Object {
            -not $_.FullName.Contains("\.git\") -and $_.Name -in $generatedDirectoryNames
        }
)
$unsafeGeneratedDirectories = @()
foreach ($directory in $generatedDirectories) {
    $relativePath = $directory.FullName.Substring($projectRoot.Length + 1).Replace("\", "/")
    & git -C $projectRoot check-ignore --quiet -- $relativePath
    $ignored = $LASTEXITCODE -eq 0
    $tracked = @(& git -C $projectRoot ls-files -- $relativePath).Count -gt 0
    if (-not $ignored -or $tracked) {
        $unsafeGeneratedDirectories += $relativePath
    }
}
Add-Result -Passed ($unsafeGeneratedDirectories.Count -eq 0) -Name "Generated directories" -Message $(if ($unsafeGeneratedDirectories.Count -eq 0) { "Installed dependencies, virtual environments, and caches are ignored and untracked." } else { "Unsafe generated directories: $($unsafeGeneratedDirectories -join ', ')" })

$nodeModulesPath = Join-Path $projectRoot "node_modules"
$venvPythonPath = Join-Path $projectRoot ".venv/Scripts/python.exe"
$toolchainInstalled = (Test-Path -LiteralPath $nodeModulesPath -PathType Container) -and (Test-Path -LiteralPath $venvPythonPath -PathType Leaf)
Add-Result -Passed $toolchainInstalled -Name "Installed toolchain" -Message $(if ($toolchainInstalled) { "Node dependencies and the Python virtual environment are installed locally." } else { "node_modules or .venv/Scripts/python.exe is missing." })
$runtimeFiles = @(
    Get-ChildItem -LiteralPath $projectRoot -Recurse -Force -File |
        Where-Object {
            -not $_.FullName.Contains("\.git\") -and $_.Extension -in @(".db", ".sqlite", ".sqlite3", ".log")
        }
)
$unsafeRuntimeFiles = @()
foreach ($file in $runtimeFiles) {
    $relativePath = $file.FullName.Substring($projectRoot.Length + 1).Replace("\", "/")
    & git -C $projectRoot check-ignore --quiet -- $relativePath
    $ignored = $LASTEXITCODE -eq 0
    $tracked = @(& git -C $projectRoot ls-files -- $relativePath).Count -gt 0
    if (-not $ignored -or $tracked) {
        $unsafeRuntimeFiles += $relativePath
    }
}
Add-Result -Passed ($unsafeRuntimeFiles.Count -eq 0) -Name "Runtime artifacts" -Message $(if ($unsafeRuntimeFiles.Count -eq 0) { "Database and runtime-log files are absent or safely ignored and untracked." } else { "Unsafe runtime files: $($unsafeRuntimeFiles -join ', ')" })
$artifactViolations = @(
    Get-ChildItem -LiteralPath (Join-Path $projectRoot "artifacts") -Recurse -Force -File |
        Where-Object { $_.Name -notin @(".gitkeep", "README.md") }
)
Add-Result -Passed ($artifactViolations.Count -eq 0) -Name "Formal artifacts" -Message $(if ($artifactViolations.Count -eq 0) { "No report, bug, evidence, export, or runtime log has been generated." } else { "Unexpected formal/runtime artifacts exist." })

$backendImplementations = @(
    Get-ChildItem -LiteralPath (Join-Path $projectRoot "sut/backend") -Recurse -File -Filter "*.py"
    Get-ChildItem -LiteralPath (Join-Path $projectRoot "plugin/backend") -Recurse -File -Filter "*.py"
)
Add-Result -Passed ($backendImplementations.Count -eq 0) -Name "Backend business implementation" -Message "No Python backend module or Flask route exists."

$frontendSource = @(
    Get-ChildItem -LiteralPath (Join-Path $projectRoot "sut/frontend/src") -Recurse -File -Include "*.ts", "*.tsx"
    Get-ChildItem -LiteralPath (Join-Path $projectRoot "plugin/frontend/src") -Recurse -File -Include "*.ts", "*.tsx"
)
$forbiddenSourcePattern = "(/api/auth|createBrowserRouter|<Route|axios\.|DeepSeek|Playwright|register\(|login\()"
$businessMatches = @()
foreach ($file in $frontendSource) {
    if (Select-String -LiteralPath $file.FullName -Pattern $forbiddenSourcePattern -CaseSensitive:$false -Quiet) {
        $businessMatches += $file.FullName
    }
}
Add-Result -Passed ($businessMatches.Count -eq 0) -Name "Frontend business implementation" -Message "Frontend source contains only foundation shells and shell tests."

$candidateFiles = @(& git -C $projectRoot ls-files --cached --others --exclude-standard)
$secretPatterns = @(
    "sk-[A-Za-z0-9_-]{16,}",
    "AKIA[A-Z0-9]{16}",
    "-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"
)
$secretMatches = @()
foreach ($relativePath in $candidateFiles) {
    if ($relativePath -eq ".env") {
        continue
    }

    $path = Join-Path $projectRoot $relativePath
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        continue
    }

    if ((Get-Item -LiteralPath $path).Length -gt 2MB) {
        continue
    }

    $content = Get-Content -Raw -LiteralPath $path -ErrorAction SilentlyContinue
    foreach ($pattern in $secretPatterns) {
        if ($content -match $pattern) {
            $secretMatches += $relativePath
            break
        }
    }
}
Add-Result -Passed ($secretMatches.Count -eq 0) -Name "Secret scan" -Message $(if ($secretMatches.Count -eq 0) { "No high-confidence API key or private-key pattern was found." } else { "Potential secrets: $($secretMatches -join ', ')" })

foreach ($jsonPath in @("package.json", "sut/frontend/package.json", "plugin/frontend/package.json", "tsconfig.base.json", "sut/frontend/tsconfig.json", "plugin/frontend/tsconfig.json")) {
    try {
        Get-Content -Raw -LiteralPath (Join-Path $projectRoot $jsonPath) | ConvertFrom-Json | Out-Null
        Add-Result -Passed $true -Name ("JSON: {0}" -f $jsonPath) -Message "Valid JSON."
    } catch {
        Add-Result -Passed $false -Name ("JSON: {0}" -f $jsonPath) -Message "Invalid JSON."
    }
}

& node -e "JSON.parse(require('fs').readFileSync('package-lock.json', 'utf8'))" 2>$null
Add-Result -Passed ($LASTEXITCODE -eq 0) -Name "JSON: package-lock.json" -Message "Valid npm lockfile JSON."
& python -c "import pathlib,tomllib; tomllib.loads(pathlib.Path('pyproject.toml').read_text(encoding='utf-8'))" 2>$null
Add-Result -Passed ($LASTEXITCODE -eq 0) -Name "pyproject.toml" -Message "Python 3.11 parsed the TOML configuration."

if ($Toolchain) {
    $npmPath = (Get-Command npm -ErrorAction Stop).Source
    $ruffPath = Join-Path $projectRoot ".venv/Scripts/ruff.exe"
    $mypyPath = Join-Path $projectRoot ".venv/Scripts/mypy.exe"
    $pytestPath = Join-Path $projectRoot ".venv/Scripts/pytest.exe"

    Invoke-CheckedCommand -Name "Prettier" -FilePath $npmPath -Arguments @("run", "format:check")
    Invoke-CheckedCommand -Name "ESLint" -FilePath $npmPath -Arguments @("run", "lint")
    Invoke-CheckedCommand -Name "TypeScript" -FilePath $npmPath -Arguments @("run", "typecheck")
    Invoke-CheckedCommand -Name "Vitest" -FilePath $npmPath -Arguments @("run", "test")
    Invoke-CheckedCommand -Name "Vite build" -FilePath $npmPath -Arguments @("run", "build")
    Invoke-CheckedCommand -Name "Ruff format" -FilePath $ruffPath -Arguments @("format", "--check", ".")
    Invoke-CheckedCommand -Name "Ruff lint" -FilePath $ruffPath -Arguments @("check", ".")
    Invoke-CheckedCommand -Name "mypy" -FilePath $mypyPath -Arguments @("tests")
    Invoke-CheckedCommand -Name "pytest coverage" -FilePath $pytestPath -Arguments @("--cov=tests", "--cov-report=term-missing", "--cov-fail-under=80")

    $buildOutputs = @("sut/frontend/dist/index.html", "plugin/frontend/dist/index.html")
    $missingBuildOutputs = @($buildOutputs | Where-Object { -not (Test-Path -LiteralPath (Join-Path $projectRoot $_) -PathType Leaf) })
    Add-Result -Passed ($missingBuildOutputs.Count -eq 0) -Name "Build outputs" -Message $(if ($missingBuildOutputs.Count -eq 0) { "Both frontend production builds generated index.html." } else { "Missing: $($missingBuildOutputs -join ', ')" })
}

$remoteOutput = @(& git -C $projectRoot remote -v)
Add-Result -Passed ($LASTEXITCODE -eq 0) -Name "Git remotes" -Message ("Read-only check completed; configured entries: {0}." -f $remoteOutput.Count)

if ($script:Failures.Count -gt 0) {
    Write-Output ("Phase 1 verification: FAIL ({0})" -f (($script:Failures | Select-Object -Unique) -join ", "))
    exit 1
}

Write-Output "Phase 1 verification: PASS"
exit 0
