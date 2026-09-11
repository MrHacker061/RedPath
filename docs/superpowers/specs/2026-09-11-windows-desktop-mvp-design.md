# RedPath Windows Desktop MVP Design

## Goal

Deliver RedPath as a downloadable Windows 11 x64 application with its own window. A new user must be able to install it, complete guided setup, and finish one authorized TryHackMe-style learning workflow without opening a terminal.

## Product boundary

RedPath is a beginner-focused cybersecurity learning app for systems the user owns or is explicitly authorized to test. It explains imported evidence, recommends one fixed learning action, requires approval, runs the exact approved action in a managed Kali environment, and records a bounded report.

The MVP will not provide arbitrary commands, public-target testing, credential guessing, reverse shells, persistence, stealth, Metasploit automation, or unrestricted exploitation. The model can recommend but cannot authorize or execute work.

## Supported platform

- Windows 11 x64 only.
- One interactive desktop user per installation.
- One RedPath application process and one FastAPI worker.
- WSL2 supplies the managed Kali environment; VirtualBox is not required.
- Internet access is required during installation and first-run model/environment downloads.

Windows 10, Windows on ARM, offline installation, multiple FastAPI workers, remote access, and multi-user accounts are outside the MVP.

## Architecture

### Desktop host

`RedPath.exe` is a small Python desktop host packaged with PyInstaller. It starts the FastAPI application on an available loopback port, waits for a successful health response, opens a WebView2 window, and shuts the server down when the window closes. The host must never bind to a non-loopback address.

The desktop host will use `pywebview`, which reuses the WebView2 runtime included with supported Windows 11 installations. It will show a native error dialog if WebView2 or the local server cannot start.

### Local web application

FastAPI will serve both `/api/v1/*` and the existing dependency-free frontend assets. The root path will return the application shell. Static file paths will be resolved through a packaging-aware resource helper so development and PyInstaller builds use the same code path.

The browser-facing frontend remains unable to submit arbitrary commands. Execution requests identify only a stored session and proposal; the backend reconstructs and revalidates the approved action.

### Data storage

SQLite, logs, downloaded setup metadata, and configuration will live below `%LOCALAPPDATA%\RedPath`. Packaged application files are read-only. Existing forward-only database migrations run before the desktop window becomes ready.

The application will create required directories with user-only access where Windows permits. Logs will use stable status codes and will not contain credentials, unrestricted model responses, raw action output, or secrets.

### Ollama

The Windows installer will acquire a pinned, checksum-verified Ollama installer from the official Ollama distribution source and install it only after the user confirms the setup step. RedPath will not silently download or execute an unverified binary.

First-run setup will:

1. Detect the configured Ollama executable and local loopback service.
2. Start or repair the local service when possible.
3. Download the pinned default model with visible progress and cancellation.
4. Confirm the model appears in Ollama's local model list.
5. Run a bounded structured-response health check.

The model download is not bundled in the RedPath installer. The default model and download size will be shown before download. Users can retry a failed download without repeating completed setup stages.

### WSL2 and managed Kali

First-run setup will detect WSL2 using Windows' native `wsl.exe` interface. If WSL2 is unavailable, RedPath will explain that enabling it requires administrator approval and may require a restart. RedPath will never bypass Windows elevation prompts.

After WSL2 is available, RedPath will import or install a pinned RedPath-managed Kali distribution under the name `RedPath-Kali`. The app will record the expected distribution identity and validate it before every action. It will not send actions to an arbitrary user-selected distribution.

The Kali adapter will use argument arrays with `shell=False` and a fixed command registry. It will accept only the existing TCP connection, HTTP header, and TLS certificate inspection actions. Every request must retain session, target, proposal, approval, expiration, emergency-stop, and result-scope validation.

### Emergency stop

The MVP runs one application process because the execution fence is process-local. Activating the emergency stop is ordered against new action starts. An action already dispatched may finish; the interface must say this explicitly. Durable stop state remains in SQLite and is checked again immediately before dispatch.

## User experience

### First-run setup

The setup wizard contains ordered stages for application storage, Ollama, model download, WSL2, managed Kali, and final health verification. Each stage reports `Ready`, `Needs attention`, `In progress`, or `Failed` and offers only relevant Retry, Repair, or View Details actions.

A user may leave setup and return later. Completed stages are revalidated rather than trusted from a saved checkbox. RedPath can still open in evidence-review mode when Ollama or Kali is unavailable.

### Dashboard

The dashboard displays FastAPI, database, Ollama, WSL2, and Kali health. It links to setup repair, a new lab session, existing sessions, settings, and diagnostics. Health details use application-owned messages rather than raw dependency output.

### Lab workflow

The complete MVP workflow is:

