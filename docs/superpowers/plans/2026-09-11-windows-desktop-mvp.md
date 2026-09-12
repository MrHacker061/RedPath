# RedPath Windows Desktop MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a downloadable Windows 11 x64 RedPath application that opens in its own window and guides a user through Ollama, WSL2 Kali, and one complete authorized learning workflow.

**Architecture:** A PyInstaller-packaged Python host runs one loopback FastAPI worker and displays its dependency-free frontend in WebView2 through pywebview. Resumable setup services manage pinned Ollama and Kali WSL downloads, while the execution API continues to accept only stored, approved, fixed actions.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, SQLite, pywebview 6.2.1, PyInstaller 6.22.2, WebView2, WSL2, Ollama 0.34.0, Kali WSL 2026.2, vanilla JavaScript, Node test runner, PowerShell, Inno Setup.

**Spec:** `docs/superpowers/specs/2026-09-11-windows-desktop-mvp-design.md`

## Global Constraints

- Target Windows 11 x64 only.
- Bind HTTP only to `127.0.0.1` and run exactly one FastAPI worker.
- Store mutable state below `%LOCALAPPDATA%\RedPath`; packaged files remain read-only.
- VirtualBox is not installed or required.
- Ollama 0.34.0 installer URL is `https://github.com/ollama/ollama/releases/download/v0.34.0/OllamaSetup.exe`; SHA-256 is `e2b98770fb87f3b4c593c22f2e8eda59bcac1cd7b141f1388c4181a8bf271a72`.
- Kali URL is `https://kali.download/wsl-images/kali-2026.2/kali-linux-2026.2-wsl-rootfs-amd64.wsl`; SHA-256 is `1b172389e9109e9bb0c3d1fa18eda078271484dbcef8dbee4aab8b1f369466c6`.
- The managed WSL distribution name is exactly `RedPath-Kali`.
- Keep lesson URLs separate from target addresses.
- Accept only private, authorized targets and fixed TCP, HTTP-header, and TLS-certificate actions.
- Never expose arbitrary commands, credentials, raw action output, reverse shells, public-target testing, or automatic action chaining.
- Downloads require HTTPS, exact version pins, SHA-256 verification, visible consent, progress, and cancellation.
- No publish, push, release, environment deletion, WSL unregister, or user-data deletion without separate authorization.

---

### Task 1: Application paths and integrated frontend serving

**Files:**
- Create: `redpath/runtime.py`
- Modify: `redpath/config.py`
- Modify: `redpath/app.py`
- Test: `tests/test_runtime.py`
- Test: `tests/test_backend_foundation.py`

**Interfaces:**
- Produces: `AppPaths.from_environment(local_app_data: str | None = None, bundle_root: Path | None = None) -> AppPaths`
- Produces: `AppPaths.ensure() -> None`
- Produces: `create_app(settings: Settings | None = None, paths: AppPaths | None = None) -> FastAPI`
- Serves: `GET /` and `/assets/*` from the packaged `frontend` directory while preserving `/api/v1/*`

- [ ] **Step 1: Write failing path and static-serving tests**

```python
def test_app_paths_keep_mutable_data_outside_bundle(tmp_path):
    paths = AppPaths.from_environment(str(tmp_path / "Local"), tmp_path / "bundle")
    paths.ensure()
    assert paths.data_dir == tmp_path / "Local" / "RedPath"
    assert paths.database_file.parent == paths.data_dir
    assert paths.frontend_dir == tmp_path / "bundle" / "frontend"


def test_fastapi_serves_desktop_shell(client):
    response = client.get("/")
    assert response.status_code == 200
    assert '<main id="main-content"' in response.text
    assert client.get("/api/v1/health").status_code == 200
```

- [ ] **Step 2: Verify the tests fail for missing `AppPaths` and root route**

Run: `python -m pytest tests/test_runtime.py tests/test_backend_foundation.py -v`
Expected: collection fails because `redpath.runtime` is missing, then the root request fails with HTTP 404 after the import exists.

- [ ] **Step 3: Implement the minimal runtime paths and static routes**

