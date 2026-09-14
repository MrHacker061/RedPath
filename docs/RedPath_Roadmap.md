# RedPath: AI Red Team Training
## Senior Capstone Project Roadmap — Late September 2026 through April 2027

---

## What Is RedPath? (Read This First)

RedPath is a **beginner cybersecurity learning tool**, not an autonomous hacking agent. Here is the exact intended experience: a university student opens RedPath, creates a lab session, pastes a TryHackMe room URL as a reference, separately types in the private IP address that TryHackMe issued them for that specific room, uploads an Nmap XML scan they ran against that IP, and then RedPath's local AI (running entirely on their machine through Ollama) explains what the scan found, suggests one logical next step, and walks them through it with a plain-English explanation. Nothing happens without the student clicking an explicit Approve button. The goal is to teach the *reasoning* behind each step, not hand the student commands to blindly copy.

**The three things that make this project technically hard:**
1. Keeping the AI separated from direct command execution — Ollama proposes actions, but a separate non-AI policy engine decides whether they are allowed.
2. Enforcing that a lesson URL (e.g., `tryhackme.com/room/basicpentesting`) is never treated as a scan target — these must always be two completely different fields.
3. Getting Kali Linux running reliably as a headless VM that starts on demand and shuts down cleanly after each action.

---

## Team Structure

Your docs describe a four-person team split by role. Assign these based on interest:

| Role | What They Own |
|---|---|
| **Worker 1** | FastAPI backend, SQLite database, session management, target policy engine, approval system, audit logging |
| **Worker 2** | Ollama connection, AI prompt design, structured recommendation schemas, learning library (port/service explanations), AI evaluation |
| **Worker 3** | Kali VM integration, SSH transport, Nmap XML parser, fixed action adapters (HTTP headers, TCP check, TLS cert, SSH identity) |
| **Worker 4** | Frontend dashboard, connecting all backend features to the UI, learning report, user testing, demo preparation |

Every worker is expected to write tests for their own security boundaries. The docs are explicit about this: a feature is not done until the failure cases are tested, not just the happy path.

---

## What Is Already Built (Do Not Rebuild These)

Milestone 1 was completed before the semester started. The following already exists and has tests passing:

- **`redpath/`** — FastAPI app that binds to `127.0.0.1` only, exposes `GET /api/v1/health`, defines shared Pydantic data contracts, and has a working SQLite setup. The loopback-only restriction is enforced by the launcher — do not bypass it.
- **`frontend/`** — A dependency-free HTML/CSS/JavaScript dashboard that calls the health endpoint and displays service status cards for FastAPI, Ollama, and Kali. Has 13 passing Node.js tests. Run it with `python -m http.server 8080 --directory frontend` and open `http://127.0.0.1:8080`.
- **`redpath_ai/`** — The provider interface, a working Ollama client (loopback-only), a rule-based fallback provider for when Ollama is unavailable, and Pydantic schemas for proposals and explanations. Learning library with keyword retrieval is also here.
- **`redpath_kali/vm.py`** — A Python wrapper that can check Kali VM status, start it, discover the real SSH port from Vagrant's output (never hardcoded), and stop it gracefully. Has 21 Python tests and 39 PowerShell safety checks.
- **`scanner/lab_scanner.py`** — A TCP connect scanner that blocks public IPs, requires `--authorized` flag, caps concurrency, and supports a fixed SSH identity check (`whoami`, `hostname`, `id`). This is the model for how all safe actions should be built.
- **`vm/`** — `KaliVM.cmd`, `KaliVM.ps1`, `Vagrantfile`, `kali-vm.json`. The Kali VM uses VirtualBox, is configured with 4 CPUs and 4096 MB RAM, binds SSH to `127.0.0.1` only, and uses a Vagrant-generated per-VM SSH key. The box is `kalilinux/rolling` version `2026.2.0`.
- **`tests/`** — ~86 passing tests across all modules above. Run them with `python -m pytest tests/` and `node --test frontend/tests/*.test.js` before starting any new work.

---

## Cross-OS / Docker Plan (Mac + Windows)

Since your team has both Mac and Windows machines, address this in Week 1 and do not let it become a surprise problem later.

**What goes in Docker:**
- The FastAPI backend (`redpath/`) — this eliminates Python version mismatches, `pip` differences, and path separator issues between Windows and Mac.
- The frontend static file server — `python -m http.server` works but a Docker-based Nginx server is more reliable and works identically on both OSes.

**What does NOT go in Docker:**
- The Kali VM. VirtualBox requires native access to CPU virtualization extensions (AMD-V or Intel VT-x). You cannot run VirtualBox inside a Docker container on a student laptop.
- Ollama. Ollama needs native GPU access for acceptable inference speed. Running it inside Docker loses GPU passthrough on most student machines. Run it natively on the host and configure it to listen on `127.0.0.1:11434` (the default).

**Line endings:** The `.gitattributes` file is already committed and configured. It forces `LF` line endings for all Python and shell files on any OS. This prevents the classic problem where a Mac developer commits a script and Windows produces files with `\r\n` that break Bash inside Kali.

**Secrets:** `.env.example` is committed. Everyone copies it to `.env` locally. The real `.env` is gitignored. Never commit actual credentials, API keys, or SSH private keys. The docs are explicit: never add `.local/`, `__pycache__/`, `.vagrant/`, VM disk images, ISO files, or logs to Git.

**Concrete Docker steps to complete in Week 1:**
1. Write a `Dockerfile` that installs the Python version from `pyproject.toml`, runs `pip install -e ".[test]"`, and starts Uvicorn on `0.0.0.0:8000` inside the container (external to the container — still localhost-only from the host perspective via port mapping).
2. Write a `docker-compose.yml` with two services: `api` (the FastAPI backend) and `frontend` (an Nginx or Python HTTP server serving `frontend/`).
3. Set `REDPATH_HOST=127.0.0.1` in `docker-compose.yml` so the launcher's loopback restriction is still enforced.
4. Confirm that `docker compose up` works on one Mac and one Windows machine before Week 2 ends.

---

## The Core Data Flow (Understand This Before Writing Code)

Every feature you build plugs into this sequence. Read it carefully.

