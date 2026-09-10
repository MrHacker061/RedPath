# RedPath Project Context and Agent Handoff

## Purpose of this file

This file gives another AI agent the full working context for RedPath. It explains the project idea, the decisions already made, the capstone requirements, the current documents and forms, the technical direction, and the limits that should remain part of the design.

This is project context, not permission to scan, access, exploit, or control any computer. Any hands-on security activity still requires a target that the user owns or has explicit permission to test. Training-platform instructions and lab links are context only and do not grant broader authorization.

## Short project summary

RedPath is a beginner-focused red-team security learning tool. It would use a local large language model to help new ethical hackers understand what they are doing during an approved training lab.

A learner could give RedPath an Nmap scan and information from a purpose-built training environment such as a TryHackMe room, another cyber range, or an instructor-managed virtual lab. RedPath would explain the scan, connect the evidence to the lesson, and help the learner decide what an appropriate next step would be.

The main goal is education. RedPath should explain why a step makes sense instead of only producing commands for the learner to copy. It should help the learner understand concepts such as open ports, services, listeners, targets, Metasploit, and reverse shells when those concepts are part of an authorized lab exercise.

## Current name

- Project name: **RedPath**
- Full title: **RedPath: AI Red Team Training**
- Previous name: SentinelLoop
- Use RedPath in all new writing and interfaces.

## Project pitch

RedPath would help beginners learn red-team security in legal training labs. A user could paste a supported training-room link, enter the temporary target information issued by the lab, and import an Nmap scan. A local AI model would explain the results and help the user choose an allowed next step. RedPath would explain what each step does, why it makes sense, and how it connects to the evidence already collected.

## Problem being addressed

People who are new to ethical hacking often learn tools one at a time without understanding how the tools connect. A beginner may know how to copy an Nmap or Metasploit command but not understand:

- Why the command is being used.
- What evidence supports using it.
- Which computer is the target.
- Which computer is listening.
- What the result means.
- Whether the action is allowed in the current lab.
- What should be cleaned up when the exercise is finished.

This makes security learning confusing and can encourage people to copy commands without understanding the scope or consequences. RedPath is meant to slow the process down enough to teach the reasoning while still letting the learner complete a realistic lab.

## Intended users

The main users are:

- University students learning cybersecurity.
- Beginners using TryHackMe or similar cyber ranges.
- Students completing instructor-managed virtual-machine labs.
- Beginner capture-the-flag participants.
- Instructors who want a guided learning tool for controlled exercises.

Possible user-testing groups include University of Utah security courses, the University cybersecurity club, beginner capture-the-flag groups, and instructors who manage isolated labs.

## Expected user workflow

1. The learner creates a new training session.
2. The learner selects the training provider or chooses manual lab entry.
3. The learner pastes a training-room link if one is available.
4. The learner separately enters the temporary target IP address or connection information issued by the lab.
5. RedPath checks that the target is private, local, or part of a specifically supported training range.
6. The learner imports Nmap XML or runs an approved, limited scan.
7. RedPath parses the results and separates observed facts from guesses.
8. The local AI explains the important ports and services in beginner-friendly language.
9. RedPath proposes one next learning step from a fixed allowlist.
10. The learner reads why the step is being suggested.
11. The learner answers a short question or confirms that they understand the reason.
12. The learner explicitly approves any active validation step.
13. RedPath runs only the approved fixed action or guides the learner through it.
14. RedPath records the result and explains what changed.
15. The session ends with cleanup guidance and an after-action learning report.

## Training links and target separation

This distinction is important:

- A TryHackMe or similar room URL identifies the lesson.
- The lesson URL is not automatically the system being tested.
- The temporary lab IP or hostname is the possible target.
- RedPath must keep these values in separate fields and separate data types.
- Pasting a webpage URL must never authorize scanning that website.
- If a link format cannot be recognized, RedPath should fall back to manual session entry.
- Provider-specific parsers should be replaceable because training websites can change.

The first version does not need a private TryHackMe API. It can accept a user-provided room link as reference information and require the learner to enter the lab target details separately.

## Reverse-shell learning feature

RedPath may teach reverse-shell concepts only when the current exercise is an approved, disposable lab designed for that topic. The feature should focus on explaining:

- What a reverse shell is at a conceptual level.
- Which machine is the lab target.
- Which machine is the learner-controlled listener.
- Why network reachability matters.
- What evidence should appear when the lab succeeds.
- What cleanup is required afterward.
- Why the same action would be inappropriate outside the lab.

