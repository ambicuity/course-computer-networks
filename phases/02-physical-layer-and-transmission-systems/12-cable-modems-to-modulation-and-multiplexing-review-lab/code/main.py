#!/usr/bin/env python3
"""DOCSIS cable-modem physical-layer model: FDM, QAM, minislots, ranging, ALOHA.

This stdlib-only program turns the qualitative description of a DOCSIS cable
plant (Tanenbaum, Computer Networks, 5e, sec. 2.8.4-2.8.5) into runnable
arithmetic and a small contention simulator. It demonstrates the four
multiplexing primitives a cable modem stacks on one shared coax:

    FDM   -> 6-MHz (US) / 8-MHz (Euro) channels         channel_bitrate()
    QAM   -> bits per symbol from constellation order    bits_per_symbol()
    TDM   -> upstream minislots, consecutive bursts      MinislotSchedule
    ALOHA -> contention on the shared request minislot   simulate_slotted_aloha()

Plus the ranging exchange (ranging_offset) that lets a modem pre-advance its
transmit timing so bursts land in their assigned minislots at the CMTS.

Run: python3 main.py
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

# --- physical constants for an HFC coax plant -------------------------------
PROP_DELAY_US_PER_KM = 5.0          # ~5 microseconds per km in coax/fiber
US_CHANNEL_HZ = 6_000_000           # North American DOCSIS channel width
EURO_CHANNEL_HZ = 8_000_000         # EuroDOCSIS channel width
SYMBOLS_PER_HZ = 1.0                # ~1 symbol/s per Hz after pulse shaping (approx.)
MINISLOT_PAYLOAD_BYTES = 8          # typical upstream minislot payload
DOWNSTREAM_CELL_BYTES = 204         # MPEG-2 cell: 184 payload + Reed-Solomon FEC
DOWNSTREAM_PAYLOAD_BYTES = 184      # net user payload per downstream cell
BACKOFF_WINDOW_CAP = 1024           # ceiling on the binary-exponential window

# constellation order M -> name
CONSTELLATIONS = {
    4: "QPSK",
    16: "QAM-16",
    64: "QAM-64",
    128: "QAM-128",
    256: "QAM-256",
}


def bits_per_symbol(order: int) -> int:
    """Return log2(order) bits carried per QAM symbol (e.g. QAM-64 -> 6)."""
    if order <= 0 or (order & (order - 1)) != 0:
        raise ValueError(f"constellation order {order} must be a power of two")
    return int(math.log2(order))


def channel_bitrate(bandwidth_hz: int, order: int, fec_efficiency: float = 1.0) -> float:
    """Raw (or net, with fec_efficiency<1) channel bit rate in bits/second.

    rate = symbol_rate * bits_per_symbol * fec_efficiency
    where symbol_rate ~= bandwidth * SYMBOLS_PER_HZ.
    """
    if not 0.0 < fec_efficiency <= 1.0:
        raise ValueError("fec_efficiency must be in (0, 1]")
    symbol_rate = bandwidth_hz * SYMBOLS_PER_HZ
    return symbol_rate * bits_per_symbol(order) * fec_efficiency


def ranging_offset(distance_km: float) -> float:
    """Required timing advance (microseconds) for a modem at distance_km.

    The modem must transmit early by the one-way propagation delay so its burst
    arrives aligned with the CMTS minislot boundary. The ranging RTT it
    measures is twice this value.
    """
    if distance_km < 0:
        raise ValueError("distance cannot be negative")
    return distance_km * PROP_DELAY_US_PER_KM


def minislots_for_packet(packet_bytes: int, framing_overhead: float = 0.10) -> int:
    """Number of consecutive upstream minislots a packet burst needs."""
    if packet_bytes <= 0:
        raise ValueError("packet must be a positive size")
    effective = packet_bytes * (1.0 + framing_overhead)
    return math.ceil(effective / MINISLOT_PAYLOAD_BYTES)


@dataclass
class Grant:
    """A CMTS grant of consecutive minislots to one modem."""

    modem_id: str
    start_slot: int
    num_slots: int

    @property
    def end_slot(self) -> int:
        return self.start_slot + self.num_slots - 1


@dataclass
class MinislotSchedule:
    """A single upstream TDM round of `total_slots` minislots.

    The CMTS scheduler hands out consecutive runs of minislots. This models the
    request/grant cycle: each modem requests N minislots and is granted a
    contiguous block if room remains.
    """

    total_slots: int
    grants: list[Grant] = field(default_factory=list)
    _next_free: int = 0

    def request(self, modem_id: str, num_slots: int) -> Grant | None:
        """Grant `num_slots` consecutive minislots, or None if the round is full."""
        if num_slots <= 0:
            raise ValueError("must request at least one minislot")
        if self._next_free + num_slots > self.total_slots:
            return None
        grant = Grant(modem_id, self._next_free, num_slots)
        self.grants.append(grant)
        self._next_free += num_slots
        return grant

    def utilization(self) -> float:
        used = sum(g.num_slots for g in self.grants)
        return used / self.total_slots if self.total_slots else 0.0


def simulate_slotted_aloha(
    num_modems: int,
    request_prob: float,
    rounds: int,
    seed: int = 1,
) -> dict[str, float]:
    """Slotted ALOHA with binary exponential backoff on the request channel.

    Each modem, when not backed off, transmits in the current request minislot
    with probability `request_prob`. If two or more transmit they collide; each
    doubles its random backoff window (capped) and retries later. Returns the
    offered load, throughput (successes/round), and collision rate.
    """
    rng = random.Random(seed)
    backoff = [0] * num_modems          # remaining backoff slots per modem
    window = [1] * num_modems           # backoff window, doubles on collision
    successes = 0
    collisions = 0

    for _ in range(rounds):
        contenders: list[int] = []
        for m in range(num_modems):
            if backoff[m] > 0:
                backoff[m] -= 1
                continue
            if rng.random() < request_prob:
                contenders.append(m)

        if len(contenders) == 1:
            window[contenders[0]] = 1   # success resets the backoff window
            successes += 1
        elif len(contenders) >= 2:
            collisions += 1
            for m in contenders:
                window[m] = min(window[m] * 2, BACKOFF_WINDOW_CAP)
                backoff[m] = rng.randint(0, window[m] - 1)

    attempts = successes + collisions
    return {
        "offered_load": num_modems * request_prob,
        "throughput": successes / rounds,
        "collision_rate": (collisions / attempts) if attempts else 0.0,
    }


def main() -> None:
    print("=" * 64)
    print("DOCSIS cable-modem physical-layer model")
    print("=" * 64)

    # 1) QAM constellation ladder ------------------------------------------
    print("\n[1] QAM constellation ladder (bits per symbol = log2(M))")
    for order in sorted(CONSTELLATIONS):
        print(f"    {CONSTELLATIONS[order]:>8}  M={order:<4} -> "
              f"{bits_per_symbol(order)} bits/symbol")

    # 2) FDM channel rates -------------------------------------------------
    print("\n[2] Downstream channel bit rate (FDM + QAM)")
    for order, fec in ((64, 0.75), (256, 0.81)):
        raw = channel_bitrate(US_CHANNEL_HZ, order) / 1e6
        net = channel_bitrate(US_CHANNEL_HZ, order, fec) / 1e6
        print(f"    6 MHz {CONSTELLATIONS[order]:>8}: raw ~{raw:5.1f} Mbps, "
              f"net ~{net:5.1f} Mbps")
    euro = channel_bitrate(EURO_CHANNEL_HZ, 64) / 1e6
    print(f"    8 MHz   QAM-64 (EuroDOCSIS): raw ~{euro:5.1f} Mbps  (~1/3 larger)")

    print("\n    Upstream stays conservative (QPSK..QAM-128) -- funneled RF noise")
    up = channel_bitrate(US_CHANNEL_HZ, 4) / 1e6
    print(f"    6 MHz   QPSK upstream: raw ~{up:5.1f} Mbps  (asymmetry vs downstream)")

    # 3) Ranging -----------------------------------------------------------
    print("\n[3] Ranging: per-modem timing advance (set before any TX)")
    for name, dist in (("modem-near", 2.0), ("modem-far", 14.0)):
        adv = ranging_offset(dist)
        print(f"    {name:>11}: {dist:4.1f} km -> advance {adv:5.1f} us "
              f"(RTT {2 * adv:.1f} us)")
    print("    Without ranging, near+far bursts overlap at the CMTS slot boundary.")

    # 4) Minislot scheduling ----------------------------------------------
    print("\n[4] Upstream minislot schedule (TDM, 8-byte payload/slot)")
    sched = MinislotSchedule(total_slots=64)
    requests = (("modem-A", 1500), ("modem-B", 64), ("modem-C", 500))
    for modem, pkt in requests:
        n = minislots_for_packet(pkt)
        grant = sched.request(modem, n)
        if grant:
            print(f"    {modem}: {pkt:>4}B packet -> {n:>3} minislots "
                  f"[{grant.start_slot:>2}..{grant.end_slot:>2}]")
        else:
            print(f"    {modem}: {pkt:>4}B packet -> {n} minislots DENIED (round full)")
    print(f"    round utilization: {sched.utilization() * 100:.0f}%")
    print(f"    downstream uses fixed {DOWNSTREAM_CELL_BYTES}B cells "
          f"({DOWNSTREAM_PAYLOAD_BYTES}B payload, STDM, no minislots)")

    # 5) Contention simulation --------------------------------------------
    print("\n[5] Request channel: slotted ALOHA + binary exponential backoff")
    print("    modems  offered_load  throughput  collision_rate")
    for n in (5, 10, 20, 40, 80):
        r = simulate_slotted_aloha(num_modems=n, request_prob=0.10, rounds=20_000)
        print(f"    {n:>6}  {r['offered_load']:>12.2f}  "
              f"{r['throughput']:>10.3f}  {r['collision_rate']:>14.3f}")
    print("    Throughput peaks near offered load ~1, then backoff collapses ->")
    print("    this is the evening upstream/VoIP stall from The Problem.")

    print("\nDone. Each block maps one DOCSIS mechanism to one multiplexing primitive.")


if __name__ == "__main__":
    main()