```
Student creates session
  └─ LabSession stored with: lesson URL, target IP (separate fields), authorization statement, expiration time

Student uploads Nmap XML
  └─ Parser extracts: hosts, open ports, protocols, service hints, scan timestamp
  └─ Each finding stored as "observed" (directly seen in scan output, not guessed)

Worker 2 asks Ollama for a recommendation
  └─ Prompt includes: normalized findings, current lesson objective, list of allowed actions
  └─ Ollama returns structured JSON: { finding_ids, action_name, arguments, reason, learning_goal }
  └─ If Ollama returns invalid JSON or an unknown action → reject it, use RuleBasedProvider fallback

Policy engine (Worker 1) checks the proposal
  └─ Is the session still authorized and not expired?
  └─ Is the target in an allowed private range (10.x, 172.16-31.x, 192.168.x)?
  └─ Is the action name in the registered action catalog?
  └─ Are all arguments within allowed values (port ranges, timeouts)?
  └─ Is emergency stop active? → If yes, reject everything
  └─ Result: ALLOWED_PENDING_APPROVAL or REJECTED_[reason]

Student sees the proposal on screen and clicks Approve
  └─ Approval record created, tied to exact session + target + action + arguments
  └─ Approval has an expiration time (e.g., 5 minutes)
  └─ Policy is rechecked one more time immediately before execution

Kali VM starts on demand
  └─ KaliVM.cmd start → waits for SSH readiness (up to 10 min first boot)
  └─ Actual SSH port discovered from Vagrant output (not assumed to be 2223)
  └─ Connection: 127.0.0.1 → dynamic port → Kali sshd:22

Fixed action adapter runs inside Kali
  └─ No free-form commands. Only named, schema-validated actions.
  └─ Example: inspect_http_headers sends one HTTP HEAD request, returns structured headers
  └─ Result parsed into structured JSON with finding IDs

Ollama explains the result in beginner language
  └─ "Port 80 returned an Apache/2.4 header, which means this is a web server running Apache..."
  └─ Result saved as "verified" if the action directly confirmed something

Audit log records every step
  └─ Who approved what, against which target, which action ran, what the result was

Learning report generated at session end
  └─ All observed/inferred/verified findings, all approved actions, cleanup checklist, study suggestions
```

---

## Week-by-Week Roadmap: Late September 2026 – April 2027

---

### PHASE 1: Foundation & Setup
### Week 1 (Late September) — Orient, Environment, Docker

**Goal:** Every team member can run the existing codebase. Cross-OS environment is solved now.

**All team members:**
- Clone the repo. Run `python -m venv .venv`, then `.venv/Scripts/python -m pip install -e ".[test]"` on Windows or `source .venv/bin/activate && pip install -e ".[test]"` on Mac.
- Run `python -m pytest tests/` — all ~86 tests must pass before you write a single line of new code. If any fail on your machine, fix the environment first.
- Run `node --test frontend/tests/*.test.js` to confirm the 13 frontend tests pass.
- Run the health endpoint: `python -m redpath` then `curl http://127.0.0.1:8000/api/v1/health`. You should get `{"status": "ok", ...}`.
- Run the frontend: `python -m http.server 8080 --directory frontend` then open `http://127.0.0.1:8080`. The service health cards will show Ollama and Kali as offline — that is expected at this stage.
- Read `docs/REDPATH_CONTEXT.md` in full. Pay special attention to the sections "Recommended MVP," "AI decision loop," and "Finding states."
- Read `docs/REDPATH_IMPLEMENTATION_TASKS.md` in full. This is your master checklist.

**Worker 1:**
- Start the `Dockerfile` and `docker-compose.yml` described above. Get the backend container running and confirm the health endpoint responds through Docker.

**Worker 4:**
- Confirm the frontend also runs through Docker. Fix any path or port issues.

**Deliverable:** Every team member can run the backend, frontend, and full test suite. Docker container starts on both a Mac and a Windows machine.

---

### Week 2 (Early October) — Team Agreements & Database Models

**Goal:** Define shared data contracts so every worker can build against them without stepping on each other.

**Worker 1 (primary this week):**
- Create all the database models in SQLAlchemy/SQLModel. These are the tables every other worker will read and write:
  - `LabSession` — fields: `id`, `user_id`, `state` (draft/authorized/ready/running/completed/expired/blocked), `lesson_url`, `lesson_provider`, `objective`, `authorization_statement`, `started_at`, `expires_at`, `cleanup_confirmed`
  - `AuthorizedTarget` — fields: `id`, `session_id`, `ip_address`, `port_range`, `authorized_at`, `expires_at`, `locked` (set to true after first approval so it cannot be changed mid-session)
  - `ScanImport` — fields: `id`, `session_id`, `file_hash`, `file_size`, `imported_at`, `scanner_type` (nmap), `scanner_version`
  - `Finding` — fields: `id`, `session_id`, `target_id`, `scan_id`, `state` (observed/inferred/verified), `category` (open_port/service_hint/etc.), `protocol`, `port`, `service_hint`, `evidence_source`
  - `Proposal` — fields: `id`, `session_id`, `finding_ids`, `action_name`, `arguments_json`, `reason`, `learning_goal`, `requires_approval`, `created_at`
  - `PolicyDecision` — fields: `id`, `proposal_id`, `allowed`, `code`, `reason`, `decided_at`
  - `Approval` — fields: `id`, `proposal_id`, `session_id`, `target_id`, `action_protected_hash`, `state` (pending/approved/rejected/expired/used), `expires_at`, `approved_at`
  - `ActionResult` — fields: `id`, `approval_id`, `action_name`, `status` (queued/starting/running/completed/timed_out/failed), `exit_code`, `parser`, `evidence_json`, `cleanup_status`, `started_at`, `finished_at`
  - `AuditEvent` — fields: `id`, `session_id`, `event_type`, `actor`, `detail_json`, `occurred_at`

- Write migrations. Confirm the database creates correctly on a fresh install.

