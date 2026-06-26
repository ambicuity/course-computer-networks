#!/usr/bin/env python3
"""Hierarchical routing table sizing and broadcast routing simulators.

Three self-contained demonstrations tied to Tanenbaum Ch.5 sections 5.2.6/5.2.7:

1. hierarchy_entry_count() -- routing-table size for flat / 2-level / 3-level
   hierarchies, reproducing the classic 720 -> 53 -> 25 entry result and the
   Kamoun-Kleinrock e*ln(N) optimum.

2. reverse_path_forward() -- Reverse Path Forwarding (Dalal & Metcalfe, 1978):
   a router accepts a broadcast copy only if it arrived on the link it would use
   to reach the source; else it discards the copy. Counts packets per decision.

3. spanning_tree_broadcast() -- broadcast over a sink/spanning tree, the optimal
   floor of exactly N-1 packets.

Stdlib only. Run: python3 main.py
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Part 1: hierarchical routing table sizing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HierarchyDesign:
    """A routing hierarchy described by routers-per-group at each level.

    levels is innermost-first: (routers_per_region, regions_per_cluster, ...).
    A single-element tuple means a flat network.
    """

    name: str
    levels: tuple[int, ...]

    def total_routers(self) -> int:
        product = 1
        for group_size in self.levels:
            product *= group_size
        return product

    def entries_per_router(self) -> int:
        """Local routers + remote groups visible at each enclosing level.

        Level 0 contributes its full router count (all local peers). Each
        higher level contributes (group_size - 1): the sibling groups reachable
        through one condensed entry each.
        """
        entries = self.levels[0]
        for group_size in self.levels[1:]:
            entries += group_size - 1
        return entries


def optimal_levels(n_routers: int) -> tuple[float, float]:
    """Kamoun-Kleinrock: optimal depth ~ ln N, entries ~ e * ln N."""
    levels = math.log(n_routers)
    return levels, math.e * levels


def hierarchy_entry_count() -> None:
    designs = [
        HierarchyDesign("flat (no hierarchy)", (720,)),
        HierarchyDesign("two-level: 30 routers x 24 regions", (30, 24)),
        HierarchyDesign("three-level: 10 x 9 regions x 8 clusters", (10, 9, 8)),
    ]
    print("=" * 64)
    print("PART 1  Hierarchical routing table sizing (N = 720 routers)")
    print("=" * 64)
    print(f"{'design':<42}{'routers':>8}{'entries':>9}")
    for d in designs:
        print(f"{d.name:<42}{d.total_routers():>8}{d.entries_per_router():>9}")
    levels, entries = optimal_levels(720)
    print("-" * 64)
    print(f"Kamoun-Kleinrock optimum: ~{levels:.2f} levels, "
          f"~{entries:.1f} entries/router (the e*ln N floor)")
    print()


# ---------------------------------------------------------------------------
# Part 2 & 3: broadcast routing on a small graph
# ---------------------------------------------------------------------------

Graph = dict[str, list[str]]


def bfs_next_hop_to_source(graph: Graph, source: str) -> dict[str, str]:
    """For every router, the neighbor on its shortest path toward `source`.

    This is exactly the unicast forwarding state RPF reuses: the link a router
    would send a packet on to reach the broadcast source.
    """
    parent: dict[str, str] = {source: source}
    queue = deque([source])
    while queue:
        node = queue.popleft()
        for neighbor in graph[node]:
            if neighbor not in parent:
                parent[neighbor] = node  # neighbor's next hop toward source
                queue.append(neighbor)
    return parent


@dataclass
class BroadcastResult:
    packets_sent: int = 0
    accepted: int = 0
    discarded: int = 0
    trace: list[str] = field(default_factory=list)


def reverse_path_forward(graph: Graph, source: str) -> BroadcastResult:
    """Simulate RPF broadcast from `source`, counting packets and decisions."""
    next_hop = bfs_next_hop_to_source(graph, source)
    result = BroadcastResult()
    # A "send" is one packet on one link. The source seeds copies to all links.
    pending: deque[tuple[str, str]] = deque()  # (from_router, to_router)
    for neighbor in graph[source]:
        pending.append((source, neighbor))
        result.packets_sent += 1

    accepted_routers: set[str] = {source}
    while pending:
        sender, router = pending.popleft()
        preferred = next_hop.get(router)
        # RPF rule: accept only if the packet arrived from our next hop to source.
        if preferred == sender and router not in accepted_routers:
            result.accepted += 1
            accepted_routers.add(router)
            result.trace.append(f"  {router}: ACCEPT (arrived from {sender}, "
                                 f"preferred link to {source}) -> forward")
            for neighbor in graph[router]:
                if neighbor != sender:
                    pending.append((router, neighbor))
                    result.packets_sent += 1
        else:
            result.discarded += 1
            reason = ("wrong link" if preferred != sender else "already accepted")
            result.trace.append(f"  {router}: DISCARD (from {sender}; {reason})")
    return result


def spanning_tree_broadcast(graph: Graph, source: str) -> BroadcastResult:
    """Broadcast over the BFS sink tree -- the optimal N-1 packet floor."""
    parent = bfs_next_hop_to_source(graph, source)
    result = BroadcastResult()
    # Each non-source router receives exactly one copy from its tree parent.
    for router, par in parent.items():
        if router != source:
            result.packets_sent += 1
            result.accepted += 1
            result.trace.append(f"  {router}: receive 1 copy from tree parent {par}")
    assert result.packets_sent == len(parent) - 1
    return result


def print_broadcast(label: str, result: BroadcastResult) -> None:
    print(label)
    for line in result.trace:
        print(line)
    print(f"  totals: {result.packets_sent} packets sent, "
          f"{result.accepted} accepted, {result.discarded} discarded")
    print()


def main() -> None:
    hierarchy_entry_count()

    # A small undirected network. Adjacency lists model bidirectional links.
    graph: Graph = {
        "I": ["F", "H", "J", "N"],
        "F": ["I", "A", "E", "G"],
        "H": ["I", "G", "L", "B"],
        "J": ["I", "E", "K", "O"],
        "N": ["I", "K", "O", "M"],
        "A": ["F", "D"],
        "E": ["F", "J", "C", "D"],
        "G": ["F", "H"],
        "L": ["H", "B"],
        "B": ["H", "L"],
        "K": ["J", "N"],
        "O": ["J", "N", "M"],
        "M": ["N", "O"],
        "D": ["A", "E", "C"],
        "C": ["E", "D"],
    }

    print("=" * 64)
    print("PART 2  Reverse Path Forwarding broadcast from router I")
    print("=" * 64)
    rpf = reverse_path_forward(graph, "I")
    print_broadcast("RPF trace (accept = arrived on preferred link to I):", rpf)

    print("=" * 64)
    print("PART 3  Spanning-tree broadcast from router I (optimal floor)")
    print("=" * 64)
    tree = spanning_tree_broadcast(graph, "I")
    print_broadcast("Spanning-tree trace:", tree)

    n = len(graph)
    print("=" * 64)
    print("SUMMARY")
    print("=" * 64)
    print(f"  network size N           : {n} routers")
    print(f"  spanning-tree packets    : {tree.packets_sent}  (optimal = N-1 = {n - 1})")
    print(f"  RPF packets              : {rpf.packets_sent}")
    print(f"  RPF overhead vs optimal  : {rpf.packets_sent - tree.packets_sent} "
          f"extra packets, 0 extra router state")
    print("  RPF needs only the unicast next-hop table; the tree needs every")
    print("  router to agree on a shared tree (easy with link-state routing).")


if __name__ == "__main__":
    main()
