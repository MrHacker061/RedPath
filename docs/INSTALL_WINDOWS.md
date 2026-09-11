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

Have sufficient free space before setup. The model and managed Kali image are
large downloads, but the current API, manifest, and UI do not expose an exact
download-size field before consent. There is no source-bound numeric size to
publish in this guide. This is a release blocker recorded in the checklist;
confirm exact transfer and storage requirements only from the final pinned
release artifacts until the UI exposes them.

## Install

1. Obtain `RedPath-Setup-0.1.0-x64.exe` from an authorized release.
2. Verify the release-provided SHA-256 before opening it. For example:

   ```powershell
   Get-FileHash .\RedPath-Setup-0.1.0-x64.exe -Algorithm SHA256
   ```

3. Run the installer. It adds a Start menu shortcut and offers an optional
   desktop shortcut.
4. Let the installer open RedPath.

Development artifacts are **unsigned** unless the release checklist says
otherwise. Windows may show a publisher or reputation warning for an unsigned
development build. Do not bypass a warning unless you independently verified
the source and installer hash.

## Check and repair local components

The current setup UI reports four components: Ollama, model, WSL2, and managed
Kali. Select one component, use **Refresh setup** to reread its status, and use
**Repair** only after the application's confirmation dialog. A repair is
synchronous: the UI shows the returned stage status after it finishes. If a
repair is in progress, the UI offers **Cancel** for that active component.

WSL2 may require an administrator-approved Windows prompt and may require a
restart. Restart RedPath after Windows restarts, then use **Refresh setup**.
The current UI does not display a downloadable artifact's pinned version,
checksum, or byte size, and it does not provide a separate Retry or View
Details control. Do not infer those details from a component card.

You can still review imported evidence when the model or managed Kali component
needs attention. Recommendations or action execution remain unavailable until
their required component is healthy.

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
