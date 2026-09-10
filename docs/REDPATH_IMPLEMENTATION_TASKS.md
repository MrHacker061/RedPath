# RedPath Four-Worker Feature Implementation To-Do List

## Project goal

Build a working RedPath MVP that accepts a lesson and separate authorized target, imports Nmap evidence, asks Ollama for a structured recommendation, checks it with a policy engine, requests approval, runs a fixed action through the headless Kali VM, and creates a learning report.

## Rules for every worker

- [ ] Keep lesson URLs separate from target addresses.
- [ ] Allow only private or specifically approved training targets.
- [ ] Never give the AI unrestricted terminal or SSH access.
- [ ] Use named actions with strict input schemas.
- [ ] Require approval before active network actions.
- [ ] Record decisions and results in the audit log.
- [ ] Support the emergency stop.
- [ ] Treat scan and tool output as untrusted data.
- [ ] Never store secrets in Git, prompts, reports, or logs.
- [ ] Add tests for every security boundary.

## Worker 1: Backend, database, sessions, and policy

### Main responsibility

Build FastAPI, SQLite, lab sessions, target validation, policy decisions, approvals, and audit records.

### Backend setup

- [ ] Create the Python project and dependency file.
- [ ] Create the FastAPI application.
- [ ] Add Pydantic request and response models.
- [ ] Add SQLAlchemy or SQLModel.
- [ ] Configure SQLite and migrations.
- [ ] Add safe configuration loading.
- [ ] Add a health endpoint and structured logging.

### Database models

- [ ] Create `User`.
- [ ] Create `LabSession`.
- [ ] Create `LessonSource`.
- [ ] Create `AuthorizedTarget`.
- [ ] Create `ScanImport` and `Finding`.
- [ ] Create `ModelRequest` and `ModelResponse`.
- [ ] Create `Proposal` and `PolicyDecision`.
- [ ] Create `Approval`.
- [ ] Create `Action` and `ActionResult`.
- [ ] Create `AuditEvent` and `Report`.
- [ ] Add timestamps, stable IDs, relationships, and constraints.

### Lab sessions

- [ ] Add session creation, viewing, listing, and closing endpoints.
- [ ] Store lesson URL and target in separate models.
- [ ] Require authorization confirmation.
- [ ] Add start and expiration times.
- [ ] Add draft, authorized, ready, running, completed, expired, and blocked states.
- [ ] Prevent expired sessions from starting actions.
- [ ] Record cleanup status when a session closes.

### Target validation

- [ ] Normalize IPv4 and IPv6 addresses.
- [ ] Reject malformed, multicast, and link-local targets.
- [ ] Reject public targets by default.
- [ ] Allow configured private lab ranges.
- [ ] Support provider rules without weakening the default.
- [ ] Tie each target to one session and expiration time.
- [ ] Prevent target changes after approval.

### Action registry

- [ ] Define action name, version, description, and risk.
- [ ] Define strict arguments for every action.
- [ ] Define allowed ports, targets, timeouts, and rates.
- [ ] Define approval and cleanup requirements.
- [ ] Define the expected result parser.
- [ ] Reject unknown actions and extra arguments.

### Policy engine

- [ ] Check session authorization and expiration.
- [ ] Check target ownership and expiration.
- [ ] Check the action registry and argument schema.
- [ ] Enforce ports, protocols, timeouts, rates, and concurrency.
- [ ] Check the emergency-stop state.
- [ ] Return a stable decision code and explanation.
- [ ] Store every policy decision.
- [ ] Keep all policy enforcement independent of Ollama.

### Approval system

- [ ] Turn an allowed proposal into pending approval.
- [ ] Tie approval to the exact session, target, action, and arguments.
- [ ] Add approve and reject endpoints.
- [ ] Add approval expiration.
- [ ] Invalidate approval if protected data changes.
- [ ] Recheck policy immediately before execution.
- [ ] Prevent approval reuse.

### Audit system

