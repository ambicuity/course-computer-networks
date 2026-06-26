#!/usr/bin/env python3
"""Assumptions for Dynamic Channel Allocation — a runnable model.

This program turns the five modeling assumptions behind every multiple-access
protocol (Tanenbaum & Wetherall, Computer Networks 6e, sec. 4.1.2) into code:

    1. Independent Traffic   -> Poisson frame arrivals at mean offered load G
    2. Single Channel        -> one shared timeline; no side channel
    3. Observable Collisions -> overlapping frames are all lost
    4. Continuous / Slotted  -> vulnerable period of 2 frame-times vs 1
    5. Carrier Sense or not   -> recorded as a switch; ALOHA assumes NONE

It does two things:

  * static_division_delay(): reproduces the M/M/1 baseline T = 1/(uC - lambda)
    and the static N-way penalty T_N = N*T that dynamic allocation must beat.
  * simulate_aloha(): a Monte Carlo contention simulator whose measured
    throughput S is compared against the closed forms
        pure   ALOHA:  S = G * exp(-2G)   (peak ~0.184 at G = 0.5)
        slotted ALOHA: S = G * exp(-G)    (peak ~0.368 at G = 1.0)

Stdlib only. Run:  python3 main.py
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

# The only fixed quantity is the frame time, normalized to 1.0 so that the
# offered load G is expressed directly in frames per frame-time.
FRAME_TIME: float = 1.0


@dataclass(frozen=True)
class Assumptions:
    """The five assumptions as explicit, per-protocol switches.

    Two are structural (independent_traffic, single_channel) and are always
    True here. Three are engineering switches you flip per protocol.
    """

    independent_traffic: bool = True   # Poisson arrivals, station blocks per frame
    single_channel: bool = True        # one shared medium, no side channel
    observable_collisions: bool = True # overlaps are detectable and lost
    slotted: bool = False              # True => 1-frame vulnerable period
    carrier_sense: bool = False        # ALOHA has none; CSMA/Ethernet does

    def vulnerable_period(self) -> float:
        """Window (in frame-times) during which a competing start kills us."""
        return FRAME_TIME if self.slotted else 2.0 * FRAME_TIME


def static_division_delay(
    capacity_bps: float,
    mean_frame_bits: float,
    arrival_rate_fps: float,
    subchannels: int,
) -> tuple[float, float]:
    """Return (T, T_N) in seconds for the M/M/1 single channel vs N-way split.

    T   = 1 / (mu*C - lambda)         single shared channel
    T_N = N / (mu*C - lambda) = N*T   statically divided into N subchannels

    mu = 1 / mean_frame_bits is the service rate in frames per bit of capacity,
    so mu*C is the channel service rate in frames/second.
    """
    if capacity_bps <= 0 or mean_frame_bits <= 0:
        raise ValueError("capacity and frame size must be positive")
    service_rate_fps = capacity_bps / mean_frame_bits  # mu * C, frames/sec
    if service_rate_fps <= arrival_rate_fps:
        raise ValueError("unstable: arrival rate >= service rate (lambda >= mu*C)")
    t_single = 1.0 / (service_rate_fps - arrival_rate_fps)
    t_divided = subchannels * t_single
    return t_single, t_divided


def analytic_throughput(offered_load: float, slotted: bool) -> float:
    """Closed-form ALOHA throughput S = G*exp(-kG), k = 1 (slotted) or 2 (pure)."""
    k = 1.0 if slotted else 2.0
    return offered_load * math.exp(-k * offered_load)


def simulate_aloha(
    offered_load: float,
    assumptions: Assumptions,
    num_frames: int,
    rng: random.Random,
) -> float:
    """Monte Carlo throughput for one offered load G under the given assumptions.

    Independent Traffic: inter-arrival gaps are exponential with mean 1/G
    frame-times (a Poisson process). Observable Collisions: a frame succeeds
    only if no other frame's start falls within its vulnerable period.
    """
    if offered_load <= 0:
        return 0.0

    # Generate Poisson arrival start times on a continuous timeline.
    starts: list[float] = []
    clock = 0.0
    for _ in range(num_frames):
        clock += rng.expovariate(offered_load)  # mean gap = 1/G
        starts.append(clock)
    starts.sort()

    if assumptions.slotted:
        # Bin each arrival into an integer slot. A slot is a success only if
        # exactly one frame lands in it; >=2 is a collision, 0 is idle.
        counts: dict[int, int] = {}
        for start in starts:
            slot = int(start)  # floor into a discrete slot index
            counts[slot] = counts.get(slot, 0) + 1
        successes = sum(1 for c in counts.values() if c == 1)
        elapsed_slots = (int(starts[-1]) - int(starts[0])) + 1
        return successes / elapsed_slots if elapsed_slots > 0 else 0.0

    # Pure ALOHA: collision iff a neighbor starts within one frame-time on
    # either side (total vulnerable period = 2 frame-times).
    successes = 0
    for i, start in enumerate(starts):
        prev_hit = i > 0 and (start - starts[i - 1]) < FRAME_TIME
        next_hit = i + 1 < len(starts) and (starts[i + 1] - start) < FRAME_TIME
        if not (prev_hit or next_hit):
            successes += 1

    total_span = starts[-1] - starts[0] if len(starts) > 1 else FRAME_TIME
    # Throughput S = useful frame-times / elapsed frame-times.
    return successes * FRAME_TIME / total_span if total_span > 0 else 0.0


def _bar(value: float, scale: float = 60.0) -> str:
    return "#" * int(round(value * scale))


def main() -> None:
    rng = random.Random(20260621)

    print("=" * 68)
    print("ASSUMPTION 1+2 baseline: static channel division is N times worse")
    print("=" * 68)
    capacity, frame, lam, n = 100e6, 10_000.0, 5000.0, 10
    t1, tn = static_division_delay(capacity, frame, lam, n)
    print(f"  C = {capacity / 1e6:.0f} Mbps, mean frame = {frame:.0f} bits, "
          f"lambda = {lam:.0f} frames/s")
    print(f"  Single shared channel    T   = {t1 * 1e6:8.1f} us")
    print(f"  Split into N = {n} channels T_N = {tn * 1e6:8.1f} us  (= {n} x T)")
    print(f"  Penalty factor           T_N/T = {tn / t1:.1f}\n")

    print("=" * 68)
    print("ASSUMPTIONS 3+4: ALOHA throughput vs offered load G")
    print("(Observable Collisions + Continuous/Slotted time, NO carrier sense)")
    print("=" * 68)

    for label, slotted in (("PURE  (vulnerable period = 2 frame-times)", False),
                           ("SLOTTED (vulnerable period = 1 frame-time)", True)):
        assumptions = Assumptions(slotted=slotted, carrier_sense=False)
        print(f"\n  {label}")
        print(f"  {'G':>5} {'S(sim)':>8} {'S(theory)':>10}   curve")
        peak_g, peak_s = 0.0, 0.0
        for step in range(1, 21):
            g = step * 0.15
            s_sim = simulate_aloha(g, assumptions, num_frames=8000, rng=rng)
            s_th = analytic_throughput(g, slotted)
            if s_sim > peak_s:
                peak_s, peak_g = s_sim, g
            print(f"  {g:5.2f} {s_sim:8.3f} {s_th:10.3f}   {_bar(s_sim)}")
        print(f"  -> simulated peak S = {peak_s:.3f} at G = {peak_g:.2f}")

    print("\n" + "=" * 68)
    print("ASSUMPTION 5: carrier sense is a switch, not a given")
    print("=" * 68)
    for proto, assumptions in (
        ("Pure ALOHA   ", Assumptions(slotted=False, carrier_sense=False)),
        ("Slotted ALOHA", Assumptions(slotted=True, carrier_sense=False)),
        ("CSMA/Ethernet", Assumptions(slotted=False, carrier_sense=True)),
    ):
        sense = "yes" if assumptions.carrier_sense else "no"
        slot = "yes" if assumptions.slotted else "no"
        print(f"  {proto}: carrier_sense={sense:>3}  slotted={slot:>3}  "
              f"vulnerable_period={assumptions.vulnerable_period():.0f} frame-times")


if __name__ == "__main__":
    main()
