[CmdletBinding()]
param()
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$installerPath = Join-Path $projectRoot 'packaging/RedPath.iss'
$buildPath = Join-Path $projectRoot 'scripts/build-installer.ps1'
foreach ($path in @($installerPath, $buildPath)) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "INSTALLER_TEST_FAILED: Missing $path" }
}
$installer = Get-Content -LiteralPath $installerPath -Raw
$build = Get-Content -LiteralPath $buildPath -Raw
$tokens = $null
$parseErrors = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile($buildPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw 'INSTALLER_TEST_FAILED: PowerShell parse errors.' }
foreach ($required in @(
    'PrivilegesRequired=lowest', 'ArchitecturesAllowed=x64os',
    'ArchitecturesInstallIn64BitMode=x64os', 'MinVersion=10.0.22000',
    'DefaultDirName={localappdata}\Programs\RedPath', 'DisableDirPage=yes',
    'OutputBaseFilename=RedPath-Setup-0.1.0-x64',
    'Name: "{userprograms}\RedPath"; Filename: "{app}\RedPath.exe"',
    'Name: "{userdesktop}\RedPath"', 'Flags: unchecked',
    'Flags: nowait postinstall skipifsilent', 'Source: "..\dist\RedPath\*"'
)) {
    if (-not $installer.Contains($required)) { throw "INSTALLER_TEST_FAILED: Missing $required" }
}
# No programmable or destructive hooks: only installed payload and shortcuts are removed.
if ($installer -match '(?im)VirtualBox|unregister|\[(?:UninstallDelete|InstallDelete|UninstallRun|Code|Registry)\]|DelTree|DeleteFile|powershell|cmd\.exe|https?://') {
    throw 'INSTALLER_TEST_FAILED: Installer contains a download or unsafe hook.'
}
$run = ($installer -split '(?im)^\[Run\]\s*$')[1].Trim()
if ($run -notmatch '^Filename: "\{app\}\\RedPath\.exe"; Description: "[^"]+"; Flags: nowait postinstall skipifsilent$') {
    throw 'INSTALLER_TEST_FAILED: Only an optional RedPath first-run launch is allowed.'
}
foreach ($required in @('INSTALLER_BUILD_PREREQUISITE', 'INSTALLER_BUILD_INPUT_MISSING', 'INSTALLER_BUILD_FAILED', 'RedPath-Setup-0.1.0-x64.exe', 'Get-FileHash', 'SOURCE_DATE_EPOCH')) {
    if (-not $build.Contains($required)) { throw "INSTALLER_TEST_FAILED: Build missing $required" }
}
if ($build -match '(?im)^\s*(?:&.*)?(?:pip|winget|choco)\s+install|Invoke-WebRequest|Start-Process|Remove-Item') {
    throw 'INSTALLER_TEST_FAILED: Build must not install, download, launch, or delete.'
}
$missingCompiler = Join-Path $projectRoot 'no-such-inno-compiler.exe'
$result = & powershell -NoProfile -ExecutionPolicy Bypass -File $buildPath -Compiler $missingCompiler 2>&1
if ($LASTEXITCODE -ne 2 -or ($result | Out-String) -notmatch 'INSTALLER_BUILD_PREREQUISITE') {
    throw 'INSTALLER_TEST_FAILED: Missing compiler must produce stable exit code 2.'
}
Write-Host 'Installer policy checks passed (no installation or compilation performed).'
