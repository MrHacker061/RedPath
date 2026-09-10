[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(Position = 0)]
    [ValidateSet(
        "help", "doctor", "install", "validate", "create", "repair", "start",
        "terminal", "shell", "run", "stop", "status", "ssh-config",
        "health", "snapshot", "snapshots", "restore", "destroy", "rebuild"
    )]
    [string]$Command = "help",

    [string]$GuestCommand,
    [string]$GuestCommandFile,
    [string]$SnapshotName = "clean",
    [string]$OutputPath,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$script:ProjectRoot = $PSScriptRoot
$script:SettingsPath = Join-Path $script:ProjectRoot "kali-vm.json"
$script:StateRoot = Join-Path $env:LOCALAPPDATA "HeadlessKaliTerminal\state"
$script:VagrantPath = $null
$script:ExitCode = 0
$script:MinimumVagrantVersion = [version]"2.4.9"
$script:MinimumFreeDiskBytes = 20GB

function Write-Info {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "[INFO] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "[ OK ] $Message" -ForegroundColor Green
}

function Write-WarningMessage {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

function Write-Failure {
    param([Parameter(Mandatory = $true)][string]$Message)
    Write-Host "[FAIL] $Message" -ForegroundColor Red
}

function Show-Help {
    $helpText = @"
Headless Kali Terminal

Creates and manages Kali Linux as a headless VirtualBox VM. The terminal
connection is local-only SSH using a generated key; no VM window is needed.

FIRST RUN
  KaliVM.cmd install
  KaliVM.cmd doctor
  KaliVM.cmd create
  KaliVM.cmd terminal

COMMANDS
  help                         Show this help.
  doctor                       Check this PC without changing it.
  install                      Install missing VirtualBox/Vagrant with winget.
  validate                     Validate the Vagrantfile and settings.
  create                       Download, create, start, and verify the VM.
  repair                       Re-run SSH hardening on an existing VM.
  start                        Start an existing VM headlessly.
  terminal (or shell)          Start if needed and open the Kali terminal.
  run -GuestCommand "COMMAND"  Run one command inside Kali.
  run -GuestCommandFile PATH   Run a local shell-command file inside Kali.
  stop [-Force]                Shut down through Kali; -Force pulls VM power.
  status                       Show VM state and local SSH endpoint.
  ssh-config [-OutputPath PATH] [-Force]
                               Print config, or safely write a UTF-8 config file.
  health                       Verify Kali identity, architecture, and SSH.
  snapshot -SnapshotName NAME  Save a VirtualBox snapshot through Vagrant.
  snapshots                    List saved snapshots.
  restore -SnapshotName NAME -Force
                               Revert guest disk state to a snapshot.
  destroy -Force               Delete this VM (keeps the cached base box).
  rebuild -Force               Delete and recreate this VM from the pinned box.

EXAMPLES
  KaliVM.cmd terminal
  KaliVM.cmd run -GuestCommand "uname -a"
  KaliVM.cmd snapshot -SnapshotName before-lab
  KaliVM.cmd ssh-config -OutputPath .\kali-ssh-config
  ssh -F kali-ssh-config kali-headless

The first create downloads an official Kali box of roughly 5 GB. VM settings
are in kali-vm.json. Guest-only files are deleted by destroy/rebuild unless you
copy them out or take an appropriate backup first.
"@
    Write-Host $helpText
}

function Resolve-Executable {
    param(
        [Parameter(Mandatory = $true)][string[]]$Names,
        [string[]]$CandidatePaths = @()
    )

    foreach ($name in $Names) {
        $commandInfo = Get-Command $name -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($null -ne $commandInfo -and -not [string]::IsNullOrWhiteSpace($commandInfo.Source)) {
            return $commandInfo.Source
        }
    }

    foreach ($candidate in $CandidatePaths) {
        if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            return $candidate
        }
    }

    return $null
}

function Resolve-VagrantPath {
    if ($null -ne $script:VagrantPath -and (Test-Path -LiteralPath $script:VagrantPath -PathType Leaf)) {
        return $script:VagrantPath
    }

    $candidates = @(
        "C:\Program Files\Vagrant\bin\vagrant.exe",
        "C:\HashiCorp\Vagrant\bin\vagrant.exe",
        "C:\Program Files\HashiCorp\Vagrant\bin\vagrant.exe",
        (Join-Path $env:LOCALAPPDATA "Programs\HashiCorp\Vagrant\bin\vagrant.exe")
    )
    $script:VagrantPath = Resolve-Executable -Names @("vagrant.exe", "vagrant") -CandidatePaths $candidates
    return $script:VagrantPath
}

function Resolve-VBoxManagePath {
    $candidates = @(
        "C:\Program Files\Oracle\VirtualBox\VBoxManage.exe",
        "C:\Program Files (x86)\Oracle\VirtualBox\VBoxManage.exe"
    )
    return Resolve-Executable -Names @("VBoxManage.exe", "VBoxManage") -CandidatePaths $candidates
}

function Resolve-WingetPath {
    return Resolve-Executable -Names @("winget.exe", "winget")
}

function Resolve-SshPath {
    $candidates = @("C:\Windows\System32\OpenSSH\ssh.exe")
    return Resolve-Executable -Names @("ssh.exe", "ssh") -CandidatePaths $candidates
}

function ConvertTo-Version {
    param([Parameter(Mandatory = $true)][string]$Text)
    $match = [regex]::Match($Text, "(?<version>\d+\.\d+\.\d+)")
    if (-not $match.Success) {
        return $null
    }
    return [version]$match.Groups["version"].Value
}

function Invoke-ExternalCapture {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$Arguments = @()
    )

    $oldErrorActionPreference = $ErrorActionPreference
    try {
        # Windows PowerShell 5.1 turns native stderr into PowerShell errors.
        # Continue lets us separate those records without making warnings fatal.
        $ErrorActionPreference = "Continue"
        $mergedOutput = @(& $Executable @Arguments 2>&1)
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $oldErrorActionPreference
    }
    $stdout = @($mergedOutput | Where-Object { $_ -isnot [System.Management.Automation.ErrorRecord] } | ForEach-Object { $_.ToString() })
    $stderr = @($mergedOutput | Where-Object { $_ -is [System.Management.Automation.ErrorRecord] } | ForEach-Object { $_.ToString() })
    $stdoutText = ($stdout -join [Environment]::NewLine).TrimEnd()
    $stderrText = ($stderr -join [Environment]::NewLine).TrimEnd()
    if ($exitCode -ne 0) {
        $diagnosticText = @($stdoutText, $stderrText) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
        throw "Command failed with exit code ${exitCode}: $Executable $($Arguments -join ' ')`n$($diagnosticText -join [Environment]::NewLine)"
    }
    if (-not [string]::IsNullOrWhiteSpace($stderrText)) {
        Write-Verbose "Successful command wrote to stderr: $stderrText"
    }
    return $stdoutText
}

