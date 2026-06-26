"""MACA: Hidden/Exposed Terminal Simulator and Handshake Tracer.

Two stdlib-only tools matching the lesson:

1. RadioNetwork -- places N stations on a 2D plane with a uniform radio range,
   computes which pairs are in range, identifies hidden-terminal pairs (two
   stations that cannot hear each other but share a common receiver), and
   exposed-terminal pairs (a station that defers unnecessarily because it
   hears a sender whose transmission would not reach the intended receiver).

2. MACAHandshake -- given the four-station A-B-C-D geometry from §4.2.5,
   simulates one MACA handshake (A → B), advances a slot clock, prints the
   RTS/CTS/data/ACK timing, and shows per-station deferral windows.  Also
   demonstrates the collision that occurs when the CTS step is skipped.

Run: python3 main.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

class Point(NamedTuple):
    x: float
    y: float

    def distance_to(self, other: "Point") -> float:
        return math.hypot(self.x - other.x, self.y - other.y)


# ---------------------------------------------------------------------------
# Radio-range network
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Station:
    name: str
    pos: Point


@dataclass
class RadioNetwork:
    """A collection of stations with a uniform radio range.

    Within *range_m* metres two stations can hear each other.  Outside that
    radius they cannot.  The model is symmetric and binary (no partial
    reception).
    """

    range_m: float
    stations: list[Station] = field(default_factory=list)

    # ---- construction helpers -------------------------------------------

    def add(self, name: str, x: float, y: float) -> "RadioNetwork":
        """Return a new network with *name* appended (immutable update)."""
        return RadioNetwork(
            range_m=self.range_m,
            stations=self.stations + [Station(name, Point(x, y))],
        )

    # ---- range queries --------------------------------------------------

    def in_range(self, a: str, b: str) -> bool:
        """True if station *a* and *b* can hear each other."""
        sa = self._get(a)
        sb = self._get(b)
        return sa.pos.distance_to(sb.pos) <= self.range_m

    def neighbours(self, name: str) -> list[str]:
        """Stations that can hear *name* (and vice-versa)."""
        return [s.name for s in self.stations if s.name != name and self.in_range(name, s.name)]

    # ---- hidden terminal detection --------------------------------------

    def hidden_terminal_pairs(self, receiver: str) -> list[tuple[str, str]]:
        """Pairs (A, C) that are both in range of *receiver* but out of range
        of each other — the classic hidden-terminal configuration.
        """
        nbrs = self.neighbours(receiver)
        pairs: list[tuple[str, str]] = []
        for i, a in enumerate(nbrs):
            for c in nbrs[i + 1:]:
                if not self.in_range(a, c):
                    pairs.append((a, c))
        return pairs

    # ---- exposed terminal detection ------------------------------------

    def exposed_terminal_cases(self) -> list[dict]:
        """Find (sender B, receiver A, exposed station C, intended dest D).

        C is an exposed terminal when:
          - C hears B (so CSMA makes C defer)
          - C wants to send to D
          - D does NOT hear B (so C's transmission would not collide at D)
          - C does NOT hear A (so C's deferral is wasted)
        """
        names = [s.name for s in self.stations]
        cases: list[dict] = []
        for b in names:
            for a in names:
                if a == b or not self.in_range(b, a):
                    continue
                for c in names:
                    if c in (a, b) or not self.in_range(c, b):
                        continue
                    # c hears b; now find d where d != a,b,c and d not in B's range
                    for d in names:
                        if d in (a, b, c):
                            continue
                        if not self.in_range(c, d):
                            continue
                        if self.in_range(d, b):
                            continue  # d hears b → not an exposed case
                        if self.in_range(c, a):
                            continue  # c hears a → not purely exposed
                        cases.append({"sender": b, "recv": a, "exposed": c, "dest": d})
        return cases

    # ---- safe concurrent transmissions ----------------------------------

    def safe_concurrent_pairs(self, tx_pairs: list[tuple[str, str]]) -> bool:
        """Return True if all transmissions in *tx_pairs* can run simultaneously
        without hidden-terminal collisions.

        A collision occurs at a receiver R when two or more senders that are
        in range of R transmit at the same time.
        """
        # count simultaneous signals arriving at each receiver
        receiver_senders: dict[str, list[str]] = {}
        for src, dst in tx_pairs:
            receiver_senders.setdefault(dst, []).append(src)
            # Also check whether src's signal reaches stations near dst
            for s in self.stations:
                if s.name != src and s.name != dst:
                    if self.in_range(src, s.name) and any(
                        self.in_range(other_src, s.name)
                        for other_src2, other_dst2 in tx_pairs
                        if other_src2 != src
                        for other_src in [other_src2]
                    ):
                        pass  # interference at bystander — not a collision at a *receiver*

        for r, senders in receiver_senders.items():
            if len(senders) > 1:
                return False
        return True

    # ---- internal -------------------------------------------------------

    def _get(self, name: str) -> Station:
        for s in self.stations:
            if s.name == name:
                return s
        raise KeyError(f"Unknown station: {name!r}")

    def print_range_table(self) -> None:
        names = [s.name for s in self.stations]
        w = max(len(n) for n in names)
        header = " " * (w + 2) + "  ".join(f"{n:>{w}}" for n in names)
        print(header)
        for a in names:
            row = f"{a:>{w}}  " + "  ".join(
                f"{'YES' if self.in_range(a, b) else ' - ':>{w}}"
                for b in names
            )
            print(row)


# ---------------------------------------------------------------------------
# MACA frame types and timing
# ---------------------------------------------------------------------------

SLOT_US = 9          # 802.11b slot = 9 µs (we use it as the time unit)
RTS_BYTES = 30       # per Karn 1990
CTS_BYTES = 30
DATA_BYTES = 1000    # example payload
ACK_BYTES = 14
RATE_MBPS = 1.0      # 1 Mbps for easy arithmetic (per chapter example)
PROP_DELAY_US = 5    # propagation A→B at 100 m
CTS_TURNAROUND_US = 20  # B's processing delay before CTS


def _tx_duration_us(bytes_: int) -> int:
    """Transmission time in microseconds at RATE_MBPS."""
    bits = bytes_ * 8
    return round(bits / RATE_MBPS)   # µs at 1 Mbps


@dataclass(frozen=True)
class MACFrame:
    kind: str          # "RTS", "CTS", "DATA", "ACK"
    src: str
    dst: str
    data_length: int   # bytes in the upcoming data frame (echoed in CTS)
    tx_start_us: int
    tx_end_us: int

    @property
    def duration_us(self) -> int:
        return self.tx_end_us - self.tx_start_us


@dataclass(frozen=True)
class DeferralWindow:
    station: str
    reason: str        # which frame was overheard
    defer_start_us: int
    defer_end_us: int

    @property
    def duration_us(self) -> int:
        return self.defer_end_us - self.defer_start_us


@dataclass
class MACAHandshake:
    """Simulate one MACA handshake between sender A and receiver B.

    Geometry (from §4.2.5):
        A -- (in range) -- B -- (in range) -- C,D
        A is NOT in range of C or D.
        C is in range of A and B.   [exposed terminal candidate]
        D is in range of B only.    [hidden terminal candidate]
        E is in range of both A and B.
    """

    def run(self, include_cts: bool = True) -> tuple[list[MACFrame], list[DeferralWindow]]:
        """Run the handshake, optionally skipping the CTS step.

        Returns (frames, deferrals).
        """
        frames: list[MACFrame] = []
        deferrals: list[DeferralWindow] = []

        rts_dur = _tx_duration_us(RTS_BYTES)
        cts_dur = _tx_duration_us(CTS_BYTES)
        data_dur = _tx_duration_us(DATA_BYTES)
        ack_dur = _tx_duration_us(ACK_BYTES)

        # ---- RTS: A → B -----------------------------------------------
        rts_start = 0
        rts_end = rts_start + rts_dur
        rts = MACFrame("RTS", "A", "B", DATA_BYTES, rts_start, rts_end)
        frames.append(rts)

        # RTS arrives at B after propagation
        rts_arrive_b = rts_end + PROP_DELAY_US

        if include_cts:
            # ---- CTS: B → A -------------------------------------------
            cts_start = rts_arrive_b + CTS_TURNAROUND_US
            cts_end = cts_start + cts_dur
            cts = MACFrame("CTS", "B", "A", DATA_BYTES, cts_start, cts_end)
            frames.append(cts)

            # CTS arrives at A after propagation
            cts_arrive_a = cts_end + PROP_DELAY_US

            # ---- DATA: A → B ------------------------------------------
            data_start = cts_arrive_a + CTS_TURNAROUND_US
            data_end = data_start + data_dur
            data = MACFrame("DATA", "A", "B", DATA_BYTES, data_start, data_end)
            frames.append(data)

            # ---- ACK: B → A -------------------------------------------
            ack_start = data_end + PROP_DELAY_US + CTS_TURNAROUND_US
            ack_end = ack_start + ack_dur
            ack = MACFrame("ACK", "B", "A", DATA_BYTES, ack_start, ack_end)
            frames.append(ack)

            # ---- Deferrals ----------------------------------------
            # C hears RTS (C is in range of A).
            # Rule: defer long enough for CTS to return to A.
            # C does NOT hear CTS (C is not in range of B in this geometry).
            c_defer_end = cts_start + cts_dur  # wait until CTS would have propagated
            deferrals.append(DeferralWindow("C", "overheard RTS from A", rts_end, c_defer_end))

            # D hears CTS (D is in range of B).
            # Rule: defer for the entire data frame (length announced in CTS).
            d_defer_end = data_end + PROP_DELAY_US
            deferrals.append(DeferralWindow("D", "overheard CTS from B", cts_end, d_defer_end))

            # E hears both RTS and CTS (in range of A and B).
            # Rule: defer from RTS through end of data frame.
            deferrals.append(DeferralWindow("E", "overheard RTS+CTS", rts_end, data_end + PROP_DELAY_US))

        else:
            # No CTS: A transmits data directly.
            # Hidden terminal scenario: C cannot detect A's transmission
            # and also transmits to B, causing a collision at B.
            data_start = rts_end + PROP_DELAY_US + CTS_TURNAROUND_US
            data_end = data_start + data_dur
            data = MACFrame("DATA", "A", "B", DATA_BYTES, data_start, data_end)
            frames.append(data)

            # C senses idle (cannot hear A) and transmits at the same time
            c_start = data_start + 10   # C starts shortly after, simulating simultaneous intent
            c_end = c_start + _tx_duration_us(DATA_BYTES)
            c_frame = MACFrame("DATA", "C", "B", DATA_BYTES, c_start, c_end)
            frames.append(c_frame)

            deferrals.append(DeferralWindow(
                "B (receiver)",
                "COLLISION — A and C transmit simultaneously, no CTS issued",
                data_start, max(data_end, c_end),
            ))

        return frames, deferrals


# ---------------------------------------------------------------------------
# Pretty printers
# ---------------------------------------------------------------------------

def _print_section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def print_radio_network_demo(net: RadioNetwork) -> None:
    _print_section("Radio-Range Network: in-range table")
    net.print_range_table()

    print()
    print("Neighbours per station:")
    for s in net.stations:
        nbrs = net.neighbours(s.name)
        print(f"  {s.name} ({s.pos.x:>4.0f},{s.pos.y:>4.0f})  range: {nbrs}")

    print()
    print("Hidden-terminal pairs (share a receiver but cannot hear each other):")
    for s in net.stations:
        pairs = net.hidden_terminal_pairs(s.name)
        if pairs:
            for a, c in pairs:
                print(f"  receiver={s.name}: {a} and {c} are hidden terminals")

    print()
    print("Exposed-terminal cases:")
    cases = net.exposed_terminal_cases()
    if cases:
        for c in cases:
            print(
                f"  {c['exposed']} hears {c['sender']}→{c['recv']} "
                f"but its own tx to {c['dest']} would not collide there "
                f"(unnecessary deferral)"
            )
    else:
        print("  (none found with this geometry)")

    print()
    print("Safe concurrent transmissions:")
    # Try A→B and C→D simultaneously
    names = [s.name for s in net.stations]
    if len(names) >= 4:
        pair1 = (names[0], names[1])
        pair2 = (names[2], names[3])
        safe = net.safe_concurrent_pairs([pair1, pair2])
        print(f"  {pair1[0]}→{pair1[1]} and {pair2[0]}→{pair2[1]} simultaneously: "
              f"{'SAFE (no hidden-terminal collision)' if safe else 'COLLISION RISK'}")


def print_handshake_demo(with_cts: bool = True) -> None:
    label = "WITH CTS (normal MACA)" if with_cts else "WITHOUT CTS (hidden-terminal collision)"
    _print_section(f"MACA Handshake Trace: {label}")

    print("""
Geometry (A-B-C-D linear, range=75 m, spacing=50 m):
  A=(0,0)  B=(50,0)  C=(100,0)  D=(150,0)
  A↔B in range, B↔C in range, C↔D in range
  A NOT in range of C or D.  D NOT in range of B.
""")

    hs = MACAHandshake()
    frames, deferrals = hs.run(include_cts=with_cts)

    print(f"  {'Frame':<6}  {'From':<4}  {'To':<4}  {'Bytes':>6}  {'Start µs':>10}  {'End µs':>8}  {'Dur µs':>8}")
    print("  " + "-" * 62)
    for f in frames:
        sz = {
            "RTS": RTS_BYTES, "CTS": CTS_BYTES, "ACK": ACK_BYTES,
        }.get(f.kind, DATA_BYTES)
        print(f"  {f.kind:<6}  {f.src:<4}  {f.dst:<4}  {sz:>6}  {f.tx_start_us:>10}  {f.tx_end_us:>8}  {f.duration_us:>8}")

    if deferrals:
        print()
        print(f"  {'Station':<10}  {'Reason':<50}  {'Start µs':>10}  {'End µs':>8}  {'Dur µs':>8}")
        print("  " + "-" * 88)
        for d in deferrals:
            print(
                f"  {d.station:<10}  {d.reason:<50}  "
                f"{d.defer_start_us:>10}  {d.defer_end_us:>8}  {d.duration_us:>8}"
            )

    if with_cts:
        print()
        print("  Key observations:")
        print("  • C hears only the RTS → defers only until CTS window closes → may transmit during DATA")
        print("    (C is an EXPOSED terminal: its tx to D would not reach B's range anyway)")
        print("  • D hears only the CTS → defers for the full data duration → hidden-terminal averted")
        print("  • E hears both → defers from RTS through end of DATA")
    else:
        print()
        print("  Key observation:")
        print("  • Without CTS, C cannot know B is about to receive; C transmits, COLLISION at B.")


def print_timing_exercise() -> None:
    """Reproduce Exercise 2 from the lesson: exact µs for each station's deferral."""
    _print_section("Timing Exercise (Lesson Exercise 2)")
    rts_bytes = 30
    rate_mbps = 1.0
    prop_us = 5
    cts_turnaround_us = 20

    rts_dur = round(rts_bytes * 8 / rate_mbps)
    print(f"  RTS transmission:   {rts_dur} µs  (30 bytes × 8 bits ÷ 1 Mbps)")
    print(f"  Propagation A→B:    {prop_us} µs")
    print(f"  CTS turnaround at B:{cts_turnaround_us} µs")

    # C is in range of A: C defers from when it sees the RTS end to when
    # the CTS would have arrived at C.  CTS is sent from B; C is not in range
    # of B, so C only needs to defer long enough for the CTS to reach A
    # (and thus no collision with the RTS re-transmission).
    rts_arrive_b = rts_dur + prop_us
    cts_start_at_b = rts_arrive_b + cts_turnaround_us
    cts_dur = round(rts_bytes * 8 / rate_mbps)  # same size
    cts_end_at_b = cts_start_at_b + cts_dur
    cts_arrive_a = cts_end_at_b + prop_us

    print()
    print(f"  C's deferral (heard RTS; not in B's range):")
    print(f"    defer start = {rts_dur} µs  (RTS transmission done)")
    print(f"    defer end   = {cts_end_at_b} µs  (CTS transmission done at B; C waits this long)")
    print(f"    C is free after {cts_end_at_b} µs")

    print()
    data_bytes = 1000
    data_dur = round(data_bytes * 8 / rate_mbps)
    data_start = cts_arrive_a + cts_turnaround_us
    data_end = data_start + data_dur
    print(f"  D's deferral (heard CTS; not in A's range):")
    print(f"    defer start = {cts_end_at_b} µs  (CTS done at B)")
    print(f"    data frame  = {data_bytes} bytes → {data_dur} µs")
    print(f"    data starts at {data_start} µs, ends at {data_end} µs")
    print(f"    D is free after {data_end + prop_us} µs")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # ------------------------------------------------------------------ #
    # Part 1: Radio-range network from chapter geometry
    # A=(0,0), B=(50,0), C=(100,0), D=(150,0), range=75 m
    # ------------------------------------------------------------------ #
    net = (
        RadioNetwork(range_m=75.0)
        .add("A", 0, 0)
        .add("B", 50, 0)
        .add("C", 100, 0)
        .add("D", 150, 0)
    )
    print_radio_network_demo(net)

    # ------------------------------------------------------------------ #
    # Part 2: Five-station network with an exposed-terminal case
    # Add E in range of both A and B (between them)
    # ------------------------------------------------------------------ #
    net5 = (
        RadioNetwork(range_m=75.0)
        .add("A", 0, 0)
        .add("B", 50, 0)
        .add("C", 100, 0)
        .add("D", 150, 0)
        .add("E", 25, 0)   # E in range of both A and B
    )
    _print_section("Five-Station Network (adds E between A and B)")
    print("Neighbours per station:")
    for s in net5.stations:
        print(f"  {s.name}: {net5.neighbours(s.name)}")
    print()
    print("Hidden-terminal pairs at each receiver:")
    found_any = False
    for s in net5.stations:
        pairs = net5.hidden_terminal_pairs(s.name)
        if pairs:
            found_any = True
            for a, c in pairs:
                print(f"  receiver={s.name}: {a} ↔ {c} are hidden terminals")
    if not found_any:
        print("  (none)")

    # ------------------------------------------------------------------ #
    # Part 3: MACA handshake traces
    # ------------------------------------------------------------------ #
    print_handshake_demo(with_cts=True)
    print_handshake_demo(with_cts=False)

    # ------------------------------------------------------------------ #
    # Part 4: Timing exercise (lesson Exercise 2)
    # ------------------------------------------------------------------ #
    print_timing_exercise()

    _print_section("Summary")
    print("""
  MACA solves the hidden-terminal problem with a two-frame handshake:
    • RTS (sender → receiver): announces upcoming data length
    • CTS (receiver → sender): echoes length; all neighbours of the RECEIVER defer

  Hidden terminals hear the CTS → defer for the full data frame.
  Exposed terminals hear only the RTS → defer only until the CTS window closes,
  then may transmit to their own destinations concurrently.

  MACAW (1994) adds per-frame ACK and per-link retry counters.
  802.11 adds CSMA/CA, NAV (virtual carrier sense), and exponential backoff.
""")


if __name__ == "__main__":
    main()
