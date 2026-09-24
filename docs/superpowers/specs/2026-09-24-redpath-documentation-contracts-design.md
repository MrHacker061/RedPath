# RedPath documentation and contracts redesign

**Historical decision record:** This earlier documentation-only design was superseded by the [code skeleton and VM retirement design](2026-09-24-redpath-code-skeleton-retirement-design.md). Its instructions to preserve the Windows VM and legacy guide no longer apply.

**Status:** Proposed design for review. This document describes a target architecture; it does not claim that the new desktop, Compose, terminal, or AI connections exist today.

## Purpose and scope

RedPath is an authorized-lab learning app. This change will make the repository's documentation describe the agreed terminal-first desktop product, its component boundaries, and the migration from the current Windows VM prototype. It will not implement the new product. Only Markdown documentation and non-executable interface contracts are in scope.

Success means a developer can tell (1) what works in the current checkout, (2) what is planned, (3) which component owns each connection, and (4) which older instructions are legacy, without reading several contradictory architecture documents.

## Current repository state

- The checkout contains a FastAPI backend, SQLite session/evidence contracts, a static frontend, an Ollama recommendation provider, an Nmap parser, and a Windows Vagrant/VirtualBox Kali manager.
- `README.md` is predominantly a guide to the current headless VM. `docs/REDPATH_SYSTEM_MAP.md` and `docs/REDPATH_PROJECT_CONNECTIONS.md` repeat the older browser/Windows/VM design.
- `docs/REDPATH_CONTAINER_FLOW.md` and `tasks/plan.md` are untracked planning work. Both describe Compose, but still treat a Kali VM as optional or outside the Compose stack. They belong to the current workspace and will not be silently discarded.
- There is no working Compose stack, native desktop shell, managed two-terminal connection, or implementation of the selected model in this checkout.

## Target product experience

The normal product opens in its own desktop window on supported Windows, macOS, and Linux systems. A lab opens with two interactive shells in the same required Kali container, side by side. The learner may open additional shells as tabs or resize the panes. A resizable AI assistant stays on the right and may pop into its own window. A collapsible teaching drawer sits below the terminals. The header shows the current lab, authorized target, and connection state. The app reports startup in plain language, such as `Starting Kali`, `Connecting to Kali`, and `Ready`; it never asks the learner to configure SSH manually.

The AI may explain selected terminal output, observed findings, and learning material. It does not type into either shell or receive SSH credentials. Manual shell commands are controlled by the learner. RedPath's approval policy governs **RedPath-initiated checks**, not every command a learner can enter in an interactive Kali shell. Documentation must not imply otherwise. Network isolation and the training platform's own authorization remain important for manual use.

The lesson URL is learning context. It is never inferred to be the target or permission to test it. Findings retain separate `observed`, `inferred`, and `verified` states.

## Target runtime boundary

```text
Native RedPath window and launcher (per supported host OS)
  -> local RedPath app/API (Linux container)
       -> Kali container (required, multiple user shell sessions)
       -> Ollama container (local model, explanations and proposals)
       -> RedPath data volume
  -> Docker runtime and Compose lifecycle (launcher-controlled)
```

The app container is the Linux environment that connects to Kali over app-managed SSH; no extra generic Linux container is required. Compose also has a persistent model volume. Kali SSH is private to the stack and should not expose a port to the host LAN. The native launcher manages Compose; neither the app container nor the model receives the host Docker socket. Any RedPath-initiated check still crosses exact-target validation, an allowlist of fixed actions, explicit learner approval, and audit recording. Its restricted check runner is a logical boundary separate from learner-controlled shells; whether it needs its own container remains an implementation design decision. A training target may require a separate platform VPN; Compose does not provide one automatically.

Compose is the local orchestrator. Kubernetes is excluded from the first version. Compose requires a working host container runtime; it is not itself an installer or a desktop-window framework. First run is an online, guided process that checks host prerequisites, helps the user obtain the appropriate runtime, downloads pinned RedPath/Kali/Ollama images and the model, starts services, and reports failures. Subsequent starts should be background-managed. Host-specific installation, virtualization, licensing, and permissions may still require user interaction. The release documentation must name its tested OS, architecture, and Linux-distribution matrix rather than claim every computer works.

## AI boundary and selected model

