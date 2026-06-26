#!/usr/bin/env python3
"""Passband transmission and multiplexing toolkit (stdlib only).

This module turns the physical-layer ideas of chapter 2.5.2-2.5.4 into
runnable, inspectable models:

  1. QAM/PSK constellation builder with Gray coding, so you can see how many
     bits ride on each symbol and confirm the "adjacent symbols differ in 1 bit"
     property that limits a single symbol slip to a single bit error.
  2. A symbol-rate / bit-rate calculator (Nyquist-style) that ties symbols per
     second to bits per second for a chosen modulation order.
  3. An FDM band planner that stacks voice-grade channels (3100 Hz usable,
     4000 Hz allocated, 900 Hz guard band) and reports spectrum usage.
  4. A TDM byte-interleaving multiplexer/demultiplexer that runs N tributary
     streams round-robin into one aggregate running at the sum rate, plus the
     statistical (STDM) contrast.

Everything is integer/float math on the standard library. No sockets, no pip.
Run:  python3 main.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# --- Constants drawn straight from the source section -----------------------
VOICE_USABLE_HZ = 3100          # filter-limited usable voice bandwidth
VOICE_ALLOCATED_HZ = 4000       # spectrum reserved per channel when multiplexed
GUARD_BAND_HZ = VOICE_ALLOCATED_HZ - VOICE_USABLE_HZ  # 900 Hz guard


# =========================================================================
# 1. Modulation: constellation + Gray coding
# =========================================================================
def gray_encode(value: int) -> int:
    """Return the Gray code of an integer (n XOR n>>1)."""
    return value ^ (value >> 1)


def bits_per_symbol(order: int) -> int:
    """Bits carried by one symbol of an `order`-point constellation."""
    if order <= 1 or (order & (order - 1)) != 0:
        raise ValueError(f"constellation order {order} must be a power of two > 1")
    return order.bit_length() - 1


@dataclass(frozen=True)
class ConstellationPoint:
    index: int        # natural symbol index 0..order-1
    gray: int         # Gray-coded label
    i: float          # in-phase amplitude
    q: float          # quadrature amplitude


def build_qam(order: int) -> list[ConstellationPoint]:
    """Build a square QAM constellation (e.g. QAM-16, QAM-64) with Gray labels.

    Square QAM needs order to be an even power of two. PSK (QPSK = QAM-4 here)
    falls out as the 2x2 case.
    """
    bits = bits_per_symbol(order)
    if bits % 2 != 0:
        raise ValueError(f"square QAM needs an even bit count; {order} gives {bits}")
    side = int(math.isqrt(order))           # points per axis
    levels = [2 * k - (side - 1) for k in range(side)]  # symmetric, e.g. -3,-1,1,3
    points: list[ConstellationPoint] = []
    for row in range(side):
        for col in range(side):
            idx = row * side + col
            # Gray-code each axis independently so neighbours differ by one bit
            gray_label = (gray_encode(row) << (bits // 2)) | gray_encode(col)
            points.append(
                ConstellationPoint(idx, gray_label, float(levels[col]), float(levels[row]))
            )
    return points


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def verify_gray_adjacency(points: list[ConstellationPoint]) -> bool:
    """Confirm every horizontal/vertical neighbour differs in exactly 1 bit."""
    side = int(math.isqrt(len(points)))
    grid = {(int(p.i), int(p.q)): p.gray for p in points}
    for (i, q), label in grid.items():
        for di, dq in ((2, 0), (0, 2)):  # adjacent points sit 2 amplitude units apart
            neigh = grid.get((i + di, q + dq))
            if neigh is not None and hamming_distance(label, neigh) != 1:
                return False
    return True


# =========================================================================
# 2. Symbol rate <-> bit rate
# =========================================================================
def bit_rate(symbol_rate_baud: float, order: int) -> float:
    """Bits/s = symbols/s * bits/symbol."""
    return symbol_rate_baud * bits_per_symbol(order)


# =========================================================================
# 3. FDM band planner
# =========================================================================
@dataclass(frozen=True)
class FdmChannel:
    name: str
    start_hz: float
    usable_hz: float

    @property
    def stop_hz(self) -> float:
        return self.start_hz + self.usable_hz


def plan_fdm(channel_names: list[str], base_hz: float = 60_000.0) -> list[FdmChannel]:
    """Stack voice channels each into its own 4 kHz slot above `base_hz`."""
    plan: list[FdmChannel] = []
    cursor = base_hz
    for name in channel_names:
        plan.append(FdmChannel(name, cursor, VOICE_USABLE_HZ))
        cursor += VOICE_ALLOCATED_HZ  # advance by usable + guard band
    return plan


# =========================================================================
# 4. TDM round-robin multiplexer
# =========================================================================
def tdm_multiplex(streams: list[list[int]]) -> list[tuple[int, int]]:
    """Interleave tributary streams round-robin into one aggregate.

    Returns a list of (stream_id, byte) in transmission order. The aggregate
    runs at the sum rate; each tributary owns a fixed, repeating time slot.
    """
    if not streams:
        return []
    rounds = max(len(s) for s in streams)
    aggregate: list[tuple[int, int]] = []
    for r in range(rounds):
        for sid, stream in enumerate(streams):
            if r < len(stream):
                aggregate.append((sid, stream[r]))
            else:
                aggregate.append((sid, 0x00))  # idle slot keeps the frame aligned
    return aggregate


def tdm_demultiplex(aggregate: list[tuple[int, int]], n_streams: int) -> list[list[int]]:
    """Reverse the multiplex by demuxing on the slot's stream id."""
    out: list[list[int]] = [[] for _ in range(n_streams)]
    for sid, byte in aggregate:
        out[sid].append(byte)
    return out


