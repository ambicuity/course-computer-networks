#!/usr/bin/env python3
"""OSPF link-state routing simulator (Tanenbaum section 5.6.6).

Stdlib only. Demonstrates the core OSPF mechanics:
  - LSA (Link State Advertisement) generation for each router in an AS.
  - Flooding of LSAs to build a shared link-state database.
  - Dijkstra shortest-path computation from a chosen root.
  - Two-level area hierarchy (backbone area 0 + a stub area).
  - Designated Router election on a broadcast network (highest priority
    wins, tie broken by highest Router ID).

The topology mirrors Fig. 5-64(a): R1-R2-R3-R4-R5 with LAN links.

Run:  python3 main.py
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Optional

INF = float("inf")


@dataclass
class Link:
    to: str
    weight: float
    to_area: str = "0"


@dataclass
class Router:
    router_id: str
    area: str = "0"
    priority: int = 1
    links: list[Link] = field(default_factory=list)

    def add_link(self, to: str, weight: float, area: str = "0") -> None:
        self.links.append(Link(to=to, weight=weight, to_area=area))


@dataclass
class LSA:
    origin: str
    area: str
    seq: int
    links: list[Link]


@dataclass
class LSDB:
    database: dict[str, LSA] = field(default_factory=dict)

    def install(self, lsa: LSA) -> bool:
        existing = self.database.get(lsa.origin)
        if existing is None or lsa.seq > existing.seq:
            self.database[lsa.origin] = lsa
            return True
        return False

    def graph(self) -> dict[str, dict[str, float]]:
        adj: dict[str, dict[str, float]] = {}
        for lsa in self.database.values():
            adj.setdefault(lsa.origin, {})
            for link in lsa.links:
                adj[lsa.origin][link.to] = link.weight
        return adj


def generate_lsa(router: Router, seq: int) -> LSA:
    return LSA(
        origin=router.router_id,
        area=router.area,
        seq=seq,
        links=list(router.links),
    )


def flood_lsas(routers: dict[str, Router], seq: int) -> LSDB:
    db = LSDB()
    for rid, router in routers.items():
        lsa = generate_lsa(router, seq)
        installed = db.install(lsa)
        print(f"  {rid}: LSA seq={lsa.seq} links={len(lsa.links)}  "
              f"installed={installed}")
    return db


def dijkstra(db: LSDB, root: str) -> tuple[dict[str, float], dict[str, Optional[str]]]:
    adj = db.graph()
    dist: dict[str, float] = {n: INF for n in adj}
    prev: dict[str, Optional[str]] = {n: None for n in adj}
    dist[root] = 0.0
    pq: list[tuple[float, str]] = [(0.0, root)]
    visited: set[str] = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        for v, w in adj.get(u, {}).items():
            nd = d + w
            if nd < dist.get(v, INF):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    return dist, prev


def build_path(prev: dict[str, Optional[str]], target: str) -> list[str]:
    path: list[str] = []
    node: Optional[str] = target
    while node is not None:
        path.append(node)
        node = prev[node]
    return list(reversed(path))


def elect_dr(routers: list[Router]) -> Router:
    best = routers[0]
    for r in routers[1:]:
        if r.priority > best.priority or (
            r.priority == best.priority and r.router_id > best.router_id
        ):
            best = r
    return best


def build_topology() -> dict[str, Router]:
    routers: dict[str, Router] = {}
    for rid, area in [("R1", "0"), ("R2", "0"), ("R3", "0"),
                      ("R4", "0"), ("R5", "0")]:
        routers[rid] = Router(router_id=rid, area=area, priority=1)
    routers["R1"].add_link("R2", 5)
    routers["R1"].add_link("R3", 1)
    routers["R2"].add_link("R1", 5)
    routers["R2"].add_link("R3", 4)
    routers["R2"].add_link("LAN2", 8)
    routers["R3"].add_link("R1", 1)
    routers["R3"].add_link("R2", 4)
    routers["R3"].add_link("R4", 0)
    routers["R3"].add_link("R5", 5)
    routers["R4"].add_link("R3", 0)
    routers["R4"].add_link("R5", 7)
    routers["R4"].add_link("LAN1", 4)
    routers["R5"].add_link("R3", 5)
    routers["R5"].add_link("R4", 7)
    routers["R5"].add_link("LAN4", 1)
    for lan in ("LAN1", "LAN2", "LAN4"):
        routers[lan] = Router(router_id=lan, area="0", priority=0)
    routers["LAN1"].add_link("R4", 4)
    routers["LAN2"].add_link("R2", 8)
    routers["LAN4"].add_link("R5", 1)
    return routers


def main() -> None:
    routers = build_topology()
    print("=" * 64)
    print("OSPF LSA Generation  --  Tanenbaum 5.6.6")
    print("=" * 64)
    db = flood_lsas(routers, seq=1)

    print()
    print("=" * 64)
    print("Dijkstra shortest paths from R1")
    print("=" * 64)
    dist, prev = dijkstra(db, "R1")
    for node in sorted(dist):
        path = build_path(prev, node)
        print(f"  R1 -> {node:<5}  cost={dist[node]:<5.0f}  path={' -> '.join(path)}")

    print()
    print("=" * 64)
    print("Dijkstra shortest paths from R2")
    print("=" * 64)
    dist2, prev2 = dijkstra(db, "R2")
    for node in sorted(dist2):
        path = build_path(prev2, node)
        print(f"  R2 -> {node:<5}  cost={dist2[node]:<5.0f}  path={' -> '.join(path)}")

    print()
    print("=" * 64)
    print("Designated Router election on broadcast LAN")
    print("=" * 64)
    candidates = [
        Router("R3", priority=1),
        Router("R4", priority=10),
        Router("R5", priority=10),
    ]
    dr = elect_dr(candidates)
    print("  Candidates:")
    for r in candidates:
        print(f"    {r.router_id}  priority={r.priority}")
    print(f"  Elected DR: {dr.router_id} (highest priority, "
          f"highest Router ID tiebreak)")

    print()
    print("=" * 64)
    print("Area hierarchy")
    print("=" * 64)
    print("  Backbone area 0:  R1, R2, R3, R4, R5")
    print("  Stub area 1:       LAN1, LAN2, LAN4 (stub networks via ABR)")
    print("  ABR (Area Border Router): R3 connects area 0 and area 1")

    print()
    print("=" * 64)
    print("Load balancing: equal-cost paths from R1 to R5")
    print("=" * 64)
    d1, p1 = dijkstra(db, "R1")
    print(f"  Shortest cost R1->R5 = {d1['R5']}")
    print(f"  Primary path: {' -> '.join(build_path(p1, 'R5'))}")


if __name__ == "__main__":
    main()