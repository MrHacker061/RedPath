# RedPath

RedPath is an authorized-lab cybersecurity learning project. **This checkout is a prototype**, not a downloadable cross-platform desktop app. It currently contains a FastAPI/SQLite backend, static frontend, Ollama recommendation provider, Nmap evidence import, and authorized scanner. The old Windows VM implementation has been removed. There is currently **no runnable Kali environment** in this checkout. The native window, Docker Compose stack, required Kali container, two managed terminals, and selected Qwen3 integration are not implemented yet.

## Current checkout

```powershell
python -m pip install -r requirements.txt
python -m pytest
```

The new `redpath_desktop.launcher`, `redpath_kali.terminal`, `redpath_ai.compose`, and `redpath.checks` modules are typed **placeholders**. Calling them raises `NotImplementedError`; they are not wired into the running API or frontend. Do not interpret the target architecture as an available installer or a working `docker compose up` workflow.

## Project documents

- [Target architecture and current-versus-planned inventory](docs/REDPATH_ARCHITECTURE.md)
- [Non-executable component contracts](docs/REDPATH_CONTRACTS.md)
- [Docker Compose diagram instructions for Lucidchart](docs/REDPATH_CONTAINER_FLOW.md)
- [Current and planned Ollama setup](docs/OLLAMA_SETUP.md)
- [Historical project context](docs/REDPATH_CONTEXT.md)
- [Team task list](docs/REDPATH_IMPLEMENTATION_TASKS.md)

Only test systems you own or are explicitly authorized to use. Keep lesson links separate from authorized target addresses. The AI does not get shell access or independent action authority.
