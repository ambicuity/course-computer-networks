#!/usr/bin/env python3
"""Internet Anatomy simulator: AS relationships and valley-free routing.

Models the Internet as a graph of Autonomous Systems linked by business
relationships: ``c2p`` (customer buys transit from provider, paid) or ``p2p``
(settlement-free peering). Enumerates policy-valid AS paths under the Gao
(2001) valley-free rule -- climb customers-to-providers, cross at most one
peer edge, descend providers-to-customers, never down-then-up -- and prints
rejected shortcuts with the reason. Also decodes reverse-DNS traceroute hop
names into (city, role, operator) triples, flagging where a new AS appears.

Stdlib only; runs under plain ``python3 main.py``. No network calls.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

REL_C2P = "c2p"  # customer -> provider (transit, paid)
REL_P2P = "p2p"  # peer <-> peer (settlement-free)
LEG_UP = "up"          # customer -> provider (forward c2p)
LEG_DOWN = "down"      # provider -> customer (reverse c2p)
LEG_ACROSS = "across"  # peer <-> peer (either direction of p2p)
PHASE_UP, PHASE_ACROSS, PHASE_DOWN = "up", "across", "down"


@dataclass(frozen=True)
class Relationship:
    """A business relationship between two Autonomous Systems. For c2p,
    ``a`` is the customer and ``b`` is the provider; for p2p they are peers."""
    a: str
    b: str
    rel: str


@dataclass
class ASGraph:
    """An Internet-as-graph of Autonomous Systems and their relationships."""
    nodes: Set[str] = field(default_factory=set)
    rels: List[Relationship] = field(default_factory=list)
    adjacency: Dict[str, List[Tuple[str, str]]] = field(
        default_factory=lambda: defaultdict(list)
    )

    def add_edge(self, a: str, b: str, rel: str) -> None:
        """Add a relationship and register both traversal directions. c2p:
        a is customer, b is provider (forward a->b "up", reverse "down").
        p2p: both directions are "across"."""
        if rel not in (REL_C2P, REL_P2P):
            raise ValueError(f"unknown relationship kind: {rel}")
        self.nodes.add(a)
        self.nodes.add(b)
        self.rels.append(Relationship(a, b, rel))
        if rel == REL_C2P:
            self.adjacency[a].append((b, LEG_UP))
            self.adjacency[b].append((a, LEG_DOWN))
        else:
            self.adjacency[a].append((b, LEG_ACROSS))
            self.adjacency[b].append((a, LEG_ACROSS))

    def legs(self, node: str) -> List[Tuple[str, str]]:
        return self.adjacency.get(node, [])


def _next_phase(phase: str, leg: str) -> Optional[str]:
    """New phase after taking ``leg`` from ``phase``, or None if forbidden."""
    if leg == LEG_UP:
        return PHASE_UP if phase == PHASE_UP else None
    if leg == LEG_ACROSS:
        return PHASE_ACROSS if phase == PHASE_UP else None
    if leg == LEG_DOWN:
        return PHASE_DOWN
    return None


def valley_free_paths(
    graph: ASGraph, source: str, dest: str
) -> Tuple[List[List[str]], List[Tuple[List[str], str]]]:
    """Enumerate all valley-free AS paths from source to dest. Returns
    (valid_paths, rejected) where rejected lists (path, reason)."""
    valid: List[List[str]] = []
    rejected: List[Tuple[List[str], str]] = []
    seen: Set[Tuple[str, Tuple[str, ...], str]] = set()

    def step(node: str, path: List[str], phase: str) -> None:
        if node == dest and len(path) > 1:
            valid.append(list(path))
            return
        for nxt, leg in graph.legs(node):
            if nxt in path:
                continue
            new_phase = _next_phase(phase, leg)
            if new_phase is None:
                reason = (f"{leg} step while in {phase} phase "
                          f"(would make a valley: down-then-up or "
                          f"two peer edges)")
                rejected.append((path + [nxt], reason))
                continue
            key = (nxt, tuple(path), new_phase)
            if key in seen:
                continue
            seen.add(key)
            step(nxt, path + [nxt], new_phase)

    step(source, [source], PHASE_UP)
    return valid, rejected


def annotate_path(path: List[str], graph: ASGraph) -> List[str]:
    """Label each hop of a path with its leg (up/down/across)."""
    labels: List[str] = []
    for i in range(len(path) - 1):
        a, b = path[i], path[i + 1]
        leg = "?"
        for nbr, lbl in graph.legs(a):
            if nbr == b:
                leg = lbl
                break
        labels.append(leg)
    return labels


def traceroute_decode(hops: List[str]) -> List[Tuple[str, str, str, bool]]:
    """Decode reverse-DNS hop names into (city, role, operator, new_as).
    e.g. ``ae-2.r21.fra00.telekom.net`` -> city ``fra``, role ``r21``,
    operator ``telekom``. A new operator (new AS) flags a peering or
    transit handoff in a real traceroute."""
    decoded: List[Tuple[str, str, str, bool]] = []
    prev_op: Optional[str] = None
    for hop in hops:
        parts = hop.lower().split(".")
        city = role = operator = "?"
        for p in parts:
            if len(p) == 3 and p.isalpha() and city == "?":
                city = p
            elif p.startswith(("ae", "r", "pos", "et", "ge")) and role == "?":
                role = p
        if len(parts) >= 2:
            operator = parts[-2]
        new_as = prev_op is not None and operator != prev_op
        decoded.append((city, role, operator, new_as))
        prev_op = operator
    return decoded


def build_demo_graph() -> ASGraph:
    """Construct the worked-example AS graph. A and B are access ISPs; R is
    a regional provider; T1 and T2 are tier-1s that peer at an IXP; C is
    content reachable through T2. The shortcut A<->B (p2p) is forbidden by
    the valley-free rule for traffic destined to C."""
    g = ASGraph()
    g.add_edge("A", "R", REL_C2P)
    g.add_edge("R", "T1", REL_C2P)
    g.add_edge("B", "T2", REL_C2P)
    g.add_edge("C", "T2", REL_C2P)
    g.add_edge("A", "B", REL_P2P)
    g.add_edge("T1", "T2", REL_P2P)
    return g


def _print_as_graph(graph: ASGraph) -> None:
    print("Relationships in the demo AS graph:")
    for rel in graph.rels:
        if rel.rel == REL_C2P:
            print(f"  {rel.a:>3}  --transit(c2p)-->  {rel.b:>3}   "
                  f"({rel.a} is customer, pays {rel.b})")
        else:
            print(f"  {rel.a:>3}  <--peering(p2p)-->  {rel.b:>3}   "
                  f"(settlement-free, at an IXP)")
    print()


def _print_paths(graph: ASGraph, source: str, dest: str) -> None:
    valid, rejected = valley_free_paths(graph, source, dest)
    print(f"Valley-free paths from {source} to {dest}: {len(valid)}")
    for path in valid:
        labels = annotate_path(path, graph)
        tagged = " -> ".join(
            f"{node}[{label}]" for node, label in zip(path[1:], labels))
        print(f"  {path[0]} -> {tagged}")
    print()
    print(f"Rejected candidate paths (valley violations): {len(rejected)}")
    for path, reason in rejected:
        print(f"  {' -> '.join(path)}")
        print(f"      REJECTED: {reason}")
    print()


def _print_traceroute() -> None:
    print("-" * 68)
    print("TRACEROUTE decoder: reading reverse-DNS hop names as anatomy")
    print("-" * 68)
    sample_hops = [
        "192.168.1.1", "ppp.ber01.telekom.net", "ae-1.r02.fra.telekom.net",
        "ae-4.r21.ams.telekom.net", "cloudflare.peer.ams-ix.net", "1.1.1.1",
    ]
    print("Sample hops (as traceroute + reverse-DNS lookup would show):")
    for i, hop in enumerate(sample_hops, 1):
        print(f"  {i:>2}  {hop}")
    print()
    decoded = traceroute_decode(sample_hops)
    print("Decoded anatomy:")
    for i, (hop, (city, role, op, new_as)) in enumerate(
        zip(sample_hops, decoded), 1
    ):
        flag = "  <== new AS: peering or transit handoff" if new_as else ""
        print(f"  hop {i:>2}: city={city:>4} role={role:>5} op={op:>10}{flag}")
    print()
    print("The hop where a new operator appears at the SAME city (ams) is the")
    print("IXP peering handoff -- a single L2 hop across the exchange fabric.")
    print("Hops within one operator (telekom) are transit inside its backbone.")


def main() -> None:
    graph = build_demo_graph()
    source, dest = "A", "C"
    print("=" * 68)
    print("INTERNET ANATOMY: AS relationships and valley-free routing")
    print("=" * 68)
    print(f"Source AS: {source} (access ISP)   Destination AS: {dest} (content)")
    print()
    _print_as_graph(graph)
    _print_paths(graph, source, dest)
    _print_traceroute()


if __name__ == "__main__":
    main()
