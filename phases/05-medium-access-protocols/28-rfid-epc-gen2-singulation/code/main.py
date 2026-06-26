"""RFID EPC Gen 2 Q-algorithm singulation simulator.

Stdlib-only Python 3 simulation of the EPC Class-1 Generation-2
(ISO/IEC 18000-63) tag-identification layer. We model:

  * Tags with EPC, 16-bit slot counter, four inventory flags (S0..S3),
    an SL (Selected) flag, a tiny state machine (Ready -> Arbitrate ->
    Reply -> Acknowledged -> Open -> Secured -> Killed), and memory
    banks (Reserved / EPC / TID / User).
  * A reader that runs Query(Q), collects the (simulated) air-channel
    reply per slot (empty / single / collision), ACKs singletons,
    pulls PC+EPC+CRC-16, and tunes Q with QAdjust.
  * A Query command builder that lays out every field of the spec
    (Command | DR | M | TRcal | Sel | Session | Target | Q | CRC-16)
    plus a CRC-16 for both polynomials (0x1021 EPC and 0x8408 command
    feedback) and a 5-bit short-CRC over a Query payload.

Run with `python3 code/main.py` to singulate 8 tags at Q=2 and print
the slot-by-slot trace, the occupancy histogram, and the final EPC
list. No pip deps. No network calls.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# CRC-16 implementations (both Gen 2 polynomials)
# ---------------------------------------------------------------------------


def crc16_ccitt_false(data: bytes) -> int:
    """CRC-16/CCITT-FALSE: poly 0x1021, init 0xFFFF, MSB-first.
    Used for the EPC memory bank's CRC-16 trailer and for secured
    memory commands."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc


