# RedPath Release-Ready MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and locally verify an unsigned Windows RedPath installer whose default recommendation provider is the configured loopback-only Ollama model and whose setup UI discloses pinned download sizes before consent.

**Architecture:** Reuse `OllamaProvider`, the existing setup response, and the current PyInstaller/Inno Setup pipeline. Add size metadata directly to the existing artifact and setup contracts, render it in the existing component cards, and retain the deterministic provider fallback and all authorization gates.

**Tech Stack:** Python 3.14, FastAPI/Pydantic, vanilla JavaScript, Node test runner, PyInstaller 6.22.2, pywebview 6.2.1, Inno Setup 6.3+

**Spec:** `docs/superpowers/specs/2026-09-12-release-ready-mvp-design.md`

## Global Constraints

- Windows 11 x64 only; the installer remains per-user and unsigned.
- Ollama stays restricted to `http://127.0.0.1:11434` and falls back to `RuleBasedProvider` on unavailable or invalid output.
- No cloud models, arbitrary tools, exploitation, credential testing, reverse shells, or public-target support.
- Setup downloads remain consent-gated, HTTPS-only, version-pinned, and SHA-256 verified.
- Build prerequisites may be installed on this development host but are not end-user runtime prerequisites.
- Do not upload, publish, sign, or delete preserved RedPath, Ollama, or `RedPath-Kali` data.

## File Map

- `redpath/app.py`: application-level default provider selection.
- `redpath_setup/manifest.py`: immutable artifact version, hash, and byte-size metadata.
- `redpath_setup/downloads.py`: verified artifact transfer and exact completed-size check.
- `redpath/contracts.py`: bounded setup metadata returned to the desktop frontend.
- `redpath/setup_api.py`: component-to-download metadata mapping.
- `frontend/setup.js`: setup response validation and literal size formatting.
- `frontend/app.js`: existing setup-card rendering.
- `docs/MVP_RELEASE_CHECKLIST.md`, `docs/INSTALL_WINDOWS.md`: source-bound release evidence and limitations.
- Existing tests mirror each changed module; no new framework or helper layer is needed.

---

### Task 1: Select Ollama by Default

**Files:**
- Modify: `redpath/app.py`
- Modify: `tests/test_recommendation_api.py`

**Interfaces:**
- Consumes: `OllamaProvider(model=OLLAMA_MODEL, fallback=RuleBasedProvider())`
- Produces: `app.state.llm_provider: OllamaProvider`

- [ ] **Step 1: Replace the old default-provider assertion with a failing Ollama assertion**

```python
def test_application_defaults_to_loopback_ollama_provider(app):
    provider = app.state.llm_provider
    assert isinstance(provider, OllamaProvider)
    assert provider.base_url == "http://127.0.0.1:11434"
    assert isinstance(provider.fallback, RuleBasedProvider)
```

- [ ] **Step 2: Run the focused test and verify it fails because the application still selects `RuleBasedProvider`**

Run: `python -m pytest tests/test_recommendation_api.py::test_application_defaults_to_loopback_ollama_provider -q`

- [ ] **Step 3: Make the smallest provider-selection change**

```python
from redpath_ai import OllamaProvider

app.state.llm_provider = OllamaProvider()
```

- [ ] **Step 4: Run provider and recommendation tests**

Run: `python -m pytest tests/test_redpath_ai.py tests/test_recommendation_api.py tests/test_desktop_workflow.py -q`
Expected: all pass without contacting a real model because networked paths remain injected or replaced in tests.

- [ ] **Step 5: Commit**

```powershell
git add redpath/app.py tests/test_recommendation_api.py
git commit -m "feat: use local Ollama provider by default"
```

### Task 2: Bind Exact Download Sizes to Pinned Inputs

**Files:**
- Modify: `redpath_setup/manifest.py`
- Modify: `redpath_setup/downloads.py`
- Modify: `tests/test_setup_foundation.py`
- Modify: `tests/test_download_limits.py`