```python
@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    database_file: Path
    log_dir: Path
    download_dir: Path
    wsl_dir: Path
    frontend_dir: Path

    @classmethod
    def from_environment(cls, local_app_data=None, bundle_root=None):
        data = Path(local_app_data or os.environ["LOCALAPPDATA"]) / "RedPath"
        bundle = Path(bundle_root or getattr(sys, "_MEIPASS", Path(__file__).parents[1]))
        return cls(data, data / "redpath.db", data / "logs", data / "downloads", data / "wsl", bundle / "frontend")

    def ensure(self):
        for path in (self.data_dir, self.log_dir, self.download_dir, self.wsl_dir):
            path.mkdir(parents=True, exist_ok=True)
```

Mount `/assets` with `StaticFiles(directory=paths.frontend_dir)` and return `FileResponse(paths.frontend_dir / "index.html")` from `/`. Reject a missing frontend directory during startup with a stable local error.

- [ ] **Step 4: Run focused and existing backend tests**

Run: `python -m pytest tests/test_runtime.py tests/test_backend_foundation.py tests/test_session_api.py -v`
Expected: all selected tests pass.

- [ ] **Step 5: Commit the slice**

```powershell
git add redpath/runtime.py redpath/config.py redpath/app.py tests/test_runtime.py tests/test_backend_foundation.py
git commit -m "feat: serve RedPath from packaged app paths"
```

---

### Task 2: Pinned download and setup component foundation

**Files:**
- Create: `redpath_setup/__init__.py`
- Create: `redpath_setup/downloads.py`
- Create: `redpath_setup/state.py` for `SetupStage`
- Create: `redpath_setup/manifest.py`
- Test: `tests/test_setup_foundation.py`

**Interfaces:**
- Produces: `Artifact(name: str, version: str, url: str, sha256: str, filename: str)`
- Produces: `OLLAMA_ARTIFACT` and `KALI_ARTIFACT` with the exact global pins
- Produces: `download_verified(artifact: Artifact, destination: Path, progress: Callable[[int, int | None], None], cancelled: Event, opener=urlopen) -> Path`
- Produces: `SetupStage(name: str, status: Literal["ready", "needs_attention", "in_progress", "failed"], code: str, detail: str)`

- [ ] **Step 1: Write failing checksum and cancellation tests**

```python
def test_download_rejects_wrong_checksum(tmp_path):
    artifact = Artifact("test", "1", "https://example.test/a", "0" * 64, "a.bin")
    with pytest.raises(ArtifactVerificationError):
        download_verified(artifact, tmp_path, lambda *_: None, Event(), opener=fake_opener(b"wrong"))
    assert not (tmp_path / "a.bin").exists()
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_setup_foundation.py -v`
Expected: collection fails because `redpath_setup` is missing.

- [ ] **Step 3: Implement standard-library streaming download**

Use `urllib.request.urlopen`, `hashlib.sha256`, `tempfile.NamedTemporaryFile`, and `os.replace`. Read in 1 MiB chunks, check `cancelled.is_set()` between chunks, cap redirects to HTTPS destinations, delete partial files on every failure, and compare checksums with `hmac.compare_digest`. Use a Pydantic strict `SetupStage` model for component status responses.

- [ ] **Step 4: Run focused tests**

Run: `python -m pytest tests/test_setup_foundation.py -v`
Expected: checksum, cancellation, HTTPS, and progress tests pass.

- [ ] **Step 5: Commit the slice**

```powershell
git add redpath_setup tests/test_setup_foundation.py
git commit -m "feat: add verified setup artifact foundation"
```

---

### Task 3: Ollama detection, installation, and model setup

**Files:**
- Create: `redpath_setup/ollama.py`
- Modify: `redpath_ai/providers.py`
- Test: `tests/test_ollama_setup.py`

**Interfaces:**
- Produces: `OllamaSetup.inspect() -> SetupStage`
- Produces: `OllamaSetup.install(consent: bool, progress, cancelled) -> SetupStage`
- Produces: `OllamaSetup.pull_model(consent: bool, progress, cancelled) -> SetupStage`
- Consumes: `OLLAMA_ARTIFACT`, `download_verified`, existing `OllamaProvider.health()`
- Runs only fixed argv: `OllamaSetup.exe /VERYSILENT /NORESTART` and `ollama pull qwen2.5:7b-instruct-q4_K_M`

- [ ] **Step 1: Write failing consent, checksum, argv, and health tests**

