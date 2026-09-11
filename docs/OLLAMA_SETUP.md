# RedPath Ollama setup

RedPath uses Ollama only as a local recommendation and explanation provider. It
does not give Ollama a shell, SSH connection, scanner, or action-execution tool.
All proposals must still pass application policy and human approval.

## Suggested MVP model

Install Ollama on the Windows host, then download the configured quantized model:

```powershell
ollama pull qwen2.5:7b-instruct-q4_K_M
```

The provider accepts only `http://127.0.0.1:11434`, so Ollama is not exposed to
the browser or LAN. Model output is checked against a strict schema and against
the exact finding IDs, action names, and argument names supplied by the backend.
Invalid output is retried once and then replaced by the deterministic safe
fallback.

Do not fine-tune the MVP. Test prompts, reviewed examples, keyword retrieval,
and evaluation scenarios first. Consider a LoRA adapter only after repeated,
measured failures show that prompting and retrieval are not enough.