**Interfaces:**
- Produces: `Artifact.size_bytes: int`
- Pinned sizes: Ollama installer `1_574_272_976`; Kali WSL image `247_857_686`; Ollama model transfer `4_683_087_332` bytes from the model manifest's config and layer sizes.

- [ ] **Step 1: Add failing artifact validation and downloader mismatch tests**

```python
def test_artifact_requires_positive_exact_size():
    with pytest.raises(ValueError, match="size"):
        Artifact("x", "1", "https://example.test/x", "0" * 64, "x.bin", 0)

def test_download_rejects_body_that_does_not_match_pinned_size(tmp_path):
    fixed = Artifact("x", "1", "https://example.test/x", hashlib.sha256(b"abc").hexdigest(), "x.bin", 4)
    with pytest.raises(ArtifactVerificationError, match="size"):
        download_verified(fixed, tmp_path, lambda *_: None, Event(), opener_for(b"abc"))
```

- [ ] **Step 2: Run focused tests and verify both fail**

Run: `python -m pytest tests/test_setup_foundation.py tests/test_download_limits.py -q`

- [ ] **Step 3: Add the required manifest field and pinned values**

```python
@dataclass(frozen=True, slots=True)
class Artifact:
    name: str
    version: str
    url: str
    sha256: str
    filename: str
    size_bytes: int

    def __post_init__(self) -> None:
        # existing checks remain
        if self.size_bytes <= 0:
            raise ValueError("artifact size must be positive")
```

Set `OLLAMA_ARTIFACT.size_bytes = 1_574_272_976` and `KALI_ARTIFACT.size_bytes = 247_857_686`.

- [ ] **Step 4: Reject a completed transfer before publishing it when its byte count differs**

Immediately before the existing SHA-256 comparison/atomic publish, compare the accumulated completed-byte count with `artifact.size_bytes` and raise `ArtifactVerificationError("size mismatch for ...")`.

- [ ] **Step 5: Update existing test-only `Artifact(...)` constructors with the exact body length and run focused tests**

Run: `python -m pytest tests/test_setup_foundation.py tests/test_download_limits.py tests/test_ollama_setup.py tests/test_wsl_setup.py -q`

- [ ] **Step 6: Commit**

```powershell
git add redpath_setup/manifest.py redpath_setup/downloads.py tests/test_setup_foundation.py tests/test_download_limits.py tests/test_ollama_setup.py tests/test_wsl_setup.py
git commit -m "feat: verify pinned setup download sizes"
```

### Task 3: Disclose Downloads Before Consent

**Files:**
- Modify: `redpath/contracts.py`
- Modify: `redpath/setup_api.py`
- Modify: `frontend/setup.js`
- Modify: `frontend/app.js`
- Modify: `frontend/index.html` only if the existing setup card lacks a reusable detail element
- Modify: `tests/test_setup_api.py`
- Modify: `frontend/tests/setup.test.js`
- Modify: `frontend/tests/markup.test.js` only if markup changes

**Interfaces:**
- Produces per component: `version: str | None`, `download_size_bytes: int | None`
- Values: Ollama from `OLLAMA_ARTIFACT`, model `OLLAMA_MODEL` and `4_683_087_332`, Kali from `KALI_ARTIFACT`, WSL `None`/`None`.

- [ ] **Step 1: Add a failing setup API contract test**

```python
def test_setup_discloses_pinned_downloads_before_consent(client):
    components = client.get("/api/v1/setup").json()["components"]
    assert components["ollama"]["download_size_bytes"] == 1_574_272_976
    assert components["model"]["download_size_bytes"] == 4_683_087_332
    assert components["kali"]["download_size_bytes"] == 247_857_686
    assert components["wsl"]["download_size_bytes"] is None
```

- [ ] **Step 2: Add a failing frontend normalization/formatting test**

