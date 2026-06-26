"""
nmap Scan Taxonomy and Host/Port Discovery Mechanics — runnable model.

Pure stdlib. No network calls, no pip deps. This program models the
*mechanics* an nmap scan relies on: how the TCP/IP stack reacts to
hand-crafted flags, how a port's state is inferred from those reactions,
how host discovery separates "alive" from "filtered", and how timing
templates trade stealth for speed.

It is a teaching simulator: it models a target host's port table and
the kernel's RFC 793 state machine responses, then exercises them with
the same flag combinations nmap uses (SYN, NULL, FIN, Xmas, ACK, UDP,
connect). The point is to make the packet/field/state reasoning visible
in printed output rather than hidden inside a C scanner.
"""

from __future__ import annotations

import ipaddress
import struct
from dataclasses import dataclass, field
from enum import IntFlag
from typing import Callable

# ---------------------------------------------------------------------------
# TCP flags (RFC 793 control bits, offset 10..15 in the 16-bit flags word).
# nmap's whole scan taxonomy is a menu over these bits.
# ---------------------------------------------------------------------------


class TCPFlag(IntFlag):
    FIN = 0x01
    SYN = 0x02
    RST = 0x04
    PSH = 0x08
    ACK = 0x10
    URG = 0x20

    def label(self) -> str:
        names = []
        if self & TCPFlag.FIN:
            names.append("FIN")
        if self & TCPFlag.SYN:
            names.append("SYN")
        if self & TCPFlag.RST:
            names.append("RST")
        if self & TCPFlag.PSH:
            names.append("PSH")
        if self & TCPFlag.ACK:
            names.append("ACK")
        if self & TCPFlag.URG:
            names.append("URG")
        return "|".join(names) if names else "(no flags)"


# nmap timing templates T0..T5 expressed as per-probe delay seconds. Real
# nmap tunes many more knobs (RTT smoothing, max retries, host timeout);
# we keep the serial round-trip estimate that drives the pacing loop.
TIMING_TEMPLATES: dict[str, float] = {
    "T0": 5.0,   # paranoid: slow, serial, IDS-friendly
    "T1": 1.5,   # sneaky
    "T2": 0.4,   # polite
    "T3": 0.1,   # default
    "T4": 0.01,  # aggressive
    "T5": 0.0,   # insane: skip retries, assume fast LAN
}


# ---------------------------------------------------------------------------
# Port model: each port carries a state and a firewall verdict.
# ---------------------------------------------------------------------------


@dataclass
class Port:
    number: int
    state: str  # "open", "closed", "open|filtered"
    app: str = ""
    # firewall verdict per probe class:
    # "allow" = reply per RFC 793, "drop" = silent, "reject" = ICMP
    fw_tcp_syn: str = "allow"
    fw_tcp_ack: str = "allow"
    fw_udp: str = "allow"

    def respond_syn(self) -> tuple[str, TCPFlag]:
        """RFC 793: open -> SYN|ACK; closed -> RST|ACK."""
        if self.fw_tcp_syn == "drop":
            return ("no-response", TCPFlag(0))
        if self.fw_tcp_syn == "reject":
            return ("icmp-port-unreachable", TCPFlag(0))
        if self.state == "open":
            return ("packet", TCPFlag.SYN | TCPFlag.ACK)
        return ("packet", TCPFlag.RST | TCPFlag.ACK)

    def respond_ack(self) -> tuple[str, TCPFlag]:
        """ACK to a non-established connection: open & closed both RST;
        a dropped ACK yields no-response, the open|filtered signal."""
        if self.fw_tcp_ack == "drop":
            return ("no-response", TCPFlag(0))
        return ("packet", TCPFlag.RST)

    def respond_stealth(self) -> tuple[str, TCPFlag]:
        """NULL/FIN/Xmas to a non-listening port. RFC 793 says a closed
        port MUST RST; an open port with no matching listener drops it."""
        if self.fw_tcp_syn == "drop":
            return ("no-response", TCPFlag(0))
        if self.state == "open":
            return ("no-response", TCPFlag(0))
        return ("packet", TCPFlag.RST | TCPFlag.ACK)


