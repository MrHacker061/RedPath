"""Both supported launchers share the same Windows instance ownership."""

from types import SimpleNamespace

import pytest
import uvicorn

from redpath import __main__ as launcher
from redpath import desktop


def test_api_launcher_uses_guarded_host_without_initializing_another_app(monkeypatch):
    events = []

    class Host:
        def __init__(self, *, port):
            assert port == 8123
            self.thread = SimpleNamespace(join=lambda: events.append("wait"))

        def start(self):
            events.append("start")

        def stop(self):
            events.append("stop")

    monkeypatch.setattr(launcher, "DesktopHost", Host, raising=False)
    monkeypatch.setattr(launcher, "_require_windows", lambda: events.append("platform"), raising=False)
    monkeypatch.setattr(launcher, "get_settings", lambda: SimpleNamespace(port=8123, host="127.0.0.1"))
    monkeypatch.setattr(uvicorn, "run", lambda *_a, **_k: pytest.fail("unguarded API app factory"))
    launcher.main()
    assert events == ["platform", "start", "wait", "stop"]


@pytest.mark.parametrize("failure", ["start", "wait"])
def test_api_launcher_always_stops_guarded_host_on_error(monkeypatch, failure):
    stopped = []

    def fail():
        raise desktop.DesktopStartupError("DESKTOP_ALREADY_RUNNING")

    host = SimpleNamespace(start=fail if failure == "start" else lambda: None, stop=lambda: stopped.append(True), thread=SimpleNamespace(join=fail))
    monkeypatch.setattr(launcher, "DesktopHost", lambda **_: host, raising=False)
    monkeypatch.setattr(launcher, "_require_windows", lambda: None, raising=False)
    monkeypatch.setattr(launcher, "get_settings", lambda: SimpleNamespace(port=8123, host="127.0.0.1"))
    monkeypatch.setattr(uvicorn, "run", lambda *_a, **_k: pytest.fail("unguarded API app factory"))
    with pytest.raises(desktop.DesktopStartupError, match="DESKTOP_ALREADY_RUNNING"):
        launcher.main()
    assert stopped == [True]


@pytest.mark.parametrize("first_launcher", ["api", "desktop"])
def test_api_and_desktop_exclude_each_other_before_storage(monkeypatch, first_launcher):
    from threading import Event, Thread
    from redpath.windows_instance import WindowsInstanceMutex

    handles = {}
    initialized, exit_server = Event(), Event()
    events, failures = [], []

    class API:
        def user_sid(self):
            return "S-1-5-21-TEST-USER"

        def create_mutex(self, name):
            handle = len(events) + 1
            exists = name in handles.values()
            handles[handle] = name
            events.append("mutex")
            return handle, 183 if exists else 0

        def close_handle(self, handle):
            del handles[handle]
            events.append("release")

    api = API()
    server = SimpleNamespace(should_exit=False, force_exit=False)

    def serve(**_):
        while not server.should_exit and not exit_server.is_set():
            exit_server.wait(0.001)

    server.run = serve

    def socket(port=0):
        assert len(handles) == 1
        events.append(("port", port))
        return SimpleNamespace(getsockname=lambda: ("127.0.0.1", port or 43210), close=lambda: events.append("socket closed"))

    def app(security, operations):
        assert len(handles) == 1
        events.append("app")
        return SimpleNamespace(state=SimpleNamespace(protected_operations=operations))

    def host(*, port=None):
        return desktop.DesktopHost(
            server_factory=lambda *_: server, health_probe=lambda *_: initialized.set() or True,
            instance_factory=lambda: WindowsInstanceMutex(api=api), port=port,
        )

    monkeypatch.setattr(desktop, "_loopback_socket", socket)
    monkeypatch.setattr(desktop, "_create_app", app)
    monkeypatch.setattr(launcher, "DesktopHost", host)
    monkeypatch.setattr(launcher, "_require_windows", lambda: None)
    monkeypatch.setattr(launcher, "get_settings", lambda: SimpleNamespace(port=8123))

    def api_main():
        try:
            launcher.main()
        except BaseException as error:
            failures.append(error)

    first = None
    api_thread = None
    try:
        if first_launcher == "desktop":
            first = host()
            first.start()
            with pytest.raises(desktop.DesktopStartupError, match="DESKTOP_ALREADY_RUNNING"):
                launcher.main()
        else:
            api_thread = Thread(target=api_main)
            api_thread.start()
            assert initialized.wait(1)
            with pytest.raises(desktop.DesktopStartupError, match="DESKTOP_ALREADY_RUNNING"):
                host().start()
        assert events.count("app") == 1  # Neither double-acquisition nor second storage initialization.
        assert len(handles) == 1
        assert ("port", 8123 if first_launcher == "api" else 0) in events
    finally:
        exit_server.set()
        if first is not None:
            first.stop()
        if api_thread is not None:
            api_thread.join(timeout=1)
            assert not api_thread.is_alive()
    assert not failures and not handles