```javascript
test("setup keeps only bounded pinned download metadata", () => {
  const setup = normalizeSetup(validSetupPayload());
  assert.equal(setup.components.ollama.downloadSizeBytes, 1574272976);
  assert.equal(setup.components.model.version, "qwen2.5:7b-instruct-q4_K_M");
});

test("download sizes use a readable binary unit", () => {
  assert.equal(formatDownloadSize(1574272976), "1.47 GiB");
});
```

- [ ] **Step 3: Run focused backend and frontend tests and verify they fail**

Run: `python -m pytest tests/test_setup_api.py -q`

Run: `node --test frontend/tests/setup.test.js`

- [ ] **Step 4: Extend the existing strict contract without adding another response type**

```python
class SetupComponentStatus(StrictModel):
    status: Literal["ready", "needs_attention", "in_progress", "failed"]
    code: str = Field(min_length=1, max_length=80)
    detail: str = Field(max_length=500)
    version: str | None = Field(default=None, max_length=80)
    download_size_bytes: int | None = Field(default=None, ge=1)
```

Have `_as_status()` attach the fixed metadata by component name; do not accept metadata from setup subprocess output.

- [ ] **Step 5: Validate and render only the two new fields**

`componentStatus()` must accept only a bounded version string or `null`, and a positive safe integer or `null`. Export one `formatDownloadSize(bytes)` function using `bytes / 1024 ** 3` for GiB and `bytes / 1024 ** 2` for MiB. Render `Version · download size` with `textContent` in the existing setup card before the repair button can invoke confirmation.

- [ ] **Step 6: Run focused and full frontend setup tests**

Run: `python -m pytest tests/test_setup_api.py tests/test_setup_foundation.py -q`

Run: `$tests=(Get-ChildItem frontend/tests/*.test.js).FullName; node --test $tests`

- [ ] **Step 7: Commit**

```powershell
git add redpath/contracts.py redpath/setup_api.py frontend/setup.js frontend/app.js frontend/index.html tests/test_setup_api.py frontend/tests/setup.test.js frontend/tests/markup.test.js
git commit -m "feat: disclose setup download sizes"
```

### Task 4: Run Complete Source Verification and Ponytail Review

**Files:**
- Modify only files required by concrete test or review findings.

**Interfaces:**
- Consumes Tasks 1-3 source state.
- Produces a reviewed, buildable source commit.

- [ ] **Step 1: Run all automated suites**

```powershell
python -m pytest -q
$tests=(Get-ChildItem frontend/tests/*.test.js).FullName
node --test $tests
& tests/Test-KaliVM.ps1
& tests/Test-DesktopBuild.ps1
& tests/Test-Installer.ps1
python -m compileall -q redpath redpath_ai redpath_kali redpath_setup scanner
git diff --check
```

- [ ] **Step 2: Review the exact branch diff with Ponytail**

Review `origin/main...HEAD` for dead metadata, duplicate formatting, speculative abstractions, or dependencies. Apply only concrete simplifications that preserve consent, validation, security, and accessibility.

- [ ] **Step 3: Rerun affected tests after review changes and commit only if the review changed source**

```powershell
git add -u
git commit -m "refactor: simplify MVP release path"
```

### Task 5: Build the Desktop Executable and Installer

**Files:**
- Generated, untracked: `build/desktop/**`
- Generated, untracked: `dist/RedPath/**`
- Generated, untracked: `dist/installer/RedPath-Setup-0.1.0-x64.exe`

**Interfaces:**
- Produces: unsigned `RedPath.exe`, unsigned installer, SHA-256 for each.

- [ ] **Step 1: Install only the repository-pinned desktop build extras**

Run: `python -m pip install ".[desktop]"`

Verify: `python -c "import importlib.metadata as m; assert m.version('pyinstaller') == '6.22.2'; assert m.version('pywebview') == '6.2.1'"`

- [ ] **Step 2: Install Inno Setup if `ISCC.exe` is absent**

Run: `winget install --id JRSoftware.InnoSetup --exact --silent --accept-package-agreements --accept-source-agreements`

Verify the resolved compiler reports version 6.3 or newer. Do not add Inno Setup to the application installer.