@dataclass
class Host:
    addr: str
    alive: bool = True
    ports: dict[int, Port] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Probe definitions: each ties a flag combination to the inference rule
# that maps the kernel response onto an nmap port state.
# ---------------------------------------------------------------------------


@dataclass
class Probe:
    name: str
    flags: TCPFlag
    proto: str  # "tcp" or "udp"
    infer: Callable[[str, TCPFlag], str]

    def describe(self) -> str:
        return f"{self.name:14s} {self.proto:3s} flags={self.flags.label()}"


def _syn_infer(resp: str, flags: TCPFlag) -> str:
    if resp in ("no-response", "icmp-port-unreachable"):
        return "filtered"
    if flags & TCPFlag.SYN and flags & TCPFlag.ACK:
        return "open"
    if flags & TCPFlag.RST:
        return "closed"
    return "filtered"


def _fin_infer(resp: str, flags: TCPFlag) -> str:
    # RFC 793: unexpected FIN to a closed port SHOULD RST, but many stacks
    # drop it. So silence is ambiguous -> open|filtered.
    if resp == "no-response":
        return "open|filtered"
    if flags & TCPFlag.RST:
        return "closed"
    return "open|filtered"


def _ack_infer(resp: str, flags: TCPFlag) -> str:
    if resp == "no-response":
        return "filtered"
    # RST on ACK only tells us the port is unfiltered; state unknown.
    return "unfiltered"


def _udp_infer(resp: str, flags: TCPFlag) -> str:
    if resp == "no-response":
        return "open|filtered"
    if resp == "icmp-port-unreachable":
        return "closed"
    if resp == "packet":
        return "open"
    return "open|filtered"


PROBES: dict[str, Probe] = {
    "sS": Probe("SYN scan", TCPFlag.SYN, "tcp", _syn_infer),
    "sT": Probe("connect()", TCPFlag.SYN, "tcp", _syn_infer),
    "sF": Probe("FIN scan", TCPFlag.FIN, "tcp", _fin_infer),
    "sN": Probe("NULL scan", TCPFlag(0), "tcp", _fin_infer),
    "sX": Probe("Xmas scan", TCPFlag.FIN | TCPFlag.PSH | TCPFlag.URG, "tcp", _fin_infer),
    "sA": Probe("ACK scan", TCPFlag.ACK, "tcp", _ack_infer),
    "sU": Probe("UDP scan", TCPFlag(0), "udp", _udp_infer),
}


# ---------------------------------------------------------------------------
# TCP/IPv4 pseudo-header checksum (RFC 793, RFC 1071). nmap and every
# hand-rolled scanner must compute this to forge valid probes.
# ---------------------------------------------------------------------------


def ones_complement_sum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    s = 0
    for i in range(0, len(data), 2):
        s += (data[i] << 8) | data[i + 1]
        s = (s & 0xFFFF) + (s >> 16)
    return s


def tcp_checksum(src: str, dst: str, tcp_header: bytes) -> int:
    """RFC 793 checksum: pseudo-header + TCP header, one's complement."""
    src_b = ipaddress.IPv4Address(src).packed
    dst_b = ipaddress.IPv4Address(dst).packed
    proto = 6
    seg_len = len(tcp_header)
    pseudo = src_b + dst_b + struct.pack(">BBH", 0, proto, seg_len)
    total = ones_complement_sum(pseudo + tcp_header)
    return (~total) & 0xFFFF


def build_tcp_segment(src: str, dst: str, sport: int, dport: int,
                      flags: TCPFlag, seq: int = 0, ack: int = 0) -> bytes:
    """Minimal 20-byte TCP header (RFC 793) with a correct checksum."""
    doff = 5  # 5 * 4 = 20 bytes, no options
    off_flags = (doff << 12) | int(flags)
    hdr = struct.pack(
        ">HHIIHHHBBH",
        sport, dport, seq, ack,
        off_flags, 8192, 0, 64, 0, 0,
    )
    csum = tcp_checksum(src, dst, hdr)
    hdr = hdr[:16] + struct.pack(">H", csum) + hdr[18:]
    return hdr


