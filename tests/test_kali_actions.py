import importlib
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from redpath_kali import KaliVMError, ProcessResult, SSHConfig


class FakeVMManager:
    def __init__(self) -> None:
        self.discover_calls = 0

    def discover_ssh_config(self) -> SSHConfig:
        self.discover_calls += 1
        return SSHConfig(
            alias="kali-headless",
            hostname="127.0.0.1",
            port=2207,
            user="vagrant",
            identity_file=Path("C:/managed/private_key"),
            identities_only=True,
            client_options=(
                "BatchMode=yes",
                "PasswordAuthentication=no",
                "KbdInteractiveAuthentication=no",
                "PreferredAuthentications=publickey",
                "IdentitiesOnly=yes",
                "ForwardAgent=no",
            ),
        )


class RecordingRunner:
    def __init__(self, result: ProcessResult) -> None:
        self.result = result
        self.calls: list[tuple[tuple[str, ...], Path, float]] = []

    def __call__(self, arguments, cwd: Path, timeout: float) -> ProcessResult:
        assert cwd.is_dir()
        self.calls.append((tuple(arguments), cwd, timeout))
        return self.result


class RaisingRunner:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.workdir: Path | None = None

    def __call__(self, arguments, cwd: Path, timeout: float) -> ProcessResult:
        self.workdir = cwd
        raise self.error


def action_api():
    try:
        return importlib.import_module("redpath_kali.actions")
    except ModuleNotFoundError:
        pytest.fail("redpath_kali.actions fixed-action adapter is missing")


def test_tcp_action_uses_fixed_noninteractive_ssh_argv():
    actions = action_api()
    vm = FakeVMManager()
    runner = RecordingRunner(ProcessResult(0, "Connection succeeded\n", ""))

    result = actions.KaliActionDispatcher(vm, runner=runner).dispatch(
        "check_tcp_connection",
        {"target_id": "target-1", "port": 8080},
        authorized_target_id="target-1",
        authorized_target_address="192.168.56.20",
    )

    assert result.status is actions.ActionStatus.SUCCEEDED
    assert result.action_name == "check_tcp_connection"
    assert result.target_id == "target-1"
    assert result.target_address == "192.168.56.20"
    assert result.port == 8080
    assert result.exit_code == 0
    assert result.stdout == "Connection succeeded\n"
    assert result.stderr == ""
    assert result.output_truncated is False
    assert vm.discover_calls == 1
    argv, workdir, timeout = runner.calls[0]
    assert argv[0] == "ssh.exe"
    assert ("-o", "BatchMode=yes") == argv[4:6]
    assert "PasswordAuthentication=no" in argv
    assert "KbdInteractiveAuthentication=no" in argv
    assert "ClearAllForwardings=yes" in argv
    assert argv[-2] == "vagrant@127.0.0.1"
    assert argv[-1] == "timeout --signal=KILL 5s nc -vz -w 5 192.168.56.20 8080"
    assert timeout == 10
    assert not workdir.exists()


def test_host_key_acceptance_is_noninteractive_and_scoped_to_cleaned_workdir():
    actions = action_api()
    runner = RecordingRunner(ProcessResult(0))

    actions.KaliActionDispatcher(FakeVMManager(), runner=runner).dispatch(
        "check_tcp_connection",
        {"target_id": "target-1", "port": 80},
        authorized_target_id="target-1",
        authorized_target_address="192.168.56.20",
    )

    argv, workdir, _ = runner.calls[0]
    assert "StrictHostKeyChecking=accept-new" in argv
    known_hosts = f"UserKnownHostsFile={workdir / 'known_hosts'}"
    assert known_hosts in argv
    assert "StrictHostKeyChecking=no" not in argv
    assert not workdir.exists()


@pytest.mark.parametrize(
    ("name", "arguments", "expected_command", "expected_timeout"),
    [
        (
            "check_tcp_connection",
            {"target_id": "target-1", "port": 22, "timeout_seconds": 3},
            "timeout --signal=KILL 3s nc -vz -w 3 192.168.56.20 22",
            8,
        ),
        (
            "inspect_http_headers",
            {"target_id": "target-1", "port": 8080},
            "timeout --signal=KILL 10s curl --head --silent --show-error "
            "--max-time 8 --connect-timeout 5 --proto =http -- "
            "http://192.168.56.20:8080/",
            15,
        ),
        (
            "inspect_tls_certificate",
            {"target_id": "target-1", "port": 443},
            "timeout --signal=KILL 10s openssl s_client -brief "
            "-connect 192.168.56.20:443",
            15,
        ),
    ],
)
def test_each_named_action_has_one_fixed_command(name, arguments, expected_command, expected_timeout):
    actions = action_api()
    runner = RecordingRunner(ProcessResult(0, "evidence", ""))

    actions.KaliActionDispatcher(FakeVMManager(), runner=runner).dispatch(
        name,
        arguments,
        authorized_target_id="target-1",
        authorized_target_address="192.168.56.20",
    )

    argv, _, timeout = runner.calls[0]
    assert argv[-1] == expected_command
    assert timeout == expected_timeout