function Enter-VagrantMutationLock {
    $mutex = [System.Threading.Mutex]::new($false, "Local\HeadlessKaliTerminal-VagrantMutation")
    $acquired = $false
    try {
        $acquired = $mutex.WaitOne(0)
    }
    catch [System.Threading.AbandonedMutexException] {
        $acquired = $true
    }
    if (-not $acquired) {
        $mutex.Dispose()
        throw "Another Headless Kali lifecycle command is already running. Let it finish, then retry."
    }
    return $mutex
}

function Exit-VagrantMutationLock {
    param([Parameter(Mandatory = $true)][System.Threading.Mutex]$Mutex)
    $Mutex.ReleaseMutex()
    $Mutex.Dispose()
}

function Invoke-Vagrant {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [switch]$Capture
    )

    $vagrant = Resolve-VagrantPath
    if ($null -eq $vagrant) {
        throw "Vagrant is not installed. Run 'KaliVM.cmd install', then retry."
    }

    if (-not (Test-Path -LiteralPath $script:StateRoot -PathType Container)) {
        $null = New-Item -ItemType Directory -Path $script:StateRoot -Force
    }

    $oldProvider = $env:VAGRANT_DEFAULT_PROVIDER
    $oldDotfilePath = $env:VAGRANT_DOTFILE_PATH
    $oldWorkingDirectory = $env:VAGRANT_CWD
    $oldNoColor = $env:VAGRANT_NO_COLOR
    $oldCheckpointDisable = $env:VAGRANT_CHECKPOINT_DISABLE
    $env:VAGRANT_DEFAULT_PROVIDER = "virtualbox"
    $env:VAGRANT_DOTFILE_PATH = $script:StateRoot
    $env:VAGRANT_CWD = $script:ProjectRoot
    $env:VAGRANT_NO_COLOR = "1"
    $env:VAGRANT_CHECKPOINT_DISABLE = "1"

    $mutationCommands = @("up", "halt", "destroy", "snapshot", "provision", "reload", "suspend", "resume")
    $requiresMutationLock = $Arguments.Count -gt 0 -and $mutationCommands -contains $Arguments[0].ToLowerInvariant()
    if ($Arguments.Count -gt 1 -and $Arguments[0].ToLowerInvariant() -eq "box") {
        $requiresMutationLock = @("add", "remove", "update", "prune", "repackage") -contains $Arguments[1].ToLowerInvariant()
    }
    $mutationLock = $null
    if ($requiresMutationLock) {
        $mutationLock = Enter-VagrantMutationLock
    }

    Push-Location $script:ProjectRoot
    try {
        if ($Capture) {
            return Invoke-ExternalCapture -Executable $vagrant -Arguments $Arguments
        }

        & $vagrant @Arguments
        if ($LASTEXITCODE -ne 0) {
            throw "Vagrant failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
        if ($null -ne $mutationLock) {
            Exit-VagrantMutationLock -Mutex $mutationLock
        }
        if ($null -eq $oldProvider) {
            Remove-Item Env:VAGRANT_DEFAULT_PROVIDER -ErrorAction SilentlyContinue
        }
        else {
            $env:VAGRANT_DEFAULT_PROVIDER = $oldProvider
        }
        if ($null -eq $oldDotfilePath) {
            Remove-Item Env:VAGRANT_DOTFILE_PATH -ErrorAction SilentlyContinue
        }
        else {
            $env:VAGRANT_DOTFILE_PATH = $oldDotfilePath
        }
        if ($null -eq $oldWorkingDirectory) {
            Remove-Item Env:VAGRANT_CWD -ErrorAction SilentlyContinue
        }
        else {
            $env:VAGRANT_CWD = $oldWorkingDirectory
        }
        if ($null -eq $oldNoColor) {
            Remove-Item Env:VAGRANT_NO_COLOR -ErrorAction SilentlyContinue
        }
        else {
            $env:VAGRANT_NO_COLOR = $oldNoColor
        }
        if ($null -eq $oldCheckpointDisable) {
            Remove-Item Env:VAGRANT_CHECKPOINT_DISABLE -ErrorAction SilentlyContinue
        }
        else {
            $env:VAGRANT_CHECKPOINT_DISABLE = $oldCheckpointDisable
        }
    }
}

function Get-RequiredProperty {
    param(
        [Parameter(Mandatory = $true)][object]$Object,
        [Parameter(Mandatory = $true)][string]$Name
    )

    if ($null -eq $Object -or -not ($Object.PSObject.Properties.Name -contains $Name)) {
        throw "kali-vm.json is missing '$Name'."
    }
    return $Object.$Name
}

