import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from redpath_kali import KaliVMError, KaliVMManager, ProcessResult, VMState, parse_ssh_config, parse_status

SSH_CONFIG_TEMPLATE = """Host kali-headless
  HostName 127.0.0.1
  User vagrant
  Port 2207
  IdentityFile {identity_file}
  IdentitiesOnly yes
"""


class FakeRunner:
    def __init__(self, responses): self.responses, self.calls = list(responses), []
    def __call__(self, arguments, cwd, timeout):
        self.calls.append((tuple(arguments), cwd, timeout))
        return self.responses.pop(0)


def make_repository(root):
    vm = root / "vm"; vm.mkdir()
    (vm / "KaliVM.ps1").write_text("# fixture", encoding="utf-8")
    (vm / "Vagrantfile").write_text('ip: "192.168.56.10"', encoding="utf-8")
    (vm / "kali-vm.json").write_text(json.dumps({"vmName": "Headless-Kali-Terminal", "memoryMB": 4096, "cpus": 4}), encoding="utf-8")


def make_state(root):
    state = root / "state"
    key = state / "machines" / "default" / "virtualbox" / "private_key"
    key.parent.mkdir(parents=True)
    key.write_text("test-only-key", encoding="utf-8")
    return state, key


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state, self.key = make_state(Path(self.temp.name))
        self.config = SSH_CONFIG_TEMPLATE.format(identity_file=self.key.as_posix())

    def tearDown(self): self.temp.cleanup()

    def test_status(self):
        self.assertEqual(parse_status("VM state: poweroff\n"), VMState.POWEROFF)
        with self.assertRaises(KaliVMError): parse_status("no state")
        with self.assertRaises(KaliVMError): parse_status("VM state: running\nVM state: poweroff")

    def test_dynamic_ssh_config(self):
        config = parse_ssh_config(self.config, managed_state_root=self.state)
        self.assertEqual(config.port, 2207)
        self.assertTrue(config.identity_file.is_absolute())

    def test_ssh_config_restrictions(self):
        for replacement in ("localhost", "::1", "192.168.1.5"):
            with self.assertRaises(KaliVMError):
                parse_ssh_config(self.config.replace("127.0.0.1", replacement), managed_state_root=self.state)
        with self.assertRaises(KaliVMError):
            parse_ssh_config(self.config.replace("IdentitiesOnly yes", "IdentitiesOnly no"), managed_state_root=self.state)

    def test_ssh_key_must_exist_inside_managed_state(self):
        outside = Path(self.temp.name) / "outside_key"; outside.write_text("key")
        escaped = SSH_CONFIG_TEMPLATE.format(identity_file=outside.as_posix())
        with self.assertRaises(KaliVMError): parse_ssh_config(escaped, managed_state_root=self.state)
        self.key.unlink()
        with self.assertRaises(KaliVMError): parse_ssh_config(self.config, managed_state_root=self.state)

    def test_ssh_key_rejects_symlink_and_wrong_managed_filename(self):
        unrelated = self.state / "machines" / "default" / "virtualbox" / "other_key"
        unrelated.write_text("key")
        wrong = SSH_CONFIG_TEMPLATE.format(identity_file=unrelated.as_posix())
        with self.assertRaises(KaliVMError): parse_ssh_config(wrong, managed_state_root=self.state)
        with patch("redpath_kali.vm._is_reparse_or_symlink", side_effect=lambda path: Path(path) == self.key):
            with self.assertRaises(KaliVMError):
                parse_ssh_config(self.config, managed_state_root=self.state)

    def test_ssh_key_rejects_unc_path(self):
        unc = SSH_CONFIG_TEMPLATE.format(identity_file=r"\\server\share\private_key")
        with self.assertRaises(KaliVMError): parse_ssh_config(unc, managed_state_root=self.state)

    def test_ssh_config_exposes_noninteractive_key_only_options(self):
        config = parse_ssh_config(self.config, managed_state_root=self.state)
        self.assertIn("BatchMode=yes", config.client_options)
        self.assertIn("PasswordAuthentication=no", config.client_options)
        self.assertIn("KbdInteractiveAuthentication=no", config.client_options)
        self.assertIn("PreferredAuthentications=publickey", config.client_options)
        self.assertIn("ForwardAgent=no", config.client_options)


class ManagerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.root = Path(self.temp.name); make_repository(self.root)
        self.state, self.key = make_state(self.root)
        self.ssh_config = SSH_CONFIG_TEMPLATE.format(identity_file=self.key.as_posix())
    def tearDown(self): self.temp.cleanup()

    def manager(self, responses):
        runner = FakeRunner(responses)
        return KaliVMManager(self.root, runner=runner, managed_state_root=self.state), runner

    def test_fixed_status_command(self):
        manager, runner = self.manager([ProcessResult(0, "VM state: poweroff\n")])
        self.assertEqual(manager.status().state, VMState.POWEROFF)
        self.assertEqual(runner.calls[0][0][-1], "status")
        self.assertIn("-NonInteractive", runner.calls[0][0]); self.assertNotIn("run", runner.calls[0][0])

    def test_start_and_verify(self):
        manager, runner = self.manager([ProcessResult(0, "started"), ProcessResult(0, "VM state: running\n")])
        self.assertEqual(manager.start().state, VMState.RUNNING)
        self.assertEqual([c[0][-1] for c in runner.calls], ["start", "status"])

    def test_discover_ssh_after_state_check(self):
        manager, runner = self.manager([ProcessResult(0, "VM state: running\n"), ProcessResult(0, self.ssh_config)])
        self.assertEqual(manager.discover_ssh_config().port, 2207)
        self.assertEqual([c[0][-1] for c in runner.calls], ["status", "ssh-config"])

    def test_graceful_stop_no_force_and_verify(self):
        manager, runner = self.manager([ProcessResult(0, "shutdown"), ProcessResult(0, "VM state: poweroff\n")])
        self.assertEqual(manager.stop().state, VMState.POWEROFF)
        self.assertNotIn("-Force", runner.calls[0][0])

    def test_failure_and_unverified_start_raise(self):
        manager, _ = self.manager([ProcessResult(1, "", "failed")])
        with self.assertRaises(KaliVMError): manager.status()
        manager, _ = self.manager([ProcessResult(0, "started"), ProcessResult(0, "VM state: poweroff\n")])
        with self.assertRaises(KaliVMError): manager.start()

    def test_changed_identity_rejected(self):
        (self.root / "vm" / "kali-vm.json").write_text(json.dumps({"vmName": "other", "memoryMB": 4096, "cpus": 4}))
        with self.assertRaises(KaliVMError): KaliVMManager(self.root, runner=FakeRunner([]))

    def test_relative_repository_root_is_rejected(self):
        with self.assertRaises(KaliVMError): KaliVMManager("relative/repository", runner=FakeRunner([]))

    def test_symlinked_lifecycle_script_is_rejected(self):
        script = self.root / "vm" / "KaliVM.ps1"
        with patch("redpath_kali.vm._is_reparse_or_symlink", side_effect=lambda path: Path(path) == script):
            with self.assertRaises(KaliVMError):
                KaliVMManager(self.root, runner=FakeRunner([]), managed_state_root=self.state)


if __name__ == "__main__": unittest.main()
