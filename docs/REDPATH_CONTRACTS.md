# RedPath component contracts

**Status:** Non-executable design contracts. Some typed functions now exist as `NotImplementedError` placeholders; they are not live routes, implemented event streams, or tested connections. The old VM adapter has been removed. Read the [architecture](REDPATH_ARCHITECTURE.md) first.

## Already implemented

The current Python contracts in `redpath/contracts.py` include `NormalizedFinding`, `AIProposal`, `PolicyDecisionContract`, `ActionResultContract`, `LessonSourceContract`, `AuthorizedTargetContract`, `SessionDetail`, and scan-import contracts. `redpath_ai/schemas.py` defines `RecommendationContext`, `ProposedStep`, `Explanation`, and `ProviderHealth`; `redpath_ai/providers.py` has loopback-only `OllamaProvider` and `RuleBasedProvider`. Existing routes include `/api/v1/health` and session create/list/detail/close, lesson-source, target, scan-import, and explanation under `/api/v1/sessions`. There is **no live terminal or launcher API**. The new launcher, Kali terminal, Compose Ollama, and approved-check functions raise `NotImplementedError` and are not wired into these routes.

## Proposed contract: Launcher and Compose

The native launcher alone owns host Docker access. Its conceptual operations are `check_prerequisites`, `acquire_pinned_artifacts`, `start_stack`, `get_service_health`, and `stop_stack`. Each request/result needs a stable operation ID, lifecycle state, bounded progress, and a user-facing error code with retry guidance. Distinguish missing runtime, permission/virtualization issue, image/model download failure, app unhealthy, Kali/SSH unavailable, and Ollama unavailable. The launcher must not pass the host Docker socket into any container. Exact installer behavior and stop-on-window-close behavior remain open decisions.

## Proposed contract: Desktop and app

The desktop talks to a local, loopback-scoped app/API boundary. Session selection, authorized target, lesson source, terminal layout, AI panel state, and evidence navigation are separate concerns. Existing session routes can be reused only after their current behavior is verified; new terminal/health event routes and transport are still to be designed. A lesson URL never populates the authorized target automatically. No host/LAN SSH endpoint is implied.

## Proposed contract: Terminal session

Each terminal belongs to a `session_id` and has a unique `terminal_id` plus a Kali connection state: `connecting`, `ready`, `disconnected`, `closing`, or `closed`. The conceptual lifecycle is create, attach/reconnect, resize, and close. The app owns private SSH and credentials. The learner owns the input byte stream. An AI request can receive only a learner-selected, length-bounded output excerpt with its session/terminal provenance; it cannot write terminal input, open a shell, or obtain SSH credentials. Reconnection must distinguish a surviving remote shell from a newly created one and never silently replay learner input. Transport, credential storage, and retention limits need a later security design.

## Proposed contract: AI tools and model

Read-only backend-owned tools provide (1) current session/lesson summary, (2) exact authorized target summary, (3) normalized findings with evidence state and provenance, (4) a learner-selected bounded terminal excerpt, and (5) reviewed learning notes. Every request carries a session ID and bounded arguments; every response carries source/provenance and an explicit size limit. Tool names and arguments are schema-validated by the backend. Tool output, scan content, and model output remain untrusted; a model request never directly runs an action. There is no general `execute_command` tool.

The selected evaluation candidate is [Qwen3-4B-Instruct-2507-Abliterated Q4_K_M](https://huggingface.co/IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated) via Ollama. A release must pin revision and artifact digest, validate the card's Ollama template compatibility, assess redistribution terms, and measure tool-call reliability, latency, and whole-stack memory. Timeout/invalid response produces an unavailable or safe fallback state, never a command. The current provider's host-loopback URL is not yet a Compose service URL.

## Proposed contract: Approved check

An AI suggestion may become an `AIProposal` only after trusted backend validation. The decision binds `session_id`, exact target identity, registered fixed `action_name`, validated arguments, supporting finding IDs, explicit learner approval, expiry/cancellation state, and an audit/decision ID. A `PolicyDecisionContract` determines allow/deny and reason; an `ActionResultContract` records outcome and evidence. Revalidate target, action, and approval immediately before the check. Denial, cancellation, timeout, or changed target fails closed. This contract applies to **app-initiated checks**, not learner-typed Kali shell commands. Runner placement is undecided.

## Proposed contract: Evidence and audit

A normalized finding retains source, target, observed facts, timestamp/provenance, and one of `observed`, `inferred`, or `verified`. AI interpretation alone cannot promote a finding to verified. Each app-initiated check links proposal, policy decision, learner approval, result/failure, and cancellation state to the exact session and target. Terminal excerpts shared with AI need explicit selection and retention policy; a full shell transcript is not silently sent to the model. No current implementation or test is claimed for these proposed paths.
