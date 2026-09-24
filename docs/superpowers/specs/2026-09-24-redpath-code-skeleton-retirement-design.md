# RedPath code skeleton and VM retirement

**Status:** Proposed code migration for user review. This supersedes the earlier documentation-only spec where they conflict. It does not describe implemented Compose, SSH, terminal, or AI service behavior.

## Intent and acceptance

Move the repository toward the agreed native desktop + Docker Compose + required Kali architecture without building those features yet. Retire the repository's Windows Vagrant/VirtualBox implementation. Keep the usable FastAPI/SQLite, frontend, evidence, policy, Nmap, scanner, and existing test paths intact. Add only small typed function entry points for future integrations, each failing visibly until implemented. A clean checkout must still install and pass its remaining automated tests.

The user explicitly chose to delete the legacy VM code, VM-only tests, guide, and links, even though no replacement Kali runtime exists yet. This means the current repository will **temporarily have no runnable Kali environment**. This migration does not stop, delete, or uninstall any VM or software outside the repository.

## Exact removal boundary

- Delete tracked `vm/` files: `Vagrantfile`, `Open-Kali-Terminal.cmd`, `KaliVM.ps1`, `KaliVM.cmd`, `kali-vm.json`, and `scripts/provision.sh`.
- Delete `redpath_kali/vm.py` and the old VM-exporting contents of `redpath_kali/__init__.py`. Retain the package name for the new Kali-container integration seam.
- Delete `tests/test_kali_vm.py` and `tests/Test-KaliVM.ps1`; these test only the retired implementation.
- Delete `docs/LEGACY_VM.md`; remove live README/canonical-doc links to it. Do not delete user-generated runtime state, installed VirtualBox/Vagrant software, or an actual VM.
- Preserve prior dated design/plan files as historical decisions, with a superseded notice if needed; do not erase them to make searches look clean. The older team task list is a planning snapshot, not executable code, and its VM assignments need team reconciliation separately.

## Minimal integration seams

1. `redpath_desktop/launcher.py`: typed host-side functions for prerequisite inspection, starting/stopping the planned Compose stack, and health. Functions raise `NotImplementedError` (or one purpose-specific exception) and have no subprocess invocation or Docker side effect. No desktop framework or installer is selected.
2. `redpath_kali/terminal.py`: typed functions for creating, resizing, and closing a learner terminal attached to the same future Kali container. No SSH client, credentials, network call, or AI terminal-write function is added. Functions fail closed.
3. `redpath_ai/compose.py`: typed future connection to private Ollama and the selected Qwen3 4B Q4_K_M model. No model download, inference call, or unvalidated tool dispatcher is added. Current loopback provider remains operational for prototype tests until replaced in a later slice.
4. `redpath/checks.py`: typed boundary for a fixed, approval-bound app-initiated check. It cannot accept an arbitrary command string; it fails closed and does not execute a check. This boundary does not claim to mediate learner-typed Kali shell commands.

These seams are importable contracts, **not** routes or functioning services. Do not wire them into the live FastAPI app or static frontend yet, because that would create a misleading UI or a new failure path. Reuse existing contract types where possible; avoid speculative extra DTOs, registries, factories, or configuration.

## Documentation and configuration migration

- Update `README.md`, `docs/REDPATH_ARCHITECTURE.md`, `docs/REDPATH_CONTRACTS.md`, `docs/REDPATH_CONTAINER_FLOW.md`, `docs/OLLAMA_SETUP.md`, and redirect stubs to say the old VM code has been removed and the new integration seams are placeholders.
- Remove live links to the deleted guide and any command instructions pointing at removed files. Keep older dated capstone/plan records visibly historical rather than silently rewriting teammate assignments.
- Update `AGENTS.md` file organization to describe `redpath_kali` as the planned container boundary instead of the former VM integration.
- Keep `pyproject.toml` packaging and current backend startup working; include the new package only if needed for importability. Do not add Compose YAML, Dockerfiles, desktop framework dependencies, or a downloadable installer in this slice.

## Safety and verification

- Verify no production import or remaining test depends on `redpath_kali.vm` or `vm/` before deletion.
- Verify every new function is typed, importable, and fails without side effects. Test each seam with one small failure-path test or consolidated table-driven test.
- Run `python -m pytest`, frontend tests if Node is available, `git diff --check`, an import/package check, and a repository-relative Markdown link check.
- Review the diff for deleted user-owned/untracked files; leave unrelated untracked work alone. Do not auto-commit, push, merge, or release.

## Known tradeoff

Removing the only working Kali launcher before Compose/Kali is implemented creates a temporary capability gap. This is intentional per the user's explicit deletion decision. The README must state it plainly. The next implementation slice should build a working, private, app-managed Kali connection and two-shell UI before advertising an MVP.
