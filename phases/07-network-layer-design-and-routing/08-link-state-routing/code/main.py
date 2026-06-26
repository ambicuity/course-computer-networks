#!/usr/bin/env python3
"""Link State Routing simulator (Tanenbaum CN 5th ed., section 5.2.5).

Implements the five steps every link state router performs:

  1. (assumed) discover neighbors    -> encoded as the topology graph
  2. set link costs                  -> edge weights on the graph
  3. build a Link State Packet (LSP) -> build_lsp / build_all_lsps
  4. flood LSPs to all routers       -> flood (with (source, seq) seen-set)
  5. compute shortest paths          -> dijkstra + routing_table

The example topology matches the lesson diagram (assets/link-state-routing.svg):

        A --4-- B --2-- C
        |       |       |
        1       6       3
        |       |       |
        D --7-- F --8-- E

Stdlib only. Run: python3 main.py
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# A topology is router -> {neighbor: cost}. Links are symmetric here, but the
# data structure allows different costs per direction (as the chapter notes).
Topology = Dict[str, Dict[str, int]]

EXAMPLE_TOPOLOGY: Topology = {
    "A": {"B": 4, "D": 1},
    "B": {"A": 4, "C": 2, "F": 6},
    "C": {"B": 2, "E": 3},
    "D": {"A": 1, "F": 7},
    "E": {"C": 3, "F": 8},
    "F": {"B": 6, "D": 7, "E": 8},
}


@dataclass(frozen=True)
class LinkStatePacket:
    """One router's advertisement of its directly observed local links."""

    source: str
    sequence: int               # 32-bit monotonic counter per source
    age: int                    # countdown; purged at 0
    links: Tuple[Tuple[str, int], ...]  # (neighbor, cost) pairs, sorted

    def body(self) -> Dict[str, int]:
        return dict(self.links)

    def __str__(self) -> str:
        body = " ".join(f"{n}:{c}" for n, c in self.links)
        return f"LSP[src={self.source} seq={self.sequence} age={self.age} | {body}]"


# --------------------------------------------------------------------------
# Step 3: build Link State Packets
# --------------------------------------------------------------------------

def build_lsp(topology: Topology, router: str, sequence: int, age: int = 60) -> LinkStatePacket:
    """Build the LSP a router emits: its identity plus every attached link."""
    links = tuple(sorted(topology[router].items()))
    return LinkStatePacket(source=router, sequence=sequence, age=age, links=links)


def build_all_lsps(topology: Topology, sequence: int = 21) -> Dict[str, LinkStatePacket]:
    return {r: build_lsp(topology, r, sequence) for r in sorted(topology)}


# --------------------------------------------------------------------------
# Step 4: flood an LSP across the network with a per-source seen-set
# --------------------------------------------------------------------------

@dataclass
class FloodResult:
    delivered: List[str] = field(default_factory=list)   # routers that accepted it
    log: List[str] = field(default_factory=list)         # human-readable trace


def flood(topology: Topology, lsp: LinkStatePacket, origin: str,
          seen: Dict[Tuple[str, str], int]) -> FloodResult:
    """Controlled flooding.

    Rules per the chapter:
      - new (higher) sequence  -> accept, forward on every line except arrival
      - duplicate sequence     -> discard
      - lower sequence         -> reject as obsolete
    `seen` maps (router, source) -> highest sequence that router has accepted
    for that source. Each router keeps its own seen-set, so a fresh LSP
    genuinely propagates hop by hop while later copies are dropped.
    """
    result = FloodResult()
    # Each queue item: (router_receiving, arrived_from). origin injects the LSP.
    queue: List[Tuple[str, Optional[str]]] = [(origin, None)]

    while queue:
        node, came_from = queue.pop(0)
        highest = seen.get((node, lsp.source), -1)

        if lsp.sequence < highest:
            result.log.append(f"{node}: REJECT obsolete {lsp.source} "
                              f"seq={lsp.sequence} < seen {highest}")
            continue
        if lsp.sequence == highest:
            result.log.append(f"{node}: DISCARD duplicate {lsp.source} seq={lsp.sequence}")
            continue

        # New: accept and forward on all lines except the one it arrived on.
        seen[(node, lsp.source)] = lsp.sequence
        result.delivered.append(node)
        outgoing = [n for n in topology[node] if n != came_from]
        arrived = came_from or "(injected)"
        result.log.append(f"{node}: ACCEPT {lsp.source} seq={lsp.sequence} "
                          f"(from {arrived}) -> forward to {outgoing or 'none'}")
        for nxt in outgoing:
            queue.append((nxt, node))

    return result


