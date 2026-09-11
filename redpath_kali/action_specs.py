"""Canonical closed-world validation and argv rendering for Kali actions."""

from __future__ import annotations

import ipaddress
import re
import shlex
from dataclasses import dataclass

from .vm import KaliVMError

_TARGET_ID_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_RFC1918_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)
_IPV6_ULA = ipaddress.ip_network("fc00::/7")


class KaliActionError(KaliVMError):
    """An action request failed the fixed, authorized action boundary."""


@dataclass(frozen=True)
class FixedActionSpec:
    name: str
    target_id: str
    target_address: str
    port: int
    guest_argv: tuple[str, ...]
    process_timeout: int

    @property
    def remote_command(self) -> str:
        """Render the exact fixed argv for the managed SSH guest shell."""
        return shlex.join(self.guest_argv)


def _target_id(value: object) -> str:
    if type(value) is not str or _TARGET_ID_PATTERN.fullmatch(value) is None:
        raise KaliActionError("authorized target identifier is invalid")
    return value


def _private_address(value: object) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    if type(value) is not str or "%" in value:
        raise KaliActionError("target must be a literal private lab address")
    try:
        address = ipaddress.ip_address(value)
    except ValueError as exc:
        raise KaliActionError("target must be a literal private lab address") from exc
    allowed = (
        isinstance(address, ipaddress.IPv4Address)
        and any(address in network for network in _RFC1918_NETWORKS)
    ) or (isinstance(address, ipaddress.IPv6Address) and address in _IPV6_ULA)
    if not allowed:
        raise KaliActionError("target must be a literal private lab address")
    return address


def _integer(value: object, *, name: str, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise KaliActionError(f"{name} must be an integer from {minimum} through {maximum}")
    return value


def render_fixed_action(
    action_name: object,
    arguments: object,
    authorized_target_id: object,
    authorized_target_address: object,
) -> FixedActionSpec:
    """Validate scope and render one canonical, non-shell guest argv array."""
    schemas = {
        "check_tcp_connection": ({"target_id", "port"}, {"timeout_seconds"}),
        "inspect_http_headers": ({"target_id", "port"}, set()),
        "inspect_tls_certificate": ({"target_id", "port"}, set()),
    }
    if type(action_name) is not str or action_name not in schemas:
        raise KaliActionError("unknown fixed Kali action")
    if type(arguments) is not dict:
        raise KaliActionError("action arguments must be a plain object")
    required, optional = schemas[action_name]
    keys = set(arguments)
    if keys != required and not (required <= keys <= required | optional):
        raise KaliActionError("action arguments do not match the fixed schema")
    target_id = _target_id(authorized_target_id)
    if _target_id(arguments.get("target_id")) != target_id:
        raise KaliActionError("action target does not match the authorized target")
    address = _private_address(authorized_target_address)
    address_text = str(address)
    port = _integer(arguments.get("port"), name="port", minimum=1, maximum=65_535)
    endpoint = f"[{address_text}]" if address.version == 6 else address_text
    if action_name == "check_tcp_connection":
        timeout = _integer(arguments.get("timeout_seconds", 5), name="timeout_seconds", minimum=1, maximum=10)
        argv = ("timeout", "--signal=KILL", f"{timeout}s", "nc", "-vz", "-w", str(timeout), address_text, str(port))
        process_timeout = timeout + 5
    elif action_name == "inspect_http_headers":
        argv = (
            "timeout", "--signal=KILL", "10s", "curl", "--head", "--silent", "--show-error",
            "--max-time", "8", "--connect-timeout", "5", "--proto", "=http", "--",
            f"http://{endpoint}:{port}/",
        )
        process_timeout = 15
    else:
        argv = ("timeout", "--signal=KILL", "10s", "openssl", "s_client", "-brief", "-connect", f"{endpoint}:{port}")
        process_timeout = 15
    return FixedActionSpec(action_name, target_id, address_text, port, argv, process_timeout)
