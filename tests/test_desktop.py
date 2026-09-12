"""Desktop lifecycle tests: no real sockets, application data, or native windows."""

import importlib
import io
import json
import sys
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from redpath import desktop


class FakeSocket:
    def __init__(self):
        self.closed = False

    def bind(self, address):
        assert address == ("127.0.0.1", 0)

    def getsockname(self):
        return ("127.0.0.1", 43210)

    def close(self):
        self.closed = True


class FakeServer:
    should_exit = False
    force_exit = False

    def run(self, sockets):
        assert len(sockets) == 1
        while not self.should_exit:
            Event().wait(0.001)


@pytest.fixture
def environment(monkeypatch):
    listener = FakeSocket()
    monkeypatch.setattr(desktop.socket, "socket", lambda *_: listener)
    monkeypatch.setattr(desktop, "_create_app", lambda _security: object())
    monkeypatch.setattr(desktop.WindowsInstanceMutex, "acquire", lambda _: None)
    monkeypatch.setattr(desktop.WindowsInstanceMutex, "release", lambda _: None)
    return listener


def test_port_selection_binds_literal_loopback(environment):
    assert desktop.find_loopback_port() == 43210
    assert environment.closed


def test_host_returns_only_after_health_and_stops_idempotently(environment):
    server = FakeServer()
    probe = Mock(return_value=True)
    host = desktop.DesktopHost(server_factory=lambda app, port: server, health_probe=probe)
    try:
        assert host.start() == "http://127.0.0.1:43210"
        assert host.thread.daemon is False
        assert host.start() == "http://127.0.0.1:43210"
        assert probe.call_args.args[0] == "http://127.0.0.1:43210/api/v1/health"
    finally:
        host.stop()
        host.stop()
    assert server.should_exit
    assert host.thread is None
    assert environment.closed


def test_health_timeout_stops_and_joins_server(environment, monkeypatch):
    clock = iter([0, 16])
    monkeypatch.setattr(desktop.time, "monotonic", lambda: next(clock))
    server = FakeServer()
    host = desktop.DesktopHost(server_factory=lambda *_: server, health_probe=lambda *_: False)
    with pytest.raises(desktop.DesktopStartupError, match="DESKTOP_HEALTH_TIMEOUT"):
        host.start()
    assert server.should_exit and host.thread is None
    assert environment.closed


def test_server_failure_has_stable_message_and_cleanup(environment):
    server = FakeServer()
    server.run = Mock(side_effect=RuntimeError("sensitive dependency details"))
    host = desktop.DesktopHost(server_factory=lambda *_: server, health_probe=lambda *_: False)
    with pytest.raises(desktop.DesktopStartupError, match="DESKTOP_SERVER_FAILED") as error:
        host.start()
    assert "sensitive" not in str(error.value)
    assert environment.closed and host.thread is None


