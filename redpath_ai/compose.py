"""Planned private Ollama connection; the existing host provider is separate."""

MODEL_SOURCE: str = "hf.co/IamLucif3r/Qwen3-4B-Instruct-2507-Abliterated:Q4_K_M"


def connect_ollama() -> None:
    raise NotImplementedError("Compose Ollama connection is not implemented")
