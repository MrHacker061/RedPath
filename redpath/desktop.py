"""Single-worker loopback server hosted by a Windows 11 WebView2 window."""

import ctypes
import importlib
import io
import json
import os
import platform
import socket
import sys
import time
from collections.abc import Callable
from http.client import HTTPConnection, HTTPException, HTTPResponse
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import urlsplit

from redpath.local_security import LocalSecurityConfig
from redpath.windows_instance import InstanceLockError, WindowsInstanceMutex


class DesktopStartupError(RuntimeError):
    """An application-owned error safe to display in a native dialog."""


def _loopback_socket() -> socket.socket:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(("127.0.0.1", 0))
        return listener
    except BaseException:
        listener.close()
        raise


def find_loopback_port() -> int:
    listener = _loopback_socket()
    try:
        return listener.getsockname()[1]
    finally:
        listener.close()


def _create_app(security: LocalSecurityConfig) -> Any:
    from redpath.app import create_app

    return create_app(security=security)


def _create_server(app: Any, port: int) -> Any:
    uvicorn = importlib.import_module("uvicorn")
    return uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, workers=1,
        log_config=None, access_log=False, timeout_graceful_shutdown=3,
    ))


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError
    return remaining


class _DeadlineReader(io.RawIOBase):
    """Keep buffered HTTP header/body reads inside one absolute deadline."""

    def __init__(self, raw: io.RawIOBase, sock: socket.socket, deadline: float):
        self.raw, self.sock, self.deadline = raw, sock, deadline

    def readable(self) -> bool:
        return True

    def readinto(self, buffer: Any) -> int:
        self.sock.settimeout(_remaining(self.deadline))
        count = self.raw.readinto(buffer)
        _remaining(self.deadline)
        return count

    def close(self) -> None:
        self.raw.close()
        super().close()


def _health_probe(url: str, deadline: float) -> bool:
    parsed = urlsplit(url)
    deadline = min(deadline, time.monotonic() + 0.25)
    connection = None
    response = None

    def bounded_response(sock: socket.socket, **kwargs: Any) -> HTTPResponse:
        result = HTTPResponse(sock, **kwargs)
        result.fp = io.BufferedReader(_DeadlineReader(result.fp.detach(), sock, deadline))
        return result

    try:
        connection = HTTPConnection("127.0.0.1", parsed.port, timeout=_remaining(deadline))
        connection.response_class = bounded_response
        connection.connect()
        connection.sock.settimeout(_remaining(deadline))
        connection.request("GET", "/api/v1/health")
        _remaining(deadline)
        response = connection.getresponse()
        payload = json.loads(response.read(4096))
        _remaining(deadline)
        return response.status == 200 and isinstance(payload, dict) and (
            payload.get("status"), payload.get("database"), payload.get("service")
        ) == ("ok", "ok", "redpath-api")
    except (OSError, ValueError, HTTPException):
        return False
    finally:
        if response is not None:
            response.close()
        if connection is not None:
            connection.close()


