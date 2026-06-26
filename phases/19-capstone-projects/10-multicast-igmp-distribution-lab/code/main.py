#!/usr/bin/env python3
"""Capstone 10: Multicast IGMP Distribution Lab (PIM-SM + IGMPv3).

Models a 5-router, 4-LAN sparse-mode multicast network with IGMPv3 host
joins, Rendezvous-Point-rooted shared tree, source registration, SPT
switchover above 1 Mbps, pruning on last-receiver-leave, and a
unicast-vs-multicast per-link bandwidth comparison.

Run:  python3 main.py
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum


class IgmpType(Enum):
    JOIN = "Membership Report (Join)"
    LEAVE = "Leave Group"


class PimType(Enum):
    JOIN = "Join"; PRUNE = "Prune"
    REGISTER = "Register"; REGISTER_STOP = "Register-Stop"


@dataclass
class Lan:
    name: str; dr: str
    receivers: list[str] = field(default_factory=list)
    active_groups: set[str] = field(default_factory=set)


@dataclass
class Receiver:
    name: str; lan: str
    subscribed: set[str] = field(default_factory=set)


@dataclass
class Source:
    name: str; lan: str; group: str
    rate_mbps: float = 0.0; is_sending: bool = False


@dataclass
class Router:
    name: str; is_rp: bool = False; is_dr: bool = False
    shared_tree: dict[str, dict] = field(default_factory=dict)
    source_tree: dict[str, dict] = field(default_factory=dict)


@dataclass
class Msg:
    kind: str; src: str; dst: str; group: str
    src_addr: str = ""; t: float = 0.0; note: str = ""


# Fixed topology: LAN1--R1--R3(RP)--R2--LAN2 ; R3--R4--LAN3(sources) ; R4--R5--LAN4
ADJ = {"R1": ["LAN1", "R3"], "R2": ["LAN2", "R3"], "R3": ["R1", "R2", "R4"],
       "R4": ["R3", "R5", "LAN3"], "R5": ["R4", "LAN4"]}
RP, SPT_THRESHOLD_MBPS = "R3", 1.0
RECEIVER_PLAN = [(1, "LAN1"), (2, "LAN1"), (3, "LAN2"), (4, "LAN2"),
                 (5, "LAN4"), (6, "LAN4"), (7, "LAN3"), (8, "LAN3")]
SOURCES = {"S1": Source("S1", "LAN3", "239.1.1.1", 2.0),
           "S2": Source("S2", "LAN3", "239.1.1.1", 0.5),
           "S3": Source("S3", "LAN3", "239.2.2.2", 1.0)}


def path(src: str, dst: str) -> list[str]:
    """BFS shortest path over the fixed router adjacency."""
    if src == dst: return [src]
    prev: dict[str, str | None] = {src: None}
    q = deque([src])
    while q:
        n = q.popleft()
        for nb in ADJ.get(n, []):
            if nb not in prev and nb in ADJ:
                prev[nb] = n
                if nb == dst: q.clear(); break
                q.append(nb)
    if dst not in prev: return []
    out, cur = [], dst
    while cur is not None: out.append(cur); cur = prev[cur]
    return list(reversed(out))


def hops_emit(p: list[str], group: str, pim: list[Msg], t: float,
              src: str, note: str) -> None:
    """Append one PIM Join/Prune per router hop along path p."""
    rh = [h for h in p if h in ADJ]
    for i in range(len(rh) - 1):
        pim.append(Msg("PIM", rh[i], rh[i + 1], group, src_addr=src, t=t, note=note))


def build_topology() -> tuple[dict[str, Router], dict[str, Lan],
                              dict[str, Receiver], dict[str, Source]]:
    rs = {n: Router(n, is_dr=(n != "R3"), is_rp=(n == "R3")) for n in ADJ}
    ls = {f"LAN{i}": Lan(f"LAN{i}", {1: "R1", 2: "R2", 3: "R4", 4: "R5"}[i])
          for i in range(1, 5)}
    hs = {f"H{i}": Receiver(f"H{i}", lan) for i, lan in RECEIVER_PLAN}
    return rs, ls, hs, dict(SOURCES)


def igmp_join(h: Receiver, group: str, ls: dict[str, Lan], rs: dict[str, Router],
              igmp: list[Msg], pim: list[Msg], t: float) -> None:
    h.subscribed.add(group); lan = ls[h.lan]; lan.active_groups.add(group)
    if h.name not in lan.receivers: lan.receivers.append(h.name)
    igmp.append(Msg("IGMP", h.name, h.lan, group, t=t, note=IgmpType.JOIN.value))
    p = path(lan.dr, RP)
    hops_emit(p, group, pim, t, "", f"(*,{group}) join -> RP {RP}")
    for i in range(len(p) - 1):
        st = rs[p[i + 1]].shared_tree.setdefault(group, {"incoming": p[i], "outgoing": []})
        if p[i] not in st["outgoing"]: st["outgoing"].append(p[i])


def igmp_leave(h: Receiver, group: str, hs: dict[str, Receiver], ls: dict[str, Lan],
               rs: dict[str, Router], igmp: list[Msg], pim: list[Msg], t: float) -> None:
    h.subscribed.discard(group); lan = ls[h.lan]
    remaining = any(group in hs[r].subscribed for r in lan.receivers if r != h.name)
    igmp.append(Msg("IGMP", h.name, h.lan, group, t=t,
                    note=IgmpType.LEAVE.value + (" (others remain)" if remaining else "")))
    if remaining: return
    lan.active_groups.discard(group)
    hops_emit(path(lan.dr, RP), group, pim, t, "",
              f"(*,{group}) prune - no receivers on {lan.name}")
    rs[lan.dr].shared_tree.pop(group, None)


def register_source(src: Source, ls: dict[str, Lan], rs: dict[str, Router],
                    pim: list[Msg], t: float) -> None:
    src.is_sending = True; dr = ls[src.lan].dr
    pim.append(Msg("PIM", dr, RP, src.group, src_addr=src.name, t=t,
                   note=f"Register: {src.name}->RP, encapsulated first packet"))
    hops_emit(path(RP, dr), src.group, pim, t, src.name,
              f"({src.name},{src.group}) join RP->source")
    pim.append(Msg("PIM", RP, dr, src.group, src_addr=src.name, t=t + 0.05,
                   note="Register-Stop: (S,G) native path established"))


def spt_switchover(dr_name: str, group: str, src: Source, ls: dict[str, Lan],
                   rs: dict[str, Router], pim: list[Msg], t: float) -> bool:
    if src.rate_mbps < SPT_THRESHOLD_MBPS: return False
    p = path(dr_name, ls[src.lan].dr); key = f"({src.name},{group})"
    hops_emit(p, group, pim, t, src.name, f"SPT cutover: {key} join")
    for i in range(len(p) - 1):
        rs[p[i + 1]].source_tree[key] = {"incoming": p[i], "outgoing": [p[i]]}
    hops_emit(path(dr_name, RP), group, pim, t + 0.01, src.name,
              f"SPT active, prune (*,{group})")
    return True


def bandwidth_compare(ss: dict[str, Source], ls: dict[str, Lan], group: str) -> dict:
    """Per-link unicast replication vs multicast fan-out for a group.

    Unicast: source replicates one stream per receiver along its RPT path.
    Multicast: one copy per backbone link, summed across used links.
    """
    active = [s for s in ss.values() if s.group == group and s.is_sending]
    rate = sum(s.rate_mbps for s in active)
    active_lans = [l for l in ls.values() if group in l.active_groups]
    recv = sum(len(l.receivers) for l in active_lans)
    # Sum the per-link unicast load: rate * (#receivers downstream of each link).
    unicast_links: dict[tuple[str, str], int] = {}
    for lan in active_lans:
        p = path(lan.dr, RP)
        for i in range(len(p) - 1):
            if p[i] in ADJ and p[i + 1] in ADJ:
                k = (p[i], p[i + 1])
                unicast_links[k] = unicast_links.get(k, 0) + len(lan.receivers)
    unicast_total = rate * sum(unicast_links.values())
    # Multicast: one copy per used link, plus the source-LAN access link.
    multicast_total = rate * (len(unicast_links) + 1 if unicast_links else 0)
    saved = max(unicast_total - multicast_total, 0)
    return {"src": len(active), "lan": len(active_lans), "recv": recv, "rate": rate,
            "links": len(unicast_links), "uni": unicast_total, "multi": multicast_total,
            "saved": saved, "pct": (100 * saved / unicast_total) if unicast_total else 0.0}


def show(msgs: list[Msg]) -> None:
    for m in msgs:
        print(f"    t={m.t:.2f} {m.kind:<4} {m.src:>4}->{m.dst:<4} "
              f"group={m.group:<10} [{m.note}]")


def main() -> None:
    print("=" * 64)
    print("Capstone 10: Multicast IGMP Distribution Lab (PIM-SM + IGMPv3)")
    print("=" * 64)
    rs, ls, hs, ss = build_topology()
    print(f"\n  Topology: 5 routers, 4 LANs, RP={RP}, SPT threshold {SPT_THRESHOLD_MBPS} Mbps")
    print(f"  LAN1--R1--{RP}(RP)--R2--LAN2  |  R4--LAN3(sources)  |  R5--LAN4")

    igmp: list[Msg] = []; pim: list[Msg] = []; t = 0.0

    print("\n  --- Phase 1: IGMPv3 joins (H1@LAN1, H3@LAN2, H5@LAN4) ---")
    for h in ("H1", "H3", "H5"):
        igmp_join(hs[h], "239.1.1.1", ls, rs, igmp, pim, t); t += 0.01
    show(igmp); show(pim)

    print("\n  --- Phase 2: Source S1 (2.0 Mbps) registers with RP ---")
    pim.clear(); register_source(ss["S1"], ls, rs, pim, t); t += 0.1
    show(pim)

    print("\n  --- Phase 3: SPT switchover (R1 detects >1 Mbps) ---")
    pim.clear()
    if spt_switchover("R1", "239.1.1.1", ss["S1"], ls, rs, pim, t):
        print(f"    S1={ss['S1'].rate_mbps} Mbps > {SPT_THRESHOLD_MBPS} -> SPT cutover")
    t += 0.05; show(pim)

    print("\n  --- Phase 4: H5 leaves -> LAN4 branch pruned ---")
    igmp.clear(); pim.clear()
    igmp_leave(hs["H5"], "239.1.1.1", hs, ls, rs, igmp, pim, t); t += 0.01
    show(igmp); show(pim)

    print("\n  --- Phase 5: Unicast vs Multicast bandwidth ---")
    for g in ("239.1.1.1", "239.2.2.2"):
        bw = bandwidth_compare(ss, ls, g)
        print(f"  {g}: sources={bw['src']} LANs={bw['lan']} recv={bw['recv']} "
              f"rate={bw['rate']:.1f} Mbps  used_links={bw['links']}")
        print(f"    unicast={bw['uni']:.1f} Mbps  multicast={bw['multi']:.1f} Mbps  "
              f"savings={bw['saved']:.1f} Mbps ({bw['pct']:.0f}%)")

    print("\n  --- Final tree state ---")
    print(f"  {'Rtr':<5} {'(*,G)':<14} incoming outgoing")
    for n, r in sorted(rs.items()):
        for g, st in r.shared_tree.items():
            print(f"  {n:<5} {g:<14} <-{st['incoming']:<4} -> {','.join(st['outgoing'])}")
    print(f"  {'Rtr':<5} {'(S,G)':<16} incoming outgoing")
    for n, r in sorted(rs.items()):
        for k, st in r.source_tree.items():
            print(f"  {n:<5} {k:<16} <-{st['incoming']:<4} -> {','.join(st['outgoing'])}")

    print("\n  Summary: RP-rooted shared tree, native (S,G) cutover above 1 Mbps,")
    print("  prune on last-receiver-leave; multicast saves backbone vs unicast.")


if __name__ == "__main__":
    main()