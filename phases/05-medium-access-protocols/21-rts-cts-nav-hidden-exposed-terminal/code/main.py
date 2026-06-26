"""RTS/CTS, NAV, and the hidden/exposed terminal problem simulator.

A stdlib-only Python simulation of the 802.11 RTS/CTS/DATA/ACK handshake,
the Network Allocation Vector (NAV) calculation, and a 4-node wireless topology
that demonstrates both the hidden terminal and the exposed terminal problems.

Topology:
  D <-- A <-----------> B <-----------> C
  A sends to B; C sends to B.
  A and C cannot hear each other.
  B (the AP) is within range of everyone.

Key mechanisms demonstrated:
  * Exact NAV arithmetic for RTS and CTS frames
  * The 4-frame RTS/CTS/DATA/ACK exchange with per-station NAV assignment
  * Hidden-terminal collision rate: no-RTS/CTS versus RTS/CTS for varying
    frame sizes and RTS thresholds
  * Why RTS/CTS does not cure exposed terminals (and why MACA does)

Run:
    python3 code/main.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# 802.11g PHY constants (OFDM)
# ---------------------------------------------------------------------------

SIFS_US: int = 16       # Short Interframe Space, µs
DIFS_US: int = 34       # DCF Interframe Space (= SIFS + 2 * SLOT), µs
SLOT_US: int = 9        # Slot time, µs  (802.11g/a)
BASIC_MBPS: float = 6.0 # BSS basic rate for control frames (RTS/CTS/ACK), Mbps

# RTS, CTS, ACK frame sizes (bytes) per the 802.11 standard
RTS_BYTES: int = 20     # Frame Control(2)+Duration(2)+RA(6)+TA(6)+FCS(4)
CTS_BYTES: int = 14     # Frame Control(2)+Duration(2)+RA(6)+FCS(4)
ACK_BYTES: int = 14     # Frame Control(2)+Duration(2)+RA(6)+FCS(4)


# ---------------------------------------------------------------------------
# Transmission-time helpers
# ---------------------------------------------------------------------------

def tx_us(byte_count: int, mbps: float) -> float:
    """Return the time in microseconds to transmit `byte_count` bytes at `mbps`."""
    return (byte_count * 8.0) / mbps


def nav_in_rts(data_bytes: int, data_mbps: float) -> float:
    """NAV value placed in the RTS Duration field (µs).

    NAV_RTS = SIFS + t(CTS) + SIFS + t(DATA) + SIFS + t(ACK)
    """
    t_cts = tx_us(CTS_BYTES, BASIC_MBPS)
    t_data = tx_us(data_bytes, data_mbps)
    t_ack = tx_us(ACK_BYTES, BASIC_MBPS)
    return SIFS_US + t_cts + SIFS_US + t_data + SIFS_US + t_ack


def nav_in_cts(data_bytes: int, data_mbps: float) -> float:
    """NAV value placed in the CTS Duration field (µs).

    NAV_CTS = SIFS + t(DATA) + SIFS + t(ACK)
    """
    t_data = tx_us(data_bytes, data_mbps)
    t_ack = tx_us(ACK_BYTES, BASIC_MBPS)
    return SIFS_US + t_data + SIFS_US + t_ack


def nav_in_data(data_mbps: float) -> float:
    """NAV value placed in the DATA Duration field (µs).

    NAV_DATA = SIFS + t(ACK)
    """
    t_ack = tx_us(ACK_BYTES, BASIC_MBPS)
    return SIFS_US + t_ack


# ---------------------------------------------------------------------------
# 802.11 frame representations
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RtsFrame:
    transmitter: str        # TA — station sending RTS
    receiver: str           # RA — intended data receiver
    data_bytes: int         # size of the DATA frame that will follow
    data_mbps: float        # rate at which DATA will be sent

    @property
    def duration_us(self) -> float:
        return nav_in_rts(self.data_bytes, self.data_mbps)

    @property
    def tx_time_us(self) -> float:
        return tx_us(RTS_BYTES, BASIC_MBPS)

    def __str__(self) -> str:
        return (f"RTS  TA={self.transmitter} RA={self.receiver} "
                f"size={RTS_BYTES}B  Duration={self.duration_us:.1f}µs")


@dataclass(frozen=True)
class CtsFrame:
    receiver: str           # RA — station that sent the RTS
    data_bytes: int
    data_mbps: float

    @property
    def duration_us(self) -> float:
        return nav_in_cts(self.data_bytes, self.data_mbps)

    @property
    def tx_time_us(self) -> float:
        return tx_us(CTS_BYTES, BASIC_MBPS)

    def __str__(self) -> str:
        return (f"CTS  RA={self.receiver} "
                f"size={CTS_BYTES}B  Duration={self.duration_us:.1f}µs")


@dataclass(frozen=True)
class DataFrame:
    transmitter: str
    receiver: str
    data_bytes: int
    data_mbps: float

    @property
    def duration_us(self) -> float:
        return nav_in_data(self.data_mbps)

    @property
    def tx_time_us(self) -> float:
        return tx_us(self.data_bytes, self.data_mbps)

    def __str__(self) -> str:
        return (f"DATA TA={self.transmitter} RA={self.receiver} "
                f"size={self.data_bytes}B@{self.data_mbps}Mbps "
                f"Duration={self.duration_us:.1f}µs")


@dataclass(frozen=True)
class AckFrame:
    receiver: str

    @property
    def duration_us(self) -> float:
        return 0.0          # ACK carries Duration=0

    @property
    def tx_time_us(self) -> float:
        return tx_us(ACK_BYTES, BASIC_MBPS)

    def __str__(self) -> str:
        return f"ACK  RA={self.receiver} size={ACK_BYTES}B  Duration=0µs"


# ---------------------------------------------------------------------------
# Topology (can_hear graph)
# ---------------------------------------------------------------------------
#
# can_hear[rx] = set of transmitters that rx can receive.
#
# Hidden-terminal topology (A sends to B, C sends to B):
#   A <-> B <-> C   but A and C cannot hear each other.
#
# Exposed-terminal extension: D is beyond A's range, B cannot hear D.

CAN_HEAR: dict[str, set[str]] = {
    'A': {'A', 'B'},        # A hears itself and B; NOT C or D
    'B': {'A', 'B', 'C'},  # AP hears A, B, C; NOT D (D is beyond B's range)
    'C': {'B', 'C'},        # C hears B and itself; NOT A or D
    'D': {'A', 'D'},        # D hears A and itself; NOT B or C
}


def can_hear(rx: str, tx: str) -> bool:
    return tx in CAN_HEAR.get(rx, set())


# ---------------------------------------------------------------------------
# 4-frame RTS/CTS/DATA/ACK exchange trace
# ---------------------------------------------------------------------------

@dataclass
class ExchangeEvent:
    t_us: float
    frame_type: str
    detail: str
    nav_updates: list[tuple[str, float]] = field(default_factory=list)


def trace_exchange(
    sender: str = 'A',
    receiver: str = 'B',
    data_bytes: int = 1000,
    data_mbps: float = 54.0,
    difs_wait_us: float = DIFS_US,
    backoff_slots: int = 4,
) -> list[ExchangeEvent]:
    """Trace the full 4-frame exchange and return a list of events with NAV updates."""
    events: list[ExchangeEvent] = []
    t = difs_wait_us + backoff_slots * SLOT_US   # A begins transmitting RTS

    # --- Frame 1: RTS from A ---
    rts = RtsFrame(sender, receiver, data_bytes, data_mbps)
    nav_updates_rts: list[tuple[str, float]] = []
    for station in CAN_HEAR:
        if station != sender and can_hear(station, sender):
            nav_updates_rts.append((station, rts.duration_us))
    events.append(ExchangeEvent(t, "RTS", str(rts), nav_updates_rts))
    t += rts.tx_time_us

    # --- SIFS ---
    t += SIFS_US

    # --- Frame 2: CTS from receiver (B) ---
    cts = CtsFrame(sender, data_bytes, data_mbps)
    nav_updates_cts: list[tuple[str, float]] = []
    for station in CAN_HEAR:
        if station != receiver and can_hear(station, receiver):
            # Only update NAV if it would be higher than what the station
            # already has from RTS; any station that heard the RTS already
            # has a NAV covering the full exchange, so CTS NAV is less.
            nav_updates_cts.append((station, cts.duration_us))
    events.append(ExchangeEvent(t, "CTS", str(cts), nav_updates_cts))
    t += cts.tx_time_us

    # --- SIFS ---
    t += SIFS_US

    # --- Frame 3: DATA from A ---
    data_frame = DataFrame(sender, receiver, data_bytes, data_mbps)
    nav_updates_data: list[tuple[str, float]] = []
    for station in CAN_HEAR:
        if station != sender and can_hear(station, sender):
            nav_updates_data.append((station, data_frame.duration_us))
    events.append(ExchangeEvent(t, "DATA", str(data_frame), nav_updates_data))
    t += data_frame.tx_time_us

    # --- SIFS ---
    t += SIFS_US

    # --- Frame 4: ACK from B ---
    ack = AckFrame(sender)
    events.append(ExchangeEvent(t, "ACK", str(ack), []))
    t += ack.tx_time_us

    return events


def print_exchange_trace(
    data_bytes: int = 1000,
    data_mbps: float = 54.0,
) -> None:
    print("=" * 72)
    print("4-FRAME RTS/CTS/DATA/ACK EXCHANGE TRACE")
    print(f"  Topology: A → B,  SIFS={SIFS_US}µs, SLOT={SLOT_US}µs")
    print(f"  Data: {data_bytes}B @ {data_mbps}Mbps,  "
          f"Basic rate: {BASIC_MBPS}Mbps")
    print("=" * 72)

    events = trace_exchange(data_bytes=data_bytes, data_mbps=data_mbps)
    for ev in events:
        print(f"\n  t={ev.t_us:>7.1f}µs  [{ev.frame_type}]  {ev.detail}")
        if ev.nav_updates:
            for station, nav_val in ev.nav_updates:
                print(f"              NAV update: station {station} "
                      f"sets NAV ← max(NAV, {nav_val:.1f}µs)")

    # Summary: total exchange duration
    ev_rts = events[0]
    ev_ack = events[-1]
    ack_frame = AckFrame('A')
    total = ev_ack.t_us + ack_frame.tx_time_us - ev_rts.t_us
    print(f"\n  Total exchange duration: {total:.1f}µs")


# ---------------------------------------------------------------------------
# NAV arithmetic table
# ---------------------------------------------------------------------------

def print_nav_table(data_mbps: float = 54.0) -> None:
    print()
    print("=" * 72)
    print("NAV VALUES FOR VARYING DATA FRAME SIZES")
    print(f"  SIFS={SIFS_US}µs  basic_rate={BASIC_MBPS}Mbps  data_rate={data_mbps}Mbps")
    print("-" * 72)
    print(f"  {'DATA (B)':>8}  {'t(CTS)':>9}  {'t(DATA)':>9}  {'t(ACK)':>9}  "
          f"{'NAV_RTS':>9}  {'NAV_CTS':>9}")
    print("-" * 72)
    for size in [100, 200, 500, 1000, 1460, 1500]:
        t_cts = tx_us(CTS_BYTES, BASIC_MBPS)
        t_data = tx_us(size, data_mbps)
        t_ack = tx_us(ACK_BYTES, BASIC_MBPS)
        nav_rts = nav_in_rts(size, data_mbps)
        nav_cts = nav_in_cts(size, data_mbps)
        print(f"  {size:>8d}  {t_cts:>8.1f}µ  {t_data:>8.1f}µ  {t_ack:>8.1f}µ  "
              f"{nav_rts:>8.1f}µ  {nav_cts:>8.1f}µ")

    # Reproduce the exact example from the prose
    print()
    print("  Prose example (SIFS=16µs, basic=6Mbps, data=54Mbps, DATA=1000B):")
    size = 1000
    t_cts = tx_us(14, 6.0)
    t_data = tx_us(size, 54.0)
    t_ack = tx_us(14, 6.0)
    nav_rts = SIFS_US + t_cts + SIFS_US + t_data + SIFS_US + t_ack
    nav_cts = SIFS_US + t_data + SIFS_US + t_ack
    print(f"    t(CTS)  = (14×8)/{BASIC_MBPS}Mbps = {t_cts:.1f}µs")
    print(f"    t(DATA) = ({size}×8)/54Mbps = {t_data:.1f}µs")
    print(f"    t(ACK)  = (14×8)/{BASIC_MBPS}Mbps = {t_ack:.1f}µs")
    print(f"    NAV_RTS = {SIFS_US}+{t_cts:.1f}+{SIFS_US}+{t_data:.1f}"
          f"+{SIFS_US}+{t_ack:.1f} = {nav_rts:.1f}µs")
    print(f"    NAV_CTS = {SIFS_US}+{t_data:.1f}+{SIFS_US}+{t_ack:.1f} = {nav_cts:.1f}µs")


# ---------------------------------------------------------------------------
# Hidden-terminal collision simulator
#
# Two stations A and C both want to send to B (the AP).
# A and C cannot hear each other — the hidden terminal problem.
#
# For each trial:
#   - A draws backoff bo_a (uniform [0, CW] * SLOT_US)
#   - C draws backoff bo_c (uniform [0, CW] * SLOT_US)
#   - A starts transmitting at t=bo_a, C starts at t=bo_c
#   - Collision at B if the two transmission intervals overlap:
#       |bo_a - bo_c| < t(DATA)
#
# With RTS/CTS (for frames >= rts_threshold):
#   - Whoever wins (smaller backoff) sends RTS to B.
#   - B replies with CTS.
#   - The loser hears B's CTS (since B is in range of both) and sets NAV.
#   - The loser defers for NAV_CTS µs → no collision.
# ---------------------------------------------------------------------------

def simulate_hidden_terminal(
    trials: int = 5000,
    cw: int = 15,
    use_rts: bool = False,
    rts_threshold_bytes: int = 500,
    data_mbps: float = 54.0,
    seed: int = 42,
) -> tuple[int, int, float]:
    """Return (successes, collisions, collision_pct)."""
    rng = random.Random(seed)
    successes = 0
    collisions = 0

    for _ in range(trials):
        data_bytes = rng.randint(64, 1500)
        bo_a = rng.randint(0, cw) * SLOT_US   # µs
        bo_c = rng.randint(0, cw) * SLOT_US   # µs
        dt = tx_us(data_bytes, data_mbps)     # µs

        if use_rts and data_bytes >= rts_threshold_bytes:
            # RTS/CTS exchange protects large frames.
            # Winner (smaller backoff) sends RTS; B sends CTS.
            # Loser hears CTS from B and defers (C can always hear B, A can hear B).
            # Both A and C are in B's can_hear set, so both hear CTS → no collision.
            if bo_a != bo_c:
                successes += 1
            else:
                # Exact tie → both send RTS simultaneously → collision at B.
                collisions += 1
        else:
            # No RTS/CTS (or frame below threshold).
            # A and C transmit to B without coordination.
            # Collision if their transmission intervals overlap.
            if abs(bo_a - bo_c) < dt:
                collisions += 1
            else:
                successes += 1

    total = successes + collisions
    pct = collisions / total * 100.0 if total else 0.0
    return successes, collisions, pct


def print_collision_table() -> None:
    print()
    print("=" * 72)
    print("HIDDEN-TERMINAL COLLISION SIMULATION (A and C → B, mutual inaudible)")
    print(f"  {5000} trials each, CW=15 (backoff in [0,15]×{SLOT_US}µs), data@54Mbps")
    print("-" * 72)
    print(f"  {'Mode':<35} {'Successes':>9} {'Collisions':>11} {'Coll%':>7}")
    print("-" * 72)
    configs: list[tuple[bool, int, str]] = [
        (False, 9999, "No RTS/CTS"),
        (True,  256,  "RTS/CTS threshold=256B"),
        (True,  512,  "RTS/CTS threshold=512B"),
        (True, 1024,  "RTS/CTS threshold=1024B"),
    ]
    for use_rts, thresh, label in configs:
        s, c, pct = simulate_hidden_terminal(
            trials=5000, use_rts=use_rts, rts_threshold_bytes=thresh
        )
        print(f"  {label:<35} {s:>9} {c:>11} {pct:>6.1f}%")

    print()
    print("  Interpretation:")
    print("  * Without RTS/CTS, hidden terminals collide whenever their")
    print("    transmission intervals overlap at B.")
    print("  * With RTS/CTS, C hears B's CTS and defers via NAV;")
    print("    collision rate drops to near 0% for frames >= threshold.")
    print("  * Below the threshold, no RTS/CTS is sent and the collision")
    print("    rate matches the unprotected case.")


# ---------------------------------------------------------------------------
# Exposed-terminal illustration (qualitative)
# ---------------------------------------------------------------------------

def print_exposed_terminal_analysis() -> None:
    print()
    print("=" * 72)
    print("EXPOSED TERMINAL ANALYSIS")
    print("  Topology: D <-- A <--------> B <--------> C")
    print("  A is transmitting to D.  B wants to send to C.")
    print("-" * 72)

    # B hears A (A is in B's CAN_HEAR).
    b_hears_a = can_hear('B', 'A')
    # B's transmission to C would it reach D? D cannot hear A's transmitter,
    # and B is out of range of D.
    b_in_d_range = can_hear('D', 'B')

    print(f"  B can hear A transmitting:               {b_hears_a}")
    print(f"  B's signal would reach D (harm A→D rx): {b_in_d_range}")
    print()
    if b_hears_a and not b_in_d_range:
        print("  Result under 802.11 CSMA/CA:")
        print("    B senses the channel busy (A's signal) and DEFERS.")
        print("    But B→C transmission would NOT have interfered at D.")
        print("    → Unnecessary deferral: CAPACITY WASTED, no collision prevented.")
        print()
        print("  Result under 802.11 RTS/CTS:")
        print("    When A's RTS is overheard by B, 802.11 has B set its NAV.")
        print("    B still defers. Exposed-terminal waste is NOT cured.")
        print()
        print("  Result under MACA (Karn 1990):")
        print("    MACA: only CTS hearers defer, not RTS hearers.")
        print("    B hears A's RTS but does NOT defer under MACA rules.")
        print("    B can send to C — exposed terminal IS cured.")


# ---------------------------------------------------------------------------
# RTS overhead vs. frame size
# ---------------------------------------------------------------------------

def print_overhead_analysis() -> None:
    print()
    print("=" * 72)
    print("RTS/CTS OVERHEAD vs. DATA FRAME SIZE")
    print(f"  basic_rate={BASIC_MBPS}Mbps, data_rate=54Mbps, SIFS={SIFS_US}µs")
    print("-" * 72)
    handshake_bytes = RTS_BYTES + CTS_BYTES
    handshake_us = tx_us(RTS_BYTES, BASIC_MBPS) + SIFS_US + tx_us(CTS_BYTES, BASIC_MBPS) + SIFS_US
    print(f"  RTS({RTS_BYTES}B)+CTS({CTS_BYTES}B) = {handshake_bytes}B overhead")
    print(f"  Handshake airtime = {handshake_us:.1f}µs (2×SIFS + t(RTS)+t(CTS)@{BASIC_MBPS}Mbps)")
    print(f"  {'DATA (B)':>8}  {'DATA time':>10}  {'Handshake':>10}  {'Overhead%':>10}  {'Worth it?':>10}")
    print("-" * 72)
    for size in [50, 100, 200, 500, 1000, 1500]:
        dt = tx_us(size, 54.0)
        overhead_pct = handshake_us / (dt + handshake_us) * 100.0
        worth_it = "Yes" if size >= 500 else "No (too small)"
        print(f"  {size:>8d}  {dt:>9.1f}µs  {handshake_us:>9.1f}µs  "
              f"{overhead_pct:>9.1f}%  {worth_it:>10}")


# ---------------------------------------------------------------------------
# MACA vs 802.11 RTS/CTS comparison
# ---------------------------------------------------------------------------

def print_maca_vs_80211() -> None:
    print()
    print("=" * 72)
    print("MACA (1990) vs. 802.11 RTS/CTS — which stations defer?")
    print("  4-node topology: A→B; C hears A (not B); D hears B (not A)")
    print("-" * 72)
    rows = [
        ("Hears RTS",           "Does NOT defer",  "Defers (sets NAV)"),
        ("Hears CTS",           "Defers",           "Defers (sets NAV)"),
        ("Hidden terminal cured?", "Yes",           "Yes"),
        ("Exposed terminal cured?","Yes",            "No"),
        ("Standardised?",       "Research only",    "IEEE 802.11 optional"),
    ]
    print(f"  {'Behaviour':<30} {'MACA':^20} {'802.11 RTS/CTS':^20}")
    print("-" * 72)
    for row in rows:
        print(f"  {row[0]:<30} {row[1]:^20} {row[2]:^20}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    random.seed(0)

    # 1. Full 4-frame exchange trace with NAV annotations
    print_exchange_trace(data_bytes=1000, data_mbps=54.0)

    # 2. NAV arithmetic table (matches prose example exactly)
    print_nav_table(data_mbps=54.0)

    # 3. Hidden-terminal collision simulation
    print_collision_table()

    # 4. Exposed-terminal qualitative analysis
    print_exposed_terminal_analysis()

    # 5. RTS/CTS overhead vs. frame size
    print_overhead_analysis()

    # 6. MACA vs. 802.11 comparison table
    print_maca_vs_80211()

    print()
    print("=" * 72)
    print("Done.")


if __name__ == "__main__":
    main()
