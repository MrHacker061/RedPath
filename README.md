# RedPath Development Workspace

This repository contains the planning documents and current private-lab tools
for **RedPath: AI Red Team Training**. RedPath is designed to help beginners
understand authorized cybersecurity labs while keeping the AI separated from
direct command execution.

## Repository layout

```text
redpath/    FastAPI backend, strict shared contracts, and SQLite models
docs/       RedPath context, architecture, connections, and implementation tasks
scanner/    Authorized private-lab Python scanner
redpath_ai/ Strict recommendation providers, prompts, and AI schemas
tests/      Python scanner tests and PowerShell VM tests
vm/         Headless Kali manager, Vagrant configuration, and provisioning
.local/     Generated machine-specific files; ignored by Git
```

## Backend foundation

The backend binds to localhost and currently exposes only a health check. It
defines strict shared contracts and the initial SQLite data model. It does not
execute tools or accept model-generated commands.

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\python -m pytest tests\test_backend_foundation.py
.\.venv\Scripts\redpath-api.exe
```

Copy `.env.example` to `.env` for local overrides. The `.env` file is ignored.
The supported launcher rejects any non-loopback `REDPATH_HOST`. AI proposals are
untrusted wire data and must pass `validate_untrusted_proposal`, policy review,
and exact user approval before any later execution component may use them.
Approval creation must store `action_protected_hash(validated_proposal)`. The
executor must call `revalidate_approval_before_execution` immediately before
running an action so changes to its name or arguments fail closed. The database
also binds each action to the exact approval, proposal, and session tuple.

The files in `docs`, `scanner`, `tests`, and `vm`, along with this README,
`.gitignore`, and `.gitattributes`, belong in GitHub. Do not add `.local`,
`__pycache__`, `.vagrant`, virtual disks, ISO files, logs, environment files,
API keys, SSH private keys, or other generated machine state.

Important project documents:

- [Full project context](./docs/REDPATH_CONTEXT.md)
- [System layout](./docs/REDPATH_SYSTEM_MAP.md)
- [Component connections](./docs/REDPATH_PROJECT_CONNECTIONS.md)
- [Four-worker implementation tasks](./docs/REDPATH_IMPLEMENTATION_TASKS.md)
- [Local Ollama setup](./docs/OLLAMA_SETUP.md)

## AI recommendation foundation

Install the Python dependency and run the tests:

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

`redpath_ai` contains the provider interface, a loopback-only Ollama client, and
a deterministic fallback. It produces validated recommendations and beginner
explanations only. It has no command runner, SSH client, scanner integration, or
execution authority. The backend remains responsible for policy and approval.

## Headless Kali terminal

This is a Windows command-line program that creates a real Kali Linux virtual
machine, runs it with no VirtualBox window, and connects to it as a normal
terminal over SSH.

It uses Kali's official `kalilinux/rolling` Vagrant box with Oracle VirtualBox.
Vagrant handles the large image download, VirtualBox VM creation, SSH port,
generated per-VM key, and repeatable start/stop lifecycle. This is substantially
less fragile than scripting Kali's graphical installer or trying to enable SSH
inside an unknown prebuilt disk.

## Quick start on this PC

VirtualBox 7.2.16 and Windows OpenSSH are already installed. Vagrant is the one
missing prerequisite.

Open PowerShell in this folder and run:

```powershell
.\vm\KaliVM.cmd install
.\vm\KaliVM.cmd doctor
.\vm\KaliVM.cmd create
.\vm\KaliVM.cmd terminal
```

`install` may show a Windows administrator prompt. The first `create` downloads
roughly 5 GB and can take a while. The resulting box plus VM usually needs well
over 10 GB, so the launcher requires at least 20 GB free on every drive used by
the Vagrant box cache or VirtualBox VM folder before create/rebuild.

After the VM exists, double-click [Open-Kali-Terminal.cmd](./vm/Open-Kali-Terminal.cmd)
or run:

```powershell
.\vm\KaliVM.cmd terminal
```

Inside the terminal, you are logged in as user `vagrant` on host
`kali-headless`. Commands entered there run in Kali, not Windows. Type `exit` to
leave the terminal. The VM intentionally stays running until you stop it:

```powershell
.\vm\KaliVM.cmd stop
```

`stop` asks Kali itself to power off and will not silently pull virtual power if
the guest is unresponsive. `stop -Force` is available as an explicit last resort
and can lose unsaved guest data.

## How it works

```text
vm/KaliVM.cmd / vm/KaliVM.ps1
        |
        v
Vagrant lifecycle + unique SSH key
        |
        v
VirtualBox headless VM (NAT only)
        |
        v
