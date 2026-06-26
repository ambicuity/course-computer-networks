"""Social Issues, Net Neutrality, and Censorship -- runnable models.

This module has no third-party dependencies and makes no network calls.
It models the mechanisms the lesson discusses:

  1. IPv4 TOS/DSCP parsing (RFC 2474) -- the 6-bit field a net-neutrality
     violator rewrites to demote a flow.
  2. A token-bucket traffic shaper/policek that reproduces the ``L/R``
     inter-packet gap a discriminating scheduler imposes.
  3. classify_violation() -- the decision rule that distinguishes shaping
     (timing changes, header intact) from DPI-driven DSCP rewriting
     (header changes) from hard policing (drops without ECN).
  4. DNS poisoning race (RFC 1035 TxID, RFC 5452 source-port randomization):
     on-path wins deterministically, off-path is probabilistic.
  5. TCP RST injection acceptance test (RFC 793 section 3.4): a forged
     RST is accepted only if its sequence number falls inside the
     receiver's receive window [RCV.NXT, RCV.NXT + RCV.WND).

Run with: ``python3 main.py``
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# 1. IPv4 TOS / DSCP parsing (RFC 2474)
# ---------------------------------------------------------------------------

DSCP_NAMES = {
    0: "CS0",
    46: "EF",    # Expedited Forwarding, RFC 3246
    34: "AF41",  # Assured Forwarding, RFC 2597
    8: "CS1", 10: "AF11", 12: "AF12", 14: "AF13",
    16: "CS2", 18: "AF21", 20: "AF22", 22: "AF23",
    24: "CS3", 26: "AF31", 28: "AF32", 30: "AF33",
    32: "CS4", 36: "AF42", 38: "AF43",
    40: "CS5", 48: "CS6", 56: "CS7",
}


@dataclass
class DSCPMarker:
    """The 6-bit DSCP and 2-bit ECN extracted from the IPv4 TOS byte."""

    dscp: int
    ecn: int
    dscp_name: str

    @classmethod
    def parse_tos(cls, tos_byte: int) -> "DSCPMarker":
        if not 0 <= tos_byte <= 0xFF:
            raise ValueError("TOS byte must be an 8-bit value")
        dscp = (tos_byte >> 2) & 0x3F
        ecn = tos_byte & 0x03
        return cls(dscp=dscp, ecn=ecn, dscp_name=DSCP_NAMES.get(dscp, f"UNKNOWN({dscp})"))

    def to_byte(self) -> int:
        return ((self.dscp & 0x3F) << 2) | (self.ecn & 0x03)


# ---------------------------------------------------------------------------
# 2. Token bucket -- the math of bandwidth discrimination
# ---------------------------------------------------------------------------

@dataclass
class TokenBucket:
    """A classic token bucket: capacity ``burst`` bytes, refill ``rate`` B/s.

    ``forward()`` returns the (possibly delayed) departure time in
    seconds.  If ``allow_drop`` is False (shaper) the packet is delayed
    until tokens exist; if True (policer) it returns None to mean
    "dropped" (no ECN signal).
    """

    rate: int               # bytes per second
    burst: int              # bucket capacity in bytes
    tokens: float = field(init=False)
    last_time: float = field(init=False)
    allow_drop: bool = False

    def __post_init__(self) -> None:
        if self.rate <= 0:
            raise ValueError("rate must be positive")
        if self.burst <= 0:
            raise ValueError("burst must be positive")
        self.tokens = float(self.burst)
        self.last_time = 0.0

    def _refill(self, now: float) -> None:
        elapsed = max(0.0, now - self.last_time)
        self.tokens = min(float(self.burst), self.tokens + elapsed * self.rate)
        self.last_time = now

    def forward(self, packet_len: int, now: float) -> float | None:
        """Return departure time (shaper) or None (policer drop)."""
        if now < self.last_time:
            now = self.last_time
        self._refill(now)
        if self.tokens >= packet_len:
            self.tokens -= packet_len
            return now
        if self.allow_drop:
            return None  # policer: hard drop, no ECN signal
        # shaper: wait until enough tokens accrue
        deficit = packet_len - self.tokens
        wait = deficit / self.rate
        self.tokens = 0.0
        self.last_time = now + wait
        return now + wait


def replay_trace(
    arrivals: list[tuple[float, int]],
    rate: int,
    burst: int,
) -> list[tuple[float, float]]:
    """Replay (arrival_time, packet_len) pairs through a shaper bucket.

    Returns [(arrival, departure)].   The inferred inter-packet gap at the
    egress reveals the shaping rate.
    """
    bucket = TokenBucket(rate=rate, burst=burst, allow_drop=False)
    departures: list[tuple[float, float]] = []
    for arrival, length in arrivals:
        dep = bucket.forward(length, arrival)
        departures.append((arrival, dep if dep is not None else arrival))
    return departures


def infer_rate(departures: list[tuple[float, float]], packet_len: int) -> float:
    """Infer the shaping rate ``R`` from the steady-state inter-departure gap.

    For a saturated bucket, gap ~= packet_len / R.
    """
    if len(departures) < 2:
        return float("inf")
    gaps = [
        departures[i + 1][1] - departures[i][1]
        for i in range(len(departures) - 1)
        if departures[i + 1][1] > departures[i][1]
    ]
    if not gaps:
        return float("inf")
    avg_gap = sum(gaps) / len(gaps)
    return packet_len / avg_gap if avg_gap > 0 else float("inf")


# ---------------------------------------------------------------------------
# 3. classify_violation -- shaping vs DSCP rewrite vs policer vs neutral
# ---------------------------------------------------------------------------

@dataclass
class CapturedPacket:
    pkt_id: int
    arrival: float
    departure: float
    tos_byte: int
    dropped: bool = False
    ecn_marked: bool = False


def classify_violation(
    ingress: list[CapturedPacket],
    egress: list[CapturedPacket],
) -> str:
    """Decide the discrimination mechanism from two capture points.

    Decision rule (encoded order matters):

      - any pkt_id present at ingress but missing at egress, with no ECN
        mark  -> POLICER_DROP
      - DSCP differs for the same pkt_id between the two captures
        -> DSCP_REWRITE (a middlebox mutated the header)
      - DSCP stable but inter-arrival gap stretches as ``L/R``
        -> SHAPING (token bucket at the scheduler)
      - none of the above  -> NEUTRAL
    """
    egress_by_id = {p.pkt_id: p for p in egress}

    # 1. Policer drops (silent, no ECN signal)?
    egress_ids = {p.pkt_id for p in egress}
    silent_drops = [
        p for p in ingress
        if p.pkt_id not in egress_ids and not p.ecn_marked
    ]
    if silent_drops:
        return "POLICER_DROP"

    # 2. DSCP rewrite between the two captures?
    for p in ingress:
        e = egress_by_id.get(p.pkt_id)
        if e is not None:
            in_dscp = DSCPMarker.parse_tos(p.tos_byte).dscp
            out_dscp = DSCPMarker.parse_tos(e.tos_byte).dscp
            if in_dscp != out_dscp:
                return "DSCP_REWRITE"

    # 3. Shaping -- DSCP stable but timing stretched?
    common = sorted(
        (p for p in ingress if p.pkt_id in egress_by_id),
        key=lambda p: p.arrival,
    )
    gaps_in: list[float] = []
    gaps_out: list[float] = []
    for i in range(len(common) - 1):
        a, b = common[i], common[i + 1]
        gaps_in.append(b.arrival - a.arrival)
        gaps_out.append(
            egress_by_id[b.pkt_id].departure - egress_by_id[a.pkt_id].departure
        )
    if gaps_in and gaps_out:
        avg_in = sum(gaps_in) / len(gaps_in)
        avg_out = sum(gaps_out) / len(gaps_out)
        if avg_in > 1e-9 and avg_out / avg_in > 2.0:
            return "SHAPING"

    return "NEUTRAL"


# ---------------------------------------------------------------------------
# 4. DNS poisoning race (RFC 1035 TxID, RFC 5452)
# ---------------------------------------------------------------------------

@dataclass
class DNSPoisoner:
    """Models a DNS forgery attempt against a resolver.

    On-path (the censor observes the query wire) wins deterministically
    because it can read the TxID and source port and reply first.
    Off-path it must guess both: the TxID is 16 bits and with RFC 5452
    source-port randomization the ephemeral port adds ~16 more bits.
    """

    on_path: bool
    port_range_bits: int = 16

    def race(
        self,
        txid: int,
        legit_rtt: float,
        forged_rtt: float,
    ) -> bool:
        """Return True if the forged answer wins the race and is accepted.

        ``legit_rtt`` / ``forged_rtt`` are the response travel times in
        seconds; whichever arrives first wins.  On-path the forger knows
        the exact TxID (and could read the port).  Off-path it must guess
        the TxID (16 bits) and the port (``port_range_bits`` bits) *and*
        arrive first.
        """
        forged_first = forged_rtt < legit_rtt
        if not forged_first:
            return False
        if self.on_path:
            return True
        guess_prob = (1.0 / 2**16) * (1.0 / 2**self.port_range_bits)
        return random.random() < guess_prob


# ---------------------------------------------------------------------------
# 5. TCP RST injection (RFC 793 section 3.4)
# ---------------------------------------------------------------------------

def rst_accepted(rcv_nxt: int, rcv_wnd: int, seg_seq: int) -> bool:
    """RFC 793 section 3.4 RST acceptance check.

    A forged RST is accepted when ``SEG.SEQ`` equals ``RCV.NXT`` or falls
    strictly inside the receive window ``(RCV.NXT, RCV.NXT + RCV.WND)``.
    Outside that range the receiver silently discards it -- the defence
    an off-path attacker cannot easily beat.
    """
    if seg_seq == rcv_nxt:
        return True
    return rcv_nxt < seg_seq < rcv_nxt + rcv_wnd


@dataclass
class RSTInjector:
    rcv_nxt: int
    rcv_wnd: int

    def inject(self, forged_seq: int) -> bool:
        return rst_accepted(self.rcv_nxt, self.rcv_wnd, forged_seq)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def main() -> None:
    random.seed(42)
    print("=" * 72)
    print("1. DSCP parsing -- the field a violator rewrites")
    print("=" * 72)
    for tos in (0xB8, 0x88, 0x00):  # EF=46<<2, AF41=34<<2, CS0=0
        m = DSCPMarker.parse_tos(tos)
        print(f"  TOS byte 0x{tos:02X} -> DSCP={m.dscp:2d} ({m.dscp_name})  ECN={m.ecn}")

    print()
    print("=" * 72)
    print("2. Token bucket -- favored vs shaped flow (packet_len=1500 bytes)")
    print("=" * 72)
    packet_len = 1500
    # All packets arrive simultaneously (a saturated ingress) so the bucket
    # drains on the first packet and every subsequent packet must wait L/R
    # tokens -- that steady-state gap is the signature of the shaping rate.
    arrivals = [(0.0, packet_len) for _ in range(8)]
    for label, rate, burst in [("favored (10 MB/s)", 10_000_000, packet_len),
                               ("shaped  (1 MB/s) ",  1_000_000, packet_len)]:
        deps = replay_trace(arrivals, rate, burst)
        inf = infer_rate(deps, packet_len)
        gap = deps[1][1] - deps[0][1]
        print(f"  {label}: inferred rate={inf/1e6:6.2f} MB/s "
              f"egress gap={gap*1e6:7.1f} us")

    print()
    print("=" * 72)
    print("3. classify_violation -- which mechanism is in play?")
    print("=" * 72)
    # Scenario A: DSCP rewrite mid-path (EF -> CS0)
    ing = [CapturedPacket(i, i * 0.001, i * 0.001, 0xB8) for i in range(5)]
    eg = [CapturedPacket(i, i * 0.001, i * 0.001, 0x00) for i in range(5)]
    print(f"  Scenario A (DSCP EF->CS0):  {classify_violation(ing, eg)}")

    # Scenario B: shaping -- timing stretched 15x, DSCP stable
    ing = [CapturedPacket(i, i * 0.0001, i * 0.0001, 0x00) for i in range(5)]
    eg = [CapturedPacket(i, i * 0.0001, i * 0.0015, 0x00) for i in range(5)]
    print(f"  Scenario B (timing 15x):     {classify_violation(ing, eg)}")

    # Scenario C: neutral -- same DSCP, same cadence
    ing = [CapturedPacket(i, i * 0.0001, i * 0.0001, 0x00) for i in range(5)]
    eg = [CapturedPacket(i, i * 0.0001, i * 0.0001, 0x00) for i in range(5)]
    print(f"  Scenario C (neutral):        {classify_violation(ing, eg)}")

    # Scenario D: policer drop -- packet 3 missing, no ECN
    ing = [CapturedPacket(i, i * 0.0001, i * 0.0001, 0x00) for i in range(5)]
    eg = [CapturedPacket(i, i * 0.0001, i * 0.0001, 0x00) for i in range(5) if i != 3]
    print(f"  Scenario D (silent drop):    {classify_violation(ing, eg)}")

    print()
    print("=" * 72)
    print("4. DNS poisoning race (TxID + source port)")
    print("=" * 72)
    poiso_on = DNSPoisoner(on_path=True)
    poiso_off = DNSPoisoner(on_path=False)
    txid = 0x4A2B
    print(f"  query TxID=0x{txid:04X}")
    for label, poisoner, ftt, ltt in [
        ("on-path,  forged first", poiso_on,  0.020, 0.080),
        ("on-path,  legit first",  poiso_on,  0.080, 0.020),
        ("off-path, forged first", poiso_off, 0.020, 0.080),
    ]:
        wins = sum(
            poisoner.race(txid, legit_rtt=ltt, forged_rtt=ftt)
            for _ in range(1000)
        )
        print(f"  {label}: accepted {wins}/1000 forged answers")

    print()
    print("=" * 72)
    print("5. TCP RST injection -- RFC 793 section 3.4 window check")
    print("=" * 72)
    injector = RSTInjector(rcv_nxt=1_000_000, rcv_wnd=65_535)
    for seq in (1_000_000, 1_000_001, 1_065_535, 1_200_000, 999_999):
        accepted = injector.inject(seq)
        verdict = "ACCEPTED -> connection dies" if accepted else "discarded (out of window)"
        print(f"  forged RST seq={seq:>10d}: {verdict}")
    print(f"  window of acceptance: [RCV.NXT, RCV.NXT + RCV.WND) = "
          f"[{injector.rcv_nxt}, {injector.rcv_nxt + injector.rcv_wnd})")

    print()
    print("Done. See assets/social-issues-network-neutrality.svg for the visuals.")


if __name__ == "__main__":
    main()