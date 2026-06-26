#!/usr/bin/env python3
"""Medium-access simulator: ALOHA, CSMA persistence, and the wireless hidden terminal.

This stdlib-only discrete-event simulator reproduces the classic random-access
throughput results and the wireless failure mode that breaks carrier sensing:

  * Pure ALOHA      S = G * e^(-2G), peak S = 1/(2e) ~= 0.184 at G = 0.5
  * Slotted ALOHA   S = G * e^(-G),  peak S = 1/e   ~= 0.368 at G = 1.0
  * 1-persistent vs non-persistent CSMA under rising offered load
  * Hidden-terminal collisions at the access point, and the RTS/CTS + NAV recovery

Throughput S is normalized goodput: successfully delivered frame-time per unit
time. Offered load G is the Poisson arrival rate in frames per frame-time.

Run:  python3 main.py
No third-party dependencies, no network access.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List

# --- Tunable model constants -------------------------------------------------
RNG_SEED = 20260621
SLOTS_PER_RUN = 200_000          # discrete slots simulated per data point
G_VALUES = [0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0]
PROP_RATIO_A = 0.01              # a = tau_prop / tau_frame; small => good sensing
RTS_OVERHEAD_FRACTION = 0.04     # RTS+CTS+SIFS cost as a fraction of a data frame


@dataclass
class Result:
    """Outcome of one simulation run at a fixed offered load G."""

    offered_load: float
    attempts: int
    successes: int

    @property
    def throughput(self) -> float:
        """Normalized goodput S = (success ratio) * offered load G."""
        if self.attempts == 0:
            return 0.0
        return (self.successes / self.attempts) * self.offered_load


def poisson_arrivals(rate_per_slot: float, rng: random.Random) -> int:
    """Number of new frames arriving in one slot, drawn from Poisson(rate)."""
    # Knuth's algorithm: stable and stdlib-only.
    limit = math.exp(-rate_per_slot)
    count = 0
    product = rng.random()
    while product > limit:
        count += 1
        product *= rng.random()
    return count


def simulate_aloha(slotted: bool, offered_load: float, rng: random.Random) -> Result:
    """Simulate pure or slotted ALOHA at a fixed offered load G.

    Pure ALOHA: a frame collides if any other frame overlaps within +/- 1
    frame-time (vulnerable window = 2). Slotted ALOHA: collision only if two or
    more frames pick the same slot (vulnerable window = 1).
    """
    successes = 0
    attempts = 0
    prev_arrivals = 0  # models the two-frame-time overlap of pure ALOHA
    for _ in range(SLOTS_PER_RUN):
        arrivals = poisson_arrivals(offered_load, rng)
        attempts += arrivals
        if slotted:
            # Exactly one arrival in this slot => clean transmission.
            if arrivals == 1:
                successes += 1
        else:
            # Pure ALOHA: a lone frame this slot AND none in the adjacent slot.
            if arrivals == 1 and prev_arrivals == 0:
                successes += 1
        prev_arrivals = arrivals
    return Result(offered_load, attempts, successes)


def simulate_csma(
    persistent: bool, offered_load: float, prop_ratio_a: float, rng: random.Random
) -> Result:
    """Simulate 1-persistent vs non-persistent CSMA at a fixed offered load.

    Carrier sense fails only during the propagation window 'a'. The persistence
    strategy decides behaviour when the channel is sensed busy:
      * 1-persistent: every waiting station transmits the instant it goes idle
        -> synchronized collisions grow with the number of waiters.
      * non-persistent: each waiter re-tries after a random delay -> the pounce
        is spread out and high-load collisions are reduced.
    """
    successes = 0
    attempts = 0
    busy = False
    for _ in range(SLOTS_PER_RUN):
        arrivals = poisson_arrivals(offered_load, rng)
        attempts += arrivals
        if arrivals == 0:
            busy = False
            continue
        if persistent:
            # Waiters released together: collide if the channel was just busy,
            # if more than one arrived, or if caught in the propagation window.
            collided = arrivals > 1 or busy or rng.random() < prop_ratio_a
        else:
            # Non-persistent backs off, so a prior-busy slot does not force a
            # synchronized retry; only same-slot contention and prop window hurt.
            collided = arrivals > 1 or rng.random() < prop_ratio_a
        if not collided:
            successes += 1
        busy = True
    return Result(offered_load, attempts, successes)


def simulate_hidden_terminal(
    use_rts_cts: bool, offered_load: float, rng: random.Random
) -> Result:
    """Two senders (A, C) out of range of each other but in range of AP B.

    Without RTS/CTS, carrier sense at A never detects C (and vice versa), so
    both transmit and collide at B whenever their frames overlap -- carrier
    sense buys nothing. With RTS/CTS, the AP's CTS is overheard by both senders;
    the loser sets its NAV and defers, so collisions at B vanish at the cost of
    a small handshake overhead.
    """
    successes = 0.0
    attempts = 0
    for _ in range(SLOTS_PER_RUN):
        a_sends = rng.random() < offered_load / 2.0
        c_sends = rng.random() < offered_load / 2.0
        local_attempts = int(a_sends) + int(c_sends)
        attempts += local_attempts
        if local_attempts == 0:
            continue
        if use_rts_cts:
            # CTS from B is overheard by the silent sender; one winner proceeds.
            # Charge the handshake overhead against delivered goodput.
            successes += 1.0 - RTS_OVERHEAD_FRACTION
        else:
            # Hidden terminals: simultaneous A and C collide at B.
            if local_attempts == 1:
                successes += 1.0
    return Result(offered_load, attempts, int(round(successes)))


def analytic_peak(slotted: bool) -> float:
    """Closed-form peak throughput for ALOHA."""
    return 1.0 / math.e if slotted else 1.0 / (2.0 * math.e)


def _row(label: str, values: List[float]) -> str:
    cells = "  ".join(f"{v:6.3f}" for v in values)
    return f"{label:<22}{cells}"


def main() -> None:
    rng = random.Random(RNG_SEED)

    header = "  ".join(f"{g:6.2f}" for g in G_VALUES)
    print("Medium-Access Simulator  (S = normalized goodput vs offered load G)\n")
    print(f"{'G ->':<22}{header}")
    print("-" * (22 + len(header)))

    pure = [simulate_aloha(False, g, rng).throughput for g in G_VALUES]
    slot = [simulate_aloha(True, g, rng).throughput for g in G_VALUES]
    print(_row("pure ALOHA", pure))
    print(_row("slotted ALOHA", slot))

    csma_1p = [simulate_csma(True, g, PROP_RATIO_A, rng).throughput for g in G_VALUES]
    csma_np = [simulate_csma(False, g, PROP_RATIO_A, rng).throughput for g in G_VALUES]
    print(_row("1-persistent CSMA", csma_1p))
    print(_row("non-persistent CSMA", csma_np))

    print("\nAnalytic peaks:")
    print(f"  pure ALOHA    1/(2e) = {analytic_peak(False):.4f}  (expected at G=0.5)")
    print(f"  slotted ALOHA 1/e    = {analytic_peak(True):.4f}  (expected at G=1.0)")
    print(f"  measured pure peak    = {max(pure):.4f}")
    print(f"  measured slotted peak = {max(slot):.4f}")

    print("\nHidden-terminal scenario (A and C cannot hear each other):")
    no_rts = simulate_hidden_terminal(False, 1.0, rng).throughput
    with_rts = simulate_hidden_terminal(True, 1.0, rng).throughput
    print(f"  carrier sense only, no RTS/CTS : goodput = {no_rts:.4f}")
    print(f"  with RTS/CTS + NAV             : goodput = {with_rts:.4f}")
    if no_rts > 0:
        print(f"  recovery factor                : {with_rts / no_rts:.2f}x")
    print(
        "\nTakeaway: carrier sense cannot prevent collisions it cannot hear;\n"
        "RTS/CTS replaces physical sensing with virtual sensing (NAV)."
    )


if __name__ == "__main__":
    main()
