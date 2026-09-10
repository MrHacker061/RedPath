#!/usr/bin/env python3
"""Small TCP connect scanner for explicitly authorized private lab hosts."""

from __future__ import annotations

import argparse
import concurrent.futures
import ipaddress
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass


COMMON_PORTS = "22,80,135,139,443,445,3389,5985,5986,8000,8080"


@dataclass(frozen=True)
class Result:
    port: int
    state: str
    service: str
    latency_ms: float


WINDOWS_IDENTITY_COMMAND = (
    "powershell.exe -NoLogo -NoProfile -NonInteractive -Command "
    '"$ErrorActionPreference=\'Stop\'; '
    "[pscustomobject]@{User=[Environment]::UserName;Computer=$env:COMPUTERNAME;"
    "PowerShell=$PSVersionTable.PSVersion.ToString()} | ConvertTo-Json -Compress\""
)


def private_target(value: str) -> ipaddress.IPv4Address:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("target must be a literal IPv4 address") from exc
    if not isinstance(address, ipaddress.IPv4Address):
        raise argparse.ArgumentTypeError("only IPv4 lab targets are supported")
    if not (address.is_private or address.is_loopback):
        raise argparse.ArgumentTypeError("target must be private or loopback; public targets are blocked")
    return address


def parse_ports(value: str) -> list[int]:
    ports: set[int] = set()
    try:
        for item in value.split(","):
            item = item.strip()
            if not item:
                continue
            if "-" in item:
                start_text, end_text = item.split("-", 1)
                start, end = int(start_text), int(end_text)
                if start > end:
                    raise ValueError
                ports.update(range(start, end + 1))
            else:
                ports.add(int(item))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("ports must look like 22,80,443 or 1-1024") from exc
    if not ports or min(ports) < 1 or max(ports) > 65535:
        raise argparse.ArgumentTypeError("ports must be between 1 and 65535")
    if len(ports) > 4096:
        raise argparse.ArgumentTypeError("one run is limited to 4096 ports")
    return sorted(ports)


def service_name(port: int) -> str:
    try:
        return socket.getservbyport(port, "tcp")
    except OSError:
        return "unknown"


def ssh_user(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", value):
        raise argparse.ArgumentTypeError("SSH user contains unsupported characters")
    return value


def verify_windows_powershell(target: str, user: str, identity_file: Path) -> dict[str, object]:
    """Use a supplied SSH key to run one fixed, read-only PowerShell identity check."""
    command = [
        "ssh",
        "-o", "BatchMode=yes",
        "-o", "PasswordAuthentication=no",
        "-o", "KbdInteractiveAuthentication=no",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=5",
        "-i", str(identity_file),
        f"{user}@{target}",
        WINDOWS_IDENTITY_COMMAND,
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
    return {
        "attempted": True,
        "authenticated": completed.returncode == 0,
        "method": "ssh-public-key",
        "output": completed.stdout.strip(),
        "error": completed.stderr.strip(),
    }


def scan_one(target: str, port: int, timeout: float) -> Result | None:
    started = time.perf_counter()
    try:
        with socket.create_connection((target, port), timeout=timeout):
            elapsed = (time.perf_counter() - started) * 1000
            return Result(port, "open", service_name(port), round(elapsed, 2))
    except (TimeoutError, socket.timeout, ConnectionRefusedError, OSError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=private_target, help="authorized private IPv4 address")
    parser.add_argument("--ports", type=parse_ports, default=parse_ports(COMMON_PORTS))
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--json", action="store_true", help="print machine-readable JSON")
    parser.add_argument(
        "--powershell-check",
        action="store_true",
        help="use an explicitly supplied SSH key to run a fixed Windows identity check",
    )
    parser.add_argument("--ssh-user", type=ssh_user, help="authorized Windows SSH account")
    parser.add_argument("--identity-file", type=Path, help="private key authorized by the Windows VM")
    parser.add_argument(
        "--authorized",
        action="store_true",
        help="confirm that you own or have explicit permission to scan the target",
    )
    args = parser.parse_args()
    if not args.authorized:
        parser.error("--authorized is required")
    if not 0.05 <= args.timeout <= 10:
        parser.error("--timeout must be between 0.05 and 10 seconds")
    if not 1 <= args.workers <= 64:
        parser.error("--workers must be between 1 and 64")
    if args.powershell_check and (not args.ssh_user or not args.identity_file):
        parser.error("--powershell-check requires --ssh-user and --identity-file")
    if args.identity_file and not args.identity_file.is_file():
        parser.error("--identity-file must name an existing file")

    target = str(args.target)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(scan_one, target, port, args.timeout) for port in args.ports]
        results = [result for future in futures if (result := future.result()) is not None]
    results.sort(key=lambda result: result.port)

    access_check: dict[str, object] | None = None
    if args.powershell_check:
        if not any(result.port == 22 for result in results):
            access_check = {
                "attempted": False,
                "authenticated": False,
                "method": "ssh-public-key",
                "error": "TCP port 22 was not open in this scan",
            }
        else:
            access_check = verify_windows_powershell(
                target, args.ssh_user, args.identity_file.expanduser().resolve()
            )

    if args.json:
        payload: dict[str, object] = {
            "target": target,
            "open_ports": [asdict(item) for item in results],
        }
        if access_check is not None:
            payload["powershell_access_check"] = access_check
        print(json.dumps(payload, indent=2))
    else:
        print(f"Authorized TCP scan of {target}: {len(results)} open port(s)")
        for result in results:
            print(f"{result.port:5}/tcp  {result.state:4}  {result.service:12}  {result.latency_ms:8.2f} ms")
        if access_check is not None:
            if access_check["authenticated"]:
                print("PowerShell access: authenticated with the supplied SSH key")
                print(access_check["output"])
            else:
                print(f"PowerShell access: not authenticated ({access_check['error']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
