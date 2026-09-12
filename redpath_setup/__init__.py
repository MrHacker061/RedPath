"""First-run setup artifacts and component status models."""

from .downloads import (
    ArtifactVerificationError,
    DownloadCancelledError,
    DownloadError,
    HTTPSRedirectHandler,
    InsecureDownloadError,
    download_verified,
)
from .manifest import Artifact, KALI_ARTIFACT, OLLAMA_ARTIFACT
from .state import SetupStage

__all__ = [
    "Artifact",
    "ArtifactVerificationError",
    "DownloadCancelledError",
    "DownloadError",
    "HTTPSRedirectHandler",
    "InsecureDownloadError",
    "KALI_ARTIFACT",
    "OLLAMA_ARTIFACT",
    "SetupStage",
    "download_verified",
]
