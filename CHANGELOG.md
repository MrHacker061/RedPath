# Changelog

## [0.1.0] - 2026-09-12

### Added

- Native Windows desktop app and per-user installer.
- Guided setup for local Ollama and managed Kali on WSL2.
- Authorized-lab sessions, scan evidence import, fixed learning actions, approvals, emergency stop, audit history, and learning reports.
- Exact setup download-size disclosure before consent.

### Changed

- Local Ollama is the default recommendation provider, with a deterministic rule-based fallback when the model is unavailable or returns invalid output.

### Security

- Ollama requests are restricted to loopback, ignore ambient proxy settings, reject redirects, and validate structured responses before proposals reach policy checks.
- Action execution remains limited to fixed allowlisted checks for explicitly authorized private lab targets.

### Release notes

- This is an unsigned development release for Windows 11 x64.
- Clean-machine, visible-window, real-model, managed-Kali, and authorized real-lab validation remain open release gates.
