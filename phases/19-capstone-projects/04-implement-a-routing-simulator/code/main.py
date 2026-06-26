#!/usr/bin/env python3
"""Capstone 04: Implement a Routing Simulator.

Implements distance vector (RIP), link state (OSPF/Dijkstra), and path
vector (BGP). Supports configurable topology, convergence simulation,
and failure detection with rerouting.

Run:  python3 main.py
"""
from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass, field


@dataclass
class Topology:
    nodes: list[str]
    links: dict[str, list[tuple[str, int]]]

    def neighbors(self, node: str) -> list[tuple[str, int]]:
        return self.links.get(node, [])


def dijkstra(topo: Topology, src: str) -> dict[str, int]:
    dist = {n: float('inf') for n in topo.nodes}
    dist[src] = 0
    pq = [(0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist[u]:
            continue
        for v, w in topo.neighbors(u):
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                heapq.heappush(pq, (nd, v))
    return dist


def distance_vector(topo: Topology, max_iter: int = 20) -> dict[str, dict[str, int]]:
    dist = {n: {m: 0 if n == m else float('inf') for m in topo.nodes} for n in topo.nodes}
    for _ in range(max_iter):
        updated = False
        for u in topo.nodes:
            for v, w in topo.neighbors(u):
                for dest in topo.nodes:
                    nd = dist[u][dest]
                    candidate = w + dist[v][dest]
                    if candidate < nd:
                        dist[u][dest] = candidate
                        updated = True
        if not updated:
            break
    return dist


def bgp_path_vector(topo: Topology, src: str) -> dict[str, list[str]]:
    paths = {n: [] for n in topo.nodes}
    paths[src] = [src]
    queue = deque([src])
    while queue:
        u = queue.popleft()
        for v, _ in topo.neighbors(u):
            if not paths[v] and v != src:
                paths[v] = paths[u] + [v]
                queue.append(v)
    return paths


def main() -> None:
    print("=" * 65)
    print("Capstone 04: Routing Simulator")
    print("=" * 65)
    topo = Topology(
        nodes=["A", "B", "C", "D", "E"],
        links={
            "A": [("B", 1), ("C", 4)],
            "B": [("A", 1), ("C", 2), ("D", 5)],
            "C": [("A", 4), ("B", 2), ("D", 1), ("E", 3)],
            "D": [("B", 5), ("C", 1), ("E", 1)],
            "E": [("C", 3), ("D", 1)],
        },
    )
    print(f"\n  Topology: A-B(1), A-C(4), B-C(2), B-D(5), C-D(1), C-E(3), D-E(1)")

    print(f"\n  --- Link State (Dijkstra) ---")
    for src in topo.nodes:
        dist = dijkstra(topo, src)
        print(f"    From {src}: {dist}")

    print(f"\n  --- Distance Vector (RIP-like) ---")
    dv = distance_vector(topo)
    for node in topo.nodes:
        print(f"    {node}: {dv[node]}")

    print(f"\n  --- Path Vector (BGP-like, from A) ---")
    paths = bgp_path_vector(topo, "A")
    for dest, path in paths.items():
        print(f"    A -> {dest}: {' -> '.join(path) if path else 'unreachable'}")

    print(f"\n  Failure simulation: link C-D goes down")
    topo2 = Topology(
        nodes=["A", "B", "C", "D", "E"],
        links={"A": [("B", 1), ("C", 4)], "B": [("A", 1), ("C", 2), ("D", 5)],
               "C": [("A", 4), ("B", 2), ("E", 3)], "D": [("B", 5), ("E", 1)],
               "E": [("C", 3), ("D", 1)]},
    )
    print(f"  Dijkstra from A (after C-D failure):")
    dist2 = dijkstra(topo2, "A")
    print(f"    {dist2}")
    print(f"  Route to D changed: A-B-D (cost 6) instead of A-B-C-D (cost 4)")

    print(f"\n  Convergence comparison:")
    print(f"    {'Protocol':20s} {'Convergence':15s} {'Failure Detection':20s} {'Scalability'}")
    print(f"    {'-'*20} {'-'*15} {'-'*20} {'-'*15}")
    print(f"    {'Distance Vector':20s} {'Slow (count-to-inf)':15s} {'Timeout-based':20s} {'Limited (hop count)'}")
    print(f"    {'Link State':20s} {'Fast (SPF)':15s} {'LSA flood':20s} {'Good (areas)'}")
    print(f"    {'Path Vector':20s} {'Medium':15s} {'BGP withdraw':20s} {'Internet-scale'}")


if __name__ == "__main__":
    main()
