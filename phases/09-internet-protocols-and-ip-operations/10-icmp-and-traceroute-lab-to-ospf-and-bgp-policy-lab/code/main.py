#!/usr/bin/env python3
"""Traceroute simulator and OSPF/BGP policy-routing decision lab.

Stdlib only. Two parts:

Part 1 - Traceroute (Tanenbaum 5.6.4): simulates Van Jacobson's method
of incrementally increasing TTL and collecting ICMP TIME_EXCEEDED
responses from each router hop.  Each hop gets a simulated RTT with
jitter.  Demonstrates the exact mechanism described in Sec. 5.6.4.

Part 2 - Policy routing lab: given a small 4-AS topology (the transit
model of Fig. 5-67), shows how BGP import/export policies decide which
path packets take between source and destination, and how OSPF
provides the intra-AS shortest path used to reach the BGP egress.

Run:  python3 main.py
"""
from __future__ import annotations

import heapq
import random
import struct
from dataclasses import dataclass, field
from typing import Optional

INF = float("inf")


@dataclass
class ICMPTimeExceeded:
    router_ip: str
    original_ttl: int


@dataclass
class ICMPEchoReply:
    router_ip: str
    original_ttl: int


@dataclass
class RouterHop:
    ip: str
    name: str
    base_latency_ms: float


@dataclass
class TracerouteResult:
    ttl: int
    router_ip: Optional[str]
    rtt_ms: float
    reached: bool


def simulate_traceroute(
    path: list[RouterHop],
    destination_ip: str,
    max_ttl: int = 30,
    seed: int = 42,
) -> list[TracerouteResult]:
    rng = random.Random(seed)
    results: list[TracerouteResult] = []
    for ttl in range(1, max_ttl + 1):
        if ttl <= len(path):
            hop = path[ttl - 1]
            rtt = hop.base_latency_ms + rng.uniform(0.5, 2.5)
            results.append(TracerouteResult(
                ttl=ttl, router_ip=hop.ip, rtt_ms=round(rtt, 3),
                reached=False,
            ))
            print(f"  {ttl:>2}  {hop.ip:<16}  {hop.name:<16}  "
                  f"{rtt:6.2f} ms")
        elif ttl == len(path) + 1:
            rtt = path[-1].base_latency_ms + rng.uniform(0.5, 2.5) if path else 1.0
            results.append(TracerouteResult(
                ttl=ttl, router_ip=destination_ip, rtt_ms=round(rtt, 3),
                reached=True,
            ))
            print(f"  {ttl:>2}  {destination_ip:<16}  DESTINATION       "
                  f"{rtt:6.2f} ms  *reached*")
            break
        else:
            results.append(TracerouteResult(
                ttl=ttl, router_ip=None, rtt_ms=0.0, reached=False,
            ))
            print(f"  {ttl:>2}  *  *  *")
    return results


def build_path() -> list[RouterHop]:
    return [
        RouterHop("10.0.0.1", "gateway", 1.2),
        RouterHop("172.16.0.1", "ISP-edge", 4.5),
        RouterHop("192.168.100.1", "ISP-core-1", 12.0),
        RouterHop("4.69.137.1", "ISP-core-2", 25.0),
        RouterHop("4.69.140.1", "transit-1", 40.0),
        RouterHop("8.8.4.1", "google-edge", 55.0),
    ]


@dataclass
class ASLink:
    src_as: int
    dst_as: int
    relation: str
    cost: int = 1


@dataclass
class ASPath:
    path: list[int]
    cost: int
    policy_ok: bool = True


def ospf_shortest_path(
    topology: dict[str, dict[str, float]],
    source: str,
    dest: str,
) -> tuple[float, list[str]]:
    dist: dict[str, float] = {n: INF for n in topology}
    prev: dict[str, Optional[str]] = {n: None for n in topology}
    dist[source] = 0.0
    pq: list[tuple[float, str]] = [(0.0, source)]
    visited: set[str] = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in visited:
            continue
        visited.add(u)
        for v, w in topology.get(u, {}).items():
            nd = d + w
            if nd < dist.get(v, INF):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    path: list[str] = []
    node: Optional[str] = dest
    while node is not None:
        path.append(node)
        node = prev[node]
    return dist[dest], list(reversed(path))


