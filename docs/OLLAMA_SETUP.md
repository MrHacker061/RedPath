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

Model arguments remain untrusted until `ProposedStep.validate_against` checks
their exact names and types against a trusted action definition. Target IDs must
equal the authorized context target, while ports and protocols must match a
supporting finding. `to_canonical_proposal` then emits Worker 1's exact backend
proposal shape. The provider exposes stable `AI_*` result codes for sanitized
audit records; raw exceptions and model content should never be used as codes.

Do not fine-tune the MVP. Test prompts, reviewed examples, keyword retrieval,
and evaluation scenarios first. Consider a LoRA adapter only after repeated,
measured failures show that prompting and retrieval are not enough.