- [ ] Record sessions and authorization.
- [ ] Record target acceptance and rejection.
- [ ] Record scan imports and model requests.
- [ ] Record policy decisions and approvals.
- [ ] Record action start, completion, timeout, and failure.
- [ ] Record Kali startup and shutdown.
- [ ] Record emergency-stop changes.
- [ ] Filter secrets and excessive output.

### Worker 1 tests and completion

- [ ] Test session creation and expiration.
- [ ] Test lesson and target separation.
- [ ] Test private-target acceptance and public-target rejection.
- [ ] Test unknown actions and invalid arguments.
- [ ] Test approval expiration and reuse prevention.
- [ ] Test emergency-stop rejection.
- [ ] Confirm a structured proposal can pass or fail policy.
- [ ] Confirm an allowed proposal can be approved once.
- [ ] Confirm the full audit history is available.

## Worker 2: Ollama, AI orchestration, retrieval, and explanations

### Main responsibility

Connect Ollama, create structured recommendations, build the learning library, and evaluate model quality.

### Provider interface

- [ ] Define `LLMProvider`.
- [ ] Add `recommend_next_step` and `explain_result`.
- [ ] Create `OllamaProvider`.
- [ ] Create `RuleBasedProvider` as a fallback.
- [ ] Leave an interface for optional `OpenAIProvider`.
- [ ] Add provider health, timeout, and availability checks.

### Ollama setup

- [ ] Select a quantized 7B or 8B instruction model.
- [ ] Document Ollama installation and model download.
- [ ] Connect through the local Ollama API.
- [ ] Prevent direct browser access to Ollama.
- [ ] Add bounded retries and request timeouts.
- [ ] Record model name, version, latency, and memory use.

### Structured AI output

- [ ] Create the `ProposedStep` Pydantic schema.
- [ ] Require supporting finding IDs.
- [ ] Require one registered action name.
- [ ] Require structured arguments, a reason, and learning goal.
- [ ] Allow a request for more evidence instead of an action.
- [ ] Reject unknown fields and actions.
- [ ] Retry invalid JSON once, then use a safe fallback.
- [ ] Ensure invalid output never reaches execution.

### Prompt construction

- [ ] Write the RedPath system prompt.
- [ ] Define the model as a teacher and planner.
- [ ] Label tool output as untrusted evidence.
- [ ] Include only normalized findings and relevant actions.
- [ ] Include observed, inferred, and verified states.
- [ ] Include the current lesson objective and prior results.
- [ ] Require one proposal or clarification request.
- [ ] Add examples of correct refusals.
- [ ] Keep policy enforcement outside the prompt.

### Learning library and retrieval

- [ ] Create beginner notes for common ports and services.
- [ ] Explain important Nmap fields.
- [ ] Document every approved action.
- [ ] Add authorization, safety, and cleanup notes.
- [ ] Create reviewed scan examples.
- [ ] Tag notes by service, port, action, and difficulty.
- [ ] Build keyword retrieval first.
- [ ] Limit retrieved prompt content.
- [ ] Add note source IDs.
- [ ] Consider embeddings only after testing keyword retrieval.

### Evidence reasoning and explanations

- [ ] Require proposals to cite finding IDs.
- [ ] Mark model interpretations as inferred.
- [ ] Prevent the model from creating verified findings.
- [ ] Ask for clarification when evidence is missing.
- [ ] Explain what each action can and cannot prove.
- [ ] Explain failed results without claiming the target is secure.
- [ ] Define unfamiliar terms for beginners.
- [ ] Recommend topics to study at session end.

### AI evaluation

- [ ] Create at least 20 reviewed scan scenarios.
- [ ] Include web, SSH, DNS, and TLS examples.
- [ ] Include incomplete and conflicting evidence.
- [ ] Include unsafe or unauthorized requests.
- [ ] Include instruction-like text inside tool output.
- [ ] Define the expected action or refusal for each case.
- [ ] Score action correctness, evidence use, clarity, and schema validity.
- [ ] Track policy rejection rate and latency.
- [ ] Compare Ollama with the rule-based fallback.

### Fine-tuning decision

