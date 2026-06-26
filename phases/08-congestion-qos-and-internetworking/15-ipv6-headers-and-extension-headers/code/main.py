"""IPv6 fixed header and extension header parser.

Stdlib-only reference that exercises RFC 8200 (IPv6 Specification) and
RFC 8201 (PMTUD for IPv6): the 40-byte fixed header, Hop-by-Hop, Routing
Type 0, Fragment, and the upper-layer pseudo-header. Byte order is
big-endian (network byte order for IPv6).
"""

from __future__ import annotations
import struct
from dataclasses import dataclass, field
from typing import List, Tuple

# Constants from RFC 8200 / RFC 4443.
IPV6_HEADER_LEN = 40
EXT_HEADER_UNIT = 8
FRAG_UNIT = 8
TCP_PROTO = 6
UDP_PROTO = 17
ICMPV6_PROTO = 58
NH_HOPBYHOP = 0
NH_ROUTING = 43
NH_FRAGMENT = 44
NH_DEST_OPTS = 60
NH_NO_NEXT = 59


@dataclass
class IPv6Header:
    """The 40-byte fixed IPv6 header. Addresses are 16-byte byte strings."""
    src: bytes = b"\x00" * 16
    dst: bytes = b"\x00" * 16
    traffic_class: int = 0
    flow_label: int = 0
    payload_length: int = 0
    next_header: int = TCP_PROTO
    hop_limit: int = 64

    def pack(self) -> bytes:
        if len(self.src) != 16 or len(self.dst) != 16:
            raise ValueError("IPv6 addresses must be 16 bytes each")
        if self.payload_length > 0xFFFF:
            raise ValueError("payload_length must fit in 16 bits")
        ver_tc_fl = (6 << 28) | (self.traffic_class << 20) | self.flow_label
        return struct.pack("!IHBB16s16s",
            ver_tc_fl, self.payload_length, self.next_header, self.hop_limit, self.src, self.dst)


@dataclass
class HopByHop:
    """Minimal PadN-style Hop-by-Hop, enough to show alignment and chaining."""
    pad_bytes: int = 6

    def pack(self) -> bytes:
        # NextHeader | HdrExtLen=0 | PadN(type=1, len=N-2, N zero bytes)
        n = max(0, self.pad_bytes - 2)
        return struct.pack("!BBB", NH_ROUTING, 0, 1) + struct.pack("!B", n) + b"\x00" * n


