# RedPath Windows MVP release checklist

Release decision: **not approved**. This checklist records evidence; it does
not publish, sign, or distribute an artifact.

## Automated evidence

| Check | Status | Evidence |
| --- | --- | --- |
| Fake-only session-to-report workflow | verified | `tests/test_desktop_workflow.py` replaces setup, model, WSL, and action execution with local fakes. |
| Installer policy | verified | `tests/Test-Installer.ps1` checks per-user x64 metadata, shortcuts, first-run launch, and the absence of download or destructive uninstall hooks. |
| Installer unavailable-prerequisite behavior | verified | `tests/Test-Installer.ps1` invokes the build script with a nonexistent compiler and requires exit code 2 plus `INSTALLER_BUILD_PREREQUISITE`. |
| Full automated suite | verified | `python -m pytest`: 287 passed (two third-party TestClient deprecation warnings). |
| Frontend suite | verified | `node --test frontend/tests/*.test.js`: 65 passed. |
| Desktop build script | verified | Exited 2 with `DESKTOP_BUILD_PREREQUISITE`; pinned desktop dependencies are absent and were not installed. |
| Installer build script | verified | Exited 2 with `INSTALLER_BUILD_PREREQUISITE`; `ISCC.exe` is absent and was not installed. |

## Clean Windows 11 x64 release gates

All gates below require an isolated clean machine and an authorized private lab
where applicable. They are not substituted by the fake-only test suite.

| Gate | Status | Evidence or next action |
| --- | --- | --- |
| Installer launch from Start menu | not run | Install the final x64 installer on a clean Windows 11 x64 account. |
| Ollama consent and install | not run | Confirm the consent gate, pinned download, checksum verification, and completed stage. |
| Default model pull | not run | Confirm progress, cancellation, retry, and local model detection. |
| Download-size disclosure | failed | The current setup API and manifest do not expose an exact model or Kali transfer-size field before consent. Add and verify it before release. |
| WSL enablement and restart recovery | not run | Approve the Windows prompt, restart if requested, and resume setup. |
| Managed Kali import | not run | Confirm only `RedPath-Kali` is accepted and health recovers after import. |
| Native application window | not run | Confirm a single local window launches and the service remains loopback-only. |
| Authorized lab workflow | not run | Complete session, evidence import, recommendation, approval, one fixed action, audit, and report against an approved private lab. |
| Emergency stop | not run | Confirm it blocks a new action start and the UI explains the in-flight-action limit. |
| Component repair | not run | Induce an approved local component failure and use the matching repair path. |
| Default uninstall preservation | not run | Confirm packaged files and shortcuts are removed while `%LOCALAPPDATA%\RedPath`, local model data, and `RedPath-Kali` remain. |
| Final executable SHA-256 | not run | Record `Get-FileHash dist\RedPath\RedPath.exe -Algorithm SHA256`. |
| Final installer SHA-256 | not run | Record `Get-FileHash dist\installer\RedPath-Setup-0.1.0-x64.exe -Algorithm SHA256`. |
| Signing status | failed | Development build is unsigned; do not describe it as signed. |
| Executable artifact path | not run | Expected: `dist\RedPath\RedPath.exe` after a successful desktop build. |
| Installer artifact path | not run | Expected: `dist\installer\RedPath-Setup-0.1.0-x64.exe` after a successful installer build. |

## Known release gap

`redpath.app.create_app()` currently selects `RuleBasedProvider` directly,
even though setup installs and checks the local Ollama model. The app therefore
does not use the configured local model by default. This is confirmed by
`tests/test_recommendation_api.py::test_application_defaults_to_rule_based_recommendation_provider`.
It is outside Task 8's installer/documentation scope and must be resolved or
explicitly accepted before claiming the model-backed MVP workflow is complete.

The setup manifest also lacks a download-size field, so the UI cannot disclose
an exact model or Kali transfer size before consent. This is outside Task 8's
installer/documentation scope but blocks the corresponding product requirement.

## Release record

Fill this section only after a release owner independently reviews the clean
machine evidence.

| Field | Value |
| --- | --- |
| Candidate version | 0.1.0 |
| Commit | pending Task 8 commit |
| Installer path | not built |
| Installer SHA-256 | not available |
| Executable path | not built |
| Executable SHA-256 | not available |
| Signing certificate / status | unsigned development build |
| Release owner decision | not approved |
