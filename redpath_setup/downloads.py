"""HTTPS-only, checksum-verified streaming downloads."""

from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path
from threading import Event
from tempfile import NamedTemporaryFile
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .manifest import Artifact

CHUNK_SIZE = 1024 * 1024


class DownloadError(RuntimeError):
    """Base class for safe setup download failures."""


class ArtifactVerificationError(DownloadError):
    """Downloaded bytes did not match the pinned artifact."""


class DownloadCancelledError(DownloadError):
    """The caller cancelled a download."""


class InsecureDownloadError(DownloadError):
    """The requested URL or redirect was not HTTPS."""


def _response_url(response: object, fallback: str) -> str:
    geturl = getattr(response, "geturl", None)
    if callable(geturl):
        return str(geturl())
    return str(getattr(response, "url", fallback))


def _content_length(response: object) -> int | None:
    headers = getattr(response, "headers", None)
    value = headers.get("Content-Length") if headers is not None and hasattr(headers, "get") else None
    if value is None:
        getheader = getattr(response, "getheader", None)
        value = getheader("Content-Length") if callable(getheader) else None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def download_verified(
    artifact: Artifact,
    destination: Path,
    progress: Callable[[int, int | None], None],
    cancelled: Event,
    opener=urlopen,
) -> Path:
    """Download one pinned artifact into *destination* and atomically publish it."""
    if urlparse(artifact.url).scheme != "https":
        raise InsecureDownloadError("artifact URL must use HTTPS")

    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    final_path = destination / artifact.filename
    temporary_path: Path | None = None

    try:
        if cancelled.is_set():
            raise DownloadCancelledError("download cancelled")
        request = Request(artifact.url, headers={"User-Agent": "RedPath-Setup/1"})
        with opener(request) as response:
            if urlparse(_response_url(response, artifact.url)).scheme != "https":
                raise InsecureDownloadError("download redirected to a non-HTTPS URL")
            total = _content_length(response)
            progress(0, total)
            digest = hashlib.sha256()
            downloaded = 0
            with NamedTemporaryFile(dir=destination, prefix=f".{artifact.filename}.", suffix=".tmp", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                while True:
                    if cancelled.is_set():
                        raise DownloadCancelledError("download cancelled")
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    temporary.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    progress(downloaded, total)
            if cancelled.is_set():
                raise DownloadCancelledError("download cancelled")
            if not hmac.compare_digest(digest.hexdigest(), artifact.sha256.lower()):
                raise ArtifactVerificationError(f"SHA-256 mismatch for {artifact.name}")
        os.replace(temporary_path, final_path)
        temporary_path = None
        return final_path
    except DownloadError:
        raise
    except Exception as exc:
        raise DownloadError(f"download failed for {artifact.name}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
