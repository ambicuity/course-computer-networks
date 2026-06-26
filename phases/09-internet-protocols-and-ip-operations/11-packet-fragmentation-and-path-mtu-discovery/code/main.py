"""Packet Fragmentation and Path MTU Discovery.

A stdlib-only Python reference implementation that exercises the ideas behind
RFC 791 (IPv4 fragmentation fields), RFC 1191 (IPv4 PMTUD), and RFC 8201 /
RFC 8200 (IPv6 PMTUD and Fragment extension header).

Run as a script to see two demos:
    1. Splitting a 4000-byte payload into MTU-sized IPv4 fragments.
    2. A Path MTU Discovery walk over a 3-hop topology.

Nothing here is meant to ship; the code exists to make the protocol math in
the lesson tangible. Every value lives on the wire, so byte order is big-endian
(the standard network byte order for IP).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

# --- constants --------------------------------------------------------------

IPV4_HEADER_MIN = 20           # RFC 791: minimum header with no options
FRAG_UNIT = 8                  # Fragment offsets are measured in 8-byte units
IDENT_MAX = 0xFFFF             # 16-bit Identification field
ICMP_FRAG_NEEDED = (3, 4)      # RFC 792: Type 3, Code 4 (Fragmentation Needed)
ICMPV6_PKT_TOO_BIG = 2         # RFC 4443: Type 2 Packet Too Big


# --- IPv4 header (fragmentation-focused) ------------------------------------

@dataclass
class IPv4Header:
    """A minimal IPv4 header. Only the fields the lesson touches are
    first-class; everything else is defaulted."""

    total_length: int
    identification: int
    flags: int = 0          # bit 0 reserved, bit 1 DF, bit 2 MF
    fragment_offset: int = 0
    ttl: int = 64
    protocol: int = 6       # TCP, just to keep things concrete
    src: int = 0x0A000001   # 10.0.0.1
    dst: int = 0x0A000002   # 10.0.0.2

    def pack(self) -> bytes:
        version_ihl = (4 << 4) | 5      # IPv4, 5 * 4 = 20 bytes of header
        flags_offset = (self.flags << 13) | self.fragment_offset
        return struct.pack(
            "!BBHHHBBHII",
            version_ihl, 0, self.total_length, self.identification,
            flags_offset, self.ttl, self.protocol, 0,  # checksum elided
            self.src, self.dst,
        )


@dataclass
class Fragment:
    """One IPv4 fragment: header + payload slice."""
    header: IPv4Header
    payload: bytes


def fragment_datagram(
    payload: bytes, mtu: int, identification: int
) -> list[Fragment]:
    """Split ``payload`` into MTU-sized IPv4 fragments.

    ``mtu`` is the maximum on-the-wire size of one fragment
    (header + data), which is the convention Path MTU Discovery uses.
    """
    if mtu < IPV4_HEADER_MIN + FRAG_UNIT:
        raise ValueError("mtu too small for at least one fragment")
    max_data = mtu - IPV4_HEADER_MIN
    max_data_aligned = (max_data // FRAG_UNIT) * FRAG_UNIT
    if max_data_aligned == 0:
        raise ValueError("mtu too small to hold an 8-byte aligned payload")

    fragments: list[Fragment] = []
    offset = 0
    remaining = payload
    while remaining:
        take = min(max_data_aligned, len(remaining))
        slice_ = remaining[:take]
        remaining = remaining[take:]
        more = bool(remaining)
        hdr = IPv4Header(
            total_length=IPV4_HEADER_MIN + len(slice_),
            identification=identification & IDENT_MAX,
            flags=0x2 if more else 0x0,            # 0x2 == MF bit
            fragment_offset=offset // FRAG_UNIT,
        )
        fragments.append(Fragment(hdr, slice_))
        offset += len(slice_)
    return fragments


def reassemble(fragments: list[Fragment]) -> bytes:
    """Rebuild the original payload from a set of IPv4 fragments.

    Fragments may arrive out of order; we trust the Identification field,
    the Fragment offset, and the absence of the MF bit.
    """
    if not fragments:
        return b""
    ident = fragments[0].header.identification
    for f in fragments:
        if f.header.identification != ident:
            raise ValueError("identification mismatch during reassembly")
    last = next(f for f in fragments if (f.header.flags & 0x2) == 0)
    end_units = last.header.fragment_offset + (
        (last.header.total_length - IPV4_HEADER_MIN) // FRAG_UNIT
    )
    out = bytearray(end_units * FRAG_UNIT)
    for f in fragments:
        start = f.header.fragment_offset * FRAG_UNIT
        out[start:start + len(f.payload)] = f.payload
    return bytes(out)


# --- IPv6 Fragment extension header (RFC 8200 section 4.5) -----------------

@dataclass
class IPv6FragmentHeader:
    """The 8-byte Fragment extension header used when an IPv6 source does
    the splitting itself."""
    next_header: int
    identification: int
    fragment_offset: int = 0
    more: bool = False  # M flag

    def pack(self) -> bytes:
        m_bit = 1 if self.more else 0
        offset_more = (m_bit << 15) | (self.fragment_offset & 0x1FFF)
        # NextHeader (8) | Reserved (8) | Offset/Res/M (16) | Ident (32)
        return struct.pack(
            "!BBHI", self.next_header, 0, offset_more,
            self.identification & 0xFFFFFFFF,
        )


# --- Path MTU Discovery walk ------------------------------------------------

@dataclass
class Link:
    """One hop on the path with its MTU."""
    name: str
    mtu: int


@dataclass
class PMTUDState:
    estimate: int
    history: list[str] = field(default_factory=list)


def probe_path(
    path: list[Link], payload_size: int, start_estimate: int,
) -> PMTUDState:
    """Walk the path, lowering the estimate each time a router reports the
    packet is too big. This is the textbook PMTUD loop (RFC 1191):
    set DF, send, wait for ICMP, shrink, repeat.
    """
    state = PMTUDState(estimate=min(start_estimate, payload_size))
    state.history.append(f"start: payload={payload_size} bytes, estimate={state.estimate}")
    while True:
        for link in path:
            if state.estimate <= link.mtu:
                state.history.append(f"send {state.estimate} bytes via {link.name} (mtu={link.mtu}): ok")
                return state
            icmp = ICMP_FRAG_NEEDED if link.name.startswith("R") else ICMPV6_PKT_TOO_BIG
            state.history.append(f"send {state.estimate} bytes via {link.name} (mtu={link.mtu}): TOO BIG")
            state.estimate = link.mtu
            state.history.append(f"<- ICMP {icmp[0]}/{icmp[1]} next-hop mtu={link.mtu}, new estimate={state.estimate}")
            break  # re-probe from the source


# --- demos ------------------------------------------------------------------

def demo_fragmentation() -> None:
    print("=== IPv4 fragmentation demo (RFC 791) ===")
    payload = (bytes(range(256)) * 16)[:4000]
    frags = fragment_datagram(payload, mtu=1500, identification=0xBEEF)
    print(f"split {len(payload)} byte payload into {len(frags)} fragments (mtu=1500, ident=0xBEEF)")
    for i, f in enumerate(frags):
        mf = "MF" if f.header.flags & 0x2 else "last"
        print(f"  frag[{i}] off={f.header.fragment_offset * FRAG_UNIT:>4}  "
              f"len={f.header.total_length - IPV4_HEADER_MIN:>4}  flags={mf}")
    rebuilt = reassemble(frags)
    print(f"reassembled: {len(rebuilt)} bytes, {'OK' if rebuilt == payload else 'MISMATCH'}")


def demo_pmtud() -> None:
    print("\n=== Path MTU Discovery demo (RFC 1191 / RFC 8201) ===")
    path = [Link("R1 (ethernet)", 1500), Link("R2 (pppoe)", 1492), Link("R3 (tunnel)", 1476)]
    state = probe_path(path=path, payload_size=4000, start_estimate=4000)
    for line in state.history:
        print("  " + line)
    print(f"final path MTU estimate = {state.estimate} bytes")


def demo_ipv6_fragment_header() -> None:
    print("\n=== IPv6 Fragment extension header (RFC 8200) ===")
    fh = IPv6FragmentHeader(next_header=6, identification=0x1234ABCD,
                            fragment_offset=185 // FRAG_UNIT, more=True)
    print(f"packed header ({len(fh.pack())} bytes): {fh.pack().hex()}")


def main() -> None:
    demo_fragmentation()
    demo_pmtud()
    demo_ipv6_fragment_header()


if __name__ == "__main__":
    main()