"""Anycast routing solver and catchment calculator.

Demonstrates the central claim of Tanenbaum section 5.2.9: anycast needs no new
routing protocol. Several physical nodes share ONE address; ordinary shortest-path
routing (here Dijkstra, plus a Bellman-Ford cross-check) delivers every source to
its nearest instance.

Technique: fuse all instances that advertise the shared anycast address into a
single synthetic sink, then run shortest path from every client to that sink. The
predecessor that the sink is reached through tells you WHICH real instance won --
that is the source's catchment assignment.

Stdlib only. No network calls. Run: python3 main.py
"""

from __future__ import annotations

import heapq
from typing import Dict, List, Optional, Tuple

# An undirected weighted graph: node -> list of (neighbor, cost).
Graph = Dict[str, List[Tuple[str, int]]]

INFINITY = float("inf")
SYNTHETIC_SINK = "__ANYCAST_SINK__"


def add_edge(graph: Graph, a: str, b: str, cost: int) -> None:
    """Insert an undirected edge a<->b with the given cost."""
    graph.setdefault(a, []).append((b, cost))
    graph.setdefault(b, []).append((a, cost))


def build_topology(instances: List[str]) -> Graph:
    """Worked example from the lesson: A-B-C-D clients, S1/S2 anycast instances.

        A --1-- B --4-- C --1-- D
        |               |
        2               2
        |               |
        S1              S2
    """
    graph: Graph = {}
    add_edge(graph, "A", "B", 1)
    add_edge(graph, "B", "C", 4)
    add_edge(graph, "C", "D", 1)
    if "S1" in instances:
        add_edge(graph, "A", "S1", 2)
    if "S2" in instances:
        add_edge(graph, "C", "S2", 2)
    return graph


def _fuse_instances(graph: Graph, instances: List[str]) -> Graph:
    """Return a new graph with every instance wired to a zero-cost synthetic sink.

    This models the routing protocol's belief that all instances ARE one node.
    """
    fused: Graph = {node: list(edges) for node, edges in graph.items()}
    for inst in instances:
        if inst in fused:
            add_edge(fused, inst, SYNTHETIC_SINK, 0)
    return fused


def dijkstra(graph: Graph, source: str) -> Tuple[Dict[str, float], Dict[str, Optional[str]]]:
    """Standard Dijkstra. Returns (distance map, predecessor map)."""
    dist: Dict[str, float] = {node: INFINITY for node in graph}
    prev: Dict[str, Optional[str]] = {node: None for node in graph}
    dist[source] = 0
    pq: List[Tuple[float, str]] = [(0, source)]
    while pq:
        d, node = heapq.heappop(pq)
        if d > dist[node]:
            continue
        for neighbor, cost in graph[node]:
            candidate = d + cost
            if candidate < dist[neighbor]:
                dist[neighbor] = candidate
                prev[neighbor] = node
                heapq.heappush(pq, (candidate, neighbor))
    return dist, prev


def _winning_instance(prev: Dict[str, Optional[str]], instances: List[str]) -> Optional[str]:
    """The sink is reached through exactly one real instance: that is the winner."""
    hop_before_sink = prev.get(SYNTHETIC_SINK)
    if hop_before_sink in instances:
        return hop_before_sink
    return None


def anycast_catchments(
    graph: Graph, instances: List[str], clients: List[str]
) -> Dict[str, Tuple[Optional[str], float]]:
    """For each client, return (winning instance, total cost to it)."""
    fused = _fuse_instances(graph, instances)
    result: Dict[str, Tuple[Optional[str], float]] = {}
    for client in clients:
        _dist, prev = dijkstra(fused, client)
        dist = _dist
        winner = _winning_instance(prev, instances)
        result[client] = (winner, dist[SYNTHETIC_SINK])
    return result


def withdraw_instance(instances: List[str], dead: str) -> List[str]:
    """Return a new instance list with `dead` removed (failure-mode simulation)."""
    return [inst for inst in instances if inst != dead]


def bellman_ford_to_sink(graph: Graph, instances: List[str], source: str) -> float:
    """Distance-vector cross-check: shortest distance from source to the fused sink.

    Proves the textbook point that distance-vector routing produces the SAME
    anycast routes as link-state routing.
    """
    fused = _fuse_instances(graph, instances)
    dist: Dict[str, float] = {node: INFINITY for node in fused}
    dist[source] = 0
    for _ in range(len(fused) - 1):
        changed = False
        for node in fused:
            if dist[node] == INFINITY:
                continue
            for neighbor, cost in fused[node]:
                if dist[node] + cost < dist[neighbor]:
                    dist[neighbor] = dist[node] + cost
                    changed = True
        if not changed:
            break
    return dist[SYNTHETIC_SINK]


def _print_catchments(title: str, catchments: Dict[str, Tuple[Optional[str], float]]) -> None:
    print(title)
    print(f"  {'source':<8}{'instance':<12}{'cost':<6}")
    print(f"  {'-' * 24}")
    by_instance: Dict[str, List[str]] = {}
    for client, (winner, cost) in sorted(catchments.items()):
        label = winner if winner else "UNREACHABLE"
        print(f"  {client:<8}{label:<12}{cost:<6}")
        by_instance.setdefault(label, []).append(client)
    print("  catchments:", {k: v for k, v in sorted(by_instance.items())})
    print()


def main() -> None:
    clients = ["A", "B", "C", "D"]
    instances = ["S1", "S2"]
    graph = build_topology(instances)

    print("=" * 52)
    print("ANYCAST ROUTING -- one address 'S' at instances S1, S2")
    print("=" * 52)
    print()

    catchments = anycast_catchments(graph, instances, clients)
    _print_catchments("Normal state (link-state / Dijkstra):", catchments)

    print("Distance-vector cross-check (Bellman-Ford):")
    for client in clients:
        dv = bellman_ford_to_sink(graph, instances, client)
        ls = catchments[client][1]
        match = "OK" if dv == ls else "MISMATCH"
        print(f"  {client}: DV cost={dv}  LS cost={ls}  [{match}]")
    print()

    print("Failure mode: S1 withdrawn (BGP WITHDRAW / node down).")
    print("Every flow pinned to S1 is re-pathed -- stateful TCP would RST.")
    survivors = withdraw_instance(instances, "S1")
    degraded = anycast_catchments(graph, survivors, clients)
    _print_catchments("Degraded state:", degraded)

    print("Observation: A and B shifted from S1 to S2, and their cost rose")
    print("(A: 2 -> 7, B: 3 -> 6). That cost jump is the re-pathing latency hit.")


if __name__ == "__main__":
    main()
