#!/usr/bin/env python3
"""IPv4 fragmentation/reassembly engine and Internet-checksum verifier.

This module makes two "design issues for the layers" concrete:

  * Internetworking  -> fragment a datagram for a small next-hop MTU and
                        reassemble it, exactly as a layer-3 gateway (router)
                        must when joining links with different MTUs.
  * Reliability      -> compute and verify the 16-bit one's-complement
                        Internet checksum (RFC 1071) used by IPv4/UDP/TCP.

Relevant IPv4 header fields (RFC 791):
  Total Length (16b), Identification (16b), Flags (3b: reserved/DF/MF),
  Fragment Offset (13b, counted in 8-byte units).

Stdlib only. No network calls. Run:  python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

IPV4_HEADER_BYTES = 20
FRAGMENT_UNIT = 8  # Fragment Offset is counted in 8-byte units (RFC 791).
MASK16 = 0xFFFF


# --------------------------------------------------------------------------
# Reliability: the 16-bit one's-complement Internet checksum (RFC 1071)
# --------------------------------------------------------------------------
def internet_checksum(words: Iterable[int]) -> int:
    """Return the 16-bit Internet checksum over a sequence of 16-bit words."""
    total = 0
    for word in words:
        total += word & MASK16
        # End-around carry: fold the overflow back into the low 16 bits.
        total = (total & MASK16) + (total >> 16)
    return (~total) & MASK16


def checksum_is_valid(words: Iterable[int], checksum: int) -> bool:
    """Verify: summing every covered word plus the checksum yields 0xFFFF."""
    total = checksum & MASK16
    for word in words:
        total += word & MASK16
        total = (total & MASK16) + (total >> 16)
    return total == MASK16


# --------------------------------------------------------------------------
# Internetworking: IPv4 fragmentation and reassembly
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Fragment:
    """One IPv4 fragment carrying part of an original datagram's payload."""

    identification: int
    total_length: int  # header + this fragment's payload, in bytes
    more_fragments: bool  # MF flag
    fragment_offset: int  # in 8-byte units
    payload: bytes

    @property
    def payload_byte_offset(self) -> int:
        return self.fragment_offset * FRAGMENT_UNIT


@dataclass
class Datagram:
    """An IPv4 datagram before fragmentation."""

    identification: int
    payload: bytes
    dont_fragment: bool = False
    header_bytes: int = IPV4_HEADER_BYTES

    @property
    def total_length(self) -> int:
        return self.header_bytes + len(self.payload)


class FragmentationNeeded(Exception):
    """Raised when DF=1 but the datagram exceeds the next-hop MTU.

    Mirrors the router emitting ICMPv4 Type 3 Code 4 (Fragmentation Needed
    and DF Set), which carries the next-hop MTU back to the sender.
    """