function Get-Settings {
    if (-not (Test-Path -LiteralPath $script:SettingsPath -PathType Leaf)) {
        throw "Missing settings file: $($script:SettingsPath)"
    }

    try {
        $settings = Get-Content -LiteralPath $script:SettingsPath -Raw | ConvertFrom-Json
    }
    catch {
        throw "kali-vm.json is not valid JSON: $($_.Exception.Message)"
    }

    $vmName = [string](Get-RequiredProperty -Object $settings -Name "vmName")
    $hostname = [string](Get-RequiredProperty -Object $settings -Name "hostname")
    $memoryMB = [int](Get-RequiredProperty -Object $settings -Name "memoryMB")
    $cpus = [int](Get-RequiredProperty -Object $settings -Name "cpus")
    $box = Get-RequiredProperty -Object $settings -Name "box"
    $boxName = [string](Get-RequiredProperty -Object $box -Name "name")
    $boxVersion = [string](Get-RequiredProperty -Object $box -Name "version")
    $recordedCatalogSha256 = [string](Get-RequiredProperty -Object $box -Name "recordedCatalogSha256")
    $directUrl = [string](Get-RequiredProperty -Object $box -Name "directUrl")
    $directSha256 = [string](Get-RequiredProperty -Object $box -Name "directSha256")

    if ([string]::IsNullOrWhiteSpace($vmName)) {
        throw "vmName cannot be empty."
    }
    if ($hostname -notmatch "^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$") {
        throw "hostname is not a valid Linux hostname."
    }
    if ($memoryMB -lt 2048 -or $memoryMB -gt 65536) {
        throw "memoryMB must be between 2048 and 65536."
    }
    if ($cpus -lt 1 -or $cpus -gt 64) {
        throw "cpus must be between 1 and 64."
    }
    if ([string]::IsNullOrWhiteSpace($boxName)) {
        throw "box.name cannot be empty."
    }
    if (-not [string]::IsNullOrWhiteSpace($recordedCatalogSha256) -and $recordedCatalogSha256 -notmatch "^[0-9a-fA-F]{64}$") {
        throw "box.recordedCatalogSha256 must be blank or a 64-character SHA-256."
    }
    if (-not [string]::IsNullOrWhiteSpace($directUrl)) {
        $parsedUri = $null
        if (-not [uri]::TryCreate($directUrl, [UriKind]::Absolute, [ref]$parsedUri) -or $parsedUri.Scheme -ne "https") {
            throw "box.directUrl must be an absolute HTTPS URL."
        }
        if ($directSha256 -notmatch "^[0-9a-fA-F]{64}$") {
            throw "box.directSha256 must be a 64-character SHA-256 when directUrl is set."
        }
        if ($boxName -notmatch "^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$") {
            throw "When directUrl is set, box.name must be a 1-40 character label using letters, numbers, dot, underscore, or hyphen."
        }
    }

    return $settings
}

function Assert-Prerequisites {
    $vboxManage = Resolve-VBoxManagePath
    if ($null -eq $vboxManage) {
        throw "VirtualBox is not installed. Run 'KaliVM.cmd install', then reboot if its installer asks."
    }

    $vagrant = Resolve-VagrantPath
    if ($null -eq $vagrant) {
        throw "Vagrant is not installed. Run 'KaliVM.cmd install', then retry."
    }

    $vagrantOutput = Invoke-ExternalCapture -Executable $vagrant -Arguments @("--version")
    $vagrantVersion = ConvertTo-Version -Text $vagrantOutput
    if ($null -eq $vagrantVersion -or $vagrantVersion -lt $script:MinimumVagrantVersion) {
        throw "Vagrant $($script:MinimumVagrantVersion) or newer is required for VirtualBox 7.2 support. Found: $vagrantOutput"
    }
}

function ConvertFrom-VagrantStateOutput {
    param([Parameter(Mandatory = $true)][string]$OutputText)

    $states = @()
    foreach ($line in ($OutputText -split "`r?`n")) {
        if ($line -match "^[^,]*,default,state,(?<state>[^,]+)$") {
            $states += $Matches["state"].Trim().ToLowerInvariant()
        }
    }

    if ($states.Count -ne 1) {
        throw "Could not determine the VM state safely: expected one state record for machine 'default', found $($states.Count)."
    }

    $state = $states[0]
    $knownStates = @(
        "not_created", "inaccessible", "poweroff", "saved", "teleported",
        "aborted", "aborted-saved", "running", "paused", "stuck",
        "teleporting", "livesnapshotting", "live-snapshotting", "starting",
        "stopping", "saving", "restoring", "teleportingpausedvm",
        "teleporting-paused", "teleportingin", "teleporting-in",
        "faulttolerantsyncing", "fault-tolerant-syncing",
        "deletingsnapshotonline", "deleting-snapshot-online",
        "deletingsnapshotpaused", "deleting-snapshot-paused",
        "onlinesnapshotting", "online-snapshotting", "restoringsnapshot",
        "restoring-snapshot", "deletingsnapshot", "deleting-snapshot",
        "settingup", "setting-up", "snapshotting", "gurumeditation",
        "guru-meditation"
    )
    if ($knownStates -notcontains $state) {
        throw "Vagrant reported an unrecognized VM state '$state'. No lifecycle action was taken."
    }
    return $state
}

function Get-VagrantState {
    $output = Invoke-Vagrant -Arguments @("status", "--machine-readable") -Capture
    return ConvertFrom-VagrantStateOutput -OutputText $output
}

function Assert-ExistingVM {
    $state = Get-VagrantState
    if ($state -eq "not_created") {
        throw "The Kali VM has not been created. Run 'KaliVM.cmd create' first."
    }
    return $state
}

function Assert-RunningVM {
    $state = Assert-ExistingVM
    if ($state -ne "running") {
        throw "The Kali VM is '$state'. Run 'KaliVM.cmd start' first."
    }
}

function Assert-StateCanStart {
    param([Parameter(Mandatory = $true)][string]$State)

    if (@("poweroff", "saved", "aborted", "aborted-saved") -notcontains $State) {
        throw "The Kali VM is in state '$State', so an automatic start would be unsafe. Wait and run status again, or diagnose the VM before retrying."
    }
}

function Get-CreationStorageTargets {
    param([switch]$AllowVirtualBoxFallback)

    $targets = [System.Collections.Generic.List[object]]::new()
    $vagrantHome = $env:VAGRANT_HOME
    if ([string]::IsNullOrWhiteSpace($vagrantHome)) {
        $vagrantHome = Join-Path ([Environment]::GetFolderPath("UserProfile")) ".vagrant.d"
    }
    $targets.Add([pscustomobject]@{ Purpose = "Vagrant box cache"; Path = $vagrantHome })

    try {
        $vboxManage = Resolve-VBoxManagePath
        if ($null -eq $vboxManage) {
            throw "VBoxManage is unavailable."
        }
        $systemProperties = Invoke-ExternalCapture -Executable $vboxManage -Arguments @("list", "systemproperties")
        $folderMatch = [regex]::Match($systemProperties, "(?m)^Default machine folder:\s*(?<path>.+?)\s*$")
        if (-not $folderMatch.Success) {
            throw "VirtualBox did not report its default machine folder."
        }
        $targets.Add([pscustomobject]@{ Purpose = "VirtualBox VM disks"; Path = $folderMatch.Groups["path"].Value })
    }
    catch {
        if (-not $AllowVirtualBoxFallback) {
            throw "Could not locate the real VirtualBox VM folder, so create/rebuild cannot continue safely: $($_.Exception.Message)"
        }
        Write-WarningMessage "Could not locate the VirtualBox VM folder, so the project drive will be checked instead: $($_.Exception.Message)"
        $targets.Add([pscustomobject]@{ Purpose = "VirtualBox fallback"; Path = $script:ProjectRoot })
    }

    return $targets
}