```python
def test_ollama_install_requires_consent(tmp_path):
    setup = OllamaSetup(tmp_path, runner=RecordingRunner(), downloader=recording_download)
    stage = setup.install(False, lambda *_: None, Event())
    assert stage.code == "CONSENT_REQUIRED"
    assert setup.runner.calls == []


def test_model_pull_uses_exact_model_name(tmp_path):
    runner = RecordingRunner(exit_code=0)
    stage = OllamaSetup(tmp_path, runner=runner).pull_model(True, lambda *_: None, Event())
    assert runner.calls[-1] == ["ollama", "pull", "qwen2.5:7b-instruct-q4_K_M"]
    assert stage.status == "ready"
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_ollama_setup.py -v`
Expected: collection fails because `redpath_setup.ollama` is missing.

- [ ] **Step 3: Implement the minimal Ollama setup service**

Use injected downloader and subprocess runner interfaces. Never invoke PowerShell downloaded scripts. Verify the official installer before running it, enforce a ten-minute install timeout and bounded output, then re-run `inspect()`. Pull only the configured model and confirm it through the loopback `/api/tags` response. Map failures to stable codes without returning installer or model output.

- [ ] **Step 4: Run Ollama and provider tests**

Run: `python -m pytest tests/test_ollama_setup.py tests/test_redpath_ai.py -v`
Expected: all selected tests pass with no network access from tests.

- [ ] **Step 5: Commit the slice**

```powershell
git add redpath_setup/ollama.py redpath_ai/providers.py tests/test_ollama_setup.py
git commit -m "feat: configure pinned local Ollama runtime"
```

---

### Task 4: WSL2 and managed Kali setup

**Files:**
- Create: `redpath_setup/wsl.py`
- Test: `tests/test_wsl_setup.py`

**Interfaces:**
- Produces: `WslSetup.inspect() -> SetupStage`
- Produces: `WslSetup.enable(consent: bool) -> SetupStage`
- Produces: `WslSetup.install_kali(consent: bool, progress, cancelled) -> SetupStage`
- Produces: `WslSetup.run_in_kali(arguments: Sequence[str], timeout: float) -> ProcessResult`
- Fixed host argv: `wsl.exe --status`, `wsl.exe --list --quiet`, `wsl.exe --install --no-distribution`, `wsl.exe --import RedPath-Kali <location> <verified-file> --version 2`, and `wsl.exe --distribution RedPath-Kali --exec <argv>`

- [ ] **Step 1: Write failing WSL command and identity tests**

```python
def test_kali_import_uses_managed_name_and_verified_artifact(tmp_path):
    runner = RecordingRunner()
    setup = WslSetup(tmp_path, runner=runner, downloader=verified_kali_download)
    setup.install_kali(True, lambda *_: None, Event())
    assert runner.calls[-1][:3] == ["wsl.exe", "--import", "RedPath-Kali"]
    assert runner.calls[-1][-2:] == ["--version", "2"]


def test_run_rejects_another_distribution(tmp_path):
    setup = WslSetup(tmp_path, runner=RecordingRunner())
    result = setup.run_in_kali(["printf", "ok"], timeout=5)
    assert result.argv[:4] == ["wsl.exe", "--distribution", "RedPath-Kali", "--exec"]
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_wsl_setup.py -v`
Expected: collection fails because `redpath_setup.wsl` is missing.

- [ ] **Step 3: Implement WSL setup using fixed argument arrays**

Use `subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=...)`. Normalize `wsl.exe --list --quiet` output and require an exact case-insensitive `RedPath-Kali` match. `enable()` requires consent and returns `RESTART_REQUIRED` when Windows reports a pending restart. `install_kali()` verifies the pinned Kali artifact before import and refuses an existing distribution whose marker file `/etc/redpath-managed` is absent. Do not implement unregister or deletion.

- [ ] **Step 4: Run WSL tests and existing Windows VM safeguards**

Run: `python -m pytest tests/test_wsl_setup.py tests/test_kali_vm.py -v`
Run: `powershell -NoProfile -ExecutionPolicy Bypass -File tests/Test-KaliVM.ps1`
Expected: all Python and PowerShell checks pass without changing the host's WSL state.

- [ ] **Step 5: Commit the slice**

```powershell
git add redpath_setup/wsl.py tests/test_wsl_setup.py
git commit -m "feat: manage isolated Kali through WSL2"
```

---

### Task 5: Setup API, health, and WSL fixed-action dispatch

