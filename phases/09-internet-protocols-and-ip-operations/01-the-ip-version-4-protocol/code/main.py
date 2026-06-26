#!/usr/bin/env python3
"""IPv4 header parser and checksum validator (Tanenbaum section 5.6.1).

Stdlib only. Demonstrates parsing a raw 20-byte IPv4 header into a
structured dataclass, validating the one's-complement header checksum
described in the text, and pretty-printing every field exactly as it
appears in Fig. 5-46 of the source material.

Run:  python3 main.py
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

PROTOCOL_MAP: dict[int, str] = {
    1: "ICMP",
    2: "IGMP",
    6: "TCP",
    17: "UDP",
    41: "IPv6 encapsulation",
    47: "GRE",
    89: "OSPF",
    132: "SCTP",
}


@dataclass
class IPv4Header:
    version: int
    ihl: int
    dscp: int
    ecn: int
    total_length: int
    identification: int
    flags: int
    df: bool
    mf: bool
    fragment_offset: int
    ttl: int
    protocol: int
    checksum: int
    src_addr: str
    dst_addr: str
    options: bytes = field(default=b"")
    payload_length: int = 0

    @property
    def header_length(self) -> int:
        return self.ihl * 4

    @property
    def protocol_name(self) -> str:
        return PROTOCOL_MAP.get(self.protocol, f"Unknown({self.protocol})")

    def checksum_ok(self, raw: bytes) -> bool:
        return compute_checksum(raw) == 0


def ip_to_str(ip_int: int) -> str:
    return ".".join(str((ip_int >> shift) & 0xFF) for shift in (24, 16, 8, 0))


def compute_checksum(data: bytes) -> int:
    if len(data) % 2 == 1:
        data = data + b"\x00"
    total = 0
    for i in range(0, len(data), 2):
        word = (data[i] << 8) | data[i + 1]
        total += word
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def parse_ipv4_header(raw: bytes) -> IPv4Header:
    if len(raw) < 20:
        raise ValueError(f"Header too short: {len(raw)} bytes (minimum 20)")
    (ver_ihl, tos, total_len, ident, flags_frag, ttl,
     proto, checksum, src, dst) = struct.unpack("!BBHHHBBHII", raw[:20])
    version = ver_ihl >> 4
    ihl = ver_ihl & 0x0F
    dscp = (tos >> 2) & 0x3F
    ecn = tos & 0x03
    df = bool(flags_frag & 0x4000)
    mf = bool(flags_frag & 0x2000)
    flags = (flags_frag >> 13) & 0x07
    frag_off = flags_frag & 0x1FFF
    header_len = ihl * 4
    options = raw[20:header_len] if header_len > 20 else b""
    payload_length = total_len - header_len if total_len >= header_len else 0
    if version != 4:
        raise ValueError(f"Version field is {version}, expected 4")
    if ihl < 5:
        raise ValueError(f"IHL={ihl} is below minimum (5)")
    return IPv4Header(
        version=version,
        ihl=ihl,
        dscp=dscp,
        ecn=ecn,
        total_length=total_len,
        identification=ident,
        flags=flags,
        df=df,
        mf=mf,
        fragment_offset=frag_off,
        ttl=ttl,
        protocol=proto,
        checksum=checksum,
        src_addr=ip_to_str(src),
        dst_addr=ip_to_str(dst),
        options=options,
        payload_length=payload_length,
    )


def format_header(h: IPv4Header, raw: bytes) -> str:
    lines = [
        f"  Version              : {h.version}",
        f"  IHL                  : {h.ihl}  (header = {h.header_length} bytes)",
        f"  Differentiated Svcs  : 0x{(h.dscp << 2 | h.ecn):02X}  "
        f"(DSCP={h.dscp}, ECN={h.ecn})",
        f"  Total length         : {h.total_length} bytes",
        f"  Identification       : 0x{h.identification:04X} ({h.identification})",
        f"  Flags                : 0x{h.flags:X}  DF={int(h.df)}  MF={int(h.mf)}",
        f"  Fragment offset      : {h.fragment_offset}  "
        f"({h.fragment_offset * 8} bytes)",
        f"  TTL                  : {h.ttl}",
        f"  Protocol             : {h.protocol} ({h.protocol_name})",
        f"  Header checksum      : 0x{h.checksum:04X}",
        f"  Source address        : {h.src_addr}",
        f"  Destination address  : {h.dst_addr}",
    ]
    if h.options:
        lines.append(f"  Options              : {h.options.hex(' ')}")
    valid = h.checksum_ok(raw[:h.header_length])
    lines.append(f"  Checksum valid       : {valid}")
    lines.append(f"  Payload length       : {h.payload_length} bytes")
    return "\n".join(lines)


def build_sample_header() -> bytes:
    ver_ihl = (4 << 4) | 5
    tos = 0
    total_len = 20 + 8
    ident = 0x1234
    flags_frag = 0x4000
    ttl = 64
    proto = 17
    src = 0xC0A80101
    dst = 0xC0A80102
    hdr = struct.pack(
        "!BBHHHBBHII",
        ver_ihl, tos, total_len, ident, flags_frag,
        ttl, proto, 0, src, dst,
    )
    cksum = compute_checksum(hdr)
    return hdr[:10] + struct.pack("!H", cksum) + hdr[12:]


def main() -> None:
    print("=" * 64)
    print("IPv4 Header Parser  --  Tanenbaum 5.6.1")
    print("=" * 64)
    raw = build_sample_header()
    print(f"Raw bytes ({len(raw)}): {raw.hex(' ')}")
    print()
    h = parse_ipv4_header(raw)
    print("Parsed header:")
    print(format_header(h, raw))

    print()
    print("=" * 64)
    print("Fragmented packet (MF=1, offset=1480)")
    print("=" * 64)
    ver_ihl = (4 << 4) | 5
    flags_frag = 0x2000 | (1480 // 8)
    frag_raw = struct.pack(
        "!BBHHHBBHII",
        ver_ihl, 0, 1500, 0xABCD, flags_frag,
        63, 6, 0, 0xC0A8010A, 0x08080808,
    )
    cksum = compute_checksum(frag_raw)
    frag_raw = frag_raw[:10] + struct.pack("!H", cksum) + frag_raw[12:]
    fh = parse_ipv4_header(frag_raw)
    print(format_header(fh, frag_raw))

    print()
    print("=" * 64)
    print("Corrupted header  --  checksum should FAIL")
    print("=" * 64)
    bad = bytearray(raw)
    bad[8] ^= 0xFF
    bh = parse_ipv4_header(bytes(bad))
    print(format_header(bh, bytes(bad)))


if __name__ == "__main__":
    main()