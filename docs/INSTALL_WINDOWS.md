# Install RedPath on Windows

## Before you start

RedPath MVP supports one interactive user on **Windows 11 x64** only. An
internet connection is required for the initial setup downloads. The packaged
app installs per user under `%LOCALAPPDATA%\Programs\RedPath`; its mutable
data stays in `%LOCALAPPDATA%\RedPath`.

Use RedPath only with systems you own or have explicit permission to test. The
MVP accepts private, authorized lab targets and its fixed learning actions only;
it does not provide a command shell, credential testing, public-target testing,
or exploitation automation.

Setup discloses these download sizes before repair consent:

| Component | Version or model | Exact disclosed bytes | Displayed size |
| --- | --- | --- | --- |
| Ollama installer | 0.34.0 | 1,574,272,976 | 1.47 GiB |
| Local model | `qwen2.5:7b-instruct-q4_K_M` | 4,683,087,332 | 4.36 GiB |
| Managed Kali image | 2026.2 | 247,857,686 | 236.38 MiB |
| WSL2 | Managed by Windows | Unknown (`null` in the API) | No size shown |

These are transfer sizes, not installed disk-space requirements. Allow extra
space for installation, model storage, and the managed environment. Ollama and
Kali artifact downloads are checked against their pinned byte counts and
SHA-256 values. The model size is fixed setup metadata; a real model pull and
its storage requirements remain a release-verification gate.

## Install

1. Obtain `RedPath-Setup-0.1.0-x64.exe` from an authorized source. The current
   candidate is a local unsigned development build, not a published release.
2. Verify the candidate's SHA-256 against the [release checklist](MVP_RELEASE_CHECKLIST.md)
   before opening it. For example:

   ```powershell
   Get-FileHash .\RedPath-Setup-0.1.0-x64.exe -Algorithm SHA256
   ```

3. Run the installer. It adds a Start menu shortcut and offers an optional
   desktop shortcut.
4. Let the installer open RedPath.

The current executable and installer are **unsigned**. Windows may show a
publisher or reputation warning for an unsigned development build. Stop if
Windows blocks the artifact; this guide does not authorize bypassing security
warnings or changing Windows security policy.

## Check and repair local components

The current setup UI reports four components: Ollama, model, WSL2, and managed
Kali. Select one component, use **Refresh setup** to reread its status, and use
**Repair** only after the application's confirmation dialog. A repair is
synchronous: the UI shows the returned stage status after it finishes. If a
repair is in progress, the UI offers **Cancel** for that active component.

WSL2 may require an administrator-approved Windows prompt and may require a
restart. Restart RedPath after Windows restarts, then use **Refresh setup**.
Component cards display the pinned version or model name and a rounded
download size after status loads. Repair stays disabled while metadata is
loading or unavailable. WSL2 has no fixed download-size disclosure. The UI does
not display artifact checksums or provide a separate Retry or View Details
control. On a host where WSL status probes time out, a refresh can take over a
minute; wait for the returned component status before attempting repair.

RedPath uses local Ollama by default at `http://127.0.0.1:11434` with
`qwen2.5:7b-instruct-q4_K_M`. It validates model output against the allowed
actions and falls back to deterministic local recommendations if Ollama is
unavailable or its output remains invalid after bounded attempts. A successful
recommendation therefore does not prove the model was available.

You can still review imported evidence when components need attention. A Ready
card does not grant action approval or guarantee an action will run. Execution
still requires an exact approval, a clear emergency stop, and the managed
Kali checks. Real-model recommendations and the complete authorized-lab
workflow remain unverified release gates.

## Use the guided lab workflow

Create a time-limited session, explicitly confirm authorization, keep the
lesson URL separate from the private target address, and import evidence for
that target. Review the proposed fixed action and its expiration before
approval. Approval does not run anything: running is a separate explicit step.
The emergency stop blocks new starts; an action already sent to the managed
environment can finish.

## Uninstall

Uninstall removes the packaged application files and shortcuts. It preserves
`%LOCALAPPDATA%\RedPath`, local model data, and the managed `RedPath-Kali`
environment by default. Keep that data if you expect to reinstall or need the
local audit and learning records. Removing it is a separate, deliberate action
outside the default uninstaller.

## Building from source

Building is optional and does not install prerequisites for you. On a Windows
11 x64 development machine, install the repository's pinned desktop Python
dependencies yourself, run `scripts/build-desktop.ps1`, then provide an
installed Inno Setup compiler explicitly to:

```powershell
.\scripts\build-installer.ps1 -Compiler 'C:\Program Files (x86)\Inno Setup 6\ISCC.exe'
```

The build script stops with a stable prerequisite message when the compiler or
desktop executable is missing. A successful build writes
`dist\installer\RedPath-Setup-0.1.0-x64.exe` and prints its SHA-256.