- [ ] Do not fine-tune the initial MVP.
- [ ] Test prompts, examples, and retrieval first.
- [ ] Record repeated model failures.
- [ ] Keep future training and test datasets separate.
- [ ] Consider a LoRA adapter only as an advanced milestone.

### Worker 2 tests and completion

- [ ] Test valid and malformed model output.
- [ ] Test unknown actions and unsupported finding IDs.
- [ ] Test refusal when no action fits.
- [ ] Test prompt-injection text inside evidence.
- [ ] Test Ollama timeout and rule-based fallback.
- [ ] Confirm recommendations cite supporting evidence.
- [ ] Confirm results receive beginner-friendly explanations.

## Worker 3: Kali VM, SSH, parsers, and fixed action adapters

### Main responsibility

Connect the existing headless Kali VM, run fixed actions, return structured results, and shut down cleanly.

### Existing VM integration

- [ ] Review `vm/KaliVM.ps1`, `vm/KaliVM.cmd`, `vm/Vagrantfile`, and `vm/kali-vm.json`.
- [ ] Reuse the existing lifecycle manager.
- [ ] Add Python wrappers for status, startup, SSH config, and shutdown.
- [ ] Preserve the VM name `Headless-Kali-Terminal`.
- [ ] Preserve Kali address `192.168.56.10`.
- [ ] Preserve the 4 CPU and 4096 MB configuration.
- [ ] Preserve disabled GUI, shared folders, clipboard, and X11.

### SSH transport

- [ ] Read the actual Vagrant SSH configuration after startup.
- [ ] Never assume host port 2223.
- [ ] Connect through `127.0.0.1` only.
- [ ] Use the Vagrant per-VM key and key-only authentication.
- [ ] Prevent unrelated SSH-agent key fallback.
- [ ] Set connection and command timeouts.
- [ ] Capture output, errors, and exit status.
- [ ] Limit returned output size.
- [ ] Treat a disconnected session as unknown until checked.

### Restricted runner

- [ ] Accept only a named action and validated JSON arguments.
- [ ] Reject free-form commands and unknown actions.
- [ ] Validate the target again inside Kali.
- [ ] Apply process timeouts.
- [ ] Use temporary action directories.
- [ ] Return a structured result envelope.
- [ ] Clean temporary files after retrieval.
- [ ] Support emergency-stop cancellation.

### Nmap parser

- [ ] Enforce XML size limits.
- [ ] Record the original file hash.
- [ ] Extract hosts, ports, protocols, services, and scan time.
- [ ] Preserve evidence references.
- [ ] Mark direct scan facts as observed.
- [ ] Handle malformed XML safely.
- [ ] Create sanitized parser fixtures.

### Fixed adapters

- [ ] Build Nmap XML import without network traffic.
- [ ] Build one limited private-target scan profile.
- [ ] Build a short TCP connection check.
- [ ] Build an HTTP header inspection action.
- [ ] Build a TLS certificate inspection action.
- [ ] Build an authenticated SSH identity check using only `whoami`, `hostname`, or `id`.
- [ ] Give every adapter a strict schema, timeout, parser, and cleanup rule.
- [ ] Exclude unrestricted Metasploit, payloads, password guessing, persistence, stealth, and arbitrary shells.

### VM lifecycle

- [ ] Keep Kali off until an approved action needs it.
- [ ] Start it on demand and wait for SSH readiness.
- [ ] Track activity and idle time.
- [ ] Stop it at session end or after an idle timeout.
- [ ] Use graceful shutdown first.
- [ ] Verify Vagrant reports `poweroff`.
- [ ] Never silently force power off.

### Worker 3 tests and completion

- [ ] Test powered-off status detection.
- [ ] Test startup and actual SSH port discovery.
- [ ] Test authentication failure, timeout, and output limits.
- [ ] Test unknown-action rejection.
- [ ] Test all result parsers.
- [ ] Test temporary-file cleanup and emergency cancellation.
- [ ] Test graceful shutdown and final `poweroff` verification.
- [ ] Confirm one approved action can run and return structured evidence.

