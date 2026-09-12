"""Per-user, cross-session Windows instance guard using stdlib Win32 bindings."""

import ctypes
import hashlib
from ctypes import wintypes
from typing import Protocol


class InstanceLockError(RuntimeError):
    """A stable instance-guard failure without raw Windows error text."""


class MutexAPI(Protocol):
    def user_sid(self) -> str: ...
    def create_mutex(self, name: str) -> tuple[int, int]: ...
    def close_handle(self, handle: int) -> None: ...


class _WindowsAPI:
    def __init__(self) -> None:
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        for library, name, args, result in [
            (self.kernel, "GetCurrentProcess", [], wintypes.HANDLE),
            (self.kernel, "CreateMutexW", [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
            (self.kernel, "CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
            (self.kernel, "LocalFree", [wintypes.LPVOID], wintypes.LPVOID),
            (self.advapi, "OpenProcessToken", [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)], wintypes.BOOL),
            (self.advapi, "GetTokenInformation", [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            (self.advapi, "ConvertSidToStringSidW", [wintypes.LPVOID, ctypes.POINTER(wintypes.LPWSTR)], wintypes.BOOL),
        ]:
            function = getattr(library, name)
            function.argtypes, function.restype = args, result

    def user_sid(self) -> str:
        token = wintypes.HANDLE()
        if not self.advapi.OpenProcessToken(self.kernel.GetCurrentProcess(), 0x0008, ctypes.byref(token)):
            raise InstanceLockError("DESKTOP_INSTANCE_LOCK_FAILED")
        try:
            size = wintypes.DWORD()
            self.advapi.GetTokenInformation(token, 1, None, 0, ctypes.byref(size))
            if not 0 < size.value <= 65536:
                raise InstanceLockError("DESKTOP_INSTANCE_LOCK_FAILED")
            buffer = ctypes.create_string_buffer(size.value)
            if not self.advapi.GetTokenInformation(token, 1, buffer, size, ctypes.byref(size)):
                raise InstanceLockError("DESKTOP_INSTANCE_LOCK_FAILED")
            # TOKEN_USER begins with SID_AND_ATTRIBUTES.Sid (a pointer).
            sid = ctypes.cast(buffer, ctypes.POINTER(wintypes.LPVOID))[0]
            text = wintypes.LPWSTR()
            if not self.advapi.ConvertSidToStringSidW(sid, ctypes.byref(text)):
                raise InstanceLockError("DESKTOP_INSTANCE_LOCK_FAILED")
            try:
                return text.value
            finally:
                self.kernel.LocalFree(ctypes.cast(text, wintypes.LPVOID))
        finally:
            self.kernel.CloseHandle(token)

    def create_mutex(self, name: str) -> tuple[int, int]:
        ctypes.set_last_error(0)
        # Holding the named handle enforces process lifetime; no thread-owned
        # mutex lock or ReleaseMutex call is needed for an instance guard.
        handle = self.kernel.CreateMutexW(None, False, name)
        return handle, ctypes.get_last_error()

    def close_handle(self, handle: int) -> None:
        self.kernel.CloseHandle(handle)


class WindowsInstanceMutex:
    def __init__(self, *, api: MutexAPI | None = None) -> None:
        self.api = api
        self.handle: int | None = None

    def acquire(self) -> None:
        if self.handle is not None:
            return
        try:
            if self.api is None:
                self.api = _WindowsAPI()
            identity = hashlib.sha256(self.api.user_sid().encode("utf-8")).hexdigest()
            handle, error = self.api.create_mutex(f"Global\\RedPath-{identity}")
            if not handle:
                raise InstanceLockError("DESKTOP_INSTANCE_LOCK_FAILED")
            if error == 183:  # ERROR_ALREADY_EXISTS; close only our duplicate.
                self.api.close_handle(handle)
                raise InstanceLockError("DESKTOP_ALREADY_RUNNING")
            self.handle = handle
        except (OSError, AttributeError):
            raise InstanceLockError("DESKTOP_INSTANCE_LOCK_FAILED") from None

    def release(self) -> None:
        if self.handle is not None:
            self.api.close_handle(self.handle)
            self.handle = None
