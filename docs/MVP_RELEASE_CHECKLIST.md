# RedPath Windows MVP release checklist

Release decision: **not approved for publication**. The unsigned 0.1.0
candidate passed the local Windows install, API launch, and default uninstall
smoke test on 2026-09-12. Separate clean-machine and real-component gates remain
open. This record does not publish, sign, or distribute an artifact.

## Automated and build evidence

| Check | Status | Evidence |
| --- | --- | --- |
| Full Python suite | verified at corrected source | `python -m pytest -q` for transport-fix commit `c828f078b1315d8ed0c20fa619a04872e953bb2c`: 391 passed, two third-party deprecation warnings, 177.19 seconds before commit. |
| Frontend suite | verified at corrected source | All `frontend/tests/*.test.js`: 72 passed, zero failed. |
| Focused release regression checks | verified locally | AI, recommendation API, and desktop workflow: 61 passed. Recommendation API, setup API, and setup foundation: 37 passed. Both Python runs had two existing warnings. `node --test frontend/tests/setup.test.js`: 8 passed. |
| Fake-only session-to-report workflow | verified | `tests/test_desktop_workflow.py` replaces setup, model, WSL, and action execution with local fakes; exactly one started and one completed audit event share approval, proposal, and action IDs. |
| Default recommendation provider | verified in source/tests | `create_app()` selects `OllamaProvider()`. Its private opener disables ambient/system proxies and rejects all redirects. Network-free tests verify prompt destinations, no redirect follow-up, and deterministic fallback; bounded attempts, response limits, and strict output validation remain. This is not evidence of a real model response. |
| Download-size disclosure | verified in source/tests and packaged API | Ollama `1574272976`, model `4683087332`, Kali `247857686` bytes; WSL version and size are `null`. Frontend tests cover literal-text display and disabling Repair until metadata loads. |
| Installer policy | verified locally | `pwsh -NoProfile -File tests/Test-Installer.ps1`: process exit 0. Checks approved payload/shortcut/launch entries, preserved-data policy, and missing prerequisites. |
| Desktop build policy | verified locally | `pwsh -NoProfile -File tests/Test-DesktopBuild.ps1`: process exit 0. |
| Kali launcher policy | verified locally | `pwsh -NoProfile -File tests/Test-KaliVM.ps1`: process exit 0, 39 passed checks. |
| Desktop rebuild | verified | `pwsh -NoProfile -File scripts/build-desktop.ps1`: exit 0; complete corrected one-directory payload produced. |
| Installer rebuild | verified | `scripts/build-installer.ps1` with Inno Setup 6.7.3: exit 0. |

The corrected source adds 27 network-free transport regression cases to the
previous 364-test Python baseline. Documentation changes after the artifact
build do not alter product source. Prior binaries and build cache are preserved
in the ignored release-plan workspace under `pre-transport-fix-dist` and
`pre-transport-fix-build-desktop`.

## Observed local Windows smoke test

Host: Windows 11 x64, build 26200, existing development account. This was not a
separate clean Windows machine. Both supplied artifact hashes were checked
before execution. No component repair, dependency download, model pull, WSL
enablement/import, or lab action was requested.

| Check | Result | Observed evidence |
| --- | --- | --- |
| Unpackaged API launch | passed | Captured PID `39532`, sole listener `127.0.0.1:57087`; `/api/v1/health` and `/` returned HTTP 200. Health reported `status=ok`, `database=ok`, `service=redpath-api`, version `0.1.0`. |
| Unpackaged setup metadata | passed | `/api/v1/setup` returned HTTP 200 in 42.18 seconds with all four exact size values above, before any repair. |
| Per-user installation | passed | Installer PID `41036`, `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-`, exit 0. Installed at `%LOCALAPPDATA%\Programs\RedPath`. |
| Installed payload and shortcut | passed | All 233 payload files matched the source payload by SHA-256. `%APPDATA%\Microsoft\Windows\Start Menu\Programs\RedPath.lnk` targeted the installed `RedPath.exe`. Optional desktop shortcut was absent. |
| Installed API launch | passed | Captured PID `40232`, sole listener `127.0.0.1:51374`; health and `/` returned HTTP 200. Health reported the same healthy API/database identity. |
| Installed setup metadata | passed | HTTP 200 in 64.11 seconds; exact Ollama/model/Kali byte counts and WSL `null` matched the unpackaged response. |
| Process cleanup | passed within smoke scope | Stopped only identity-checked task-started RedPath PIDs `39532` and `40232`; their listeners were absent afterward. No RedPath processes remained. |
| Default uninstall | passed | Exact uninstaller `%LOCALAPPDATA%\Programs\RedPath\unins000.exe`, PID `22140`, `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART`, exit 0. All payload files and Start menu shortcut were removed; the install directory disappeared after uninstaller self-cleanup. |
| Existing application-data preservation | passed | `%LOCALAPPDATA%\RedPath` remained. The task-created sentinel survived uninstall unchanged; the existing `redpath.db` retained SHA-256 `3163BBB174DBBF47F606FC5D321D42BA307534F54DAB632B6AA59333D534E462`. The sentinel is preserved with the ignored smoke evidence. |

The desktop reserves an OS-assigned loopback port; port 8000 is not its fixed
runtime address. Both corrected-artifact launches passed on their first smoke
attempt with a 160-second setup request deadline covering sequential WSL status
probes. No WSL process was terminated by this fix wave.