class DesktopHost:
    def __init__(
        self,
        server_factory: Callable[[Any, int], Any] = _create_server,
        health_probe: Callable[[str, float], bool] = _health_probe,
        instance_factory: Callable[[], WindowsInstanceMutex] = WindowsInstanceMutex,
    ) -> None:
        self.server_factory = server_factory
        self.health_probe = health_probe
        self.instance_factory = instance_factory
        self.instance: WindowsInstanceMutex | None = None
        self.server: Any = None
        self.thread: Thread | None = None
        self.listener: socket.socket | None = None
        self.url: str | None = None
        self._failed = False

    def _serve(self) -> None:
        try:
            self.server.run(sockets=[self.listener])
        except BaseException:
            self._failed = True

    def start(self) -> str:
        if self.url is not None:
            return self.url
        try:
            self._failed = False
            if self.instance is None:
                instance = self.instance_factory()
                instance.acquire()
                self.instance = instance
            # Keep the OS-assigned port reserved until Uvicorn takes ownership.
            self.listener = _loopback_socket()
            port = self.listener.getsockname()[1]
            self.server = self.server_factory(_create_app(LocalSecurityConfig(port)), port)
            self.thread = Thread(target=self._serve, name="RedPath HTTP", daemon=False)
            self.thread.start()
            url = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 15
            while True:
                if self._failed or not self.thread.is_alive():
                    raise DesktopStartupError("DESKTOP_SERVER_FAILED: Restart RedPath; check local diagnostics if it persists.")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DesktopStartupError("DESKTOP_HEALTH_TIMEOUT: RedPath did not become ready within 15 seconds. Restart and check local diagnostics.")
                healthy = self.health_probe(url + "/api/v1/health", deadline)
                if time.monotonic() >= deadline:
                    raise DesktopStartupError("DESKTOP_HEALTH_TIMEOUT: RedPath did not become ready within 15 seconds. Restart and check local diagnostics.")
                if healthy:
                    self.url = url
                    return url
                time.sleep(max(0, min(0.05, deadline - time.monotonic())))
        except BaseException as error:
            self.stop()
            if isinstance(error, InstanceLockError):
                raise DesktopStartupError(f"{error}: Close the other RedPath instance before restarting.") from None
            if isinstance(error, (DesktopStartupError, KeyboardInterrupt, SystemExit)):
                raise
            raise DesktopStartupError("DESKTOP_SERVER_FAILED: RedPath could not start. Check local storage and reinstall RedPath if needed.") from None

    def stop(self) -> None:
        self.url = None
        try:
            if self.server is not None:
                self.server.should_exit = True
            if self.thread is not None and self.thread.ident is not None:
                self.thread.join(timeout=5)
                if self.thread.is_alive():
                    self.server.force_exit = True
                    self.thread.join(timeout=1)
                if self.thread.is_alive():
                    raise DesktopStartupError("DESKTOP_SHUTDOWN_TIMEOUT: RedPath could not stop its server. Close RedPath in Task Manager before restarting.")
                self.thread = None
        finally:
            if self.listener is not None:
                self.listener.close()
                self.listener = None
            if self.instance is not None and (self.thread is None or not self.thread.is_alive()):
                self.instance.release()
                self.instance = None


def _require_windows() -> None:
    if sys.platform != "win32" or sys.getwindowsversion().build < 22000 or (
        platform.machine().lower() not in {"amd64", "x86_64"} or sys.maxsize <= 2**32
    ):
        raise DesktopStartupError("DESKTOP_PLATFORM_UNSUPPORTED: RedPath requires Windows 11 x64.")


def _load_webview() -> Any:
    try:
        return importlib.import_module("webview")
    except (ImportError, OSError):
        raise DesktopStartupError('DESKTOP_DEPENDENCY_MISSING: Reinstall RedPath, or run python -m pip install ".[desktop]" in the source checkout.') from None


def _show_error(error: DesktopStartupError) -> None:
    # Store only the stable code; dependency exceptions may contain private data.
    try:
        directory = Path(os.environ["LOCALAPPDATA"]) / "RedPath" / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "desktop-startup.log").write_text(str(error).split(":", 1)[0] + "\n", encoding="utf-8")
    except (OSError, KeyError):
        pass
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, str(error), "RedPath could not start", 0x10)


def main() -> None:
    host = DesktopHost()
    try:
        try:
            _require_windows()
            webview = _load_webview()
            url = host.start()
            try:
                webview.create_window("RedPath", url, width=1280, height=820, min_size=(960, 640))
                webview.start(gui="edgechromium")
            except Exception:
                raise DesktopStartupError("DESKTOP_WEBVIEW_FAILED: Repair Microsoft Edge WebView2 Runtime at https://developer.microsoft.com/microsoft-edge/webview2/ and restart RedPath.") from None
        finally:
            host.stop()
    except DesktopStartupError as error:
        _show_error(error)
        raise


if __name__ == "__main__":
    main()
