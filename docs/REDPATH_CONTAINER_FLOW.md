# RedPath Docker Compose diagram for Lucidchart

**Status:** Diagram instructions for the planned product, not a working Compose setup. The [architecture](REDPATH_ARCHITECTURE.md) is canonical; [contracts](REDPATH_CONTRACTS.md) define boundaries. Docker Compose is the local orchestrator. Kubernetes is not in the first release.

## Paste this into Lucidchart

Draw a left-to-right diagram titled **RedPath: native desktop + local Docker Compose**. Put the learner and **Native desktop window + launcher** on the left, outside a large **Docker Compose (planned)** box. Inside Compose draw **RedPath app (Linux)**, **Kali (required)**, and **Ollama**. Under the app and Ollama draw **RedPath data** and **Ollama models** volumes. Put an **Authorized training target** on the right, outside Compose. Show a separate **Lesson URL** input above the desktop. Mark every target component **planned**. Do not draw a fourth generic Linux machine or an optional Kali VM.

## Put these boxes in these spots

| Spot | Box label | Text inside the box |
| --- | --- | --- |
| Far left, outside Compose | **Learner** | Controls two Kali shells, chooses lesson/target separately, and approves RedPath-initiated active checks. |
| Next to learner, on host | **Native desktop window + launcher** | Shows two same-Kali terminals, tabs, right AI sidebar/pop-out, bottom teaching drawer, and status header. Checks host Docker prerequisites and starts/stops Compose. |
| Above desktop | **Lesson URL** | Optional learning context; never automatically a target. |
| Middle, large outer box | **Docker Compose (planned)** | One local stack with the three required services and persistent volumes. Host Docker runtime is a prerequisite. |
| Left inside Compose | **1. RedPath app (Linux)** | API/UI, sessions, private SSH terminal manager, target policy, AI context, evidence, and audit. Local host-facing UI/API only. |
| Center inside Compose | **2. Kali (required)** | Same Kali container hosts the learner's two default SSH shells and additional tabs. SSH is private to the stack. |
| Right inside Compose | **3. Ollama** | Private local model API using the selected Qwen3 4B Q4_K_M evaluation candidate. No shell or target access. |
| Inside app | **Fixed-check approval gate** | Exact authorized target, registered bounded action, learner approval, cancellation, and audit. Runner deployment is not yet chosen. This does not govern learner-typed shell commands. |
| Below app | **RedPath data volume** | Persistent SQLite/session/evidence/audit data. |
| Below Ollama | **Ollama models volume** | Persistent model files downloaded during guided online setup. |
| Far right, outside Compose | **Authorized training target** | Private or explicitly authorized training system; platform VPN may be required separately. |

## Draw these arrows

1. **Learner → desktop:** lab, separate lesson URL and exact authorized target; user input to either Kali shell.
2. **Desktop launcher → host Docker runtime:** prerequisite check, pinned image/model acquisition, Compose start/health/stop. No Docker socket arrow into Compose.
3. **Desktop ↔ RedPath app:** local loopback-scoped UI/API and terminal stream (protocol not chosen yet).
4. **RedPath app ↔ Kali:** private, app-managed SSH for multiple learner-controlled shells. Draw no AI-to-Kali arrow.
5. **Kali → authorized training target:** learner-typed lab traffic; label **manual shell boundary, not app approval-gated**.
6. **RedPath app ↔ Ollama:** bounded read-only context and explanation/proposal; label **untrusted suggestion, no execution permission**.
7. **Proposal → fixed-check approval gate → authorized target:** one exact-target fixed check only after learner approval; audit result back to app. The runner is logical here, not a committed fourth service.
8. **App ↔ RedPath data** and **Ollama ↔ model volume:** persistent state. No lesson-URL-to-target arrow.

## What goes inside Docker Compose

| Compose item | Planned contents and connection |
| --- | --- |
| `redpath-app` service | Linux app/API and terminal manager. Connect privately to Kali and Ollama. Mount `redpath-data`. Publish only local UI/API to host loopback. No Docker socket. |
| `kali` service | Required training shell environment. Accept app-managed private SSH only; no host/LAN SSH port. Two default shells share this container and session. |
| `ollama` service | Local Qwen3 4B candidate; private API to app, persistent `ollama-models`; no host-facing model port. |
| `redpath-data` volume | Keep SQLite and app records across restarts. One local app instance writes to this database. |
| `ollama-models` volume | Keep model weights across restarts so setup does not repeat each launch. |
| private Compose networking | App-to-Kali SSH and app-to-Ollama API stay private. Compose networking alone is not an authorization boundary for learner shells or approved checks. |
| restricted check runner | Logical fixed-action boundary only; whether separate service/container is needed remains undecided. |

## How a session works

1. The launcher checks host prerequisites, starts the private Compose stack, and opens the desktop window. The app shows `Connecting to Kali` until private SSH and both default shells are ready.
2. The learner chooses a lesson and enters a separate exact authorized target. A lesson URL alone grants no testing permission.
3. The learner controls the Kali terminals. AI receives only bounded, learner-selected output and read-only backend context. AI cannot enter commands.
4. If RedPath proposes an active fixed check, the app validates target/action, displays the exact operation, asks approval, then records execution or cancellation. That gate is separate from learner shell traffic.
5. Evidence is saved with source and `observed`/`inferred`/`verified` state. Ollama may explain it, but an AI explanation cannot itself verify it.

## Build notes so the diagram does not overpromise

- This repository has not implemented the launcher, Compose services, terminal manager, or selected model. The old VM source was removed, so there is currently no runnable Kali path. Typed integration functions are placeholders only.
- The backend currently requires a loopback bind address. Containerization needs a deliberate inside-container bind change while host publishing remains loopback-only.
- The host needs a compatible Docker runtime and perhaps platform VPN. Compose does not install either. First-run downloads need network access.
- The Q4_K_M model file is about 2.5 GB, not a whole-stack RAM estimate. Tool reliability and low-end speed remain untested; see [Ollama setup](OLLAMA_SETUP.md).
- Do not draw a separate generic Linux service, optional Kali, browser-only first release, Kubernetes cluster, AI-to-shell control, or a mandatory fourth check-worker service.
