# Task 8 report: Windows installer and release checks

## Scope completed

- Added a per-user, Windows 11 x64 Inno Setup definition for
  `RedPath-Setup-0.1.0-x64.exe`.
- Added a build script that reports stable, non-installing prerequisite and
  input failures before compiling.
- Added policy checks for installer metadata, shortcuts, safe first-run launch,
  and default preservation of user data, local models, and `RedPath-Kali`.
- Added a fake-only end-to-end API workflow from setup health through a closed
  session report. It does not start host processes, contact a model service,
  invoke WSL, or contact a target.
- Added the Windows install guide and a release checklist with unverified
  clean-machine gates called out explicitly.

## Verification

- `python -m pytest`: 287 passed; two third-party TestClient deprecation
  warnings were reported.
- `node --test frontend/tests/*.test.js`: 65 passed.
- `tests/Test-KaliVM.ps1`, `tests/Test-DesktopBuild.ps1`, and
  `tests/Test-Installer.ps1`: passed.
- `python -m compileall -q redpath redpath_ai redpath_kali redpath_setup scanner`
  and `git diff --check`: passed.
- The desktop and installer build commands each exited with their documented
  code 2 prerequisite outcome. No desktop dependencies or Inno Setup compiler
  were present, and none were installed.

## Confirmed limitation

`create_app()` assigns `RuleBasedProvider` rather than an `OllamaProvider`.
The existing test explicitly verifies that default. This Task 8 work leaves the
provider selection unchanged; it is a release gap documented in
`docs/MVP_RELEASE_CHECKLIST.md`.

The setup manifest and API also omit exact pre-consent download-size metadata.
The guide gives a practical capacity estimate and the checklist records the
missing product disclosure as a separate release blocker.

## Non-actions

No installer, desktop executable, model, managed environment, target action,
or remote download was created or run by the fake-only test. No artifact was
published, signed, pushed, or released.