127.0.0.1:dynamic-port --> Kali sshd:22 --> terminal
```

The SSH forward is bound to `127.0.0.1`, so another computer on the LAN cannot
connect to it. It starts at host port 2223 and Vagrant automatically chooses a
different local port if necessary. This matters here because the saved
`CS 4440 VM` already has a `127.0.0.1:2222 -> guest:22` rule. Never assume the
chosen port; `status` and `ssh-config` read the actual value from Vagrant.

The source manifest [kali-vm.json](./vm/kali-vm.json) records these selections and
provenance details:

- Official catalog box: `kalilinux/rolling`
- Version: `2026.2.0`
- Recorded catalog SHA-256: `503366b477184fcfcbb3888f7e887d267d3b588dd697053ba99a3e9527370626`
- Default resources: 4 CPUs and 4096 MB RAM

The recorded value documents the live official catalog value checked when this
program was built; it is not a second verifier. Vagrant enforces the checksum
from format-validated catalog metadata served over TLS during download. Normal starts do
not check for updates, which keeps later boots deterministic and allows them to
work from the locally cached box.

## Commands

```text
vm\KaliVM.cmd help
vm\KaliVM.cmd doctor
vm\KaliVM.cmd install
vm\KaliVM.cmd validate
vm\KaliVM.cmd create
vm\KaliVM.cmd repair
vm\KaliVM.cmd start
vm\KaliVM.cmd terminal
vm\KaliVM.cmd run -GuestCommand "id && uname -a"
vm\KaliVM.cmd run -GuestCommandFile .\commands.sh
vm\KaliVM.cmd stop
vm\KaliVM.cmd status
vm\KaliVM.cmd health
vm\KaliVM.cmd ssh-config
vm\KaliVM.cmd snapshot -SnapshotName before-lab
vm\KaliVM.cmd snapshots
vm\KaliVM.cmd restore -SnapshotName before-lab -Force
vm\KaliVM.cmd destroy -Force
vm\KaliVM.cmd rebuild -Force
```

`terminal` is idempotent: it starts an existing stopped VM and creates one if
none exists. `create` and `start` run a health check that proves the guest is
Kali x86-64, its SSH service is active, and password/root SSH login is disabled.
`repair` re-runs that idempotent SSH hardening if first-boot provisioning was
interrupted.

For a shell command containing nested quotes, use `-GuestCommandFile` or invoke
`vm\KaliVM.ps1` directly from PowerShell. Windows batch argument forwarding can
alter nested quotes even though ordinary commands work through `vm\KaliVM.cmd`.
File contents and built-in health scripts are base64-transported before the
native Vagrant call so Windows PowerShell 5.1 cannot split their nested quotes.

The `-Force` requirement on restore, destroy, and rebuild is deliberate:

- `restore` discards guest disk changes newer than the snapshot.
- `destroy` removes the VM disk but leaves the downloaded base box cached.
- `rebuild` validates the configuration, checks storage, and ensures the exact
  verified base box is cached before it destroys the existing VM and creates a
  clean one.

A snapshot is convenient rollback state, not a backup. Copy important files to
Windows or another backup location before destructive operations.

## Use another SSH client or VS Code

Export the exact connection generated by Vagrant:

```powershell
.\vm\KaliVM.cmd ssh-config -OutputPath .\.local\kali-ssh-config
ssh -F .\.local\kali-ssh-config kali-headless
```

Export refuses to overwrite an existing file unless `-Force` is added, which
helps prevent accidentally replacing a real personal SSH config.

For VS Code, install Microsoft's **Remote - SSH** extension, add the contents of
that generated config to an SSH config file, and connect to `kali-headless`.
VS Code's window remains on Windows while its remote terminal, files, and tools
run inside Kali.

## Security choices

The project makes conservative terminal-only choices by default:

- VirtualBox starts with `gui = false` and uses NAT, not a bridged/public NIC.
- SSH binds only to Windows loopback and uses a generated per-VM private key.
- First-boot provisioning verifies the key exists, then disables password,
  keyboard-interactive, and root SSH logins.
- The Windows project folder is not mounted into Kali.
- Shared clipboard, clipboard file transfer, drag-and-drop, audio, and VRDE are
  disabled.
- Guest X11 and SSH-agent forwarding are disabled; TCP forwarding remains
  enabled so tools such as VS Code Remote-SSH can function.
- Concurrent VM-changing commands are blocked by a named Windows mutex.
- A failed `vagrant up` preserves the partially created VM instead of silently
  deleting its disk, which makes diagnosis and retry possible.

Kali is a security-testing distribution. Only scan or test systems you own or
have explicit permission to assess.

## Authorized Windows lab scanner

[`scanner/lab_scanner.py`](./scanner/lab_scanner.py) is a small TCP connect scanner intended for a Windows VM on a
private VirtualBox lab network. It blocks public IP addresses, requires an
explicit authorization flag, caps concurrency, and does not exploit services or
open a shell.

Copy it into Kali and run it with the Windows VM's private address:

```bash
python3 ~/lab_scanner.py 192.168.56.20 --authorized
python3 ~/lab_scanner.py 192.168.56.20 --ports 1-1024 --authorized
python3 ~/lab_scanner.py 192.168.56.20 --ports 22,80,445,3389,5985 --authorized --json
```

Kali is configured with adapter 1 as NAT for updates and adapter 2 as host-only
at `192.168.56.10`. Attach the Windows VM to the existing `VirtualBox Host-Only
Ethernet Adapter` and assign it an unused address such as `192.168.56.20/24`.
Windows should classify the host-only adapter as a private network. Enable only
the specific Windows services you intend to test.
For remote command exercises, use Windows OpenSSH with key authentication rather
than a reverse shell.

After intentionally installing a Kali public key for a Windows lab account, the
scanner can perform a separately triggered access check. It disables password
and interactive authentication and runs only fixed read-only PowerShell commands
that report the account name, computer name, and PowerShell version:

```bash
python3 ~/lab_scanner.py 192.168.56.20 --ports 22 --authorized \
  --powershell-check --ssh-user LabUser --identity-file ~/.ssh/windows_lab
