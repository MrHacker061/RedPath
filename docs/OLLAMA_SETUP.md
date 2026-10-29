# RedPath Ollama setup

RedPath uses Ollama only as a local recommendation and explanation provider. It
does not give Ollama a shell, SSH connection, scanner, or action-execution tool.
All proposals must still pass application policy and human approval.

## Supported models

RedPath supports two local models. The list lives in `redpath_ai/models.py`,
which is the only file to edit when adding or changing a model.

| Toggle value | Ollama model | Download size | Notes |
| --- | --- | --- | --- |
| `qwen3.5` (default) | `qwen3.5:9b` | about 6.1 GiB | Newer and stronger; the default |
| `qwen2.5` | `qwen2.5:7b-instruct-q4_K_M` | about 4.4 GiB | Smaller and faster on modest hardware |

Install Ollama on the Windows host, then download the models:

```powershell
ollama pull qwen3.5:9b
ollama pull qwen2.5:7b-instruct-q4_K_M
```

The setup screen's **Local model** card can also download the selected model
after you consent.

## Switching models

Set `REDPATH_MODEL` in the project's `.env` file and restart RedPath:

```text
REDPATH_MODEL=qwen3.5
```

Use `qwen2.5` to switch to Qwen 2.5. If the setting is missing, RedPath uses
Qwen 3.5. An unknown value stops RedPath at startup with an error that lists the
valid choices. The setup screen's model card always shows the selected model.

## GPU memory (VRAM) and normal memory (RAM)

RedPath does not manage memory itself. Ollama already loads as much of a model
as fits into the graphics card's memory (VRAM) and keeps the rest in normal
memory (RAM). Without a supported graphics card, the model runs from RAM only.

RedPath only asks Ollama for the selected model, so the default (Qwen 3.5) is
the model loaded into VRAM first. On a GPU with 6 GB of VRAM, Qwen 3.5 does not
fully fit, so part of it runs from RAM and answers are slower. Qwen 2.5 fits
better on smaller GPUs. To see where a loaded model is running, use:

```powershell
ollama ps
```

The `PROCESSOR` column shows the GPU and CPU split, for example `40%/60% CPU/GPU`.

## Thinking mode

Qwen 3.5 can "think" out loud before it answers. RedPath turns this off on every
request (`"think": false`) because it slows answers down and can break the
strict JSON format RedPath requires. Qwen 2.5 has no thinking mode and ignores
the setting.

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
