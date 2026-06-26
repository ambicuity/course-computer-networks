#!/usr/bin/env python3
"""Bluetooth baseband + EPC Gen 2 inventory simulator (stdlib only).

Three self-contained models tied to the lesson:

1. bluetooth_capacity()  -- compute piconet TDM capacity and the 13%
   basic-rate SCO efficiency breakdown (settling / header / repetition).
2. BluetoothHeader        -- pack the 18-bit baseband header, apply 3x
   repetition coding, inject bit errors, recover by majority vote.
3. run_inventory()        -- EPC Gen 2 slotted-ALOHA tag inventory with the
   Query -> RN16 -> Ack -> EPC handshake and QAdjust (binary-exponential-
   backoff-style) tuning of the slot count.

Run:  python3 main.py
No network calls, no third-party packages.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Bluetooth constants (Tanenbaum 5e, sec 4.6.5 / 4.6.6)
# ---------------------------------------------------------------------------
SLOT_US = 625.0          # one Bluetooth time slot, microseconds
HOPS_PER_SEC = 1600      # frequency hops per second (one per slot)
SETTLING_US = 255.0      # mid-point of the 250-260 us per-hop settling time
SLOTS_PER_SEC_PER_DIR = 800   # slave uses only odd slots -> 800 slots/s
SCO_PAYLOAD_BITS = 80    # most robust SCO variant: 80-bit payload, 3x repeated


# ---------------------------------------------------------------------------
# Part 1: piconet capacity
# ---------------------------------------------------------------------------
def bluetooth_capacity() -> dict[str, float]:
    """Reproduce the 64 kbps SCO voice channel and 13% efficiency split."""
    capacity_bps = SLOTS_PER_SEC_PER_DIR * SCO_PAYLOAD_BITS  # per direction

    # Efficiency components for the basic-rate 80-bit SCO frame.
    settling_frac = SETTLING_US / SLOT_US           # ~0.41 lost to settling
    header_frac = 0.20                              # access code + header
    repetition_frac = 0.26                          # 80 bits sent 3x -> 240
    payload_frac = 1.0 - settling_frac - header_frac - repetition_frac

    return {
        "capacity_bps_per_dir": capacity_bps,
        "settling_frac": settling_frac,
        "header_frac": header_frac,
        "repetition_frac": repetition_frac,
        "payload_efficiency": payload_frac,
    }


def multislot_throughput(payload_bits: int, n_slots: int) -> float:
    """Effective throughput of an n-slot frame: one settling gap amortized."""
    frame_us = n_slots * SLOT_US
    useful_us = frame_us - SETTLING_US
    if useful_us <= 0:
        return 0.0
    # bits delivered per frame / frame duration -> bits per second.
    return payload_bits / (frame_us / 1_000_000.0)


# ---------------------------------------------------------------------------
# Part 2: 18-bit baseband header with 3x repetition coding
# ---------------------------------------------------------------------------
@dataclass
class BluetoothHeader:
    """The 18-bit logical Bluetooth baseband header (sec 4.6.6)."""

    addr: int   # 3 bits: active member address (1-7)
    type_: int  # 4 bits: ACL/SCO/poll/null + FEC + slot count
    flow: int   # 1 bit:  buffer-full flow control
    arqn: int   # 1 bit:  piggybacked ACK
    seqn: int   # 1 bit:  stop-and-wait sequence bit
    hec: int    # 8 bits: header error check

    def to_bits(self) -> list[int]:
        fields = [
            (self.addr, 3),
            (self.type_, 4),
            (self.flow, 1),
            (self.arqn, 1),
            (self.seqn, 1),
            (self.hec, 8),
        ]
        bits: list[int] = []
        for value, width in fields:
            for i in reversed(range(width)):
                bits.append((value >> i) & 1)
        assert len(bits) == 18, "logical header must be 18 bits"
        return bits


def repetition_encode(bits: list[int]) -> list[int]:
    """Send each bit three times -> 54-bit transmitted header."""
    out: list[int] = []
    for b in bits:
        out.extend([b, b, b])
    return out


def flip_bits(coded: list[int], positions: list[int]) -> list[int]:
    """Flip the given transmitted-bit positions to simulate radio noise."""
    noisy = list(coded)
    for p in positions:
        if 0 <= p < len(noisy):
            noisy[p] ^= 1
    return noisy


def majority_decode(coded: list[int]) -> list[int]:
    """Recover 18 bits by majority vote over each group of three copies."""
    recovered: list[int] = []
    for i in range(0, len(coded), 3):
        triple = coded[i : i + 3]
        recovered.append(1 if sum(triple) >= 2 else 0)
    return recovered


# ---------------------------------------------------------------------------
# Part 3: EPC Gen 2 slotted-ALOHA inventory (sec 4.7.3 / 4.7.4)
# ---------------------------------------------------------------------------
@dataclass
class RoundStats:
    q: int
    slots: int
    idle: int
    single: int
    collision: int
    identified: int


def _run_round(q: int, tag_ids: list[int],
               rng: random.Random) -> tuple[RoundStats, list[int]]:
    """One inventory round: each unread tag picks a slot in [0, 2^q)."""
    n_slots = 1 << q
    buckets: dict[int, list[int]] = {}
    for tag in tag_ids:
        slot = rng.randrange(n_slots)
        buckets.setdefault(slot, []).append(tag)

    idle = single = collision = 0
    identified: list[int] = []
    for slot in range(n_slots):
        occupants = buckets.get(slot, [])
        if not occupants:
            idle += 1
        elif len(occupants) == 1:
            # Query/QRepeat -> RN16 with no collision -> Ack -> EPC sent.
            single += 1
            identified.append(occupants[0])
        else:
            collision += 1  # RN16s collide; reader hears garbage, no Ack
    return RoundStats(q, n_slots, idle, single, collision, len(identified)), identified


def adjust_q(q: int, stats: RoundStats) -> int:
    """QAdjust feedback: too many collisions -> grow Q; too idle -> shrink."""
    if stats.collision > stats.idle and q < 15:
        return q + 1
    if stats.idle > 2 * stats.collision and q > 0:
        return q - 1
    return q


def run_inventory(num_tags: int, start_q: int, adaptive: bool,
                  seed: int = 42) -> tuple[int, int, list[RoundStats]]:
    """Inventory all tags. Returns (total_slots, rounds, per-round stats)."""
    rng = random.Random(seed)
    remaining = list(range(num_tags))
    q = start_q
    total_slots = 0
    history: list[RoundStats] = []
    rounds = 0
    while remaining and rounds < 200:
        stats, identified = _run_round(q, remaining, rng)
        total_slots += stats.slots
        history.append(stats)
        for tag in identified:
            remaining.remove(tag)
        rounds += 1
        if adaptive:
            q = adjust_q(q, stats)
    return total_slots, rounds, history


def aloha_throughput(num_contenders: int, q: int) -> float:
    """Expected fraction of slots that succeed: G*e^-G with G = n / 2^q."""
    g = num_contenders / (1 << q)
    return g * math.exp(-g)


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 64)
    print("PART 1  Bluetooth piconet capacity (basic-rate SCO)")
    print("=" * 64)
    cap = bluetooth_capacity()
    print(f"  slots/sec per direction : {SLOTS_PER_SEC_PER_DIR}")
    print(f"  SCO payload per slot     : {SCO_PAYLOAD_BITS} bits")
    print(f"  channel capacity/dir     : {cap['capacity_bps_per_dir']:,.0f} bps "
          f"(= one full-duplex 64 kbps PCM voice channel)")
    print(f"  settling overhead        : {cap['settling_frac']:.0%}")
    print(f"  header overhead          : {cap['header_frac']:.0%}")
    print(f"  repetition overhead      : {cap['repetition_frac']:.0%}")
    print(f"  net payload efficiency   : {cap['payload_efficiency']:.0%}")
    one = multislot_throughput(SCO_PAYLOAD_BITS, 1)
    five = multislot_throughput(2744, 5)
    print(f"  1-slot frame throughput  : {one:,.0f} bps")
    print(f"  5-slot frame throughput  : {five:,.0f} bps  (overhead amortized)")

    print()
    print("=" * 64)
    print("PART 2  18-bit header with 3x repetition + majority decode")
    print("=" * 64)
    hdr = BluetoothHeader(addr=5, type_=0b0011, flow=1, arqn=1, seqn=0, hec=0xA5)
    logical = hdr.to_bits()
    coded = repetition_encode(logical)
    print(f"  logical header (18 bits) : {''.join(map(str, logical))}")
    print(f"  transmitted (54 bits)    : {''.join(map(str, coded))}")

    # Recoverable: each flip lands on a different bit's single copy.
    spread = flip_bits(coded, [0, 9, 24])  # one copy in three separate triples
    rec_ok = majority_decode(spread)
    print(f"  3 spread flips -> decode  : {''.join(map(str, rec_ok))} "
          f"correct={rec_ok == logical}")

    # Unrecoverable: 2 of 3 copies of the same bit (the Addr MSB) corrupted.
    swamped = flip_bits(coded, [0, 1])
    rec_bad = majority_decode(swamped)
    print(f"  2 copies of bit 0 flipped : {''.join(map(str, rec_bad))} "
          f"correct={rec_bad == logical}  (majority loses one bit)")

    print()
    print("=" * 64)
    print("PART 3  EPC Gen 2 inventory: fixed Q vs adaptive QAdjust")
    print("=" * 64)
    tags = 40
    fixed_slots, fixed_rounds, fixed_hist = run_inventory(tags, start_q=4, adaptive=False)
    adapt_slots, adapt_rounds, adapt_hist = run_inventory(tags, start_q=4, adaptive=True)
    first = fixed_hist[0]
    print(f"  population                : {tags} tags")
    print(f"  fixed  Q=4 (16 slots)     : {fixed_slots} slots over {fixed_rounds} rounds")
    print(f"    round 1 outcome         : idle={first.idle} single={first.single} "
          f"collision={first.collision}  (overloaded: 40 tags / 16 slots)")
    print(f"  adaptive QAdjust          : {adapt_slots} slots over {adapt_rounds} rounds")
    print(f"  improvement               : {(1 - adapt_slots / fixed_slots):.0%} fewer slots")

    print()
    print("  Q-sweep, expected success fraction G*e^-G for 40 contenders:")
    best_q, best = 0, 0.0
    for q in range(2, 9):
        thru = aloha_throughput(tags, q)
        marker = ""
        if thru > best:
            best, best_q = thru, q
        print(f"    Q={q:>2}  2^Q={1 << q:>4} slots  success/slot={thru:.3f}")
    print(f"  peak near Q={best_q} (2^Q={1 << best_q} ~ {tags} tags), "
          f"matching slotted-ALOHA's 1/e = {1 / math.e:.3f} bound")


if __name__ == "__main__":
    main()
