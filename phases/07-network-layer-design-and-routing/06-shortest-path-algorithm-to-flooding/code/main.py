"""Shortest path (Dijkstra) and flooding on the same router topology.

This module builds the weighted graph from Tanenbaum Fig. 5-7 and demonstrates
the two foundational routing primitives of the network layer:

  1. dijkstra()  -- computes shortest paths from a source to every node using
     the classic (length, predecessor, label) labeling scheme, promoting the
     smallest tentative node to permanent each round. It records a trace of the
     promotions so you can compare against the textbook step (b)-(f) table.

  2. flood()     -- forwards every incoming packet on every line except the one
     it arrived on, damped by a hop counter (TTL) and, optionally, by per-source
     sequence-number suppression with a summarizing counter k. It counts the
     duplicate explosion so you can see suppression collapse it.

Pure standard library. No network calls. Run: python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

INFINITY = 10**9  # larger than any real path; mirrors the textbook INFINITY


@dataclass
class Graph:
    """Undirected weighted graph: nodes are routers, edges are links."""

    adjacency: Dict[str, Dict[str, int]] = field(default_factory=dict)

    def add_edge(self, u: str, v: str, weight: int) -> None:
        if weight < 0:
            raise ValueError(
                f"negative weight {weight} on {u}-{v}: Dijkstra requires non-negative weights"
            )
        self.adjacency.setdefault(u, {})[v] = weight
        self.adjacency.setdefault(v, {})[u] = weight

    def neighbors(self, node: str) -> Dict[str, int]:
        return self.adjacency.get(node, {})

    def nodes(self) -> List[str]:
        return sorted(self.adjacency.keys())


@dataclass
class NodeState:
    """Per-node Dijkstra state: distance, predecessor, and label."""

    length: int = INFINITY
    predecessor: Optional[str] = None
    label: str = "tentative"  # or "permanent"


def dijkstra(graph: Graph, source: str) -> Tuple[Dict[str, NodeState], List[str]]:
    """Return final per-node state plus the ordered list of promoted nodes.

    Uses the O(V^2) array scan from Fig. 5-8 so the trace is easy to follow.
    """
    state: Dict[str, NodeState] = {n: NodeState() for n in graph.nodes()}
    state[source].length = 0
    state[source].label = "permanent"
    working = source
    promotion_trace: List[str] = [source]

    while True:
        # Relax every tentative neighbor of the working node.
        for neighbor, weight in graph.neighbors(working).items():
            ns = state[neighbor]
            if ns.label == "tentative":
                candidate = state[working].length + weight
                if candidate < ns.length:
                    ns.length = candidate
                    ns.predecessor = working

        # Find the smallest tentative node across the whole graph.
        best_node: Optional[str] = None
        best_len = INFINITY
        for node, ns in state.items():
            if ns.label == "tentative" and ns.length < best_len:
                best_len = ns.length
                best_node = node

        if best_node is None:  # all reachable nodes are permanent
            break

        state[best_node].label = "permanent"
        promotion_trace.append(best_node)
        working = best_node

    return state, promotion_trace


def reconstruct_path(state: Dict[str, NodeState], destination: str) -> List[str]:
    """Walk predecessors backward from destination to source, then reverse."""
    path: List[str] = []
    cur: Optional[str] = destination
    while cur is not None:
        path.append(cur)
        cur = state[cur].predecessor
    path.reverse()
    return path


@dataclass
class FloodResult:
    forwards: int  # total packet copies put on a wire
    delivered: List[str]  # nodes that received at least one copy
    final_k: Dict[str, int]  # per-router highest seq summarized (suppression on)


def flood(
    graph: Graph,
    source: str,
    seq: int,
    hop_limit: int,
    suppress: bool,
) -> FloodResult:
    """Flood one packet from source.

    Without suppression: each router re-forwards on every line except the inbound
    one, bounded only by the hop counter -> exponential duplicates.
    With suppression: each router keeps a counter k per source; a packet with
    seq <= k is dropped -> exactly one forward per router.
    """
    forwards = 0
    delivered: Set[str] = {source}
    seen_k: Dict[str, int] = {n: -1 for n in graph.nodes()}

    # queue items: (current_router, arrived_from, remaining_hops)
    queue: List[Tuple[str, Optional[str], int]] = [(source, None, hop_limit)]

    while queue:
        router, arrived_from, hops = queue.pop(0)

        if hops <= 0:  # hop counter (TTL) reached zero -> discard
            continue

        if suppress:
            if seq <= seen_k[router]:  # already flooded this or newer -> drop
                continue
            seen_k[router] = max(seen_k[router], seq)

        for neighbor in graph.neighbors(router):
            if neighbor == arrived_from:  # never send back where it came from
                continue
            forwards += 1
            delivered.add(neighbor)
            queue.append((neighbor, router, hops - 1))

    return FloodResult(forwards=forwards, delivered=sorted(delivered), final_k=seen_k)


def build_textbook_graph() -> Graph:
    """The weighted graph of Tanenbaum Fig. 5-7 (used for the A->D example)."""
    g = Graph()
    g.add_edge("A", "B", 2)
    g.add_edge("A", "G", 6)
    g.add_edge("B", "C", 7)
    g.add_edge("B", "E", 2)
    g.add_edge("C", "D", 3)
    g.add_edge("E", "F", 2)
    g.add_edge("E", "G", 1)
    g.add_edge("F", "D", 2)
    g.add_edge("G", "H", 4)
    g.add_edge("F", "H", 2)
    return g


def print_dijkstra_report(graph: Graph, source: str, destination: str) -> None:
    state, trace = dijkstra(graph, source)
    print(f"Dijkstra from {source} (promotion order: {' -> '.join(trace)})")
    print(f"{'node':<6}{'length':<8}{'pred':<6}{'label':<10}")
    for node in graph.nodes():
        ns = state[node]
        length = "inf" if ns.length >= INFINITY else str(ns.length)
        pred = ns.predecessor or "-"
        print(f"{node:<6}{length:<8}{pred:<6}{ns.label:<10}")
    path = reconstruct_path(state, destination)
    print(
        f"shortest {source}->{destination}: {' '.join(path)}  "
        f"cost={state[destination].length}"
    )


def print_flood_report(graph: Graph, source: str) -> None:
    diameter_guess = len(graph.nodes())  # safe worst-case hop budget
    print(f"\nFlooding one packet from {source} (seq=5, hop_limit={diameter_guess})")
    naive = flood(graph, source, seq=5, hop_limit=diameter_guess, suppress=False)
    smart = flood(graph, source, seq=5, hop_limit=diameter_guess, suppress=True)
    print(f"  no suppression : {naive.forwards:>6} forwards, reached {len(naive.delivered)} nodes")
    print(f"  seq-number 'k' : {smart.forwards:>6} forwards, reached {len(smart.delivered)} nodes")
    saved = naive.forwards - smart.forwards
    print(
        f"  suppression removed {saved} duplicate forwards "
        f"({100 * saved / max(naive.forwards, 1):.1f}% of the storm)"
    )


def main() -> None:
    graph = build_textbook_graph()

    print("=" * 60)
    print("SHORTEST PATH (Dijkstra) on Tanenbaum Fig. 5-7")
    print("=" * 60)
    print_dijkstra_report(graph, source="A", destination="D")

    print("\n" + "=" * 60)
    print("Effect of re-weighting A-G from 6 to 30")
    print("=" * 60)
    reweighted = build_textbook_graph()
    reweighted.add_edge("A", "G", 30)
    print_dijkstra_report(reweighted, source="A", destination="G")

    print("\n" + "=" * 60)
    print("FLOODING on the same topology")
    print("=" * 60)
    print_flood_report(graph, source="A")


if __name__ == "__main__":
    main()