- [ ] **Step 3: Build the desktop artifact**

Run: `powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-desktop.ps1`

Expected: `dist/RedPath/RedPath.exe` exists and the script prints its SHA-256.

- [ ] **Step 4: Build the installer using the resolved absolute compiler path**

Run:

```powershell
$compiler = (Get-ChildItem "${env:ProgramFiles(x86)}\Inno Setup *\ISCC.exe" -File | Sort-Object FullName | Select-Object -Last 1).FullName
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-installer.ps1 -Compiler $compiler
```

Expected: `dist/installer/RedPath-Setup-0.1.0-x64.exe` exists and the script prints its SHA-256.

- [ ] **Step 5: Record immutable artifact evidence**

```powershell
Get-Item dist/RedPath/RedPath.exe,dist/installer/RedPath-Setup-0.1.0-x64.exe | Select-Object FullName,Length,LastWriteTimeUtc
Get-FileHash dist/RedPath/RedPath.exe,dist/installer/RedPath-Setup-0.1.0-x64.exe -Algorithm SHA256
```

Do not commit generated binaries unless repository policy explicitly tracks release artifacts.

### Task 6: Smoke-Test Installation and Update the Release Record

**Files:**
- Modify: `docs/MVP_RELEASE_CHECKLIST.md`
- Modify: `docs/INSTALL_WINDOWS.md`

**Interfaces:**
- Consumes the exact Task 5 hashes and artifact paths.
- Produces an honest local-machine release decision; clean-machine gates remain unverified unless actually run there.

- [ ] **Step 1: Run the unpackaged executable and verify its bounded local runtime**

Start the exact `dist/RedPath/RedPath.exe` process, capture its PID, wait only until its loopback health endpoint responds, verify no non-loopback listening socket belongs to that PID, then stop only that captured process after the check.

- [ ] **Step 2: Install the generated package silently for the current user**

Run the exact installer with `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-`. Verify `%LOCALAPPDATA%\Programs\RedPath\RedPath.exe` and the Start menu shortcut exist.

- [ ] **Step 3: Smoke-test the installed executable**

Launch the installed executable, verify the local health endpoint and setup response, and confirm the setup response contains Ollama/model/Kali sizes before any repair request. Stop only the captured RedPath process.

- [ ] **Step 4: Verify default uninstall preservation**

Create a harmless sentinel under `%LOCALAPPDATA%\RedPath`, run the generated uninstaller silently, verify packaged files and shortcuts are removed, and verify the sentinel remains. Remove only the test sentinel afterward; do not remove application data, Ollama data, or `RedPath-Kali`.

- [ ] **Step 5: Update documentation with observed evidence**

Replace stale automated-test counts, record both hashes and paths, mark local install/launch/uninstall gates with exact evidence, remove the resolved default-provider and size-disclosure blockers, and leave signing plus separate-clean-machine gates unresolved.

- [ ] **Step 6: Run documentation and source integrity checks**

```powershell
rg -n "RuleBasedProvider directly|Download-size disclosure.*failed|not built|not available" docs/MVP_RELEASE_CHECKLIST.md docs/INSTALL_WINDOWS.md
git diff --check
git status --short
```

- [ ] **Step 7: Commit the release record**

```powershell
git add docs/MVP_RELEASE_CHECKLIST.md docs/INSTALL_WINDOWS.md
git commit -m "docs: record Windows MVP release evidence"
```

### Task 7: Final Verification and Handoff

**Files:**
- No source changes unless a verified failure requires a focused fix and regression test.

- [ ] **Step 1: Rerun the entire automated suite on the final source commit**

Run the same commands from Task 4 and require all applicable checks to pass.

- [ ] **Step 2: Confirm the branch is clean except ignored build artifacts**

Run: `git status --short --branch`

- [ ] **Step 3: Report the exact commit, artifact paths, hashes, test totals, unsigned status, and any unverified clean-machine or real-lab gates**

Do not call the artifact production-ready, signed, published, or clean-machine verified without matching evidence.
