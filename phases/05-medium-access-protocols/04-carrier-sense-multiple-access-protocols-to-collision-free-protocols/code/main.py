#!/usr/bin/env python3
"""Carrier-sense and collision-free MAC protocol models (stdlib only).

This module reproduces the core mechanisms from Tanenbaum & Wetherall ch. 4
sections 4.2.2 (CSMA / CSMA-CD) and 4.2.3 (collision-free protocols):

  * Analytic channel-utilization curves S(G) for ALOHA, slotted ALOHA, and
    1-persistent / nonpersistent CSMA, so the load ordering of Figure 4-4 can
    be reproduced and inspected.
  * A CSMA/CD slot-time (2 tau) and minimum-frame calculator that explains the
    64-byte / 51.2 us rule for 10 Mbps Ethernet and flags runts.
  * A binary-countdown arbitration tracer using the wired-OR rule.
  * A bit-map vs binary-countdown overhead comparison.

Run directly:  python3 main.py
No third-party dependencies, no network access.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# --------------------------------------------------------------------------- #
# Analytic throughput models S(G).  G = offered load (attempts per frame time).
# --------------------------------------------------------------------------- #

def aloha_throughput(g: float) -> float:
    """Pure ALOHA: S = G * e^(-2G). Peaks at 1/(2e) ~= 0.184 at G = 0.5."""
    return g * math.exp(-2.0 * g)


def slotted_aloha_throughput(g: float) -> float:
    """Slotted ALOHA: S = G * e^(-G). Peaks at 1/e ~= 0.368 at G = 1."""
    return g * math.exp(-g)


def nonpersistent_csma_throughput(g: float, a: float) -> float:
    """Nonpersistent CSMA (Kleinrock & Tobagi, 1975).

    `a` is the normalized propagation delay = tau / frame_time, i.e. the
    fraction of a frame that fits on the wire (the bandwidth-delay product).
    Smaller `a` -> higher achievable utilization.
    """
    num = g * math.exp(-a * g)
    den = g * (1.0 + 2.0 * a) + math.exp(-a * g)
    return num / den


def one_persistent_csma_throughput(g: float, a: float) -> float:
    """1-persistent CSMA (Kleinrock & Tobagi, 1975).

    Greedier than nonpersistent: every station that waited out a busy channel
    fires the instant it goes idle, so utilization is lower at high load.
    """
    exp_g1a = math.exp(-g * (1.0 + a))
    num = g * (1.0 + g + a * g * (1.0 + g + a * g / 2.0)) * exp_g1a
    den = g * (1.0 + 2.0 * a) - (1.0 - math.exp(-a * g)) + (1.0 + a * g) * exp_g1a
    return num / den


# --------------------------------------------------------------------------- #
# CSMA/CD slot time and minimum frame size.
# --------------------------------------------------------------------------- #

SPEED_OF_PROPAGATION_M_PER_S = 2.0e8  # ~0.66c on copper, a common assumption


@dataclass(frozen=True)
class SlotResult:
    """Outcome of a CSMA/CD slot-time computation."""

    one_way_tau_us: float
    slot_time_2tau_us: float
    min_frame_bits: int
    min_frame_bytes: float


def csmacd_slot(cable_len_m: float, bit_rate_bps: float,
                prop_speed: float = SPEED_OF_PROPAGATION_M_PER_S) -> SlotResult:
    """Compute the 2*tau contention slot and the implied minimum frame.

    A CSMA/CD sender must still be transmitting at t = 2*tau (the worst-case
    round trip) to be certain of hearing a collision. Hence:
        min_frame_bits = slot_time * bit_rate
    """
    tau_s = cable_len_m / prop_speed
    slot_s = 2.0 * tau_s
    min_bits = slot_s * bit_rate_bps
    return SlotResult(
        one_way_tau_us=tau_s * 1e6,
        slot_time_2tau_us=slot_s * 1e6,
        min_frame_bits=int(math.ceil(min_bits)),
        min_frame_bytes=min_bits / 8.0,
    )


def is_runt(frame_bytes: int, slot: SlotResult) -> bool:
    """A frame shorter than the slot-time minimum is a runt (unsafe for CD)."""
    return frame_bytes < math.ceil(slot.min_frame_bytes)


# --------------------------------------------------------------------------- #
# Binary countdown (wired-OR address arbitration).
# --------------------------------------------------------------------------- #

def binary_countdown(addresses: list[int], width: int) -> tuple[int, list[str]]:
    """Run one binary-countdown bidding round; return (winner, trace lines).

    Rule: contenders broadcast their address MSB-first. The channel BOOLEAN-ORs
    simultaneously asserted bits. A station drops out the moment it sees a bit
    that is 0 in its own address overwritten by a 1 on the channel. The highest
    surviving address wins.
    """
    contenders = set(addresses)
    trace: list[str] = []
    for bit in range(width - 1, -1, -1):
        # Wired-OR: channel shows 1 if any surviving contender asserts this bit.
        channel_bit = 1 if any((a >> bit) & 1 for a in contenders) else 0
        dropped = {a for a in contenders
                   if (a >> bit) & 1 == 0 and channel_bit == 1}
        bit_index = width - 1 - bit
        survivors = sorted(_fmt(a, width) for a in contenders)
        drops = sorted(_fmt(a, width) for a in dropped) or ["-"]
        trace.append(
            f"  bit {bit_index} (2^{bit}): wired-OR={channel_bit} "
            f"survivors={survivors} drop={drops}"
        )
        contenders -= dropped
        if len(contenders) == 1:
            break
    winner = max(contenders) if contenders else max(addresses)
    return winner, trace


def _fmt(addr: int, width: int) -> str:
    return format(addr, f"0{width}b")


# --------------------------------------------------------------------------- #
# Overhead comparison: bit-map vs binary countdown.
# --------------------------------------------------------------------------- #

def bitmap_overhead_bits(n_stations: int) -> int:
    """Basic bit-map protocol: one contention bit per station per cycle."""
    return n_stations


def binary_countdown_overhead_bits(n_stations: int) -> int:
    """Binary countdown: ceil(log2 N) arbitration bits per winning frame."""
    return max(1, math.ceil(math.log2(n_stations)))


# --------------------------------------------------------------------------- #
# Demonstration.
# --------------------------------------------------------------------------- #

def main() -> None:
    print("=" * 70)
    print("CSMA family: channel utilization S vs offered load G  (a = 0.01)")
    print("=" * 70)
    a = 0.01
    print(f"{'G':>5} | {'pureALOHA':>9} | {'slotALOHA':>9} | "
          f"{'nonpers':>9} | {'1-persist':>9}")
    print("-" * 60)
    for g in (0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 8.0):
        print(f"{g:>5.2f} | {aloha_throughput(g):>9.3f} | "
              f"{slotted_aloha_throughput(g):>9.3f} | "
              f"{nonpersistent_csma_throughput(g, a):>9.3f} | "
              f"{one_persistent_csma_throughput(g, a):>9.3f}")
    print("\nNote: slotted ALOHA caps at 1/e =", round(1 / math.e, 3),
          "-- CSMA exceeds it because stations listen before talking.")

    print("\n" + "=" * 70)
    print("CSMA/CD slot time and minimum frame size")
    print("=" * 70)
    examples = [
        ("Classic 10 Mbps, 2500 m (4 repeaters)", 2500.0, 10e6),
        ("Fast Ethernet 100 Mbps, 200 m segment", 200.0, 100e6),
        ("Gigabit 1 Gbps, 100 m segment", 100.0, 1e9),
    ]
    for label, length_m, rate in examples:
        s = csmacd_slot(length_m, rate)
        print(f"\n{label}")
        print(f"  one-way tau   = {s.one_way_tau_us:8.2f} us")
        print(f"  slot 2*tau    = {s.slot_time_2tau_us:8.2f} us")
        print(f"  min frame     = {s.min_frame_bits} bits "
              f"= {s.min_frame_bytes:.1f} bytes")
        verdict = "RUNT (unsafe)" if is_runt(64, s) else "64 B is safe"
        print(f"  64-byte frame : {verdict}")

    print("\n" + "=" * 70)
    print("Binary countdown: wired-OR bidding (Datakit, Fraser 1987)")
    print("=" * 70)
    addrs = [0b0010, 0b0100, 0b1001, 0b1010]
    print("Contenders:", [_fmt(addr, 4) for addr in addrs])
    winner, trace = binary_countdown(addrs, width=4)
    for line in trace:
        print(line)
    print(f"  WINNER = {_fmt(winner, 4)} (= decimal {winner}, the highest "
          f"address)")

    print("\n" + "=" * 70)
    print("Per-cycle overhead: bit-map vs binary countdown")
    print("=" * 70)
    print(f"{'stations':>9} | {'bit-map bits':>12} | {'bin-countdown bits':>18}")
    print("-" * 46)
    for n in (8, 64, 1000, 100000):
        print(f"{n:>9} | {bitmap_overhead_bits(n):>12} | "
              f"{binary_countdown_overhead_bits(n):>18}")
    print("\nBit-map cost grows as N; binary countdown grows as log2(N), so it "
          "scales to thousands of stations.")


if __name__ == "__main__":
    main()
