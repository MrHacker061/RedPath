# RedPath Documentation and Contracts Implementation Plan

**Historical plan:** Superseded by the [code skeleton and VM retirement plan](2026-09-24-redpath-code-skeleton-retirement.md). Do not execute its VM-preservation or legacy-guide steps now.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace contradictory RedPath architecture prose with one accurate target-design source and one set of non-executable interface contracts, while preserving the current prototype and its working instructions.

**Architecture:** Keep the current code untouched. Write the target architecture and contracts first, then redirect or revise older docs to point at them. Keep current behavior and planned behavior visibly separate in every document.

**Tech Stack:** Markdown documentation; existing Python/FastAPI, static frontend, Windows Vagrant prototype; planned native launcher, Docker Compose app/Kali/Ollama stack, and Ollama-hosted Qwen3 4B candidate.

**Spec:** `docs/superpowers/specs/2026-09-24-redpath-documentation-contracts-design.md`

## Global Constraints

- Only Markdown documents may change. Do not create runtime code, Compose YAML, desktop scaffolding, tests, or executable contracts.
- Preserve `vm/`, `redpath_kali/`, existing app modules, tests, and the uncommitted `docs/REDPATH_CONTAINER_FLOW.md` and `tasks/plan.md` until their own planned edit.
- The target product has two user-controlled Kali shells by default, an AI sidebar, a teaching drawer, and app-managed private SSH. The current checkout does not provide these features.
- Kali is required in the target Compose stack. VirtualBox/Vagrant is the existing prototype, not a first-version prerequisite. Kubernetes is out of scope.
- The selected AI candidate is `IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated` Q4_K_M via Ollama. No CPU speed, total RAM floor, model reliability, or redistribution clearance has been verified.
- AI has no direct shell authority. App-initiated checks use fixed actions, exact-target policy, learner approval, and audit; interactive shell use is learner-controlled and cannot be described as fully mediated by that policy.
- Lesson URLs and authorized target addresses remain separate. Evidence labels retain observed/inferred/verified meaning.
- Do not commit, push, merge, release, or alter GitLab; the repository AGENTS.md requires separate authorization for those actions.

## Review Focus

1. A new reader may mistake target design for working software: each canonical doc and README must state current-versus-planned status near the top.
2. A reader may infer a Kali shell command is policy-approved because RedPath displays it: contracts must distinguish interactive user shells from app-initiated checks.
3. Old links may break during consolidation: both superseded docs must remain as small redirect stubs, and README links must resolve.
4. A first-run user may assume Compose installs Docker or a VPN: architecture and setup docs must state host-runtime and lab-VPN prerequisites.
5. A low-end user may assume the selected 2.5 GB model needs only 2.5 GB RAM: AI docs must say file size is not whole-stack memory use and mark performance untested.

## File map

| File | Single responsibility |
| --- | --- |
| `docs/REDPATH_ARCHITECTURE.md` | Canonical target UI, services, boundaries, startup/failure flow, and current-versus-planned inventory. |
| `docs/REDPATH_CONTRACTS.md` | Non-executable component interfaces and invariants, including existing-versus-proposed APIs. |
| `docs/LEGACY_VM.md` | Existing Windows Vagrant/VirtualBox operator instructions extracted from README. |
| `README.md` | Short current-state entrypoint and navigation to target, contract, and legacy docs. |
| `docs/REDPATH_CONTAINER_FLOW.md` | Lucidchart-oriented target diagram, not a second canonical architecture. |
| `docs/OLLAMA_SETUP.md` | Existing host Ollama behavior versus planned Compose model flow. |
| `docs/REDPATH_SYSTEM_MAP.md` and `docs/REDPATH_PROJECT_CONNECTIONS.md` | Short superseded pointers, preserving old link targets. |
| `docs/REDPATH_CONTEXT.md` | Historical capstone context with current-design notice. |
| `docs/REDPATH_IMPLEMENTATION_TASKS.md` and `tasks/plan.md` | Existing team planning with an upfront discrepancy notice, not silently reassigned work. |

---

### Task 1: Canonical target architecture

