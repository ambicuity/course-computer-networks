#!/usr/bin/env python3
"""Multicast routing toolkit (stdlib only).

Demonstrates the four mechanisms from chapter 5.2.8 "Multicast Routing":

1. Class D -> Ethernet MAC mapping and the 32-way (2^5) aliasing problem.
2. Reverse Path Forwarding (RPF): accept a packet only if it arrived on the
   interface the router would use to reach the source unicast.
3. Source-based tree construction: RPF flood + recursive PRUNE.
4. Core-based (shared) tree construction: union of member->core shortest paths.

No third-party packages, no network calls. Runs under plain `python3 main.py`.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Set, Tuple

# IANA-reserved OUI for IPv4 multicast frames (RFC 1112 section 6.4).
MULTICAST_OUI = (0x01, 0x00, 0x5E)
CLASS_D_FIRST_OCTET_LOW = 224  # 1110 0000
CLASS_D_FIRST_OCTET_HIGH = 239  # 1110 1111

Graph = Dict[str, List[str]]  # undirected adjacency list


# --------------------------------------------------------------------------- #
# 1. Class D address -> Ethernet MAC mapping
# --------------------------------------------------------------------------- #
def ipv4_to_multicast_mac(ip: str) -> str:
    """Map a Class D IPv4 group address to its 01:00:5E Ethernet MAC.

    Only the low 23 bits of the 28-bit group id are copied into the MAC, so
    2^5 = 32 distinct groups alias to the same frame address.
    """
    octets = [int(o) for o in ip.split(".")]
    if len(octets) != 4 or not all(0 <= o <= 255 for o in octets):
        raise ValueError(f"not a dotted-quad IPv4 address: {ip!r}")
    if not CLASS_D_FIRST_OCTET_LOW <= octets[0] <= CLASS_D_FIRST_OCTET_HIGH:
        raise ValueError(f"{ip} is not Class D (224.0.0.0 - 239.255.255.255)")

    ip_int = (octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]
    low23 = ip_int & 0x7FFFFF  # keep only the low 23 bits
    mac_bytes = (
        MULTICAST_OUI[0],
        MULTICAST_OUI[1],
        MULTICAST_OUI[2],
        (low23 >> 16) & 0x7F,  # bit 24 is forced to 0
        (low23 >> 8) & 0xFF,
        low23 & 0xFF,
    )
    return ":".join(f"{b:02X}" for b in mac_bytes)


def aliasing_group(ip: str) -> List[str]:
    """Return all 32 Class D addresses that share ``ip``'s Ethernet MAC."""
    octets = [int(o) for o in ip.split(".")]
    ip_int = (octets[0] << 24) | (octets[1] << 16) | (octets[2] << 8) | octets[3]
    low23 = ip_int & 0x7FFFFF
    out: List[str] = []
    for high5 in range(32):  # the 5 discarded bits of the group id
        # prefix 1110 occupies bits 28-31; high5 occupies bits 23-27.
        candidate = (0b1110 << 28) | (high5 << 23) | low23
        out.append(
            f"{(candidate >> 24) & 0xFF}.{(candidate >> 16) & 0xFF}."
            f"{(candidate >> 8) & 0xFF}.{candidate & 0xFF}"
        )
    return out


# --------------------------------------------------------------------------- #
# 2. Reverse Path Forwarding check
# --------------------------------------------------------------------------- #
def rpf_check(arrival_iface: str, rpf_iface: str) -> Tuple[bool, str]:
    """Return (accept, reason).

    Accept only if the packet arrived on the interface the router would use to
    reach the source (the RPF interface); otherwise drop.
    """
    if arrival_iface == rpf_iface:
        return True, f"arrived on RPF interface {rpf_iface}: accept + forward"
    return (
        False,
        f"arrived on {arrival_iface} but RPF interface is {rpf_iface}: "
        f"drop (off reverse path / loop or stale route)",
    )


# --------------------------------------------------------------------------- #
# Shortest-path helpers (unweighted BFS; networks here are unit-cost)
# --------------------------------------------------------------------------- #
def shortest_path(graph: Graph, src: str, dst: str) -> List[str]:
    """BFS shortest path src -> dst, inclusive. Empty list if unreachable."""
    if src == dst:
        return [src]
    prev: Dict[str, str] = {src: src}
    q = deque([src])
    while q:
        node = q.popleft()
        for nb in graph[node]:
            if nb not in prev:
                prev[nb] = node
                if nb == dst:
                    path = [dst]
                    while path[-1] != src:
                        path.append(prev[path[-1]])
                    return list(reversed(path))
                q.append(nb)
    return []


# --------------------------------------------------------------------------- #
# 3. Source-based tree: RPF flood + recursive PRUNE
# --------------------------------------------------------------------------- #
def broadcast_tree_links(graph: Graph, source: str) -> Set[Tuple[str, str]]:
    """Full (unpruned) RPF broadcast tree link set, for before/after counts."""
    links: Set[Tuple[str, str]] = set()
    for node in graph:
        if node == source:
            continue
        path = shortest_path(graph, source, node)
        if len(path) >= 2:
            links.add(tuple(sorted((path[-1], path[-2]))))
    return links