# =========================================================================
# Demonstration
# =========================================================================
def main() -> None:
    print("=" * 66)
    print("PASSBAND MODULATION + MULTIPLEXING TOOLKIT")
    print("=" * 66)

    # --- Modulation ------------------------------------------------------
    for order in (4, 16, 64):
        name = "QPSK" if order == 4 else f"QAM-{order}"
        pts = build_qam(order)
        ok = verify_gray_adjacency(pts)
        print(f"\n[{name}] order={order}  bits/symbol={bits_per_symbol(order)}  "
              f"Gray-adjacency-1bit={ok}")
        if order == 16:
            print("  sample of Gray-coded QAM-16 (index -> label : I,Q):")
            for p in pts[:4]:
                print(f"    {p.index:2d} -> {p.gray:04b} : ({p.i:+.0f},{p.q:+.0f})")

    # Worked rate example: a 1 Msymbol/s carrier across modulation orders
    print("\n[Bit rate] symbol rate fixed at 1,000,000 baud:")
    for order in (2, 4, 16, 64, 256):
        try:
            br = bit_rate(1_000_000, order)
            print(f"    order={order:3d}  {bits_per_symbol(order)} bits/sym "
                  f"-> {br/1e6:.0f} Mb/s")
        except ValueError as exc:
            print(f"    order={order}: {exc}")

    # --- FDM -------------------------------------------------------------
    print("\n[FDM] three voice-grade channels stacked from 60 kHz:")
    plan = plan_fdm(["Ch-1", "Ch-2", "Ch-3"])
    for ch in plan:
        print(f"    {ch.name}: usable {ch.start_hz/1e3:.1f}-{ch.stop_hz/1e3:.1f} kHz "
              f"(guard {GUARD_BAND_HZ} Hz to next)")
    span = plan[-1].start_hz + VOICE_ALLOCATED_HZ - plan[0].start_hz
    used = len(plan) * VOICE_USABLE_HZ
    print(f"    total span {span/1e3:.0f} kHz, usable {used/1e3:.1f} kHz, "
          f"efficiency {100*used/span:.1f}%")

    # --- TDM -------------------------------------------------------------
    print("\n[TDM] round-robin multiplex of three byte streams:")
    streams = [
        [0x41, 0x42, 0x43],        # 'A','B','C'
        [0x61, 0x62],              # 'a','b'   (shorter -> idle slot padded)
        [0x31, 0x32, 0x33],        # '1','2','3'
    ]
    agg = tdm_multiplex(streams)
    print("    aggregate frame (slot:byte):",
          " ".join(f"S{sid}:{b:02X}" for sid, b in agg))
    recovered = tdm_demultiplex(agg, len(streams))
    print(f"    demux matches original (ignoring idle pad): "
          f"{recovered[0] == streams[0] and recovered[2] == streams[2]}")
    print("    NOTE: TDM = fixed slots even when a tributary is idle; "
          "STDM would skip the idle slot (packet switching).")

    print("\n" + "=" * 66)
    print("Done. Same weights run from constellation to aggregate bit stream.")
    print("=" * 66)


if __name__ == "__main__":
    main()