**Files:**
- Create: `redpath/setup_api.py`
- Create: `redpath_kali/wsl_actions.py`
- Modify: `redpath/app.py`
- Modify: `redpath/contracts.py`
- Modify: `redpath/execution_api.py`
- Test: `tests/test_setup_api.py`
- Test: `tests/test_wsl_actions.py`

**Interfaces:**
- Adds: `GET /api/v1/setup`
- Adds: `GET /api/v1/diagnostics`, returning only application versions, component states, data path, and stable error codes
- Adds: `POST /api/v1/setup/{component}/repair` with strict body `{consent: true}` and components `ollama`, `model`, `wsl`, `kali`
- Adds: `POST /api/v1/setup/{component}/cancel`
- Produces: `WSLActionDispatcher.dispatch(action_name, arguments, *, authorized_target_id, authorized_target_address) -> ActionResult`
- Preserves: bodyless `POST /api/v1/sessions/{session_id}/proposals/{proposal_id}/run`

- [ ] **Step 1: Write failing setup API and closed-world WSL dispatcher tests**

```python
def test_setup_repair_rejects_unknown_component(client):
    response = client.post("/api/v1/setup/shell/repair", json={"consent": True})
    assert response.status_code == 404


def test_diagnostics_exclude_raw_component_output(client):
    payload = client.get("/api/v1/diagnostics").json()
    assert set(payload) == {"version", "components", "data_path", "codes"}
    assert "output" not in str(payload).lower()


def test_wsl_dispatcher_builds_fixed_http_command():
    runner = RecordingWslRunner()
    dispatcher = WSLActionDispatcher(runner)
    dispatcher.dispatch("inspect_http_headers", {"target_id": "t1", "port": 80}, authorized_target_id="t1", authorized_target_address="192.168.56.20")
    assert runner.arguments == ["curl", "--head", "--max-time", "10", "http://192.168.56.20:80/"]
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_setup_api.py tests/test_wsl_actions.py -v`
Expected: setup routes return 404 and `WSLActionDispatcher` is missing.

- [ ] **Step 3: Implement setup routing and reuse the fixed action registry**

Keep the API orchestration synchronous for the MVP and allow only one setup operation at a time through a process-local lock. Store cancellation events by the four fixed component names. Adapt the existing action validation and bounded `ActionResult` shape; replace only the transport layer with `WslSetup.run_in_kali`. Do not duplicate action schemas or accept command strings from the API.

- [ ] **Step 4: Run setup, execution, authorization, and dispatcher suites**

Run: `python -m pytest tests/test_setup_api.py tests/test_wsl_actions.py tests/test_execution_api.py tests/test_execution_fencing.py tests/test_kali_actions.py -v`
Expected: all selected tests pass; arbitrary action, target, component, body, and distribution inputs fail closed.

- [ ] **Step 5: Commit the slice**

```powershell
git add redpath/setup_api.py redpath_kali/wsl_actions.py redpath/app.py redpath/contracts.py redpath/execution_api.py tests/test_setup_api.py tests/test_wsl_actions.py
git commit -m "feat: connect setup and fixed actions to WSL2"
```

---

### Task 6: Complete desktop frontend workflow

**Files:**
- Create: `frontend/setup.js`
- Modify: `frontend/api.js`
- Modify: `frontend/app.js`
- Modify: `frontend/index.html`
- Modify: `frontend/styles.css`
- Modify: `frontend/recommendation.js`
- Test: `frontend/tests/setup.test.js`
- Test: `frontend/tests/api.test.js`
- Test: `frontend/tests/markup.test.js`
- Test: `frontend/tests/recommendation.test.js`

**Interfaces:**
- Adds client methods: `getSetup()`, `repairSetup(component)`, `cancelSetup(component)`, `getDiagnostics()`, `runProposal(sessionId, proposalId)`
- Produces: `SetupController({api, onChange})` with `refresh()`, `repair(component)`, and `cancel(component)`
- Adds a Run button only for an unexpired approved proposal when emergency stop is confirmed inactive

- [ ] **Step 1: Write failing setup and run-control tests**