@dataclass
class RoutingType0:
    """Type 0 routing header with a list of intermediate hops (RFC 8200 4.4)."""
    addresses: List[bytes] = field(default_factory=list)

    def pack(self) -> bytes:
        if len(self.addresses) > 23:
            raise ValueError("Type 0 max 23 intermediate addresses")
        if any(len(a) != 16 for a in self.addresses):
            raise ValueError("routing addresses must be 16 bytes each")
        seg_left = len(self.addresses)
        hlen = (2 * (1 + seg_left) // EXT_HEADER_UNIT) if seg_left else 0
        # NextHeader | HdrExtLen | RoutingType=0 | SegmentsLeft | Reserved(4) | Addrs...
        header = struct.pack("!BBBB", NH_FRAGMENT, hlen, 0, seg_left) + b"\x00" * 4
        for a in self.addresses:
            header += a
        return header


@dataclass
class FragmentHeader:
    """The 8-byte IPv6 Fragment extension header (RFC 8200 4.5)."""
    next_header: int
    identification: int
    fragment_offset: int = 0
    more: bool = False

    def pack(self) -> bytes:
        m_bit = 1 if self.more else 0
        offset_more = (m_bit << 15) | (self.fragment_offset & 0x1FFF)
        return struct.pack("!BBHI", self.next_header, 0, offset_more,
                           self.identification & 0xFFFFFFFF)


@dataclass
class ExtLink:
    """A single link in the extension header chain.

    `kind` is the Next Header value of *this* extension (e.g. NH_HOPBYHOP=0);
    `next_header` is the protocol that follows it (e.g. NH_ROUTING=43).
    """
    kind: int
    next_header: int
    body: bytes


def walk_chain(fixed_header: IPv6Header, extensions: List[ExtLink]) -> Tuple[IPv6Header, List[ExtLink], int]:
    """Walk the chain left to right; return (header, seen, upper_proto).

    The fixed header's `next_header` is the kind of the first extension;
    each extension's `next_header` is the kind of the next (or a
    transport protocol like TCP=6 / UDP=17 / ICMPv6=58).
    """
    current_next = fixed_header.next_header
    seen: List[ExtLink] = []
    for link in extensions:
        if link.kind != current_next:
            raise ValueError(
                f"chain broken: expected kind={current_next}, got {link.kind}")
        seen.append(link)
        current_next = link.next_header
    return fixed_header, seen, current_next


def pseudo_header(src: bytes, dst: bytes, length: int, next_header: int) -> bytes:
    """The pseudo-header for TCP / UDP / ICMPv6 checksums in IPv6.

    Length is the upper-layer length (header + payload), not the IPv6
    header. The pseudo-header itself is 40 bytes for IPv6 (vs. 12 for IPv4).
    """
    if len(src) != 16 or len(dst) != 16:
        raise ValueError("pseudo-header addresses must be 16 bytes")
    if length > 0xFFFFFFFF:
        raise ValueError("length must fit in 32 bits")
    return struct.pack("!16s16sIIBBH", src, dst, length, length, 0, 0, next_header)


def demo_fixed_header() -> None:
    print("=== IPv6 fixed header (RFC 8200 sec. 3) ===")
    src = bytes.fromhex("20010db8000000000000000000000001")
    dst = bytes.fromhex("20010db8000000000000000000000002")
    h = IPv6Header(src=src, dst=dst, traffic_class=0xb8, flow_label=0x12345,
                   payload_length=64, next_header=NH_HOPBYHOP, hop_limit=64)
    raw = h.pack()
    print(f"packed {len(raw)}-byte header: {raw.hex()}")
    ver = raw[0] >> 4
    tc = ((raw[0] & 0xF) << 4) | (raw[1] >> 4)
    fl = ((raw[1] & 0xF) << 16) | (raw[2] << 8) | raw[3]
    print(f"version={ver}  traffic_class=0x{tc:02x}  flow_label=0x{fl:05x}")


def demo_chain_walk() -> None:
    print("\n=== Extension header chain (Hop-by-Hop -> Routing -> Fragment) ===")
    extensions = [
        ExtLink(kind=NH_HOPBYHOP, next_header=NH_ROUTING, body=HopByHop(pad_bytes=6).pack()),
        ExtLink(kind=NH_ROUTING, next_header=NH_FRAGMENT, body=RoutingType0(addresses=[b"\x20" * 16]).pack()),
        ExtLink(kind=NH_FRAGMENT, next_header=TCP_PROTO, body=FragmentHeader(next_header=TCP_PROTO,
            identification=0x1234ABCD, fragment_offset=185 // FRAG_UNIT, more=True).pack()),
    ]
    h = IPv6Header(payload_length=sum(len(e.body) for e in extensions), next_header=NH_HOPBYHOP)
    _, seen, upper = walk_chain(h, extensions)
    print(f"chain length: {len(seen)} extension header(s)")
    for i, link in enumerate(seen):
        print(f"  ext[{i}]: kind={link.kind}, next={link.next_header}, body_len={len(link.body)}")
    print(f"upper-layer protocol: {upper} (6=TCP)")


def demo_pseudo_header() -> None:
    print("\n=== Upper-layer pseudo-header (RFC 8200 sec. 8.1) ===")
    src = bytes.fromhex("20010db8000000000000000000000001")
    dst = bytes.fromhex("20010db8000000000000000000000002")
    p = pseudo_header(src, dst, length=200, next_header=TCP_PROTO)
    print(f"pseudo-header ({len(p)} bytes): {p.hex()}")


def main() -> None:
    demo_fixed_header()
    demo_chain_walk()
    demo_pseudo_header()


if __name__ == "__main__":
    main()
