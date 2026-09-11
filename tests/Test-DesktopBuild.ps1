[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$buildPath = Join-Path $projectRoot 'scripts/build-desktop.ps1'
$specPath = Join-Path $projectRoot 'packaging/redpath.spec'
foreach ($path in @($buildPath, $specPath)) {
    if (-not (Test-Path -LiteralPath $path)) { throw "DESKTOP_BUILD_TEST_FAILED: Missing $path" }
}
$tokens = $null
$parseErrors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile($buildPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'DESKTOP_BUILD_TEST_FAILED: PowerShell parse errors.' }
$build = Get-Content -LiteralPath $buildPath -Raw
$spec = Get-Content -LiteralPath $specPath -Raw
$project = Get-Content -LiteralPath (Join-Path $projectRoot 'pyproject.toml') -Raw
foreach ($required in @('DESKTOP_BUILD_PREREQUISITE', '.[desktop]', 'PyInstaller', '6.22.2', 'PYTHONHASHSEED', 'SOURCE_DATE_EPOCH', 'RedPath/RedPath.exe')) {
    if (-not $build.Contains($required)) { throw "DESKTOP_BUILD_TEST_FAILED: Missing $required" }
}
if ($build -match '(?m)^\s*(?:&.*)?(?:pip|winget|choco)\s+install') {
    throw 'DESKTOP_BUILD_TEST_FAILED: Build must not install tools.'
}
foreach ($required in @('console=False', 'frontend', 'collect_data_files', 'redpath_setup', 'redpath_kali', 'redpath_ai', 'upx=False')) {
    if (-not $spec.Contains($required)) { throw "DESKTOP_BUILD_TEST_FAILED: Spec missing $required" }
}
foreach ($required in @('pywebview==6.2.1', 'pyinstaller==6.22.2', 'redpath-desktop = "redpath.desktop:main"')) {
    if (-not $project.Contains($required)) { throw "DESKTOP_BUILD_TEST_FAILED: Project missing $required" }
}
$missingPython = Join-Path $projectRoot 'no-such-desktop-python.exe'
$result = & powershell -NoProfile -ExecutionPolicy Bypass -File $buildPath -Python $missingPython 2>&1
if ($LASTEXITCODE -ne 2 -or ($result | Out-String) -notmatch 'DESKTOP_BUILD_PREREQUISITE') {
    throw 'DESKTOP_BUILD_TEST_FAILED: Missing build tools need a stable prerequisite error and exit code 2.'
}
Write-Host 'Desktop build static checks passed (no tools installed or build launched).'
