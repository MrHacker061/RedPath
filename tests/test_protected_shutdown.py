"""The guard owns actual sync workers, including abandoned AnyIO requests."""

from threading import Event
from types import SimpleNamespace

import anyio
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from redpath import desktop
from redpath.app import create_app
from redpath.config import Settings
from redpath.contracts import SetupRepairRequest
from redpath.runtime import AppPaths
from redpath.setup_api import repair_setup
from redpath_setup.state import SetupStage


class Mutex:
    def __init__(self):
        self.held = True
        self.released = Event()

    def release(self):
        self.held = False
        self.released.set()


def make_app(tmp_path):
    paths = AppPaths.from_environment(str(tmp_path))
    return create_app(Settings(database_url=f"sqlite:///{paths.database_file}"), paths)


def stopped_host(app):
    host = desktop.DesktopHost(shutdown_timeout=0.05)
    host.operations = app.state.protected_operations
    host.app = app
    host.instance = Mutex()
    host.server = SimpleNamespace(should_exit=False, force_exit=False)
    host.thread = SimpleNamespace(ident=1, join=lambda **_: None, is_alive=lambda: False)
    return host


def test_abandoned_anyio_setup_worker_keeps_guard_after_http_thread_exits(tmp_path):
    app = make_app(tmp_path)
    entered, release, finished = Event(), Event(), Event()
    cancellation = []

    def install(consent, progress, cancelled):
        cancellation.append(cancelled)
        entered.set()
        try:
            assert release.wait(3)
            return SetupStage("ollama", "ready", "OLLAMA_READY", "Ready")
        finally:
            finished.set()

    app.state.ollama_setup.install = install
    request = Request({"type": "http", "app": app})

    async def exercise():
        async with anyio.create_task_group() as tasks:
            async def request_task():
                await anyio.to_thread.run_sync(lambda: repair_setup("ollama", SetupRepairRequest(consent=True), request), abandon_on_cancel=True)

            tasks.start_soon(request_task)
            while not entered.is_set():
                await anyio.sleep(0.001)
            tasks.cancel_scope.cancel()
        host = stopped_host(app)
        mutex = host.instance
        try:
            with pytest.raises(desktop.DesktopStartupError, match="DESKTOP_PROTECTED_WORK_PENDING"):
                host.stop()
            assert mutex.held and not finished.is_set()
            assert cancellation[0].is_set()
            with pytest.raises(HTTPException) as rejected:
                repair_setup("ollama", SetupRepairRequest(consent=True), request)
            assert rejected.value.status_code == 503
        finally:
            release.set()
            assert finished.wait(1)
            assert mutex.released.wait(1)
            host.stop()

    anyio.run(exercise)


def test_shutdown_wait_does_not_hold_operation_lock_needed_by_finishing_worker(tmp_path):
    from redpath.operations import ProtectedOperations
    from threading import Thread

    operations = ProtectedOperations()
    entered, release = Event(), Event()

    def worker():
        with operations.operation(cancellable=True) as cancelled:
            entered.set()
            assert cancelled.wait(1)
            release.set()

    thread = Thread(target=worker)
    thread.start()
    assert entered.wait(1)
    operations.close_admission()
    assert operations.wait_idle(1)
    thread.join(timeout=1)
    assert release.is_set() and not thread.is_alive()
    with pytest.raises(HTTPException):
        with operations.operation():
            pytest.fail("shutdown admitted another worker")


def test_error_inside_worker_releases_its_registration(tmp_path):
    from redpath.operations import ProtectedOperations

    operations = ProtectedOperations()
    with pytest.raises(ValueError):
        with operations.operation():
            raise ValueError("failed action")
    operations.close_admission()
    assert operations.wait_idle(0)


def test_guard_outlives_worker_when_its_child_has_not_exited(tmp_path):
    app = make_app(tmp_path)
    host = stopped_host(app)
    mutex = host.instance
    child = SimpleNamespace(returncode=None)
    child.poll = lambda: child.returncode
    with host.operations.operation():
        host.operations.own_child(child)
    try:
        with pytest.raises(desktop.DesktopStartupError, match="DESKTOP_PROTECTED_WORK_PENDING"):
            host.stop()
        assert mutex.held
        assert host._guard_waiter is not None and not host._guard_waiter.daemon
    finally:
        child.returncode = 0
        assert mutex.released.wait(1)
        host._guard_waiter.join(timeout=1)
        host.stop()


def test_lifespan_exit_does_not_dispose_storage_under_abandoned_worker(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    entered, release = Event(), Event()
    disposals = []
    monkeypatch.setattr(app.state.engine, "dispose", lambda: disposals.append(True))

    def worker():
        with app.state.protected_operations.operation():
            entered.set()
            assert release.wait(3)

    async def exercise():
        async with app.router.lifespan_context(app):
            async with anyio.create_task_group() as tasks:
                async def request_task():
                    await anyio.to_thread.run_sync(worker, abandon_on_cancel=True)

                tasks.start_soon(request_task)
                while not entered.is_set():
                    await anyio.sleep(0.001)
                tasks.cancel_scope.cancel()
        host = stopped_host(app)
        mutex = host.instance
        try:
            assert not disposals
            with pytest.raises(desktop.DesktopStartupError, match="DESKTOP_PROTECTED_WORK_PENDING"):
                host.stop()
            assert not disposals and mutex.held
        finally:
            release.set()
            assert mutex.released.wait(1)
            host._guard_waiter.join(timeout=1)
        assert disposals == [True]

    anyio.run(exercise)