@pytest.mark.parametrize(
    ("action_name", "arguments"),
    [
        ("free_form_shell", {"target_id": "target-1", "port": 80}),
        ("check_tcp_connection;id", {"target_id": "target-1", "port": 80}),
        ("check_tcp_connection", {"target_id": "target-1", "port": 80, "command": "id"}),
        ("inspect_http_headers", {"target_id": "target-1", "port": 80, "timeout_seconds": 5}),
        ("inspect_tls_certificate", {"target_id": "target-1", "port": 443, "shell": True}),
        ("check_tcp_connection", {"target_id": "target-1"}),
        ("check_tcp_connection", {"target_id": "target-1", "port": "80"}),
        ("check_tcp_connection", {"target_id": "target-1", "port": True}),
        ("check_tcp_connection", {"target_id": "target-1", "port": 0}),
        ("check_tcp_connection", {"target_id": "target-1", "port": 65536}),
        ("check_tcp_connection", {"target_id": "target-1", "port": 80, "timeout_seconds": 0}),
        ("check_tcp_connection", {"target_id": "target-1", "port": 80, "timeout_seconds": 11}),
        ("check_tcp_connection", {"target_id": "target-1", "port": 80, "timeout_seconds": "5"}),
    ],
)
def test_unknown_actions_extra_fields_and_non_strict_values_are_rejected(action_name, arguments):
    actions = action_api()
    vm = FakeVMManager()
    runner = RecordingRunner(ProcessResult(0))

    with pytest.raises(actions.KaliActionError):
        actions.KaliActionDispatcher(vm, runner=runner).dispatch(
            action_name,
            arguments,
            authorized_target_id="target-1",
            authorized_target_address="192.168.56.20",
        )

    assert vm.discover_calls == 0
    assert runner.calls == []


@pytest.mark.parametrize("arguments", [[], "target-1", None])
def test_arguments_must_be_a_plain_structured_object(arguments):
    actions = action_api()
    with pytest.raises(actions.KaliActionError, match="plain object"):
        actions.KaliActionDispatcher(FakeVMManager(), runner=RecordingRunner(ProcessResult(0))).dispatch(
            "check_tcp_connection",
            arguments,
            authorized_target_id="target-1",
            authorized_target_address="192.168.56.20",
        )


def test_action_target_must_match_backend_authorized_target():
    actions = action_api()
    vm = FakeVMManager()
    runner = RecordingRunner(ProcessResult(0))

    with pytest.raises(actions.KaliActionError, match="does not match"):
        actions.KaliActionDispatcher(vm, runner=runner).dispatch(
            "check_tcp_connection",
            {"target_id": "target-other", "port": 80},
            authorized_target_id="target-1",
            authorized_target_address="192.168.56.20",
        )

    assert vm.discover_calls == 0
    assert runner.calls == []


def test_target_identifier_cannot_create_a_metacharacter_channel():
    actions = action_api()
    with pytest.raises(actions.KaliActionError, match="target identifier"):
        actions.KaliActionDispatcher(FakeVMManager(), runner=RecordingRunner(ProcessResult(0))).dispatch(
            "check_tcp_connection",
            {"target_id": "target-1;id", "port": 80},
            authorized_target_id="target-1;id",
            authorized_target_address="192.168.56.20",
        )


@pytest.mark.parametrize(
    "address",
    [
        "8.8.8.8",
        "127.0.0.1",
        "169.254.169.254",
        "224.0.0.1",
        "0.0.0.0",
        "192.0.2.1",
        "::1",
        "fe80::1",
        "example.test",
        "192.168.56.20;id",
    ],
)
def test_public_malformed_and_special_use_targets_are_rejected(address):
    actions = action_api()
    vm = FakeVMManager()
    runner = RecordingRunner(ProcessResult(0))

    with pytest.raises(actions.KaliActionError, match="private lab"):
        actions.KaliActionDispatcher(vm, runner=runner).dispatch(
            "check_tcp_connection",
            {"target_id": "target-1", "port": 80},
            authorized_target_id="target-1",
            authorized_target_address=address,
        )

    assert vm.discover_calls == 0
    assert runner.calls == []


def test_ipv6_ula_is_formatted_safely_for_http_and_tls():
    actions = action_api()
    runner = RecordingRunner(ProcessResult(0))
    dispatcher = actions.KaliActionDispatcher(FakeVMManager(), runner=runner)

    dispatcher.dispatch(
        "inspect_http_headers",
        {"target_id": "target-1", "port": 8080},
        authorized_target_id="target-1",
        authorized_target_address="fd00::20",
    )
    dispatcher.dispatch(
        "inspect_tls_certificate",
        {"target_id": "target-1", "port": 443},
        authorized_target_id="target-1",
        authorized_target_address="fd00::20",
    )

    assert runner.calls[0][0][-1].endswith("'http://[fd00::20]:8080/'")
    assert runner.calls[1][0][-1].endswith("-connect '[fd00::20]:443'")


