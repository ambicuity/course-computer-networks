#!/usr/bin/env python3
"""Ethernet performance: classic CSMA/CD efficiency, slot-time/diameter limits,
hub-vs-switch collision domains, Fast Ethernet PHYs, and duplex-mismatch triage.

Implements the Metcalfe & Boggs (1976) heavy-load model and Tanenbaum Eq. (4-7):

    A          = k * p * (1 - p) ** (k - 1)        # one station wins a slot
    efficiency = 1 / (1 + 2 * B * L * e / (c * F))  # optimal e-slot contention

All stdlib, no network calls. Run:  python3 main.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ---- Physical constants ----------------------------------------------------
SIGNAL_SPEED_MPS = 2.0e8          # ~0.66c, propagation in copper/UTP
E_SLOTS = math.e                  # asymptotic mean contention slots (optimal p)
MIN_FRAME_BYTES = 64              # 802.3 minimum frame = 512 bit slot at 10 Mbps
SLOT_BITS_10M = 512               # 64 bytes * 8


# ---- 1. Contention model ---------------------------------------------------
def prob_one_station_wins(k: int, p: float) -> float:
    """Probability A that exactly one of k stations acquires the slot (Eq. 4-5)."""
    if k <= 0:
        return 0.0
    return k * p * (1.0 - p) ** (k - 1)


def optimal_success_prob(k: int) -> float:
    """A at the optimal per-slot transmit probability p = 1/k."""
    return prob_one_station_wins(k, 1.0 / k)


def mean_contention_slots(k: int) -> float:
    """Mean slots per contention = 1/A; bounded above by e as k grows."""
    a = optimal_success_prob(k)
    return 1.0 / a if a > 0 else float("inf")


# ---- 2. Slot time, diameter, efficiency ------------------------------------
def slot_time_us(bandwidth_mbps: float) -> float:
    """Slot time in microseconds: 512 bit-times scaled by speed (51.2 us @ 10M)."""
    return SLOT_BITS_10M / (bandwidth_mbps * 1e6) * 1e6


def max_collision_diameter_m(bandwidth_mbps: float) -> float:
    """Worst-case round-trip span that still fits the 512-bit slot.

    2 * L / c <= slot_time  ->  L = slot_time * c / 2. ~5120 m at 10 Mbps,
    shrinking 10x to ~512 m at 100 Mbps (the 802.3u trade-off).
    """
    slot_s = slot_time_us(bandwidth_mbps) / 1e6
    return slot_s * SIGNAL_SPEED_MPS / 2.0


def channel_efficiency(frame_bytes: int, bandwidth_mbps: float,
                       cable_len_m: float) -> float:
    """Tanenbaum Eq. (4-7): 1 / (1 + 2*B*L*e / (c*F)) for the optimal e-slot case."""
    b_bps = bandwidth_mbps * 1e6
    f_bits = frame_bytes * 8
    penalty = (2.0 * b_bps * cable_len_m * E_SLOTS) / (SIGNAL_SPEED_MPS * f_bits)
    return 1.0 / (1.0 + penalty)


# ---- 3. Hub vs switch ------------------------------------------------------
@dataclass(frozen=True)
class BoxProfile:
    kind: str
    ports: int
    collision_domains: int
    runs_csma_cd: bool
    simultaneous_frames: int

    def describe(self) -> str:
        return (f"{self.kind:<7} ports={self.ports:<3} "
                f"collision_domains={self.collision_domains:<3} "
                f"CSMA/CD={'yes' if self.runs_csma_cd else 'no ':<3} "
                f"simultaneous_frames={self.simultaneous_frames}")


def hub_profile(ports: int) -> BoxProfile:
    """A hub is logically one shared cable: a single collision domain."""
    return BoxProfile("HUB", ports, 1, True, 1)


def switch_profile(ports: int, full_duplex: bool = True) -> BoxProfile:
    """A switch gives each port its own collision domain; full duplex => no CSMA/CD."""
    return BoxProfile("SWITCH", ports, ports, not full_duplex, ports)


# ---- 4. Fast Ethernet physical layers --------------------------------------
@dataclass(frozen=True)
class FastEthernetPHY:
    name: str
    cable: str
    pairs: str
    encoding: str
    max_segment_m: int
    full_duplex: bool


FAST_ETHERNET_PHYS: tuple[FastEthernetPHY, ...] = (
    FastEthernetPHY("100Base-T4", "Cat 3 UTP", "4 (3 active/dir)",
                    "ternary 8B6T @ 25 MHz", 100, False),
    FastEthernetPHY("100Base-TX", "Cat 5 UTP", "2",
                    "4B/5B @ 125 MHz", 100, True),
    FastEthernetPHY("100Base-FX", "MM fiber", "2 strands",
                    "4B/5B NRZI", 2000, True),
)


def phy_must_be_full_duplex(phy: FastEthernetPHY,
                            bandwidth_mbps: float = 100.0) -> bool:
    """True if the segment is longer than the half-duplex collision diameter,
    so a legal CSMA/CD hub link is impossible (e.g. 2 km 100Base-FX)."""
    return phy.max_segment_m > max_collision_diameter_m(bandwidth_mbps)


# ---- 5. Duplex-mismatch triage ---------------------------------------------
@dataclass(frozen=True)
class IfCounters:
    side: str
    late_collisions: int = 0
    fcs_errors: int = 0
    runts: int = 0
    carrier_sense_errors: int = 0


def classify_duplex(switch_side: IfCounters, host_side: IfCounters) -> str:
    """Heuristic per Shalunov & Carlson (2005). Late collisions + FCS + runts on
    the half-duplex end, carrier-sense errors on the full-duplex end => mismatch."""
    half_signature = (switch_side.late_collisions > 0
                      and switch_side.fcs_errors > 0
                      and switch_side.runts > 0)
    full_signature = host_side.carrier_sense_errors > 0
    if half_signature and full_signature:
        return ("DUPLEX MISMATCH: switch side is HALF duplex (late collisions + "
                "FCS + runts); host side is hard-set FULL (carrier-sense errors). "
                "Fix: set both ends to autonegotiate, or match duplex explicitly.")
    if half_signature:
        return ("Half-duplex collisions present on switch side, but no carrier "
                "errors on host. Check cabling/length before assuming mismatch.")
    return "No duplex-mismatch signature in these counters."


# ---- Demonstration ---------------------------------------------------------
def main() -> None:
    print("=" * 68)
    print("ETHERNET PERFORMANCE -> FAST ETHERNET")
    print("=" * 68)

    print("\n[1] Heavy-load contention (Metcalfe-Boggs, optimal p = 1/k)")
    print(f"  {'k stations':>11} | {'A (one wins)':>12} | {'mean slots':>10}")
    for k in (1, 2, 4, 8, 16, 64, 256):
        print(f"  {k:>11} | {optimal_success_prob(k):>12.4f} "
              f"| {mean_contention_slots(k):>10.3f}")
    print(f"  As k -> inf: A -> 1/e = {1/math.e:.4f}, mean slots -> e = {math.e:.3f}")

    print("\n[2] Channel efficiency at 10 Mbps, full 2500 m diameter (Eq. 4-7)")
    diam_10m = max_collision_diameter_m(10)
    print(f"  slot time = {slot_time_us(10):.1f} us, collision diameter = {diam_10m:.0f} m")
    print(f"  {'frame (B)':>9} | {'efficiency':>10}")
    for fb in (64, 256, 512, 1024):
        eff = channel_efficiency(fb, 10, diam_10m)
        print(f"  {fb:>9} | {eff*100:>9.1f}%")

    print("\n[3] Fast Ethernet slot-time trade-off (frame format unchanged)")
    for bw in (10, 100):
        print(f"  {bw:>4} Mbps: slot={slot_time_us(bw):.2f} us, "
              f"max diameter={max_collision_diameter_m(bw):.0f} m")

    print("\n[4] Hub vs switch (8 ports)")
    print("  " + hub_profile(8).describe())
    print("  " + switch_profile(8, full_duplex=True).describe())

    print("\n[5] Fast Ethernet PHYs")
    for phy in FAST_ETHERNET_PHYS:
        forced = phy_must_be_full_duplex(phy)
        note = "  <- too long for half-duplex hub, switch+full-duplex only" if forced else ""
        print(f"  {phy.name:<11} {phy.cable:<10} pairs={phy.pairs:<16} "
              f"{phy.encoding:<22} {phy.max_segment_m:>4} m "
              f"{'FULL' if phy.full_duplex else 'HALF'}{note}")

    print("\n[6] Duplex-mismatch triage on a 'slow 100/full' link")
    sw = IfCounters("switch", late_collisions=412, fcs_errors=1190, runts=380)
    host = IfCounters("host", carrier_sense_errors=905)
    print("  " + classify_duplex(sw, host))


if __name__ == "__main__":
    main()
