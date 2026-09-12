"""One per-user Windows mutex; Win32 calls and desktop resources are injected."""

from types import SimpleNamespace

import pytest

from redpath import desktop


class FakeMutex:
    def __init__(self):
        self.held = False
        self.events = []

    def acquire(self):
        self.events.append("acquire")
        assert not self.held
        self.held = True

    def release(self):
        self.events.append("release")
        self.held = False


def test_host_acquires_instance_before_any_storage_or_listener_and_releases_after_shutdown(monkeypatch):
    mutex = FakeMutex()
    listener = SimpleNamespace(getsockname=lambda: ("127.0.0.1", 43210), close=lambda: mutex.events.append("socket closed"))
    server = SimpleNamespace(should_exit=False, force_exit=False)

    def reserve():
        assert mutex.held
        mutex.events.append("socket")
        return listener

    def create_app(security):
        assert mutex.held
        assert security.host == "127.0.0.1:43210"
        mutex.events.append("app")
        return object()

    class Thread:
        ident = 1

        def __init__(self, **kwargs):
            self.alive = True

        def start(self):
            pass

        def is_alive(self):
            return self.alive

        def join(self, timeout):
            assert mutex.held and server.should_exit
            mutex.events.append("join")
            self.alive = False

    monkeypatch.setattr(desktop, "_loopback_socket", reserve)
    monkeypatch.setattr(desktop, "_create_app", create_app)
    monkeypatch.setattr(desktop, "Thread", Thread)
    host = desktop.DesktopHost(server_factory=lambda *_: server, health_probe=lambda *_: True, instance_factory=lambda: mutex)
    host.start()
    assert mutex.held
    host.stop()
    host.stop()
    assert mutex.events == ["acquire", "socket", "app", "join", "socket closed", "release"]


def test_second_instance_fails_before_app_creation(monkeypatch):
    from redpath.windows_instance import InstanceLockError

    class AlreadyRunning(FakeMutex):
        def acquire(self):
            raise InstanceLockError("DESKTOP_ALREADY_RUNNING")

    monkeypatch.setattr(desktop, "_create_app", lambda *_: pytest.fail("second instance initialized storage"))
    host = desktop.DesktopHost(instance_factory=AlreadyRunning)
    with pytest.raises(desktop.DesktopStartupError, match="DESKTOP_ALREADY_RUNNING"):
        host.start()


def test_mutex_is_per_user_closes_duplicate_handle_and_allows_restart():
    from redpath.windows_instance import WindowsInstanceMutex

    class API:
        def __init__(self):
            self.open = {}
            self.next_handle = 1
            self.sid = "S-1-5-21-111"

        def user_sid(self):
            return self.sid

        def create_mutex(self, name):
            handle = self.next_handle
            self.next_handle += 1
            exists = name in self.open.values()
            self.open[handle] = name
            return handle, 183 if exists else 0

        def close_handle(self, handle):
            del self.open[handle]

    api = API()
    first = WindowsInstanceMutex(api=api)
    first.acquire()
    from redpath.windows_instance import InstanceLockError
    with pytest.raises(InstanceLockError, match="DESKTOP_ALREADY_RUNNING"):
        WindowsInstanceMutex(api=api).acquire()
    assert len(api.open) == 1
    assert next(iter(api.open.values())).startswith("Global\\RedPath-")
    api.sid = "S-1-5-21-222"
    other = WindowsInstanceMutex(api=api)
    other.acquire()
    assert len(api.open) == 2
    other.release()
    first.release()
    first.release()
    restarted = WindowsInstanceMutex(api=api)
    restarted.acquire()
    restarted.release()
    assert not api.open


def test_shutdown_timeout_retains_mutex_until_server_has_stopped():
    mutex = FakeMutex()
    mutex.acquire()
    host = desktop.DesktopHost(instance_factory=lambda: mutex)
    host.instance = mutex
    host.server = SimpleNamespace(should_exit=False, force_exit=False)
    host.thread = SimpleNamespace(ident=1, join=lambda **_kwargs: None, is_alive=lambda: True)
    with pytest.raises(desktop.DesktopStartupError, match="DESKTOP_SHUTDOWN_TIMEOUT"):
        host.stop()
    assert mutex.held and host.server.force_exit
    host.thread.is_alive = lambda: False
    host.stop()
    assert not mutex.held


def test_storage_initialization_failure_releases_instance(monkeypatch):
    mutex = FakeMutex()
    monkeypatch.setattr(desktop, "_loopback_socket", lambda: SimpleNamespace(getsockname=lambda: ("127.0.0.1", 43210), close=lambda: None))

    def fail(_security):
        assert mutex.held
        raise OSError("storage unavailable")

    monkeypatch.setattr(desktop, "_create_app", fail)
    host = desktop.DesktopHost(instance_factory=lambda: mutex)
    with pytest.raises(desktop.DesktopStartupError, match="DESKTOP_SERVER_FAILED"):
        host.start()
    assert not mutex.held


def test_importing_app_factory_does_not_initialize_storage(monkeypatch):
    import importlib
    import redpath.app as app_module
    from redpath.runtime import AppPaths

    monkeypatch.setattr(AppPaths, "ensure", lambda _self: pytest.fail("import initialized storage before the mutex"))
    importlib.reload(app_module)


def test_win32_failure_never_grants_instance_ownership():
    from redpath.windows_instance import InstanceLockError, WindowsInstanceMutex

    api = SimpleNamespace(user_sid=lambda: "S-1-5-21-111", create_mutex=lambda _: (0, 5), close_handle=lambda _: pytest.fail("closed invalid handle"))
    mutex = WindowsInstanceMutex(api=api)
    with pytest.raises(InstanceLockError, match="DESKTOP_INSTANCE_LOCK_FAILED"):
        mutex.acquire()
    assert mutex.handle is None