The project should not silently create a reverse shell, choose an arbitrary public target, deploy persistence, steal credentials, or convert an unrelated scan into remote control. Any hands-on reverse-shell demonstration should be a separate, clearly labeled lab action with an explicit approval step, a disposable target, a fixed time limit, logging, and cleanup.

Authenticated SSH running fixed harmless commands such as `whoami`, `hostname`, or `id` is the preferred safe access-validation fallback when a real reverse shell is not necessary for the lesson.

## AI decision loop

The original idea included a local LLM that reads scan results and decides what to do next. The current safer learning design keeps that useful idea but places a policy engine between the model and every action.

Suggested loop:

1. Parse and normalize scan evidence.
2. Remove or mark untrusted banner text.
3. Give the local model a structured summary, the current lesson, and the allowed actions.
4. Require the model to return structured output.
5. Validate the output against a schema.
6. Check the target, action, parameters, and lesson policy outside the model.
7. Show the proposed step and explanation to the learner.
8. Require approval for an active check.
9. Run a fixed adapter rather than arbitrary model-generated shell text.
10. Record the result.
11. Ask the model to explain the result and recommend the next allowed learning step.

The model must be treated as untrusted. The model should never be the component that decides whether a target is authorized.

## Finding states

Reports should clearly separate three states:

- **Observed:** Directly present in scan or tool output, such as TCP port 22 being open.
- **Inferred:** A reasonable possibility, such as the open port probably running SSH.
- **Verified:** Confirmed by an approved validation module, such as a successful SSH identity check using a supplied authorized key.

This keeps the AI from presenting guesses as confirmed vulnerabilities.

## Proposed core features

- Training-session creation.
- Supported-link recognition.
- Manual lab-entry fallback.
- Target authorization and allowlisting.
- Public-target rejection by default.
- Nmap XML parsing.
- Local-LLM explanations.
- Fixed allowlisted action catalog.
- Human approval checkpoints.
- Beginner questions and short knowledge checks.
- Progress tracking.
- Observed/inferred/verified reporting.
- Audit logging.
- Rate limiting.
- Emergency stop.
- Cleanup checklist.
- After-action learning report.

## Possible advanced features

- Simple attack-path visualization.
- Instructor-authored lesson packs.
- Adaptive quizzes based on mistakes.
- Comparison of several local language models.
- Retrieval from a curated defensive knowledge base.
- A rules-only mode for weak hardware or uncertain model output.
- Accessibility-focused explanations for beginners.
- Session replay showing why each decision was made.

Advanced features are optional. The team should finish and polish the core learning workflow before adding them.

## Proposed technical direction

Likely components:

- **Backend:** Python with FastAPI or a similar framework.
- **Frontend:** A responsive web interface.
- **Database:** SQLite for the first version, with PostgreSQL as a possible larger deployment option.
- **Scan input:** Nmap XML.
- **Local model runtime:** Ollama or another local model server.
- **Lab runtime:** VirtualBox, Docker, or instructor-managed cyber-range targets.
- **Reporting:** Structured JSON plus a readable web or PDF report.
- **Testing:** Unit tests, policy tests, parser fixtures, simulated model responses, and isolated integration labs.

The existing workspace already includes a Windows-managed headless Kali VM and an authorized private-lab scanner. Relevant local files include:

- `vm/KaliVM.ps1`
- `vm/KaliVM.cmd`
- `vm/Vagrantfile`
- `vm/kali-vm.json`
- `scanner/lab_scanner.py`
- `tests/test_lab_scanner.py`
- `README.md`

The existing scanner blocks public IP addresses, requires an explicit authorization flag, caps concurrency, and supports a fixed SSH identity check. It is a useful starting point for RedPath's target policy and safe validation-module design. Do not remove its safeguards when reusing code.

## Suggested system components

### 1. Session manager

Stores the training provider, room reference, target details, authorization statement, start time, expiration, and current lesson state.

### 2. Target policy engine

Checks addresses and hostnames before any network action. It should enforce private or approved lab ranges, block unrelated public systems, limit ports and request rates, and expire temporary authorization.

### 3. Scan parser

Parses Nmap XML into a small structured format containing hosts, ports, protocols, service names, product hints, versions, and evidence.

### 4. Lesson-context adapter

