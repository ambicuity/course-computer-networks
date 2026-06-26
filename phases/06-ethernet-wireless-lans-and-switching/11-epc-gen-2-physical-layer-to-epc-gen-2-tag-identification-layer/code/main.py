"""EPC Gen 2 UHF Class-1 tag identification: Query frame codec + slotted-ALOHA round simulator.

This module models the two layers of the EPC Gen 2 air interface (Tanenbaum,
Computer Networks, Sec. 4.7):

  * Physical / framing layer  -> build and decode the 22-bit `Query` command,
    including its 4-bit Command (1000), the Q field, and a CRC-5.
  * Tag identification layer   -> a slotted-ALOHA inventory round where each tag
    draws a random slot in [0, 2^Q - 1], the reader resolves singleton slots via
    the RN16 -> ACK -> EPC handshake, and `QAdjust` tunes Q like Ethernet's
    binary exponential backoff.

Stdlib only. Run:  python3 main.py
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# Query frame: field widths in transmission order (Tanenbaum Fig. 4-40).
# ---------------------------------------------------------------------------
QUERY_COMMAND = 0b1000          # 4-bit code identifying a Query
CRC5_POLY = 0b101001            # CRC-5 generator (x^5 + x^3 + 1), 6-bit form

# (field name, bit width); CRC-5 is appended separately.
QUERY_FIELDS: Tuple[Tuple[str, int], ...] = (
    ("Command", 4),   # 1000 = Query
    ("DR", 1),        # divide ratio (link frequency)
    ("M", 2),         # cycles/symbol: FM0 / Miller-2/4/8
    ("TR", 1),        # pilot tone (TRext)
    ("Sel", 2),       # tag selection by SL flag
    ("Session", 2),   # S0..S3
    ("Target", 1),    # inventoried flag A or B
    ("Q", 4),         # slot-count exponent: slots = 2^Q
)


def crc5(bits: int, width: int) -> int:
    """Compute a 5-bit CRC over `width` bits of `bits` (MSB first)."""
    reg = bits << 5  # append 5 zero bits
    total = width + 5
    poly_top = 1 << 5
    for i in range(total - 1, 4, -1):
        if reg & (1 << i):
            reg ^= CRC5_POLY << (i - 5)
    return reg & 0b11111


@dataclass(frozen=True)
class Query:
    """A decoded EPC Gen 2 Query command."""

    dr: int = 0
    m: int = 1
    tr: int = 0
    sel: int = 0
    session: int = 0
    target: int = 0
    q: int = 4

    def slot_count(self) -> int:
        return 1 << self.q  # 2^Q


def build_query(query: Query) -> Tuple[int, int]:
    """Pack a Query into its 17 payload bits plus a 5-bit CRC.

    Returns (payload_bits, total_width) where total_width includes the CRC.
    """
    values = {
        "Command": QUERY_COMMAND,
        "DR": query.dr,
        "M": query.m,
        "TR": query.tr,
        "Sel": query.sel,
        "Session": query.session,
        "Target": query.target,
        "Q": query.q,
    }
    payload = 0
    payload_width = 0
    for name, width in QUERY_FIELDS:
        value = values[name]
        if value >= (1 << width):
            raise ValueError(f"{name}={value} does not fit in {width} bits")
        payload = (payload << width) | value
        payload_width += width
    crc = crc5(payload, payload_width)
    frame = (payload << 5) | crc
    return frame, payload_width + 5


def decode_query(frame: int, total_width: int) -> Query:
    """Decode a Query frame, validating the Command code and CRC-5."""
    crc = frame & 0b11111
    payload = frame >> 5
    payload_width = total_width - 5
    if crc5(payload, payload_width) != crc:
        raise ValueError("CRC-5 check failed (corrupted Query)")
    fields: Dict[str, int] = {}
    remaining = payload
    # Unpack from the least-significant field backwards.
    for name, width in reversed(QUERY_FIELDS):
        fields[name] = remaining & ((1 << width) - 1)
        remaining >>= width
    if fields["Command"] != QUERY_COMMAND:
        raise ValueError(f"not a Query: Command={fields['Command']:04b}")
    return Query(
        dr=fields["DR"], m=fields["M"], tr=fields["TR"], sel=fields["Sel"],
        session=fields["Session"], target=fields["Target"], q=fields["Q"],
    )


# ---------------------------------------------------------------------------
# Tag identification layer: slotted-ALOHA inventory round.
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class RoundResult:
    q: int
    num_tags: int
    empty: int
    single: int      # singleton slots -> successful RN16/ACK/EPC handshakes
    collision: int

    @property
    def slots(self) -> int:
        return 1 << self.q

    @property
    def utilization(self) -> float:
        return self.single / self.slots if self.slots else 0.0


def simulate_round(num_tags: int, q: int, seed: int | None = None) -> RoundResult:
    """One inventory round: each tag picks a random slot in [0, 2^Q - 1].

    A slot with exactly one tag is a success (clean RN16 -> ACK -> EPC).
    A slot with >= 2 tags is a collision; empty slots carry only the carrier.
    """
    rng = random.Random(seed)
    slots = 1 << q
    chosen = Counter(rng.randrange(slots) for _ in range(num_tags))
    occupancy = Counter(chosen.values())  # tags-in-slot -> how many such slots
    single = occupancy.get(1, 0)
    collision = sum(count for tags, count in occupancy.items() if tags >= 2)
    empty = slots - single - collision
    return RoundResult(q=q, num_tags=num_tags, empty=empty,
                       single=single, collision=collision)


def sweep_q(num_tags: int, q_lo: int = 0, q_hi: int = 12,
            trials: int = 200) -> List[Tuple[int, float]]:
    """Average singleton-slot count over `trials` rounds for each Q; pick the best."""
    results: List[Tuple[int, float]] = []
    for q in range(q_lo, q_hi + 1):
        total_single = sum(
            simulate_round(num_tags, q, seed=s).single for s in range(trials)
        )
        results.append((q, total_single / trials))
    return results


def recommend_q(num_tags: int) -> int:
    """Best Q: smallest exponent with 2^Q >= num_tags (target ~1 tag/slot)."""
    q = 0
    while (1 << q) < num_tags:
        q += 1
    return q


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------
def _print_round(label: str, r: RoundResult) -> None:
    print(f"  {label}: Q={r.q} ({r.slots} slots), {r.num_tags} tags -> "
          f"empty={r.empty}, single={r.single}, collision={r.collision}, "
          f"util={r.utilization:.0%}")


def main() -> None:
    print("=== EPC Gen 2 Query frame codec ===")
    q_cmd = Query(dr=1, m=1, tr=0, sel=0, session=1, target=0, q=4)
    frame, width = build_query(q_cmd)
    print(f"  Query(session=S1, Q=4) -> {width}-bit frame 0x{frame:06X} "
          f"= {frame:0{width}b}")
    decoded = decode_query(frame, width)
    print(f"  decoded back: session=S{decoded.session}, Q={decoded.q}, "
          f"slots={decoded.slot_count()}  (round-trip OK)")
    try:
        decode_query(frame ^ 0b1000, width)  # flip a payload bit
    except ValueError as exc:
        print(f"  corrupted frame correctly rejected: {exc}")

    print("\n=== Healthy round: 10 tags, Q=4 (Tanenbaum problem 34) ===")
    _print_round("round", simulate_round(num_tags=10, q=4, seed=7))
    print(f"  recommend_q(10) = {recommend_q(10)}  (2^4 = 16 >= 10)")

    print("\n=== Warehouse collapse: 300 tags stuck at Q=4 ===")
    bad = simulate_round(num_tags=300, q=4, seed=7)
    _print_round("collapse", bad)
    print(f"  nearly every one of {bad.slots} slots collides -> "
          f"only {bad.single} tags identified this round")

    print("\n=== Recovery: sweep Q for 300 tags (avg singleton slots) ===")
    sweep = sweep_q(num_tags=300, q_lo=4, q_hi=11, trials=300)
    best_q, best_single = max(sweep, key=lambda t: t[1])
    for q, avg in sweep:
        marker = "  <- best" if q == best_q else ""
        print(f"    Q={q:2d} ({1 << q:5d} slots): "
              f"~{avg:6.1f} tags identified/round{marker}")
    print(f"  recommend_q(300) = {recommend_q(300)} "
          f"(2^{recommend_q(300)} = {1 << recommend_q(300)} >= 300); "
          f"sweep peak at Q={best_q}")


if __name__ == "__main__":
    main()
