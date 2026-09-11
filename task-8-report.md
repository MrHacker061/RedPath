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
The guide does not publish an unsupported size estimate, and the checklist
records the missing product disclosure as a separate release blocker.

## Non-actions

The fake-only test did not run a real external target action or process. No
artifact was published, signed, pushed, or released.

## Correction round 1

- Corrected the install guide to describe only the current Ollama, model, WSL2,
  and managed-Kali refresh, repair, and cancel controls. It no longer claims
  storage/final stages, progress, pin display, Retry, or View Details controls.
- Recorded that exact pre-consent model and Kali download sizes are unavailable
  from the current API, manifest, and UI; the checklist retains this as a
  release blocker rather than publishing an unsupported estimate.
- Extended the fake-only workflow assertion from approval through the exact
  action ID, action-started/action-completed audit events, and proposal-bound
  report entries. The completion audit now records `approval_id`, and the start
  audit flushes the generated action ID before it is recorded.
- Replaced the installer-policy denylist with allowed installer sections,
  approved payload destination, exact shortcut/launch entries, and adversarial
  checks for lifecycle deletion sections, flags, and preserved-data deletion.
- Bound the release checklist baseline to `cda4aac` and recorded the current
  Python, Node, PowerShell, tool pins, and setup artifact versions.

Verification for this correction: `python -m pytest` passed 287 tests; the
frontend suite passed 65 tests; Kali VM, desktop-build, and installer policy
checks passed; `compileall` and `git diff --check` passed. Both build scripts
returned their stable exit code 2 prerequisite outcome without installing
anything.
