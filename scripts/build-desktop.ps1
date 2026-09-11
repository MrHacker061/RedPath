[CmdletBinding()]
param([string]$Python = 'python')

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$prerequisite = 'DESKTOP_BUILD_PREREQUISITE: Install the pinned build dependencies with: python -m pip install ".[desktop]"'
if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    Write-Host $prerequisite
    exit 2
}
Push-Location $projectRoot
$previousHashSeed = $env:PYTHONHASHSEED
$previousEpoch = $env:SOURCE_DATE_EPOCH
try {
    & $Python -c "import importlib.util as u; import importlib.metadata as m; import sys; sys.exit(0 if u.find_spec('PyInstaller') and u.find_spec('webview') and m.version('pyinstaller') == '6.22.2' and m.version('pywebview') == '6.2.1' else 1)"
    if ($LASTEXITCODE -ne 0) {
        Write-Host $prerequisite
        exit 2
    }
    & $Python -c "import sys, platform; sys.exit(0 if sys.platform == 'win32' and sys.getwindowsversion().build >= 22000 and platform.machine().lower() in ('amd64', 'x86_64') and sys.maxsize > 2**32 else 1)"
    if ($LASTEXITCODE -ne 0) { throw 'DESKTOP_BUILD_PLATFORM: Build on Windows 11 x64 with 64-bit Python.' }
    $env:PYTHONHASHSEED = '0'
    $env:SOURCE_DATE_EPOCH = '1789084800'
    & $Python -m PyInstaller --noconfirm --clean --distpath (Join-Path $projectRoot 'dist') --workpath (Join-Path $projectRoot 'build/desktop') (Join-Path $projectRoot 'packaging/redpath.spec')
    if ($LASTEXITCODE -ne 0) { throw 'DESKTOP_BUILD_FAILED: PyInstaller failed; review the build output.' }
    $artifact = Join-Path $projectRoot 'dist/RedPath/RedPath.exe'
    if (-not (Test-Path -LiteralPath $artifact -PathType Leaf)) { throw 'DESKTOP_BUILD_FAILED: RedPath.exe was not produced.' }
    Write-Host "Desktop executable: $artifact"
    Get-FileHash -LiteralPath $artifact -Algorithm SHA256
}
finally {
    $env:PYTHONHASHSEED = $previousHashSeed
    $env:SOURCE_DATE_EPOCH = $previousEpoch
    Pop-Location
}
