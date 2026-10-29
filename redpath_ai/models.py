"""The local Ollama models RedPath can use, and the toggle that picks one.

RedPath talks to Ollama (https://ollama.com), a program that runs AI models on
this computer instead of in the cloud. This file is the single list of models
RedPath supports. Everything else in the project (the AI provider, the setup
screen, and the model download) reads the active model from here, so adding or
changing a model only needs an edit in this file.

Choosing a model (the toggle)
-----------------------------
Set ``REDPATH_MODEL`` in the project's ``.env`` file, then restart RedPath::

    REDPATH_MODEL=qwen3.5    Qwen 3.5, 9B: general purpose (default)
    REDPATH_MODEL=qwen2.5    Qwen 2.5, 7B: coding

If the setting is missing, RedPath uses Qwen 3.5. An unknown value stops
RedPath at startup with an error that lists the valid choices, so a typo never
silently switches to a different model.

GPU memory (VRAM) and normal memory (RAM)
-----------------------------------------
This file does not manage memory, on purpose. Ollama already does it: when a
model is first used, Ollama puts as much of it as fits into the graphics card's
memory (VRAM, fast) and keeps the rest in normal memory (RAM, slower). With no
supported graphics card, the whole model runs from RAM.

RedPath only ever asks Ollama for the selected model, and Qwen 3.5 is the
default, so Qwen 3.5 is the model Ollama loads into VRAM first. Qwen 2.5 is only
loaded if the toggle selects it.

Downloading the models
----------------------
The setup screen's "Local model" card downloads whichever model is selected.
To download both by hand, run::

    ollama pull qwen3.5:9b
    ollama pull qwen2.5:7b-instruct-q4_K_M
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class OllamaModel:
    """One model RedPath can use.

    ``tag`` is the exact name Ollama uses for the model, the same name used in
    ``ollama pull <tag>``. ``use`` is a short description of what the model is
    best at. ``download_bytes`` is the size of that download, shown on the
    setup screen before the user agrees to download it.
    """

    tag: str
    download_bytes: int
    # describes the use cases for each model.
    use: str


# The toggle values accepted by REDPATH_MODEL, mapped to the model each one uses.
MODELS: dict[str, OllamaModel] = {
    "qwen3.5": OllamaModel(tag="qwen3.5:9b", use="General purpose", download_bytes=6_550_827_108),
    "qwen2.5": OllamaModel(tag="qwen2.5:7b-instruct-q4_K_M", use="Coding model", download_bytes=4_683_087_332),
}

# Used when REDPATH_MODEL is not set.
DEFAULT_MODEL = "qwen3.5"


def selected_model(choice: str = DEFAULT_MODEL) -> OllamaModel:
    """Return the model for a toggle value such as ``"qwen3.5"``.

    Raises ``ValueError`` with the list of valid choices for an unknown value.
    """
    try:
        return MODELS[choice]
    except KeyError:
        raise ValueError(f"REDPATH_MODEL must be one of: {', '.join(MODELS)}") from None
