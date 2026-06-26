"""MACA (Multiple Access with Collision Avoidance) simulator.

Models a wireless LAN as a radio-range graph and demonstrates the RTS/CTS
handshake from Tanenbaum's "Wireless LAN Protocols" section. Shows:

  * why naive CSMA fails on hidden terminals (carrier sense reports activity
    at the SENDER, but collisions are decided at the RECEIVER),
  * how the receiver's CTS silences its own neighbourhood,
  * which overhearing stations defer after an RTS vs. after a CTS,
  * how a frame's length field becomes a NAV (Network Allocation Vector)
    microsecond silence timer (virtual carrier sense).

Stdlib only. Run: python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

# --- Protocol constants (orders of magnitude follow MACA / 802.11) ----------
RTS_BYTES = 30          # MACA RTS frame size (Tanenbaum: "this short frame, 30 bytes")
CTS_BYTES = 30          # CTS echoes the data length; similar size
SIFS_US = 16            # short interframe space between handshake frames (802.11a)
PHY_PREAMBLE_US = 20    # rough PHY preamble + header overhead per frame


# --- Radio topology ---------------------------------------------------------
class RadioTopology:
    """Undirected graph: an edge means two stations are within radio range."""

    def __init__(self, edges: List[Tuple[str, str]]) -> None:
        self._adj: Dict[str, Set[str]] = {}
        for a, b in edges:
            self._adj.setdefault(a, set()).add(b)
            self._adj.setdefault(b, set()).add(a)

    def stations(self) -> List[str]:
        return sorted(self._adj)

    def can_hear(self, x: str, y: str) -> bool:
        """True if x is within radio range of y (symmetric here)."""
        return y in self._adj.get(x, set())

    def neighbors(self, x: str) -> Set[str]:
        """Every station that would overhear x's transmission."""
        return set(self._adj.get(x, set()))


# --- Frames -----------------------------------------------------------------
@dataclass(frozen=True)
class Frame:
    kind: str            # "RTS" | "CTS" | "DATA" | "ACK"
    src: str
    dst: str
    data_len_bytes: int  # length the handshake reserves the channel for


def nav_microseconds(frame_bytes: int, mbps: float) -> float:
    """Convert an announced frame length into a NAV silence interval (us).

    Time-on-air = preamble + (bits / rate). 802.11 neighbours set their NAV
    to this value and skip contention for exactly that long.
    """
    bits = frame_bytes * 8
    payload_us = bits / mbps  # mbps == bits per microsecond
    return PHY_PREAMBLE_US + payload_us


# --- MACA exchange ----------------------------------------------------------
@dataclass
class ExchangeResult:
    rts: Frame
    cts: Frame
    deferred_by_rts: Set[str] = field(default_factory=set)
    deferred_by_cts: Set[str] = field(default_factory=set)
    free_to_transmit: Set[str] = field(default_factory=set)
    nav_us: float = 0.0


def maca_exchange(
    topo: RadioTopology, sender: str, receiver: str,
    data_len_bytes: int, mbps: float,
) -> ExchangeResult:
    """Run one RTS -> CTS exchange and classify every other station.

    A station hearing only the RTS is near the SENDER: it stays quiet just
    long enough for the CTS to return, then it is free. A station hearing the
    CTS is near the RECEIVER: it must defer for the whole data frame.
    """
    rts = Frame("RTS", sender, receiver, data_len_bytes)
    cts = Frame("CTS", receiver, sender, data_len_bytes)  # length copied from RTS

    heard_rts = topo.neighbors(sender) - {receiver}
    heard_cts = topo.neighbors(receiver) - {sender}

    result = ExchangeResult(rts=rts, cts=cts)
    result.nav_us = nav_microseconds(data_len_bytes, mbps)

    for st in topo.stations():
        if st in (sender, receiver):
            continue
        hears_rts = st in heard_rts
        hears_cts = st in heard_cts
        if hears_cts:
            # Near the receiver -> defer for the full data transmission.
            result.deferred_by_cts.add(st)
        elif hears_rts:
            # Near the sender only -> quiet during CTS window, then FREE.
            result.deferred_by_rts.add(st)
            result.free_to_transmit.add(st)
        # Hears neither -> unaffected.
    return result