def fragment(datagram: Datagram, mtu: int) -> list[Fragment]:
    """Split a datagram so each fragment's total length fits within `mtu`."""
    if datagram.total_length <= mtu:
        return [
            Fragment(
                identification=datagram.identification,
                total_length=datagram.total_length,
                more_fragments=False,
                fragment_offset=0,
                payload=datagram.payload,
            )
        ]

    if datagram.dont_fragment:
        raise FragmentationNeeded(
            f"datagram is {datagram.total_length} bytes but next-hop MTU is "
            f"{mtu} and DF=1; router would drop and send ICMP Type 3 Code 4"
        )

    # Payload bytes that fit per fragment, rounded DOWN to an 8-byte multiple
    # so every non-final Fragment Offset lands on a unit boundary.
    max_payload = mtu - datagram.header_bytes
    if max_payload < FRAGMENT_UNIT:
        raise ValueError(f"MTU {mtu} too small for a {datagram.header_bytes}B header")
    chunk = (max_payload // FRAGMENT_UNIT) * FRAGMENT_UNIT

    fragments: list[Fragment] = []
    payload = datagram.payload
    offset_units = 0
    for start in range(0, len(payload), chunk):
        piece = payload[start : start + chunk]
        is_last = start + chunk >= len(payload)
        fragments.append(
            Fragment(
                identification=datagram.identification,
                total_length=datagram.header_bytes + len(piece),
                more_fragments=not is_last,
                fragment_offset=offset_units,
                payload=piece,
            )
        )
        offset_units += len(piece) // FRAGMENT_UNIT
    return fragments


class ReassemblyError(Exception):
    """Raised when a fragment set cannot be reassembled (gap or missing tail)."""


def reassemble(fragments: list[Fragment], header_bytes: int = IPV4_HEADER_BYTES) -> bytes:
    """Reassemble fragments sharing one Identification back into the payload."""
    if not fragments:
        raise ReassemblyError("no fragments")
    ids = {f.identification for f in fragments}
    if len(ids) != 1:
        raise ReassemblyError(f"fragments span multiple datagrams: {sorted(ids)}")

    ordered = sorted(fragments, key=lambda f: f.fragment_offset)
    if not any(f.more_fragments is False for f in ordered):
        raise ReassemblyError("missing final fragment (no MF=0)")

    out = bytearray()
    expected_offset = 0
    for frag in ordered:
        if frag.payload_byte_offset != expected_offset:
            raise ReassemblyError(
                f"gap: expected byte offset {expected_offset}, "
                f"got {frag.payload_byte_offset}"
            )
        out.extend(frag.payload)
        expected_offset += len(frag.payload)
    return bytes(out)


# --------------------------------------------------------------------------
# Demonstration
# --------------------------------------------------------------------------
def _print_fragment_table(fragments: list[Fragment]) -> None:
    print(f"{'frag':>4} {'TotalLen':>9} {'MF':>3} {'offset(units)':>13} "
          f"{'byteOff':>8} {'payload':>8}")
    for i, f in enumerate(fragments):
        print(f"{i:>4} {f.total_length:>9} {int(f.more_fragments):>3} "
              f"{f.fragment_offset:>13} {f.payload_byte_offset:>8} "
              f"{len(f.payload):>8}")


def main() -> None:
    print("=" * 64)
    print("Internetworking: IPv4 fragmentation across a smaller-MTU link")
    print("=" * 64)
    original = Datagram(identification=0xB1A5, payload=bytes(3980))  # 4000B total
    for mtu in (1500, 576):
        frags = fragment(original, mtu=mtu)
        print(f"\nNext-hop MTU = {mtu}  ->  {len(frags)} fragment(s)")
        _print_fragment_table(frags)
        recovered = reassemble(frags)
        ok = recovered == original.payload
        print(f"reassembled {len(recovered)} bytes, matches original: {ok}")

    print("\n" + "=" * 64)
    print("DF=1 black hole: router cannot fragment, must signal the sender")
    print("=" * 64)
    pinned = Datagram(identification=0x0001, payload=bytes(2000), dont_fragment=True)
    try:
        fragment(pinned, mtu=1500)
    except FragmentationNeeded as exc:
        print(f"FragmentationNeeded -> {exc}")

    print("\n" + "=" * 64)
    print("Reliability: 16-bit Internet checksum (RFC 1071)")
    print("=" * 64)
    header_words = [0x4500, 0x003C, 0x1C46, 0x4000, 0x4006, 0xAC10, 0x0A63, 0xAC10, 0x0A0C]
    cks = internet_checksum(header_words)
    print(f"words    = {[hex(w) for w in header_words]}")
    print(f"checksum = {hex(cks)}")
    print(f"verify (clean)   -> valid={checksum_is_valid(header_words, cks)}")

    corrupted = header_words.copy()
    corrupted[3] ^= 0x0100  # flip one bit
    print(f"verify (bit-flip) -> valid={checksum_is_valid(corrupted, cks)}")


if __name__ == "__main__":
    main()
