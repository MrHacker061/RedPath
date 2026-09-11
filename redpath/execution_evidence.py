"""Closed-world evidence extraction from fixed Kali action results."""
import json
import re
from typing import Any

from redpath_kali import ActionResult, ActionStatus

MAX_INSPECTED_OUTPUT_CHARS = 4_096
MAX_PERSISTED_EVIDENCE_CHARS = 16_384
_HTTP_STATUS = re.compile(r"(?m)^HTTP/\d(?:\.\d)?\s+([1-5]\d{2})(?:\s|$)")
_TLS_PROTOCOL = re.compile(r"(?mi)^Protocol version:\s*(TLSv1(?:\.[123])?)\s*$")
_TLS_CIPHER = re.compile(r"(?mi)^Ciphersuite:\s*([A-Z0-9_-]{1,64})\s*$")
_TLS_VERIFICATION = re.compile(r"(?mi)^Verification:\s*([A-Z][A-Z ]{0,31})\s*$")


def structured_evidence(result: ActionResult) -> list[dict[str, Any]]:
    """Extract only fixed, allowlisted facts; never return raw process output."""

    stdout = result.stdout[:MAX_INSPECTED_OUTPUT_CHARS]
    stderr = result.stderr[:MAX_INSPECTED_OUTPUT_CHARS]
    item: dict[str, Any] = {
        "kind": result.action_name.removeprefix("inspect_"),
        "action_name": result.action_name,
        "target_id": result.target_id,
        "target_address": result.target_address,
        "port": result.port,
        "outcome": result.status.value,
        "output_truncated": (
            result.output_truncated
            or len(result.stdout) > MAX_INSPECTED_OUTPUT_CHARS
            or len(result.stderr) > MAX_INSPECTED_OUTPUT_CHARS
        ),
    }
    if result.action_name == "check_tcp_connection":
        item["kind"] = "tcp_connection"
        item["reachable"] = result.status is ActionStatus.SUCCEEDED
    elif result.action_name == "inspect_http_headers":
        match = _HTTP_STATUS.search(stdout)
        item["http_status"] = int(match.group(1)) if match else None
    else:
        inspected = stdout + "\n" + stderr
        protocol = _TLS_PROTOCOL.search(inspected)
        cipher = _TLS_CIPHER.search(inspected)
        verification = _TLS_VERIFICATION.search(inspected)
        item["protocol"] = protocol.group(1) if protocol else None
        item["cipher_suite"] = cipher.group(1) if cipher else None
        item["verification"] = (
            "verified"
            if verification and verification.group(1) == "OK"
            else "failed" if verification else "unknown"
        )
    if result.status is not ActionStatus.SUCCEEDED:
        item["failure_category"] = (
            "timed_out"
            if result.status is ActionStatus.TIMED_OUT
            else "fixed_action_failed"
        )
    evidence = [item]
    serialized = json.dumps(
        evidence, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    if len(serialized) > MAX_PERSISTED_EVIDENCE_CHARS:
        raise ValueError("bounded action evidence exceeded its persistence limit")
    return evidence
