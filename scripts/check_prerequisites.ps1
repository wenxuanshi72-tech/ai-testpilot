[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$script:HasFailure = $false

function Write-Check {
    param(
        [Parameter(Mandatory)]
        [ValidateSet("PASS", "WARN", "FAIL", "INFO")]
        [string]$Status,

        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$Message
    )

    if ($Status -eq "FAIL") {
        $script:HasFailure = $true
    }

    Write-Output ("[{0}] {1}: {2}" -f $Status, $Name, $Message)
}

function Get-CommandVersion {
    param(
        [Parameter(Mandatory)]
        [string]$CommandName,

        [Parameter(Mandatory)]
        [string[]]$Arguments
    )

    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if (-not $command) {
        return $null
    }

    $output = & $command.Source @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        return $null
    }

    return (($output | Out-String).Trim())
}

$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
Write-Output "AI TestPilot prerequisite check (read-only)"
Write-Output ("Project root: {0}" -f $projectRoot)

$gitVersion = Get-CommandVersion -CommandName "git" -Arguments @("--version")
if ($gitVersion) {
    Write-Check -Status "PASS" -Name "Git" -Message $gitVersion
} else {
    Write-Check -Status "FAIL" -Name "Git" -Message "Git is missing or cannot report its version."
}

$pythonVersion = Get-CommandVersion -CommandName "python" -Arguments @("--version")
if ($pythonVersion) {
    $versionMatch = [regex]::Match($pythonVersion, "(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)")
    if ($versionMatch.Success -and $versionMatch.Groups["major"].Value -eq "3" -and $versionMatch.Groups["minor"].Value -eq "11") {
        Write-Check -Status "PASS" -Name "Python" -Message ("{0} (target: Python 3.11)" -f $pythonVersion)
    } else {
        Write-Check -Status "FAIL" -Name "Python" -Message ("{0}; this workspace targets Python 3.11.x." -f $pythonVersion)
    }
} else {
    Write-Check -Status "FAIL" -Name "Python" -Message "Python is missing or cannot report its version."
}

$pipVersion = Get-CommandVersion -CommandName "python" -Arguments @("-m", "pip", "--version")
if ($pipVersion) {
    Write-Check -Status "PASS" -Name "pip" -Message $pipVersion
} else {
    Write-Check -Status "FAIL" -Name "pip" -Message "python -m pip is unavailable."
}

$nodeVersion = Get-CommandVersion -CommandName "node" -Arguments @("--version")
if ($nodeVersion) {
    $nodeMatch = [regex]::Match($nodeVersion, "v(?<major>\d+)\.(?<minor>\d+)\.(?<patch>\d+)")
    $nodeSupported = $nodeMatch.Success -and (
        [int]$nodeMatch.Groups["major"].Value -gt 20 -or
        ([int]$nodeMatch.Groups["major"].Value -eq 20 -and [int]$nodeMatch.Groups["minor"].Value -ge 19)
    )
    if ($nodeSupported) {
        Write-Check -Status "PASS" -Name "Node.js" -Message ("{0} (manifest minimum: 20.19.0)" -f $nodeVersion)
    } else {
        Write-Check -Status "FAIL" -Name "Node.js" -Message ("{0}; package.json requires Node >=20.19.0." -f $nodeVersion)
    }
} else {
    Write-Check -Status "FAIL" -Name "Node.js" -Message "Node.js is missing or cannot report its version."
}

$npmVersion = Get-CommandVersion -CommandName "npm" -Arguments @("--version")
if ($npmVersion) {
    Write-Check -Status "PASS" -Name "npm" -Message $npmVersion
} else {
    Write-Check -Status "FAIL" -Name "npm" -Message "npm is missing or cannot report its version."
}

$browserCommands = @("msedge", "chrome", "firefox")
$browsersOnPath = @($browserCommands | Where-Object { Get-Command $_ -ErrorAction SilentlyContinue })
if ($browsersOnPath.Count -gt 0) {
    Write-Check -Status "INFO" -Name "Browser" -Message ("Commands on PATH: {0}. Playwright-managed browsers are validated only after authorized installation." -f ($browsersOnPath -join ", "))
} else {
    Write-Check -Status "WARN" -Name "Browser" -Message "No supported browser command is on PATH. A later Playwright phase must validate its managed browser without a global install."
}

$dotEnvPath = Join-Path $projectRoot ".env"
if (Test-Path -LiteralPath $dotEnvPath) {
    & git -C $projectRoot check-ignore --quiet -- .env
    if ($LASTEXITCODE -eq 0) {
        Write-Check -Status "WARN" -Name ".env" -Message "A local .env exists and is ignored. Its content was not read."
    } else {
        Write-Check -Status "FAIL" -Name ".env" -Message "A local .env exists but is not ignored. Its content was not read."
    }
} else {
    Write-Check -Status "PASS" -Name ".env" -Message "No local .env exists; .env.example remains the safe template."
}

$generatedDirectoryNames = @("node_modules", ".venv", "venv", "__pycache__")
$generatedDirectories = @(
    Get-ChildItem -LiteralPath $projectRoot -Recurse -Force -Directory -ErrorAction Stop |
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
Write-Check -Status $(if ($unsafeGeneratedDirectories.Count -eq 0) { "PASS" } else { "FAIL" }) -Name "Generated directories" -Message $(if ($unsafeGeneratedDirectories.Count -eq 0) { "Installed dependencies, virtual environments, and caches are ignored and untracked." } else { "Unsafe generated directories: $($unsafeGeneratedDirectories -join ', ')" })

$runtimeFiles = @(
    Get-ChildItem -LiteralPath $projectRoot -Recurse -Force -File -ErrorAction Stop |
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
if ($unsafeRuntimeFiles.Count -eq 0) {
    Write-Check -Status "PASS" -Name "Runtime files" -Message "Database and runtime-log files are absent or safely ignored and untracked."
} else {
    Write-Check -Status "FAIL" -Name "Runtime files" -Message ("Unsafe runtime files: {0}" -f ($unsafeRuntimeFiles -join ", "))
}
if ($script:HasFailure) {
    Write-Output "Prerequisite result: FAIL"
    exit 1
}

Write-Output "Prerequisite result: PASS (warnings are informational and require later-phase review)"
exit 0
