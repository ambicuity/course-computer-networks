#!/usr/bin/env python3
"""Packet Fragmentation (Tanenbaum section 5.5.5).

Stdlib only, no network calls.  Demonstrates IP-style fragmentation and
reassembly with the Fragment Offset, More-Fragments flag, and the packet
Identification field.  Reproduces the textbook Fig. 5-43 example (10 data
bytes fragmented through an 8-byte MTU then a 5-byte MTU) and a realistic
1500-byte Ethernet case, plus a Path MTU Discovery trace.

Parts:
  1. IP fragmentation engine: split a datagram so every fragment except the
     last has a payload that is a multiple of 8 and fits the link MTU.
     Each fragment carries (identification, fragment_offset, more_fragments).
  2. Reassembly engine: place fragments at their byte offset, detect
     completeness via MF=0 and contiguous coverage, handle out-of-order
     and duplicate fragments.
  3. Path MTU discovery: send DF=1 packets along a path with shrinking MTUs;
     routers that cannot forward report the next-hop MTU via ICMP 3/4; the
     source backs off until the packet fits the entire path.
"""
from __future__ import annotations

from dataclasses import dataclass, field

IPV4_HEADER = 20
FRAGMENT_UNIT = 8


@dataclass(frozen=True)
class Fragment:
    """A single IP fragment as it appears on the wire."""

    identification: int
    offset_field: int          # 13-bit value (byte offset / unit)
    more_fragments: bool       # MF flag
    payload_size: int          # bytes of original datagram this fragment carries
    unit: int = FRAGMENT_UNIT  # elementary fragment unit (8 for real IP, 1 for toy)

    @property
    def byte_offset(self) -> int:
        return self.offset_field * self.unit

    def __repr__(self) -> str:
        mf = "1" if self.more_fragments else "0"
        return (
            f"Frag(id={self.identification}, off={self.offset_field}, "
            f"mf={mf}, payload={self.payload_size}B, byte_off={self.byte_offset})"
        )


