"""Safe, evidence-only parsing for user-supplied Nmap XML exports."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Literal

from defusedxml import ElementTree as DefusedET
from defusedxml.common import DefusedXmlException
from pydantic import Field

from redpath.contracts import EvidenceState, NormalizedFinding, StrictModel

DEFAULT_MAX_XML_BYTES = 5 * 1024 * 1024


class NmapImportError(ValueError):
    """Raised when supplied evidence cannot be safely imported."""


class NmapService(StrictModel):
    name: str | None = None
    product: str | None = None
    version: str | None = None
    extra_info: str | None = None
    tunnel: str | None = None
    detection_method: str | None = None
    confidence: int | None = Field(default=None, ge=0, le=10)


class NmapPortEvidence(StrictModel):
    evidence_ref: str
    state: EvidenceState = EvidenceState.OBSERVED
    protocol: Literal["tcp", "udp"]
    port: int = Field(ge=1, le=65535)
    port_state: str
    state_reason: str | None = None
    service: NmapService


class NmapHostEvidence(StrictModel):
    evidence_ref: str
    state: EvidenceState = EvidenceState.OBSERVED
    status: str | None = None
    addresses: list[str]
    hostnames: list[str]
    ports: list[NmapPortEvidence]


class NmapScanMetadata(StrictModel):
    scanner: Literal["nmap"] = "nmap"
    source_sha256: str
    source_size_bytes: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    command_redacted: Literal[True] = True


class NmapImportResult(StrictModel):
    scan_id: str
    session_id: str
    target_id: str
    metadata: NmapScanMetadata
    hosts: list[NmapHostEvidence]
    findings: list[NormalizedFinding]


def parse_nmap_xml_file(path: str | Path, *, scan_id: str, session_id: str, target_id: str, max_bytes: int = DEFAULT_MAX_XML_BYTES) -> NmapImportResult:
    """Read and parse a local XML file without performing network activity."""
    source = Path(path)
    try:
        size = source.stat().st_size
    except OSError as exc:
        raise NmapImportError("Nmap XML evidence could not be read") from exc
    if size > max_bytes:
        raise NmapImportError(f"Nmap XML exceeds the {max_bytes}-byte limit")
    try:
        data = source.read_bytes()
    except OSError as exc:
        raise NmapImportError("Nmap XML evidence could not be read") from exc
    return parse_nmap_xml_bytes(data, scan_id=scan_id, session_id=session_id, target_id=target_id, max_bytes=max_bytes)


def parse_nmap_xml_bytes(data: bytes, *, scan_id: str, session_id: str, target_id: str, max_bytes: int = DEFAULT_MAX_XML_BYTES) -> NmapImportResult:
    """Normalize supplied Nmap XML into stable observed-evidence records."""
    if max_bytes < 1:
        raise ValueError("max_bytes must be positive")
    if len(data) > max_bytes:
        raise NmapImportError(f"Nmap XML exceeds the {max_bytes}-byte limit")
    if not data.strip():
        raise NmapImportError("Nmap XML evidence is empty")
    digest = sha256(data).hexdigest()
    try:
        root = DefusedET.fromstring(data)
    except (DefusedXmlException, DefusedET.ParseError, UnicodeError) as exc:
        raise NmapImportError("Nmap XML is malformed or contains unsafe XML") from exc
    if root.tag != "nmaprun" or root.get("scanner") not in (None, "nmap"):
        raise NmapImportError("XML is not an Nmap scan export")

    hosts, findings = [], []
    prefix = f"nmap:{digest}"
    for host_index, host_node in enumerate(root.findall("host"), start=1):
        host_ref = f"{prefix}:host:{host_index}"
        addresses = [value for node in host_node.findall("address") if (value := node.get("addr"))]
        hostnames = [value for node in host_node.findall("./hostnames/hostname") if (value := node.get("name"))]
        status_node = host_node.find("status")
        port_records = []
        for port_index, port_node in enumerate(host_node.findall("./ports/port"), start=1):
            protocol, raw_port = port_node.get("protocol"), port_node.get("portid")
            if protocol not in {"tcp", "udp"} or raw_port is None:
                continue
            try:
                port = int(raw_port)
            except ValueError:
                continue
            if not 1 <= port <= 65535:
                continue
            state_node = port_node.find("state")
            port_state = state_node.get("state", "unknown") if state_node is not None else "unknown"
            service = _service_from_node(port_node.find("service"))
            port_ref = f"{host_ref}:port:{protocol}:{port}:{port_index}"
            port_records.append(NmapPortEvidence(evidence_ref=port_ref, protocol=protocol, port=port, port_state=port_state, state_reason=state_node.get("reason") if state_node is not None else None, service=service))
            if port_state == "open":
                findings.append(NormalizedFinding(id=f"finding:{digest}:{host_index}:{protocol}:{port}", session_id=session_id, target_id=target_id, state=EvidenceState.OBSERVED, category="open_port", protocol=protocol, port=port, service_hint=service.name, evidence_source=port_ref))
        hosts.append(NmapHostEvidence(evidence_ref=host_ref, status=status_node.get("state") if status_node is not None else None, addresses=addresses, hostnames=hostnames, ports=port_records))

    return NmapImportResult(scan_id=scan_id, session_id=session_id, target_id=target_id, metadata=NmapScanMetadata(source_sha256=digest, source_size_bytes=len(data), started_at=_epoch_datetime(root.get("start")), finished_at=_finished_at(root)), hosts=hosts, findings=findings)


def _service_from_node(node) -> NmapService:
    if node is None:
        return NmapService()
    confidence = node.get("conf")
    return NmapService(name=node.get("name"), product=node.get("product"), version=node.get("version"), extra_info=node.get("extrainfo"), tunnel=node.get("tunnel"), detection_method=node.get("method"), confidence=int(confidence) if confidence and confidence.isdigit() else None)


def _finished_at(root) -> datetime | None:
    finished = root.find("./runstats/finished")
    return _epoch_datetime(finished.get("time")) if finished is not None else None


def _epoch_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None