# ---------------------------------------------------------------------------
# The scanner.
# ---------------------------------------------------------------------------


def scan_port(host: Host, probe: Probe, port: Port) -> str:
    if probe.proto == "tcp":
        if probe.name in ("SYN scan", "connect()"):
            resp, flags = port.respond_syn()
        elif probe.name == "ACK scan":
            resp, flags = port.respond_ack()
        else:  # NULL / FIN / Xmas
            resp, flags = port.respond_stealth()
    else:  # udp
        if port.fw_udp == "drop":
            resp, flags = ("no-response", TCPFlag(0))
        elif port.state == "open" and port.app:
            resp, flags = ("packet", TCPFlag(0))  # app responds
        elif port.state == "closed":
            resp, flags = ("icmp-port-unreachable", TCPFlag(0))
        else:
            resp, flags = ("no-response", TCPFlag(0))
    return probe.infer(resp, flags)


def run_scan(host: Host, scan_type: str, timing: str = "T3") -> dict[int, str]:
    probe = PROBES[scan_type]
    delay = TIMING_TEMPLATES[timing]
    results: dict[int, str] = {}
    for pnum, port in sorted(host.ports.items()):
        state = scan_port(host, probe, port)
        results[pnum] = state
    _ = delay  # would pace probes by `delay` seconds in a real loop
    return results


def host_discovery(host: Host) -> str:
    if host.alive:
        return "Host is up"
    return "Host seems down (no response to ICMP echo / ARP / TCP 443 / TCP 80)"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def _sample_host() -> Host:
    h = Host(addr="203.0.113.10")
    h.ports = {
        22: Port(22, "open", "ssh"),
        80: Port(80, "open", "http"),
        443: Port(443, "closed"),
        3306: Port(3306, "open", "mysql", fw_tcp_syn="drop"),
        53: Port(53, "open", "dns", fw_udp="allow"),
        137: Port(137, "closed", "", fw_udp="allow"),
        8080: Port(8080, "closed", "", fw_tcp_syn="drop"),
    }
    return h


def main() -> None:
    host = _sample_host()

    print("=" * 72)
    print("nmap scan taxonomy -- target", host.addr)
    print("=" * 72)
    print(host_discovery(host))
    print()

    for st in ["sS", "sT", "sF", "sN", "sX", "sA", "sU"]:
        probe = PROBES[st]
        print(f"--- {probe.describe()}")
        results = run_scan(host, st)
        for pnum, state in results.items():
            app = host.ports[pnum].app or "-"
            print(f"    {pnum:>5}/{probe.proto} {state:16s} {app}")
        print()

    # Forge a SYN probe and verify its checksum is populated.
    seg = build_tcp_segment("198.51.100.5", host.addr, 54321, 22,
                            TCPFlag.SYN, seq=0x12345678)
    csum = struct.unpack(">H", seg[16:18])[0]
    print(f"Forged SYN segment to :22 -> 20 bytes, checksum=0x{csum:04x}")
    print("  bytes:", seg.hex())
    print("  inferred (SYN scan on port 22):", run_scan(host, "sS")[22])
    print()

    print("Timing template effect (total probe air time, 7 ports, serial):")
    for tname, delay in TIMING_TEMPLATES.items():
        total = len(host.ports) * delay
        print(f"  {tname}: per-probe {delay:>5.2f}s -> ~{total:6.2f}s serial")

    print()
    print("Lesson: same target, different flag menus -> different state")
    print("vocabularies. SYN gives open/closed/filtered; FIN/NULL/Xmas give")
    print("open|filtered; ACK gives only unfiltered; UDP adds ICMP-dependent")
    print("closed. The scanner never 'sees' a port -- it infers it from the")
    print("RFC 793 / RFC 768 response (or silence) the kernel returns.")


if __name__ == "__main__":
    main()