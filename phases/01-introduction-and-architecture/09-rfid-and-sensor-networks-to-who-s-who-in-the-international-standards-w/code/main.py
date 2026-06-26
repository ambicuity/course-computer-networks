#!/usr/bin/env python3
"""RFID Gen2 singulation simulator + standards-body classifier.

Two self-contained, stdlib-only demonstrations for the lesson
"RFID and Sensor Networks to Who's Who in the International Standards World":

1. ``simulate_round`` / ``sweep_q`` model EPC Gen2 (ISO/IEC 18000-63)
   frame-slotted-ALOHA anti-collision. Each of ``2**Q`` slots is empty,
   a singleton (one tag -> read succeeds), or a collision (>=2 tags). We
   compare the Monte-Carlo result against the closed-form expected number
   of singletons, ``n * (1 - 1/L)**(n-1)`` with ``L = 2**Q``, and show why
   an undersized Q collapses the read rate for a large tag population.

2. ``classify_standard`` maps a standard identifier (e.g. "RFC 9293",
   "ISO/IEC 18000-63", "IEEE 802.15.4", "H.264") to the body that owns it
   and whether it is de jure or de facto.

Run: ``python3 main.py``  (no arguments, no dependencies, no network).
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

# --- Part 1: EPC Gen2 frame-slotted-ALOHA singulation ----------------------

NUM_TAGS = 60  # tags energized in the reader field at once (the warehouse case)


@dataclass(frozen=True)
class RoundResult:
    q: int
    slots: int
    empty: int
    singletons: int  # tags successfully singulated this round
    collisions: int  # slots with >=2 tags

    @property
    def collision_slots(self) -> int:
        return self.slots - self.empty - self.singletons


def simulate_round(num_tags: int, q: int, rng: random.Random) -> RoundResult:
    """Simulate one Gen2 inventory round with 2**q slots and num_tags tags.

    Each tag loads a random slot counter in [0, 2**q - 1]. A slot with
    exactly one tag is a successful read; a slot with two or more is a
    collision (no ACK, tags re-roll on a later round).
    """
    slots = 1 << q  # 2**q
    counts = [0] * slots
    for _ in range(num_tags):
        counts[rng.randrange(slots)] += 1

    empty = sum(1 for c in counts if c == 0)
    singletons = sum(1 for c in counts if c == 1)
    collisions = sum(1 for c in counts if c >= 2)
    return RoundResult(q=q, slots=slots, empty=empty,
                       singletons=singletons, collisions=collisions)


def expected_singletons(num_tags: int, q: int) -> float:
    """Closed form: n * (1 - 1/L)**(n-1) with L = 2**q slots."""
    load = 1 << q
    if num_tags == 0:
        return 0.0
    return num_tags * (1 - 1 / load) ** (num_tags - 1)


def sweep_q(num_tags: int, q_values: range, trials: int = 400) -> None:
    """Average singletons-per-round over many trials for each Q."""
    rng = random.Random(20240621)
    print(f"  Gen2 singulation: {num_tags} tags in one reader field")
    print("  Q   slots   sim singletons/round   theory   efficiency")
    print("  --  ------  --------------------   ------   ----------")
    for q in q_values:
        total = 0
        for _ in range(trials):
            total += simulate_round(num_tags, q, rng).singletons
        sim = total / trials
        theory = expected_singletons(num_tags, q)
        efficiency = sim / (1 << q)  # successful reads per slot
        print(f"  {q:<2}  {1 << q:<6}  {sim:>18.2f}   {theory:>6.2f}   "
              f"{efficiency:>6.1%}")


def best_q(num_tags: int, q_values: range) -> int:
    """Q that maximizes expected reads-per-slot efficiency."""
    return max(q_values, key=lambda q: expected_singletons(num_tags, q) / (1 << q))


# --- Part 2: standards-body classifier -------------------------------------

@dataclass(frozen=True)
class Standard:
    body: str
    kind: str  # "de jure" or "de facto"
    note: str


# Ordered rules: first matching pattern wins.
_RULES: list[tuple[re.Pattern[str], Standard]] = [
    (re.compile(r"^RFC\s*\d+$", re.I),
     Standard("IETF (under IAB / ISOC)", "de jure",
              "Internet-Draft -> RFC; 'rough consensus and running code'")),
    (re.compile(r"^ISO/IEC\s*\d+", re.I),
     Standard("ISO + IEC (JTC1)", "de jure",
              "CD -> DIS -> IS; JTC1 covers information technology")),
    (re.compile(r"^ISO\s*\d+", re.I),
     Standard("ISO", "de jure", "International Organization for Standardization")),
    (re.compile(r"^IEEE\s*802", re.I),
     Standard("IEEE 802 LAN/MAN Committee", "de jure",
              "Working-group draft -> standard; e.g. 802.3, 802.11, 802.15")),
    (re.compile(r"^802\.", re.I),
     Standard("IEEE 802 LAN/MAN Committee", "de jure",
              "Working-group draft -> standard")),
    (re.compile(r"^[HX]\.\d+$", re.I),
     Standard("ITU-T (was CCITT)", "de jure",
              "Recommendation adopted by member governments")),
    (re.compile(r"^(HTTP|Bluetooth)$", re.I),
     Standard("(originated by usage)", "de facto",
              "Adopted by usage; later ratified de jure (HTTP->IETF)")),
]


def classify_standard(identifier: str) -> Standard:
    """Map a standard identifier to its owning body and de facto/de jure type."""
    ident = identifier.strip()
    for pattern, std in _RULES:
        if pattern.match(ident):
            return std
    return Standard("unknown", "unknown", "no rule matched")


def print_classifications(identifiers: list[str]) -> None:
    print("  identifier           body                              type")
    print("  -------------------  --------------------------------  --------")
    for ident in identifiers:
        std = classify_standard(ident)
        print(f"  {ident:<19}  {std.body:<32}  {std.kind}")
        print(f"      -> {std.note}")


# --- Demonstration ---------------------------------------------------------

def main() -> None:
    print("=" * 68)
    print("PART 1  EPC Gen2 (ISO/IEC 18000-63) slotted-ALOHA singulation")
    print("=" * 68)
    sweep_q(NUM_TAGS, range(2, 9))
    chosen = best_q(NUM_TAGS, range(2, 11))
    print(f"\n  Most efficient Q for {NUM_TAGS} tags (reads/slot): Q = {chosen} "
          f"({1 << chosen} slots)")
    print("  Note: Q=4 (16 slots) collapses for 60 tags -- almost every slot")
    print("  collides. The Gen2 Q-adjust loop grows Q after collisions.")

    print()
    print("=" * 68)
    print("PART 2  Who owns which standard?  (de facto vs de jure)")
    print("=" * 68)
    print_classifications([
        "ISO/IEC 18000-63",  # UHF Gen2 RFID air interface
        "IEEE 802.15.4",     # sensor-mesh PHY/MAC (ZigBee/6LoWPAN)
        "RFC 9293",          # TCP
        "RFC 4944",          # IPv6 over 802.15.4 (6LoWPAN)
        "H.264",             # ITU-T video, also ISO/IEC MPEG-4 AVC
        "X.509",             # ITU-T PKI certificates
        "802.3",             # Ethernet
        "Bluetooth",         # de facto, originated at Ericsson
        "HTTP",              # de facto, later adopted by IETF
    ])


if __name__ == "__main__":
    main()
