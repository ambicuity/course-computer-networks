"""Shortest Path Routing Lab — Dijkstra and Bellman-Ford on a sample network topology.

Implements both single-source shortest-path algorithms, extracts per-router
forwarding tables, compares the two algorithms, demonstrates Bellman-Ford on a
graph with a negative edge (where Dijkstra would fail), and simulates a link
failure to detect a transient micro-loop during reconvergence.

Run:  python3 main.py
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Graph model
# ---------------------------------------------------------------------------

Node = str
EdgeList = List[Tuple[Node, Node, int]]  # (u, v, weight)


@dataclass
class Graph:
    """Undirected weighted graph as an adjacency list. Routing links are
    bidirectional and symmetric by default."""

    adj: Dict[Node, Dict[Node, int]] = field(default_factory=dict)

    def add_node(self, n: Node) -> None:
        self.adj.setdefault(n, {})

    def add_link(self, u: Node, v: Node, w: int) -> None:
        """Add a symmetric edge u-v with weight w."""
        self.add_node(u)
        self.add_node(v)
        self.adj[u][v] = w
        self.adj[v][u] = w

    def add_directed_link(self, u: Node, v: Node, w: int) -> None:
        """Add a one-way edge u->v with weight w (for TE / policy demos)."""
        self.add_node(u)
        self.add_node(v)
        self.adj[u][v] = w

    def remove_link(self, u: Node, v: Node) -> None:
        self.adj.get(u, {}).pop(v, None)
        self.adj.get(v, {}).pop(u, None)

    def nodes(self) -> List[Node]:
        return sorted(self.adj)

    def edges(self) -> EdgeList:
        """Return all directed edges (u, v, w). For symmetric links both directions appear."""
        out: EdgeList = []
        for u in self.adj:
            for v, w in self.adj[u].items():
                out.append((u, v, w))
        return out


def sample_topology() -> Graph:
    """Five-router POP topology used throughout the lab."""
    g = Graph()
    g.add_link("A", "B", 1)
    g.add_link("A", "C", 4)
    g.add_link("B", "C", 1)
    g.add_link("B", "D", 2)
    g.add_link("C", "E", 0)
    return g


def topology_with_negative_edge() -> Graph:
    """Same topology plus a one-way negative-cost TE link D->E (traffic engineering)."""
    g = sample_topology()
    g.add_directed_link("D", "E", -3)
    return g


# ---------------------------------------------------------------------------
# Dijkstra — O(E log V), requires non-negative weights
# ---------------------------------------------------------------------------


def dijkstra(g: Graph, source: Node) -> Tuple[Dict[Node, int], Dict[Node, Optional[Node]], List[str]]:
    """Return (dist, prev, trace). Uses a binary heap with lazy deletion."""
    dist: Dict[Node, int] = {n: float("inf") for n in g.nodes()}  # type: ignore[assignment]
    prev: Dict[Node, Optional[Node]] = {n: None for n in g.nodes()}
    dist[source] = 0
    heap: List[Tuple[int, Node]] = [(0, source)]
    settled: set = set()
    trace: List[str] = []
    relax_count = 0

    while heap:
        d, u = heapq.heappop(heap)
        if u in settled:
            continue
        settled.add(u)
        trace.append(f"settle {u} (dist={d})")
        for v, w in sorted(g.adj[u].items()):
            if v in settled:
                continue
            nd = d + w
            if nd < dist[v]:
                dist[v] = nd
                prev[v] = u
                heapq.heappush(heap, (nd, v))
                relax_count += 1
                trace.append(f"  relax {u}->{v} w={w}: dist[{v}]={nd} prev={u}")
    trace.append(f"Dijkstra relaxations: {relax_count}")
    return dist, prev, trace


# ---------------------------------------------------------------------------
# Bellman-Ford — O(V*E), handles negative weights, detects negative cycles
# ---------------------------------------------------------------------------


def bellman_ford(g: Graph, source: Node) -> Tuple[Dict[Node, int], Dict[Node, Optional[Node]], List[str]]:
    """Return (dist, prev, trace). Flags negative cycles reachable from source."""
    dist: Dict[Node, int] = {n: float("inf") for n in g.nodes()}  # type: ignore[assignment]
    prev: Dict[Node, Optional[Node]] = {n: None for n in g.nodes()}
    dist[source] = 0
    edges = g.edges()
    trace: List[str] = []
    relax_count = 0
    V = len(g.nodes())

    for i in range(V - 1):
        changed = False
        for u, v, w in edges:
            if dist[u] + w < dist[v]:
                dist[v] = dist[u] + w
                prev[v] = u
                relax_count += 1
                changed = True
                trace.append(f"pass {i + 1}: relax {u}->{v} w={w}: dist[{v}]={dist[v]} prev={u}")
        if not changed:
            trace.append(f"converged after pass {i + 1}")
            break
    trace.append(f"Bellman-Ford relaxations: {relax_count}")

    # negative-cycle detection: one extra pass
    for u, v, w in edges:
        if dist[u] + w < dist[v]:
            trace.append(f"NEGATIVE CYCLE detected on {u}->{v} (w={w})")
            return dist, prev, trace
    return dist, prev, trace


# ---------------------------------------------------------------------------
# Forwarding table extraction — tree to next-hop
# ---------------------------------------------------------------------------


def next_hop(prev: Dict[Node, Optional[Node]], source: Node, dest: Node) -> Optional[Node]:
    """Walk prev[] back from dest toward source; return the neighbor adjacent to source.

    Guarded against cycles in prev[] (e.g. when a negative cycle was detected).
    """
    if dest == source:
        return source
    node: Optional[Node] = dest
    seen: set = set()
    while node is not None and prev[node] != source:
        if node in seen:
            return None  # prev cycle — no well-defined next hop
        seen.add(node)
        node = prev[node]
    return node  # None means unreachable or cyclic


def forwarding_table(
    g: Graph, dist: Dict[Node, int], prev: Dict[Node, Optional[Node]], source: Node
) -> List[Tuple[Node, int, Optional[Node]]]:
    """Return list of (dest, cost, next_hop) sorted by destination."""
    table: List[Tuple[Node, int, Optional[Node]]] = []
    for dest in g.nodes():
        if dest == source:
            continue
        nh = next_hop(prev, source, dest)
        cost = dist[dest] if dist[dest] != float("inf") else -1
        table.append((dest, cost, nh))
    return sorted(table)


# ---------------------------------------------------------------------------
# OSPF cost helper
# ---------------------------------------------------------------------------


def ospf_cost(bandwidth_mbps: float, reference_mbps: float = 100.0) -> int:
    """OSPF default interface cost = reference_bandwidth / interface_bandwidth, min 1."""
    return max(1, int(reference_mbps // bandwidth_mbps))


# ---------------------------------------------------------------------------
# Reconvergence and micro-loop detection
# ---------------------------------------------------------------------------


def all_router_tables(g: Graph) -> Dict[Node, List[Tuple[Node, int, Optional[Node]]]]:
    """Run Dijkstra from every router; return {router: forwarding_table}."""
    out: Dict[Node, List[Tuple[Node, int, Optional[Node]]]] = {}
    for r in g.nodes():
        dist, prev, _ = dijkstra(g, r)
        out[r] = forwarding_table(g, dist, prev, r)
    return out


def detect_microloop(
    after: Dict[Node, List[Tuple[Node, int, Optional[Node]]]],
) -> List[str]:
    """Flag any (X, Y, dest) where after-failure X->Y and Y->X for the same dest."""
    report: List[str] = []

    def table_map(t: List[Tuple[Node, int, Optional[Node]]]) -> Dict[Node, Optional[Node]]:
        return {d: nh for (d, _, nh) in t}

    for x in after:
        xmap = table_map(after[x])
        for y in xmap:
            if y == x:
                continue
            ymap = table_map(after.get(y, []))
            for dest, nh_x in xmap.items():
                if nh_x == y and ymap.get(dest) == x:
                    report.append(f"MICRO-LOOP: {x} -> {y} and {y} -> {x} for dest {dest}")
    return report


def simulate_failure(g: Graph, u: Node, v: Node) -> List[str]:
    """Remove link u-v, recompute all tables, report micro-loops."""
    g.remove_link(u, v)
    after = all_router_tables(g)
    report = detect_microloop(after)
    if not report:
        report.append("No two-router micro-loop detected (may still have longer loops).")
    return report


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def print_table(title: str, rows: List[Tuple[Node, int, Optional[Node]]]) -> None:
    print(f"\n{title}")
    print(f"  {'dest':<6}{'cost':<8}{'next hop':<10}")
    print(f"  {'-' * 6}{'-' * 8}{'-' * 10}")
    for dest, cost, nh in rows:
        nh_s = nh if nh is not None else "UNREACHABLE"
        print(f"  {dest:<6}{cost:<8}{nh_s:<10}")


def main() -> int:
    g = sample_topology()
    src = "A"

    print("=" * 64)
    print("SHORTEST PATH ROUTING LAB")
    print("=" * 64)
    print("\nTopology (adjacency list):")
    for n in g.nodes():
        print(f"  {n}: {dict(sorted(g.adj[n].items()))}")
    print(f"\nEdges: {g.edges()}")

    # --- Dijkstra ---
    print("\n" + "-" * 64)
    print("1. DIJKSTRA from source A")
    print("-" * 64)
    d_dist, d_prev, d_trace = dijkstra(g, src)
    for line in d_trace:
        print(line)
    print_table("Forwarding table at A (Dijkstra):", forwarding_table(g, d_dist, d_prev, src))

    # --- Bellman-Ford on same graph ---
    print("\n" + "-" * 64)
    print("2. BELLMAN-FORD from source A (same non-negative graph)")
    print("-" * 64)
    bf_dist, bf_prev, bf_trace = bellman_ford(g, src)
    for line in bf_trace:
        print(line)
    print_table("Forwarding table at A (Bellman-Ford):", forwarding_table(g, bf_dist, bf_prev, src))

    same_tree = (d_dist == bf_dist) and (d_prev == bf_prev)
    print(f"\nTrees identical (non-negative graph)? {same_tree}")
    if not same_tree:
        print("  Dijkstra dist:   ", d_dist)
        print("  BellmanFord dist:", bf_dist)

    # --- Bellman-Ford with negative edge ---
    print("\n" + "-" * 64)
    print("3. BELLMAN-FORD on graph with NEGATIVE edge D-E = -3")
    print("-" * 64)
    gn = topology_with_negative_edge()
    print(f"Edges: {gn.edges()}")
    bf_dist_n, bf_prev_n, bf_trace_n = bellman_ford(gn, src)
    for line in bf_trace_n:
        print(line)
    has_neg_cycle = any("NEGATIVE CYCLE" in line for line in bf_trace_n)
    if has_neg_cycle:
        print("\nNegative cycle detected — forwarding table is undefined (no stable path).")
    else:
        print_table(
            "Forwarding table at A (Bellman-Ford, negative edge):",
            forwarding_table(gn, bf_dist_n, bf_prev_n, src),
        )
    print("\nNote: Dijkstra cannot run here — the negative edge breaks the")
    print("'settled = final' invariant. Bellman-Ford handles it correctly.")

    # --- OSPF cost clamp demo ---
    print("\n" + "-" * 64)
    print("4. OSPF COST: bandwidth -> metric (reference = 100 Mbps default)")
    print("-" * 64)
    for bw in [10, 100, 1000, 10000, 40000]:
        c = ospf_cost(bw)
        print(f"  {bw:>7} Mbps  ->  cost {c}")
    print("\nWith reference raised to 40000 Mbps (40 Gbps):")
    for bw in [10, 100, 1000, 10000, 40000]:
        c = ospf_cost(bw, reference_mbps=40000)
        print(f"  {bw:>7} Mbps  ->  cost {c}")

    # --- Reconvergence ---
    print("\n" + "-" * 64)
    print("5. RECONVERGENCE: fail link B-C, detect micro-loops")
    print("-" * 64)
    g2 = sample_topology()
    report = simulate_failure(g2, "B", "C")
    for line in report:
        print(line)
    print("\nDuring the window before all routers re-run SPF, a packet for the")
    print("affected destination can bounce between the looping pair until TTL")
    print("(RFC 791) expires and the router emits ICMP Time Exceeded (type 11).")

    print("\n" + "=" * 64)
    print("Done. Review the trace, the forwarding tables, and the micro-loop report.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())