def build_source_tree(
    graph: Graph, source: str, members: Set[str]
) -> Set[Tuple[str, str]]:
    """Build a pruned source-based multicast tree.

    Step 1: RPF flood from ``source`` over a sink tree (shortest paths),
    producing the full broadcast tree. Step 2: recursively PRUNE any leaf
    router that has no member below it.
    """
    parent: Dict[str, str] = {}
    children: Dict[str, List[str]] = {n: [] for n in graph}
    for node in graph:
        if node == source:
            continue
        path = shortest_path(graph, source, node)
        if len(path) >= 2:
            par = path[-2]
            parent[node] = par
            children[par].append(node)

    keep: Set[str] = set()

    def has_member_below(node: str) -> bool:
        survives = node in members
        for ch in children[node]:
            if has_member_below(ch):
                survives = True
        if survives:
            keep.add(node)
        return survives

    has_member_below(source)
    keep.add(source)

    links: Set[Tuple[str, str]] = set()
    for node, par in parent.items():
        if node in keep:  # link survives only if the child node is kept
            links.add(tuple(sorted((node, par))))
    return links


# --------------------------------------------------------------------------- #
# 4. Core-based (shared) tree: union of member->core shortest paths
# --------------------------------------------------------------------------- #
def build_core_tree(
    graph: Graph, core: str, members: Set[str]
) -> Set[Tuple[str, str]]:
    """Shared tree = union of the shortest path from each member to the core."""
    links: Set[Tuple[str, str]] = set()
    for m in members:
        path = shortest_path(graph, m, core)
        for a, b in zip(path, path[1:]):
            links.add(tuple(sorted((a, b))))
    return links


def max_member_path(graph: Graph, root: str, members: Set[str]) -> int:
    """Worst-case hop distance from ``root`` to any member."""
    return max(
        (len(shortest_path(graph, root, m)) - 1 for m in members), default=0
    )


# --------------------------------------------------------------------------- #
# Demonstration
# --------------------------------------------------------------------------- #
def main() -> None:
    print("=" * 68)
    print("1. CLASS D -> ETHERNET MAC MAPPING (23-bit, 32-way aliasing)")
    print("=" * 68)
    for ip in ("224.1.1.1", "225.1.1.1", "239.129.1.1", "239.255.255.250"):
        print(f"  {ip:<18} -> {ipv4_to_multicast_mac(ip)}")
    print("\n  These groups all collide to one MAC (top 5 group bits discarded):")
    for ip in aliasing_group("224.1.1.1")[:4]:
        print(f"     {ip:<14} -> {ipv4_to_multicast_mac(ip)}")
    print("  ... 32 IP groups total share that frame address.")

    print("\n" + "=" * 68)
    print("2. REVERSE PATH FORWARDING CHECK")
    print("=" * 68)
    print("  Router R: RPF interface toward source S is eth2.")
    for arrival in ("eth2", "eth0", "eth1"):
        ok, reason = rpf_check(arrival, "eth2")
        print(f"  packet on {arrival:<5} -> {'ACCEPT' if ok else 'DROP  '} | {reason}")
    print("  Route flap: unicast next hop changes to eth0; old eth2 copies now:")
    ok, reason = rpf_check("eth2", "eth0")
    print(f"  packet on eth2  -> {'ACCEPT' if ok else 'DROP  '} | {reason}")

    # Fig 5-16 style topology. Source = leftmost router "A".
    graph: Graph = {
        "A": ["B", "C"],
        "B": ["A", "D", "E"],
        "C": ["A", "E", "F"],
        "D": ["B", "G"],
        "E": ["B", "C", "H"],
        "F": ["C", "I"],
        "G": ["D"],
        "H": ["E"],
        "I": ["F", "J"],
        "J": ["I"],
    }
    source = "A"
    group1 = {"G", "H", "J"}  # scattered -> denser
    group2 = {"H", "J"}  # sparser

    print("\n" + "=" * 68)
    print("3. SOURCE-BASED TREE: RPF FLOOD + PRUNE  (source = A)")
    print("=" * 68)
    full = broadcast_tree_links(graph, source)
    print(f"  Full RPF broadcast tree: {len(full)} links")
    for grp, members in (("group1", group1), ("group2", group2)):
        pruned = build_source_tree(graph, source, members)
        print(
            f"  {grp} members {sorted(members)}: pruned to {len(pruned)} links "
            f"(removed {len(full) - len(pruned)})"
        )
        print(f"     surviving links: {sorted(pruned)}")

    print("\n" + "=" * 68)
    print("4. CORE-BASED (SHARED) TREE  vs  SOURCE TREE")
    print("=" * 68)
    core = "E"  # central rendezvous point
    for grp, members in (("group1", group1), ("group2", group2)):
        src_tree = build_source_tree(graph, source, members)
        core_tree = build_core_tree(graph, core, members)
        print(
            f"  {grp}: source-tree {len(src_tree)} links, "
            f"max path {max_member_path(graph, source, members)} hops"
        )
        print(
            f"        core-tree   {len(core_tree)} links (root={core}), "
            f"max path {max_member_path(graph, core, members)} hops"
        )
    print("\n  Source trees: shortest paths but up to m*n trees of router state.")
    print("  Shared tree:  one tree per group, possibly longer paths.")


if __name__ == "__main__":
    main()