The selected model candidate is [`IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated`](https://huggingface.co/IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated) at Q4_K_M through Ollama. Its published model file is about 2.5 GB, but that is not a whole-stack RAM requirement. Pin the exact model revision and artifact digest for an eventual release; verify upstream license obligations before redistribution. The model card reports Ollama tool-call support and a small native-tool-call test, but explicitly says this is not a full reliability evaluation. The documents must not present tool accuracy, low-end performance, or safe behavior as verified.

The first documented AI tools are read-only, backend-owned interfaces: current session/lesson, approved target summary, normalized findings, a learner-selected bounded terminal excerpt, and reviewed learning content. A model tool request is untrusted data. The backend validates the tool name and arguments, limits context, and returns a bounded result. A request for an active check becomes a proposal subject to normal policy and approval; it is not a shell command and never bypasses the learner. Terminal output and scan text are untrusted inputs that may contain prompt-injection instructions.

The 4B model is the selected evaluation candidate, not a proven minimum-hardware default. If it is unavailable or too slow, core session, terminal, and evidence functions must remain usable and the AI should show a clear unavailable state. No alternate model is selected by this document. A low-power profile requires measured whole-stack tests before release.

## Document ownership and migration

| File | Planned documentation treatment |
| --- | --- |
| `README.md` | Replace the VM-heavy landing page with a short current-state quick start, project map, and links to canonical target-design and legacy guides. Never give planned commands as working setup. |
| `docs/REDPATH_ARCHITECTURE.md` | New canonical target architecture: desktop UI, startup, Compose services, data flow, authorization boundary, failure states, and implemented-versus-planned table. |
| `docs/REDPATH_CONTRACTS.md` | New non-executable contracts for desktop/launcher, terminal sessions, health states, AI read tools, proposals/approval, evidence, and service ownership. Mark proposed fields/routes as such; do not overwrite the existing Python contracts. |
| `docs/LEGACY_VM.md` | Move the detailed current Vagrant/VirtualBox instructions out of `README.md`; clearly label them as the existing prototype, not the target installation path. |
| `docs/REDPATH_CONTAINER_FLOW.md` | Update the untracked Lucidchart diagram to match the approved three-service app/Kali/Ollama target and the native launcher. Preserve its diagram purpose and label all services planned. |
| `docs/OLLAMA_SETUP.md` | Separate the currently implemented host-loopback provider from the planned Compose/Ollama model flow and selected Qwen3 candidate. |
| `docs/REDPATH_SYSTEM_MAP.md`, `docs/REDPATH_PROJECT_CONNECTIONS.md` | Remove the duplicate, outdated architecture prose only after the canonical documents cover its still-useful facts. Replace each with a short superseded pointer so existing links do not break. |
| `docs/REDPATH_CONTEXT.md` | Preserve as historical capstone context, add a prominent current-design pointer and warn that older implementation details may differ. Do not rewrite the capstone narrative as if new software exists. |
| `docs/REDPATH_IMPLEMENTATION_TASKS.md`, `tasks/plan.md` | Preserve teammate assignments and uncommitted planning. Add a short discrepancy notice pointing to the new design; revise the live roadmap separately with its owners. No automatic GitLab changes. |
| `vm/`, `redpath_kali/`, `frontend/`, `redpath/`, `redpath_ai/`, `scanner/`, `tests/` | No code moves, deletions, or behavior changes in this documentation task. |

This is a replace-and-redirect documentation migration, not a code migration. Actual retirement of Vagrant/VirtualBox must wait until the Compose/Kali replacement works and its consumers are verified.

## Contract inventory to document

1. **Launcher-to-Compose:** prerequisites, start/stop request, image/model acquisition state, service health, failure and retry states. The launcher owns Docker access.
2. **Desktop-to-app:** same-origin local API, lab session selection, terminal layout preferences, AI/sidebar state, evidence navigation. Existing endpoints are listed separately from planned endpoints.
3. **App-to-Kali terminal:** app-managed private SSH, session-scoped terminal ID, create/attach/resize/close lifecycle, bidirectional byte stream, reconnection behavior, bounded transcript excerpt for AI. Terminal data is not a model command channel.
4. **App-to-Ollama:** model identity, bounded input context, read-only tool call request/response, schema validation, timeouts, and unavailable fallback.
5. **Policy-to-approved-check runner:** exact session, target, fixed action and arguments, learner approval, audit receipt, cancellation. This is distinct from an interactive learner shell; its process/container placement is not decided here.
6. **Evidence/reporting:** normalized finding, source, `observed`/`inferred`/`verified` state, provenance, and audit linkage.

The contract document should describe shape and responsibility without inventing implementation-complete endpoints, transport protocols, or security properties that have not been tested.

## Verification for the documentation change

- Review the diff and ensure only Markdown documents changed.
- Check all repository-relative links and each reference to removed or superseded docs.
- Search the canonical docs and README for claims that VirtualBox is required, Kali is optional, the 7B model is the selected default, or the product is already a working cross-platform desktop app.
- Confirm the existing quick-start and `python -m pytest` instructions still describe the current checkout accurately; run tests only to check that documentation work did not disturb the current application.
- Verify the selected model name, format, and limitations against its Hugging Face card; do not claim local inference or performance testing occurred.
- Preserve untracked user work. Do not commit, push, merge, release, or update GitLab without a separate authorization.

## Decisions deliberately deferred

- Exact desktop framework and installer technology.
- Supported release OS/CPU architecture matrix and minimum RAM/CPU/VRAM, pending whole-stack measurements.
- Exact desktop-to-app terminal streaming protocol, SSH credential lifecycle, and Kali container build contents, pending security and integration design.
- Whether closing the desktop window stops the lab or leaves services running.
- Whether a lower-power alternate AI model is offered after benchmarking.

These are explicit design tasks, not claims silently filled in by this documentation pass.
