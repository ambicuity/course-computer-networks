#!/usr/bin/env python3
"""Stdlib pcap reader and TCP-flag annotator for the Packet Capture Workflow lesson.

No third-party dependencies, no network access. This program:

  1. Builds a small but *valid* classic .pcap byte stream in memory containing a
     TCP three-way-handshake attempt that fails: SYN, two retransmitted SYNs,
     then a RST. One frame is deliberately snaplen-truncated to demonstrate the
     incl_len < orig_len defect.
  2. Parses the 24-byte pcap global header, detecting endianness from the magic
     number (0xa1b2c3d4 host order vs 0xd4c3b2a1 swapped).
  3. Walks every 16-byte record header, flags truncated packets, and dissects the
     Ethernet -> IPv4 -> TCP chain to recover ports, sequence numbers, and flags.
  4. Prints a tshark-style trace and a plain-language verdict.

Run:  python3 main.py
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

PCAP_MAGIC_LE = 0xA1B2C3D4  # microsecond resolution, little-endian writer
PCAP_MAGIC_BE = 0xD4C3B2A1  # same file written big-endian (must byte-swap)
ETHERTYPE_IPV4 = 0x0800
IP_PROTO_TCP = 6
ETH_HDR_LEN = 14
IP_HDR_LEN = 20
TCP_HDR_LEN = 20

# TCP flag bit positions within the flags byte.
TCP_FLAGS: list[tuple[int, str]] = [
    (0x01, "FIN"),
    (0x02, "SYN"),
    (0x04, "RST"),
    (0x08, "PSH"),
    (0x10, "ACK"),
    (0x20, "URG"),
]


@dataclass(frozen=True)
class Packet:
    """One dissected record from the pcap file."""

    number: int
    ts: float
    incl_len: int
    orig_len: int
    src_ip: str
    dst_ip: str
    src_port: int
    dst_port: int
    seq: int
    ack: int
    flags: str

    @property
    def truncated(self) -> bool:
        return self.incl_len < self.orig_len


def decode_flags(flags_byte: int) -> str:
    """Turn a TCP flags byte into a readable label like 'SYN' or 'SYN,ACK'."""
    names = [name for bit, name in TCP_FLAGS if flags_byte & bit]
    return ",".join(names) if names else "(none)"


def _ip_to_bytes(ip: str) -> bytes:
    return bytes(int(octet) for octet in ip.split("."))


def _ip_from_bytes(raw: bytes) -> str:
    return ".".join(str(b) for b in raw)


def build_eth_ip_tcp(
    src_ip: str,
    dst_ip: str,
    src_port: int,
    dst_port: int,
    seq: int,
    ack: int,
    flags_byte: int,
) -> bytes:
    """Assemble a minimal Ethernet + IPv4 + TCP frame (no options, no payload)."""
    # Ethernet: dst MAC, src MAC, ethertype (14 bytes).
    eth = bytes.fromhex("0011223344550066778899aa") + struct.pack(">H", ETHERTYPE_IPV4)
    # TCP header (20 bytes). Data offset 5 words (<<4); checksum left 0 for the demo.
    tcp = struct.pack(
        ">HHIIBBHHH",
        src_port,
        dst_port,
        seq,
        ack,
        5 << 4,   # data offset = 5 words, reserved = 0
        flags_byte,
        65535,    # window
        0,        # checksum (not validated in this demo)
        0,        # urgent pointer
    )
    # IPv4 header (20 bytes). version 4 / IHL 5, TTL 64, protocol TCP.
    total_len = IP_HDR_LEN + len(tcp)
    ip = struct.pack(
        ">BBHHHBBH4s4s",
        0x45,     # version 4, IHL 5
        0x00,     # DSCP/ECN
        total_len,
        0x1234,   # identification
        0x4000,   # flags=DF, fragment offset 0
        64,       # TTL
        IP_PROTO_TCP,
        0,        # header checksum (not validated here)
        _ip_to_bytes(src_ip),
        _ip_to_bytes(dst_ip),
    )
    return eth + ip + tcp


def build_demo_pcap() -> bytes:
    """Return a complete little-endian .pcap byte stream for the failing handshake."""
    snaplen = 65535
    global_header = struct.pack(
        "<IHHiIII",
        PCAP_MAGIC_LE,
        2, 4,     # version major / minor
        0,        # thiszone (GMT offset)
        0,        # sigfigs
        snaplen,
        1,        # network = LINKTYPE_ETHERNET
    )

    client, server = "10.0.0.12", "10.0.0.5"
    # (ts, src, dst, sport, dport, seq, ack, flags_byte, truncate_to)
    plan = [
        (1.000000, client, server, 51514, 5432, 1000, 0, 0x02, None),  # SYN
        (2.000000, client, server, 51514, 5432, 1000, 0, 0x02, None),  # SYN retransmit
        (4.000000, client, server, 51514, 5432, 1000, 0, 0x02, 40),    # SYN, truncated
        (4.500000, server, client, 5432, 51514, 0, 1001, 0x14, None),  # RST,ACK (refused)
    ]

    body = bytearray()
    for ts, s_ip, d_ip, s_port, d_port, seq, ack, flags, trunc in plan:
        frame = build_eth_ip_tcp(s_ip, d_ip, s_port, d_port, seq, ack, flags)
        orig_len = len(frame)
        saved = frame if trunc is None else frame[:trunc]
        ts_sec = int(ts)
        ts_usec = int(round((ts - ts_sec) * 1_000_000))
        rec = struct.pack("<IIII", ts_sec, ts_usec, len(saved), orig_len)
        body += rec + saved
    return global_header + bytes(body)


def parse_global_header(data: bytes) -> tuple[str, int, int]:
    """Return (endian_prefix, snaplen, link_type); detect byte order from magic."""
    magic = struct.unpack("<I", data[:4])[0]
    if magic == PCAP_MAGIC_LE:
        endian = "<"
    elif magic == PCAP_MAGIC_BE:
        endian = ">"  # file written big-endian; swap every field
    else:
        raise ValueError(f"not a microsecond pcap file (magic={magic:#010x})")
    snaplen = struct.unpack(endian + "I", data[16:20])[0]
    link_type = struct.unpack(endian + "I", data[20:24])[0]
    return endian, snaplen, link_type


def dissect(saved: bytes) -> dict:
    """Pull L3/L4 fields out of a (possibly truncated) Ethernet frame."""
    out = {
        "src_ip": "?", "dst_ip": "?", "src_port": 0,
        "dst_port": 0, "seq": 0, "ack": 0, "flags": "(truncated)",
    }
    if len(saved) < ETH_HDR_LEN + IP_HDR_LEN + TCP_HDR_LEN:
        return out  # not enough bytes for full Eth+IP+TCP
    if struct.unpack(">H", saved[12:14])[0] != ETHERTYPE_IPV4:
        return out
    ip = saved[ETH_HDR_LEN:ETH_HDR_LEN + IP_HDR_LEN]
    out["src_ip"] = _ip_from_bytes(ip[12:16])
    out["dst_ip"] = _ip_from_bytes(ip[16:20])
    if ip[9] != IP_PROTO_TCP:
        return out
    tcp = saved[ETH_HDR_LEN + IP_HDR_LEN:ETH_HDR_LEN + IP_HDR_LEN + TCP_HDR_LEN]
    sport, dport, seq, ack = struct.unpack(">HHII", tcp[:12])
    out.update(
        src_port=sport, dst_port=dport, seq=seq, ack=ack,
        flags=decode_flags(tcp[13]),
    )
    return out


def read_pcap(data: bytes) -> list[Packet]:
    """Parse a full pcap byte stream into a list of dissected Packets."""
    endian, _snaplen, _link = parse_global_header(data)
    packets: list[Packet] = []
    offset, number = 24, 0
    while offset + 16 <= len(data):
        ts_sec, ts_usec, incl_len, orig_len = struct.unpack(
            endian + "IIII", data[offset:offset + 16]
        )
        offset += 16
        saved = data[offset:offset + incl_len]
        offset += incl_len
        number += 1
        f = dissect(saved)
        packets.append(
            Packet(
                number=number,
                ts=ts_sec + ts_usec / 1_000_000,
                incl_len=incl_len,
                orig_len=orig_len,
                flags=f["flags"],
                src_ip=f["src_ip"],
                dst_ip=f["dst_ip"],
                src_port=f["src_port"],
                dst_port=f["dst_port"],
                seq=f["seq"],
                ack=f["ack"],
            )
        )
    return packets


def print_trace(packets: list[Packet]) -> None:
    """Render a tshark-like trace table."""
    print(f"{'No.':>3}  {'Time':>7}  {'Source':<13} -> {'Dest':<13} "
          f"{'Sport':>5} {'Dport':>5} {'Flags':<8} {'Seq':>5}  Note")
    print("-" * 84)
    base = packets[0].ts if packets else 0.0
    for p in packets:
        note = "TRUNCATED (incl<orig)" if p.truncated else ""
        print(f"{p.number:>3}  {p.ts - base:>7.3f}  {p.src_ip:<13} -> "
              f"{p.dst_ip:<13} {p.src_port:>5} {p.dst_port:>5} "
              f"{p.flags:<8} {p.seq:>5}  {note}")


def diagnose(packets: list[Packet]) -> str:
    """Apply workflow step 4: turn the trace into a one-line verdict."""
    syns = [p for p in packets if p.flags == "SYN"]
    rsts = [p for p in packets if "RST" in p.flags]
    truncs = [p for p in packets if p.truncated]
    lines: list[str] = []
    if len(syns) >= 2 and all(s.seq == syns[0].seq for s in syns):
        deltas = [round(syns[i + 1].ts - syns[i].ts, 1) for i in range(len(syns) - 1)]
        lines.append(
            f"SYN to port {syns[0].dst_port} retransmitted {len(syns)} times "
            f"(same seq {syns[0].seq}); inter-arrival {deltas}s -> RTO backoff."
        )
    if rsts:
        port = syns[0].dst_port if syns else "?"
        lines.append(
            f"Server sent {rsts[0].flags} -> connection refused "
            f"(nothing listening on {port})."
        )
    if truncs:
        nums = ", ".join(str(p.number) for p in truncs)
        lines.append(
            f"Packet(s) {nums} truncated: incl_len < orig_len -> snaplen too small."
        )
    return "\n".join(f"  - {ln}" for ln in lines) if lines else "  - clean trace."


def main() -> None:
    print("=== Packet Capture Workflow: stdlib pcap reader ===\n")
    raw = build_demo_pcap()
    endian, snaplen, link_type = parse_global_header(raw)
    order = "little-endian (host)" if endian == "<" else "big-endian (swapped)"
    print(f"Global header: magic OK, byte order = {order}, "
          f"snaplen = {snaplen}, link type = {link_type} (1=Ethernet)\n")

    packets = read_pcap(raw)
    print_trace(packets)
    print("\nVerdict (workflow step 4):")
    print(diagnose(packets))
    print("\nShip it: export these frames, annotate the SYN/RST/truncation, "
          "write the one-line conclusion.")


if __name__ == "__main__":
    main()
