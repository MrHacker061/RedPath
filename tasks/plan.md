# RedPath Compose MVP implementation plan

**Historical roadmap discrepancy notice:** This roadmap preserves team assignments, estimates, dates, and GitLab links, but its optional Kali VM, browser-first, and 7B-model assumptions are outdated. The repository VM code has been removed; any related task must be reconciled before work starts. The agreed first-version target requires a native desktop window and a Kali container inside Compose, with [architecture](../docs/REDPATH_ARCHITECTURE.md) and [contracts](../docs/REDPATH_CONTRACTS.md) as the design source. Team owners should reconcile GitLab work items separately; this repository update did not change them.

Status: planning only. The implementation tasks are tracked in the [RedPath GitLab work items](https://capstone.cs.utah.edu/redpath/redpath/-/work_items), with [#28](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/28) as the ordered roadmap. This file is an index and records decisions and risks; it is not a second task checklist.

The GitLab roadmap now records assignees, due dates, and total-hour estimates. They are planning estimates, not commitments from the teammates. Foundation runs September 24–October 2, the Compose stack October 5–16, the learner flow October 19–30, and the delivery gate November 2–13, 2026. The optional VM adapter runs in parallel.

| Teammate | Main workstream | Estimated hours |
| --- | --- | ---: |
| Jacob Arens | VM/lab integration, scanner validation, restricted worker | 51 (includes 8 optional VM hours) |
| Jacob Tolman | Docker/Compose, app and Ollama packaging | 49 |
| Chris Ventura | Policy, sessions, AI flow, release coordination | 47 |
| Bryan Munoz Barron | Dashboard, evidence, reports, tests, desktop packaging | 47 |

Total: 194 hours, of which 186 hours are on the Compose MVP path. The per-item hour split and due date are in GitLab [#28](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/28).

## Goal

Build a one-computer Docker Compose version of RedPath that a beginner can use through a local UI or desktop window for explicitly authorized labs. The learner enters a lesson and separate target, imports or requests bounded evidence, receives a local AI explanation, approves any active check, and can review a report. The model never gets execution authority.

## Architecture decisions to confirm

- Compose is the default local runtime. Kubernetes is outside the MVP.
- Use separate app, Ollama, and restricted check-worker services, plus persistent app-data and model volumes.
- Publish only the app UI/API to host loopback. Worker target access requires allowlist, exact approval, and independent revalidation; Compose networking alone is not the authorization boundary.
- The headless Kali VM is optional/legacy, not a requirement for the Compose MVP.
- Choose which repository is canonical before wiring CI or release automation; the GitLab project currently contains planning and a README while this workspace uses the GitHub remote.

## Ordered task index

### Foundation

1. [#14 Decide the code source of truth](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/14)
2. [#1 Define the Compose-first architecture](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/1)
3. [#8 Research cross-OS Docker requirements](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/8)
4. [#10 Validate clean developer setup](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/10)
5. [#11 Evaluate a local Ollama model](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/11)
6. [#3 Validate private-lab scanner safety](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/3)

Checkpoint: agree on lab scope, canonical repository, model/hardware floor, and an architecture that another teammate can review.

### Compose foundation

7. [#16 Build the app image and same-origin UI/API](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/16)
8. [#17 Run Ollama with persistent model storage](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/17)
9. [#19 Enforce target policy, approval, and stop](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/19)
10. [#18 Build the restricted worker](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/18)
11. [#24 Wire Compose services, networks, volumes, and health](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/24)

Checkpoint: clean start/stop, loopback-only UI, persistent data/models, and a denied target cannot reach the worker.

### Learner flow

12. [#2 Finish dashboard health](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/2)
13. [#20 Complete learner sessions](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/20)
14. [#21 Connect Nmap evidence and approved live checks](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/21)
15. [#22 Connect AI explanations and suggestions](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/22)
16. [#23 Save audit history and export reports](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/23)

Checkpoint: a beginner can complete one authorized session and explain what was observed versus inferred.

### Delivery gate

17. [#25 Run CI and end-to-end safety tests](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/25)
18. [#26 Package the desktop window](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/26)
19. [#27 Complete release and usability review](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/27)

Optional parallel work: [#29 Validate the headless Kali VM adapter](https://capstone.cs.utah.edu/redpath/redpath/-/work_items/29). It must not block the Compose MVP release gate.

Checkpoint: tested install, rollback, security review, beginner walkthrough, and explicit team approval before publishing. The roadmap is not release authorization.

## Risks and open decisions

- Docker and a training-platform VPN may need separate installation and setup. The installer must disclose these requirements.
- Ollama model size and memory use may exclude lower-end hosts. Select and test a CPU fallback.
- Existing backend loopback validation needs a safe container-specific change without exposing the host API to the LAN.
- GitHub and GitLab currently differ. The team must choose a canonical repository and review process in #14. Assigned owners and dates are provisional planning values and should be reviewed at the next team meeting.
- Preserve the authorization boundary through imports, model output, worker transport, reports, and emergency stop. Test denial and failure paths, not only a successful lab.
