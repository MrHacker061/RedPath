from hashlib import sha256
from pathlib import Path

import pytest

from redpath.nmap_parser import NmapImportError, parse_nmap_xml_bytes, parse_nmap_xml_file


FIXTURE = Path(__file__).parent / "fixtures" / "nmap_sample.xml"
IDS = {"scan_id": "scan-1", "session_id": "session-1", "target_id": "target-1"}


def test_parses_hosts_ports_services_times_and_open_findings():
    result = parse_nmap_xml_file(FIXTURE, **IDS)
    assert result.metadata.source_sha256 == sha256(FIXTURE.read_bytes()).hexdigest()
    assert result.metadata.started_at.isoformat() == "2023-11-14T22:13:20+00:00"
    assert result.metadata.finished_at.isoformat() == "2023-11-14T22:14:20+00:00"
    assert result.metadata.command_redacted is True
    assert result.hosts[0].addresses == ["192.168.56.20"]
    assert result.hosts[0].hostnames == ["lab-target.local"]
    assert [(p.protocol, p.port, p.port_state) for p in result.hosts[0].ports] == [("tcp", 22, "open"), ("tcp", 80, "closed"), ("udp", 53, "open")]
    assert result.hosts[0].ports[0].service.product == "OpenSSH"
    assert [(f.protocol, f.port, f.service_hint, f.state.value) for f in result.findings] == [("tcp", 22, "ssh", "observed"), ("udp", 53, "domain", "observed")]


def test_contract_is_bound_to_scan_session_and_target():
    result = parse_nmap_xml_file(FIXTURE, **IDS)
    assert result.scan_id == "scan-1"
    assert all(f.session_id == "session-1" and f.target_id == "target-1" for f in result.findings)
    assert all(f.evidence_source.startswith(f"nmap:{result.metadata.source_sha256}:") for f in result.findings)


def test_identical_evidence_has_stable_ids_and_references():
    first = parse_nmap_xml_file(FIXTURE, **IDS)
    second = parse_nmap_xml_file(FIXTURE, **IDS)
    assert [f.id for f in first.findings] == [f.id for f in second.findings]
    assert [f.evidence_source for f in first.findings] == [f.evidence_source for f in second.findings]


def test_rejects_oversized_input_before_parsing(tmp_path):
    source = tmp_path / "large.xml"
    source.write_bytes(b"x" * 11)
    with pytest.raises(NmapImportError, match="10-byte limit"):
        parse_nmap_xml_file(source, max_bytes=10, **IDS)
    with pytest.raises(NmapImportError, match="10-byte limit"):
        parse_nmap_xml_bytes(b"x" * 11, max_bytes=10, **IDS)


@pytest.mark.parametrize("data", [b"", b"<nmaprun>", b"<not-nmap/>"])
def test_rejects_empty_malformed_and_non_nmap_xml(data):
    with pytest.raises(NmapImportError):
        parse_nmap_xml_bytes(data, **IDS)


def test_rejects_dtd_entity_payload():
    unsafe = b'<!DOCTYPE x [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><nmaprun>&xxe;</nmaprun>'
    with pytest.raises(NmapImportError, match="unsafe XML"):
        parse_nmap_xml_bytes(unsafe, **IDS)


def test_ignores_unsupported_or_invalid_ports_without_inventing_evidence():
    xml = b'''<nmaprun scanner="nmap"><host><ports>
      <port protocol="sctp" portid="80"><state state="open"/></port>
      <port protocol="tcp" portid="70000"><state state="open"/></port>
      <port protocol="tcp" portid="bad"><state state="open"/></port>
    </ports></host></nmaprun>'''
    result = parse_nmap_xml_bytes(xml, **IDS)
    assert result.hosts[0].ports == []
    assert result.findings == []


def test_does_not_preserve_nmap_command_line():
    xml = b'<nmaprun scanner="nmap" args="nmap -p22 secret.example"><runstats/></nmaprun>'
    payload = parse_nmap_xml_bytes(xml, **IDS).model_dump(mode="json")
    assert "secret.example" not in str(payload)