function Get-CreationDriveStatus {
    param([switch]$AllowVirtualBoxFallback)

    $drives = @{}
    foreach ($target in (Get-CreationStorageTargets -AllowVirtualBoxFallback:$AllowVirtualBoxFallback)) {
        $fullPath = [System.IO.Path]::GetFullPath([string]$target.Path)
        $root = [System.IO.Path]::GetPathRoot($fullPath)
        if ([string]::IsNullOrWhiteSpace($root)) {
            throw "Could not determine the storage drive for $($target.Purpose): $fullPath"
        }
        $key = $root.TrimEnd("\").ToLowerInvariant()
        if (-not $drives.ContainsKey($key)) {
            $drives[$key] = [pscustomobject]@{
                Root = $root
                Purposes = [System.Collections.Generic.List[string]]::new()
            }
        }
        $drives[$key].Purposes.Add([string]$target.Purpose)
    }

    $results = [System.Collections.Generic.List[object]]::new()
    foreach ($entry in $drives.Values) {
        try {
            $driveInfo = [System.IO.DriveInfo]::new([string]$entry.Root)
            $freeBytes = $driveInfo.AvailableFreeSpace
        }
        catch {
            throw "Could not measure free space on '$($entry.Root)': $($_.Exception.Message)"
        }
        $results.Add([pscustomobject]@{
            Root = $entry.Root
            Purposes = $entry.Purposes -join " and "
            FreeBytes = $freeBytes
        })
    }
    return $results
}

function Assert-CreationDiskSpace {
    foreach ($driveStatus in (Get-CreationDriveStatus)) {
        if ($driveStatus.FreeBytes -lt $script:MinimumFreeDiskBytes) {
            $freeGB = [math]::Round($driveStatus.FreeBytes / 1GB, 1)
            throw "At least 20 GB of free disk is required on '$($driveStatus.Root)' for $($driveStatus.Purposes) before create/rebuild; only ${freeGB} GB is free."
        }
    }
}

function Invoke-Preflight {
    param([switch]$RequireCreationSpace)

    $settings = Get-Settings
    if ($RequireCreationSpace) {
        Assert-CreationDiskSpace
    }

    try {
        $os = Get-CimInstance Win32_OperatingSystem
        $freeMemoryMB = [math]::Round([double]$os.FreePhysicalMemory / 1024)
        $requestedMemoryMB = [int]$settings.memoryMB
        if ($freeMemoryMB -lt ($requestedMemoryMB + 2048)) {
            Write-WarningMessage "Only ${freeMemoryMB} MB of RAM is currently free; close large apps before giving the VM ${requestedMemoryMB} MB."
        }
    }
    catch {
        Write-WarningMessage "Could not measure free RAM: $($_.Exception.Message)"
    }
}

function Invoke-Validate {
    Assert-Prerequisites
    $null = Get-Settings
    Write-Info "Validating Vagrantfile and settings..."
    Invoke-Vagrant -Arguments @("validate")
    Write-Success "Configuration is valid."
}

function Invoke-HealthCheck {
    Assert-RunningVM
    Write-Info "Verifying that this is an active x86-64 Kali guest..."
    $healthCommand = 'set -eu; . /etc/os-release; test "$ID" = kali; test "$(uname -m)" = x86_64; systemctl is-active --quiet ssh; effective="$(sudo /usr/sbin/sshd -T)"; printf "%s\n" "$effective" | grep -qx "passwordauthentication no"; printf "%s\n" "$effective" | grep -qx "kbdinteractiveauthentication no"; printf "%s\n" "$effective" | grep -qx "permitrootlogin no"; printf "%s\n" "$effective" | grep -qx "allowagentforwarding no"; printf "Kali %s | user=%s | arch=%s | ssh=active | password-login=off\n" "${VERSION_ID:-rolling}" "$(id -un)" "$(uname -m)"'
    Invoke-VagrantGuestScript -ScriptText $healthCommand
    Write-Success "The headless Kali terminal is healthy."
}

function Invoke-VagrantUp {
    param([switch]$NoProvision)

    $arguments = @("up", "--provider", "virtualbox")
    if ($NoProvision) {
        $arguments += "--no-provision"
    }
    $arguments += "--no-destroy-on-error"

    try {
        Invoke-Vagrant -Arguments $arguments
    }
    catch {
        $upError = $_
        try {
            $afterFailureState = Get-VagrantState
            if ($afterFailureState -eq "running") {
                Write-WarningMessage "The VM is running, but setup did not finish. Its disk was preserved; run 'KaliVM.cmd repair'."
            }
            else {
                Write-WarningMessage "Setup stopped with VM state '$afterFailureState'. Its disk was preserved for a safe retry or diagnosis."
            }
        }
        catch {
            Write-WarningMessage "Setup failed and its final VM state could not be read. No automatic destroy was requested."
        }
        throw $upError
    }
}

function ConvertTo-GuestCommandTransport {
    param([Parameter(Mandatory = $true)][string]$ScriptText)

    # Windows PowerShell 5.1 can split native arguments containing nested
    # quotes. Base64 keeps the vagrant.exe argument ASCII-only and stable.
    $normalizedScript = $ScriptText.Replace("`r`n", "`n").Replace("`r", "`n")
    $scriptBytes = [System.Text.Encoding]::UTF8.GetBytes($normalizedScript)
    $encodedScript = [Convert]::ToBase64String($scriptBytes)
    return "printf '%s' '$encodedScript' | base64 -d | /bin/bash -s"
}

function Invoke-VagrantGuestScript {
    param([Parameter(Mandatory = $true)][string]$ScriptText)
    $transportCommand = ConvertTo-GuestCommandTransport -ScriptText $ScriptText
    Invoke-Vagrant -Arguments @("ssh", "-c", $transportCommand)
}

function Get-EffectiveBoxName {
    param([Parameter(Mandatory = $true)]$Settings)

    $baseName = [string]$Settings.box.name
    $directUrl = [string]$Settings.box.directUrl
    if ([string]::IsNullOrWhiteSpace($directUrl)) {
        return $baseName
    }
    return "${baseName}-sha256-$(([string]$Settings.box.directSha256).ToLowerInvariant())"
}

function ConvertFrom-VagrantBoxListOutput {
    param([Parameter(Mandatory = $true)][AllowEmptyString()][string]$OutputText)

    $boxes = [System.Collections.Generic.List[object]]::new()
    $current = $null

    foreach ($line in ($OutputText -split "`r?`n")) {
        $parts = $line -split ",", 4
        if ($parts.Count -ne 4) {
            continue
        }
        $type = $parts[2]
        $value = $parts[3].Replace("%!(VAGRANT_COMMA)", ",")
        if ($type -eq "box-name") {
            if ($null -ne $current) {
                $boxes.Add($current)
            }
            $current = [pscustomobject]@{ Name = $value; Provider = ""; Version = ""; Architecture = "" }
        }
        elseif ($null -ne $current) {
            switch ($type) {
                "box-provider" { $current.Provider = $value }
                "box-version" { $current.Version = $value }
                "box-architecture" { $current.Architecture = $value }
            }
        }
    }
    if ($null -ne $current) {
        $boxes.Add($current)
    }
    return $boxes
}

function Get-InstalledVagrantBoxes {
    $output = Invoke-Vagrant -Arguments @("box", "list", "--machine-readable") -Capture
    return ConvertFrom-VagrantBoxListOutput -OutputText $output
}

function Test-RequiredBoxCached {
    param([Parameter(Mandatory = $true)]$Settings)

    $effectiveName = Get-EffectiveBoxName -Settings $Settings
    $isDirect = -not [string]::IsNullOrWhiteSpace([string]$Settings.box.directUrl)
    foreach ($box in (Get-InstalledVagrantBoxes)) {
        if ($box.Name -ne $effectiveName -or $box.Provider -ne "virtualbox") {
            continue
        }
        if ($box.Architecture -ne "amd64") {
            continue
        }
        if ($isDirect -or $box.Version -eq [string]$Settings.box.version) {
            return $true
        }
    }
    return $false
}

function Ensure-RequiredBoxCached {
    param([Parameter(Mandatory = $true)]$Settings)

    if (Test-RequiredBoxCached -Settings $Settings) {
        return
    }

    $effectiveName = Get-EffectiveBoxName -Settings $Settings
    $directUrl = [string]$Settings.box.directUrl
    if ([string]::IsNullOrWhiteSpace($directUrl)) {
        Write-Info "The pinned Kali box is not cached. Downloading and verifying it before the existing VM is deleted..."
        $arguments = @(
            "box", "add", [string]$Settings.box.name,
            "--provider", "virtualbox",
            "--architecture", "amd64",
            "--box-version", [string]$Settings.box.version
        )
    }
    else {
        Write-Info "The checksum-pinned direct box is not cached. Downloading and verifying it before the existing VM is deleted..."
        $arguments = @(
            "box", "add", $directUrl,
            "--name", $effectiveName,
            "--provider", "virtualbox",
            "--architecture", "amd64",
            "--checksum-type", "sha256",
            "--checksum", [string]$Settings.box.directSha256
        )
    }
    Invoke-Vagrant -Arguments $arguments
    if (-not (Test-RequiredBoxCached -Settings $Settings)) {
        throw "Vagrant completed the box download, but the required verified box was not found in its cache. The existing VM was not deleted."
    }
}

function Invoke-Repair {
    Assert-Prerequisites
    $operationLock = Enter-VagrantMutationLock
    try {
        $state = Assert-ExistingVM
        if ($state -ne "running") {
            Assert-StateCanStart -State $state
            Invoke-Preflight
            Write-Info "Starting the existing Kali VM without provisioning so repair can run cleanly..."
            Invoke-VagrantUp -NoProvision
        }
        Write-Info "Re-running the idempotent SSH hardening provisioner..."
        Invoke-Vagrant -Arguments @("provision")
        Invoke-HealthCheck
        Write-Success "Repair and verification completed."
    }
    finally {
        Exit-VagrantMutationLock -Mutex $operationLock
    }
}

function Invoke-Create {
    Assert-Prerequisites
    $operationLock = Enter-VagrantMutationLock
    try {
        Invoke-Validate
        $settings = Get-Settings
        $state = Get-VagrantState
        if ($state -eq "not_created") {
            Invoke-Preflight -RequireCreationSpace
            if ([string]::IsNullOrWhiteSpace([string]$settings.box.directUrl)) {
                Write-Info "Creating '$($settings.vmName)' from official Kali catalog box $($settings.box.name) $($settings.box.version)."
                Write-Info "The first run downloads roughly 5 GB; Vagrant verifies the catalog checksum."
            }
            else {
                Write-Info "Creating '$($settings.vmName)' from checksum-pinned direct box '$(Get-EffectiveBoxName -Settings $settings)' (manifest label $($settings.box.version))."
                Write-Info "Vagrant will verify box.directSha256 while downloading the configured HTTPS URL."
            }
            Invoke-VagrantUp
        }
        elseif ($state -eq "running") {
            Invoke-Preflight
            Write-Info "The Kali VM already exists and is running."
        }
        else {
            Assert-StateCanStart -State $state
            Invoke-Preflight
            Write-Info "The Kali VM already exists in state '$state'; starting it headlessly."
            Invoke-VagrantUp
        }

        Invoke-HealthCheck
        Write-Success "Ready. Open it with: KaliVM.cmd terminal"
    }
    finally {
        Exit-VagrantMutationLock -Mutex $operationLock
    }
}

function Invoke-Start {
    Assert-Prerequisites
    $operationLock = Enter-VagrantMutationLock
    try {
        $state = Assert-ExistingVM
        if ($state -eq "running") {
            Write-Info "The Kali VM is already running."
        }
        else {
            Assert-StateCanStart -State $state
            Invoke-Preflight
            Write-Info "Starting the Kali VM headlessly (current state: $state)..."
            Invoke-VagrantUp
        }
        Invoke-HealthCheck
    }
    finally {
        Exit-VagrantMutationLock -Mutex $operationLock
    }
}

function Invoke-Terminal {
    Assert-Prerequisites
    $state = Get-VagrantState
    if ($state -eq "not_created") {
        Write-Info "No Kali VM exists yet, so terminal will create it first."
        Invoke-Create
    }
    elseif ($state -ne "running") {
        Invoke-Start
    }
    else {
        Invoke-HealthCheck
    }

    Write-Host ""
    Write-Success "Connected to Kali. Type 'exit' to return to Windows; use 'KaliVM.cmd stop' when done."
    Invoke-Vagrant -Arguments @("ssh")
}

function Invoke-GuestCommand {
    if (-not [string]::IsNullOrWhiteSpace($GuestCommand) -and -not [string]::IsNullOrWhiteSpace($GuestCommandFile)) {
        throw "Use either -GuestCommand or -GuestCommandFile, not both."
    }

    $commandToRun = $GuestCommand
    if (-not [string]::IsNullOrWhiteSpace($GuestCommandFile)) {
        $resolvedCommandFile = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($GuestCommandFile)
        if (-not (Test-Path -LiteralPath $resolvedCommandFile -PathType Leaf)) {
            throw "Guest command file not found: $resolvedCommandFile"
        }
        $commandToRun = Get-Content -LiteralPath $resolvedCommandFile -Raw
    }
    if ([string]::IsNullOrWhiteSpace($commandToRun)) {
        throw 'run requires -GuestCommand or -GuestCommandFile. Example: KaliVM.cmd run -GuestCommand "uname -a"'
    }
    Assert-Prerequisites
    $state = Assert-ExistingVM
    if ($state -ne "running") {
        Invoke-Start
    }
    Invoke-VagrantGuestScript -ScriptText $commandToRun
}

function Invoke-Stop {
    Assert-Prerequisites
    $stopLock = Enter-VagrantMutationLock
    try {
        $state = Get-VagrantState
        if ($state -eq "not_created") {
            Write-Info "No Kali VM exists."
            return
        }
        if ($state -eq "poweroff") {
            Write-Info "The Kali VM is already powered off."
            return
        }
        if ($Force) {
            Write-WarningMessage "Forcing VirtualBox power off. This is equivalent to pulling a computer's power plug."
            Invoke-Vagrant -Arguments @("halt", "--force")
            $state = Get-VagrantState
            if ($state -ne "poweroff") {
                throw "The forced halt command finished, but Vagrant reports state '$state' instead of 'poweroff'."
            }
            Write-Success "The Kali VM was forcibly powered off."
            return
        }
        if ($state -ne "running") {
            throw "The Kali VM is '$state', not running. Start it before requesting a clean guest shutdown, or use stop -Force only if pulling virtual power is acceptable."
        }

        Write-Info "Requesting shutdown from inside Kali (no forced power-off fallback)..."
        try {
            Invoke-VagrantGuestScript -ScriptText "sudo systemctl poweroff"
        }
        catch {
            Write-WarningMessage "The SSH command ended while shutdown was requested; checking the actual VM state before deciding whether it stopped."
            Write-Verbose $_.Exception.Message
        }

        $shutdownTimer = [System.Diagnostics.Stopwatch]::StartNew()
        while ($shutdownTimer.Elapsed.TotalSeconds -lt 120) {
            Start-Sleep -Seconds 2
            $state = Get-VagrantState
            if ($state -eq "poweroff") {
                Write-Success "The Kali VM shut down cleanly."
                return
            }
            if ($state -ne "running" -and $state -ne "stopping") {
                throw "Shutdown did not reach the expected 'poweroff' state; Vagrant reports '$state'. No forced power-off was attempted."
            }
        }

        throw "Kali did not shut down within 120 seconds. No power was pulled. Retry, or use 'KaliVM.cmd stop -Force' only if losing unsaved guest data is acceptable."
    }
    finally {
        Exit-VagrantMutationLock -Mutex $stopLock
    }
}

function Get-SshConfig {
    Assert-Prerequisites
    $null = Assert-ExistingVM
    return Invoke-Vagrant -Arguments @("ssh-config", "--host", "kali-headless") -Capture
}

function Export-SshConfig {
    $sshConfig = Get-SshConfig
    if ([string]::IsNullOrWhiteSpace($OutputPath)) {
        Write-Output $sshConfig
        return
    }

    $resolvedOutputPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputPath)
    if (Test-Path -LiteralPath $resolvedOutputPath -PathType Container) {
        throw "SSH config output must be a file path, not a directory: $resolvedOutputPath"
    }
    $parentDirectory = Split-Path -Parent $resolvedOutputPath
    if ([string]::IsNullOrWhiteSpace($parentDirectory) -or -not (Test-Path -LiteralPath $parentDirectory -PathType Container)) {
        throw "The ssh-config output directory does not exist: $parentDirectory"
    }
    if ((Test-Path -LiteralPath $resolvedOutputPath -PathType Leaf) -and -not $Force) {
        throw "Refusing to overwrite existing SSH config: $resolvedOutputPath. Re-run with -Force only if replacement is intended."
    }

    $temporaryName = ".{0}.{1}.tmp" -f ([System.IO.Path]::GetFileName($resolvedOutputPath)), [guid]::NewGuid().ToString("N")
    $temporaryPath = Join-Path $parentDirectory $temporaryName
    try {
        $utf8WithoutBom = [System.Text.UTF8Encoding]::new($false)
        [System.IO.File]::WriteAllText($temporaryPath, $sshConfig + [Environment]::NewLine, $utf8WithoutBom)
        Move-Item -LiteralPath $temporaryPath -Destination $resolvedOutputPath -Force
    }
    finally {
        if (Test-Path -LiteralPath $temporaryPath -PathType Leaf) {
            Remove-Item -LiteralPath $temporaryPath -Force
        }
    }
    Write-Success "Wrote OpenSSH config to $resolvedOutputPath"
}