1. Create a time-limited lab session and explicitly confirm authorization.
2. Enter a lesson URL separately from the private target address.
3. Import Nmap XML containing exactly the authorized target.
4. Review observed, inferred, and verified findings.
5. Generate a local explanation and request a safe recommendation.
6. Review the exact fixed action, target, arguments, supporting evidence, and expiration.
7. Approve or reject the proposal.
8. Explicitly run an approved proposal.
9. Review structured evidence, cleanup status, audit history, and the learning report.

The run control is displayed only after a valid approval receipt. The backend remains authoritative; hiding or enabling a control never grants permission.

### Settings and diagnostics

Settings shows the selected Ollama model, data location, Kali distribution identity, and component repair actions. Diagnostics offers a redacted, copyable summary containing versions and stable error codes but no raw target output or secrets.

## Failure handling

- Startup failure shows a native dialog and writes a bounded local diagnostic record.
- Missing WebView2 stops startup with official repair guidance.
- Database migration failure stops startup without modifying additional state.
- Ollama or model failure disables recommendations but preserves evidence review.
- WSL2 or Kali failure disables action execution but preserves approval review and reports.
- Authorization, scope, target, approval, expiration, emergency-stop, and dispatcher uncertainty fail closed.
- Interrupted setup resumes from revalidated component state.
- Installer and setup downloads require HTTPS, a pinned version, and a pinned SHA-256 checksum.

## Installer and lifecycle

Inno Setup will produce a signed-ready Windows installer definition. The MVP build may be unsigned during development, but documentation must clearly identify that limitation.

The installer will:

- Install RedPath under the current user's application location.
- Create Start menu and optional desktop shortcuts.
- Acquire and configure the pinned Ollama version with explicit consent.
- Launch RedPath's first-run setup.
- Avoid bundling VirtualBox or an AI model.

Uninstall removes packaged application files and shortcuts. It will ask separately before deleting `%LOCALAPPDATA%\RedPath`, the Ollama model, or `RedPath-Kali`; user data and large environments are preserved by default.

## Testing strategy

### Automated tests

- Python unit tests for resource paths, application directories, startup state, setup state transitions, checksums, WSL command construction, distribution validation, and desktop-host shutdown.
- FastAPI integration tests for frontend/static serving, component health, setup status, repair boundaries, and the complete session-to-report workflow using injected fakes.
- Frontend Node tests for setup, dashboard health, execution controls, error states, accessibility, and safe rendering.
- PowerShell static tests for installer metadata and Windows launcher/build scripts.
- Existing authorization, fencing, action-registry, evidence-redaction, AI, parser, VM, and frontend suites remain green.

Every new behavior follows red-green-refactor. Tests must fail for the missing behavior before production code is added.

### Runtime verification

A clean Windows 11 x64 virtual machine will verify:

1. Installation without VirtualBox.
2. Explicit Ollama installation and first-run model download.
3. WSL2 enablement guidance and restart recovery.
4. Managed Kali installation and health recovery.
5. Desktop launch in its own window.
6. One complete authorized TryHackMe-style workflow.
7. Emergency-stop behavior.
8. Repair and uninstall behavior.

Live runtime checks that require administrator approval, a Windows restart, large downloads, or an authorized lab target remain manual release gates; automated tests use fakes and never contact a real target.

## Build and release outputs

The repository will provide:

- A repeatable PyInstaller build command.
- An Inno Setup script.
- A development launcher.
- A packaged desktop executable.
- A Windows installer artifact when the required local build tools are available.
- A short installation and demo guide.
- A release checklist that records installer hash, dependency versions, test results, and unresolved signing limitations.

No artifact is pushed, published, or released without separate user authorization.

## MVP acceptance criteria

The MVP is accepted when all of the following are true:

- RedPath installs on a clean Windows 11 x64 system without VirtualBox.
- It opens in its own WebView2 window from a Start menu shortcut.
- Ollama is installed with user confirmation and the default model is downloaded during first-run setup.
- WSL2 and `RedPath-Kali` are configured through a resumable wizard.
- Component failures provide safe Retry, Repair, or View Details paths.
- The existing authorized workflow completes through a structured learning report.
- No UI or API accepts arbitrary commands, arbitrary WSL distributions, public targets, credentials, or reverse-shell payloads.
- Emergency stop blocks new action starts in the single-process app.
- All automated test suites pass.
- The clean-machine runtime checklist is completed or each unavailable external verification is clearly reported as unverified.

## Deliberate MVP omissions

- No Electron or Tauri shell.
- No custom updater.
- No cloud service or remote API.
- No bundled AI model.
- No VirtualBox support.
- No multi-process FastAPI deployment.
- No Windows 10 or ARM build.
- No automatic action chaining.
- No arbitrary terminal or exploit framework integration.

These features should be added only after the MVP workflow is proven and a specific requirement justifies their cost.