# --------------------------------------------------------------------------
# Step 5: reassemble the global topology and run Dijkstra
# --------------------------------------------------------------------------

def reassemble_topology(lsps: Dict[str, LinkStatePacket]) -> Topology:
    """Rebuild the full graph from a complete set of LSPs."""
    graph: Topology = {src: {} for src in lsps}
    for src, lsp in lsps.items():
        for neighbor, cost in lsp.links:
            graph.setdefault(src, {})[neighbor] = cost
    return graph


def dijkstra(topology: Topology, source: str) -> Tuple[Dict[str, int], Dict[str, Optional[str]]]:
    """Shortest paths from `source`. Returns (dist, predecessor)."""
    dist: Dict[str, int] = {node: float("inf") for node in topology}
    prev: Dict[str, Optional[str]] = {node: None for node in topology}
    dist[source] = 0
    pq: List[Tuple[int, str]] = [(0, source)]
    settled: set = set()

    while pq:
        d, node = heapq.heappop(pq)
        if node in settled:
            continue
        settled.add(node)
        for neighbor, cost in sorted(topology[node].items()):
            nd = d + cost
            if nd < dist[neighbor]:
                dist[neighbor] = nd
                prev[neighbor] = node
                heapq.heappush(pq, (nd, neighbor))
    return dist, prev


def path_to(prev: Dict[str, Optional[str]], source: str, dest: str) -> List[str]:
    path: List[str] = []
    node: Optional[str] = dest
    while node is not None:
        path.append(node)
        if node == source:
            break
        node = prev[node]
    return list(reversed(path))


def routing_table(topology: Topology, source: str) -> Dict[str, Tuple[Optional[str], int]]:
    """Map each destination -> (next_hop, total_cost) for `source`."""
    dist, prev = dijkstra(topology, source)
    table: Dict[str, Tuple[Optional[str], int]] = {}
    for dest in sorted(topology):
        if dest == source:
            continue
        path = path_to(prev, source, dest)
        next_hop = path[1] if len(path) > 1 else None
        table[dest] = (next_hop, dist[dest])
    return table


# --------------------------------------------------------------------------
# Demonstration
# --------------------------------------------------------------------------

def main() -> None:
    print("=" * 64)
    print("LINK STATE ROUTING SIMULATOR")
    print("=" * 64)

    print("\n[Step 3] Each router builds its Link State Packet:")
    lsps = build_all_lsps(EXAMPLE_TOPOLOGY, sequence=21)
    for src in sorted(lsps):
        print("  " + str(lsps[src]))

    print("\n[Step 4] Flood router B's LSP across the network:")
    seen: Dict[Tuple[str, str], int] = {}
    res = flood(EXAMPLE_TOPOLOGY, lsps["B"], origin="B", seen=seen)
    for line in res.log:
        print("  " + line)
    print(f"  -> delivered to: {sorted(set(res.delivered))}")

    print("\n[Step 4] Re-flood an OBSOLETE copy of B (seq=20 < 21):")
    stale = build_lsp(EXAMPLE_TOPOLOGY, "B", sequence=20)
    res2 = flood(EXAMPLE_TOPOLOGY, stale, origin="B", seen=seen)
    print("  " + res2.log[0])

    print("\n[Step 5] Reassemble topology and run Dijkstra from A:")
    graph = reassemble_topology(lsps)
    dist, prev = dijkstra(graph, "A")
    for dest in sorted(graph):
        if dest == "A":
            continue
        path = " -> ".join(path_to(prev, "A", dest))
        print(f"  A to {dest}: cost {dist[dest]:>2}   path {path}")

    print("\n[Step 5] Routing table installed at A (dest -> next hop, cost):")
    table = routing_table(graph, "A")
    print(f"  {'DEST':<6}{'NEXT HOP':<10}{'COST'}")
    for dest, (next_hop, cost) in table.items():
        print(f"  {dest:<6}{str(next_hop):<10}{cost}")


if __name__ == "__main__":
    main()