def naive_csma_collision(
    topo: RadioTopology, sender: str, receiver: str, other_sender: str,
) -> bool:
    """Would naive CSMA (no RTS/CTS) let `other_sender` collide at `receiver`?

    The collision happens when both senders reach the receiver but cannot
    hear each other -- the classic hidden-terminal case.
    """
    both_reach_receiver = topo.can_hear(sender, receiver) and topo.can_hear(
        other_sender, receiver
    )
    senders_mutually_deaf = not topo.can_hear(sender, other_sender)
    return both_reach_receiver and senders_mutually_deaf


# --- Demonstration ----------------------------------------------------------
def _line_topology() -> RadioTopology:
    """A - B - C - D line, plus E sitting next to B (hears B and C)."""
    return RadioTopology(
        edges=[("A", "B"), ("B", "C"), ("C", "D"), ("B", "E"), ("C", "E")]
    )


def main() -> None:
    topo = _line_topology()
    print("Wireless LAN topology (edge = within radio range):")
    for st in topo.stations():
        print(f"  {st} hears: {', '.join(sorted(topo.neighbors(st)))}")
    print()

    # 1) Hidden terminal under naive CSMA: A and C both send to B.
    print("=== Naive CSMA: hidden terminal A and C -> B ===")
    a_hears_c = topo.can_hear("A", "C")
    collide = naive_csma_collision(topo, "A", "B", "C")
    print(f"  A can hear C? {a_hears_c}")
    print(f"  Both reach B but are mutually deaf -> collision at B? {collide}")
    print("  Carrier sense at C reports IDLE; the frame from A is destroyed.")
    print()

    # 2) MACA fixes it: A sends RTS to B, B replies CTS, neighbours defer.
    rate = 24.0  # Mbps
    data_bytes = 1200
    print(f"=== MACA: A -> B, {data_bytes} bytes at {rate} Mbps ===")
    res = maca_exchange(topo, "A", "B", data_bytes, rate)
    print(f"  RTS: {res.rts.src}->{res.rts.dst} len={res.rts.data_len_bytes}B")
    print(f"  CTS: {res.cts.src}->{res.cts.dst} len={res.cts.data_len_bytes}B")
    print(f"  NAV silence for data frame: {res.nav_us:.1f} us")
    print(f"  Deferred by hearing CTS (near receiver B): "
          f"{sorted(res.deferred_by_cts) or 'none'}")
    print(f"  Heard RTS only, FREE after CTS window (near sender A): "
          f"{sorted(res.free_to_transmit) or 'none'}")
    print("  -> C and E hear B's CTS, so they correctly stay silent for the")
    print("     data frame: MACA stopped a hidden-terminal collision at B.")
    print()

    # 2b) Exposed-terminal case on the pure A-B-C-D line (no E shortcut):
    #     B -> A in progress; C wants to send to D. C hears the RTS but NOT
    #     the CTS, so MACA leaves C free -- the concurrency we want.
    line = RadioTopology(edges=[("A", "B"), ("B", "C"), ("C", "D")])
    print("=== Exposed terminal: B -> A on pure A-B-C-D line ===")
    ex = maca_exchange(line, "B", "A", data_bytes, rate)
    print(f"  Heard RTS only, FREE to send elsewhere (e.g. C -> D): "
          f"{sorted(ex.free_to_transmit) or 'none'}")
    print("  -> C is EXPOSED: it could safely transmit to D, and MACA lets it.")
    print()

    # 3) Overhead crossover: RTS/CTS cost vs. data time-on-air.
    print("=== RTS/CTS handshake overhead vs. frame size (54 Mbps) ===")
    handshake_us = (
        nav_microseconds(RTS_BYTES, 54.0) + SIFS_US
        + nav_microseconds(CTS_BYTES, 54.0) + SIFS_US
    )
    for size in (64, 256, 1500):
        data_us = nav_microseconds(size, 54.0)
        ratio = handshake_us / (handshake_us + data_us)
        verdict = "overhead dominates" if ratio > 0.5 else "worth it"
        print(f"  {size:>4}B data: handshake={handshake_us:5.1f}us "
              f"data={data_us:6.1f}us overhead={ratio*100:4.1f}% ({verdict})")


if __name__ == "__main__":
    main()
