"""Pinned setup artifacts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Artifact:
    name: str
    version: str
    url: str
    sha256: str
    filename: str

    def __post_init__(self) -> None:
        if not self.name or not self.version:
            raise ValueError("artifact name and version are required")
        if not self.url:
            raise ValueError("artifact URL is required")
        if len(self.sha256) != 64 or any(c not in "0123456789abcdefABCDEF" for c in self.sha256):
            raise ValueError("artifact SHA-256 must be 64 hexadecimal characters")
        if not self.filename or self.filename in {".", ".."} or any(c in self.filename for c in "/\\\x00"):
            raise ValueError("artifact filename must be a simple file name")


OLLAMA_ARTIFACT = Artifact(
    name="ollama",
    version="0.34.0",
    url="https://github.com/ollama/ollama/releases/download/v0.34.0/OllamaSetup.exe",
    sha256="e2b98770fb87f3b4c593c22f2e8eda59bcac1cd7b141f1388c4181a8bf271a72",
    filename="OllamaSetup.exe",
)

KALI_ARTIFACT = Artifact(
    name="kali",
    version="2026.2",
    url="https://kali.download/wsl-images/kali-2026.2/kali-linux-2026.2-wsl-rootfs-amd64.wsl",
    sha256="1b172389e9109e9bb0c3d1fa18eda078271484dbcef8dbee4aab8b1f369466c6",
    filename="kali-linux-2026.2-wsl-rootfs-amd64.wsl",
)