def test_health_wait_does_not_sleep_past_deadline(environment, monkeypatch):
    now = [0.0]
    sleeps = []
    monkeypatch.setattr(desktop.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(desktop.time, "sleep", sleeps.append)

    def slow_probe(*_):
        now[0] = 15.0
        return False

    host = desktop.DesktopHost(server_factory=lambda *_: FakeServer(), health_probe=slow_probe)
    with pytest.raises(desktop.DesktopStartupError, match="DESKTOP_HEALTH_TIMEOUT"):
        host.start()
    assert sum(sleeps) == 0


def test_late_success_cannot_mark_host_ready(environment, monkeypatch):
    now = [0.0]
    monkeypatch.setattr(desktop.time, "monotonic", lambda: now[0])

    def late_success(*_):
        now[0] = 15.5
        return True

    host = desktop.DesktopHost(server_factory=lambda *_: FakeServer(), health_probe=late_success)
    try:
        with pytest.raises(desktop.DesktopStartupError, match="DESKTOP_HEALTH_TIMEOUT"):
            host.start()
        assert host.url is None
        assert host.thread is None
    finally:
        host.stop()


@pytest.mark.parametrize("slow_part", ["headers", "body", "none"])
def test_progressive_response_cannot_extend_health_deadline(monkeypatch, slow_part):
    now = [0.0]
    monkeypatch.setattr(desktop.time, "monotonic", lambda: now[0])
    payload = b'{"status":"ok","database":"ok","service":"redpath-api"}'
    headers = f"HTTP/1.1 200 OK\r\nContent-Length: {len(payload)}\r\n\r\n".encode()
    chunks = (
        [(0.09, headers[:12]), (0.09, headers[12:]), (0.09, payload)]
        if slow_part == "headers" else
        [(0.01, headers), (0.09, payload[:10]), (0.09, payload[10:20]), (0.09, payload[20:])]
    )
    if slow_part == "none":
        chunks = [(0.01, headers), (0.01, payload)]

    class ProgressiveSocket:
        def __init__(self):
            self.timeout = 0.2
            self.timeouts = []
            self.closed = False

        def settimeout(self, timeout):
            self.timeout = timeout
            self.timeouts.append((now[0], timeout))

        def sendall(self, _):
            now[0] += 0.01

        def setsockopt(self, *_):
            pass

        def makefile(self, *_args, **_kwargs):
            owner = self

            class Incoming(io.RawIOBase):
                def readable(self):
                    return True

                def readinto(self, buffer):
                    if not chunks:
                        return 0
                    delay, data = chunks.pop(0)
                    if delay > owner.timeout:
                        now[0] += owner.timeout
                        raise TimeoutError
                    now[0] += delay
                    buffer[:len(data)] = data
                    return len(data)

            return io.BufferedReader(Incoming())

        def close(self):
            self.closed = True

    transport = ProgressiveSocket()
    connection = desktop.HTTPConnection("127.0.0.1", 43210, timeout=0.2)

    def connect(_address, timeout, *_args):
        transport.settimeout(timeout)
        now[0] += 0.02
        return transport

    connection._create_connection = connect
    factory = lambda *_args, **_kwargs: connection
    monkeypatch.setattr(desktop, "HTTPConnection", factory)
    assert desktop._health_probe("http://127.0.0.1:43210/api/v1/health", 0.2) is (slow_part == "none")
    assert now[0] <= 0.2
    assert all(timeout <= 0.2 - at for at, timeout in transport.timeouts)
    assert transport.closed


def test_initialization_failure_closes_reserved_socket(environment):
    host = desktop.DesktopHost(server_factory=Mock(side_effect=ValueError("private")))
    with pytest.raises(desktop.DesktopStartupError, match="DESKTOP_SERVER_FAILED"):
        host.start()
    assert environment.closed


def test_uvicorn_config_is_one_worker_loopback_without_console_logging(monkeypatch):
    uvicorn = SimpleNamespace(Config=Mock(), Server=Mock())
    monkeypatch.setitem(sys.modules, "uvicorn", uvicorn)
    desktop._create_server(object(), 43210)
    config = uvicorn.Config.call_args.kwargs
    assert config["host"] == "127.0.0.1"
    assert config["workers"] == 1
    assert config["log_config"] is None
    assert config["access_log"] is False
    assert config["timeout_graceful_shutdown"] < 5


@pytest.mark.parametrize("payload, expected", [
    ({"status": "ok", "database": "ok", "service": "redpath-api"}, True),
    ({"status": "degraded", "database": "unavailable", "service": "redpath-api"}, False),
    ({"status": "ok", "database": "ok", "service": "other"}, False),
])
def test_health_requires_correct_service_and_healthy_database(monkeypatch, payload, expected):
    monkeypatch.setattr(desktop.time, "monotonic", lambda: 0.0)
    connection = Mock()
    connection.getresponse.return_value = SimpleNamespace(
        status=200, read=lambda _: json.dumps(payload).encode(), close=lambda: None
    )
    factory = Mock(return_value=connection)
    monkeypatch.setattr(desktop, "HTTPConnection", factory)
    assert desktop._health_probe("http://127.0.0.1:43210/api/v1/health", 0.2) is expected
    assert factory.call_args.args == ("127.0.0.1", 43210)
    assert factory.call_args.kwargs["timeout"] == 0.2
    connection.close.assert_called_once()


def test_optional_dependencies_are_lazy_and_missing_webview_is_actionable(monkeypatch):
    monkeypatch.setitem(sys.modules, "webview", None)
    importlib.reload(desktop)
    with pytest.raises(
        desktop.DesktopStartupError, match=r"DESKTOP_DEPENDENCY_MISSING.*\.\[desktop\]"
    ):
        desktop._load_webview()


@pytest.mark.parametrize("platform, build, machine", [
    ("linux", 30000, "AMD64"), ("win32", 19045, "AMD64"), ("win32", 22631, "ARM64"),
])
def test_unsupported_platform_has_windows_11_error(monkeypatch, platform, build, machine):
    monkeypatch.setattr(sys, "platform", platform)
    monkeypatch.setattr(sys, "getwindowsversion", lambda: SimpleNamespace(build=build), raising=False)
    monkeypatch.setattr(desktop.platform, "machine", lambda: machine)
    monkeypatch.setattr(desktop, "_show_error", Mock())
    with pytest.raises(desktop.DesktopStartupError, match="Windows 11 x64"):
        desktop.main()


@pytest.mark.parametrize("window_fails", [False, True])
def test_native_window_always_stops_host(monkeypatch, window_fails):
    host = Mock()
    host.start.return_value = "http://127.0.0.1:43210"
    webview = Mock()
    if window_fails:
        webview.start.side_effect = RuntimeError("private backend details")
    monkeypatch.setattr(desktop, "_require_windows", lambda: None)
    monkeypatch.setattr(desktop, "DesktopHost", lambda: host)
    monkeypatch.setattr(desktop, "_load_webview", lambda: webview)
    show_error = Mock()
    monkeypatch.setattr(desktop, "_show_error", show_error)
    if window_fails:
        with pytest.raises(desktop.DesktopStartupError, match="DESKTOP_WEBVIEW_FAILED"):
            desktop.main()
        assert "private" not in str(show_error.call_args)
    else:
        desktop.main()
    webview.create_window.assert_called_once_with(
        "RedPath", host.start.return_value, width=1280, height=820, min_size=(960, 640)
    )
    webview.start.assert_called_once_with(gui="edgechromium")
    host.stop.assert_called_once()
