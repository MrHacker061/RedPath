# RedPath architecture

**Status:** Target design, not a working desktop release. See [contracts](REDPATH_CONTRACTS.md) for proposed interfaces. The repository's old VM implementation has been removed; no Kali runtime is currently available here.

## Current checkout

The repository currently has a FastAPI/SQLite application, a static frontend, a loopback-only Ollama recommendation provider, Nmap evidence import, and an authorized scanner. The Windows VM code has been retired. `redpath_desktop.launcher`, `redpath_kali.terminal`, `redpath_ai.compose`, and `redpath.checks` are typed, fail-closed placeholders, not working connections. There is no runnable Kali environment, Docker Compose stack, native desktop launcher, managed two-terminal UI, or integration of the selected Qwen3 model.

## Target experience

RedPath opens in its own window on tested Windows, macOS, and Linux releases. The workspace is terminal-centered: two live, resizable, learner-controlled SSH shells into the **same required Kali container** appear side by side. More shells can open as tabs. A resizable AI sidebar sits on the right and can pop out. A collapsible teaching drawer sits below the terminals. The header shows the lesson, separately authorized target, and connection state. The learner sees plain-language states such as `Starting Kali`, `Connecting to Kali`, and `Ready`, not SSH setup instructions.

AI can explain selected output and findings, answer lesson questions, and suggest a bounded next step. It cannot type into the shells. The core terminals, sessions, and saved evidence remain available if AI is unavailable or slow.

## Target runtime

```text
Native desktop window + launcher (host OS)
  -> host Docker runtime / Compose lifecycle (launcher-controlled)
       -> RedPath app + API (Linux container)
            -> Kali container (required; private, app-managed SSH)
            -> Ollama container (private local model API)
            -> persistent RedPath data
       -> persistent Ollama model storage
  -> authorized training target (may require platform VPN)
```

The app container is the Linux environment that connects to Kali; there is no extra generic Linux container. The launcher manages Docker from the host. Containers must not receive the host Docker socket. Kali SSH and Ollama are private to the stack, not exposed to the host LAN. The desktop reaches only the local app interface. A restricted runner for RedPath-initiated fixed checks is a **logical** boundary; whether it becomes a separate container is undecided. Docker Compose is the local orchestrator; Kubernetes is out of the first release.

Compose does not install a host container runtime, virtualization support, or a training-platform VPN. The first run is an online guided prerequisite check and download of pinned images and the model. Installation, licensing, OS permissions, or virtualization setup may still need the user. Later launches should start services in the background. The tested OS/CPU-architecture matrix and hardware minimums must be established before release.

## Connections and trust boundaries

| Connection | Owner and boundary |
| --- | --- |
| Lesson URL -> app | Learning context only. A URL is not a target or authorization. |
| Authorized target -> app | Separate exact target and lab scope entered/confirmed by the learner. |
| Desktop -> app -> Kali | App manages SSH and terminal lifecycle. Shell input is learner-controlled; AI has no terminal write channel or SSH credential. |
| App -> Ollama | Bounded lesson, finding, and learner-selected output context; model output is untrusted. |
| AI proposal -> fixed check | Backend validates registered action and exact target; learner approves; execution and cancellation are audited. No arbitrary command tool. |
| Kali/user shell -> lab | Manual commands are outside RedPath's fixed-check approval gate. Network isolation and the platform's rules still matter. |

Scan text, terminal output, lesson content, and model responses may contain hostile instructions; none may grant tool authority. A finding is `observed`, `inferred`, or `verified` based on its actual evidence, not on AI confidence. Provenance and approval must remain attached to app-initiated checks. RedPath must not claim its policy mediates every command the learner enters into Kali.

## Startup and failure states

1. First run: launcher checks host Docker/runtime, permissions, storage, architecture, and connectivity; guides the user through missing prerequisites; downloads pinned app/Kali/Ollama images and model; starts the stack; waits for health; then opens the workspace.
2. Later run: launcher starts or reconnects to the local stack, checks app/Kali/Ollama separately, establishes private SSH to Kali, and opens two shells in the same lab session.
3. If Docker is missing or inaccessible, show the prerequisite and a retry path. Do not claim Compose installed it silently.
4. If an image or model download fails, keep a resumable/retryable setup state and do not report `Ready`.
5. If Kali or SSH fails, show `Connecting to Kali` or a specific failed state; do not display a false live shell. AI and saved lessons may remain accessible.
6. If Ollama is absent or too slow, mark AI unavailable and retain terminal, session, and evidence access. No measured low-end performance is claimed.

## Security scope

RedPath is for systems the learner owns or is explicitly authorized to test, including approved training labs. App-initiated checks must use fixed allowlisted actions, exact target validation, explicit approval, bounded execution, and an audit record. The interactive Kali shell is powerful and learner-controlled; its availability does not expand authorization. RedPath will not add automatic exploitation, credential guessing, persistence, or reverse-shell deployment.

## Open release decisions

Choose the desktop framework, installer and host-runtime onboarding, supported OS/architecture matrix, measured RAM/CPU requirements, terminal transport and SSH credential lifecycle, restricted-runner placement, close-window behavior, and any lower-power model only after implementation and testing. The selected Qwen3 candidate and current provider are described in [Ollama setup](OLLAMA_SETUP.md).
