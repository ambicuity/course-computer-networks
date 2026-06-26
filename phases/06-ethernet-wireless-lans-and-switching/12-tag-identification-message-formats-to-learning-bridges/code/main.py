"""Tag Identification Message Formats to Learning Bridges.

Three runnable demonstrations, stdlib only:

1. EPC Gen 2 *Query* command codec -- pack/unpack the 22-bit reader-to-tag
   message (Command, DR, M, TR, Sel, Session, Target, Q, CRC-5) and verify
   the CRC-5 (poly x^5 + x^3 + 1, used by EPC Gen 2).
2. Slotted-ALOHA inventory simulator -- given N tags and a Q value, count
   empty / single / collision slots and report read efficiency, showing why
   the reader must tune Q (its binary-exponential-backoff analog).
3. Learning-bridge simulator -- backward learning on source MACs, the
   discard / forward / flood three-case rule, and aging.

Run: python3 main.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

# --------------------------------------------------------------------------
# 1. EPC Gen 2 Query command codec
# --------------------------------------------------------------------------

# (name, width-in-bits) in transmission order. Sum of widths = 22.
QUERY_FIELDS: list[tuple[str, int]] = [
    ("Command", 4),  # 1000 = Query
    ("DR", 1),       # divide ratio
    ("M", 2),        # cycles per symbol
    ("TR", 1),       # pilot tone
    ("Sel", 2),      # tag selection
    ("Session", 2),  # S0..S3
    ("Target", 1),   # A or B
    ("Q", 4),        # slot exponent -> 2^Q slots
    ("CRC", 5),      # CRC-5
]

QUERY_COMMAND_CODE = 0b1000
CRC5_POLY = 0b101001  # x^5 + x^3 + 1 -> 6-bit divisor (degree 5)


def crc5(payload_bits: str) -> int:
    """Compute a 5-bit CRC over a string of '0'/'1' bits.

    Standard shift-register long division by CRC5_POLY (degree 5),
    initialised to zero remainder. Returns an int in range 0..31.
    """
    reg = 0
    for bit in payload_bits:
        reg = (reg << 1) | int(bit)
        if reg & 0b100000:  # bit 5 set -> reduce by polynomial
            reg ^= CRC5_POLY
    return reg & 0b11111


def pack_query(dr: int, m: int, tr: int, sel: int,
               session: int, target: int, q: int) -> str:
    """Build the 22-bit Query message as a '0'/'1' string, CRC included."""
    parts: dict[str, int] = {
        "Command": QUERY_COMMAND_CODE, "DR": dr, "M": m, "TR": tr,
        "Sel": sel, "Session": session, "Target": target, "Q": q,
    }
    payload = ""
    for name, width in QUERY_FIELDS:
        if name == "CRC":
            continue
        value = parts[name]
        if value >= (1 << width):
            raise ValueError(f"{name}={value} does not fit in {width} bits")
        payload += format(value, f"0{width}b")
    return payload + format(crc5(payload), "05b")


def parse_query(bits: str) -> dict[str, int]:
    """Decode a 22-bit Query string into its named fields."""
    if len(bits) != 22:
        raise ValueError(f"Query must be 22 bits, got {len(bits)}")
    out: dict[str, int] = {}
    pos = 0
    for name, width in QUERY_FIELDS:
        out[name] = int(bits[pos:pos + width], 2)
        pos += width
    out["_crc_ok"] = int(crc5(bits[:17]) == out["CRC"])
    out["_slots"] = 1 << out["Q"]
    return out


# --------------------------------------------------------------------------
# 2. Slotted-ALOHA RFID inventory simulator
# --------------------------------------------------------------------------

@dataclass
class InventoryResult:
    q: int
    n_tags: int
    slots: int
    empty: int
    single: int
    collision: int

    @property
    def efficiency(self) -> float:
        """Fraction of slots that yielded exactly one successful tag read."""
        return self.single / self.slots if self.slots else 0.0


def run_inventory(n_tags: int, q: int, rng: random.Random) -> InventoryResult:
    """Simulate one inventory round: each tag picks a slot in 0..2^Q-1."""
    slots = 1 << q
    counts = [0] * slots
    for _ in range(n_tags):
        counts[rng.randrange(slots)] += 1
    empty = sum(1 for c in counts if c == 0)
    single = sum(1 for c in counts if c == 1)
    collision = sum(1 for c in counts if c >= 2)
    return InventoryResult(q, n_tags, slots, empty, single, collision)


def best_q_for(n_tags: int, rng: random.Random) -> int:
    """Sweep Q and return the one giving the best reads-per-slot efficiency.

    Real readers target roughly one tag per slot (Q ~ log2(N)). We score by
    the fraction of slots that are single-reply, so very large Q -- which
    reads almost everyone but wastes thousands of empty slots -- is penalised.
    """
    best_q, best_eff = 0, -1.0
    for q in range(0, 12):
        # average a few rounds to smooth randomness
        eff = sum(run_inventory(n_tags, q, rng).efficiency
                  for _ in range(8)) / 8
        if eff > best_eff:
            best_eff, best_q = eff, q
    return best_q


# --------------------------------------------------------------------------
# 3. Learning-bridge simulator (IEEE 802.1D backward learning)
# --------------------------------------------------------------------------

@dataclass
class Entry:
    port: int
    last_seen: float


@dataclass
class LearningBridge:
    ports: list[int]
    aging_seconds: float = 300.0
    table: dict[str, Entry] = field(default_factory=dict)

    def _learn(self, src_mac: str, in_port: int, now: float) -> bool:
        """Backward learning: record/refresh source MAC -> ingress port."""
        prev = self.table.get(src_mac)
        moved = prev is not None and prev.port != in_port
        self.table[src_mac] = Entry(in_port, now)
        return prev is None or moved  # True == new learn or a MAC move

    def age(self, now: float) -> list[str]:
        """Purge entries older than the aging time. Returns purged MACs."""
        purged = [mac for mac, e in self.table.items()
                  if now - e.last_seen > self.aging_seconds]
        for mac in purged:
            del self.table[mac]
        return purged

    def forward(self, src_mac: str, dst_mac: str, in_port: int,
                now: float) -> tuple[str, list[int]]:
        """Apply the three-case rule. Returns (action, output_ports)."""
        learned = self._learn(src_mac, in_port, now)
        tag = " [learned]" if learned else ""
        entry = self.table.get(dst_mac)
        if entry is None:
            outs = [p for p in self.ports if p != in_port]
            return f"FLOOD (dst {dst_mac} unknown){tag}", outs
        if entry.port == in_port:
            return f"DISCARD (dst already on port {in_port}){tag}", []
        return f"FORWARD to port {entry.port}{tag}", [entry.port]


# --------------------------------------------------------------------------
# Demonstrations
# --------------------------------------------------------------------------

def demo_query_codec() -> None:
    print("=" * 64)
    print("1. EPC Gen 2 Query command codec (22-bit reader-to-tag message)")
    print("=" * 64)
    bits = pack_query(dr=0, m=1, tr=0, sel=0, session=0, target=0, q=4)
    print(f"Packed bits ({len(bits)} bits): {bits}")
    fields = parse_query(bits)
    pos = 0
    for name, width in QUERY_FIELDS:
        chunk = bits[pos:pos + width]
        pos += width
        print(f"  {name:<8} {width}b  {chunk:<5} = {fields[name]}")
    print(f"  CRC-5 valid: {bool(fields['_crc_ok'])}")
    print(f"  Q={fields['Q']} -> tags randomise over 2^{fields['Q']} "
          f"= {fields['_slots']} slots (0..{fields['_slots'] - 1})")


def demo_inventory() -> None:
    print("\n" + "=" * 64)
    print("2. Slotted-ALOHA inventory: tuning Q for the tag population")
    print("=" * 64)
    rng = random.Random(42)
    n = 200
    print(f"Population: {n} tags. Per-slot outcomes at several Q values:\n")
    print(f"{'Q':>2} {'slots':>6} {'empty':>6} {'single':>7} "
          f"{'collide':>8} {'efficiency':>11}")
    for q in (2, 4, 6, 7, 8, 10):
        r = run_inventory(n, q, rng)
        print(f"{r.q:>2} {r.slots:>6} {r.empty:>6} {r.single:>7} "
              f"{r.collision:>8} {r.efficiency:>10.1%}")
    bq = best_q_for(n, rng)
    print(f"\nReader's QAdjust target for {n} tags: Q={bq} "
          f"(2^{bq}={1 << bq} slots maximises single-reply reads).")
    print("Q too low -> collisions dominate; Q too high -> empty slots waste time.")


def demo_bridge() -> None:
    print("\n" + "=" * 64)
    print("3. Learning bridge: backward learning + discard/forward/flood")
    print("=" * 64)
    b1 = LearningBridge(ports=[1, 2, 3, 4], aging_seconds=300.0)
    # (src, dst, ingress_port, time_seconds)
    traffic = [
        ("A", "D", 1, 0.0),   # A unknown dst -> learn A on 1, flood
        ("C", "A", 3, 1.0),   # learn C on 3, A now known -> forward to 1
        ("D", "C", 4, 2.0),   # learn D on 4, C known -> forward to 3
        ("A", "D", 1, 3.0),   # D now known -> forward to 4
        ("B", "A", 1, 4.0),   # B on same port as A (hub) -> forward to 1
    ]
    for src, dst, port, t in traffic:
        action, outs = b1.forward(src, dst, port, t)
        out_s = ",".join(map(str, outs)) if outs else "-"
        print(f"t={t:>4}s  {src}->{dst:<2} in:p{port}  =>  {action:<40} "
              f"out:[{out_s}]")
    print("\nForwarding table:")
    for mac, e in sorted(b1.table.items()):
        print(f"  {mac} -> port {e.port}  (last seen t={e.last_seen}s)")
    print("\nAge the table at t=400s (aging=300s):")
    purged = b1.age(400.0)
    print(f"  purged (silent > 300s): {purged or 'none'}")
    print("  -> frames to a purged MAC will be FLOODED until it speaks again.")


def main() -> None:
    demo_query_codec()
    demo_inventory()
    demo_bridge()


if __name__ == "__main__":
    main()
