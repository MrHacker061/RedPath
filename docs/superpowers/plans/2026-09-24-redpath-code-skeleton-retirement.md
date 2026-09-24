# RedPath Code Skeleton and VM Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the repository's Vagrant/VirtualBox implementation and add only typed, fail-closed integration seams for the planned desktop/Compose/Kali/Ollama architecture.

**Architecture:** Keep today's backend, frontend, scanner, AI prototype, and data contracts working. New functions are importable placeholders with no side effects or live routes. Remove the legacy VM files only after proving no retained consumer imports them; update current documentation to state the temporary Kali capability gap.

**Tech Stack:** Python 3.11+, pytest, existing FastAPI/Pydantic, static frontend; Markdown documentation.

**Spec:** `docs/superpowers/specs/2026-09-24-redpath-code-skeleton-retirement-design.md`

## Global Constraints

- Delete repository files only. Do not touch installed VirtualBox/Vagrant, a running VM, its disk, or user runtime state.
- Do not add Compose YAML, Dockerfiles, a desktop framework, SSH code, Ollama calls, executable checks, new routes, or frontend controls in this slice.
- Preserve all existing non-VM behavior and tests. Keep model output untrusted and AI out of learner terminals.
- New functions must be typed and must raise `NotImplementedError` before any side effect. Do not return fake success.
- Preserve unrelated untracked work and dated historical decisions. Do not commit, push, merge, release, or modify GitLab without separate authorization.

## Review Focus

1. A new function might appear operational: a test must assert it raises, and current README must call it a placeholder.
2. An old VM import might survive deletion: search all retained Python, JS, tests, package metadata, and live docs before/after removal.
3. A guide may link to deleted files: run a local Markdown link check and remove current-facing links to `LEGACY_VM.md`.
4. Deleting the VM leaves no Kali runtime: state this in README/architecture rather than claiming an MVP.
5. A `run_approved_check` signature might imply authorization is complete: keep it unexported from live routes and document that real execution will require session/target/approval revalidation.

## File map

| Area | Action |
| --- | --- |
| `redpath_desktop/__init__.py`, `redpath_desktop/launcher.py` | Add native-launcher/Compose function signatures; no Docker calls. |
| `redpath_kali/__init__.py`, `redpath_kali/terminal.py` | Replace VM exports with Kali-container terminal signatures. |
| `redpath_ai/compose.py` | Add selected-model and private-Ollama connection signature; keep current provider. |
| `redpath/checks.py` | Add fixed-check boundary signature; no execution. |
| `tests/test_integration_seams.py` | Prove every placeholder fails closed and exposes typed signatures. |
| `vm/*`, `redpath_kali/vm.py`, VM-only tests, `docs/LEGACY_VM.md` | Delete exact approved legacy files after inventory. |
| README, canonical docs, redirect docs, `AGENTS.md` | Remove dead links and describe present capability gap and placeholders. |
| Historical capstone/task/spec/plan files | Keep with existing historical labels; do not erase teammate assignments or past decisions. |

---

### Task 1: Add minimal, fail-closed integration seams

**Files:** Create `redpath_desktop/__init__.py`, `redpath_desktop/launcher.py`, `redpath_kali/terminal.py`, `redpath_ai/compose.py`, `redpath/checks.py`, `tests/test_integration_seams.py`; modify `redpath_kali/__init__.py`.

**Interfaces:**

- `redpath_desktop.launcher`: `check_prerequisites() -> None`, `start_stack() -> None`, `stop_stack() -> None`, `service_health() -> dict[str, str]`.
- `redpath_kali.terminal`: `open_terminal(session_id: str) -> str`, `resize_terminal(terminal_id: str, columns: int, rows: int) -> None`, `close_terminal(terminal_id: str) -> None`.
- `redpath_ai.compose`: `MODEL_SOURCE: str`, `connect_ollama() -> None`.
- `redpath.checks`: `run_approved_check(proposal: ValidatedProposal, *, approved_protected_hash: str) -> ActionResultContract`. It never executes in this slice.

