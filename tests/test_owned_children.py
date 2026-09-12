"""A timed-out runner must not forget a child whose termination is unconfirmed."""

import io
import subprocess
from threading import Event

import pytest

from redpath.operations import ProtectedOperations
from redpath_setup import ollama, wsl


class UnreapedChild:
    def __init__(self):
        self.returncode = None
        self.stdout, self.stderr = io.BytesIO(), io.BytesIO()
        self.terminated = self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    def wait(self, timeout):
        raise subprocess.TimeoutExpired("fake-child", timeout)


@pytest.mark.parametrize("runner", ["wsl", "ollama"])
def test_owned_child_survives_worker_registration_until_exit_confirmed(tmp_path, monkeypatch, runner):
    operations = ProtectedOperations()
    child = UnreapedChild()
    cancelled = Event()
    cancelled.set()
    monkeypatch.setattr(subprocess, "Popen", lambda *_a, **_k: child)
    with operations.operation():
        with pytest.raises((wsl.WslOperationCancelled, ollama.ProcessCancelled)):
            if runner == "wsl":
                wsl._run_cancellable(["wsl.exe", "--status"], tmp_path, 1, cancelled)
            else:
                ollama._run(["ollama.exe", "pull", "fixed-model"], tmp_path, 1, cancelled, lambda *_: None)
    operations.close_admission()
    assert child.terminated and child.killed
    assert operations.wait_idle(0) is False
    child.returncode = -9
    assert operations.wait_idle(1) is True