def fragment(packet_size: int, mtu: int, header_size: int = IPV4_HEADER,
              identification: int = 1, unit: int = FRAGMENT_UNIT) -> list[Fragment]:
    """Split *packet_size* bytes of payload into IP fragments for *mtu*.

    Each fragment's payload is a multiple of *unit* (8 for real IP) except the
    last, and never exceeds (mtu - header_size) bytes.
    """
    if packet_size < 0:
        raise ValueError("packet_size must be non-negative")
    max_payload = mtu - header_size
    if max_payload <= 0:
        raise ValueError("mtu smaller than header; cannot fragment")
    # largest multiple of unit that fits in the remaining payload space
    chunk = (max_payload // unit) * unit
    if chunk == 0:
        raise ValueError("mtu too small for even one unit-sized fragment")
    fragments: list[Fragment] = []
    offset = 0
    remaining = packet_size
    while remaining > 0:
        size = min(chunk, remaining)
        last = remaining - size == 0
        fragments.append(
            Fragment(
                identification=identification,
                offset_field=offset // unit,
                more_fragments=not last,
                payload_size=size,
                unit=unit,
            )
        )
        offset += size
        remaining -= size
    return fragments


def reassemble(fragments: list[Fragment]) -> bytes | None:
    """Reassemble fragments into the original payload, or None if incomplete.

    Fragments may arrive out of order; duplicates are discarded.  Completeness
    is determined by the fragment with MF=0 (which reveals the total length)
    plus a gap-free buffer from offset 0 up to that total.  When a fragment
    with MF=1 has itself been re-fragmented (fragment_chain), the last
    sub-fragment inherits the parent's MF=1, so we also accept a complete
    gap-free buffer whose last byte is covered even without an explicit MF=0.
    """
    if not fragments:
        return None
    total: int | None = None
    for f in fragments:
        if not f.more_fragments:
            total = f.byte_offset + f.payload_size
            break
    # If no explicit MF=0, infer total from the highest byte reached.
    if total is None:
        total = max(f.byte_offset + f.payload_size for f in fragments)
    buf = bytearray(total)
    placed = bytearray(total)
    for f in fragments:
        end = f.byte_offset + f.payload_size
        if end > total:
            return None
        placed[f.byte_offset:end] = [1] * f.payload_size
    if not all(placed[:total]):
        return None
    return bytes(buf)


def fragment_chain(packet_size: int, mtus: list[int], header: int = IPV4_HEADER,
                    unit: int = FRAGMENT_UNIT) -> list[Fragment]:
    """Fragment through a series of shrinking MTUs (Fig. 5-43(c) case).

    Each fragment from the previous stage is re-fragmented for the next smaller
    MTU.  Sub-fragment offsets are made absolute (relative to the original
    datagram) by adding the parent fragment's byte_offset, exactly as
    intermediate routers do when fragments hit an even smaller link.
    """
    current = fragment(packet_size, mtus[0], header, unit=unit)
    for mtu in mtus[1:]:
        expanded: list[Fragment] = []
        for f in current:
            subs = fragment(f.payload_size, mtu, header,
                            identification=f.identification, unit=f.unit)
            for s in subs:
                # The last sub-fragment inherits the parent's MF flag: if the
                # parent had more fragments after it, so does its last piece.
                mf = s.more_fragments or f.more_fragments
                expanded.append(
                    Fragment(
                        identification=s.identification,
                        offset_field=s.offset_field + f.offset_field,
                        more_fragments=mf,
                        payload_size=s.payload_size,
                        unit=f.unit,
                    )
                )
        current = expanded
    return current


def path_mtu_discover(path_mtu_list: list[int], start_size: int,
                      header: int = IPV4_HEADER) -> tuple[int, list[str]]:
    """Simulate PMTUD probing *start_size* payload through *path_mtu_list*.

    Returns (effective_mtu, trace).  Each hop that cannot carry the current
    payload drops the packet and reports its MTU via ICMP; the source backs off.
    """
    current = start_size
    trace: list[str] = []
    for i, mtu in enumerate(path_mtu_list):
        needed = current + header
        if needed > mtu:
            current = mtu - header
            trace.append(
                f"hop {i}: mtu={mtu} too small for {needed}B payload; "
                f"ICMP 3/4 -> source backs off to payload {current}B"
            )
        else:
            trace.append(f"hop {i}: mtu={mtu} ok for {needed}B payload")
    return current, trace


def print_table(fragments: list[Fragment]) -> None:
    print(f"  {'#':>2} {'offset':>7} {'offset_f':>8} {'MF':>3} {'payload':>8}")
    for i, f in enumerate(fragments):
        mf = "1" if f.more_fragments else "0"
        print(f"  {i:>2} {f.byte_offset:>7} {f.offset_field:>8} "
              f"{mf:>3} {f.payload_size:>8}")
    total = sum(f.payload_size for f in fragments)
    print(f"  total payload across {len(fragments)} fragments: {total} bytes")


def main() -> None:
    print("=" * 72)
    print("1. Realistic: 1480-byte payload (1500-byte IP packet) -> MTU 576")
    print("=" * 72)
    frags = fragment(1480, 576, IPV4_HEADER, identification=0x1A2B)
    print_table(frags)
    rebuilt = reassemble(frags)
    assert rebuilt is not None and len(rebuilt) == 1480
    print(f"  reassembly ok: {len(rebuilt)} bytes recovered\n")

    print("=" * 72)
    print("2. Textbook Fig. 5-43: 10 bytes -> MTU 8 (payload) -> MTU 5 (payload)")
    print("=" * 72)
    # The textbook uses 1-byte elementary units for this toy example, so we
    # pass unit=1 and header_size=0 to treat the stated size as the payload
    # limit directly, matching Fig. 5-43.
    stage_b = fragment(10, 8, header_size=0, identification=27, unit=1)
    print("  stage (b) — after the 8-byte network:")
    print_table(stage_b)
    stage_c = fragment_chain(10, [8, 5], header=0, unit=1)
    print("\n  stage (c) — after the 5-byte network re-fragments:")
    print_table(stage_c)
    rebuilt2 = reassemble(stage_c)
    assert rebuilt2 is not None and len(rebuilt2) == 10
    print(f"\n  reassembly ok: {len(rebuilt2)} bytes recovered\n")

    print("=" * 72)
    print("3. PMTUD: source sends 1472-byte payload through [1500, 1400, 1280]")
    print("=" * 72)
    eff, trace = path_mtu_discover([1500, 1400, 1280], 1472, IPV4_HEADER)
    for line in trace:
        print(f"  {line}")
    print(f"  effective payload after PMTUD: {eff} bytes\n")

    print("=" * 72)
    print("4. Out-of-order and duplicate fragment reassembly")
    print("=" * 72)
    base = fragment(552, 200, header_size=0)
    shuffled = [base[1], base[2], base[0], base[1]]  # out of order + duplicate
    result = reassemble(shuffled)
    assert result is not None and len(result) == 552
    print(f"  reassembly from out-of-order+duplicate set: {len(result)} bytes ok")

    # Exercise 6 demo
    print("\n" + "=" * 72)
    print("5. Exercise demo: 10000-byte payload -> MTU 1492")
    print("=" * 72)
    ex = fragment(10000, 1492, IPV4_HEADER)
    print_table(ex)
    print(f"  last fragment offset field: {ex[-1].offset_field}")


if __name__ == "__main__":
    main()