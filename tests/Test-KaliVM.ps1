[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$vmRoot = Join-Path $projectRoot "vm"
$failures = [System.Collections.Generic.List[string]]::new()

function Test-Condition {
    param(
        [Parameter(Mandatory = $true)][bool]$Condition,
        [Parameter(Mandatory = $true)][string]$Name
    )
    if ($Condition) {
        Write-Host "[PASS] $Name" -ForegroundColor Green
    }
    else {
        Write-Host "[FAIL] $Name" -ForegroundColor Red
        $failures.Add($Name)
    }
}

$scriptPath = Join-Path $vmRoot "KaliVM.ps1"
$tokens = $null
$parseErrors = $null
$scriptAst = [System.Management.Automation.Language.Parser]::ParseFile(
    $scriptPath,
    [ref]$tokens,
    [ref]$parseErrors
)
Test-Condition -Condition ($parseErrors.Count -eq 0) -Name "KaliVM.ps1 has no PowerShell parse errors"
if ($parseErrors.Count -gt 0) {
    $parseErrors | ForEach-Object { Write-Host "       $($_.Message)" -ForegroundColor Red }
}

if ($parseErrors.Count -eq 0) {
    $stateFunction = $scriptAst.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq "ConvertFrom-VagrantStateOutput"
    }, $true)
    $boxFunction = $scriptAst.Find({
        param($node)
        $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and
            $node.Name -eq "ConvertFrom-VagrantBoxListOutput"
    }, $true)

    Test-Condition -Condition ($null -ne $stateFunction) -Name "VM state parser function is present"
    Test-Condition -Condition ($null -ne $boxFunction) -Name "Vagrant box-list parser function is present"

    if ($null -ne $stateFunction) {
        $stateParser = $stateFunction.Body.GetScriptBlock()
        $validState = & $stateParser -OutputText "1,other,state,poweroff`n2,default,state,running"
        Test-Condition -Condition ($validState -eq "running") -Name "VM state parser selects exactly the default machine"

        $missingStateRejected = $false
        try { $null = & $stateParser -OutputText "1,other,state,running" }
        catch { $missingStateRejected = $_.Exception.Message -match "expected one state record" }
        Test-Condition -Condition $missingStateRejected -Name "VM state parser rejects a missing default state"

        $duplicateStateRejected = $false
        try { $null = & $stateParser -OutputText "1,default,state,running`n2,default,state,poweroff" }
        catch { $duplicateStateRejected = $_.Exception.Message -match "found 2" }
        Test-Condition -Condition $duplicateStateRejected -Name "VM state parser rejects duplicate default states"

        $unknownStateRejected = $false
        try { $null = & $stateParser -OutputText "1,default,state,potato" }
        catch { $unknownStateRejected = $_.Exception.Message -match "unrecognized VM state" }
        Test-Condition -Condition $unknownStateRejected -Name "VM state parser rejects unknown provider states"
    }

    if ($null -ne $boxFunction) {
        $boxParser = $boxFunction.Body.GetScriptBlock()
        $boxOutput = "1,,box-name,kalilinux/rolling`n2,,box-provider,virtualbox`n3,,box-version,2026.2.0`n4,,box-architecture,amd64"
        $parsedBoxes = @(& $boxParser -OutputText $boxOutput)
        $boxParsed = $parsedBoxes.Count -eq 1 -and
            $parsedBoxes[0].Name -eq "kalilinux/rolling" -and
            $parsedBoxes[0].Provider -eq "virtualbox" -and
            $parsedBoxes[0].Version -eq "2026.2.0" -and
            $parsedBoxes[0].Architecture -eq "amd64"
        Test-Condition -Condition $boxParsed -Name "Vagrant box-list parser associates name, provider, version, and architecture"
    }
}

$settingsPath = Join-Path $vmRoot "kali-vm.json"
$settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
Test-Condition -Condition ($settings.memoryMB -ge 2048) -Name "VM memory is at least 2048 MB"
Test-Condition -Condition ($settings.cpus -ge 1) -Name "VM has at least one CPU"
Test-Condition -Condition ($settings.box.name -eq "kalilinux/rolling") -Name "Default source is Kali's official catalog box"
Test-Condition -Condition ($settings.box.version -match "^\d{4}\.\d+\.\d+$") -Name "Kali box version is pinned"
Test-Condition -Condition ($settings.box.recordedCatalogSha256 -match "^[0-9a-f]{64}$") -Name "Box provenance records the catalog SHA-256"