function Invoke-Status {
    Assert-Prerequisites
    $state = Get-VagrantState
    Write-Host "VM state: $state"
    if ($state -eq "running") {
        $sshConfig = Get-SshConfig
        $hostName = [regex]::Match($sshConfig, "(?m)^\s*HostName\s+(?<value>.+)$").Groups["value"].Value.Trim()
        $port = [regex]::Match($sshConfig, "(?m)^\s*Port\s+(?<value>.+)$").Groups["value"].Value.Trim()
        $user = [regex]::Match($sshConfig, "(?m)^\s*User\s+(?<value>.+)$").Groups["value"].Value.Trim()
        Write-Host "SSH:      ${user}@${hostName}:$port (localhost only)"
        Write-Host "Terminal: KaliVM.cmd terminal"
    }
}

function Assert-SnapshotName {
    if ($SnapshotName -notmatch "^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$") {
        throw "SnapshotName must be 1-64 characters using letters, numbers, dot, underscore, or hyphen."
    }
}

function Invoke-SnapshotSave {
    Assert-Prerequisites
    $operationLock = Enter-VagrantMutationLock
    try {
        $null = Assert-ExistingVM
        Assert-SnapshotName
        Invoke-Vagrant -Arguments @("snapshot", "save", $SnapshotName)
        Write-Success "Saved snapshot '$SnapshotName'."
    }
    finally {
        Exit-VagrantMutationLock -Mutex $operationLock
    }
}

