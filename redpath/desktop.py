"""Single-worker loopback server hosted by a Windows 11 WebView2 window."""

import ctypes
import importlib
import json
import os
import platform
import socket
import sys
import time
from collections.abc import Callable
from http.client import HTTPConnection
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import urlsplit


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


def _create_app() -> Any:
    # Reuse the existing app; importing it twice would initialize storage twice.
    from redpath.app import app

    return app


def _create_server(app: Any, port: int) -> Any:
    uvicorn = importlib.import_module("uvicorn")
    return uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, workers=1,
        log_config=None, access_log=False, timeout_graceful_shutdown=3,
    ))


def _health_probe(url: str, timeout: float) -> bool:
    parsed = urlsplit(url)
    connection = HTTPConnection("127.0.0.1", parsed.port, timeout=timeout)
    try:
        connection.request("GET", "/api/v1/health")
        response = connection.getresponse()
        payload = json.loads(response.read(4096))
        return response.status == 200 and isinstance(payload, dict) and (
            payload.get("status"), payload.get("database"), payload.get("service")
        ) == ("ok", "ok", "redpath-api")
    except (OSError, ValueError):
        return False
    finally:
        connection.close()


class DesktopHost:
    def __init__(
        self,
        server_factory: Callable[[Any, int], Any] = _create_server,
        health_probe: Callable[[str, float], bool] = _health_probe,
    ) -> None:
        self.server_factory = server_factory
        self.health_probe = health_probe
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
            # Keep the OS-assigned port reserved until Uvicorn takes ownership.
            self.listener = _loopback_socket()
            port = self.listener.getsockname()[1]
            self.server = self.server_factory(_create_app(), port)
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
                if self.health_probe(url + "/api/v1/health", min(0.25, remaining)):
                    self.url = url
                    return url
                time.sleep(max(0, min(0.05, deadline - time.monotonic())))
        except BaseException as error:
            self.stop()
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
        finally:
            if self.listener is not None:
                self.listener.close()
                self.listener = None


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