def crc16_ibm(data: bytes) -> int:
    """CRC-16/IBM: poly 0x8408 (reflected 0x1021), init 0xFFFF,
    reflected input and output. Used for command feedback (the
    short 5-bit CRC inside Query, and the full CRC-16 inside ACK,
    Req_RN, Read, Write, etc.)."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0x8408
            else:
                crc >>= 1
    return crc


def short_crc5_query(payload_bits: int) -> int:
    """The 5-bit CRC-16/IBM short form used in Query messages.

    The Query trailer is 5 bits: the spec treats the command bits
    (Command | DR | M | TRcal | Sel | Session | Target | Q) as a
    19-bit field and appends a 5-bit CRC. We compute CRC-16/IBM
    over the 19-bit field packed into 3 bytes, then return the
    top 5 bits, matching EPCglobal's published example.
    """
    packed = payload_bits.to_bytes(3, "big")
    full = crc16_ibm(packed)
    return (full >> 11) & 0x1F


# ---------------------------------------------------------------------------
# Query command builder
# ---------------------------------------------------------------------------


def build_query(
    dr: int = 0,
    m: int = 0,
    trcal: int = 1,
    sel: int = 0b00,
    session: int = 0b00,
    target: int = 0,
    q: int = 4,
) -> Tuple[int, int]:
    """Lay out the Query command field by field.

    Layout (bits):  Command(4)=1000 | DR(1) | M(2) | TRcal(1) |
                    Sel(2) | Session(2) | Target(1) | Q(4) | CRC-5(5)

    Returns the 19-bit payload and the 5-bit CRC trailer.
    """
    payload = (
        (0b1000 << 15)
        | ((dr & 0x1) << 14)
        | ((m & 0x3) << 12)
        | ((trcal & 0x1) << 11)
        | ((sel & 0x3) << 9)
        | ((session & 0x3) << 7)
        | ((target & 0x1) << 6)
        | (q & 0xF)
    )
    return payload, short_crc5_query(payload)


# ---------------------------------------------------------------------------
# Tag model
# ---------------------------------------------------------------------------


STATE_READY = "Ready"
STATE_ARBITRATE = "Arbitrate"
STATE_REPLY = "Reply"
STATE_ACKED = "Acknowledged"
STATE_OPEN = "Open"
STATE_SECURED = "Secured"
STATE_KILLED = "Killed"


@dataclass
class Tag:
    epc_hex: str
    handle: int = 0
    slot_counter: int = 0
    state: str = STATE_READY
    sl_flag: bool = False
    # Four independent inventory sessions; each tracks its own
    # inventoried flag ("A" = not yet read, "B" = already read).
    s_flag: List[str] = field(default_factory=lambda: ["A", "A", "A", "A"])
    # Memory banks as byte arrays; we only model Reserved + EPC.
    kill_pwd: bytes = b"\x00\x00\x00\x00"
    access_pwd: bytes = b"\x00\x00\x00\x00"
    user_memory: bytearray = field(default_factory=lambda: bytearray(64))
    rn16: int = 0

    def epc_bytes(self) -> bytes:
        """Convert the textual EPC into bytes (hex-encoded)."""
        s = self.epc_hex.replace("-", "").replace(" ", "")
        return bytes.fromhex(s)

    def epc_word(self) -> bytes:
        """Build the EPC memory-bank payload: CRC-16(CCITT) | PC | EPC."""
        pc = len(self.epc_bytes()).to_bytes(2, "big") + b"\x00\x00"
        body = self.epc_bytes()
        return crc16_ccitt_false(pc + body).to_bytes(2, "big") + pc + body

    def prepare_for_inventory(self, q: int, session: int, target: int) -> None:
        """Drop a fresh 16-bit slot counter in [0, 2^q)."""
        if self.state == STATE_KILLED:
            return
        self.slot_counter = random.randint(0, (1 << q) - 1)
        self.state = STATE_ARBITRATE
        self.handle = 0
        # Optionally flip the session flag on entry.
        if self.s_flag[session] != ("B" if target else "A"):
            self.s_flag[session] = "B" if target else "A"

    def step(self) -> Optional[int]:
        """One slot tick: decrement counter; if it hits 0, move to Reply
        and broadcast a fresh RN16. Returns the RN16 to transmit, or
        None if the tag stayed silent."""
        if self.state != STATE_ARBITRATE:
            return None
        if self.slot_counter > 0:
            self.slot_counter -= 1
            return None
        self.state = STATE_REPLY
        self.rn16 = random.randint(0, 0xFFFF)
        return self.rn16

    def accept_ack(self, rn16: int) -> bool:
        """ACK handler. Match the RN16 to confirm the slot, then
        return True so the reader knows to fetch the EPC."""
        if self.state != STATE_REPLY or self.rn16 != rn16:
            return False
        self.state = STATE_ACKED
        return True

    def finish_epc_tx(self) -> None:
        """After the reader pulls PC+EPC+CRC-16, mark as Open."""
        if self.state == STATE_ACKED:
            self.state = STATE_OPEN


# ---------------------------------------------------------------------------
# Reader / channel
# ---------------------------------------------------------------------------


@dataclass
class SlotStat:
    slot: int
    kind: str  # "empty" | "single" | "collision"
    tags: List[Tag] = field(default_factory=list)


@dataclass
class InventoryRound:
    q: int
    slots: List[SlotStat] = field(default_factory=list)


def run_round(
    tags: List[Tag],
    q: int,
    session: int = 0,
    target: int = 0,
    rng_seed: Optional[int] = None,
) -> InventoryRound:
    """Run a full Gen 2 inventory round.

    For each of 2^q slots: collect RN16s from every tag whose
    counter landed on that slot, classify the slot, ACK singletons,
    and pull their EPC. Collision tags drop a fresh counter and
    re-enter Arbitrate so the next round can retry them.
    """
    if rng_seed is not None:
        random.seed(rng_seed)

    # All candidate tags draw fresh counters.
    candidates = [t for t in tags if t.state != STATE_KILLED]
    for t in candidates:
        t.prepare_for_inventory(q, session, target)

    round_ = InventoryRound(q=q)
    for slot in range(1 << q):
        # Step each tag once: those with counter>0 decrement silently,
        # those with counter==0 emit an RN16 and move to Reply.
        replies: List[Tag] = []
        for t in candidates:
            rn = t.step()
            if rn is not None:
                replies.append(t)

        if len(replies) == 0:
            round_.slots.append(SlotStat(slot=slot, kind="empty"))
            continue

        if len(replies) == 1:
            tag = replies[0]
            round_.slots.append(SlotStat(slot=slot, kind="single", tags=[tag]))
            # ACK the tag; it moves to Acknowledged, then we pull EPC.
            if tag.accept_ack(tag.rn16):
                tag.finish_epc_tx()
            continue

        # Collision: all involved tags failed to decode the ACK, so
        # they draw fresh counters and re-enter Arbitrate for next round.
        round_.slots.append(SlotStat(slot=slot, kind="collision", tags=replies))
        for t in replies:
            t.state = STATE_ARBITRATE
            t.slot_counter = random.randint(0, (1 << q) - 1)
    return round_


def singulate(
    tags: List[Tag],
    initial_q: int = 4,
    max_rounds: int = 32,
    session: int = 0,
    target: int = 0,
) -> Tuple[List[Tag], List[InventoryRound], int]:
    """Singulate every tag. Returns the singulated set, all rounds,
    and the final tuned Q value."""
    q = initial_q
    rounds: List[InventoryRound] = []
    for _ in range(max_rounds):
        round_ = run_round(tags, q, session=session, target=target)
        rounds.append(round_)

        # QAdjust: if two collisions in a row, grow Q; if two empties
        # in a row, shrink Q. Clamp to [0, 15].
        kinds = [s.kind for s in round_.slots]
        if "collision" in kinds and kinds.count("collision") >= 2 and q < 15:
            q += 1
        elif "empty" in kinds and kinds.count("empty") >= 2 and q > 0:
            q -= 1

        # Did we read every non-killed tag this round?
        inventoried = {
            tag
            for s in round_.slots
            if s.kind == "single"
            for tag in s.tags
        }
        alive = {t for t in tags if t.state != STATE_KILLED}
        if inventoried == alive:
            return sorted(inventoried, key=lambda t: t.epc_hex), rounds, q
    return sorted({t for s in rounds[-1].slots if s.kind == "single" for t in s.tags},
                  key=lambda t: t.epc_hex), rounds, q


# ---------------------------------------------------------------------------
# Pretty printers
# ---------------------------------------------------------------------------


def print_slot_map(round_: InventoryRound) -> None:
    """Render a slot-by-slot trace for one round."""
    print(f"\n  Round  Q={round_.q}  slots=2^{round_.q}={1 << round_.q}")
    print(f"  {'slot':>4}  {'class':<10}  tags")
    print(f"  {'-' * 4}  {'-' * 10}  {'-' * 28}")
    for s in round_.slots:
        if s.kind == "empty":
            print(f"  {s.slot:>4}  {'empty':<10}  -")
        elif s.kind == "single":
            t = s.tags[0]
            print(
                f"  {s.slot:>4}  {'single':<10}  {t.epc_hex[:14]}..."
                f"  RN16=0x{t.rn16:04X}"
            )
        else:
            joined = " | ".join(t.epc_hex[:10] + ".." for t in s.tags)
            print(f"  {s.slot:>4}  {'COLLISION':<10} {joined}")


def print_occupancy(rounds: List[InventoryRound]) -> None:
    total_empty = sum(s.kind == "empty" for r in rounds for s in r.slots)
    total_single = sum(s.kind == "single" for r in rounds for s in r.slots)
    total_coll = sum(s.kind == "collision" for r in rounds for s in r.slots)
    total = total_empty + total_single + total_coll
    if total == 0:
        print("  (no slots observed)")
        return
    print("\n  Slot occupancy across all rounds:")
    print(f"  {'empty':<12} {total_empty:>5}  {100 * total_empty / total:5.1f}%")
    print(f"  {'single':<12} {total_single:>5}  {100 * total_single / total:5.1f}%")
    print(f"  {'collision':<12} {total_coll:>5}  {100 * total_coll / total:5.1f}%")
    print(f"  {'total slots':<12} {total:>5}")


def dump_query_bits(payload: int, crc: int) -> None:
    bits = f"{payload:019b}"
    print("\n  Query frame (19 bits payload + 5 bits CRC):")
    print(f"    Command=1000 | DR={bits[4:5]} | M={bits[5:7]} |"
          f" TRcal={bits[7:8]} | Sel={bits[8:10]} |"
          f" Session={bits[10:12]} | Target={bits[12:13]} |"
          f" Q={bits[13:17]}")
    print(f"    short-CRC (5b) = 0b{crc:05b}  (poly 0x8408)")


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------


def main() -> None:
    # Eight realistic 96-bit EPCs (GS1-style).
    epcs = [
        "E280116060002020DB7C1234AB",
        "E280116060002020DB7C5678CD",
        "E280116060002020DB7C90ABCDE",
        "E280116060002020DB7CDEF012",
        "E280116060002020DB7CAAAA00",
        "E280116060002020DB7CBBBB11",
        "E280116060002020DB7CCCCC22",
        "E280116060002020DB7CDDDD33",
    ]
    tags = [Tag(epc_hex=e) for e in epcs]

    print("=" * 72)
    print("RFID EPC Gen 2 — Q-algorithm singulation simulator")
    print("=" * 72)
    print(f"\n  Starting inventory of {len(tags)} Class-1 passive tags")
    print("  Reader radio: UHF, reader-talks-first, continuous wave + backscatter")
    print("  Singulation:  Query(Q=2) -> RN16 -> ACK -> PC+EPC+CRC-16")
    print("  Sessions:     S0 only (one reader)")

    # Build a Query for Q=2 and dump its bit layout + 5-bit CRC.
    payload, crc = build_query(q=2)
    dump_query_bits(payload, crc)

    # Singulate with the Q-algorithm and QAdjust.
    singulated, rounds, final_q = singulate(
        tags, initial_q=2, max_rounds=12, session=0, target=0,
    )

    print(f"\n  Completed in {len(rounds)} round(s); final tuned Q={final_q}")
    for i, r in enumerate(rounds, start=1):
        print(f"\n  --- Round {i} ---")
        print_slot_map(r)

    print_occupancy(rounds)

    print(f"\n  Singulated EPCs ({len(singulated)}):")
    for t in singulated:
        epc_word = t.epc_word()
        trailer_ok = crc16_ccitt_false(epc_word[2:]) == int.from_bytes(epc_word[:2], "big")
        print(
            f"    {t.epc_hex}  CRC16={'OK' if trailer_ok else 'BAD'}  "
            f"state={t.state}  S0={t.s_flag[0]}"
        )

    # Cross-check: full CRC-16/IBM over a synthetic command frame.
    synthetic = bytes.fromhex("1008000400")
    print(f"\n  CRC-16/IBM over 0x{synthetic.hex().upper()} "
          f"= 0x{crc16_ibm(synthetic):04X}")
    print(f"  CRC-16/CCITT-FALSE over 0x{synthetic.hex().upper()} "
          f"= 0x{crc16_ccitt_false(synthetic):04X}")


if __name__ == "__main__":
    main()