**Files:**
- Create: `docs/REDPATH_ARCHITECTURE.md`
- Read: `README.md`, `docs/REDPATH_CONTAINER_FLOW.md`, `docs/REDPATH_SYSTEM_MAP.md`, `docs/REDPATH_PROJECT_CONNECTIONS.md`, `docs/superpowers/specs/2026-09-24-redpath-documentation-contracts-design.md`

**Interfaces:**
- Consumes: approved spec and actual source inventory.
- Produces: stable headings for `Current checkout`, `Target experience`, `Target runtime`, `Connections and trust boundaries`, `Startup and failure states`, `Security scope`, and `Open release decisions`.

- [ ] **Step 1:** Write `Current checkout` with the existing FastAPI/SQLite/frontend/Ollama-provider/Nmap/Windows-VM facts and an explicit statement that Compose, native desktop, two-terminal management, and selected-model integration are not implemented.
- [ ] **Step 2:** Write `Target experience` with two same-Kali shells side by side, terminal tabs and resize, right AI sidebar/pop-out, bottom teaching drawer, current lab/authorized target header, and plain-language connecting states.
- [ ] **Step 3:** Write `Target runtime` with native launcher outside Compose, app/Kali/Ollama services inside, app-managed private SSH, persistent app/model data, host Docker runtime, optional platform VPN, and Kubernetes excluded. Describe the restricted app-check runner as a logical boundary with deployment placement undecided.
- [ ] **Step 4:** Write `Connections and trust boundaries` and `Security scope`: lesson URL versus target, Ollama versus app, selected terminal excerpt versus whole shell, learner shell versus approved fixed check, and observed/inferred/verified evidence. State that RedPath policy cannot claim control over every manually entered Kali command.
- [ ] **Step 5:** Write first-run and normal-start sequences and failure states for Docker missing, image pull failure, Kali SSH failure, Ollama unavailable, and model too slow. Do not imply silent installation or a measured hardware floor.
- [ ] **Step 6:** Review the file against the spec's target UI/runtime/AI sections; reject any sentence that presents a planned component as currently running.

### Task 2: Non-executable integration contracts

**Files:**
- Create: `docs/REDPATH_CONTRACTS.md`
- Read: `redpath/contracts.py`, `redpath_ai/schemas.py`, `redpath_ai/providers.py`, `redpath/session_api.py`, `docs/REDPATH_ARCHITECTURE.md`

**Interfaces:**
- Consumes: Task 1's component names and status labels.
- Produces: contract sections named `Launcher and Compose`, `Desktop and app`, `Terminal session`, `AI tools and model`, `Approved check`, and `Evidence and audit`.

- [ ] **Step 1:** List existing endpoint and Python contract names accurately in a short `Already implemented` section. Mark every future interface as `Proposed contract`; do not fabricate a live route or event stream.
- [ ] **Step 2:** Define launcher/Compose ownership: prerequisite check, first-run acquisition, start/stop, health, and user-visible error codes. Specify that only the native launcher can manage Docker; no container gets the host Docker socket.
- [ ] **Step 3:** Define the terminal lifecycle conceptually: `terminal_id`, `session_id`, Kali connection state, create/attach/resize/close, reconnection, bounded selected-output excerpt, and user-only input stream. No AI-to-terminal write method.
- [ ] **Step 4:** Define AI read tools by purpose and minimum fields: current lesson, authorized target summary, normalized findings, learner-selected bounded terminal excerpt, and reviewed learning note. All returns are untrusted context. Define model identity, timeout/unavailable state, schema validation, and no direct action execution.
- [ ] **Step 5:** Define the approved-check proposal and decision boundary by reusing existing `AIProposal`, `PolicyDecisionContract`, and `ActionResultContract` vocabulary where applicable. Include exact session/target/action/arguments/approval/audit and cancellation. Do not conflate this with a learner shell.
- [ ] **Step 6:** Check each proposed field against the architecture. Confirm there is no `execute_command`-style general AI tool, no undocumented host/LAN SSH exposure, and no assertion that model or policy tests have passed.

### Task 3: Make current and planned setup honest

**Files:**
- Create: `docs/LEGACY_VM.md`
- Modify: `README.md`
- Modify: `docs/OLLAMA_SETUP.md`

**Interfaces:**
- Consumes: Task 1 architecture and Task 2 contracts.
- Produces: a short repository landing page, a working legacy guide, and a model setup guide with clear status labels.