def test_nonzero_exit_is_a_bounded_structured_failure():
    actions = action_api()
    runner = RecordingRunner(ProcessResult(7, "partial", "connection failed"))

    result = actions.KaliActionDispatcher(FakeVMManager(), runner=runner).dispatch(
        "inspect_http_headers",
        {"target_id": "target-1", "port": 80},
        authorized_target_id="target-1",
        authorized_target_address="10.10.10.20",
    )

    assert result.status is actions.ActionStatus.FAILED
    assert result.exit_code == 7
    assert result.stdout == "partial"
    assert result.stderr == "connection failed"
    assert result.error == "fixed action exited with status 7"


def test_timeout_returns_partial_output_and_cleans_temporary_directory():
    actions = action_api()
    error = subprocess.TimeoutExpired(
        cmd=["ssh.exe"], timeout=8, output="partial stdout", stderr="partial stderr"
    )
    runner = RaisingRunner(error)

    result = actions.KaliActionDispatcher(FakeVMManager(), runner=runner).dispatch(
        "check_tcp_connection",
        {"target_id": "target-1", "port": 80, "timeout_seconds": 3},
        authorized_target_id="target-1",
        authorized_target_address="172.16.20.30",
    )

    assert result.status is actions.ActionStatus.TIMED_OUT
    assert result.exit_code is None
    assert result.stdout == "partial stdout"
    assert result.stderr == "partial stderr"
    assert result.error == "fixed action timed out after 8 seconds"
    assert runner.workdir is not None
    assert not runner.workdir.exists()


def test_runner_error_is_sanitized_and_temporary_directory_is_cleaned():
    actions = action_api()
    runner = RaisingRunner(OSError("secret host detail"))

    result = actions.KaliActionDispatcher(FakeVMManager(), runner=runner).dispatch(
        "check_tcp_connection",
        {"target_id": "target-1", "port": 80},
        authorized_target_id="target-1",
        authorized_target_address="10.0.0.20",
    )

    assert result.status is actions.ActionStatus.FAILED
    assert result.error == "fixed action runner unavailable"
    assert "secret" not in repr(result)
    assert runner.workdir is not None
    assert not runner.workdir.exists()


def test_vm_discovery_error_is_returned_without_starting_an_action():
    actions = action_api()

    class BrokenVM:
        def discover_ssh_config(self):
            raise KaliVMError("private key path detail")

    runner = RecordingRunner(ProcessResult(0))
    result = actions.KaliActionDispatcher(BrokenVM(), runner=runner).dispatch(
        "check_tcp_connection",
        {"target_id": "target-1", "port": 80},
        authorized_target_id="target-1",
        authorized_target_address="192.168.56.20",
    )

    assert result.status is actions.ActionStatus.FAILED
    assert result.error == "managed Kali SSH is unavailable"
    assert "private key" not in repr(result)
    assert runner.calls == []


def test_output_is_truncated_per_stream():
    actions = action_api()
    too_large = "x" * (actions.MAX_ACTION_OUTPUT_CHARS + 50)
    runner = RecordingRunner(ProcessResult(0, too_large, too_large))

    result = actions.KaliActionDispatcher(FakeVMManager(), runner=runner).dispatch(
        "check_tcp_connection",
        {"target_id": "target-1", "port": 80},
        authorized_target_id="target-1",
        authorized_target_address="192.168.56.20",
    )

    expected = "x" * actions.MAX_ACTION_OUTPUT_CHARS + "\n[output truncated]"
    assert result.stdout == expected
    assert result.stderr == expected
    assert result.output_truncated is True


def test_default_runner_never_uses_a_shell_or_live_stdin():
    actions = action_api()
    completed = SimpleNamespace(returncode=0, stdout="ok", stderr="")
    with patch("redpath_kali.actions.subprocess.run", return_value=completed) as run:
        result = actions.KaliActionDispatcher(FakeVMManager()).dispatch(
            "check_tcp_connection",
            {"target_id": "target-1", "port": 80},
            authorized_target_id="target-1",
            authorized_target_address="192.168.56.20",
        )

    assert result.status is actions.ActionStatus.SUCCEEDED
    _, kwargs = run.call_args
    assert kwargs["shell"] is False
    assert kwargs["stdin"] is subprocess.DEVNULL
    assert kwargs["timeout"] == 10


@pytest.mark.parametrize(
    "changes",
    [
        {"hostname": "192.168.56.10"},
        {"user": "root"},
        {"identities_only": False},
        {"client_options": ("BatchMode=no",)},
    ],
)
def test_unexpected_ssh_transport_configuration_is_rejected(changes):
    actions = action_api()

    class UnsafeVM(FakeVMManager):
        def discover_ssh_config(self):
            original = super().discover_ssh_config()
            values = original.__dict__ | changes
            return SSHConfig(**values)

    runner = RecordingRunner(ProcessResult(0))
    with pytest.raises(actions.KaliActionError, match="SSH configuration"):
        actions.KaliActionDispatcher(UnsafeVM(), runner=runner).dispatch(
            "check_tcp_connection",
            {"target_id": "target-1", "port": 80},
            authorized_target_id="target-1",
            authorized_target_address="192.168.56.20",
        )

    assert runner.calls == []