function Invoke-SnapshotList {
    Assert-Prerequisites
    $null = Assert-ExistingVM
    Invoke-Vagrant -Arguments @("snapshot", "list")
}

function Invoke-SnapshotRestore {
    Assert-Prerequisites
    $operationLock = Enter-VagrantMutationLock
    try {
        $null = Assert-ExistingVM
        Assert-SnapshotName
        if (-not $Force) {
            throw "Restore discards newer guest disk changes. Re-run with -Force if that is intended."
        }
        Invoke-Vagrant -Arguments @("snapshot", "restore", $SnapshotName, "--no-provision")
        Write-Success "Restored snapshot '$SnapshotName'."
    }
    finally {
        Exit-VagrantMutationLock -Mutex $operationLock
    }
}

function Invoke-Destroy {
    Assert-Prerequisites
    $operationLock = Enter-VagrantMutationLock
    try {
        $state = Get-VagrantState
        if ($state -eq "not_created") {
            Write-Info "No Kali VM exists. Nothing was deleted."
            return
        }
        if (-not $Force) {
            throw "Destroy deletes all guest-only files. Re-run 'KaliVM.cmd destroy -Force' if that is intended."
        }
        Write-WarningMessage "Deleting the Kali VM and its guest disk. The downloaded base box remains cached."
        Invoke-Vagrant -Arguments @("destroy", "--force")
        Write-Success "The Kali VM was deleted."
    }
    finally {
        Exit-VagrantMutationLock -Mutex $operationLock
    }
}

