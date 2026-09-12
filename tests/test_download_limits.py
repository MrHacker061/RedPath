"""Socket/deadline tests with fake transports, never a real download."""

import hashlib
import io
from dataclasses import replace
from threading import Event, get_ident

import pytest

from redpath_setup import downloads
from redpath_setup.manifest import OLLAMA_ARTIFACT


class Response(io.BytesIO):
    headers = {}

    def geturl(self):
        return "https://example.test/artifact"


def artifact(body=b"first"):
    return replace(OLLAMA_ARTIFACT, filename="a.bin", sha256=hashlib.sha256(body).hexdigest(), size_bytes=len(body))


def test_download_passes_bounded_socket_timeout_to_opener(tmp_path):
    timeouts = []

    def opener(request, *, timeout=None):
        timeouts.append(timeout)
        return Response(b"first")

    assert downloads.download_verified(artifact(), tmp_path, lambda *_: None, Event(), opener).read_bytes() == b"first"
    assert timeouts[0] is not None and 0 < timeouts[0] <= 5


@pytest.mark.parametrize("cancel", [False, True])
def test_stalled_download_cleans_every_partial_without_cross_thread_close(tmp_path, cancel):
    cancelled = Event()
    owner = get_ident()
    reads = []
    closed_by = []

    class Stalled(Response):
        def read(self, size):
            reads.append(size)
            if len(reads) == 1:
                return b"first"
            if cancel:
                cancelled.set()
            raise TimeoutError("read timed out")

        def read1(self, size):
            return self.read(size)

        def close(self):
            closed_by.append(get_ident())
            super().close()

    error = downloads.DownloadCancelledError if cancel else downloads.DownloadError
    with pytest.raises(error):
        downloads.download_verified(artifact(), tmp_path, lambda *_: None, cancelled, lambda *_a, **_k: Stalled())
    assert list(tmp_path.iterdir()) == []
    assert closed_by == [owner]