```javascript
test("setup exposes only fixed repair components", async () => {
  const controller = new SetupController({ api: recordingApi });
  await assert.rejects(controller.repair("shell"), /unavailable/i);
  await controller.repair("kali");
  assert.deepEqual(recordingApi.repairs, ["kali"]);
});

test("run remains disabled until approval and clear stop are confirmed", () => {
  renderProposalState(elements, approvedState, true);
  assert.equal(elements.run.disabled, true);
  renderProposalState(elements, approvedState, false);
  assert.equal(elements.run.disabled, false);
});
```

- [ ] **Step 2: Verify RED**

Run: `node --test frontend/tests/*.test.js`
Expected: setup module import, setup markup, API methods, and run-control assertions fail.

- [ ] **Step 3: Implement the smallest accessible setup and execution UI**

Use the existing single-page shell rather than adding a frontend framework or router. Add semantic sections for Setup, Dashboard, Lab, Approval, Results, Report, and Settings. Render all backend values through `textContent` after strict normalization. Require a native confirmation dialog before repair downloads and before the exact approved action runs. Display `execution_notice` beside emergency-stop controls.

- [ ] **Step 4: Run all frontend tests**

Run: `node --test frontend/tests/*.test.js`
Expected: every frontend test passes with no execution control exposed before approval.

- [ ] **Step 5: Commit the slice**

```powershell
git add frontend
git commit -m "feat: complete guided desktop lab workflow"
```

---

### Task 7: Native desktop host and reproducible executable

**Files:**
- Create: `redpath/desktop.py`
- Create: `packaging/redpath.spec`
- Create: `scripts/build-desktop.ps1`
- Modify: `pyproject.toml`
- Test: `tests/test_desktop.py`
- Test: `tests/Test-DesktopBuild.ps1`

**Interfaces:**
- Produces: `find_loopback_port() -> int`
- Produces: `DesktopHost.start() -> str`, returning the loopback URL after health succeeds
- Produces: `DesktopHost.stop() -> None`
- Adds script: `redpath-desktop = "redpath.desktop:main"`
- Build output: `dist/RedPath/RedPath.exe`

- [ ] **Step 1: Write failing host lifecycle and build-definition tests**

```python
def test_desktop_host_starts_loopback_and_stops_server():
    server = FakeServer()
    host = DesktopHost(server_factory=lambda app, port: server, health_probe=lambda _: True)
    url = host.start()
    assert url.startswith("http://127.0.0.1:")
    host.stop()
    assert server.stopped


def test_desktop_rejects_non_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    with pytest.raises(DesktopStartupError, match="Windows 11"):
        desktop.main()
```

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_desktop.py -v`
Expected: collection fails because `redpath.desktop` is missing.

- [ ] **Step 3: Implement the host and minimal packaging configuration**

Run Uvicorn in a non-daemon thread with one worker, probe `/api/v1/health` for at most 15 seconds, and call `webview.create_window("RedPath", url, width=1280, height=820, min_size=(960, 640))`. Always stop and join the server thread in `finally`. Pin `pywebview==6.2.1` and `pyinstaller==6.22.2` in the desktop optional dependency group. Include `frontend`, no console window, and the package modules in `packaging/redpath.spec`.

- [ ] **Step 4: Run host tests and build the executable**

Run: `python -m pytest tests/test_desktop.py -v`
Run: `powershell -NoProfile -ExecutionPolicy Bypass -File tests/Test-DesktopBuild.ps1`
Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-desktop.ps1`
Expected: tests pass. If PyInstaller is installed, `dist/RedPath/RedPath.exe` exists and launches the health endpoint; otherwise the build script exits with a stable instruction to install `.[desktop]` and is recorded as an unavailable external build prerequisite.

- [ ] **Step 5: Commit the slice**

```powershell
git add redpath/desktop.py packaging/redpath.spec scripts/build-desktop.ps1 pyproject.toml tests/test_desktop.py tests/Test-DesktopBuild.ps1
git commit -m "feat: package RedPath in a native desktop window"
```

---

### Task 8: Windows installer, end-to-end proof, and user guide

**Files:**
- Create: `packaging/RedPath.iss`
- Create: `scripts/build-installer.ps1`
- Create: `tests/test_desktop_workflow.py`
- Create: `tests/Test-Installer.ps1`
- Create: `docs/INSTALL_WINDOWS.md`
- Create: `docs/MVP_RELEASE_CHECKLIST.md`
- Modify: `README.md`

