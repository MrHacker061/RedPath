[CmdletBinding()]
param([string]$Compiler = 'ISCC.exe')

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$compilerCommand = Get-Command $Compiler -CommandType Application -ErrorAction SilentlyContinue
if (-not $compilerCommand) {
    Write-Host 'INSTALLER_BUILD_PREREQUISITE: Inno Setup ISCC.exe is missing. Install Inno Setup 6.3 or newer separately, then pass -Compiler with its absolute path.'
    exit 2
}
$desktop = Join-Path $projectRoot 'dist/RedPath/RedPath.exe'
if (-not (Test-Path -LiteralPath $desktop -PathType Leaf)) {
    Write-Host 'INSTALLER_BUILD_INPUT_MISSING: dist/RedPath/RedPath.exe is missing. Run scripts/build-desktop.ps1 first.'
    exit 2
}
$artifact = Join-Path $projectRoot 'dist/installer/RedPath-Setup-0.1.0-x64.exe'
# Avoid mistaking an earlier installer for newly produced output, without deleting it.
if (Test-Path -LiteralPath $artifact) {
    throw 'INSTALLER_BUILD_OUTPUT_EXISTS: Move the existing installer aside before rebuilding.'
}
$previousEpoch = $env:SOURCE_DATE_EPOCH
Push-Location $projectRoot
try {
    $env:SOURCE_DATE_EPOCH = '1789084800'
    & $compilerCommand.Source '/Qp' (Join-Path $projectRoot 'packaging/RedPath.iss')
    if ($LASTEXITCODE -ne 0) { throw 'INSTALLER_BUILD_FAILED: Inno Setup failed; review compiler output.' }
    if (-not (Test-Path -LiteralPath $artifact -PathType Leaf)) {
        throw 'INSTALLER_BUILD_FAILED: Inno Setup did not produce the expected installer.'
    }
    Write-Host "Installer: $artifact"
    Get-FileHash -LiteralPath $artifact -Algorithm SHA256
}
finally {
    $env:SOURCE_DATE_EPOCH = $previousEpoch
    Pop-Location
}
