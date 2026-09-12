"""Concurrent pipe draining with bounded storage; all children are fake."""

import io
import subprocess
from threading import Barrier, Event, get_ident
from time import monotonic

import pytest

from redpath_setup import wsl


class OversizedStream:
    def __init__(self, byte, barrier):
        self.byte, self.barrier = byte, barrier
        self.remaining = 1024 * 1024
        self.started = False
        self.eof = Event()
        self.closed_by = None
        self.reader = None

    def read(self, size):
        assert 0 < size <= 4096, "reader must never request unbounded output"
        self.reader = get_ident()
        if not self.started:
            self.started = True
            self.barrier.wait(timeout=1)
        if not self.remaining:
            self.eof.set()
            return b""
        count = min(size, self.remaining)
        self.remaining -= count
        return self.byte * count

    def close(self):
        self.closed_by = get_ident()


class Process:
    def __init__(self):
        barrier = Barrier(2)
        self.stdout = OversizedStream(b"o", barrier)
        self.stderr = OversizedStream(b"e", barrier)
        self.returncode = None
        self.terminated = False

    def communicate(self, **_kwargs):
        raise AssertionError("full output buffering is forbidden")

    def poll(self):
        if self.stdout.eof.is_set() and self.stderr.eof.is_set():
            self.returncode = 0
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.returncode = -9

    def wait(self, timeout):
        return self.returncode


@pytest.mark.parametrize("setup", [False, True])
def test_action_and_setup_drain_oversized_both_streams_concurrently(tmp_path, monkeypatch, setup):
    process = Process()
    calls = []
    monkeypatch.setattr(wsl.subprocess, "Popen", lambda *args, **kwargs: calls.append((args, kwargs)) or process)
    monkeypatch.setattr(wsl.subprocess, "run", lambda *_a, **_k: pytest.fail("capture_output must not buffer action output"))
    argv = ["wsl.exe", "--status"]
    result = wsl._run_cancellable(argv, tmp_path, 2, Event()) if setup else wsl._run(argv, tmp_path, 2)
    assert result.returncode == 0
    assert result.stdout.startswith("o" * 1024) and result.stderr.startswith("e" * 1024)
    assert len(result.stdout) <= 32800 and len(result.stderr) <= 32800
    assert result.stdout.endswith("[output truncated]") and result.stderr.endswith("[output truncated]")
    assert process.stdout.remaining == process.stderr.remaining == 0
    assert process.stdout.reader != process.stderr.reader
    assert process.stdout.reader == process.stdout.closed_by
    assert process.stderr.reader == process.stderr.closed_by
    assert calls[0][0][0] == argv
    assert calls[0][1]["shell"] is False
    assert calls[0][1]["stdin"] == subprocess.DEVNULL


@pytest.mark.parametrize("cancel", [False, True])
def test_blocked_inherited_pipes_cannot_extend_timeout_or_cancellation(tmp_path, monkeypatch, cancel):
    release = Event()
    entered = Barrier(2)
    cancelled = Event()
    process = Process()

    class Blocked(io.BytesIO):
        def read(self, size):
            entered.wait(timeout=1)
            if cancel:
                cancelled.set()
            release.wait(timeout=1)
            return b""

    process.stdout = Blocked()
    process.stderr = Blocked()
    process.poll = lambda: process.returncode
    monkeypatch.setattr(wsl.subprocess, "Popen", lambda *_a, **_k: process)
    started = monotonic()
    try:
        error = wsl.WslOperationCancelled if cancel else subprocess.TimeoutExpired
        with pytest.raises(error):
            wsl._run_cancellable(["wsl.exe", "--status"], tmp_path, 0.1, cancelled)
        assert monotonic() - started < 0.7
        assert process.terminated
        assert not process.stdout.closed and not process.stderr.closed
    finally:
        release.set()


def test_exited_child_with_inherited_writers_fails_within_bounded_drain(tmp_path, monkeypatch):
    release = Event()
    process = Process()

    class Blocked(io.BytesIO):
        def read(self, size):
            release.wait(timeout=1)
            return b""

    process.stdout, process.stderr = Blocked(), Blocked()
    process.poll = lambda: 0
    monkeypatch.setattr(wsl.subprocess, "Popen", lambda *_a, **_k: process)
    started = monotonic()
    try:
        with pytest.raises(wsl.WslSetupError, match="pipes did not close"):
            wsl._run_cancellable(["wsl.exe", "--status"], tmp_path, 60, Event())
        assert monotonic() - started < 0.7
        assert not process.stdout.closed and not process.stderr.closed
    finally:
        release.set()