def test_progressive_download_cannot_extend_absolute_deadline(tmp_path, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(downloads, "monotonic", lambda: now[0], raising=False)

    class Progressive(Response):
        def read(self, size):
            now[0] += 1
            return b"first" if now[0] < 4 else b""

        def read1(self, size):
            return self.read(size)

    with pytest.raises(downloads.DownloadError, match="deadline"):
        downloads.download_verified(artifact(b"first" * 3), tmp_path, lambda *_: None, Event(), lambda *_a, **_k: Progressive(), deadline_seconds=2)
    assert now[0] <= 2
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("cancel", [False, True])
def test_socket_reader_bounds_progressive_headers_and_stalled_body(monkeypatch, cancel):
    now = [0.0]
    monkeypatch.setattr(downloads, "monotonic", lambda: now[0], raising=False)
    cancelled = Event()
    timeouts = []

    class Socket:
        def settimeout(self, value):
            timeouts.append(value)

    class Raw(io.RawIOBase):
        def readinto(self, buffer):
            now[0] += 0.1
            if cancel:
                cancelled.set()
            buffer[0] = 65
            return 1

    reader = downloads._DeadlineReader(Raw(), Socket(), 0.2, cancelled)
    buffer = bytearray(1)
    if cancel:
        with pytest.raises(downloads.DownloadCancelledError):
            reader.readinto(buffer)
    else:
        assert reader.readinto(buffer) == 1
        with pytest.raises(downloads.DownloadError, match="deadline"):
            reader.readinto(buffer)
    assert all(0 < value <= 0.25 for value in timeouts)
    assert now[0] <= 0.2


def test_secure_opener_passes_timeout_through_urllib(monkeypatch):
    calls = []

    class Opener:
        def open(self, request, **kwargs):
            calls.append(kwargs)
            return Response(b"first")

    monkeypatch.setattr(downloads, "build_opener", lambda *handlers: Opener())
    result = downloads._secure_open(object(), timeout=0.2, deadline=downloads.monotonic() + 1, cancelled=Event())
    result.close()
    assert calls == [{"timeout": 0.2}]


@pytest.mark.parametrize("slow", ["none", "headers", "body", "tls"])
def test_default_https_transport_enforces_deadline_with_fake_socket(tmp_path, monkeypatch, slow):
    import ssl
    from urllib.request import ProxyHandler, build_opener

    now = [0.0]
    timeouts = []
    body = b"first"
    headers = b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\n"
    parts = [(0.01, headers), (0.01, body)]
    if slow == "headers":
        parts = [(0.09, headers[:10]), (0.09, headers[10:]), (0.09, body)]
    elif slow == "body":
        parts = [(0.01, headers), (0.09, body[:1]), (0.09, body[1:2]), (0.09, body[2:])]

    class Socket:
        timeout = 0.2

        def settimeout(self, value):
            timeouts.append((now[0], value))
            self.timeout = value

        def setsockopt(self, *_args):
            pass

        def sendall(self, _data):
            pass

        def close(self):
            pass

        def makefile(self, *_args):
            sock = self

            class Raw(io.RawIOBase):
                def readable(self):
                    return True

                def readinto(self, buffer):
                    if not parts:
                        return 0
                    delay, data = parts.pop(0)
                    if delay > sock.timeout:
                        now[0] += sock.timeout
                        raise TimeoutError
                    now[0] += delay
                    buffer[:len(data)] = data
                    return len(data)

            return io.BufferedReader(Raw())

    sock = Socket()

    def connect(_address, timeout, *_args):
        sock.settimeout(timeout)
        now[0] += 0.1 if slow == "tls" else 0.01
        return sock

    def wrap(_context, socket, **_kwargs):
        delay = 0.15 if slow == "tls" else 0.01
        if delay > socket.timeout:
            now[0] += socket.timeout
            raise TimeoutError
        now[0] += delay
        return socket

    monkeypatch.setattr(downloads, "monotonic", lambda: now[0])
    monkeypatch.setattr(downloads, "_connect", connect, raising=False)
    monkeypatch.setattr(ssl.SSLContext, "wrap_socket", wrap)
    monkeypatch.setattr(downloads, "build_opener", lambda *handlers: build_opener(ProxyHandler({}), *handlers))
    if slow == "none":
        assert downloads.download_verified(artifact(), tmp_path, lambda *_: None, Event(), deadline_seconds=0.2).read_bytes() == body
    else:
        with pytest.raises(downloads.DownloadError):
            downloads.download_verified(artifact(), tmp_path, lambda *_: None, Event(), deadline_seconds=0.2)
        assert list(tmp_path.iterdir()) == []
    assert now[0] <= 0.2
    assert all(value <= 0.2 - at for at, value in timeouts)


@pytest.mark.parametrize("cancel", [False, True])
def test_os_resolver_wait_is_bounded_and_cannot_accumulate_threads(monkeypatch, cancel):
    from time import monotonic

    release, finished, cancelled = Event(), Event(), Event()

    def resolver(*_args, **_kwargs):
        try:
            if cancel:
                cancelled.set()
            release.wait(timeout=1)
            return []
        finally:
            finished.set()

    monkeypatch.setattr(downloads.socket, "getaddrinfo", resolver)
    started = monotonic()
    try:
        error = downloads.DownloadCancelledError if cancel else downloads.DownloadError
        with pytest.raises(error):
            downloads._resolve("example.test", 443, monotonic() + 0.05, cancelled)
        assert monotonic() - started < 0.3
        with pytest.raises(downloads.DownloadError, match="resolver"):
            downloads._resolve("example.test", 443, monotonic() + 1, Event())
    finally:
        release.set()
        assert finished.wait(timeout=1)


def test_connect_attempts_share_one_deadline_and_close_timed_out_sockets(monkeypatch):
    now = [0.0]
    sockets = []
    monkeypatch.setattr(downloads, "monotonic", lambda: now[0])
    monkeypatch.setattr(downloads, "_resolve", lambda *_: [(2, 1, 6, "", ("192.0.2.1", 443))] * 2, raising=False)

    class Socket:
        closed = False

        def __init__(self, *_args):
            sockets.append(self)

        def settimeout(self, value):
            self.timeout = value

        def connect(self, _address):
            now[0] += min(0.15, self.timeout)
            raise TimeoutError

        def close(self):
            self.closed = True

    monkeypatch.setattr(downloads.socket, "socket", Socket)
    with pytest.raises((downloads.DownloadError, TimeoutError)):
        downloads._connect(("example.test", 443), 5, None, 0.2, Event())
    assert now[0] <= 0.2
    assert len(sockets) == 2 and all(sock.closed for sock in sockets)
