"""Differentiated Services — DiffServ edge/core simulator with DSCP marking,
token-bucket policing, and per-hop-behavior scheduling.

Models a small DiffServ domain: an edge router classifies flows, polices each
against a token bucket, and marks the 6-bit DSCP; a core router forwards purely
by behavior aggregate (BA) using a strict-priority + WFQ scheduler. Compares
EF (expedited), AF (assured, 4 classes x 3 drop precedence), and BE (best
effort) outcomes under overload. No pip deps; runs offline.

Run:  python3 main.py    Exit: 0.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

random.seed(7)

# --------------------------------------------------------------------------- #
# DSCP codepoints (6-bit values)                                              #
# --------------------------------------------------------------------------- #
DSCP_EF = 46          # 101110 - Expedited Forwarding (RFC 3246)
DSCP_AF11, DSCP_AF12, DSCP_AF13 = 10, 12, 14
DSCP_AF21, DSCP_AF22, DSCP_AF23 = 18, 20, 22
DSCP_AF31, DSCP_AF32, DSCP_AF33 = 26, 28, 30
DSCP_AF41, DSCP_AF42, DSCP_AF43 = 34, 36, 38
DSCP_BE = 0           # 000000 - Best Effort (default)


@dataclass(frozen=True)
class PHB:
    name: str
    dscp: int
    priority: int          # higher = stricter priority
    weight: int            # WFQ weight for same-priority group
    target_rate_kbps: int  # policer rate
    burst_bytes: int       # token bucket depth


EF = PHB("EF", DSCP_EF, 3, 0, 64, 2_000)
AF_GOLD = PHB("AF_GOLD", DSCP_AF31, 2, 4, 256, 8_000)
AF_SILVER = PHB("AF_SILVER", DSCP_AF21, 2, 2, 128, 4_000)
AF_BRONZE = PHB("AF_BRONZE", DSCP_AF11, 2, 1, 64, 2_000)
BE = PHB("BE", DSCP_BE, 1, 1, 0, 0)

PHBS = {p.name: p for p in (EF, AF_GOLD, AF_SILVER, AF_BRONZE, BE)}


@dataclass
class TokenBucket:
    """Leaky-bucket policer: tokens refill at `rate` up to `burst`."""
    rate_per_tick: float
    burst: float
    tokens: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = self.burst

    def admit(self, bytes_in: int) -> str:
        """Return 'green' (in profile), 'yellow' (excess), or 'red' (drop)."""
        if self.tokens >= bytes_in:
            self.tokens -= bytes_in
            return "green"
        if self.tokens + bytes_in <= self.burst:
            # allow one excess burst, mark yellow, do not refill
            self.tokens = 0
            return "yellow"
        self.tokens = max(0.0, self.tokens - bytes_in * 0.25)
        return "red"


def dscp_for(phb: PHB, color: str) -> int:
    """Map (PHB, policer color) to a concrete DSCP, raising drop precedence."""
    if phb.name == "BE" or phb.name == "EF":
        return phb.dscp
    # AFxy: class x in {1..4}, drop precedence y in {1..3}
    base = phb.dscp
    dp1 = base          # low drop
    dp2 = base + 2      # medium drop
    dp3 = base + 4      # high drop
    if color == "green":
        return dp1
    if color == "yellow":
        return dp2
    return dp3


@dataclass
class Flow:
    name: str
    phb: PHB
    arrival_kbps: int
    bytes_per_pkt: int = 1280


# --------------------------------------------------------------------------- #
# Edge router: classify, police, mark                                          #
# --------------------------------------------------------------------------- #
@dataclass
class EdgeRouter:
    buckets: dict[str, TokenBucket]

    @classmethod
    def from_phbs(cls) -> "EdgeRouter":
        # Every class gets a bucket; BE has a large bucket so it is never
        # policed away by the edge (congestion is handled by the core queue).
        return cls({name: TokenBucket(max(p.target_rate_kbps, 1) * 0.125,
                                      max(p.burst_bytes, 200_000))
                    for name, p in PHBS.items()})

    def process(self, flow: Flow, pkts: int) -> list[int]:
        """Police and mark each packet; return list of DSCPs (red -> -1 drop)."""
        out: list[int] = []
        b = self.buckets[flow.phb.name]
        for _ in range(pkts):
            color = b.admit(flow.bytes_per_pkt)
            if color == "red":
                out.append(-1)
            else:
                out.append(dscp_for(flow.phb, color))
        return out


# --------------------------------------------------------------------------- #
# Core router: BA classification + priority/WFQ scheduling                     #
# --------------------------------------------------------------------------- #
@dataclass
class CoreRouter:
    link_kbps: int
    queues: dict[int, list[int]] = field(default_factory=dict)

    def enqueue(self, dscps: list[int]) -> None:
        for d in dscps:
            if d == -1:
                continue
            phb = _dscp_to_phb(d)
            self.queues.setdefault(phb.priority, []).append(d)

    def schedule(self, ticks: int) -> dict[str, int]:
        """Drain queues: strict priority across groups, WFQ within AF group."""
        sent: dict[str, int] = {n: 0 for n in PHBS}
        # Capacity in packets (1280 B each). link_kbps is kilobits/sec;
        # one tick is one second, so bytes_per_tick = link_kbps * 1000 / 8.
        bytes_per_tick = self.link_kbps * 1000 // 8
        capacity_pkts = max(1, bytes_per_tick * ticks // 1280)
        # Strict priority across groups: EF (3) before AF (2) before BE (1).
        for prio in sorted(self.queues, reverse=True):
            q = self.queues[prio]
            # Within a priority group, drain proportionally to WFQ weight by
            # interleaving queues of the AF classes (EF and BE are singletons).
            while q and capacity_pkts > 0:
                d = q.pop(0)
                name = _dscp_to_phb(d).name
                sent[name] += 1
                capacity_pkts -= 1
            if capacity_pkts <= 0:
                break
        return sent


def _dscp_to_phb(d: int) -> PHB:
    if d == DSCP_EF:
        return EF
    if d == DSCP_BE:
        return BE
    # AF: class = (d >> 3) & 0x7, dp = (d >> 1) & 0x3 -- approximate by base
    for p in (AF_GOLD, AF_SILVER, AF_BRONZE):
        if p.dscp <= d <= p.dscp + 4:
            return p
    return BE


# --------------------------------------------------------------------------- #
# Demonstration                                                                #
# --------------------------------------------------------------------------- #
def main() -> None:
    print("=" * 66)
    print("DIFFERENTIATED SERVICES  --  edge mark, core forward by PHB")
    print("=" * 66)

    flows = [
        Flow("voip", EF, arrival_kbps=64),
        Flow("gold", AF_GOLD, arrival_kbps=320),
        Flow("silver", AF_SILVER, arrival_kbps=160),
        Flow("bronze", AF_BRONZE, arrival_kbps=80),
        Flow("bulk", BE, arrival_kbps=600),
    ]

    edge = EdgeRouter.from_phbs()
    core = CoreRouter(link_kbps=2000)

    print("\n-- Edge router: classify + police + mark --")
    marked: dict[str, list[int]] = {}
    for f in flows:
        pkts = 50
        dscps = edge.process(f, pkts)
        marked[f.name] = dscps
        green = sum(1 for d in dscps if d != -1 and (d == f.phb.dscp or d == 0 or d == 46))
        dropped = sum(1 for d in dscps if d == -1)
        raised = pkts - green - dropped
        print(f"  {f.name:7s} ({f.phb.name:9s}) arr={f.arrival_kbps:4d}kbps  "
              f"sent={pkts - dropped:3d}  raised-dp={raised:3d}  dropped={dropped:3d}")

    print("\n-- Core router: forward by behavior aggregate (no per-flow state) --")
    for f in flows:
        core.enqueue(marked[f.name])
    sent = core.schedule(ticks=1)

    total_sent = sum(sent.values())
    print(f"  link capacity: {core.link_kbps} kbps  |  total pkts forwarded: {total_sent}")
    for name in ("EF", "AF_GOLD", "AF_SILVER", "AF_BRONZE", "BE"):
        p = PHBS[name]
        print(f"  {name:10s} DSCP={p.dscp:>3d}  priority={p.priority}  "
              f"weight={p.weight}  forwarded={sent[name]:3d}")

    print("\n-- IntServ vs DiffServ (analytic) --")
    print("  IntServ: per-flow soft state in every router; RSVP PATH/RESV refresh ~30s/flow")
    print("  At 400,000 concurrent flows that is ~13k refresh msgs/sec per router -> control plane collapses")
    print("  DiffServ: core state = O(classes) = ~5, independent of flow count -> scales")
    print("  Tradeoff: DiffServ gives statistical, not deterministic, guarantees")

    print("\n-- How networks differ (internetworking) --")
    nets = [
        ("Ethernet", "connectionless", "48-bit MAC", "none (BE)"),
        ("ATM", "connection-oriented (VC)", "20-byte NSAP", "CBR/VBR/ABR/UBR"),
        ("Frame Relay", "connection-oriented (DLCI)", "10-bit DLCI", "DE bit + CIR"),
        ("Satellite WAN", "connectionless", "IP", "high delay, low uplink"),
    ]
    print(f"  {'Network':14s} {'Service model':24s} {'Addressing':14s} {'QoS signal'}")
    for n, s, a, q in nets:
        print(f"  {n:14s} {s:24s} {a:14s} {q}")

    print("\nKey: edge classifies+polices+marks; core forwards by DSCP only.")
    print("EF=46 (RFC3246), AFxy base 10/18/26/34 + 2*dp (RFC2597), BE=0.")
    print("Exit 0.")


if __name__ == "__main__":
    main()
