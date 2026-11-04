# RedPath Ollama setup

RedPath uses Ollama only as a local recommendation and explanation provider. It
does not give Ollama a shell, SSH connection, scanner, or action-execution tool.
All proposals must still pass application policy and human approval.

## Supported models

RedPath supports two local models. The list lives in `redpath_ai/models.py`,
which is the only file to edit when adding or changing a model.

| Toggle value | Ollama model | Download size | Notes |
| --- | --- | --- | --- |
| `qwen3` (default) | `hf.co/IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated:Q4_K_M` | about 2.3 GiB | Qwen3 4B Instruct 2507, 4-bit; general purpose; the default |
| `qwen2.5-coder` | `hf.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q3_K_M` | about 3.5 GiB | Qwen2.5-Coder 7B Instruct, 3-bit; tuned for code |

Both models are quantized (stored with fewer bits per number) so they fit in a
6 GB graphics card and answer quickly. Both download straight from Hugging Face.

The Qwen3 model is "abliterated": a third-party version of the official
Qwen3-4B-Instruct-2507 with its refusal behaviour reduced. RedPath does not rely
on the model refusing anything. The answer format, the strict checks, policy,
and the user's approval limit what a recommendation can do.

Install Ollama on the Windows host, then download the models:

```powershell
ollama pull hf.co/IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated:Q4_K_M
ollama pull hf.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q3_K_M
```

The setup screen's **Local model** card can also download the selected model
after you consent.

## Switching models

Set `REDPATH_MODEL` in the project's `.env` file and restart RedPath:

```text
REDPATH_MODEL=qwen3
```

Use `qwen2.5-coder` to switch to Qwen2.5-Coder. If the setting is missing,
RedPath uses Qwen3. An unknown value, including the old names `qwen3.5` and
`qwen2.5`, stops RedPath at startup with an error that lists the valid choices. The setup screen's model card always shows the selected model.

## GPU memory (VRAM) and normal memory (RAM)

RedPath does not manage memory itself. Ollama already loads as much of a model
as fits into the graphics card's memory (VRAM) and keeps the rest in normal
memory (RAM). Without a supported graphics card, the model runs from RAM only.

RedPath only asks Ollama for the selected model, so the default (Qwen3) is the
model loaded into VRAM first. Both models are small enough to run mostly or
fully from VRAM on a GPU with 6 GB. To see where a loaded model is running, use:

```powershell
ollama ps
```

The `PROCESSOR` column shows the GPU and CPU split, for example `40%/60% CPU/GPU`.

## Thinking mode

Some models can "think" out loud before they answer. RedPath turns this off on
every request (`"think": false`) because it slows answers down and can break the
strict JSON format RedPath requires. Neither current model has a thinking mode
(Qwen3-4B-Instruct-2507 is a non-thinking model), so both ignore the setting.

## Running RedPath in Docker

Inside a container, `127.0.0.1` means the container itself, not your computer,
so RedPath in Docker cannot reach Ollama at the normal address. Ollama stays
installed on your computer, and `docker-compose.yml` points the container at
Docker's name for the host computer instead:

```yaml
REDPATH_OLLAMA_URL: http://host.docker.internal:11434
```

RedPath accepts this second address only inside a container. Docker creates a
marker file (`/.dockerenv`) in every container, and the provider checks for it
(`CONTAINER_MARKERS` in `redpath_ai/providers.py`). The Docker launcher in
`redpath/container.py` uses the same markers. On Windows itself, Docker Desktop
maps `host.docker.internal` to your computer's network address, so the native
app refuses that address and always uses `127.0.0.1`. Do not put
`REDPATH_OLLAMA_URL` in `.env`: the native app reads `.env` too, and would stop
at startup with an error.

Limits in Docker:

- Install Ollama and download models on your computer, not from the Docker
  setup screen. Its "Install Ollama" and "Download model" buttons run inside the
  container, where Ollama is not installed.
- Kali still needs WSL on Windows and does not work from Docker.
- On Linux, Ollama listens only on `127.0.0.1` by default, which containers
  cannot reach. Start it with `OLLAMA_HOST=0.0.0.0` if Docker cannot connect,
  and block port 11434 from other computers with a firewall, since that setting
  makes Ollama listen on every network. Docker Desktop on Windows works without
  this.

## Output checks

The provider accepts only `http://127.0.0.1:11434`, plus the Docker host address
inside a container, so Ollama is not exposed to the browser or LAN. Model output is checked against a strict schema and against
the exact finding IDs, action names, and argument names supplied by the backend.
Invalid output is replaced right away by the deterministic safe fallback. It is
not retried: RedPath asks with `temperature` 0, so asking the same question
again returns the same answer.

Model arguments remain untrusted until `ProposedStep.validate_against` checks
their exact names and types against a trusted action definition. Target IDs must
equal the authorized context target, while ports and protocols must match a
supporting finding. `to_canonical_proposal` then emits Worker 1's exact backend
proposal shape. The provider exposes stable `AI_*` result codes for sanitized
audit records; raw exceptions and model content should never be used as codes.

Do not fine-tune the MVP. Test prompts, reviewed examples, keyword retrieval,
and evaluation scenarios first. Consider a LoRA adapter only after repeated,
measured failures show that prompting and retrieval are not enough.
