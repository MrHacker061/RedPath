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

function Get-InstallerSections([string]$source) {
    $allowed = @('Setup', 'Tasks', 'Files', 'Icons', 'Run')
    $sections = @{}
    $current = $null
    foreach ($rawLine in ($source -split "`r?`n")) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith(';')) { continue }
        if ($line -match '^\[([A-Za-z]+)\]$') {
            $current = $Matches[1]
            if ($current -notin $allowed) {
                throw "INSTALLER_TEST_FAILED: Unexpected installer section [$current]."
            }
            if ($sections.ContainsKey($current)) {
                throw "INSTALLER_TEST_FAILED: Duplicate installer section [$current]."
            }
            $sections[$current] = [System.Collections.Generic.List[string]]::new()
            continue
        }
        if ($null -eq $current) {
            throw 'INSTALLER_TEST_FAILED: Installer content must be inside an allowed section.'
        }
        $sections[$current].Add($line)
    }
    foreach ($required in $allowed) {
        if (-not $sections.ContainsKey($required)) {
            throw "INSTALLER_TEST_FAILED: Missing installer section [$required]."
        }
    }
    return $sections
}

function Assert-ExactlyOneInstallerEntry([System.Collections.Generic.List[string]]$entries, [string]$expected, [string]$section) {
    if ($entries.Count -ne 1 -or $entries[0] -cne $expected) {
        throw "INSTALLER_TEST_FAILED: [$section] must contain only its approved entry."
    }
}

function Assert-InstallerDefinition([string]$source) {
    $sections = Get-InstallerSections $source
    foreach ($required in @(
        'PrivilegesRequired=lowest', 'ArchitecturesAllowed=x64os',
        'ArchitecturesInstallIn64BitMode=x64os', 'MinVersion=10.0.22000',
        'DefaultDirName={localappdata}\Programs\RedPath', 'DisableDirPage=yes',
        'OutputBaseFilename=RedPath-Setup-0.1.0-x64'
    )) {
        if ($sections.Setup -notcontains $required) {
            throw "INSTALLER_TEST_FAILED: Missing required [Setup] value $required."
        }
    }
    Assert-ExactlyOneInstallerEntry $sections.Tasks 'Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked' 'Tasks'
    Assert-ExactlyOneInstallerEntry $sections.Files 'Source: "..\dist\RedPath\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs touch' 'Files'
    if ($sections.Icons.Count -ne 2 -or $sections.Icons[0] -cne 'Name: "{userprograms}\RedPath"; Filename: "{app}\RedPath.exe"' -or $sections.Icons[1] -cne 'Name: "{userdesktop}\RedPath"; Filename: "{app}\RedPath.exe"; Tasks: desktopicon') {
        throw 'INSTALLER_TEST_FAILED: [Icons] must create only approved Start menu and optional desktop shortcuts.'
    }
    Assert-ExactlyOneInstallerEntry $sections.Run 'Filename: "{app}\RedPath.exe"; Description: "Launch RedPath and open first-run setup"; Flags: nowait postinstall skipifsilent' 'Run'
    if ($source -match '(?im)\bunins\w*(?:delete|uninstall)\w*\b') {
        throw 'INSTALLER_TEST_FAILED: Installer must not use uninstall deletion flags.'
    }
    foreach ($rawLine in ($source -split "`r?`n")) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith(';')) { continue }
        $referencesPreservedData = $line -match '(?i)(?:\{localappdata\}|%localappdata%|localappdata).{0,120}\bredpath\b|\b(?:ollama|redpath-kali)\b'
        $lifecycleOperation = $line -match '(?i)\b(?:delete|remove|unins\w*|unregister|deltree|rmdir)\b'
        if ($referencesPreservedData -and $lifecycleOperation) {
            throw 'INSTALLER_TEST_FAILED: Installer must not delete preserved application data or environments.'
        }
    }
    if ($source -match '(?im)VirtualBox') {
        throw 'INSTALLER_TEST_FAILED: Installer must not mention VirtualBox.'
    }
}

function Assert-InstallerDefinitionRejected([string]$source, [string]$name) {
    try {
        Assert-InstallerDefinition $source
    }
    catch {
        return
    }
    throw "INSTALLER_TEST_FAILED: $name was accepted."
}

Assert-InstallerDefinition $installer
Assert-InstallerDefinition "$installer`r`n; Documentation can say delete %LOCALAPPDATA%\RedPath only outside the uninstaller."
Assert-InstallerDefinitionRejected "$installer`r`n[Dirs]`r`nName: `"{localappdata}\RedPath`"" 'unapproved [Dirs] section'
Assert-InstallerDefinitionRejected ($installer -replace 'DestDir: "\{app\}"', 'DestDir: "{localappdata}\RedPath"') 'unexpected [Files] destination'
Assert-InstallerDefinitionRejected ($installer -replace 'Flags: unchecked', 'Flags: unchecked uninsalwaysuninstall') 'uninstall deletion flag'
Assert-InstallerDefinitionRejected "$installer`r`n[UninstallDelete]`r`nType: files; Name: `"{localappdata}\RedPath`"" 'uninstall deletion section'
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