Both setup responses reported `OLLAMA_UNAVAILABLE` for Ollama/model,
`WSL_UNAVAILABLE` for WSL, and `KALI_WSL_REQUIRED` for Kali. This validates
unavailable-component reporting and metadata, not component readiness.
Desktop launches used hidden windows; a WebView2 child existed, but rendered
native-window behavior and graceful window-close shutdown were not verified.
The smoke stopped the exact captured processes after evidence collection.

## Unresolved release gates

All clean-machine gates require a separate Windows 11 x64 machine and an
authorized private lab where applicable. Local smoke and fake-only tests do
not substitute for them.

| Gate | Status | Required evidence |
| --- | --- | --- |
| Separate clean Windows installation and Start menu launch | not run | Install the exact candidate on a clean account and open the actual shortcut. Local shortcut existence/target verification alone does not cover this. |
| Visible native application window | not run | Verify one rendered window, setup disclosure, WebView2 behavior, and graceful close with loopback-only service ownership. |
| Ollama consent and install | not run | Confirm consent, pinned download, checksum/size verification, and completed stage. |
| Real default-model pull and recommendation | not run | Pull `qwen2.5:7b-instruct-q4_K_M`; verify size/storage, progress, cancellation, retry, detection, and a recommendation produced by the model. |
| WSL enablement and restart recovery | not run | Approve the Windows prompt, restart if required, and resume setup. |
| Managed Kali import | not run | Verify the exact marker-owned `RedPath-Kali` distribution and healthy status after import. |
| Authorized real-lab workflow | not run | Complete session, evidence import, recommendation, explicit approval, one fixed action, audit, and report against an approved private target; verify behavior when components need attention. |
| Emergency stop | not run against a real lab | Verify blocked new starts and the documented in-flight-action limit. |
| Component repair | not run | Induce an approved component failure and exercise its consented repair path. |
| Existing model/distribution preservation during uninstall | not run with populated components | Local `.ollama`, Ollama app-data, and the per-user WSL distribution registry were absent before and after this smoke. Preservation of an installed model or real `RedPath-Kali` remains untested. |
| Code signing | unresolved | Both candidate binaries report `NotSigned`; no signing certificate was used. |
| Final integration and release-owner approval | unresolved | Automated checks pass; independent release review and release-owner approval remain required. No publication is authorized by this record. |

Ollama is the default provider, with deterministic fallback when unavailable,
redirected, or invalid. Setup cards describe component status; they do not grant action
approval or establish that a recommendation came from the real model.

## Source and runtime binding

Both artifacts were built from clean source commit
`c828f078b1315d8ed0c20fa619a04872e953bb2c`, which includes the loopback
transport fix. The local smoke used those exact corrected hashes. Only these
release documents changed after the build; product source was unchanged.

| Item | Bound value |
| --- | --- |
| Python runtime | CPython 3.14.7, Windows x64 |
| Node runtime | v24.19.0 |
| Corrected build, smoke, and static-test runtime | PowerShell 7.6.5 |
| PyInstaller | 6.22.2, installed |
| pywebview | 6.2.1, installed |
| Inno Setup compiler | 6.7.3 at `C:\Users\bocaj\AppData\Local\Programs\Inno Setup 6\ISCC.exe` |
| Observed WebView2 runtime | 152.0.4191.66 |
| Ollama setup artifact | 0.34.0, 1,574,272,976 bytes |
| Default model metadata | `qwen2.5:7b-instruct-q4_K_M`, 4,683,087,332 bytes |
| Managed Kali artifact | 2026.2, 247,857,686 bytes |

Static checks were evaluated by the standalone PowerShell process exit code;
their intentional nested missing-prerequisite probes return 2 internally.
No execution-policy setting was changed. The build retained its existing
optional hidden-import warnings; API/sqlite/setup smoke does not cover every
optional import. No same-source reproducibility comparison or complete
transitive-dependency pinning claim is made.

## Candidate artifact record

| Field | Value |
| --- | --- |
| Candidate version | 0.1.0 |
| Build source commit | `c828f078b1315d8ed0c20fa619a04872e953bb2c` |
| Local-smoke product source commit | `c828f078b1315d8ed0c20fa619a04872e953bb2c` |
| Installer path | `C:\Users\bocaj\Downloads\Headless Kali Linux\.worktrees\pr11-merge\dist\installer\RedPath-Setup-0.1.0-x64.exe` |
| Installer bytes | 22,747,157 |
| Installer SHA-256 | `F1EF18DD36516DE67FB64AF13CD4428AE0925915E31100B603867957C35C3473` |
| Executable path | `C:\Users\bocaj\Downloads\Headless Kali Linux\.worktrees\pr11-merge\dist\RedPath\RedPath.exe` |
| Executable bytes | 11,766,166 |
| Executable SHA-256 | `D0C867E37CEDCF254113D4DCB87D45A67B814BE89202D73931DB0E360A4C4FAC` |
| Signing certificate / status | No certificate; both files `NotSigned` |
| Local install/API/uninstall smoke | passed on 2026-09-12, with limitations above |
| Release owner decision | not approved for publication |

`RedPath.exe` requires the complete `dist\RedPath` one-directory payload or
the installer. The smoke installation was uninstalled; the build artifacts
remain at the recorded paths and are ignored by Git.