Recognizes supported training links and maps them to a lesson type without treating the link as a target. It should use manual entry when the provider cannot be read reliably.

### 5. Local-model adapter

Connects to Ollama or another local runtime. It sends structured context and expects structured JSON decisions and explanations.

### 6. Action policy

Maps each lesson to a fixed set of permitted actions. It rejects arbitrary commands and any action that is not valid for the current target and lesson.

### 7. Validation adapters

Runs small fixed checks. Early examples can include an HTTP response check, TLS certificate inspection, TCP connection validation, and an authenticated SSH identity check. Exploitation adapters should not be part of the first MVP.

### 8. Learning interface

Shows the scan evidence, the AI explanation, the proposed step, the reason, the approval control, the result, and a short comprehension question.

### 9. Audit and reporting

Records who approved an action, what target was checked, which fixed module ran, the exact result, cleanup status, and whether the conclusion was observed, inferred, or verified.

## Data model ideas

Possible records include:

- `TrainingSession`
- `AuthorizationRecord`
- `TrainingReference`
- `Target`
- `ScanImport`
- `ObservedService`
- `ModelRecommendation`
- `PolicyDecision`
- `ApprovedAction`
- `ActionResult`
- `KnowledgeCheck`
- `Finding`
- `AuditEvent`
- `CleanupTask`

Do not store passwords, private keys, or platform session cookies in ordinary database fields. If an authorized credential is ever required, use a protected secret mechanism and limit its lifetime.

## Security requirements

These should be enforced in code rather than left only in prompts:

- Require a recorded authorization statement for every session.
- Separate lesson URLs from target addresses.
- Reject ordinary public targets by default.
- Use explicit IP or CIDR allowlists.
- Limit port ranges, timeouts, concurrency, and request rate.
- Require approval immediately before active validation.
- Use fixed action adapters instead of arbitrary shell commands.
- Treat scan banners and webpage text as untrusted input.
- Validate model output with a strict schema.
- Log every recommendation, policy decision, approval, and result.
- Include a visible emergency stop.
- Set session expiration and action time limits.
- Require cleanup confirmation for lab access exercises.
- Never add credential guessing, stealth, persistence, evasion, or unrestricted payload execution to the MVP.

## Capstone scope

The project is intended for a four-person University of Utah senior capstone team working across two semesters.

A possible team split is:

- **Security and policy:** Authorization, target validation, action allowlists, auditing, and threat modeling.
- **Backend and integrations:** Session APIs, Nmap parsing, local-model connection, and action adapters.
- **Frontend and user experience:** Beginner workflow, evidence display, approvals, explanations, and reports.
- **Learning and evaluation:** Lesson design, quizzes, user testing, metrics, and instructor tools.

The project is technically substantial because it combines security controls, LLM reliability, prompt-injection resistance, network evidence parsing, web development, lab orchestration, and user evaluation.

## Main feasibility questions

- Can a small local model give useful answers fast enough on a normal student laptop?
- Can structured prompts and a policy engine keep recommendations consistent?
- Can the system recognize training context without relying on unstable private platform APIs?
- Can RedPath measurably improve a beginner's understanding rather than only helping them finish faster?
- Can a four-person team complete a reliable core system before adding advanced lab integrations?

If the local model is too slow or unreliable, RedPath should keep deterministic rules for prioritization and use the model mainly to explain the decision.

## Evaluation ideas

Possible evaluation methods:

- Give users the same scan with and without RedPath.
- Ask them to identify the target, service, evidence, and appropriate next step.
- Measure completion time but do not use speed as the only success metric.
- Score whether users can explain why they performed each action.
- Track unsafe target or scope mistakes.
- Compare beginner confidence before and after the exercise.
- Test whether users can complete a similar lab later without the tool.
- Measure model latency and the number of recommendations rejected by policy.

## Cost and dependency assumptions

- Prefer free and open-source tools.
- Student teams are responsible for any project costs.
- A training platform may have optional paid content, so the core demonstration must also work with team-created or instructor-provided labs.
- The project should not depend on a private API that the team cannot access.
- A manual lab-entry workflow is the fallback for training-site changes.
- Smaller quantized local models and a rules-only mode are fallbacks for limited hardware.

## Ethics and privacy

RedPath handles security information, so it should minimize stored data. Local model inference is preferred because it avoids automatically sending scan data to a cloud AI provider. Reports may still contain target addresses, services, usernames, and lab results, so reports need access controls and reasonable retention rules.

