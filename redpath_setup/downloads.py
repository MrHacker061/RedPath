"""HTTPS-only, checksum-verified streaming downloads."""

from __future__ import annotations

import hashlib
import hmac
import io
import math
import os
import socket
from http.client import HTTPConnection, HTTPSConnection, HTTPResponse
from pathlib import Path
from threading import Event, Lock, Thread
from tempfile import NamedTemporaryFile
from time import monotonic
from typing import Callable
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener, urlopen

from .manifest import Artifact

CHUNK_SIZE = 1024 * 1024
CONNECT_TIMEOUT_SECONDS = 5.0
READ_TIMEOUT_SECONDS = 0.25
DOWNLOAD_DEADLINE_SECONDS = 1800.0
_resolver_lock = Lock()


class DownloadError(RuntimeError):
    """Base class for safe setup download failures."""


class ArtifactVerificationError(DownloadError):
    """Downloaded bytes did not match the pinned artifact."""


class DownloadCancelledError(DownloadError):
    """The caller cancelled a download."""


class InsecureDownloadError(DownloadError):
    """The requested URL or redirect was not HTTPS."""


class HTTPSRedirectHandler(HTTPRedirectHandler):
    """Reject insecure redirect destinations before urllib follows them."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirect_url = urljoin(req.full_url, newurl)
        if urlparse(redirect_url).scheme.lower() != "https":
            raise InsecureDownloadError("download redirected to a non-HTTPS URL")
        return super().redirect_request(req, fp, code, msg, headers, redirect_url)


def _remaining(deadline: float, cancelled: Event) -> float:
    if cancelled.is_set():
        raise DownloadCancelledError("download cancelled")
    remaining = deadline - monotonic()
    if remaining <= 0:
        raise DownloadError("download deadline exceeded")
    return remaining


def _resolve(host: str, port: int, deadline: float, cancelled: Event) -> list[tuple]:
    """Bound the caller's OS resolver wait, with at most one unresolved worker."""
    _remaining(deadline, cancelled)
    if not _resolver_lock.acquire(blocking=False):
        raise DownloadError("download resolver is still busy")
    done = Event()
    addresses = []

    def resolve() -> None:
        try:
            addresses.extend(socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)[:16])
        except OSError:
            pass
        finally:
            _resolver_lock.release()
            done.set()

    worker = Thread(target=resolve, name="RedPath download DNS", daemon=True)
    try:
        worker.start()
    except BaseException:
        _resolver_lock.release()
        raise
    while not done.is_set():
        cancelled.wait(min(0.02, _remaining(deadline, cancelled)))
    _remaining(deadline, cancelled)
    if not addresses:
        raise DownloadError("download resolver failed")
    return addresses


def _connect(address: tuple[str, int], timeout: float, source_address: tuple[str, int] | None, deadline: float, cancelled: Event) -> socket.socket:
    deadline = min(deadline, monotonic() + timeout)
    for family, kind, protocol, _name, sockaddr in _resolve(*address, deadline, cancelled):
        _remaining(deadline, cancelled)
        sock = socket.socket(family, kind, protocol)
        try:
            sock.settimeout(min(timeout, _remaining(deadline, cancelled)))
            if source_address:
                sock.bind(source_address)
            sock.connect(sockaddr)
            _remaining(deadline, cancelled)
            return sock
        except OSError:
            sock.close()
        except BaseException:
            sock.close()
            raise
    _remaining(deadline, cancelled)
    raise DownloadError("download connection failed")


class _DeadlineReader(io.RawIOBase):
    """Bound each raw socket read, including progressive HTTP/chunk headers."""

    def __init__(self, raw: io.RawIOBase, sock: socket.socket, deadline: float, cancelled: Event):
        self.raw, self.sock = raw, sock
        self.deadline, self.cancelled = deadline, cancelled

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: object) -> int:
        self.sock.settimeout(min(READ_TIMEOUT_SECONDS, _remaining(self.deadline, self.cancelled)))
        try:
            count = self.raw.readinto(buffer)
        except TimeoutError:
            _remaining(self.deadline, self.cancelled)
            raise
        _remaining(self.deadline, self.cancelled)
        return count

    def close(self) -> None:
        # Executed by the downloading thread, never a cancellation thread.
        self.raw.close()
        super().close()


