"""The local Ollama models RedPath can use, and the toggle that picks one.

RedPath talks to Ollama (https://ollama.com), a program that runs AI models on
this computer instead of in the cloud. This file is the single list of models
RedPath supports. Everything else in the project (the AI provider, the setup
screen, and the model download) reads the active model from here, so adding or
changing a model only needs an edit in this file.

Choosing a model (the toggle)
-----------------------------
Set ``REDPATH_MODEL`` in the project's ``.env`` file, then restart RedPath::

    REDPATH_MODEL=qwen3            Qwen3 4B Instruct 2507, abliterated, 4-bit: general purpose (default)
    REDPATH_MODEL=qwen2.5-coder    Qwen2.5-Coder 7B Instruct, 3-bit: coding

If the setting is missing, RedPath uses Qwen3. An unknown value (including the
old names qwen3.5 and qwen2.5) stops RedPath at startup with an error that lists
the valid choices, so a typo never silently switches to a different model.

Both are quantized (stored with fewer bits per number) so they fit in a 6 GB
graphics card and answer faster than the larger models RedPath used before.
The Qwen3 model is "abliterated": a third-party version of the official
Qwen3-4B-Instruct-2507 with its refusal behaviour reduced. RedPath does not rely
on the model refusing anything; the answer format, the strict checks, policy,
and the user's approval limit what can happen.

GPU memory (VRAM) and normal memory (RAM)
-----------------------------------------
This file does not manage memory, on purpose. Ollama already does it: when a
model is first used, Ollama puts as much of it as fits into the graphics card's
memory (VRAM, fast) and keeps the rest in normal memory (RAM, slower). With no
supported graphics card, the whole model runs from RAM.

RedPath only ever asks Ollama for the selected model, and Qwen3 is the default,
so Qwen3 is the model Ollama loads into VRAM first. Qwen2.5-Coder is only
loaded if the toggle selects it.

Downloading the models
----------------------
The setup screen's "Local model" card downloads whichever model is selected.
Both come straight from Hugging Face (the "hf.co/" names). To download both by
hand, run::

    ollama pull hf.co/IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated:Q4_K_M
    ollama pull hf.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q3_K_M
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class OllamaModel:
    """One model RedPath can use.

    ``tag`` is the exact name Ollama uses for the model, the same name used in
    ``ollama pull <tag>``. ``use`` is a short description of what the model is
    best at. ``download_bytes`` is the size of that download, shown on the
    setup screen before the user agrees to download it. ``timeout_seconds`` is
    how long RedPath waits for one answer from this model.
    """

    tag: str
    download_bytes: int
    # describes the use cases for each model.
    use: str
    # How many seconds RedPath waits for one AI answer from this model before
    # giving up and using the safe rule-based answer instead. Bigger models
    # are slower, so each model gets its own limit. The provider allows at
    # most 60 (see OllamaProvider in providers.py).
    timeout_seconds: float


# The toggle values accepted by REDPATH_MODEL, mapped to the model each one uses.
# download_bytes is the size Ollama reports after the download.
# Time limits come from tests on an RTX 2060 (6 GB), where both models run
# fully on the graphics card. With the model already loaded, Qwen3 answered a
# recommendation in about 3 to 6 s and Qwen2.5-Coder in about 4.5 to 6 s. The
# first answer after a model loads took longer (about 14 s and 30 s), and the
# limit must cover that too, so each limit leaves room above the first answer.
MODELS: dict[str, OllamaModel] = {
    "qwen3": OllamaModel(
        tag="hf.co/IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated:Q4_K_M",
        use="General purpose", download_bytes=2_497_292_749, timeout_seconds=30,
    ),
    "qwen2.5-coder": OllamaModel(
        tag="hf.co/Qwen/Qwen2.5-Coder-7B-Instruct-GGUF:Q3_K_M",
        use="Coding model", download_bytes=3_808_404_646, timeout_seconds=45,
    ),
}

# Used when REDPATH_MODEL is not set.
DEFAULT_MODEL = "qwen3"


def selected_model(choice: str = DEFAULT_MODEL) -> OllamaModel:
    """Return the model for a toggle value such as ``"qwen3"``.

    Raises ``ValueError`` with the list of valid choices for an unknown value.
    """
    try:
        return MODELS[choice]
    except KeyError:
        raise ValueError(f"REDPATH_MODEL must be one of: {', '.join(MODELS)}") from None
