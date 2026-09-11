"""First-run setup artifacts and persisted component state."""

from .downloads import (
    ArtifactVerificationError,
    DownloadCancelledError,
    DownloadError,
    InsecureDownloadError,
    download_verified,
)
from .manifest import Artifact, KALI_ARTIFACT, OLLAMA_ARTIFACT
from .state import SetupStage, SetupState

__all__ = [
    "Artifact",
    "ArtifactVerificationError",
    "DownloadCancelledError",
    "DownloadError",
    "InsecureDownloadError",
    "KALI_ARTIFACT",
    "OLLAMA_ARTIFACT",
    "SetupStage",
    "SetupState",
    "download_verified",
]
