#!/usr/bin/env python3
"""ALOHA channel simulator and analytic model (pure and slotted).

This stdlib-only program reproduces the classic ALOHA throughput results from
Tanenbaum, Computer Networks, section 4.2.1:

    Pure ALOHA:    S = G * e^(-2G)   peak 1/(2e) ~= 0.184 at G = 0.5
    Slotted ALOHA: S = G * e^(-G)    peak 1/e    ~= 0.368 at G = 1.0

It does two things:
  1. Prints the closed-form analytic throughput curve for both variants.
  2. Runs a Monte-Carlo experiment: in each frame time we draw a Poisson number
     of transmission attempts with mean G. A frame SUCCEEDS only if it is the
     lone transmitter in its vulnerable period (one slot for slotted ALOHA;
     two slots for pure ALOHA). Measured success rates are printed beside the
     theory to show convergence.

No third-party packages, no network calls. Run: python3 main.py
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


# --- Analytic model ---------------------------------------------------------

def pure_aloha_throughput(g: float) -> float:
    """Throughput S of pure ALOHA at offered load g (attempts per frame time)."""
    return g * math.exp(-2.0 * g)


def slotted_aloha_throughput(g: float) -> float:
    """Throughput S of slotted ALOHA at offered load g."""
    return g * math.exp(-g)


def slot_outcome_probabilities(g: float) -> tuple[float, float, float]:
    """Return (empty, success, collision) probabilities for one slotted slot.

    empty     = P(0 attempts)        = e^(-g)
    success   = P(exactly 1 attempt) = g * e^(-g)
    collision = P(>= 2 attempts)     = 1 - empty - success
    """
    empty = math.exp(-g)
    success = g * math.exp(-g)
    collision = 1.0 - empty - success
    return empty, success, collision


def expected_transmissions(g: float) -> float:
    """Expected transmissions per delivered frame (slotted): E = e^g."""
    return math.exp(g)


def poisson_sample(mean: float, rng: random.Random) -> int:
    """Draw one Poisson-distributed integer using Knuth's algorithm (stdlib only)."""
    limit = math.exp(-mean)
    k = 0
    product = 1.0
    while True:
        k += 1
        product *= rng.random()
        if product <= limit:
            return k - 1


# --- Monte-Carlo channel ----------------------------------------------------

@dataclass(frozen=True)
class SimResult:
    g: float
    measured_throughput: float
    theory_throughput: float
    empty_frac: float
    collision_frac: float


def simulate_slotted(g: float, slots: int, rng: random.Random) -> SimResult:
    """Slotted ALOHA: each slot succeeds iff exactly one station transmits."""
    successes = empties = collisions = 0
    for _ in range(slots):
        attempts = poisson_sample(g, rng)
        if attempts == 0:
            empties += 1
        elif attempts == 1:
            successes += 1
        else:
            collisions += 1
    return SimResult(
        g=g,
        measured_throughput=successes / slots,
        theory_throughput=slotted_aloha_throughput(g),
        empty_frac=empties / slots,
        collision_frac=collisions / slots,
    )


def simulate_pure(g: float, slots: int, rng: random.Random) -> SimResult:
    """Pure ALOHA approximated on a fine time grid.

    Continuous time is modeled by subdividing each frame time into many
    micro-slots and placing frame *starts* as a Poisson process. A start is a
    success only when it is the lone start within +/- one frame time of itself
    (its two-frame-time vulnerable window).
    """
    sub = 20  # micro-slots per frame time
    micro_mean = g / sub
    grid = [poisson_sample(micro_mean, rng) for _ in range(slots * sub)]
    window = sub  # one frame time, in micro-slots
    successes = 0
    n = len(grid)
    for i in range(n):
        if grid[i] != 1:
            continue
        lo = max(0, i - window)
        hi = min(n, i + window + 1)
        others = sum(grid[lo:hi]) - grid[i]
        if others == 0:
            successes += 1
    return SimResult(
        g=g,
        measured_throughput=successes / slots,
        theory_throughput=pure_aloha_throughput(g),
        empty_frac=0.0,
        collision_frac=0.0,
    )


# --- Reporting --------------------------------------------------------------

def print_peaks() -> None:
    print("Analytic peaks")
    print("-" * 60)
    print(f"  Pure ALOHA   : S_max = 1/(2e) = {1 / (2 * math.e):.4f} at G = 0.5")
    print(f"  Slotted ALOHA: S_max = 1/e    = {1 / math.e:.4f} at G = 1.0")
    empty, success, collision = slot_outcome_probabilities(1.0)
    print(
        f"  Slotted @ G=1: empty={empty:.3f} success={success:.3f} "
        f"collision={collision:.3f}"
    )
    print()


def print_sweep(rng: random.Random, slots: int) -> None:
    loads = [0.1, 0.3, 0.5, 0.7, 1.0, 1.5, 2.0, 3.0]
    print(f"Throughput sweep (Monte-Carlo, {slots} frame times per point)")
    print("-" * 72)
    header = (
        f"{'G':>5} | {'pure meas':>10} {'pure thy':>9} | "
        f"{'slot meas':>10} {'slot thy':>9}"
    )
    print(header)
    print("-" * 72)
    for g in loads:
        pure = simulate_pure(g, slots, rng)
        slot = simulate_slotted(g, slots, rng)
        print(
            f"{g:>5.1f} | {pure.measured_throughput:>10.4f} "
            f"{pure.theory_throughput:>9.4f} | "
            f"{slot.measured_throughput:>10.4f} {slot.theory_throughput:>9.4f}"
        )
    print()


def print_collapse() -> None:
    print("Congestion collapse (slotted): expected transmissions E = e^G")
    print("-" * 60)
    for g in [0.5, 1.0, 1.5, 2.0, 3.0]:
        s = slotted_aloha_throughput(g)
        e = expected_transmissions(g)
        note = "  <-- peak" if abs(g - 1.0) < 1e-9 else ""
        print(f"  G={g:>3.1f}  throughput={s:.4f}  E(tx/frame)={e:6.2f}{note}")
    print()
    print("  Past G=1 throughput falls while retransmissions explode: collapse.")
    print()


def main() -> None:
    rng = random.Random(42)
    print("=" * 72)
    print("ALOHA: pure vs slotted random-access channel")
    print("=" * 72)
    print()
    print_peaks()
    print_sweep(rng, slots=40_000)
    print_collapse()
    print("Read off: pure peaks near G=0.5 (~0.184), slotted near G=1 (~0.368).")
    print("Both measured curves should track theory within Monte-Carlo noise.")


if __name__ == "__main__":
    main()