- [ ] **Step 1:** Baseline: run `python -m pytest`; record count and failures without altering user files.
- [ ] **Step 2:** Write one `tests/test_integration_seams.py` test importing all functions and calling each in `pytest.raises(NotImplementedError)`. Assert `MODEL_SOURCE == "hf.co/IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated:Q4_K_M"`; inspect `typing.get_type_hints` for a return annotation on every function. For `run_approved_check`, use a `ValidatedProposal.model_construct(...)` test value and a hash string; no check may run.
- [ ] **Step 3:** Run `python -m pytest tests/test_integration_seams.py -q`; it must fail from missing imports before implementation.
- [ ] **Step 4:** Add only the specified signatures in the mapped files, each with a one-line `raise NotImplementedError("<component> is not implemented")`. Add minimal module docstrings. Replace `redpath_kali/__init__.py` VM exports with terminal function exports; do not add adapters, clients, factories, or exception classes.
- [ ] **Step 5:** Re-run the focused test and existing `tests/test_redpath_ai.py`, `tests/test_backend_foundation.py`, and `tests/test_session_api.py`. The current app must still start/import and keep its existing routes.

### Task 2: Retire the exact legacy VM implementation

**Files:** Delete `vm/Vagrantfile`, `vm/Open-Kali-Terminal.cmd`, `vm/KaliVM.ps1`, `vm/KaliVM.cmd`, `vm/kali-vm.json`, `vm/scripts/provision.sh`, `redpath_kali/vm.py`, `tests/test_kali_vm.py`, `tests/Test-KaliVM.ps1`, `docs/LEGACY_VM.md`.

**Interfaces:** No new interface. Retained code must not import removed paths.

- [ ] **Step 1:** Run `git status --short` and `git ls-files vm redpath_kali tests docs/LEGACY_VM.md`; verify each target path is within this repository and whether it is tracked or user-untracked. Inspect `vm/` for ignored generated state; never recursively delete the directory or state.
- [ ] **Step 2:** Search `rg -n 'redpath_kali\.vm|KaliVM|Vagrantfile|LEGACY_VM|vm/' redpath redpath_ai redpath_kali scanner frontend tests pyproject.toml README.md docs AGENTS.md` and classify retained imports versus historical prose. If a production consumer exists, stop and revise migration before deleting.
- [ ] **Step 3:** Delete only the exact source/test/guide paths listed above using `apply_patch`. Do not run `Remove-Item -Recurse` or clean ignored `.vagrant` state.
- [ ] **Step 4:** Run `python -m pytest`; expect only the remaining non-VM suite and record its count. Any failure from a retained consumer is a migration defect, not a reason to restore unused VM scaffolding blindly.

### Task 3: Update current-facing docs and verify the whole change

**Files:** Modify `README.md`, `AGENTS.md`, `docs/REDPATH_ARCHITECTURE.md`, `docs/REDPATH_CONTRACTS.md`, `docs/REDPATH_CONTAINER_FLOW.md`, `docs/OLLAMA_SETUP.md`, `docs/REDPATH_SYSTEM_MAP.md`, `docs/REDPATH_PROJECT_CONNECTIONS.md`; inspect `docs/REDPATH_CONTEXT.md`, `docs/REDPATH_IMPLEMENTATION_TASKS.md`, `tasks/plan.md`, dated spec/plan files as historical records.

**Interfaces:** README/canonical docs tell developers which imports are placeholders, what still works, and what no longer runs.

- [ ] **Step 1:** Replace README's Windows VM claim and guide link with an honest note: VM code has been removed; no Kali runtime, native desktop, Compose stack, or selected-model integration exists yet. Keep `python -m pip install -r requirements.txt` and `python -m pytest`.
- [ ] **Step 2:** Update architecture/contracts/container flow/Ollama docs to reflect the removed VM, new placeholder module names, and retained current loopback provider. Remove links to `LEGACY_VM.md` from redirect stubs. Keep planned-vs-current status prominent. Update AGENTS file organization to name the Kali-container integration boundary.
- [ ] **Step 3:** Leave historical team assignments and dated specs/plans intact, but ensure their top notices indicate historical status or supersession where they refer to removed code. Do not silently rewrite GitLab-linked estimates.
- [ ] **Step 4:** Run full `python -m pytest` and `npm test --prefix frontend` if Node is available; verify `python -c "import redpath, redpath_ai, redpath_kali, redpath_desktop"`. Run `git diff --check`, `git status --short`, and a local relative Markdown-link checker. Search current-facing files for dangling `LEGACY_VM`, `KaliVM`, `Vagrantfile`, and `redpath_kali.vm` references.
- [ ] **Step 5:** Review the final diff for only approved exact-path deletions, typed no-op-free placeholders, and no secret/runtime-state removal. Report the temporary capability gap, test output, and no commit/push/release.
