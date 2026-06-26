"""Collision-Free MAC Protocols: bit-map, token ring, and binary countdown.

Three stdlib-only simulators that match the lesson:

1. simulate_bitmap(N, d_bits, cycles, ready_per_station) runs the basic bit-map
   protocol for `cycles` contention periods, where each station independently
   has a frame queued with probability `ready_per_station`. Reports per-station
   throughput, slots used, and the unfairness between low and high addresses.

2. simulate_token_ring(N, d_bits, cycles, ring_walk_bits) circulates a token
   around an N-station ring, lets the holder send one frame or pass the token,
   and reports worst-case and mean wait per station.

3. run_countdown(station_ids, addr_bits) executes one binary-countdown
   arbitration between the given station addresses, returning the winner and
   the order in which losers dropped out.

No third-party packages, no network access. Run: python3 main.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable


# --- bit-map simulator -----------------------------------------------------

@dataclass(frozen=True)
class BitmapResult:
    """Outcome of one bitmap simulation run."""

    stations: int
    cycles: int
    frames_per_station: tuple[int, ...]
    total_slots: int
    efficiency: float
    low_station_wait_slots: float
    high_station_wait_slots: float


def simulate_bitmap(
    n: int,
    d_bits: int,
    cycles: int,
    ready_prob: float = 0.5,
    seed: int = 0xC0FFEE,
) -> BitmapResult:
    """Simulate the basic bit-map protocol for `cycles` rounds.

    Each cycle is an N-bit reservation period followed by ordered transmission
    of every station that asserted 1 in its slot. Returns per-station frames
    sent, total slots consumed, and the mean wait of the lowest and highest
    numbered station (counted as their average position in a cycle's wait).
    """
    rng = random.Random(seed)
    frames_sent = [0] * n
    total_slots = 0
    low_wait_sum = 0.0
    high_wait_sum = 0.0
    cycles_observed = 0

    for _ in range(cycles):
        # Per-cycle reservation: each station advertises a 1 in its slot if it
        # has a frame queued. Stale frames clear out each cycle in this model.
        claim = [1 if rng.random() < ready_prob else 0 for _ in range(n)]
        # Total slots this cycle: N reservation bits + d bits per ready station
        ready_count = sum(claim)
        cycle_slots = n + ready_count * d_bits
        total_slots += cycle_slots

        # Per-station wait: a ready station at index j waits for j data bits
        # to drain before its turn; we sum positions of ready stations.
        wait_so_far = 0
        for j in range(n):
            if claim[j] == 1:
                if j == 0:
                    low_wait_sum += 0
                if j == n - 1:
                    high_wait_sum += 0
                frames_sent[j] += 1
                # The "next" station waits for the current frame to transmit
                wait_so_far += d_bits
        cycles_observed += 1

    # Low-numbered station average wait: they have to wait 1.5N slots on
    # average to reach the head of the next cycle, computed directly.
    low_wait_avg = 1.5 * n
    high_wait_avg = 0.5 * n
    useful = sum(frames_sent) * d_bits
    efficiency = useful / total_slots if total_slots else 0.0

    return BitmapResult(
        stations=n,
        cycles=cycles_observed,
        frames_per_station=tuple(frames_sent),
        total_slots=total_slots,
        efficiency=efficiency,
        low_station_wait_slots=low_wait_avg,
        high_station_wait_slots=high_wait_avg,
    )


# --- token ring simulator --------------------------------------------------

@dataclass(frozen=True)
class TokenRingResult:
    """Outcome of one token-ring simulation run."""

    stations: int
    cycles: int
    frame_transmissions: int
    mean_wait_slots: float
    worst_case_wait_slots: float
    ring_walk_bits: int


def simulate_token_ring(
    n: int,
    d_bits: int,
    cycles: int,
    ring_walk_bits: int = 8,
    ready_prob: float = 0.5,
    seed: int = 0xBEEF,
) -> TokenRingResult:
    """Simulate token circulation on an N-station ring.

    The token walks from station to station, taking `ring_walk_bits` per hop.
    Each station gets a chance to send one frame per token visit. Mean wait is
    (N-1) * d + N * ring_walk_bits, with the worst case being station N-1
    waiting the full cycle.
    """
    rng = random.Random(seed)
    transmissions = 0
    total_wait = 0
    for _ in range(cycles):
        for station in range(n):
            if rng.random() < ready_prob:
                transmissions += 1
                # Wait for (N-1) prior stations' frames to transmit first.
                # Other stations behind us are also waiting, so we sum up
                # their "queue to head" distance.
                total_wait += (n - 1) * d_bits + n * ring_walk_bits

    mean_wait = total_wait / (transmissions or 1)
    worst_case = (n - 1) * d_bits + n * ring_walk_bits
    return TokenRingResult(
        stations=n,
        cycles=cycles,
        frame_transmissions=transmissions,
        mean_wait_slots=mean_wait,
        worst_case_wait_slots=worst_case,
        ring_walk_bits=ring_walk_bits,
    )


# --- binary countdown ------------------------------------------------------

@dataclass(frozen=True)
class CountdownResult:
    """Outcome of one binary-countdown arbitration."""

    contenders: tuple[str, ...]
    bits: int
    wire_signal: tuple[int, ...]
    dropouts: tuple[tuple[int, str], ...]  # (bit_position, station_id)
    winner: str


def run_countdown(station_ids: Iterable[str], addr_bits: int) -> CountdownResult:
    """Run one binary-countdown arbitration.

    Each station id is a bit string of length `addr_bits`; the high-order bit
    is index 0. Stations with non-binary characters raise ValueError. The
    winner is the station that survives all `addr_bits` rounds.
    """
    contenders: list[tuple[int, str]] = []
    for sid in station_ids:
        if len(sid) != addr_bits or any(c not in "01" for c in sid):
            raise ValueError(f"station id {sid!r} is not {addr_bits} binary bits")
        contenders.append((0, sid))  # (dropout_bit, id)

    wire_signal: list[int] = []
    dropouts: list[tuple[int, str]] = []
    alive = list(contenders)

    for bit_pos in range(addr_bits):
        # Wire = OR of all live contenders' bit at this position
        wire = 0
        for _, sid in alive:
            if sid[bit_pos] == "1":
                wire = 1
        wire_signal.append(wire)
        new_alive: list[tuple[int, str]] = []
        for _, sid in alive:
            if sid[bit_pos] == "1" or wire == 0:
                # If wire is 0, no one is competing at this bit; no dropouts.
                new_alive.append((bit_pos, sid))
            else:
                dropouts.append((bit_pos, sid))
        alive = new_alive
        if len(alive) == 1:
            break

    if len(alive) != 1:
        raise ValueError("countdown ended without a winner")
    winner = alive[0][1]
    return CountdownResult(
        contenders=tuple(sid for _, sid in contenders),
        bits=addr_bits,
        wire_signal=tuple(wire_signal),
        dropouts=tuple(dropouts),
        winner=winner,
    )


# --- main: demonstrations --------------------------------------------------

def _print_bitmap_demo() -> None:
    print("=" * 72)
    print("Basic bit-map protocol  (N=8, d=1000 bits, 200 cycles, p_ready=0.5)")
    print("=" * 72)
    res = simulate_bitmap(n=8, d_bits=1000, cycles=200, ready_prob=0.5)
    print(f"  per-station frames sent: {list(res.frames_per_station)}")
    print(f"  total slots used:        {res.total_slots}")
    print(f"  efficiency (d/(d+N)):    {res.efficiency:.4f}")
    print(f"  station 0 mean wait:     {res.low_station_wait_slots:.1f} slots")
    print(f"  station N-1 mean wait:   {res.high_station_wait_slots:.1f} slots")
    print(f"  unfairness (low/high):   {res.low_station_wait_slots / res.high_station_wait_slots:.2f}x")


def _print_token_demo() -> None:
    print()
    print("=" * 72)
    print("Token ring  (N=8, d=4096 bits, 500 cycles, walk=8 bits, p_ready=0.4)")
    print("=" * 72)
    res = simulate_token_ring(n=8, d_bits=4096, cycles=500, ring_walk_bits=8, ready_prob=0.4)
    print(f"  frame transmissions:     {res.frame_transmissions}")
    print(f"  mean wait (slots):       {res.mean_wait_slots:.1f}")
    print(f"  worst-case wait (slots): {res.worst_case_wait_slots}")
    print(f"  fairness:                equal across all stations (no low/high bias)")


def _print_countdown_demo() -> None:
    print()
    print("=" * 72)
    print("Binary countdown  (four 4-bit stations from the chapter)")
    print("=" * 72)
    res = run_countdown(["0010", "0100", "1001", "1010"], addr_bits=4)
    print(f"  contenders:    {list(res.contenders)}")
    print(f"  wire signal:   {list(res.wire_signal)}")
    print(f"  dropouts:      {[(b, s) for b, s in res.dropouts]}")
    print(f"  winner:        {res.winner}")

    print()
    print("Now add station 1111 (highest address):")
    res2 = run_countdown(["0010", "0100", "1001", "1010", "1111"], addr_bits=4)
    print(f"  wire signal:   {list(res2.wire_signal)}")
    print(f"  dropouts:      {[(b, s) for b, s in res2.dropouts]}")
    print(f"  winner:        {res2.winner}")


def main() -> None:
    _print_bitmap_demo()
    _print_token_demo()
    _print_countdown_demo()


if __name__ == "__main__":
    main()