```

This option does not guess credentials, exploit a service, accept arbitrary
remote commands, change the Windows VM, or establish a reverse shell.

## State and files

The VM source and configuration stay together in the `vm` folder. Machine-specific Vagrant state,
including its VM UUID and generated private key, is kept at:

```text
%LOCALAPPDATA%\HeadlessKaliTerminal\state
```

The large global box cache remains in Vagrant's normal per-user data directory,
and VirtualBox stores the VM disk in its configured machine folder. This keeps
private machine state out of Downloads and lets the launcher keep recognizing
the VM if this project folder is renamed or moved. Keep `vm/Vagrantfile`,
`vm/kali-vm.json`, and `vm/scripts` together.

## Configuration

Edit [kali-vm.json](./vm/kali-vm.json) while the VM is stopped. Reasonable values
for this computer are already selected. Changes to the VM display name or box
source generally require a rebuild; CPU and memory changes take effect after a
Vagrant reload/restart.

The `box.directUrl` and `box.directSha256` fields are intentionally centralized.
If Kali moves its Vagrant distribution away from the current catalog, set an
exact official HTTPS `.box` URL, its SHA-256, its matching version label, and a
short `box.name` label such as `kali-direct`. The program appends the complete
SHA-256 to the effective Vagrant cache name. Changing the expected bytes therefore
creates a different cache identity instead of silently reusing an older box. Do
not use an unverified third-party image.

## Troubleshooting

### `doctor` says Vagrant is missing after install

Close PowerShell, open a new one, and run:

```powershell
.\vm\KaliVM.cmd doctor
```

The script also checks Vagrant's normal absolute install paths, so a new shell
is only needed if the installer has not finished updating the environment.

### VM startup is slow

Windows VBS/hypervisor is active on this computer. VirtualBox can fall back to
its NEM backend when direct AMD-V is unavailable. The existing Ubuntu VM has
successfully booted that way, so this is a performance warning rather than proof
of failure. The launcher allows ten minutes for a slow first boot. It does not
disable Hyper-V, VBS, Credential Guard, or other Windows security features.

### Create was interrupted or provisioning failed

Run:

```powershell
.\vm\KaliVM.cmd status
.\vm\KaliVM.cmd repair
```

Vagrant can resume an interrupted box download for up to 24 hours, and `create`
is safe to rerun. The
program uses `--no-destroy-on-error`, so failed VM state remains available for
diagnosis. Do not use `rebuild -Force` unless losing guest-only data is okay.

### Check the exact terminal path

```powershell
.\vm\KaliVM.cmd status
.\vm\KaliVM.cmd ssh-config
.\vm\KaliVM.cmd health
```

This separates VM state, local SSH configuration, and guest identity/service
checks rather than guessing from a VirtualBox preview.

## Upstream lifecycle note

As of September 1, 2026, HashiCorp's dedicated HCP Vagrant deprecation schedule
lists an accelerated timeline: creation of new boxes/registries ends October 1,
2026; support and maintenance end November 2, 2026; and operations end December
31, 2026. The community Vagrant CLI remains available. This does not prevent a
cached box from working, and the manifest supports a checksum-pinned direct
official source when Kali publishes its long-term replacement. The manager does
not silently switch to an untested image.

Official references:

- [Kali Vagrant documentation](https://www.kali.org/docs/virtualization/install-vagrant-guest-vm/)
- [Kali Vagrant rebuild announcement](https://www.kali.org/blog/kali-vagrant-rebuilt/)
- [Kali default credentials](https://www.kali.org/docs/introduction/default-credentials/)
- [Vagrant VirtualBox headless configuration](https://developer.hashicorp.com/vagrant/docs/providers/virtualbox/configuration)
- [Vagrant forwarded-port security](https://developer.hashicorp.com/vagrant/docs/networking/forwarded_ports)
- [Vagrant SSH key settings](https://developer.hashicorp.com/vagrant/docs/vagrantfile/ssh_settings)
- [Vagrant box downloads and checksums](https://developer.hashicorp.com/vagrant/docs/cli/box)
- [Vagrant up failure-preservation option](https://developer.hashicorp.com/vagrant/docs/cli/up)
- [Vagrant environment/state paths](https://developer.hashicorp.com/vagrant/docs/other/environmental-variables)
- [HCP Vagrant end-of-life dates](https://developer.hashicorp.com/hcp/docs/vagrant/hcp-vagrant-eol)