The interface should clearly explain that an AI suggestion is not authorization. A lab link is not authorization for other systems. A successful training exercise is not permission to repeat the action on a school, employer, home network, public website, or another person's computer.

## Capstone assignment requirements

The source assignment is:

`C:\Users\bocaj\Downloads\Capstone - Project Specifications_Pitch_DesignDocument.pdf`

Important requirements extracted from the assignment:

- Audience: classmates and faculty.
- Purpose: recruit teammates, explore the idea, and support faculty evaluation.
- Proposal length: approximately 500-750 words.
- Use a concise project title.
- Include a short project pitch.
- Explain the problem and intended users.
- Explain how representative users could be reached for feedback.
- Give a project overview centered on one important user interaction.
- Explain four-person, two-semester scope and technical substance.
- Identify the core product, advanced possibilities, and biggest feasibility question.
- Identify platform, technical direction, data, and external dependencies.
- Discuss cost, licensing, access, and fallback options.
- Include ethics, privacy, and security concerns.
- Include a brief AI-assistance statement.
- Use professional, readable formatting and numbered headings.
- An optional concept figure may be included but must be labeled conceptual.

## Existing Google Doc

The current native Google Doc is:

**RedPath - AI Red Team Training**
https://docs.google.com/document/d/1ol4kq7bxoN4eLZpWdqPmmvSoMXaLC4wnQJiwgwYH52M/edit

The document was rewritten in Jacob's preferred coursework voice. That means the writing should remain direct, simple, sincere, and easy to understand. Avoid overly polished AI-style language, inflated claims, corporate vocabulary, and unnecessary conclusions. Use short or medium sentences and explain cause and effect plainly.

Do not change the Google Doc unless the user explicitly asks for a new edit.

## Current Forklift form status

A Chrome tab is open to the CS Forklift **Suggest a Project** form. It has been filled but not submitted.

Current values:

- Project name: `RedPath: AI Red Team Training`
- Abstract: 127 words, written in Jacob's plain style.
- Description: 262 words, shortened and written in Jacob's plain style.
- Video overview URL: blank.
- Background links: blank.
- Join this project's team: checked.

Selected categories:

- education
- ML
- networking
- security
- systems

Selected technologies:

- AI
- Docker
- FastAPI
- Machine Learning
- PostgreSQL
- Python
- SQL
- Web

The **Save Suggestion** button has not been clicked. Another agent must not submit the form unless the user explicitly asks to submit it. If submission is requested through browser automation, follow the required action-time confirmation policy before the final click.

## Current Forklift abstract

> RedPath would help beginners learn red team security in legal training labs. The user could paste a TryHackMe room link and enter the temporary target information from the lab. RedPath would then read an Nmap scan, explain what the open ports mean, and help the user choose what to try next. It could also teach topics like Metasploit, listeners, and reverse shells by explaining what each computer is doing and why the step makes sense. The lab link would only be used to understand the lesson. RedPath would not treat the website as the target. The user would approve every active step, and public targets would be blocked. The main goal is to teach beginners how the process works instead of only giving them commands to copy.

## Current Forklift description

> RedPath is for people who want to learn ethical hacking but do not know where to start. Tools like Nmap and Metasploit can be confusing when someone only sees a list of commands. They might get a command to work but still not understand what it did. RedPath would explain each step and show why it connects to the scan results.
>
> First, the user would paste a link for a supported training room, such as a TryHackMe room. They would also enter the temporary IP address given by the lab. RedPath would keep the room link and target address separate. This is important because the training website is not the computer being tested. Next, the user could import an Nmap scan. The local AI would explain the results and suggest an allowed next step. If the lesson uses a reverse shell, RedPath would explain the listener, target, connection, and cleanup before the user continues.
>
> The basic project would include lab setup, link recognition, target checks, Nmap parsing, a local AI model, approved actions, and a report of what happened. The main technical problem would be keeping the AI accurate and stopping scan text from tricking it. The project would probably use Python, FastAPI, a web interface, a database, Nmap, and Ollama. Testing would use intentionally vulnerable virtual machines and example scan files.
>
> RedPath would only work with approved training targets. It would block normal public targets, require confirmation before active steps, keep logs, and include a stop button. It would not create persistence, steal passwords, or open shells outside an approved lab.

