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

Have sufficient free space before setup. The default
`qwen2.5:7b-instruct-q4_K_M` model is about 4.7 GB. The managed Kali image is a
multi-gigabyte download. Allow at least 20 GB free for the image, extracted
environment, model, and working data. The release candidate does not yet carry
an exact Kali-size field into the setup UI, so verify the final artifact's
transfer size and consent display during the clean-machine release gate.

## Install

1. Obtain `RedPath-Setup-0.1.0-x64.exe` from an authorized release.
2. Verify the release-provided SHA-256 before opening it. For example:

   ```powershell
   Get-FileHash .\RedPath-Setup-0.1.0-x64.exe -Algorithm SHA256
   ```

3. Run the installer. It adds a Start menu shortcut and offers an optional
   desktop shortcut.
4. Let the installer open RedPath. The setup wizard can be left and resumed;
   completed stages are checked again rather than trusted from a saved status.

Development artifacts are **unsigned** unless the release checklist says
otherwise. Windows may show a publisher or reputation warning for an unsigned
development build. Do not bypass a warning unless you independently verified
the source and installer hash.

## Complete first-run setup

The in-app wizard shows storage, Ollama, model, WSL2, managed Kali, and final
health stages. It never installs those large dependencies silently.

- Confirm the Ollama step before its pinned installer is downloaded and run.
- Confirm the model download after reviewing its local storage requirement and
  progress.
- WSL2 may require an administrator-approved Windows prompt. A restart may be
  required before setup can continue.
- Confirm the managed Kali import only after setup shows the pinned artifact
  and progress.

If a stage fails, use only the wizard's matching **Retry**, **Repair**, or
**View Details** action. Restart RedPath after a Windows restart, then reopen
setup. You can still review imported evidence when the model or managed Kali
stage needs attention; recommendations or action execution remain unavailable
until their required components are healthy.

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