## Worker 4: Frontend, reports, integration, testing, and delivery

### Main responsibility

Build the student interface, connect every backend feature, create reports, test the full workflow, and prepare the demo.

### Frontend foundation

- [ ] Choose React or a simpler server-rendered interface.
- [ ] Create the frontend and shared API client.
- [ ] Add navigation, loading states, and clear errors.
- [ ] Add accessible colors, labels, and keyboard navigation.
- [ ] Prevent secrets from appearing in browser state.

### Dashboard and sessions

- [ ] Show FastAPI, Ollama, and Kali health.
- [ ] Show emergency-stop state.
- [ ] List and create lab sessions.
- [ ] Add provider, lesson URL, target, objective, authorization, and expiration fields.
- [ ] Clearly explain that the lesson page is not the target.
- [ ] Display target-policy errors.

### Evidence workspace

- [ ] Add Nmap XML upload.
- [ ] Display hosts, ports, service hints, and evidence sources.
- [ ] Label findings as observed, inferred, or verified.
- [ ] Hide raw output by default.
- [ ] Add a bounded raw-evidence view.

### Recommendation and approval

- [ ] Add the next-step request control.
- [ ] Show supporting findings, reason, and learning goal.
- [ ] Display policy results separately from AI confidence.
- [ ] Prevent rejected proposals from reaching approval.
- [ ] Show exact target, action, arguments, timeout, and cleanup.
- [ ] Add approve and reject buttons.
- [ ] Handle approval expiration and duplicate clicks.

### Action progress and emergency stop

- [ ] Show queued, starting, running, stopping, completed, timed-out, and failed states.
- [ ] Add safe progress polling or server events.
- [ ] Add a visible emergency-stop button independent of Ollama.
- [ ] Show what stopped and what still needs cleanup.
- [ ] Block new action controls while stopped.

### Learning report

- [ ] Show the objective and authorized-target summary.
- [ ] Separate observed, inferred, and verified findings.
- [ ] List recommendations, policy decisions, and approvals.
- [ ] List actions, results, and what each result proved.
- [ ] Add cleanup confirmation and study suggestions.
- [ ] Add print or Markdown export.
- [ ] Keep secrets out of reports.

### Full integration

- [ ] Connect sessions and targets to Worker 1's API.
- [ ] Connect scan upload to Worker 3's parser.
- [ ] Connect recommendations to Worker 2's orchestrator.
- [ ] Connect policy and approvals to Worker 1.
- [ ] Connect approved execution to Worker 3.
- [ ] Return normalized results to the evidence view.
- [ ] Ask Ollama to explain results without granting execution authority.
- [ ] Connect the audit history, stop control, and report.

### User testing and delivery

- [ ] Write a beginner test script.
- [ ] Test whether users separate the lesson URL from the target.
- [ ] Test whether users understand recommendations and evidence states.
- [ ] Measure task completion with and without RedPath.
- [ ] Collect clarity and confidence ratings.
- [ ] Create a disposable host-only target VM.
- [ ] Prepare a known Nmap XML sample and one short live action.
- [ ] Record backup screenshots or a demo video.
- [ ] Create installation and end-to-end instructions.
- [ ] Document limitations and future work.

### Worker 4 tests and completion

- [ ] Test forms, accessibility, errors, and duplicate-click protection.
- [ ] Test blocked proposals and expired approvals.
- [ ] Test action states and emergency stop.
- [ ] Test report completeness.
- [ ] Test the full workflow from session creation through Kali shutdown.
- [ ] Confirm a beginner can use RedPath without a direct terminal.

## Shared integration contracts

### Normalized finding

```json
{
  "id": "finding-12",
  "session_id": "session-1",
  "target_id": "target-3",
  "state": "observed",
  "category": "open_port",
  "protocol": "tcp",
  "port": 80,
  "service_hint": "http",
  "evidence_source": "scan-7"
}
```

### AI proposal

