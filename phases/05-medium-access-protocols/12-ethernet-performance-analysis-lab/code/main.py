#!/usr/bin/env python3
"""Ethernet performance analysis: slot time, bandwidth-distance product, and CSMA/CD efficiency.

This stdlib-only module computes the timing fundamentals of classic shared
Ethernet and measures channel efficiency under varying offered load:

  * Transmission time: how long to push frame bits onto the wire
  * Propagation delay: time for the first bit to cross the cable
  * Slot time: 512 bit-times (51.2 µs at 10 Mbps, 5.12 µs at 100 Mbps)
  * Bandwidth-distance product: bits physically in flight at once
  * CSMA/CD collision simulation with binary exponential backoff
  * Throughput curves from light load to saturation (64-byte vs 1518-byte frames)
  * Late collision detection on oversized collision domains

The collision-detection rule requires the minimum frame transmission time to
exceed the round-trip propagation delay of the collision domain.  This constrains
both minimum frame size (64 bytes / 512 bits) and maximum network diameter.

Run:  python3 main.py
No third-party dependencies, no network access.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import List

# ---------------------------------------------------------------------------
# Physical and IEEE 802.3 constants
# ---------------------------------------------------------------------------
SIGNAL_SPEED_MPS: float = 2e8       # ~2/3 speed of light on copper/fiber (m/s)
MIN_FRAME_BYTES: int = 64            # Smallest Ethernet frame (header + payload + FCS)
MAX_FRAME_BYTES: int = 1518          # Largest non-tagged Ethernet frame (bytes)
SLOT_TIME_BITS: int = 512            # Classic Ethernet slot = 64 bytes × 8 bits

# ---------------------------------------------------------------------------
# Simulation parameters
# ---------------------------------------------------------------------------
RNG_SEED: int = 20260621
SIMULATION_SLOTS: int = 60_000      # discrete slot-time events per data point
MAX_BACKOFF_ATTEMPTS: int = 16       # IEEE 802.3: discard after 16 failed attempts
MAX_BACKOFF_EXP_CAP: int = 10        # IEEE 802.3: backoff window capped at 2^10


# ---------------------------------------------------------------------------
# Analytic timing model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EthernetScenario:
    """One Ethernet configuration: line rate, frame size, and cable length.

    All timing values are derived analytically from physical constants and the
    IEEE 802.3 slot-time definition.  No simulation is needed here.
    """

    label: str
    line_rate_bps: float             # bits per second (e.g. 10e6 for 10 Mbps)
    frame_bytes: int
    cable_length_m: float

    # --- derived timing quantities ------------------------------------------

    @property
    def frame_bits(self) -> int:
        return self.frame_bytes * 8

    @property
    def transmission_time_s(self) -> float:
        """Serialization delay: time to clock all frame bits onto the wire."""
        return self.frame_bits / self.line_rate_bps

    @property
    def propagation_time_s(self) -> float:
        """One-way propagation: time for the first bit to reach the far end."""
        return self.cable_length_m / SIGNAL_SPEED_MPS

    @property
    def round_trip_delay_s(self) -> float:
        """Worst-case collision return time: 2 × one-way propagation."""
        return 2.0 * self.propagation_time_s

    @property
    def slot_time_s(self) -> float:
        """IEEE 802.3 slot time = SLOT_TIME_BITS / line_rate."""
        return SLOT_TIME_BITS / self.line_rate_bps

    @property
    def bits_in_flight(self) -> float:
        """Bandwidth-distance product: bits physically on the medium one-way."""
        return self.line_rate_bps * self.propagation_time_s

    @property
    def collision_window_ok(self) -> bool:
        """True when the sender can still be transmitting when a collision returns.

        The rule: transmission_time_s >= round_trip_delay_s.
        For the minimum 64-byte frame, this must hold for any cable in the domain.
        If it fails, a late collision (post-slot) is possible.
        """
        return self.transmission_time_s >= self.round_trip_delay_s

    def timing_row(self) -> str:
        tt_us = self.transmission_time_s * 1e6
        pt_us = self.propagation_time_s * 1e6
        rtt_us = self.round_trip_delay_s * 1e6
        st_us = self.slot_time_s * 1e6
        bif = self.bits_in_flight
        verdict = "OK" if self.collision_window_ok else "LATE COLLISION RISK"
        return (
            f"  {self.label}\n"
            f"    Tx time (frame)     : {tt_us:8.2f} µs\n"
            f"    One-way prop delay  : {pt_us:8.2f} µs\n"
            f"    Round-trip (2×prop) : {rtt_us:8.2f} µs\n"
            f"    Slot time (512 bits): {st_us:8.2f} µs\n"
            f"    Bits in flight      : {bif:8.1f} bits\n"
            f"    Collision window    : {verdict}"
        )


# ---------------------------------------------------------------------------
# CSMA/CD simulation with binary exponential backoff
# ---------------------------------------------------------------------------

@dataclass
class SimStats:
    """Accumulated statistics from one CSMA/CD simulation run."""

    frames_sent: int = 0
    frames_delivered: int = 0
    total_collisions: int = 0
    late_collisions: int = 0
    total_slot_time_used: int = 0    # slot-times consumed (tx + idle + collision waste)
    total_payload_bits: int = 0      # bits in successfully delivered frames

    @property
    def efficiency(self) -> float:
        """Useful payload bits / total channel bit-capacity consumed."""
        total_bits = self.total_slot_time_used * SLOT_TIME_BITS
        if total_bits == 0:
            return 0.0
        return self.total_payload_bits / total_bits

    @property
    def delivered_fraction(self) -> float:
        """Fraction of sent frames that were delivered without dropping."""
        if self.frames_sent == 0:
            return 0.0
        return self.frames_delivered / self.frames_sent


def _backoff_slots(attempt: int, rng: random.Random) -> int:
    """Binary exponential backoff: uniform random in [0, 2^min(attempt, cap))."""
    window = 2 ** min(attempt, MAX_BACKOFF_EXP_CAP)
    return rng.randrange(window)


def simulate_csmacd(
    num_stations: int,
    offered_load: float,           # aggregate arrival probability per slot (0–1)
    frame_bytes: int,
    cable_length_m: float,
    line_rate_bps: float,
    rng: random.Random,
) -> SimStats:
    """Discrete-time CSMA/CD simulation.

    Time is measured in Ethernet slot-times (512 bit-times each).  One slot is
    the smallest unit of contention: if two stations start transmitting in the
    same slot they detect the collision by the end of the round-trip propagation
    window and both jam, then back off.

    Stations sense the channel each slot.  If the channel is busy they defer.
    If the channel is idle and their backoff counter has reached zero they
    attempt to transmit.  Simultaneous attempts in the same slot collide.

    Late-collision detection: if the round-trip propagation (in slot-times) is
    greater than the minimum frame length (1 slot = 512 bits = 64 bytes), a
    collision can return after the sender has already finished the minimum
    frame—indicating an over-sized collision domain.
    """
    stats = SimStats()

    slot_time_s = SLOT_TIME_BITS / line_rate_bps
    frame_tx_slots = max(1, math.ceil((frame_bytes * 8) / SLOT_TIME_BITS))
    prop_delay_s = cable_length_m / SIGNAL_SPEED_MPS
    # Propagation in slot-times (0 means < half a slot — perfectly sensed)
    prop_slots: int = round(prop_delay_s / slot_time_s)

    # Minimum frame = exactly 1 slot (64 bytes = 512 bits = SLOT_TIME_BITS).
    # Late collision: round-trip > 1 slot time.
    min_frame_slots = 1
    late_collision_possible = (2 * prop_slots) > min_frame_slots

    # Per-station arrival probability (Bernoulli approximation of Poisson)
    per_station_prob = offered_load / num_stations

    # Station state vectors
    backoff: List[int] = [0] * num_stations
    ready: List[bool] = [False] * num_stations
    attempt_count: List[int] = [0] * num_stations
    channel_busy_until: int = -1  # first slot when channel is free again

    for slot in range(SIMULATION_SLOTS):
        # --- new frame arrivals ---
        for i in range(num_stations):
            if not ready[i] and rng.random() < per_station_prob:
                ready[i] = True
                attempt_count[i] = 0
                backoff[i] = 0

        # --- decrement backoff counters ---
        for i in range(num_stations):
            if ready[i] and backoff[i] > 0:
                backoff[i] -= 1

        channel_idle = slot >= channel_busy_until

        # --- gather stations ready to transmit ---
        txers = [
            i for i in range(num_stations)
            if ready[i] and backoff[i] == 0 and channel_idle
        ]

        if not txers:
            stats.total_slot_time_used += 1
            continue

        if len(txers) == 1:
            # --- successful transmission ---
            i = txers[0]
            stats.frames_sent += 1
            stats.frames_delivered += 1
            stats.total_payload_bits += frame_bytes * 8
            stats.total_slot_time_used += frame_tx_slots
            channel_busy_until = slot + frame_tx_slots
            ready[i] = False
            attempt_count[i] = 0

        else:
            # --- collision ---
            stats.frames_sent += len(txers)
            stats.total_collisions += len(txers)
            if late_collision_possible:
                stats.late_collisions += len(txers)

            # Channel occupied during collision: partial frame + round-trip
            collision_slots = max(1, 2 * prop_slots + 1)
            stats.total_slot_time_used += collision_slots
            channel_busy_until = slot + collision_slots

            # Binary exponential backoff for each collider
            for i in txers:
                attempt_count[i] += 1
                if attempt_count[i] > MAX_BACKOFF_ATTEMPTS:
                    ready[i] = False      # discard after too many retries
                    attempt_count[i] = 0
                else:
                    backoff[i] = _backoff_slots(attempt_count[i], rng)

    return stats


# ---------------------------------------------------------------------------
# Formatted output helpers
# ---------------------------------------------------------------------------

def _section(title: str) -> None:
    bar = "─" * (len(title) + 4)
    print(f"\n{bar}")
    print(f"  {title}")
    print(bar)


def _efficiency_table(
    frame_bytes: int,
    cable_m: float,
    line_rate_bps: float,
    num_stations: int,
    rng: random.Random,
) -> None:
    rate_mbps = line_rate_bps / 1e6
    slot_s = SLOT_TIME_BITS / line_rate_bps
    sim_duration_s = SIMULATION_SLOTS * slot_s
    print(
        f"\n  Frame={frame_bytes}B  Cable={cable_m:.0f}m  "
        f"Rate={rate_mbps:.0f}Mbps  Stations={num_stations}"
    )
    print(
        f"  {'Load':>6}  {'Goodput Mb/s':>13}  {'Efficiency':>11}  "
        f"{'Collisions':>12}  {'Late Coll.':>11}"
    )
    print(f"  {'─'*6}  {'─'*13}  {'─'*11}  {'─'*12}  {'─'*11}")

    for load in [0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90]:
        s = simulate_csmacd(
            num_stations, load, frame_bytes, cable_m, line_rate_bps, rng
        )
        goodput_mbps = (s.total_payload_bits / sim_duration_s) / 1e6
        print(
            f"  {load:6.2f}  {goodput_mbps:11.3f} Mb/s"
            f"  {s.efficiency * 100:9.1f}%"
            f"  {s.total_collisions:12d}"
            f"  {s.late_collisions:11d}"
        )


# ---------------------------------------------------------------------------
# Main demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    rng = random.Random(RNG_SEED)

    print("=" * 72)
    print("  ETHERNET PERFORMANCE ANALYSIS")
    print("  Slot time, bandwidth-distance product, and CSMA/CD efficiency")
    print("=" * 72)

    # ------------------------------------------------------------------
    # PART 1  Analytic timing worksheet
    # ------------------------------------------------------------------
    _section("TIMING WORKSHEET: Tx time, propagation, slot time, bits in flight")

    scenarios = [
        EthernetScenario("10 Mbps | 64 B min frame  | 500 m cable", 10e6, 64, 500),
        EthernetScenario("10 Mbps | 1518 B max frame | 500 m cable", 10e6, 1518, 500),
        EthernetScenario("100 Mbps| 64 B min frame  | 500 m cable", 100e6, 64, 500),
        EthernetScenario("100 Mbps| 1518 B max frame | 500 m cable", 100e6, 1518, 500),
        EthernetScenario("1 Gbps  | 64 B min frame  | 500 m cable", 1e9, 64, 500),
        EthernetScenario("10 Mbps | 64 B min frame  | 2500 m cable", 10e6, 64, 2500),
    ]

    for s in scenarios:
        print()
        print(s.timing_row())

    print()
    print("  Key insight:")
    print("    10 Mbps Ethernet: 64-byte frame Tx time = 51.2 µs = the slot time.")
    print("    The 2500 m max diameter gives RTT = 25 µs < 51.2 µs → collision")
    print("    always detected before the minimum frame finishes.  Safe.")
    print("    At 100 Mbps the slot shrinks to 5.12 µs, so the max diameter")
    print("    shrinks proportionally (≈ 250 m for a two-repeater topology).")
    print("    At 1 Gbps, the 64-byte frame Tx time (0.512 µs) is smaller than")
    print("    the 500 m RTT (5 µs), so half-duplex would need carrier extension")
    print("    or a domain under ~50 m — impractical; Gigabit Ethernet is always")
    print("    full-duplex switched in practice.")

    # ------------------------------------------------------------------
    # PART 2  Bandwidth-distance product across line rates
    # ------------------------------------------------------------------
    _section("BANDWIDTH-DISTANCE PRODUCT: bits in flight on a 500 m cable")

    print()
    print(f"  {'Rate':>10}  {'Prop delay':>12}  {'Bits in flight (one-way)':>25}")
    print(f"  {'─'*10}  {'─'*12}  {'─'*25}")
    for rate, label in [(10e6, "10 Mbps"), (100e6, "100 Mbps"), (1e9, "1 Gbps")]:
        s = EthernetScenario(label, rate, 64, 500)
        print(f"  {label:>10}  {s.propagation_time_s*1e6:10.2f} µs  {s.bits_in_flight:25.1f} bits")

    print()
    print("  Same cable, same propagation delay — but higher line rate means more")
    print("  bits are in flight simultaneously.  At 1 Gbps, a 500 m cable holds")
    print("  2500 bits, making half-duplex collision detection nearly impossible.")

    # ------------------------------------------------------------------
    # PART 3  Throughput vs. load: frame size comparison
    # ------------------------------------------------------------------
    _section("CSMA/CD EFFICIENCY vs OFFERED LOAD: 64-byte vs 1518-byte frames")
    print("  (10 Mbps, 500 m cable, 10 stations)")

    for fb in (MIN_FRAME_BYTES, MAX_FRAME_BYTES):
        _efficiency_table(fb, 500.0, 10e6, 10, rng)

    print()
    print("  Key insight:")
    print("    Larger frames amortize the collision/backoff overhead over more payload")
    print("    bits.  Under the same collision rate, a 1518-byte frame wastes less")
    print("    channel capacity per delivered byte than a 64-byte frame.")
    print("    At heavy load (≥ 0.50) the 64-byte curve drops faster because each")
    print("    retransmission costs proportionally more relative to its small payload.")

    # ------------------------------------------------------------------
    # PART 4  Line rate comparison: 10 vs 100 Mbps
    # ------------------------------------------------------------------
    _section("RATE SENSITIVITY: 64-byte frames, 500 m cable, 10 stations")
    print("  Propagation delay is identical; the slot-time shrinks 10× at 100 Mbps.")

    for rate in (10e6, 100e6):
        _efficiency_table(MIN_FRAME_BYTES, 500.0, rate, 10, rng)

    print()
    print("  Key insight:")
    print("    Higher line rate = shorter bit-time = propagation consumes more of")
    print("    the slot.  At 100 Mbps the 500 m cable uses ~49% of the slot-time")
    print("    budget (2.5 µs RTT vs 5.12 µs slot), leaving almost no margin.")
    print("    The collision domain must shrink as speed increases.")

    # ------------------------------------------------------------------
    # PART 5  Distance sensitivity and late-collision detection
    # ------------------------------------------------------------------
    _section("DISTANCE SENSITIVITY AND LATE COLLISIONS: 100 Mbps, 10 stations")
    print("  At 100 Mbps the slot = 5.12 µs.  A 700 m cable gives RTT = 7 µs > 5.12 µs.")
    print("  Collisions can then return AFTER the minimum 64-byte frame finishes.")

    for dist in (100.0, 500.0, 700.0):
        _efficiency_table(MIN_FRAME_BYTES, dist, 100e6, 10, rng)
        s_ref = EthernetScenario(f"{dist:.0f}m", 100e6, MIN_FRAME_BYTES, dist)
        rtt_us = s_ref.round_trip_delay_s * 1e6
        slot_us = s_ref.slot_time_s * 1e6
        verdict = "within slot" if rtt_us <= slot_us else "EXCEEDS slot → LATE COLLISION"
        print(f"    → RTT={rtt_us:.2f} µs  slot={slot_us:.2f} µs  [{verdict}]")

    print()
    print("  Key insight:")
    print("    Late collisions are not normal congestion.  They indicate an over-")
    print("    sized collision domain, duplex mismatch, or too many repeaters.")
    print("    The sender has already finished and released the medium before it")
    print("    discovers the frame was corrupted — binary exponential backoff will")
    print("    retry, but from the sender's view the frame 'should' have succeeded.")

    # ------------------------------------------------------------------
    # PART 6  Why modern Ethernet eliminated shared CSMA/CD
    # ------------------------------------------------------------------
    _section("SUMMARY: Slot time, shared limits, and the switch transition")
    print("""
  Classic 10 Mbps Ethernet (10BASE-5 / 10BASE-T)
  ─────────────────────────────────────────────────
  • Slot time: 512 bits / 10 Mbps = 51.2 µs
  • Minimum frame: 64 bytes ensures the sender occupies one full slot
  • Maximum diameter: ~2500 m with repeaters (RTT fits inside 51.2 µs)
  • At saturation: binary exponential backoff limits collapse, but
    efficiency can fall below 40% when many stations contend

  Fast Ethernet 100 Mbps (100BASE-TX)
  ─────────────────────────────────────────────────
  • Slot time: 512 bits / 100 Mbps = 5.12 µs  (10× shorter)
  • Maximum diameter: ~250 m (collision domain shrank proportionally)
  • Shared half-duplex use became rare; most ports went full-duplex

  Gigabit Ethernet 1000 Mbps (1000BASE-T)
  ─────────────────────────────────────────────────
  • Slot time for 64-byte frame: 512 bits / 1 Gbps = 0.512 µs
  • Propagation on a 100 m cable: 0.5 µs — almost equal to Tx time
  • Half-duplex required carrier extension to 512 bytes (4096 bits)
  • In practice, all Gigabit Ethernet links are full-duplex switched;
    CSMA/CD was retained in the standard but is never triggered

  Switched full-duplex: end of CSMA/CD
  ─────────────────────────────────────────────────
  • Each port has a dedicated Tx path and a dedicated Rx path
  • No shared medium → no contention → no collision possible
  • CSMA/CD, slot time, minimum frame constraints, and BEB are all
    rendered irrelevant by the switch fabric
  • The minimum 64-byte frame survives as a frame size floor for
    backward compatibility, not for collision detection
    """)


if __name__ == "__main__":
    main()