**Worker 2:**
- Finalize the `ProposedStep` Pydantic schema that Ollama must return. Required fields: `finding_ids` (list of finding IDs from the database), `action_name` (must be a registered name), `arguments` (dict matching the action's schema), `reason` (string, 1-3 sentences), `learning_goal` (string, what concept this teaches). Optional: `needs_more_evidence` (bool, allows Ollama to say "I don't have enough information yet").
- This schema needs sign-off from Worker 1 before either person writes more code.

**Worker 3:**
- Define the initial action catalog entries as Python dataclasses or Pydantic models. For each action define: `name`, `version`, `description`, `risk_level` (low/medium), `required_arguments`, `allowed_ports`, `max_timeout_seconds`, `requires_cleanup` (bool), `result_parser`.
- Starting actions to define: `inspect_http_headers`, `tcp_connect_check`, `inspect_tls_certificate`, `ssh_identity_check`.

**Worker 4:**
- Sketch the session creation form fields. The lesson URL field and target IP field must be clearly labeled as separate inputs with explanatory text ("This is your TryHackMe room link, not what we will scan" and "This is the IP address TryHackMe gave you for this specific room").
- Review Worker 1's database models and flag anything that will be hard to display in the frontend.

**Deliverable:** Database models are committed and reviewed by at least two team members. `ProposedStep` schema and action catalog definitions are agreed upon and documented.

---

### PHASE 2: Evidence Pipeline (No AI, No Kali Yet)
### Week 3 (Mid October) — Session Creation & Target Validation

**Goal:** A student can create a lab session and have the target IP validated before anything else happens.

**Worker 1 (primary this week):**
- Add `POST /api/v1/sessions` — creates a `LabSession`. Required body fields: `lesson_url` (string, stored as reference only), `target_ip` (string), `objective` (string), `authorization_statement` (string — the student must type something like "I have permission to scan 10.10.10.5 as part of my TryHackMe lab"). Session starts in `draft` state.
- Add target validation logic. The rules from `scanner/lab_scanner.py` are the starting point. A target IP must be one of: `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, or a configured lab CIDR. Any other address returns a `403` with a clear error message like "Public IP addresses are not allowed. RedPath only works with private lab targets."
- Add `GET /api/v1/sessions/{id}` and `GET /api/v1/sessions` (list).
- Add session state machine: draft → authorized (after the user confirms their authorization statement) → ready (after a scan is imported). Expired sessions cannot start any actions.

**Worker 4:**
- Build the session creation page with two clearly separated fields: lesson URL and target IP.
- Add the authorization statement input. It should be a text area with a placeholder like "I own this machine / I have explicit permission to test 10.10.x.x as part of my TryHackMe lab today."
- Display target validation errors clearly when the backend rejects a public IP.
- Add a session list page showing state, lesson URL, target, and expiration time.

**Worker 2 & 3:**
- Worker 2: Start writing beginner explanation notes for the learning library. Minimum entries this week: ports 22 (SSH), 80 (HTTP), 443 (HTTPS), 445 (SMB), 3389 (RDP). Each note should explain what the port is, what service typically runs on it, what an attacker might look for, and what a beginner should understand before acting on it.
- Worker 3: Set up Nmap XML fixture files. Create at least three: a simple web server (ports 80, 443 open), a Linux SSH server (port 22 open), a Windows machine (ports 445, 3389 open). These fixture files are what every worker will use for testing — they avoid needing a live network.

**Deliverable:** `POST /api/v1/sessions` works. A private IP creates a session successfully. A public IP (e.g., `8.8.8.8`) is rejected with a clear error. Session list shows on the frontend.

---

### Week 4 (Late October) — Nmap XML Import & Finding Display

**Goal:** Upload an Nmap XML file and see parsed findings on screen. Still no AI, no Kali, no live network traffic.

**Worker 3 (primary this week):**
- Build the Nmap XML parser in `redpath/`. It should:
  - Enforce a maximum file size (e.g., 5 MB — large scans suggest something went wrong).
  - Record the SHA-256 hash of the uploaded file for audit purposes.
  - Extract: each host's IP address, each open port, the protocol (tcp/udp), the Nmap service name (e.g., `http`, `ssh`), the product hint if present (e.g., `Apache httpd`), the version hint if present (e.g., `2.4.49`), and the scan timestamp.
  - Store each port as a `Finding` with `state = "observed"`. The word "observed" means: this is directly present in the scan output. Nmap reported port 80 open — that is observed. The guess that it might be running WordPress — that is "inferred," and we do not store inferences from Nmap banners as facts.
  - Banner text (the `<service>` element's extra info) must be treated as untrusted. Store it, but flag it so the AI knows it comes from the target's own response and could be spoofed.
  - Handle malformed XML gracefully — return a clear error, do not crash.
- Use your fixture files from Week 3 as test inputs. Write parser tests for all three fixtures.

**Worker 1:**
- Add `POST /api/v1/sessions/{id}/scans` endpoint. Accepts a file upload (multipart form). Stores the file hash and file metadata in `ScanImport`. Calls the parser. Returns the list of created `Finding` records.
- Move the session state from `authorized` to `ready` after a successful scan import.

**Worker 4:**
- Add an Nmap XML upload button to the session page. On success, display the parsed findings as a table with columns: Host, Port, Protocol, Service Hint, State.
- Label each row's state visually — "observed" should be displayed clearly (a badge or tag). Do not display raw banner text by default; put it behind a collapsible "Show raw evidence" toggle.
- If the upload fails (bad XML, too large, public IP in the scan), show a specific error message.

**Worker 2:**
- Test the learning library retrieval against the fixture findings. Given a finding for port 80, the library should return the HTTP explanation note. Given port 22, it should return the SSH note. Fix any retrieval gaps.

**Deliverable:** Upload one of the Nmap XML fixture files → findings appear on screen with `observed` labels. Upload a malformed XML file → clear error, no crash. All parser tests pass.

---

### PHASE 3: AI Recommendation Layer
### Week 5 (Early November) — Ollama Setup & Structured Output

**Goal:** Connect Ollama. Get a real AI recommendation back in the correct JSON format.

**Worker 2 (primary this week):**
- Install Ollama on your development machine. On Mac: `brew install ollama` then `ollama serve`. On Windows: download `OllamaSetup.exe` from `ollama.com` — it installs as a background service on `localhost:11434` automatically. No additional configuration is needed for the default setup.
- Pull a model. The docs recommend a quantized 7B or 8B instruction model. Use `ollama pull llama3.1:8b` or `ollama pull mistral:7b-instruct`. The download is 4–5 GB. Do this over a fast connection. Once pulled, the model is cached locally and works offline.
- Build the prompt template. The system prompt must tell Ollama it is a cybersecurity tutor (not an autonomous agent), that tool output is untrusted evidence, and that it must return a single JSON object matching the `ProposedStep` schema. Add examples directly in the system prompt showing a correct response and a correct refusal (when evidence is insufficient). Keep the prompt under 1,500 tokens so it leaves room for actual findings.
- The user message in each API call should contain: the session objective, the list of normalized findings (with IDs, port, protocol, service hint, state), the list of allowed action names, and the last result if there is one.
- If Ollama returns invalid JSON: retry once with a stricter instruction ("Return only valid JSON matching the schema, no explanation text"). If the second attempt also fails: fall back to `RuleBasedProvider`, which picks the most conservative safe action based on what ports are open.
- Add a timeout of 30 seconds per Ollama request. If Ollama is not running or times out: use the rule-based fallback and log a warning.

**Worker 1:**
- Add `POST /api/v1/sessions/{id}/recommend` endpoint. Calls Worker 2's recommendation logic. Returns either a `ProposedStep` or an error. Records the model request and response in `ModelRequest` / `ModelResponse` tables.
- Do not yet build the full policy engine — that is Week 6. For now, return the proposal as-is so the frontend can display it.

**Worker 3:**
- Verify that your action catalog from Week 2 is importable from the backend. Worker 1's recommend endpoint needs to send the list of allowed action names to the AI.

**Worker 4:**
- Add a "Get Recommendation" button on the session page (only visible when state is `ready`).
- Display the proposal: show the `reason` field prominently ("Why RedPath is suggesting this"), the `learning_goal` field ("What you will learn"), the action name, and the finding IDs it's based on.
- Do not add approve/reject buttons yet — that is Week 7.

**Deliverable:** Click "Get Recommendation" → Ollama returns a `ProposedStep` → it appears on screen with the reason and learning goal displayed. Ollama timeout triggers the rule-based fallback gracefully.

---

### Week 6 (Mid November) — Policy Engine

**Goal:** Every proposal goes through a non-AI policy check before the student ever sees an Approve button.

**Worker 1 (primary this week):**
- Build the policy engine as a standalone Python module (no FastAPI dependency — it should be testable in pure Python). It takes a `Proposal` and the current session state, and returns a `PolicyDecision` with `allowed: bool`, `code: str`, and `reason: str`.
- Checks to implement, in order:
  1. Is the session in state `ready` or `running`? If not: `REJECTED_SESSION_NOT_ACTIVE`
  2. Is the session's expiration time in the future? If not: `REJECTED_SESSION_EXPIRED`
  3. Is the target IP still in an allowed private range? If not: `REJECTED_TARGET_NOT_ALLOWED`
  4. Is the `action_name` in the action catalog? If not: `REJECTED_UNKNOWN_ACTION`
  5. Does the `arguments` dict match the action's required schema (correct keys, correct types, ports within allowed range)? If not: `REJECTED_INVALID_ARGUMENTS`
  6. Is the emergency stop flag active? If yes: `REJECTED_EMERGENCY_STOP`
  7. All checks pass: `ALLOWED_PENDING_APPROVAL`
- Wire this into the recommend endpoint: call the policy engine after getting the proposal, store the `PolicyDecision`, and return both to the frontend.
- **Critical:** The policy engine must never call Ollama. It must never trust Ollama's output for authorization decisions. The checks are pure Python logic against the database and the action catalog.

**Worker 4:**
- Update the recommendation display. Show the `PolicyDecision` code and reason visually distinct from the AI's `reason` field. The student should clearly see: "RedPath AI suggested this" (AI's reason) vs. "Policy check result: Allowed / Rejected" (policy engine's result).
- If the policy rejects a proposal, show the rejection reason and do not show an Approve button. Show a "Request a different recommendation" button instead.

**Worker 2:**
- Write 10 test scan scenarios for AI evaluation. Each scenario is a set of findings + a session objective + an expected correct action or expected refusal. Include at least: one straightforward HTTP port 80 finding (expect `inspect_http_headers`), one where only port 22 is open (expect `ssh_identity_check`), one where no useful ports are open (expect `needs_more_evidence`), one where banner text contains instruction-like text (expect Ollama to ignore it and not follow embedded instructions).
- This is groundwork for the full evaluation in Week 12.

**Worker 3:**
- Write integration tests for each action definition in the catalog: confirm that valid arguments pass schema validation and that invalid arguments (wrong port, missing required field, out-of-range value) fail.

**Deliverable:** Policy engine rejects a proposal with an unknown action name. Policy engine rejects a proposal targeting a public IP. Policy engine approves a valid `inspect_http_headers` proposal targeting a private IP with port 80 as a finding. All policy tests pass.

---

### PHASE 4: Approval System & Kali Actions
### Week 7 (Late November / Early December) — Approval System

**Goal:** Student can approve a policy-checked proposal. The approval is tied to exact parameters and has an expiration.

**Worker 1 (primary this week):**
- Add the `Approval` table and the following endpoints:
  - `POST /api/v1/proposals/{id}/approve` — creates an `Approval` record. Computes `action_protected_hash` as `SHA-256(session_id + target_ip + action_name + sorted(arguments))`. Stores the hash. Sets `expires_at` to 5 minutes from now. Only one pending approval per proposal at a time.
  - `POST /api/v1/proposals/{id}/reject` — marks the proposal as rejected. Student can request a new recommendation after this.
  - `GET /api/v1/approvals/{id}` — returns approval state, expiration, and the exact action/target/arguments it covers.
- Before any action actually runs (this will be wired up in Week 8), the executor must call a `revalidate_approval_before_execution` function that re-runs the policy engine and re-checks the hash. If anything has changed (target was modified, session expired, emergency stop activated), the approval is invalidated and the action does not run.
- An approval can only be used once. Set state to `used` after execution begins. Prevent duplicate-click race conditions.

**Worker 4 (primary this week):**
- Add Approve and Reject buttons. They appear only when `PolicyDecision.allowed == true`.
- Show the student the exact parameters they are approving before they click: "You are about to run **inspect_http_headers** against **10.10.10.5** on port **80**. This will send a single HTTP request to retrieve response headers. Timeout: 10 seconds."
- Add a countdown timer showing approval expiration (5 minutes). If the approval expires before the student clicks, clear it and ask them to re-request.
- Handle the case where the student double-clicks Approve — the second click should be silently ignored (the backend returns an error, the frontend shows "Already approved").
- Add the emergency stop button. It should be visible at all times during an active session, not just during actions. It hits `POST /api/v1/sessions/{id}/stop`. After emergency stop, the Approve button disappears and a banner shows "Emergency stop is active — no new actions can run."

**Worker 2 & 3:**
- Workers 2 and 3: Write tests using the approved fixture findings from Week 4 and the policy scenarios from Week 6. Make sure a rejected policy decision never allows an Approval record to be created (test this explicitly — it is a security boundary).

**Deliverable:** Student approves a proposal → `Approval` record created with hash and 5-minute expiration. Rejected proposals cannot be approved. Emergency stop prevents new approvals. Double-click is handled correctly.

---

### Week 8 (Early December) — Kali VM Starts and First Action Runs

**Goal:** An approved action triggers Kali to start, runs the fixed action inside Kali, and returns a structured result.

**Worker 3 (primary this week):**
- Wire the existing `redpath_kali/vm.py` wrapper into the action execution pipeline. The flow:
  1. Check if Kali is already running (`vm.status()` returns `running`). If not, call `vm.start()`.
  2. Wait for SSH readiness — poll every 5 seconds, give up after 10 minutes (first boot with 5 GB download can be slow).
  3. Call `vm.ssh_config()` to get the actual SSH port. This is critical: do not assume port 2223. Vagrant may assign a different port if 2223 is taken by the existing CS 4440 VM.
  4. Connect via SSH to `127.0.0.1:{discovered_port}` using the Vagrant-managed private key. Disable password auth, keyboard-interactive auth, and SSH-agent fallback.
  5. Run the action. For `inspect_http_headers`: inside Kali, run `curl -s -I http://{target_ip}:{port}`. The target IP comes from the `AuthorizedTarget` record — the runner must re-validate this before passing it to any command.
  6. Parse the output. Extract: HTTP status code, `Server` header value, `Content-Type`, `X-Powered-By` if present. Return as structured JSON.
  7. Call `vm.stop()` after the action completes. Confirm Vagrant reports `poweroff` before returning.
- Wrap the entire execution in a timeout (60 seconds for this action). If it times out, stop Kali gracefully and return `status: "timed_out"`.
- **Do not pass the raw command to SSH as a string.** Build the command as a list of arguments to prevent injection. The action adapter constructs the exact command — the runner just executes what the adapter gives it.

**Worker 1:**
- Add `POST /api/v1/approvals/{id}/execute` endpoint. Calls `revalidate_approval_before_execution`, then hands off to Worker 3's runner. Returns the `ActionResult` record (queued state immediately, then polled for completion).
- Add `GET /api/v1/actions/{id}` for status polling. The frontend will poll this every 2 seconds to check if the action is still running.
- Store the action result in `ActionResult`. Store structured evidence (the parsed HTTP headers, for example) in `evidence_json`. Do not store raw SSH output in the database.

**Worker 4:**
- Show action progress states: `queued` → `starting` → `running` → `completed` (or `timed_out` / `failed`).
- Poll `GET /api/v1/actions/{id}` every 2 seconds while the action is in a non-terminal state.
- Show the result when complete: display the parsed HTTP headers in a human-readable format, not as raw JSON.
- Emergency stop during action: if the student hits emergency stop while an action is running, the backend sets a cancellation flag. The runner checks this flag between steps. Show "Stopping..." state in the UI.

**Worker 2:**
- When the action result comes back, call Ollama with the result and ask it to explain what it means in beginner language. Example: "The server returned an `Apache/2.4.49` header. This tells us the web server is Apache, version 2.4.49. This version has a known path traversal vulnerability (CVE-2021-41773). In a real authorized lab, this would be a good thing to investigate further." Store this explanation and display it beneath the result.
- The explanation call must not grant the AI any new execution authority. The AI explains — it does not trigger anything.

**Deliverable:** Approve the `inspect_http_headers` action → Kali starts → HTTP headers from the private lab target come back → result shows on screen with Worker 2's plain-English explanation → Kali shuts down and reports `poweroff`. This is the first end-to-end flow.

---

### PHASE 5: Full Learning Loop
### Week 9 (Mid December) — Audit Log, Evidence States, Additional Adapters

**Goal:** The full audit trail is in place. Evidence moves from observed → verified. Additional action adapters are built.

**Worker 1 (primary this week):**
- Wire `AuditEvent` records throughout every significant step. Events to log: session created, session authorized, session expired, target accepted, target rejected, scan imported, model requested, proposal created, policy decision made, proposal approved, proposal rejected, execution started, execution completed, execution timed out, emergency stop activated, emergency stop cleared, Kali started, Kali stopped, session closed, cleanup confirmed.
- Each event should store: event type, session ID, user identifier, a JSON detail object (the target IP for target events, the action name for execution events, etc.), and a timestamp.
- Secrets must never appear in audit events. The detail JSON should reference IDs, not actual key values or SSH key contents.

**Worker 3 (primary this week):**
- Add the TCP connect check adapter: attempts a TCP connection to `{target_ip}:{port}`, waits up to 5 seconds, returns whether the connection succeeded or was refused. This is the lowest-risk adapter and useful for confirming that a port is actually open before committing to a heavier action.
- Add the TLS certificate inspection adapter: connects to `{target_ip}:{port}` with TLS, retrieves the certificate's subject CN, issuer, validity dates, and SANs. Does not validate or exploit the certificate — only reads it. Useful for confirming HTTPS is running and identifying what the certificate is for.
- Update the findings pipeline: when an action result comes back, if the action directly confirmed something (e.g., TCP connect succeeded on port 80), update the corresponding `Finding` from `state = "observed"` to `state = "verified"`. If Ollama inferred something from a result without a direct confirmation (e.g., "this is probably WordPress because of the headers"), that remains `state = "inferred"` and is stored as a separate derived finding.

**Worker 2:**
- Add 10 more scan scenarios for AI evaluation (20 total now). New additions: a TLS-only service (port 443, no 80), a service with misleading banner text that names a different product than what's actually running, a scan with only high-numbered ports open (no common services), a scan where Ollama should ask for more evidence before recommending an action.
- Expand the learning library to cover: TLS/HTTPS concepts, what "version disclosure" means (why seeing `Apache/2.4.49` in a header matters), the difference between observed vs inferred vs verified findings, and what an audit log is for.

**Worker 4:**
- Update the finding display to show state transitions in real time. When a finding moves from `observed` to `verified`, highlight it.
- Show the audit log tab on the session page. Display events in chronological order with timestamps.
- Add a "Show raw evidence" expandable section on each action result for users who want to see the raw parsed output.

**Deliverable:** Full audit log is populated after an end-to-end run. TCP connect adapter and TLS adapter work against a local test target. Findings correctly update from `observed` to `verified` after a successful action.

---

### Week 10 (Late December / Early January) — Learning Report & SSH Identity Check

**Goal:** Session ends with a complete learning report. SSH identity check adapter is ready.

**Worker 3 (primary this week):**
- Add the SSH identity check adapter. This is the most sensitive adapter and must be the most constrained:
  - It requires an authorized SSH key path stored in the session (not a password).
  - It connects to `{target_ip}:22` using the provided key.
  - It runs exactly three commands, hardcoded in the adapter code: `whoami`, `hostname`, `id`.
  - It returns the three outputs. No other commands are accepted. No interactive shell. The command list is a constant in the code, not a parameter.
  - If SSH connection fails: return a `failed` result with the error type (connection refused, authentication failed, timeout). Do not guess why it failed.
  - Cleanup: the SSH session is closed immediately after the three commands complete.
- Add cleanup tracking to `ActionResult`: `cleanup_status` can be `not_required`, `pending`, or `confirmed`. The SSH identity check sets `cleanup_status = "not_required"` because it makes no changes to the target. A reverse-shell lab action (out of scope for MVP) would set it to `pending` until the student confirms they've cleaned up.

**Worker 4 (primary this week):**
- Build the learning report page. This is shown when a session is closed (`POST /api/v1/sessions/{id}/close`). The report should include:
  - Session summary: lab objective, lesson URL, authorized target IP, session duration, authorization statement.
  - Findings: a table of all findings grouped by state (observed, inferred, verified). Each finding shows host, port, protocol, service hint, and the action that verified it (if any).
  - Actions taken: list of all approved actions with their results and Ollama's explanation for each.
  - Policy decisions: any rejected proposals and why they were rejected.
  - Cleanup checklist: one item per action that required cleanup. Student confirms each item.
  - Study suggestions from Worker 2's library: 3–5 topics to read more about based on what was found.
- Add a Markdown export button. The exported file should be a clean, readable session log the student can keep.
- Add a print stylesheet so the report can be printed or saved as PDF from the browser.

**Worker 1 & 2:**
- Worker 1: Add the session close endpoint. Require cleanup confirmation for any pending cleanup items before state moves to `completed`.
- Worker 2: Wire the study suggestion logic. After a session ends, look at the verified findings and return relevant learning library entries the student should read next.

**Deliverable:** Full end-to-end run completes with a learning report. Report shows all findings, all actions, Ollama explanations, and a cleanup checklist. Markdown export downloads correctly.

---

### WEEK 11 (Early January) — Buffer, Bug Fixes & Winter Demo Prep

**Goal:** Stabilize everything built in Phase 1–5. Run the full flow on both Mac and Windows. Fix the most critical bugs.

**All team members:**
- Do a full end-to-end run on a Mac machine and a Windows machine. Document every difference in behavior and fix any cross-OS issues.
- Run the full test suite. All existing tests must still pass. Any feature that broke something else gets fixed this week, not next semester.
- Identify the 5 biggest problems or missing pieces. Prioritize by: "Does this block the demo?" If yes, fix it. If no, log it for Semester 2.
- Prepare the winter demo script:
  1. Open RedPath, create a session with a TryHackMe lesson URL and a private lab IP.
  2. Enter the authorization statement.
  3. Upload the HTTP fixture Nmap XML.
  4. Click "Get Recommendation" — Ollama recommends `inspect_http_headers`.
  5. Policy engine approves it.
  6. Student reads the reason and learning goal, then clicks Approve.
  7. Kali starts, action runs, result and explanation appear.
  8. Close the session, view the learning report.
- Record a backup demo video in case live demo has issues.

**Deliverable:** Clean end-to-end demo working on both operating systems. Backup video recorded. Top bugs documented for Semester 2.

---

### PHASE 6: Hardening, Evaluation & Polish (Semester 2)
### Week 12 (Mid January) — Policy Hardening & Rate Limiting

**Goal:** Every security boundary has a test. Policy edge cases are handled.

**Worker 1 (primary this week):**
- Add rate limiting to the policy engine: a session cannot run more than 10 actions per hour. An action against the same target:port combination cannot run more than 3 times in 5 minutes. These limits prevent runaway tool loops even if the frontend has a bug.
- Add concurrency limits: only one action per session at a time. The backend must enforce this — not just the frontend.
- Write explicit tests for every rejection code: `REJECTED_SESSION_EXPIRED`, `REJECTED_SESSION_NOT_ACTIVE`, `REJECTED_TARGET_NOT_ALLOWED`, `REJECTED_UNKNOWN_ACTION`, `REJECTED_INVALID_ARGUMENTS`, `REJECTED_EMERGENCY_STOP`, `REJECTED_RATE_LIMITED`. Each test should try to bypass the rejection and confirm it cannot.
- Test approval reuse: use an approval once, then try to use the same approval ID again. Confirm the backend rejects it with `REJECTED_APPROVAL_ALREADY_USED`.
- Test approval expiration: create an approval, wait for it to expire (or mock the time), then attempt execution. Confirm it fails.

**Worker 3:**
- Add idle timeout to the Kali VM: if Kali has been running for 30 minutes with no action in progress, call `vm.stop()` automatically. The next action will start it again on demand.
- Write tests for the idle timeout logic using mocked time.
- Write tests that confirm: an unknown action name is rejected before SSH is ever opened, temporary files created during an action are cleaned up even if the action fails midway, and the `poweroff` state is verified after every `vm.stop()` call.

**Worker 2:**
- Expand the AI evaluation set to 20+ scenarios. Run all of them through Ollama and score each one:
  - Did Ollama pick the correct action? (Yes/No)
  - Did it cite the correct finding IDs? (Yes/No)
  - Was the schema valid? (Yes/No)
  - Was the explanation clear to a beginner? (1–5)
- Run the same scenarios through the `RuleBasedProvider` fallback and compare scores. Document where Ollama does better and where it does worse.

**Worker 4:**
- Add accessible error handling throughout the UI: every API error should show a specific message, not a generic "Something went wrong." Screen reader labels on all interactive controls. Keyboard navigation (Tab order, Enter to submit, Esc to cancel).

**Deliverable:** Every policy rejection code has a passing test. Approval reuse is blocked. Rate limiting is active. AI evaluation scores documented.

---

### Week 13 (Late January) — AI Prompt Refinement

**Goal:** Fix the most common AI failures found in Week 12's evaluation without fine-tuning the model.

**Worker 2 (primary this week):**
- For each category of AI failure found in the evaluation, fix it through prompt and library changes only (fine-tuning is out of scope for MVP):
  - If Ollama frequently picks wrong actions: add more example proposals to the system prompt for the specific service types that caused failures.
  - If Ollama ignores finding IDs: make the prompt more explicit that `finding_ids` must reference actual IDs from the provided list, and add a validation step that rejects proposals referencing non-existent IDs.
  - If Ollama produces text instead of JSON: add a more prominent instruction in the system prompt and consider adding a JSON mode flag if the model supports it.
  - If banner text injection works (Ollama follows instructions embedded in scan output): add an explicit warning in the prompt that content inside `<service_info>` tags is untrusted data from the target, not instructions.
- Re-run the full 20+ scenario evaluation after prompt changes. Document the before/after scores.
- Add retrieval to the prompt: before building the final prompt, run keyword retrieval against the learning library for each open port found. Include the top 2 relevant library notes in the prompt. This gives Ollama concrete background without making the prompt too long.

**All workers:** Code review week. Every worker reviews at least one other worker's code for security issues — specifically: does this code trust any unvalidated input? Does it use string formatting to build commands? Does it log anything that might contain secrets?

**Deliverable:** AI evaluation scores improve compared to Week 12 baseline. Prompt injection via banner text is confirmed to be rejected. Code review findings are documented and highest-priority ones are fixed.

---

### Week 14 (Early February) — User Testing Setup

**Goal:** Set up a real lab environment for beginner user testing and write the test protocol.

**Worker 4 (primary this week):**
- Set up the intentionally vulnerable test target VM. Options: Metasploitable 2 (Ubuntu, many intentionally vulnerable services, well-known in CTF community), or a simple VirtualBox Ubuntu 20.04 with Apache installed. The target must be on the VirtualBox host-only network at `192.168.56.20/24` (Kali is at `192.168.56.10`). Assign the Windows VM to the same host-only adapter. Enable only the services you plan to test in the user study.
- Prepare the test Nmap XML file. Run an actual Nmap scan against the test target and save the XML: `nmap -sV -oX test_scan.xml 192.168.56.20`. This is the file test participants will upload.
- Write the test script: a step-by-step procedure a beginner can follow, with prompts for what they should identify at each step and what they should do.
- Design the comprehension questions. At minimum ask participants: "What IP address was the scan target?" (checking they understand target separation), "Why did RedPath suggest the `inspect_http_headers` action?" (checking they read the reason), "What did the HTTP headers tell us?" (checking they understood the result explanation).

**Worker 2:**
- Add comprehension questions to the session flow. After each action result, show a short 1–2 question knowledge check. Example after `inspect_http_headers`: "What does the Server header value tell us?" with multiple choice options. Store their answer. If wrong, show a brief explanation. This is not graded — it is formative.

**Worker 1:**
- Add a `GET /api/v1/sessions/{id}/report` endpoint that returns the full session data as JSON. Worker 4's Markdown export will call this. Also needed for the evaluation data export.

**Deliverable:** Test lab VM is running with the target accessible from Kali. Test Nmap XML is ready. Test script and comprehension questions are written and reviewed by at least two team members.

---

### Week 15 (Mid February) — User Testing

**Goal:** Run the user study with real beginners. Collect data.

**All team members:**
- Recruit 6–10 beginner participants (university classmates who are not on the capstone team, beginner CTF members, or students from introductory security courses). They should not be familiar with the specific test lab.
- Run each participant through the test script twice: once without RedPath (give them the Nmap XML and the lab objective, let them decide what to do on their own), once with RedPath. Randomize order across participants to reduce order effects.
- Measure and record:
  - Did they correctly identify the target IP vs. the lesson URL? (Scope awareness)
  - Did they choose an appropriate next action? (Action selection)
  - Could they explain *why* they chose that action when asked? (Conceptual understanding)
  - Did they make any scope mistakes (try to scan a public IP, try to access the lesson website)? (Safety behavior)
  - How long did each task take? (Efficiency — but not the only metric)
  - Confidence rating before and after (1–5 self-report)
- After the session: ask each participant where they found RedPath confusing, what terminology they did not understand, and what they would change.

**Deliverable:** Raw test data collected and documented. At least one team member takes notes during each session. Data is organized before Week 16.

---

### Week 16 (Late February) — Fix Top User Testing Issues

**Goal:** Analyze test results and fix the highest-priority problems before final polish.

**All team members:**
- Analyze the data. Group feedback into categories: UI confusion, terminology confusion, workflow confusion, AI explanation clarity, policy error messages.
- Pick the top 5–7 issues that most participants had. Prioritize by: "Does this prevent a beginner from completing the lab?" If yes, fix it this week.
- Common issues to expect and fixes:
  - "I didn't know the lesson URL wasn't the target" → Improve the label text and add an explainer tooltip on the session creation form.
  - "I don't know what 'observed' means" → Add a glossary pop-up to the findings table. Define observed/inferred/verified in plain English.
  - "The policy error was confusing" → Rewrite rejection messages in plain English: "This IP address is public. RedPath only works with private lab targets like those from TryHackMe or VirtualBox labs" instead of `REJECTED_TARGET_NOT_ALLOWED`.
  - "Ollama took too long and I thought it crashed" → Add a visible loading indicator with estimated wait time ("Asking RedPath AI — this usually takes 5–15 seconds").

**Deliverable:** Top issues from user testing are fixed and committed. Updated frontend is tested by at least two team members who were not the ones who built the fix.

---

### Week 17 (Early March) — Windows Installer & Mac Docker Polish

**Goal:** RedPath is packaged and installable by someone who has not read the repo docs.

**Worker 1 & 3 (primary this week):**
- Review `packaging/RedPath.iss` — this is an Inno Setup script that builds a Windows `.exe` installer. Confirm it installs the Python environment and the Ollama requirement is documented (Ollama must be installed separately since it requires GPU driver setup). The installer's expected output is `dist/installer/RedPath-Setup-0.1.0-x64.exe`.
- The Windows launchers (`redpath-desktop`, `redpath-api`) use a Windows named mutex so only one instance runs at a time. Test this: try starting two instances and confirm the second one exits cleanly.
- Write `docs/INSTALL_MAC.md` describing the Mac Docker path: install Docker Desktop, clone the repo, copy `.env.example` to `.env`, run `docker compose up`, install Ollama natively, install VirtualBox + Vagrant for the Kali VM.
- Test the full Mac Docker path with a clean machine (no pre-installed Python or Node).

**Worker 4:**
- Final accessibility pass. Use a screen reader (VoiceOver on Mac, NVDA on Windows) on the main session flow. Fix any missing `aria-label` attributes, unclear button text, or color-only status indicators.
- Confirm all interactive elements are reachable by keyboard. Add `tabindex` where needed.

**Worker 2:**
- Add the final polish to the learning library. Minimum 20 notes covering the most common ports: 21 (FTP), 22 (SSH), 23 (Telnet), 25 (SMTP), 53 (DNS), 80 (HTTP), 110 (POP3), 139/445 (SMB), 443 (HTTPS), 3389 (RDP), 5900 (VNC), 8080 (HTTP alternate). Each note should cover: what the service is, what an attacker looks for, what a beginner should investigate first, and what action RedPath can run against it.

**Deliverable:** Windows installer builds without errors. Mac Docker path works on a clean machine following only the README and `INSTALL_MAC.md`. All accessibility issues found by screen reader testing are fixed.

---

### Week 18 (Mid March) — End-to-End Integration Tests

**Goal:** The full workflow is tested automatically, not just unit-tested. No secrets can escape.

**All team members:**
- Write end-to-end integration tests that cover the complete session lifecycle:
  - Test 1: Create session → import fixture XML → get recommendation → check policy → approve → run action → check result → close session → verify audit log → verify learning report content.
  - Test 2: Create session with a public IP → confirm rejection at every entry point (session creation, target validation, policy engine).
  - Test 3: Create session → get recommendation → let approval expire → attempt execution → confirm failure.
  - Test 4: Activate emergency stop during a running action → confirm action stops → confirm no new approvals can be created → deactivate stop → confirm new approvals work again.
  - Test 5: Send malformed Ollama output (invalid JSON, unknown action name, out-of-range arguments) → confirm policy rejects it → confirm rule-based fallback activates.
- Run the final MVP Acceptance Checklist from `docs/REDPATH_IMPLEMENTATION_TASKS.md` line by line. Every checkbox must pass before Week 19.

**Worker 1:**
- Confirm secrets cannot appear in reports, audit logs, or API responses. Write a test that deliberately sets a fake API key in `.env` and confirms it never appears in any response body, any log line, or any database record.

**Deliverable:** All end-to-end integration tests pass. MVP Acceptance Checklist is fully checked off. Security review finds no secrets in outputs.

---

### Week 19 (Late March) — Final Bug Fixes & Documentation

**Goal:** Fix whatever the integration tests found. Documentation is complete enough that a new team member could pick up the project.

**All team members:**
- Fix all issues found in Week 18's testing.
- Write/finalize `docs/MVP_RELEASE_CHECKLIST.md`. This should cover: all tests passing, installer tested, secrets not in Git, Kali gracefully shuts down, emergency stop works, report exports correctly.
- Worker 4: Write the end-to-end run guide. A step-by-step guide covering: install Ollama, set up Kali VM, clone repo, configure `.env`, run the backend, run the frontend, complete a full lab session.
- Worker 2: Write the limitations doc. Be honest about where the AI makes mistakes, what it cannot teach, and what a more advanced version would add (e.g., fine-tuned model, Metasploit integration behind extra safety layers, multi-user support).
- All: Document what a future team would need to build next (the "future work" section expected in a capstone writeup).

**Deliverable:** All documentation complete. No known blocking bugs. Every team member has run the full flow independently on their own machine.

---

### Week 20 (Early April) — Demo Rehearsal & Presentation

**Goal:** Final demo. Presentation to class and faculty.

**All team members:**
- Rehearse the demo at least twice with all team members watching. The demo script:
  1. Show the running health dashboard (FastAPI green, Ollama green, Kali standby).
  2. Create a session. Show the separate lesson URL and target IP fields. Enter the authorization statement.
  3. Upload the test Nmap XML. Show findings appear with `observed` labels.
  4. Click "Get Recommendation." Show Ollama's proposal appear with the reason and learning goal.
  5. Show the policy decision: `ALLOWED_PENDING_APPROVAL`.
  6. Show the approval details page (exact target, action, arguments, timeout). Click Approve.
  7. Show Kali starting on-demand.
  8. Show the action running and the result appearing.
  9. Show Ollama's plain-English explanation of the result.
  10. Show the finding update from `observed` to `verified`.
  11. Close the session and show the complete learning report.
  12. Export the Markdown report.
  13. Show the emergency stop button working.
  14. Show a public IP being rejected.
- Have a backup demo video ready in case live demo fails. The video should be the most recent clean run from Week 19.
- Prepare a short presentation covering: the problem RedPath solves, the technical architecture (the AI-to-policy-to-approval-to-execution pipeline), what was built, what was measured in user testing, what was learned, and what would come next.

**Final Deliverable:** Complete, working RedPath MVP demonstrated to class and faculty. Full test suite passes. All documentation committed. Session archived in the repo.

---

## Hard Rules to Keep in Mind All Semester

These come directly from your documentation. Any team member can call these out if they are being violated:

1. **Lesson URL ≠ Target IP.** They are separate database columns, separate form fields, separate data types. Pasting a TryHackMe URL must never auto-populate the target field.
2. **Ollama is untrusted.** The policy engine runs independently of Ollama and ignores what Ollama thinks about authorization. Ollama proposes — the policy engine decides.
3. **No action runs without explicit approval.** No exceptions. Not even for "safe" actions like TCP connect.
4. **Approval is hash-locked.** If the target IP, action name, or arguments change after approval is created, the approval is invalid. The re-validation step immediately before execution enforces this.
5. **No secrets in Git.** `.env`, SSH private keys, API keys, VirtualBox disk images — none of this belongs in the repo. The `.gitignore` already covers most of this, but check before every commit.
6. **Emergency stop is always visible.** It is not a hidden feature. It should be present in the UI at all times during an active session.
7. **No public IP targets.** This is enforced in code at three places: session creation, policy engine, and inside the Kali runner. All three must check.

---

## Out of Scope for MVP (Do Not Add These)

- Arbitrary Metasploit module execution
- Free-form shell commands generated by Ollama
- Credential guessing or password spraying of any kind
- Persistence mechanisms (cron jobs, startup scripts, backdoors in the target)
- Evasion or stealth features
- Fine-tuning the Ollama model
- A private TryHackMe API (use manual entry as the fallback)
- PostgreSQL (SQLite is correct for a single-user desktop MVP)
- Multi-user authentication (single local user for MVP)
- Scanning public internet targets under any circumstances