function Invoke-Rebuild {
    Assert-Prerequisites
    $operationLock = Enter-VagrantMutationLock
    try {
        if (-not $Force) {
            throw "Rebuild deletes all guest-only files. Re-run 'KaliVM.cmd rebuild -Force' if that is intended."
        }

        # Complete every safe validation and source-readiness check first.
        Invoke-Validate
        Invoke-Preflight -RequireCreationSpace
        $settings = Get-Settings
        $state = Get-VagrantState
        if ($state -ne "not_created") {
            Ensure-RequiredBoxCached -Settings $settings
            # A just-downloaded box may have changed free space. Recheck while
            # the existing VM is still intact so a low-space result is harmless.
            Invoke-Preflight -RequireCreationSpace
            Write-WarningMessage "Deleting the current Kali VM before rebuilding it."
            Invoke-Vagrant -Arguments @("destroy", "--force")
        }
        Invoke-Create
    }
    finally {
        Exit-VagrantMutationLock -Mutex $operationLock
    }
}

function Invoke-InstallPrerequisites {
    $winget = Resolve-WingetPath
    if ($null -eq $winget) {
        throw "winget is unavailable. Install VirtualBox and Vagrant from their official sites, then run doctor."
    }

    $packages = @()
    if ($null -eq (Resolve-VBoxManagePath)) {
        $packages += [pscustomobject]@{ Name = "Oracle VirtualBox"; Id = "Oracle.VirtualBox" }
    }
    if ($null -eq (Resolve-VagrantPath)) {
        $packages += [pscustomobject]@{ Name = "HashiCorp Vagrant"; Id = "Hashicorp.Vagrant" }
    }

    if ($packages.Count -eq 0) {
        Write-Success "VirtualBox and Vagrant are already installed."
        return
    }

    Write-WarningMessage "Installers may show a Windows administrator prompt. VirtualBox can briefly reset network adapters."
    foreach ($package in $packages) {
        Write-Info "Installing $($package.Name) from the winget community repository..."
        & $winget install --id $package.Id --exact --source winget --accept-source-agreements --accept-package-agreements
        if ($LASTEXITCODE -ne 0) {
            throw "winget could not install $($package.Name) (exit code $LASTEXITCODE)."
        }
    }

    $script:VagrantPath = $null
    Write-Success "Prerequisite installation finished."
    Write-Info "If doctor cannot see a new installation, close this terminal, reopen it, and run doctor again."
}

function Write-DoctorCheck {
    param(
        [Parameter(Mandatory = $true)][ValidateSet("ok", "warn", "fail")][string]$Level,
        [Parameter(Mandatory = $true)][string]$Message
    )

    switch ($Level) {
        "ok" { Write-Success $Message }
        "warn" { Write-WarningMessage $Message }
        "fail" { Write-Failure $Message }
    }
}