def _secure_open(request: Request, *, timeout: float, deadline: float, cancelled: Event):
    def response(sock: socket.socket, **kwargs: object) -> HTTPResponse:
        result = HTTPResponse(sock, **kwargs)
        result.fp = io.BufferedReader(_DeadlineReader(result.fp.detach(), sock, deadline, cancelled))
        return result

    class Connection(HTTPSConnection):
        response_class = staticmethod(response)

        def connect(self) -> None:
            connect_deadline = min(deadline, monotonic() + timeout)
            self.timeout = _remaining(connect_deadline, cancelled)
            self._create_connection = lambda address, timeout, source_address=None: _connect(address, timeout, source_address, connect_deadline, cancelled)
            HTTPConnection.connect(self)
            # Recompute after TCP/proxy setup so TLS cannot receive a fresh
            # full timeout after that setup consumed most of the deadline.
            self.sock.settimeout(_remaining(connect_deadline, cancelled))
            self.sock = self._context.wrap_socket(self.sock, server_hostname=self._tunnel_host or self.host)
            self.sock.settimeout(min(READ_TIMEOUT_SECONDS, _remaining(deadline, cancelled)))

    class Handler(HTTPSHandler):
        def https_open(self, req):
            _remaining(deadline, cancelled)
            return self.do_open(Connection, req, context=self._context)

    return build_opener(HTTPSRedirectHandler(), Handler()).open(request, timeout=timeout)


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
    *, deadline_seconds: float = DOWNLOAD_DEADLINE_SECONDS,
) -> Path:
    """Download one pinned artifact into *destination* and atomically publish it."""
    if urlparse(artifact.url).scheme != "https":
        raise InsecureDownloadError("artifact URL must use HTTPS")
    if type(deadline_seconds) not in (int, float) or not math.isfinite(deadline_seconds) or not 0 < deadline_seconds <= DOWNLOAD_DEADLINE_SECONDS:
        raise DownloadError("download deadline must be positive and at most 1800 seconds")
    deadline = monotonic() + deadline_seconds

    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    final_path = destination / artifact.filename
    temporary_path: Path | None = None

    try:
        _remaining(deadline, cancelled)
        request = Request(artifact.url, headers={"User-Agent": "RedPath-Setup/1"})
        active_opener = (lambda request, timeout: _secure_open(request, timeout=timeout, deadline=deadline, cancelled=cancelled)) if opener is urlopen else opener
        with active_opener(request, timeout=min(CONNECT_TIMEOUT_SECONDS, _remaining(deadline, cancelled))) as response:
            _remaining(deadline, cancelled)
            if urlparse(_response_url(response, artifact.url)).scheme != "https":
                raise InsecureDownloadError("download redirected to a non-HTTPS URL")
            total = _content_length(response)
            progress(0, total)
            digest = hashlib.sha256()
            downloaded = 0
            with NamedTemporaryFile(dir=destination, prefix=f".{artifact.filename}.", suffix=".tmp", delete=False) as temporary:
                temporary_path = Path(temporary.name)
                while True:
                    _remaining(deadline, cancelled)
                    chunk = response.read1(CHUNK_SIZE)
                    _remaining(deadline, cancelled)
                    if not chunk:
                        break
                    temporary.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    progress(downloaded, total)
            _remaining(deadline, cancelled)
            if not hmac.compare_digest(digest.hexdigest(), artifact.sha256.lower()):
                raise ArtifactVerificationError(f"SHA-256 mismatch for {artifact.name}")
            if downloaded != artifact.size_bytes:
                raise ArtifactVerificationError(f"size mismatch for {artifact.name}")
        _remaining(deadline, cancelled)
        os.replace(temporary_path, final_path)
        temporary_path = None
        return final_path
    except DownloadError:
        raise
    except Exception as exc:
        if cancelled.is_set():
            raise DownloadCancelledError("download cancelled") from None
        raise DownloadError(f"download failed for {artifact.name}") from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass
