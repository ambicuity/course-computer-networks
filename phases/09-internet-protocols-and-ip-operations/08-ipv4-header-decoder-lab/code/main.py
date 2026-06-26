#!/usr/bin/env python3
"""Full IPv4 header decoder lab (Tanenbaum section 5.6.1).

Stdlib only. Give it raw hex bytes, get a fully structured header with
every field decoded, the one's-complement header checksum validated,
the upper-layer protocol identified (TCP=6, UDP=17, ICMP=1, OSPF=89),
and the flags decoded (Reserved, DF, MF).  Designed to mirror the
exact byte layout of Fig. 5-46 in the source material.

Run:  python3 main.py
"""
from __future__ import annotations

import struct
import sys
from dataclasses import dataclass, field
from typing import Optional

PROTOCOL_MAP: dict[int, str] = {
    0: "HOPOPT",
    1: "ICMP",
    2: "IGMP",
    4: "IPv4 encapsulation",
    6: "TCP",
    8: "EGP",
    17: "UDP",
    41: "IPv6 encapsulation",
    46: "RSVP",
    47: "GRE",
    50: "ESP",
    51: "AH",
    58: "ICMPv6",
    59: "No Next Header",
    88: "EIGRP",
    89: "OSPF",
    103: "PIM",
    132: "SCTP",
    137: "MPLS-in-IP",
}

DSCP_NAMES: dict[int, str] = {
    0: "Default",
    8: "CS1",
    10: "AF11",
    12: "AF12",
    14: "AF13",
    16: "CS2",
    18: "AF21",
    46: "EF",
}


@dataclass
class DecodedHeader:
    version: int
    ihl: int
    dscp: int
    ecn: int
    total_length: int
    identification: int
    reserved_flag: bool
    df: bool
    mf: bool
    fragment_offset: int
    ttl: int
    protocol: int
    checksum: int
    src_addr: str
    dst_addr: str
    options: bytes = field(default=b"")
    payload: bytes = field(default=b"")
    checksum_valid: bool = False

    @property
    def header_length(self) -> int:
        return self.ihl * 4

    @property
    def protocol_name(self) -> str:
        return PROTOCOL_MAP.get(self.protocol, f"Unknown({self.protocol})")

    @property
    def dscp_name(self) -> str:
        return DSCP_NAMES.get(self.dscp, f"DSCP {self.dscp}")

    @property
    def flags_str(self) -> str:
        flags = []
        flags.append(f"R={int(self.reserved_flag)}")
        flags.append(f"DF={int(self.df)}")
        flags.append(f"MF={int(self.mf)}")
        return " ".join(flags)


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


def decode(raw: bytes) -> DecodedHeader:
    if len(raw) < 20:
        raise ValueError(f"Header too short: {len(raw)} bytes")
    (ver_ihl, tos, total_len, ident, flags_frag, ttl,
     proto, checksum, src, dst) = struct.unpack("!BBHHHBBHII", raw[:20])
    version = ver_ihl >> 4
    ihl = ver_ihl & 0x0F
    dscp = (tos >> 2) & 0x3F
    ecn = tos & 0x03
    reserved = bool(flags_frag & 0x8000)
    df = bool(flags_frag & 0x4000)
    mf = bool(flags_frag & 0x2000)
    frag_off = flags_frag & 0x1FFF
    header_len = ihl * 4
    options = raw[20:header_len] if header_len > 20 else b""
    payload = raw[header_len:total_len] if total_len <= len(raw) else b""
    checksum_valid = compute_checksum(raw[:header_len]) == 0
    if version != 4:
        raise ValueError(f"Version field is {version}, expected 4")
    if ihl < 5:
        raise ValueError(f"IHL={ihl} below minimum (5)")
    return DecodedHeader(
        version=version,
        ihl=ihl,
        dscp=dscp,
        ecn=ecn,
        total_length=total_len,
        identification=ident,
        reserved_flag=reserved,
        df=df,
        mf=mf,
        fragment_offset=frag_off,
        ttl=ttl,
        protocol=proto,
        checksum=checksum,
        src_addr=ip_to_str(src),
        dst_addr=ip_to_str(dst),
        options=options,
        payload=payload,
        checksum_valid=checksum_valid,
    )


def decode_from_hex(hex_str: str) -> DecodedHeader:
    cleaned = hex_str.replace(" ", "").replace("\n", "")
    raw = bytes.fromhex(cleaned)
    return decode(raw)


def format_decoded(h: DecodedHeader) -> str:
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("IPv4 HEADER DECODED")
    lines.append("=" * 60)
    lines.append(f"  Version              : {h.version}")
    lines.append(f"  IHL                  : {h.ihl}  (header = {h.header_length} bytes)")
    lines.append(f"  Differentiated Svcs  : DSCP={h.dscp} ({h.dscp_name})  ECN={h.ecn}")
    lines.append(f"  Total length         : {h.total_length} bytes")
    lines.append(f"  Identification       : 0x{h.identification:04X} ({h.identification})")
    lines.append(f"  Flags                : {h.flags_str}")
    lines.append(f"  Fragment offset      : {h.fragment_offset}  "
                 f"({h.fragment_offset * 8} bytes into datagram)")
    lines.append(f"  TTL                  : {h.ttl}")
    lines.append(f"  Protocol             : {h.protocol} ({h.protocol_name})")
    lines.append(f"  Header checksum      : 0x{h.checksum:04X}  "
                 f"valid={h.checksum_valid}")
    lines.append(f"  Source address       : {h.src_addr}")
    lines.append(f"  Destination address  : {h.dst_addr}")
    if h.options:
        lines.append(f"  Options ({len(h.options)} bytes)     : {h.options.hex(' ')}")
    if h.payload:
        lines.append(f"  Payload ({len(h.payload)} bytes)      : {h.payload.hex(' ')[:80]}")
    return "\n".join(lines)


def build_tcp_packet() -> bytes:
    ver_ihl = (4 << 4) | 5
    tos = 0
    total_len = 40
    ident = 0x1C46
    flags_frag = 0x4000
    ttl = 64
    proto = 6
    src = 0xC0A80101
    dst = 0x08080808
    hdr = struct.pack(
        "!BBHHHBBHII",
        ver_ihl, tos, total_len, ident, flags_frag,
        ttl, proto, 0, src, dst,
    )
    cksum = compute_checksum(hdr)
    hdr = hdr[:10] + struct.pack("!H", cksum) + hdr[12:]
    tcp_hdr = struct.pack("!HHLLBBHH",
                          0x0050, 0x0050, 1, 0, 0x50, 0x02,
                          0x7FFF, 0)
    return hdr + tcp_hdr


def build_icmp_packet() -> bytes:
    ver_ihl = (4 << 4) | 5
    tos = 0
    total_len = 28
    ident = 0xAB12
    flags_frag = 0x0000
    ttl = 255
    proto = 1
    src = 0xC0A8010A
    dst = 0xC0A80101
    hdr = struct.pack(
        "!BBHHHBBHII",
        ver_ihl, tos, total_len, ident, flags_frag,
        ttl, proto, 0, src, dst,
    )
    cksum = compute_checksum(hdr)
    hdr = hdr[:10] + struct.pack("!H", cksum) + hdr[12:]
    icmp = struct.pack("!BBHHH", 8, 0, 0, 0x1234, 1)
    cksum_icmp = compute_checksum(icmp)
    icmp = struct.pack("!BBHHH", 8, 0, cksum_icmp, 0x1234, 1)
    return hdr + icmp


def build_fragmented_packet() -> bytes:
    ver_ihl = (4 << 4) | 5
    tos = 0
    total_len = 1500
    ident = 0xBEEF
    flags_frag = 0x2000 | (1480 // 8)
    ttl = 50
    proto = 6
    src = 0xC0A80101
    dst = 0x08080808
    hdr = struct.pack(
        "!BBHHHBBHII",
        ver_ihl, tos, total_len, ident, flags_frag,
        ttl, proto, 0, src, dst,
    )
    cksum = compute_checksum(hdr)
    hdr = hdr[:10] + struct.pack("!H", cksum) + hdr[12:]
    return hdr + b"\x00" * 1480


def main() -> None:
    print("=" * 60)
    print("IPv4 Header Decoder Lab")
    print("=" * 60)

    print()
    print("Test 1: TCP packet (192.168.1.1 -> 8.8.8.8)")
    print("-" * 60)
    tcp = build_tcp_packet()
    print(f"Raw hex: {tcp.hex(' ')}")
    h = decode(tcp)
    print(format_decoded(h))

    print()
    print("Test 2: ICMP Echo Request (192.168.1.10 -> 192.168.1.1)")
    print("-" * 60)
    icmp = build_icmp_packet()
    print(f"Raw hex: {icmp.hex(' ')}")
    h2 = decode(icmp)
    print(format_decoded(h2))

    print()
    print("Test 3: Fragmented TCP packet (MF=1, offset=1480)")
    print("-" * 60)
    frag = build_fragmented_packet()
    h3 = decode(frag)
    print(format_decoded(h3))

    print()
    print("Test 4: Decode from a hex string (real-world capture)")
    print("-" * 60)
    hex_capture = "4500003c1c4640004006b1e6c0a8010108080808"
    print(f"Input: {hex_capture}")
    h4 = decode_from_hex(hex_capture)
    print(format_decoded(h4))

    print()
    print("Test 5: Corrupted checksum (flip one byte)")
    print("-" * 60)
    bad = bytearray(tcp)
    bad[8] ^= 0xFF
    h5 = decode(bytes(bad))
    print(format_decoded(h5))


if __name__ == "__main__":
    main()