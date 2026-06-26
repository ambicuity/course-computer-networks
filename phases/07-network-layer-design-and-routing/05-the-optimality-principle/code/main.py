#!/usr/bin/env python3
"""Sink trees and the optimality principle (Bellman, 1957).

This program demonstrates the optimality principle from Section 5.2.1 of
Tanenbaum's *Computer Networks*: if router J lies on the optimal path from
I to K, then the J->K suffix of that path is itself optimal. The direct
consequence is that all optimal routes to a single destination form a
loop-free **sink tree** rooted at that destination.

Capabilities (stdlib only, no network calls):
  * Build a weighted, undirected graph from an edge list.
  * Run Dijkstra to compute the sink tree rooted at any destination, i.e.
    every router's optimal cost and single next hop toward that destination.
  * Verify the optimality principle empirically: for every router J on every
    source's optimal path, confirm the stored suffix cost equals the
    independently computed J->destination optimal cost.
  * Detect the equal-cost (ECMP / DAG) case where a router keeps >1 next hop.
  * Simulate an inconsistent topology view to produce a next-hop disagreement
    (the seed of a transient micro-loop).

Run:  python3 main.py
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

INFINITY = float("inf")

Graph = Dict[str, Dict[str, float]]


def build_graph(edges: List[Tuple[str, str, float]]) -> Graph:
    """Build an undirected adjacency map from (u, v, cost) triples."""
    graph: Graph = {}
    for u, v, cost in edges:
        if cost <= 0:
            raise ValueError(f"link {u}-{v} has non-positive cost {cost}")
        graph.setdefault(u, {})[v] = cost
        graph.setdefault(v, {})[u] = cost
    return graph


@dataclass
class TreeEntry:
    """One router's optimal route toward the destination."""

    source: str
    cost: float
    next_hop: Optional[str]
    equal_cost_next_hops: List[str] = field(default_factory=list)


def shortest_paths_from(graph: Graph, root: str) -> Tuple[Dict[str, float], Dict[str, str]]:
    """Dijkstra from `root`. Returns (cost map, parent map) over the graph.

    Because links are undirected, the cost from `root` to X equals the cost
    from X to `root`; we exploit this to build the sink tree rooted at a
    destination by running a single Dijkstra from that destination.
    """
    if root not in graph:
        raise KeyError(f"router {root!r} not in graph")
    dist: Dict[str, float] = {node: INFINITY for node in graph}
    parent: Dict[str, str] = {}
    dist[root] = 0.0
    visited: set[str] = set()
    pq: List[Tuple[float, str]] = [(0.0, root)]

    while pq:
        d, node = heapq.heappop(pq)
        if node in visited:
            continue
        visited.add(node)
        for neighbor, weight in sorted(graph[node].items()):
            cand = d + weight
            if cand < dist[neighbor]:
                dist[neighbor] = cand
                parent[neighbor] = node
                heapq.heappush(pq, (cand, neighbor))
    return dist, parent


def sink_tree(graph: Graph, destination: str) -> Dict[str, TreeEntry]:
    """Compute the sink tree rooted at `destination`.

    The next hop a source uses toward the destination is the source's parent
    in the Dijkstra tree rooted at the destination (one step back toward root).
    Equal-cost alternatives are detected by scanning each source's neighbors.
    """
    dist, parent = shortest_paths_from(graph, destination)
    tree: Dict[str, TreeEntry] = {}
    for source in sorted(graph):
        if source == destination:
            tree[source] = TreeEntry(source, 0.0, None)
            continue
        primary = parent.get(source)
        # Every neighbor that lies on AN optimal path satisfies:
        #   cost(source, n) + dist[n] == dist[source]
        equal: List[str] = []
        for neighbor, weight in sorted(graph[source].items()):
            if dist[neighbor] + weight == dist[source]:
                equal.append(neighbor)
        tree[source] = TreeEntry(source, dist[source], primary, equal)
    return tree


def reconstruct_path(graph: Graph, source: str, destination: str) -> List[str]:
    """Walk the sink tree from `source` to `destination` via next hops."""
    _, parent = shortest_paths_from(graph, destination)
    path = [source]
    node = source
    while node != destination:
        nxt = parent.get(node)
        if nxt is None:
            raise ValueError(f"no path from {source} to {destination}")
        path.append(nxt)
        node = nxt
    return path


