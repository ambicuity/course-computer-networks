#!/usr/bin/env python3
"""Layered-bisection diagnostic engine + RFC-accurate header parser.

This module turns the lesson's method into runnable tools:

1. parse_ipv4_header / parse_tcp_header read fields at the exact byte
   offsets defined by RFC 791 (IPv4) and RFC 793 (TCP).
2. ipv4_checksum implements the RFC 1071 one's-complement internet checksum
   so you can verify a captured header against the wire.
3. classify_tcp_state maps an observed TCP state to the RFC 793 named
   transition and the most likely fault.
4. diagnose walks a symptom through the OSI/TCP-IP layers, top-down or
   bottom-up, stopping at the first falsified MUST.

Stdlib only. No network calls. Run: python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable


# --- Layer model (OSI <-> TCP/IP) ------------------------------------------

@dataclass(frozen=True)
class Layer:
    """One layer of the model. Each layer owns a distinct kind of evidence,
    which is the search space the bisection halves on each test."""
    osi: int
    name: str
    owns: str          # what kind of evidence lives here
    tool: str          # the cheapest command that collects it


LAYERS: tuple[Layer, ...] = (
    Layer(1, "Physical", "carrier, link state, error counters", "ip link / ethtool -S"),
    Layer(2, "Data Link", "MAC, ARP cache, frame, VLAN (RFC 826)", "ip neigh"),
    Layer(3, "Network", "IP reachability, TTL, MTU, ICMP (RFC 791/1191)", "ping / traceroute"),
    Layer(4, "Transport", "ports, SYN/ACK/RST/FIN, seq/ack (RFC 793)", "ss -tan / tcpdump"),
    Layer(7, "Application", "HTTP status, DNS RRs, TLS alerts", "curl -v / dig"),
)


# --- IPv4 header parsing (RFC 791) -----------------------------------------

@dataclass
class IPv4Header:
    version: int
    ihl_words: int          # header length in 32-bit words
    total_length: int
    ttl: int
    protocol: int
    checksum: int
    src: str
    dst: str

    @property
    def header_len_bytes(self) -> int:
        return self.ihl_words * 4


def _ip_to_str(b: bytes) -> str:
    return ".".join(str(x) for x in b)


def parse_ipv4_header(data: bytes) -> IPv4Header:
    """Parse the fixed 20-byte IPv4 header per RFC 791 field offsets."""
    if len(data) < 20:
        raise ValueError("IPv4 header needs at least 20 bytes")
    version = data[0] >> 4                          # high nibble of byte 0
    ihl_words = data[0] & 0x0F                       # low nibble = length in words
    total_length = int.from_bytes(data[2:4], "big")
    ttl = data[8]                                    # byte offset 8
    protocol = data[9]                               # offset 9: 6=TCP, 17=UDP, 1=ICMP
    checksum = int.from_bytes(data[10:12], "big")    # offset 10, 16 bits
    src = _ip_to_str(data[12:16])
    dst = _ip_to_str(data[16:20])
    return IPv4Header(version, ihl_words, total_length, ttl, protocol, checksum, src, dst)


def ipv4_checksum(header: bytes) -> int:
    """RFC 1071 one's-complement internet checksum over a 20-byte IPv4 header.

    The checksum field (bytes 10-11) is treated as zero during computation.
    """
    work = bytearray(header)
    if len(work) % 2 != 0:
        work.append(0)
    work[10] = 0                                     # zero the checksum field
    work[11] = 0
    total = 0
    for i in range(0, len(work), 2):
        total += (work[i] << 8) | work[i + 1]
    while total >> 16:                               # fold carries back in
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


# --- TCP header parsing (RFC 793) ------------------------------------------

TCP_FLAGS: tuple[str, ...] = ("FIN", "SYN", "RST", "PSH", "ACK", "URG")


@dataclass
class TCPHeader:
    src_port: int
    dst_port: int
    seq: int
    ack: int
    data_offset_words: int
    flags: list[str] = field(default_factory=list)
    window: int = 0


def parse_tcp_header(data: bytes) -> TCPHeader:
    """Parse the fixed 20-byte TCP header per RFC 793 field offsets."""
    if len(data) < 20:
        raise ValueError("TCP header needs at least 20 bytes")
    src_port = int.from_bytes(data[0:2], "big")
    dst_port = int.from_bytes(data[2:4], "big")
    seq = int.from_bytes(data[4:8], "big")           # 32-bit sequence number
    ack = int.from_bytes(data[8:12], "big")          # 32-bit acknowledgement
    data_offset_words = data[12] >> 4                # high nibble of byte 12
    flag_byte = data[13]
    flags = [name for bit, name in enumerate(TCP_FLAGS) if flag_byte & (1 << bit)]
    window = int.from_bytes(data[14:16], "big")
    return TCPHeader(src_port, dst_port, seq, ack, data_offset_words, flags, window)


# --- TCP state classification (RFC 793 state machine) ----------------------

TCP_STATE_FAULTS: dict[str, str] = {
    "SYN-SENT": "SYN sent, no SYN/ACK back: Layer 3 no route, or firewall silently dropping.",
    "SYN-RECEIVED": "Got SYN, sent SYN/ACK, awaiting final ACK: possible SYN-flood or lost ACK.",
    "ESTABLISHED": "Connection open. If app hangs with rising retransmits, suspect PMTUD black hole.",
    "FIN-WAIT-2": "Our FIN was ACKed but peer never sent its FIN: peer app not closing; tcp_fin_timeout reaps it.",
    "TIME-WAIT": "Normal close; held 2*MSL (4 min) to absorb stray segments before port reuse.",
    "CLOSE-WAIT": "Peer sent FIN, our app hasn't called close(): file-descriptor leak in our code.",
}


def classify_tcp_state(state: str) -> str:
    return TCP_STATE_FAULTS.get(state, f"Unknown/handshake-complete state: {state}")


# --- Layered bisection engine ----------------------------------------------

@dataclass
class Check:
    """One falsifiable test tied to a layer and an RFC requirement."""
    layer_osi: int
    rfc: str
    must: str               # the normative requirement
    evidence_cmd: str       # how to collect the proof
    passed: Callable[[], bool]


def _layer_name(osi: int) -> str:
    for layer in LAYERS:
        if layer.osi == osi:
            return f"L{layer.osi} {layer.name}"
    return f"L{osi}"


def diagnose(symptom: str, checks: list[Check], bottom_up: bool = True) -> str:
    """Run a layered bisection, stopping at the first falsified MUST."""
    ordered = sorted(checks, key=lambda c: c.layer_osi, reverse=not bottom_up)
    direction = "bottom-up" if bottom_up else "top-down"
    lines = [f"Symptom: {symptom}", f"Strategy: {direction} bisection", "-" * 64]
    for c in ordered:
        ok = c.passed()
        verdict = "PASS" if ok else "FALSIFIED -> fault localized here"
        lines.append(f"[{_layer_name(c.layer_osi):<16}] {c.rfc}: {verdict}")
        lines.append(f"     MUST: {c.must}")
        lines.append(f"     test: {c.evidence_cmd}")
        if not ok:
            lines.append("-" * 64)
            lines.append(f"DIAGNOSIS: fault owned by {_layer_name(c.layer_osi)} ({c.rfc}).")
            return "\n".join(lines)
    lines.append("All checks passed; symptom not explained by these layers.")
    return "\n".join(lines)


# --- Demonstration ----------------------------------------------------------

def _sample_ipv4_header() -> bytes:
    """A real-shaped IPv4 header: version 4, IHL 5, TTL 64, proto 6 (TCP),
    src 192.168.1.10 -> dst 93.184.216.34, with a correct RFC 1071 checksum."""
    base = bytes([
        0x45, 0x00, 0x00, 0x3C,   # ver/ihl, dscp/ecn, total length=60
        0x1C, 0x46, 0x40, 0x00,   # id, flags(DF)/frag offset
        0x40, 0x06, 0x00, 0x00,   # ttl=64, proto=6(TCP), checksum placeholder
        0xC0, 0xA8, 0x01, 0x0A,   # src 192.168.1.10
        0x5D, 0xB8, 0xD8, 0x22,   # dst 93.184.216.34
    ])
    cksum = ipv4_checksum(base)
    return base[:10] + cksum.to_bytes(2, "big") + base[12:]


def _sample_tcp_syn() -> bytes:
    return bytes([
        0xD4, 0x31, 0x01, 0xBB,   # src port 54321 -> dst port 443
        0x00, 0x00, 0x30, 0x39,   # seq = 12345 (32-bit ISN)
        0x00, 0x00, 0x00, 0x00,   # ack = 0 (none yet on a SYN)
        0x50, 0x02, 0xFF, 0xFF,   # data offset 5 words, flags=SYN, window=65535
        0x00, 0x00, 0x00, 0x00,   # checksum, urgent pointer (complete 20-byte header)
    ])


def main() -> None:
    print("=" * 64)
    print("RFC-driven layered debugging demo")
    print("=" * 64)

    ip_bytes = _sample_ipv4_header()
    ip = parse_ipv4_header(ip_bytes)
    print("\n[1] IPv4 header parsed at RFC 791 offsets:")
    print(f"    version={ip.version}  IHL={ip.ihl_words} words "
          f"({ip.header_len_bytes} bytes)  TTL={ip.ttl}  proto={ip.protocol}")
    print(f"    {ip.src} -> {ip.dst}  total_length={ip.total_length}")
    recomputed = ipv4_checksum(ip_bytes)
    status = "OK (RFC 1071)" if recomputed == ip.checksum else "CORRUPT"
    print(f"    wire checksum=0x{ip.checksum:04X}  recomputed=0x{recomputed:04X}  -> {status}")

    tcp = parse_tcp_header(_sample_tcp_syn())
    print("\n[2] TCP header parsed at RFC 793 offsets:")
    print(f"    {tcp.src_port} -> {tcp.dst_port}  seq={tcp.seq} (32-bit ISN)  "
          f"ack={tcp.ack}  flags={'|'.join(tcp.flags)}  win={tcp.window}")

    print("\n[3] TCP state classification (RFC 793 state machine):")
    for state in ("SYN-SENT", "ESTABLISHED", "FIN-WAIT-2", "CLOSE-WAIT"):
        print(f"    {state:<13}: {classify_tcp_state(state)}")

    print("\n[4] Bisection for the PMTUD black-hole scenario:")
    print("    'large HTTPS responses hang over VPN, small ones work'\n")
    checks = [
        Check(1, "IEEE 802.3", "link MUST show carrier",
              "ip link show", lambda: True),
        Check(2, "RFC 826", "gateway MAC MUST resolve",
              "ip neigh", lambda: True),
        Check(3, "RFC 1191", "router MUST send ICMP Type 3 Code 4 and host MUST act",
              "tcpdump 'icmp[icmptype]==3 and icmp[icmpcode]==4'", lambda: False),
        Check(4, "RFC 793", "handshake MUST complete",
              "ss -tan | grep ESTAB", lambda: True),
        Check(7, "RFC 7231", "server MUST return a status",
              "curl -v https://host/", lambda: True),
    ]
    print(diagnose("large HTTPS responses hang over VPN", checks, bottom_up=True))
    print("\nFix: clamp TCP MSS (e.g. iptables TCPMSS --clamp-mss-to-pmtu),")
    print("which edits the TCP MSS option so segments fit the tunnel MTU.")


if __name__ == "__main__":
    main()