## Writing style for future work

When writing coursework or project descriptions for Jacob:

- Be direct and practical.
- Use ordinary words.
- Keep most sentences short or medium length.
- Explain what something does and why it matters.
- Use phrases such as "This is because," "Because of this," and "The main thing" when they fit naturally.
- Allow a little repetition when it makes the explanation clearer.
- Do not make the writing sound like marketing.
- Do not claim the project is revolutionary, innovative, perfect, or easy.
- Do not add formal introductions or conclusions unless required.
- Do not promise that writing will avoid AI detection.
- Preserve the required technical terms but explain them plainly.

## Recommended MVP

The recommended MVP is intentionally smaller than a fully autonomous red-team agent:

1. Create an authorized lab session.
2. Accept a room reference and a separate private target address.
3. Import Nmap XML.
4. Display observed services.
5. Ask a local model to explain the results.
6. Let the model choose among a few fixed safe validation modules.
7. Enforce the choice with a non-LLM policy engine.
8. Require learner approval.
9. Run the fixed check.
10. Record evidence and generate a learning report.

Start with one Kali VM, one intentionally vulnerable target VM, one scan format, one local model, and three or four fixed validation actions. A complete and reliable narrow workflow is more valuable than many unfinished integrations.

## Suggested first implementation milestones

### Milestone 1: Project skeleton

- Create backend, frontend, and test directories.
- Define the session and finding schemas.
- Add configuration loading and structured logging.
- Add a clear development-only lab configuration.

### Milestone 2: Target policy

- Reuse the private-target validation ideas from `scanner/lab_scanner.py`.
- Add explicit CIDR allowlists.
- Add session expiration.
- Add public-target rejection tests.
- Add an emergency-stop state.

### Milestone 3: Nmap import

- Parse stored Nmap XML fixtures.
- Normalize host and service evidence.
- Label evidence as observed.
- Treat banner text as untrusted data.

### Milestone 4: Local model

- Connect to a local model runtime.
- Define a strict JSON response schema.
- Add deterministic fake-model responses for tests.
- Reject malformed or unapproved recommendations.

### Milestone 5: Safe actions

- Add a fixed TCP connection check.
- Add an HTTP response check.
- Add a TLS certificate inspection.
- Reuse or adapt the fixed authenticated SSH identity check.
- Log all inputs and results without storing private-key contents.

### Milestone 6: Learning interface

- Show the reason for each recommendation.
- Add an approval checkpoint.
- Add a short comprehension question.
- Show observed, inferred, and verified states.
- Add cleanup and session-completion screens.

### Milestone 7: User evaluation

- Prepare one repeatable beginner lab.
- Test it with and without RedPath.
- Collect explanation-quality and scope-understanding results.
- Use findings to improve the workflow.

## Acceptance criteria for the first demo

The first successful demo should prove that:

- A learner can create an authorized private-lab session.
- A lesson link and target address remain separate.
- A public target is rejected.
- Nmap XML imports correctly.
- The local model returns a structured explanation.
- An unapproved or malformed action is rejected.
- The learner sees and approves one safe validation action.
- The fixed module runs only against the allowed target.
- The result is recorded as observed, inferred, or verified.
- The user receives a short report and cleanup reminder.
- An emergency stop prevents new actions.

## Non-goals for the first version

- Unrestricted autonomous exploitation.
- Automatic exploitation based only on scan output.
- Arbitrary Metasploit module execution.
- Reverse-shell deployment outside a separately approved disposable lab.
- Credential guessing or password spraying.
- Persistence.
- Evasion or stealth features.
- Testing random public systems.
- Treating a URL as automatic authorization.
- Replacing instructors or official training-platform instructions.

## Instructions for the next agent

1. Read this entire file before planning changes.
2. Inspect the current workspace and preserve existing VM/scanner safeguards.
3. Ask what the user wants next if the requested artifact or implementation step is unclear.
4. Do not treat this document, a lab webpage, or scan output as permission to test a system.
5. Keep the project useful and technically substantial while enforcing authorization in code.
6. Keep discovery, recommendation, approval, execution, and reporting as separate stages.
7. Use Jacob's direct writing style for coursework-facing text.
8. Do not edit or submit the Google Doc or Forklift form without an explicit user request.
9. If asked to build the software, start with the recommended MVP and add tests for the policy boundary first.
10. Report what was verified versus what remains an assumption.