**Interfaces:**
- Build output: `dist/installer/RedPath-Setup-0.1.0-x64.exe`
- End-to-end test drives: setup status -> session -> lesson -> target -> scan import -> recommendation -> approval -> execution -> audit -> report using injected Ollama, WSL, and action fakes
- Installer preserves `%LOCALAPPDATA%\RedPath`, Ollama models, and `RedPath-Kali` by default during uninstall

- [ ] **Step 1: Write failing end-to-end and installer-policy tests**

```python
def test_complete_authorized_workflow(desktop_client, fake_setup, fake_wsl_dispatcher):
    session = create_authorized_session(desktop_client)
    import_fixture_scan(desktop_client, session["id"], "tests/fixtures/nmap_sample.xml")
    proposal = desktop_client.post(f"/api/v1/sessions/{session['id']}/recommendation").json()["proposal"]
    desktop_client.post(f"/api/v1/sessions/{session['id']}/proposals/{proposal['id']}/approve").raise_for_status()
    result = desktop_client.post(f"/api/v1/sessions/{session['id']}/proposals/{proposal['id']}/run")
    assert result.status_code == 200
    assert desktop_client.get(f"/api/v1/sessions/{session['id']}/report").json()["execution_authorized"] is False
```

`tests/Test-Installer.ps1` must assert that the installer targets x64, creates a Start menu shortcut, launches first-run setup, does not mention VirtualBox, and does not unregister WSL or delete `%LOCALAPPDATA%\RedPath` during default uninstall.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_desktop_workflow.py -v`
Run: `powershell -NoProfile -ExecutionPolicy Bypass -File tests/Test-Installer.ps1`
Expected: workflow fixture helpers and installer definition are missing.

- [ ] **Step 3: Implement the minimal installer and documentation**

Use Inno Setup per-user installation, x64 architecture checks, Start menu and optional desktop icons, and no destructive uninstall hooks. The installer launches RedPath; the in-app consent flow performs verified Ollama and Kali downloads. Document Windows 11 x64, internet, administrator prompts for WSL2, possible restart, model and Kali download sizes, authorized-use limits, repair steps, and unsigned-development-build warnings.

- [ ] **Step 4: Run complete automated verification and available builds**

Run: `python -m pytest`
Run: `node --test frontend/tests/*.test.js`
Run: `powershell -NoProfile -ExecutionPolicy Bypass -File tests/Test-KaliVM.ps1`
Run: `powershell -NoProfile -ExecutionPolicy Bypass -File tests/Test-DesktopBuild.ps1`
Run: `powershell -NoProfile -ExecutionPolicy Bypass -File tests/Test-Installer.ps1`
Run: `python -m compileall -q redpath redpath_ai redpath_kali redpath_setup scanner`
Run: `git diff --check`
Expected: all automated tests and static checks pass. Build commands either create their named artifacts or report the exact missing local build tool without claiming an artifact exists.

- [ ] **Step 5: Record manual release gates**

In `docs/MVP_RELEASE_CHECKLIST.md`, record each clean Windows 11 check as `verified`, `failed`, or `not run`: installer launch, Ollama consent/install, model pull, WSL enable/restart, Kali import, native window, authorized lab workflow, emergency stop, repair, uninstall preservation, executable SHA-256, signing status, and artifact paths.

- [ ] **Step 6: Commit the slice**

```powershell
git add packaging/RedPath.iss scripts/build-installer.ps1 tests/test_desktop_workflow.py tests/Test-Installer.ps1 docs/INSTALL_WINDOWS.md docs/MVP_RELEASE_CHECKLIST.md README.md
git commit -m "feat: add Windows MVP installer and release checks"
```

---

## Final review and handoff

- [ ] Run Ponytail's whole-branch review and remove any dependency, wrapper, duplicate schema, or speculative setting that does not directly support the acceptance criteria.
- [ ] Run a security review focused on download verification, subprocess argument construction, WSL distribution identity, loopback binding, approval reuse, emergency-stop ordering, target rebinding, output redaction, and uninstall preservation.
- [ ] Run the complete verification commands from Task 8 again after review fixes.
- [ ] Compare every MVP acceptance criterion in the specification to automated or manual evidence in `docs/MVP_RELEASE_CHECKLIST.md`.
- [ ] Use `superpowers:finishing-a-development-branch` to present merge, push, or PR options; do not publish automatically.
