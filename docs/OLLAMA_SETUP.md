# RedPath Ollama setup

**Status:** The host-loopback provider below exists today. `redpath_ai.compose.connect_ollama` is only a typed placeholder that raises `NotImplementedError`; the Compose/Ollama setup and selected Qwen3 model are not integrated. See [architecture](REDPATH_ARCHITECTURE.md) and [contracts](REDPATH_CONTRACTS.md).

## Existing provider

`redpath_ai/providers.py` currently defines a local `OllamaProvider` that accepts only `http://127.0.0.1:11434`, defaults to `qwen2.5:7b-instruct-q4_K_M`, and returns structured recommendations/explanations with a deterministic fallback. That 7B name is the **current code default**, not the selected target model. The existing provider does not give Ollama a shell, SSH connection, scanner, or action-execution tool. Its strict response schema and `ProposedStep.validate_against` check untrusted output against known findings and fixed action definitions; backend policy and approval remain separate.

For this existing host-based prototype only, install Ollama separately and pull its current configured model:

```powershell
ollama pull qwen2.5:7b-instruct-q4_K_M
```

## Planned Compose model

The selected evaluation candidate is [`IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated` Q4_K_M](https://huggingface.co/IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated), served by a private Ollama container with persistent model storage. The native launcher should guide a one-time online image/model download and report progress or failures. The app would call Ollama by its private Compose service name, **not** by the current hard-coded loopback URL. Neither the model nor the app container receives the host Docker socket; Ollama has no shell or target access.

The model card offers an Ollama path but discusses chat-template compatibility and reports only a small native tool-call smoke test, not dependable multi-step tool use. A future implementation must validate the exact template and tool schemas, measure failure rates and CPU latency, pin the revision and artifact digest, and review redistribution terms before bundling it. The approximately 2.5 GB Q4_K_M file is a download/storage figure, not a total RAM or GPU requirement for the app, Kali, Ollama, and host runtime. No low-end performance floor or tool reliability has been verified.

AI tools in the [proposed contracts](REDPATH_CONTRACTS.md) are read-only context providers. An active check is only a proposal that requires exact-target policy validation, learner approval, and audit. If Ollama is missing or slow, terminal and evidence functions remain usable with a visible AI-unavailable state. No alternate model is selected yet.
