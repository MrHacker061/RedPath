import subprocess

import pytest

from redpath_kali import ProcessResult


class RecordingWslRunner:
    def __init__(self, result: ProcessResult | None = None) -> None:
        self.result = result or ProcessResult(0, "HTTP/1.1 200 OK\n", "")
        self.arguments: list[str] | None = None
        self.timeout: float | None = None

    def run_in_kali(self, arguments, timeout: float) -> ProcessResult:
        self.arguments = list(arguments)
        self.timeout = timeout
        return self.result


def test_wsl_dispatcher_builds_fixed_http_command():
    from redpath_kali.wsl_actions import WSLActionDispatcher

    runner = RecordingWslRunner()
    dispatcher = WSLActionDispatcher(runner)
    result = dispatcher.dispatch(
        "inspect_http_headers", {"target_id": "t1", "port": 80},
        authorized_target_id="t1", authorized_target_address="192.168.56.20",
    )

    assert runner.arguments == ["curl", "--head", "--max-time", "10", "http://192.168.56.20:80/"]
    assert runner.timeout == 15
    assert result.action_name == "inspect_http_headers"
    assert result.status.value == "succeeded"


@pytest.mark.parametrize(
    ("action_name", "arguments", "address"),
    [
        ("free_form_shell", {"target_id": "t1", "port": 80}, "192.168.56.20"),
        ("inspect_http_headers", {"target_id": "t1", "port": 80, "command": "id"}, "192.168.56.20"),
        ("inspect_http_headers", {"target_id": "other", "port": 80}, "192.168.56.20"),
        ("inspect_http_headers", {"target_id": "t1", "port": 80}, "8.8.8.8"),
    ],
)
def test_wsl_dispatcher_reuses_closed_world_validation(action_name, arguments, address):
    from redpath_kali.wsl_actions import WSLActionDispatcher
    from redpath_kali import KaliActionError

    runner = RecordingWslRunner()
    with pytest.raises(KaliActionError):
        WSLActionDispatcher(runner).dispatch(
            action_name, arguments, authorized_target_id="t1", authorized_target_address=address
        )
    assert runner.arguments is None


def test_wsl_dispatcher_sanitizes_transport_failure():
    from redpath_kali.wsl_actions import WSLActionDispatcher

    class BrokenRunner:
        def run_in_kali(self, _arguments, timeout: float):
            raise OSError("SECRET_WSL_TRANSPORT_DETAIL")

    result = WSLActionDispatcher(BrokenRunner()).dispatch(
        "check_tcp_connection", {"target_id": "t1", "port": 22},
        authorized_target_id="t1", authorized_target_address="10.0.0.2",
    )

    assert result.status.value == "failed"
    assert result.error == "managed Kali WSL is unavailable"
    assert "SECRET" not in repr(result)


def test_wsl_dispatcher_preserves_bounded_timeout_result():
    from redpath_kali.wsl_actions import WSLActionDispatcher

    class TimedOutRunner:
        def run_in_kali(self, _arguments, timeout: float):
            raise subprocess.TimeoutExpired("wsl.exe", timeout, output="partial", stderr="failed")

    result = WSLActionDispatcher(TimedOutRunner()).dispatch(
        "inspect_tls_certificate", {"target_id": "t1", "port": 443},
        authorized_target_id="t1", authorized_target_address="192.168.56.20",
    )

    assert result.status.value == "timed_out"
    assert result.stdout == "partial"
    assert result.stderr == "failed"