def bgp_policy_path(
    links: list[ASLink],
    src_as: int,
    dst_as: int,
    denied_transit: set[tuple[int, int]],
) -> Optional[ASPath]:
    adj: dict[int, list[tuple[int, int, str]]] = {}
    for link in links:
        adj.setdefault(link.src_as, []).append(
            (link.dst_as, link.cost, link.relation))
        adj.setdefault(link.dst_as, []).append(
            (link.src_as, link.cost, link.relation))
    best_path: Optional[list[int]] = None
    best_cost = INF
    queue: list[tuple[int, int, list[int]]] = [(0, src_as, [src_as])]
    while queue:
        cost, asn, path = queue.pop(0)
        if cost >= best_cost:
            continue
        if asn == dst_as:
            if cost < best_cost:
                best_cost = cost
                best_path = path
            continue
        for next_as, link_cost, relation in adj.get(asn, []):
            if next_as in path:
                continue
            if (asn, next_as) in denied_transit:
                continue
            queue.append((cost + link_cost, next_as, path + [next_as]))
    if best_path is None:
        return None
    return ASPath(path=best_path, cost=best_cost, policy_ok=True)


def main() -> None:
    print("=" * 64)
    print("Traceroute Simulator  --  Tanenbaum 5.6.4")
    print("=" * 64)
    print("Method: send packets with TTL=1,2,3,... and collect ICMP")
    print("TIME_EXCEEDED from each router along the path.")
    print()
    path = build_path()
    dest = "8.8.8.8"
    print(f"Destination: {dest}")
    print(f"{'TTL':>3}  {'Router':<16}  {'Name':<16}  {'RTT':>8}")
    print("-" * 52)
    results = simulate_traceroute(path, dest)
    print()
    print(f"Hops: {len([r for r in results if r.router_ip and not r.reached])}")
    print(f"Final RTT: {results[-1].rtt_ms:.2f} ms")

    print()
    print("=" * 64)
    print("ICMP message types used by traceroute")
    print("=" * 64)
    print("  Echo Request (type 8)  -> sent to destination")
    print("  Time Exceeded (type 11) -> returned by router when TTL=0")
    print("  Echo Reply (type 0)    -> returned by destination on arrival")
    print("  Destination Unreachable (type 3) -> if host is down")

    print()
    print("=" * 64)
    print("OSPF shortest path (intra-AS)")
    print("=" * 64)
    topology: dict[str, dict[str, float]] = {
        "R1": {"R2": 1, "R3": 5},
        "R2": {"R1": 1, "R3": 2, "R4": 6},
        "R3": {"R1": 5, "R2": 2, "R4": 1},
        "R4": {"R2": 6, "R3": 1},
    }
    cost, sp = ospf_shortest_path(topology, "R1", "R4")
    print(f"  R1 -> R4: cost={cost:.0f}  path={' -> '.join(sp)}")

    print()
    print("=" * 64)
    print("BGP policy routing (4-AS transit topology, Fig. 5-67)")
    print("=" * 64)
    links = [
        ASLink(1, 2, "customer"),
        ASLink(1, 3, "customer"),
        ASLink(1, 4, "customer"),
        ASLink(2, 3, "peer"),
    ]
    print("  AS1 = transit provider, AS2/AS3/AS4 = customers")
    print("  AS2-AS3 = peer link (free, no transit)")
    print()

    print("  Case A: A(in AS2) -> C(in AS4), transit via AS1")
    p = bgp_policy_path(links, 2, 4, denied_transit=set())
    if p:
        print(f"    Path: {' -> '.join(f'AS{a}' for a in p.path)}  cost={p.cost}")
    print()

    print("  Case B: AS2 -> AS4 but AS1 denies transit (AS2,AS1)")
    p2 = bgp_policy_path(links, 2, 4, denied_transit={(2, 1), (1, 2)})
    if p2:
        print(f"    Path: {' -> '.join(f'AS{a}' for a in p2.path)}  cost={p2.cost}")
    else:
        print("    No path (transit denied through AS1, no peer transit)")
    print()

    print("  Case C: AS2 -> AS3 using peer link directly")
    p3 = bgp_policy_path(links, 2, 3, denied_transit=set())
    if p3:
        print(f"    Path: {' -> '.join(f'AS{a}' for a in p3.path)}  cost={p3.cost}")
    print()

    print("=" * 64)
    print("Combined: OSPF carries inside AS, BGP chooses between ASes")
    print("=" * 64)
    print("  Packet A->C flow:")
    print("    1. A sends to C; local router looks up BGP route")
    print("    2. BGP best path: AS2 -> AS1 -> AS4 (customer transit)")
    print("    3. Inside AS2: OSPF carries packet from A to AS2 egress")
    print("    4. At AS2 egress: handed to AS1 via BGP")
    print("    5. Inside AS1: OSPF carries to AS4 egress")
    print("    6. At AS4: delivered to C")


if __name__ == "__main__":
    main()