$vagrantfile = Get-Content -LiteralPath (Join-Path $vmRoot "Vagrantfile") -Raw
Test-Condition -Condition ($vagrantfile -match 'vb\.gui\s*=\s*false') -Name "VirtualBox GUI is explicitly disabled"
Test-Condition -Condition ($vagrantfile -match 'host_ip:\s*"127\.0\.0\.1"') -Name "SSH forwarding is bound to localhost"
Test-Condition -Condition ($vagrantfile -match 'auto_correct:\s*true') -Name "SSH port collisions are auto-corrected"
Test-Condition -Condition ($vagrantfile -match 'synced_folder.*disabled:\s*true') -Name "Host folder sharing is disabled"
Test-Condition -Condition ($vagrantfile -match 'box_check_update\s*=\s*false') -Name "Automatic rolling-box updates are disabled"
Test-Condition -Condition ($vagrantfile -match 'box_architecture\s*=\s*"amd64"') -Name "Kali box architecture is pinned to amd64"
Test-Condition -Condition ($vagrantfile -match 'box_download_checksum_type\s*=\s*"sha256"') -Name "Direct-source fallback requires SHA-256"
Test-Condition -Condition ($vagrantfile -match 'effective_box_name.*direct_sha256') -Name "Direct-source cache identity is derived from its checksum"

$provisionScript = Get-Content -LiteralPath (Join-Path $vmRoot "scripts\provision.sh") -Raw
Test-Condition -Condition ($provisionScript -match 'PasswordAuthentication no') -Name "Password SSH login is disabled during provisioning"
Test-Condition -Condition ($provisionScript -match 'PermitRootLogin no') -Name "Root SSH login is disabled during provisioning"
Test-Condition -Condition ($provisionScript -match 'AllowAgentForwarding no') -Name "SSH agent forwarding is disabled during provisioning"
Test-Condition -Condition ($provisionScript -match '00-headless-kali\.conf') -Name "SSH hardening drop-in loads before less restrictive defaults"
Test-Condition -Condition ($provisionScript -match 'sshd -t') -Name "SSH configuration is validated before reload"

$helpOutput = @(& pwsh.exe -NoLogo -NoProfile -File $scriptPath help 2>&1)
$helpExitCode = $LASTEXITCODE
Test-Condition -Condition ($helpExitCode -eq 0) -Name "Help command exits successfully"
Test-Condition -Condition (($helpOutput -join "`n") -match "Headless Kali Terminal") -Name "Help command identifies the program"
Test-Condition -Condition (($helpOutput -join "`n") -match "repair") -Name "Help exposes an interrupted-provision repair path"
Test-Condition -Condition (($helpOutput -join "`n") -match "OutputPath") -Name "Help exposes encoding-safe SSH config export"
Test-Condition -Condition (($helpOutput -join "`n") -match "GuestCommandFile") -Name "Help exposes quote-safe guest script execution"

$managerScript = Get-Content -LiteralPath $scriptPath -Raw
Test-Condition -Condition ($managerScript -match 'sshd -T') -Name "Runtime health check verifies effective SSH hardening"
Test-Condition -Condition ($managerScript -match 'allowagentforwarding no') -Name "Runtime health check verifies agent forwarding remains disabled"
Test-Condition -Condition ($managerScript -match 'ToBase64String') -Name "Guest scripts use quote-stable base64 transport"
Test-Condition -Condition ($managerScript -match 'Could not determine the VM state safely') -Name "Lifecycle commands fail closed when VM state cannot be parsed"
Test-Condition -Condition ($managerScript -match 'Ensure-RequiredBoxCached') -Name "Rebuild stages the verified base box before deletion"
Test-Condition -Condition ($managerScript -match '\$box\.Architecture -ne "amd64"') -Name "Rebuild accepts only the pinned amd64 cache architecture"
Test-Condition -Condition ($managerScript -match 'create/rebuild cannot continue safely') -Name "Creation fails closed when the VirtualBox disk folder is unknown"
Test-Condition -Condition ($managerScript -match 'SSH config output must be a file path, not a directory') -Name "SSH config export rejects directory targets"

if ($failures.Count -gt 0) {
    Write-Host ""
    Write-Host "$($failures.Count) test(s) failed." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "All static and launcher tests passed." -ForegroundColor Green
exit 0
