#!/usr/bin/env python3
"""Mobile IP simulator and multicast routing-tree builder (Tanenbaum 5.6.8-5.6.9).

Stdlib only. Two independent parts:

Part 1 - Mobile IP (Sec. 5.6.9): simulates home agent, foreign agent,
care-of address registration, and reverse tunneling of packets from
the home network to a visiting mobile host.  Shows the triangular
routing the source material describes.

Part 2 - Internet Multicasting (Sec. 5.6.8): builds a multicast
distribution tree from a source to a group of receivers using a
shortest-path-tree algorithm, with IGMP-style group membership on
each LAN and local-scope vs global-scope address classification.

Run:  python3 main.py
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Optional

INF = float("inf")

MULTICAST_LOCAL: tuple[int, int] = (0xE0000000, 0xE00000FF)


@dataclass
class MobileHost:
    name: str
    home_addr: str
    care_of_addr: Optional[str] = None
    home_agent: Optional[str] = None
    visited_agent: Optional[str] = None

    @property
    def is_at_home(self) -> bool:
        return self.care_of_addr is None


@dataclass
class Agent:
    name: str
    network_prefix: str
    mobiles: dict[str, MobileHost] = field(default_factory=dict)

    def register_visitor(self, host: MobileHost, coa: str) -> None:
        host.care_of_addr = coa
        host.visited_agent = self.name
        self.mobiles[host.name] = host


@dataclass
class HomeAgent:
    name: str
    network_prefix: str
    bindings: dict[str, str] = field(default_factory=dict)

    def register_mobile(self, host: MobileHost, coa: str) -> None:
        host.home_agent = self.name
        self.bindings[host.home_addr] = coa
        print(f"  [{self.name}] binding: {host.home_addr} -> {coa} "
              f"(for {host.name})")

    def intercept_and_tunnel(self, dst_addr: str, packet: bytes) -> Optional[bytes]:
        coa = self.bindings.get(dst_addr)
        if coa is None:
            return None
        tunneled = _encap(packet, coa)
        print(f"  [{self.name}] tunnel packet for {dst_addr} -> {coa}")
        return tunneled


def _encap(inner: bytes, dst: str) -> bytes:
    header = bytes([0x45, 0x00, 0x00, 0x14, 0x00, 0x00, 0x00, 0x00,
                    0x40, 0x04, 0x00, 0x00, 0x0A, 0x00, 0x00, 0x01])
    dst_bytes = bytes(int(p) for p in dst.split("."))
    return header + dst_bytes + inner


def simulate_mobile_ip() -> None:
    ha = HomeAgent(name="HA-Home", network_prefix="160.80.0.0/16")
    fa = Agent(name="FA-Foreign", network_prefix="192.1.1.0/24")
    mh = MobileHost(name="Mobile-1", home_addr="160.80.40.20")
    print(f"  Mobile host: {mh.name}  home_addr={mh.home_addr}")
    print(f"  Home agent:  {ha.name}  prefix={ha.network_prefix}")
    print(f"  Foreign agent: {fa.name}  prefix={fa.network_prefix}")
    print()
    print("  Step 1: Mobile moves to foreign network, gets care-of address")
    coa = "192.1.1.55"
    fa.register_visitor(mh, coa)
    print(f"  {mh.name} care-of address = {coa}")
    print()
    print("  Step 2: Mobile registers with home agent")
    ha.register_mobile(mh, coa)
    print()
    print("  Step 3: Correspondent sends packet to mobile's home address")
    packet = b"HELLO-MOBILE"
    print(f"  Packet: {packet!r}  dst={mh.home_addr}")
    print("  Step 4: Home agent intercepts and tunnels to care-of address")
    tunneled = ha.intercept_and_tunnel(mh.home_addr, packet)
    if tunneled:
        print(f"  Tunneled packet ({len(tunneled)} bytes) delivered to {coa}")
    print("  Step 5: Foreign agent decapsulates and delivers to mobile")
    print(f"  {mh.name} receives: {packet!r}")
    print()
    print("  Triangular routing: correspondent -> HA -> FA -> mobile")
    print("  Mobile replies directly to correspondent (no tunnel back)")


@dataclass
class MulticastGroup:
    group_addr: str
    members: list[str] = field(default_factory=list)

    def is_local_scope(self) -> bool:
        parts = self.group_addr.split(".")
        first = int(parts[0])
        if first == 224 and int(parts[1]) == 0 and int(parts[2]) == 0:
            return True
        return False


def build_multicast_tree(
    topology: dict[str, dict[str, float]],
    source: str,
    group: MulticastGroup,
) -> dict[str, float]:
    """Shortest-path tree from source to all group members (Dijkstra)."""
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
    tree: dict[str, float] = {}
    for member in group.members:
        if dist[member] < INF:
            path: list[str] = []
            node: Optional[str] = member
            while node is not None and node != source:
                path.append(node)
                node = prev[node]
            path.append(source)
            tree[member] = dist[member]
    return tree


def simulate_multicast() -> None:
    topology: dict[str, dict[str, float]] = {
        "S": {"R1": 1, "R2": 1},
        "R1": {"S": 1, "R3": 1, "R4": 1},
        "R2": {"S": 1, "R5": 1},
        "R3": {"R1": 1, "H1": 1},
        "R4": {"R1": 1, "H2": 1},
        "R5": {"R2": 1, "H3": 1},
        "H1": {"R3": 1},
        "H2": {"R4": 1},
        "H3": {"R5": 1},
    }
    print("  Topology nodes: S, R1-R5, H1-H3")
    print("  Source: S")
    groups = [
        MulticastGroup("224.0.0.1", ["H1", "H2", "H3"]),
        MulticastGroup("224.0.0.5", ["H1", "H2"]),
        MulticastGroup("239.1.1.1", ["H1", "H2", "H3"]),
    ]
    for g in groups:
        scope = "local (no routing needed)" if g.is_local_scope() else "global"
        print()
        print(f"  Group {g.group_addr}  scope={scope}  members={g.members}")
        tree = build_multicast_tree(topology, "S", g)
        for member, cost in sorted(tree.items()):
            print(f"    S -> {member}  cost={cost:.0f}")
        if not tree:
            print("    (no reachable members)")


def main() -> None:
    print("=" * 64)
    print("Mobile IP Simulator  --  Tanenbaum 5.6.9")
    print("=" * 64)
    simulate_mobile_ip()

    print()
    print("=" * 64)
    print("Internet Multicasting  --  Tanenbaum 5.6.8")
    print("=" * 64)
    simulate_multicast()

    print()
    print("=" * 64)
    print("IGMP membership tracking")
    print("=" * 64)
    host_groups: dict[str, list[str]] = {
        "H1": ["224.0.0.1", "224.0.0.5", "239.1.1.1"],
        "H2": ["224.0.0.1", "239.1.1.1"],
        "H3": ["224.0.0.1"],
    }
    for host, groups in host_groups.items():
        print(f"  {host} groups: {', '.join(groups)}")
    all_groups: dict[str, list[str]] = {}
    for host, groups in host_groups.items():
        for g in groups:
            all_groups.setdefault(g, []).append(host)
    print("  Multicast router sees:")
    for g, members in sorted(all_groups.items()):
        print(f"    {g}: {members}")


if __name__ == "__main__":
    main()