def verify_optimality_principle(graph: Graph, destination: str) -> List[str]:
    """Empirically check the optimality principle for every router.

    For each source I and each router J on I's optimal path to the
    destination K, confirm that cost(suffix J..K) == optimal cost(J -> K).
    Returns human-readable violation strings (empty list == principle holds).
    """
    dist, _ = shortest_paths_from(graph, destination)
    violations: List[str] = []
    for source in sorted(graph):
        if source == destination:
            continue
        path = reconstruct_path(graph, source, destination)
        total = sum(graph[path[i]][path[i + 1]] for i in range(len(path) - 1))
        prefix = 0.0
        for idx, j in enumerate(path):
            suffix_cost = total - prefix
            if suffix_cost != dist[j]:
                violations.append(
                    f"VIOLATION: suffix {j}..{destination} costs {suffix_cost:g} "
                    f"but optimal {j}->{destination} is {dist[j]:g}"
                )
            if idx < len(path) - 1:
                prefix += graph[path[idx]][path[idx + 1]]
    return violations


def inconsistent_view(graph: Graph, u: str, v: str, new_cost: float) -> Graph:
    """Return a copy of `graph` with one link reweighted (a stale local view).

    Simulates a desynchronized link-state database: only this copy changes,
    so a router computing on it can disagree with its neighbors' next hops,
    which is exactly how a transient micro-loop forms during reconvergence.
    """
    view: Graph = {n: dict(adj) for n, adj in graph.items()}
    if v in view.get(u, {}):
        view[u][v] = new_cost
        view[v][u] = new_cost
    return view


def print_sink_tree(tree: Dict[str, TreeEntry], destination: str) -> None:
    print(f"  Sink tree rooted at {destination}:")
    print(f"  {'source':<8}{'cost':>6}  {'next hop':<10}{'ECMP next hops'}")
    print(f"  {'-' * 44}")
    for source in sorted(tree):
        e = tree[source]
        nh = e.next_hop if e.next_hop else "(root)"
        ecmp = ",".join(e.equal_cost_next_hops) if len(e.equal_cost_next_hops) > 1 else "-"
        cost = "0" if e.cost == 0 else f"{e.cost:g}"
        print(f"  {source:<8}{cost:>6}  {nh:<10}{ecmp}")


def main() -> None:
    # Worked-example topology from the lesson (undirected, weights = link cost).
    edges: List[Tuple[str, str, float]] = [
        ("A", "B", 2), ("B", "C", 7),
        ("A", "G", 6), ("B", "E", 3), ("C", "F", 2),
        ("G", "E", 1), ("E", "F", 2), ("F", "D", 3),
    ]
    graph = build_graph(edges)

    print("=" * 56)
    print("THE OPTIMALITY PRINCIPLE - sink trees (Bellman, 1957)")
    print("=" * 56)

    dest = "D"
    tree = sink_tree(graph, dest)
    print_sink_tree(tree, dest)

    print(f"\n  Example path A -> {dest}: " + " -> ".join(reconstruct_path(graph, "A", dest)))

    print("\n  Verifying optimality principle on every optimal path...")
    violations = verify_optimality_principle(graph, dest)
    if violations:
        for v in violations:
            print("   " + v)
    else:
        print("   OK: every suffix on every optimal path is itself optimal.")

    # Equal-cost case: lower A-G so A has two equal-cost paths to D.
    print("\n  --- Equal-cost (ECMP / DAG) case ---")
    # A->B->E->F->D = 2+3+2+3 = 10. Make A->G->E->F->D also = 10:
    # A-G + 1 + 2 + 3 = 10  =>  A-G = 4.
    tie_edges = [e for e in edges if e[:2] != ("A", "G")] + [("A", "G", 4)]
    tie_tree = sink_tree(build_graph(tie_edges), dest)
    a_entry = tie_tree["A"]
    print(f"  With A-G=4, router A cost to {dest} = {a_entry.cost:g}, "
          f"next hops = {a_entry.equal_cost_next_hops}")
    if len(a_entry.equal_cost_next_hops) > 1:
        print("   A now has multiple equal-cost next hops -> sink tree becomes a DAG (ECMP).")
    else:
        print("   Single next hop -> still a unique sink tree.")

    # Inconsistent-view case: G sees E-F as expensive, disagreeing with B.
    print("\n  --- Inconsistent topology view (micro-loop seed) ---")
    g_view = inconsistent_view(graph, "E", "F", 50)
    g_next = sink_tree(g_view, dest)["G"].next_hop
    b_next = sink_tree(graph, dest)["B"].next_hop
    print(f"  Consistent view: B's next hop to {dest} = {b_next}")
    print(f"  G's stale view (E-F=50): G's next hop to {dest} = {g_next}")
    print("   When neighbors disagree on next hops, packets can loop until the")
    print("   IPv4 TTL / IPv6 Hop Limit (RFC 791 / RFC 8200) expires.")
    print("=" * 56)


if __name__ == "__main__":
    main()