function Invoke-Doctor {
    $healthy = $true
    Write-Host "Headless Kali host check"
    Write-Host ""

    if ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) {
        Write-DoctorCheck -Level ok -Message "Windows host detected."
    }
    else {
        Write-DoctorCheck -Level fail -Message "This launcher currently targets Windows."
        $healthy = $false
    }

    if ([Environment]::Is64BitOperatingSystem) {
        Write-DoctorCheck -Level ok -Message "64-bit Windows is compatible with the pinned amd64 Kali box."
    }
    else {
        Write-DoctorCheck -Level fail -Message "The pinned Kali box requires a 64-bit Windows host."
        $healthy = $false
    }

    try {
        $settings = Get-Settings
        Write-DoctorCheck -Level ok -Message "kali-vm.json is valid: $($settings.memoryMB) MB RAM, $($settings.cpus) CPUs, box $($settings.box.version)."
    }
    catch {
        Write-DoctorCheck -Level fail -Message $_.Exception.Message
        $healthy = $false
    }

    try {
        $processor = Get-CimInstance Win32_Processor | Select-Object -First 1
        if ($processor.VirtualizationFirmwareEnabled) {
            Write-DoctorCheck -Level ok -Message "CPU virtualization is enabled ($($processor.NumberOfCores) cores / $($processor.NumberOfLogicalProcessors) threads)."
        }
        else {
            Write-DoctorCheck -Level fail -Message "CPU virtualization appears disabled in BIOS/UEFI."
            $healthy = $false
        }
    }
    catch {
        Write-DoctorCheck -Level warn -Message "Could not query CPU virtualization: $($_.Exception.Message)"
    }

    try {
        $os = Get-CimInstance Win32_OperatingSystem
        $totalGB = [math]::Round([double]$os.TotalVisibleMemorySize / 1MB, 1)
        $freeGB = [math]::Round([double]$os.FreePhysicalMemory / 1MB, 1)
        Write-DoctorCheck -Level ok -Message "RAM: ${totalGB} GB total, ${freeGB} GB currently free."
    }
    catch {
        Write-DoctorCheck -Level warn -Message "Could not query host RAM."
    }

    try {
        foreach ($driveStatus in (Get-CreationDriveStatus -AllowVirtualBoxFallback)) {
            $freeDiskGB = [math]::Round($driveStatus.FreeBytes / 1GB, 1)
            if ($driveStatus.FreeBytes -ge $script:MinimumFreeDiskBytes) {
                Write-DoctorCheck -Level ok -Message "Disk $($driveStatus.Root) ($($driveStatus.Purposes)): ${freeDiskGB} GB free."
            }
            else {
                Write-DoctorCheck -Level fail -Message "Disk $($driveStatus.Root) ($($driveStatus.Purposes)): only ${freeDiskGB} GB free; at least 20 GB is required."
                $healthy = $false
            }
        }
    }
    catch {
        Write-DoctorCheck -Level fail -Message "Could not query create/rebuild storage: $($_.Exception.Message)"
        $healthy = $false
    }

    $vboxManage = Resolve-VBoxManagePath
    if ($null -eq $vboxManage) {
        Write-DoctorCheck -Level fail -Message "VirtualBox is missing. Run: KaliVM.cmd install"
        $healthy = $false
    }
    else {
        try {
            $vboxOutput = Invoke-ExternalCapture -Executable $vboxManage -Arguments @("--version")
            Write-DoctorCheck -Level ok -Message "VirtualBox $vboxOutput at $vboxManage"
        }
        catch {
            Write-DoctorCheck -Level fail -Message "VirtualBox was found but did not run: $($_.Exception.Message)"
            $healthy = $false
        }
    }

    $vagrant = Resolve-VagrantPath
    if ($null -eq $vagrant) {
        Write-DoctorCheck -Level fail -Message "Vagrant is missing. Run: KaliVM.cmd install"
        $healthy = $false
    }
    else {
        try {
            $vagrantOutput = Invoke-ExternalCapture -Executable $vagrant -Arguments @("--version")
            $vagrantVersion = ConvertTo-Version -Text $vagrantOutput
            if ($null -ne $vagrantVersion -and $vagrantVersion -ge $script:MinimumVagrantVersion) {
                Write-DoctorCheck -Level ok -Message "$vagrantOutput at $vagrant"
            }
            else {
                Write-DoctorCheck -Level fail -Message "Vagrant $($script:MinimumVagrantVersion) or newer is required; found $vagrantOutput."
                $healthy = $false
            }
        }
        catch {
            Write-DoctorCheck -Level fail -Message "Vagrant was found but did not run: $($_.Exception.Message)"
            $healthy = $false
        }
    }

    $ssh = Resolve-SshPath
    if ($null -eq $ssh) {
        Write-DoctorCheck -Level warn -Message "Windows OpenSSH is missing. 'vagrant ssh' may still work, but exported ssh-config will need an SSH client."
    }
    else {
        Write-DoctorCheck -Level ok -Message "Windows OpenSSH is available at $ssh"
    }

    try {
        $deviceGuard = Get-CimInstance -Namespace "root\Microsoft\Windows\DeviceGuard" -ClassName Win32_DeviceGuard -ErrorAction Stop
        if ($deviceGuard.VirtualizationBasedSecurityStatus -eq 2) {
            Write-DoctorCheck -Level warn -Message "Windows VBS/hypervisor is active. VirtualBox should work through NEM, but this VM may run more slowly."
        }
    }
    catch {
        # VBS reporting is optional and varies by Windows edition.
    }

    if ($null -ne $vagrant -and (Test-Path -LiteralPath $script:StateRoot -PathType Container)) {
        Write-DoctorCheck -Level ok -Message "Managed Kali state exists. Use 'KaliVM.cmd status' for its live VM state."
    }
    elseif ($null -ne $vagrant) {
        Write-DoctorCheck -Level ok -Message "Managed Kali VM state is not initialized yet (expected before first create)."
    }

    Write-Host ""
    if ($healthy) {
        Write-Success "This PC is ready. Next: KaliVM.cmd create"
    }
    else {
        Write-Failure "One or more required checks failed. Fix the failed item(s), then run doctor again."
        $script:ExitCode = 1
    }
}

function Invoke-Main {
    switch ($Command.ToLowerInvariant()) {
        "help" { Show-Help }
        "doctor" { Invoke-Doctor }
        "install" { Invoke-InstallPrerequisites }
        "validate" { Invoke-Validate }
        "create" { Invoke-Create }
        "repair" { Invoke-Repair }
        "start" { Invoke-Start }
        "terminal" { Invoke-Terminal }
        "shell" { Invoke-Terminal }
        "run" { Invoke-GuestCommand }
        "stop" { Invoke-Stop }
        "status" { Invoke-Status }
        "ssh-config" { Export-SshConfig }
        "health" { Assert-Prerequisites; Invoke-HealthCheck }
        "snapshot" { Invoke-SnapshotSave }
        "snapshots" { Invoke-SnapshotList }
        "restore" { Invoke-SnapshotRestore }
        "destroy" { Invoke-Destroy }
        "rebuild" { Invoke-Rebuild }
    }
}

try {
    Invoke-Main
}
catch {
    Write-Failure $_.Exception.Message
    $script:ExitCode = 1
}

exit $script:ExitCode