- [ ] **Step 1:** Move the VM-specific README material (current commands, file/state locations, troubleshooting, and upstream links) into `docs/LEGACY_VM.md`. Preserve command spelling and current behavior; label it `Existing Windows prototype; not the target installer`.
- [ ] **Step 2:** Rewrite README to identify the current checkout and planned app separately, give the existing `python -m pip install -r requirements.txt` and `python -m pytest` workflow, and link architecture, contracts, Compose diagram, Ollama setup, and legacy VM guide. Do not offer a non-existent desktop download or `docker compose up` as a working command.
- [ ] **Step 3:** Update `docs/OLLAMA_SETUP.md` with an `Existing provider` section that accurately records its current loopback behavior and model setting, followed by a `Planned Compose model` section naming the selected Qwen3 4B Q4_K_M source, online first download, private service path, and untested performance/tool-call caveat. A 2.5 GB model file is not a total RAM estimate.
- [ ] **Step 4:** Compare legacy commands and links against original README and run a link check on README and `docs/LEGACY_VM.md`.

### Task 4: Redirect conflicting diagrams and planning prose

**Files:**
- Modify: `docs/REDPATH_CONTAINER_FLOW.md`
- Modify: `docs/REDPATH_SYSTEM_MAP.md`
- Modify: `docs/REDPATH_PROJECT_CONNECTIONS.md`
- Modify: `docs/REDPATH_CONTEXT.md`
- Modify: `docs/REDPATH_IMPLEMENTATION_TASKS.md`
- Modify: `tasks/plan.md`

**Interfaces:**
- Consumes: canonical Task 1 and Task 2 documents.
- Produces: one consistent current-design navigation path while preserving old document links and team-owned work items.

- [ ] **Step 1:** Update the Lucidchart flow so its boxes are desktop launcher, app, Kali, Ollama, data/model storage, and authorized training target. Draw app-managed private SSH to Kali, read-only AI context to Ollama, and the separate proposal/approval gate. Label target services planned; do not show an extra generic Linux image or optional Kali.
- [ ] **Step 2:** Replace `docs/REDPATH_SYSTEM_MAP.md` and `docs/REDPATH_PROJECT_CONNECTIONS.md` with short superseded stubs linking architecture, contracts, and legacy VM guide. First verify the canonical docs preserve still-useful facts; leave Git history as the detailed historical record.
- [ ] **Step 3:** Add a top notice to `docs/REDPATH_CONTEXT.md` identifying it as capstone background and linking the canonical target design. Leave the personal/coursework narrative intact.
- [ ] **Step 4:** Add a top notice to `docs/REDPATH_IMPLEMENTATION_TASKS.md` and `tasks/plan.md` that the optional-Kali, browser-first, and 7B assumptions are outdated; direct readers to the architecture and contracts. Preserve names, estimates, dates, and external links for the team to reconcile separately.
- [ ] **Step 5:** Search all modified docs for contradictions: `optional Kali`, `VirtualBox prerequisite`, `Windows host only`, `qwen2.5` as selected target model, and `no direct terminal`. Historical or current-prototype mentions are allowed only when labeled as such.

### Task 5: Whole-document verification and handoff

**Files:**
- Review: all files in the file map
- Do not modify: source code, tests, Compose configuration, GitLab, branches, releases

**Interfaces:**
- Consumes: Tasks 1-4.
- Produces: a verifiable doc diff and a concise migration receipt.

- [ ] **Step 1:** Run `git status --short` and `git diff --check`; confirm only the planned Markdown files were changed and pre-existing untracked work remains present.
- [ ] **Step 2:** Check relative Markdown links in every changed document against files in the checkout. Check old README links after redirecting the two superseded docs.
- [ ] **Step 3:** Run `python -m pytest` as a regression check if the environment is ready; if it cannot run, report the exact failure instead of claiming tests pass. Runtime behavior is not expected to change.
- [ ] **Step 4:** Review the selected model's official Hugging Face card again for name, Q4_K_M format, Ollama compatibility, basic tool-test scope, and license caveat. Keep source links near those claims.
- [ ] **Step 5:** Report files added/changed, facts intentionally left unresolved, and that no desktop/Compose/AI runtime was implemented. Do not commit or publish without separate authorization.
