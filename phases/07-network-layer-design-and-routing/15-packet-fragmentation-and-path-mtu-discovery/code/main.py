#!/usr/bin/env python3
"""IPv4 Packet Fragmentation and Path MTU Discovery (RFC 791, RFC 1191).

Demonstrates the core mechanisms described in the lesson:

  1. fragment_packet  - Split an IP datagram into fragments for a given link MTU,
                        producing the Identification, Fragment Offset (8-byte units),
                        MF bit, and Total Length for each fragment.
  2. reassemble       - Validate and reconstruct the original payload from an
                        (possibly out-of-order) list of fragments.
  3. simulate_pmtud   - Step through a Path MTU Discovery exchange (RFC 1191):
                        source sends DF=1 packets, routers return ICMP "frag needed",
                        source learns and caches the path MTU, retransmits smaller.

Stdlib only.  Run: python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Every IPv4 header is exactly 20 bytes (without options).
IPV4_HEADER_LEN = 20


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Fragment:
    """One IPv4 fragment as it would appear on the wire."""
    identification: int      # 16-bit shared ID for all pieces of one datagram
    offset_bytes: int        # byte offset of this fragment in the original payload
    offset_field: int        # value stored in the IPv4 header (offset_bytes // 8)
    data_len: int            # number of payload bytes carried by this fragment
    mf: int                  # More Fragments flag: 1 for all but the last fragment
    total_len: int           # IPv4 Total Length field (header + data_len)

    def __str__(self) -> str:
        flags = f"MF={self.mf} DF=0"
        return (
            f"  ID={self.identification:#06x}  "
            f"offset={self.offset_bytes:5d} B  "
            f"(field={self.offset_field:4d})  "
            f"data={self.data_len:4d} B  "
            f"{flags}  "
            f"total_len={self.total_len}"
        )


# ---------------------------------------------------------------------------
# Step 1 – Fragmentation
# ---------------------------------------------------------------------------

def fragment_packet(
    identification: int,
    total_data: int,
    path_mtu: int,
) -> List[Fragment]:
    """Fragment an IPv4 datagram with `total_data` bytes of payload.

    Parameters
    ----------
    identification:
        The 16-bit ID shared by all fragments of this datagram.
    total_data:
        Original payload size in bytes (not counting the IP header).
    path_mtu:
        MTU of the outgoing link in bytes (includes the IP header).

    Returns a list of Fragment objects in send order.

    Fragment offset alignment rule (RFC 791):
        Every fragment's data block must be a multiple of 8 bytes,
        except the last fragment which carries the remainder.
    """
    max_data_per_frag = path_mtu - IPV4_HEADER_LEN
    if max_data_per_frag <= 0:
        raise ValueError(f"MTU {path_mtu} is too small for a 20-byte IP header")

    # Round down to nearest 8-byte boundary (alignment requirement)
    max_data_per_frag = (max_data_per_frag // 8) * 8
    if max_data_per_frag == 0:
        raise ValueError(f"MTU {path_mtu} leaves no room for payload after alignment")

    fragments: List[Fragment] = []
    offset = 0
    remaining = total_data

    while remaining > 0:
        chunk = min(max_data_per_frag, remaining)
        is_last = (remaining <= max_data_per_frag)
        mf = 0 if is_last else 1
        fragments.append(Fragment(
            identification=identification,
            offset_bytes=offset,
            offset_field=offset // 8,
            data_len=chunk,
            mf=mf,
            total_len=IPV4_HEADER_LEN + chunk,
        ))
        offset += chunk
        remaining -= chunk

    return fragments


# ---------------------------------------------------------------------------
# Step 2 – Reassembly
# ---------------------------------------------------------------------------

def reassemble(fragments: List[Fragment]) -> int:
    """Reassemble and validate a list of fragments.

    Checks:
      - No gaps between consecutive fragments.
      - Exactly one fragment with MF=0 (the last one).
      - All other fragments have MF=1.

    Returns the total number of reassembled payload bytes.
    Raises AssertionError if any check fails.
    """
    if not fragments:
        raise ValueError("No fragments to reassemble")

    sorted_frags = sorted(fragments, key=lambda f: f.offset_bytes)
    expected_offset = 0
    total_bytes = 0

    for i, frag in enumerate(sorted_frags):
        is_last = (i == len(sorted_frags) - 1)
        assert frag.offset_bytes == expected_offset, (
            f"Gap in reassembly: expected offset {expected_offset} B, "
            f"got {frag.offset_bytes} B"
        )
        assert (frag.mf == 0) == is_last, (
            f"MF bit wrong at offset {frag.offset_bytes}: "
            f"mf={frag.mf} but is_last={is_last}"
        )
        expected_offset += frag.data_len
        total_bytes += frag.data_len

    return total_bytes


# ---------------------------------------------------------------------------
# Re-fragmentation helper
# ---------------------------------------------------------------------------

def refragment(frags: List[Fragment], new_mtu: int) -> List[Fragment]:
    """Re-fragment already-fragmented pieces that exceed `new_mtu`.

    The original Identification value is preserved (RFC 791).
    Fragment Offset values are computed relative to the original datagram.
    """
    result: List[Fragment] = []
    for frag in frags:
        if frag.total_len <= new_mtu:
            result.append(frag)
        else:
            # Fragment this piece further; offsets are relative to original
            sub_frags = fragment_packet(frag.identification, frag.data_len, new_mtu)
            for sf in sub_frags:
                sf.offset_bytes += frag.offset_bytes
                sf.offset_field = sf.offset_bytes // 8
                # MF must reflect the global picture: set unless this sub-fragment
                # is the last piece of the last original fragment.
                if frag.mf == 1:
                    sf.mf = 1   # more original fragments remain after this one
            result.extend(sub_frags)
    return result


# ---------------------------------------------------------------------------
# Step 3 – Path MTU Discovery simulation (RFC 1191)
# ---------------------------------------------------------------------------

@dataclass
class PmtudResult:
    """Outcome of a PMTU discovery exchange."""
    path_mtu: int
    rounds: int
    log: List[str] = field(default_factory=list)


def simulate_pmtud(original_size: int, hop_mtus: List[int]) -> PmtudResult:
    """Simulate RFC 1191 Path MTU Discovery.

    The source sends a packet of `original_size` bytes with DF=1.
    Each entry in `hop_mtus` is the outgoing MTU at one router hop.
    When the packet is larger than a hop's MTU the router drops it and
    returns ICMP Type 3 Code 4 ("fragmentation needed") with the hop MTU.
    The source learns the ceiling, reduces its packet, and retransmits.

    Returns PmtudResult with the discovered path MTU and a trace log.
    """
    log: List[str] = []
    current_size = original_size
    rounds = 0

    log.append(f"Source sends {current_size}-byte packet (DF=1)")

    for hop_index, mtu in enumerate(hop_mtus, start=1):
        if current_size > mtu:
            log.append(
                f"  Hop {hop_index}: MTU={mtu}, packet ({current_size} B) too large — "
                f"DF=1 → drop + ICMP 'frag needed, next-hop MTU={mtu}'"
            )
            current_size = mtu
            rounds += 1
            log.append(f"  Source learns MTU={mtu}, retransmits {current_size}-byte packet")
        else:
            log.append(f"  Hop {hop_index}: MTU={mtu}, packet fits ({current_size} B <= {mtu})")

    log.append(f"Path MTU discovered: {current_size} bytes after {rounds} ICMP round-trip(s)")
    return PmtudResult(path_mtu=current_size, rounds=rounds, log=log)


# ---------------------------------------------------------------------------
# Exercise: offset arithmetic from the lesson
# ---------------------------------------------------------------------------

def exercise_offset_arithmetic() -> None:
    """Lesson Exercise 1: 3000-byte payload, MTU=1000."""
    print("=== Exercise: 3000-byte payload, MTU=1000 ===")
    frags = fragment_packet(identification=0x0042, total_data=3000, path_mtu=1000)
    print(f"  Number of fragments: {len(frags)}")
    for f in frags:
        print(f)
    recovered = reassemble(frags)
    print(f"  Reassembled: {recovered} bytes  (expected 3000)\n")


# ---------------------------------------------------------------------------
# Main demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    sep = "=" * 64

    # ------------------------------------------------------------------
    # Demo 1 – Fragmentation from the lesson's worked example
    # ------------------------------------------------------------------
    print(sep)
    print("DEMO 1 — Fragment a 1400-byte payload over MTU=620")
    print(sep)
    frags1 = fragment_packet(identification=0xABCD, total_data=1400, path_mtu=620)
    print(f"  Original datagram: 20-byte header + 1400-byte payload = 1420 bytes")
    print(f"  Max data per fragment: {620 - IPV4_HEADER_LEN} B → aligned to "
          f"{((620 - IPV4_HEADER_LEN) // 8) * 8} B")
    print(f"  Fragments produced: {len(frags1)}")
    for f in frags1:
        print(f)
    recovered1 = reassemble(frags1)
    print(f"  Reassembled: {recovered1} bytes (original 1400 bytes) ✓\n")

    # ------------------------------------------------------------------
    # Demo 2 – Reassembly from out-of-order fragments
    # ------------------------------------------------------------------
    print(sep)
    print("DEMO 2 — Reassembly from out-of-order arrival")
    print(sep)
    shuffled = list(reversed(frags1))   # deliver last fragment first
    recovered2 = reassemble(shuffled)
    print(f"  Fragments delivered in reverse order — reassembled: {recovered2} bytes ✓\n")

    # ------------------------------------------------------------------
    # Demo 3 – Re-fragmentation
    # ------------------------------------------------------------------
    print(sep)
    print("DEMO 3 — Re-fragmentation (MTU=800 then MTU=500)")
    print(sep)
    frags_800 = fragment_packet(identification=0x1234, total_data=1400, path_mtu=800)
    print(f"  After MTU=800: {len(frags_800)} fragment(s)")
    for f in frags_800:
        print(f)

    frags_500 = refragment(frags_800, new_mtu=500)
    print(f"\n  After re-fragmentation at MTU=500: {len(frags_500)} fragment(s)")
    for f in frags_500:
        print(f)
    recovered3 = reassemble(frags_500)
    print(f"  Reassembled: {recovered3} bytes (original 1400 bytes) ✓\n")

    # ------------------------------------------------------------------
    # Demo 4 – Path MTU Discovery
    # ------------------------------------------------------------------
    print(sep)
    print("DEMO 4 — Path MTU Discovery (RFC 1191)")
    print(sep)
    result = simulate_pmtud(
        original_size=1400,
        hop_mtus=[1500, 1200, 900, 900],
    )
    for line in result.log:
        print(f"  {line}")
    print()

    # ------------------------------------------------------------------
    # Demo 5 – Lesson's scenario: campus → WAN → tunnel
    # ------------------------------------------------------------------
    print(sep)
    print("DEMO 5 — Lesson Scenario: 8 KB datagram, path MTUs [1500, 4470, 1280]")
    print(sep)
    result2 = simulate_pmtud(
        original_size=8192,
        hop_mtus=[1500, 4470, 1280],
    )
    for line in result2.log:
        print(f"  {line}")
    print(f"\n  Without PMTUD, mid-path fragmentation at MTU=1280 would")
    print(f"  produce {len(fragment_packet(0x9999, 8192 - 20, 1280))} fragments per 8 KB datagram.")
    print(f"  Loss of any one fragment requires retransmitting all 8192 bytes.\n")

    # ------------------------------------------------------------------
    # Lesson exercise
    # ------------------------------------------------------------------
    exercise_offset_arithmetic()


if __name__ == "__main__":
    main()