```json
{
  "finding_ids": ["finding-12"],
  "action_name": "inspect_http_headers",
  "arguments": {"target_id": "target-3", "port": 80},
  "reason": "An HTTP service was observed and has not been checked yet.",
  "learning_goal": "Understand what HTTP response headers can reveal.",
  "requires_approval": true
}
```

### Policy decision

```json
{
  "proposal_id": "proposal-8",
  "allowed": true,
  "code": "ALLOWED_PENDING_APPROVAL",
  "reason": "The target and fixed action are allowed for this session."
}
```

### Action result

```json
{
  "action_id": "action-9",
  "status": "completed",
  "exit_code": 0,
  "parser": "http_headers_v1",
  "evidence": [],
  "cleanup_status": "not_required"
}
```

## Shared milestone plan

### Milestone 1: Foundation

- [ ] Worker 1 creates FastAPI and SQLite.
- [ ] Worker 2 creates provider and proposal schemas.
- [ ] Worker 3 creates VM and parser interfaces.
- [ ] Worker 4 creates the frontend shell.
- [ ] Everyone approves the shared data contracts.

### Milestone 2: Evidence-only prototype

- [ ] Create a session with separate lesson and target.
- [ ] Import Nmap XML.
- [ ] Display normalized observed findings.
- [ ] Generate a rule-based explanation.

### Milestone 3: Ollama recommendation

- [ ] Connect Ollama and retrieval.
- [ ] Generate and validate one proposal.
- [ ] Run it through policy.
- [ ] Display allowed and rejected outcomes.

### Milestone 4: Approval and Kali action

- [ ] Approve the exact proposal.
- [ ] Start Kali on demand.
- [ ] Discover the actual SSH settings.
- [ ] Run one fixed action and parse its result.
- [ ] Shut Kali down gracefully.

### Milestone 5: Complete learning loop

- [ ] Explain the result.
- [ ] Update evidence states.
- [ ] Display audit history.
- [ ] Generate the learning report.
- [ ] Confirm emergency-stop behavior.

### Milestone 6: Evaluation and delivery

- [ ] Finish policy and integration tests.
- [ ] Run the AI evaluation set.
- [ ] Conduct beginner user testing.
- [ ] Fix the highest-priority problems.
- [ ] Prepare the demo, backup, documentation, and presentation.

## Merge order

1. Worker 1 publishes API and database contracts.
2. Workers 2 and 3 build against the shared schemas.
3. Worker 4 builds against the API contracts.
4. Worker 3 provides parser fixtures before live VM work.
5. Worker 2 tests recommendations using those fixtures.
6. Worker 1 connects proposals, policy, and approvals.
7. Worker 3 connects approved execution.
8. Worker 4 verifies the complete user flow.
9. Everyone reviews security and failure paths.

## Definition of done

A feature is finished only when:

- [ ] Implementation and input validation are complete.
- [ ] Failure behavior is clear.
- [ ] Security rules are enforced outside the AI.
- [ ] Unit or integration tests pass.
- [ ] Audit behavior is included when needed.
- [ ] User errors are understandable.
- [ ] Documentation is updated.
- [ ] Another worker reviewed it.
- [ ] It works in the complete RedPath flow.

## Final MVP acceptance checklist

- [ ] A user can create an authorized session.
- [ ] Lesson and target remain separate.
- [ ] Public or unapproved targets are blocked.
- [ ] Nmap XML imports correctly.
- [ ] Findings show observed, inferred, and verified states.
- [ ] Ollama returns a structured recommendation.
- [ ] Invalid model output is rejected.
- [ ] Policy checks every proposal.
- [ ] The user approves an exact action.
- [ ] Kali starts only when required.
- [ ] RedPath discovers the actual SSH port.
- [ ] A fixed action runs against the approved target.
- [ ] Results return in structured form and receive an explanation.
- [ ] Audit events record the workflow.
- [ ] Emergency stop blocks new actions.
- [ ] Kali shuts down gracefully and reaches `poweroff`.
- [ ] The learning report is complete.
- [ ] The demo does not expose secrets.
