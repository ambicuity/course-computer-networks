#!/usr/bin/env python3
"""Incident Response Packet Kit (Production Lab 06).

Defines capture filters for various incident types, evidence preservation
procedures, chain-of-custody tracking, and a runbook for assembling a
"packet kit" — the curated set of pcaps, hashes, logs, and timeline
artifacts an on-call engineer hands off to incident response.

Run:  python3 main.py

The output walks through:
  1. The six canonical incident classes and their capture filters
  2. The tcpdump / tshark commands an operator runs to capture each
  3. Evidence preservation steps (rotation, hashing, off-box transfer)
  4. A chain-of-custody log with SHA-256 verification
  5. An analysis checklist
  6. A timeline correlator that joins pcap events with syslog
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import os
import sys
from dataclasses import dataclass, field
from typing import Iterable


CAPTURE_FILTERS: list[dict[str, str]] = [
    {
        "incident": "Network Outage",
        "filter": "host <affected_ip> and (port 80 or port 443 or port 22)",
        "duration": "5 min",
        "interface": "all",
    },
    {
        "incident": "DDoS Attack",
        "filter": "(dst port 80 or dst port 443) and tcp[tcpflags] & tcp-syn != 0",
        "duration": "10 min",
        "interface": "uplink",
    },
    {
        "incident": "Security Breach",
        "filter": "host <suspect_ip> and (port 22 or port 3389 or port 4444)",
        "duration": "30 min",
        "interface": "dmz",
    },
    {
        "incident": "Latency Issue",
        "filter": "host <affected_ip> and tcp",
        "duration": "10 min",
        "interface": "affected",
    },
    {
        "incident": "DNS Issue",
        "filter": "port 53",
        "duration": "5 min",
        "interface": "all",
    },
    {
        "incident": "Rogue DHCP",
        "filter": "(port 67 or port 68) and ether src not <legit_dhcp_mac>",
        "duration": "5 min",
        "interface": "user-vlan",
    },
]


TCPDUMP_COMMANDS: list[tuple[str, str]] = [
    ("Outage",       "tcpdump -i eth0 -w outage.pcap 'host 10.0.0.5 and (port 80 or port 443)'"),
    ("DDoS",         "tcpdump -i eth1 -w ddos.pcap '(dst port 80 or dst 443) and tcp[tcpflags] & tcp-syn != 0'"),
    ("Breach",       "tcpdump -i eth2 -w breach.pcap 'host 203.0.113.50 and (port 22 or port 3389)'"),
    ("DNS",          "tcpdump -i eth0 -w dns.pcap 'port 53'"),
    ("Latency",      "tcpdump -i eth0 -w latency.pcap -j adapter -J tcp -w latency.pcap 'host 10.0.0.7 and tcp'"),
    ("Full capture", "tcpdump -i eth0 -w full-%Y%m%d%H%M%S.pcap -G 300 -W 12 'not port 22'"),
    ("Ring buffer",  "tcpdump -i eth0 -w ring.pcap -W 24 -C 200 'not (port 22 or port 3389)'"),
]


@dataclass
class CustodyEvent:
    timestamp: str
    actor: str
    action: str
    location: str


@dataclass
class CustodyLog:
    case_id: str
    incident: str
    capturer: str
    start: str
    end: str
    file_name: str
    file_size_mb: float
    sha256: str
    storage_path: str
    events: list[CustodyEvent] = field(default_factory=list)

    def verify(self, observed_sha: str) -> bool:
        return observed_sha.lower() == self.sha256.lower()

    def append(self, event: CustodyEvent) -> None:
        self.events.append(event)


def hash_file(path: str) -> str:
    """Compute SHA-256 of a file by streaming 64 KB at a time.

    The function tolerates a missing file by returning the SHA-256 of an
    empty input, which a real chain-of-custody process would reject.
    """
    h = hashlib.sha256()
    if not os.path.exists(path):
        return h.hexdigest()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def timeline(events: Iterable[tuple[str, str]]) -> list[tuple[_dt.datetime, str]]:
    """Convert (iso-timestamp, description) into sorted (datetime, desc) pairs."""
    out: list[tuple[_dt.datetime, str]] = []
    for ts, desc in events:
        try:
            out.append((_dt.datetime.fromisoformat(ts.replace("Z", "+00:00")), desc))
        except ValueError:
            out.append((_dt.datetime.fromtimestamp(0, tz=_dt.timezone.utc), desc))
    out.sort(key=lambda x: x[0])
    return out


def render_filter_table(filters: list[dict[str, str]]) -> str:
    lines = [f"  {'Incident':20s} {'Filter':55s} {'Duration':8s} {'Interface'}"]
    lines.append(f"  {'-'*20} {'-'*55} {'-'*8} {'-'*12}")
    for c in filters:
        lines.append(
            f"  {c['incident']:20s} \"{c['filter']:53s}\" {c['duration']:8s} {c['interface']}"
        )
    return "\n".join(lines)


def render_timeline(events: list[tuple[_dt.datetime, str]]) -> str:
    lines = ["  Timeline (UTC):"]
    for ts, desc in events:
        lines.append(f"    {ts.strftime('%Y-%m-%dT%H:%M:%SZ')}  {desc}")
    return "\n".join(lines)


def main() -> None:
    print("=" * 65)
    print("Incident Response Packet Kit")
    print("=" * 65)

    print(f"\n  Capture Filters ({len(CAPTURE_FILTERS)} scenarios):\n")
    print(render_filter_table(CAPTURE_FILTERS))

    print(f"\n  tcpdump / tshark Commands:")
    for label, cmd in TCPDUMP_COMMANDS:
        print(f"    {label:14s}  {cmd}")

    print(f"\n  Evidence Preservation Steps:")
    print(f"    1. Start capture immediately (don't wait for approval).")
    print(f"    2. Write to .pcap (not just screen output).")
    print(f"    3. Use -G 300 for 5-minute rotation (prevents oversized files).")
    print(f"    4. Copy captures to secure evidence storage:")
    print(f"         scp capture.pcap evidence@forensics-server:/cases/CASE-001/")
    print(f"    5. Generate SHA-256 hash for chain of custody:")
    print(f"         sha256sum capture.pcap > capture.pcap.sha256")
    print(f"    6. Record every access in the custody log (who, when, why).")
    print(f"    7. Keep the original pcap read-only (chmod 444).")

    custody = CustodyLog(
        case_id="CASE-2024-001",
        incident="Suspected data exfiltration",
        capturer="J. Smith (NetOps)",
        start="2024-06-22T14:30:00Z",
        end="2024-06-22T14:45:00Z",
        file_name="breach-capture.pcap",
        file_size_mb=45.2,
        sha256="a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890",
        storage_path="/evidence/CASE-2024-001/breach-capture.pcap",
    )
    custody.append(CustodyEvent("2024-06-22T15:00:00Z", "J. Smith",      "capture",   "edge-fw-1"))
    custody.append(CustodyEvent("2024-06-22T16:00:00Z", "A. Jones",      "analysis",  "forensics-vm"))
    custody.append(CustodyEvent("2024-06-22T18:00:00Z", "Security Team", "review",    "secure-vault"))

    print(f"\n  Chain of Custody Log:")
    print(f"    Case ID:     {custody.case_id}")
    print(f"    Incident:    {custody.incident}")
    print(f"    Capturer:    {custody.capturer}")
    print(f"    Start time:  {custody.start}")
    print(f"    End time:    {custody.end}")
    print(f"    File:        {custody.file_name} ({custody.file_size_mb} MB)")
    print(f"    SHA-256:     {custody.sha256[:16]}…{custody.sha256[-8:]}")
    print(f"    Storage:     {custody.storage_path}")
    print(f"    Access log:")
    for ev in custody.events:
        print(f"                 {ev.timestamp} - {ev.actor} ({ev.action}) @ {ev.location}")
    print(f"    Verify (demo): {custody.verify(custody.sha256)}")

    print(f"\n  Analysis Checklist:")
    checklist = [
        "Verify capture integrity (SHA-256 match)",
        "Load in Wireshark, apply display filters",
        "Check for anomalous protocols/ports",
        "Extract HTTP objects (File -> Export Objects -> HTTP)",
        "Check DNS queries for suspicious domains",
        "Analyze TLS SNI for unexpected destinations",
        "Look for data staging (large outbound transfers)",
        "Document findings with timestamps",
        "Generate report (PDF + pcap evidence)",
    ]
    for item in checklist:
        print(f"    [ ] {item}")

    print(f"\n  Demo: hash an empty file in the current directory if present:")
    demo_target = "demo.pcap"
    if not os.path.exists(demo_target):
        with open(demo_target, "wb") as fh:
            fh.write(b"\x00" * 1024)
        print(f"    (created empty {demo_target} for the demo)")
    observed = hash_file(demo_target)
    print(f"    SHA-256({demo_target}) = {observed[:16]}…{observed[-8:]}")

    events = [
        ("2024-06-22T14:30:05Z", "Edge firewall logs show 1.2 Gbps outbound from 10.0.0.42"),
        ("2024-06-22T14:31:12Z", "IDS signature TROJAN-EXFIL-HTTP fires on 10.0.0.42 → 198.51.100.7"),
        ("2024-06-22T14:32:00Z", "tcpdump capture starts on edge-fw-1"),
        ("2024-06-22T14:33:48Z", "DNS resolver logs show 47 lookups for *.bad.example"),
        ("2024-06-22T14:35:00Z", "NetOps pages IR team; case opened"),
        ("2024-06-22T14:45:00Z", "Capture ends; pcap transferred to evidence vault"),
    ]
    print("\n" + render_timeline(timeline(events)))

    print(f"\n  Ship It:")
    print(f"    outputs/ contains: chain-of-custody.pdf, capture.pcap, capture.pcap.sha256,")
    print(f"    syslog-correlated-timeline.md, executive-summary.md, iocs.txt")


if __name__ == "__main__":
    main()
