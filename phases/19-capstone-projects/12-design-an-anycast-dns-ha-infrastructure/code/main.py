#!/usr/bin/env python3
"""Capstone 12: Design an Anycast DNS HA Infrastructure.

Simulates a 4-node anycast DNS topology (VIP 192.0.2.53) with BGP route
propagation, ECMP load distribution, health-check-driven BGP withdrawal,
and a side-by-side comparison against unicast failover.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

VIP = "192.0.2.53"
HC_INTERVAL = 5.0
HC_STRIKES = 3
BGP_CONVERGE = 0.5
UNICAST_TIMEOUT = 5.0
REGIONS = ["US-East", "US-West", "EU-West", "AP-South"]


class Status(Enum):
    HEALTHY = "Healthy"
    FAILED = "Failed"


@dataclass
class Node:
    name: str
    region: str
    asn: int
    latency: dict[str, float]
    status: Status = Status.HEALTHY
    strikes: int = 0
    advertising: bool = True


@dataclass
class Client:
    name: str
    hosts: int
    asn: int
    connected: list[int]


@dataclass
class Route:
    origin: str
    origin_asn: int
    as_path: list[int]
    active: bool = True


@dataclass
class Event:
    t: float
    kind: str
    detail: str


def build_topology() -> tuple[dict[str, Node], dict[str, Client]]:
    """4 DNS nodes in 4 regions; 4 client regions each with their own ASN."""
    nodes = {
        "DNS-US-EAST":  Node("DNS-US-EAST",  "US-East",  64501, {"US-East": 8,   "US-West": 45,  "EU-West": 85,  "AP-South": 200}),
        "DNS-US-WEST":  Node("DNS-US-WEST",  "US-West",  64502, {"US-East": 45,  "US-West": 8,   "EU-West": 140, "AP-South": 150}),
        "DNS-EU-WEST":  Node("DNS-EU-WEST",  "EU-West",  64503, {"US-East": 85,  "US-West": 140, "EU-West": 12,  "AP-South": 180}),
        "DNS-AP-SOUTH": Node("DNS-AP-SOUTH", "AP-South", 64504, {"US-East": 200, "US-West": 150, "EU-West": 180, "AP-South": 15}),
    }
    clients = {
        "US-East":  Client("US-East",  5000, 65001, [64501, 64502, 64503, 64504]),
        "US-West":  Client("US-West",  3000, 65002, [64502, 64501, 64504, 64503]),
        "EU-West":  Client("EU-West",  4000, 65003, [64503, 64501, 64502, 64504]),
        "AP-South": Client("AP-South", 2000, 65004, [64504, 64502, 64501, 64503]),
    }
    return nodes, clients


def propagate_routes(nodes: dict[str, Node], clients: dict[str, Client]) -> dict[str, list[Route]]:
    """Build the BGP route table: every client's paths to the VIP."""
    table: dict[str, list[Route]] = {}
    for c in clients.values():
        routes: list[Route] = []
        for n in nodes.values():
            if not n.advertising:
                continue
            path = [n.asn] if n.asn in c.connected else [c.connected[0], n.asn]
            routes.append(Route(n.name, n.asn, path, n.advertising))
        routes.sort(key=lambda r: (len(r.as_path), r.origin_asn))
        table[c.name] = routes
    return table


def select_node(cname: str, table: dict[str, list[Route]], nodes: dict[str, Node]) -> tuple[str, float]:
    """Best-path selection with ECMP tie-break on lowest latency."""
    routes = table.get(cname, [])
    if not routes:
        return "NONE", 9999.0
    best_len = len(routes[0].as_path)
    equal = [r for r in routes if len(r.as_path) == best_len]
    chosen = min(equal, key=lambda r: nodes[r.origin].latency.get(cname, 9999))
    return chosen.origin, nodes[chosen.origin].latency.get(cname, 9999)


def simulate_failover(nodes: dict[str, Node], clients: dict[str, Client], victim: str) -> list[Event]:
    """Drive the timeline: failure -> 3-strike detection -> BGP withdraw -> converge."""
    events: list[Event] = []
    t = 0.0
    nodes[victim].status = Status.FAILED
    events.append(Event(t, "NODE-DOWN", f"{victim} DNS service crashed"))

    while nodes[victim].advertising and nodes[victim].strikes < HC_STRIKES:
        t += HC_INTERVAL
        if nodes[victim].status == Status.FAILED:
            nodes[victim].strikes += 1
            if nodes[victim].strikes >= HC_STRIKES:
                nodes[victim].advertising = False
                events.append(Event(t, "BGP-WITHDRAW",
                                    f"{victim} withdrew {VIP} after {HC_STRIKES} strikes"))

    t += BGP_CONVERGE
    events.append(Event(t, "CONVERGED", f"route withdrawal propagated in {BGP_CONVERGE}s"))
    table = propagate_routes(nodes, clients)
    affected = sum(c.hosts for c in clients.values() if select_node(c.name, table, nodes)[0] != victim)
    events.append(Event(t, "REROUTED", f"{affected} clients moved off {victim}"))
    return events


def ecmp_distribution(nodes: dict[str, Node], clients: dict[str, Client]) -> dict[str, int]:
    """Per-node host count after BGP selection; ECMP hash is implicit in select_node."""
    table = propagate_routes(nodes, clients)
    load = {n: 0 for n in nodes}
    for c in clients.values():
        load[select_node(c.name, table, nodes)[0]] += c.hosts
    return load


def compare_with_unicast(nodes: dict[str, Node], clients: dict[str, Client]) -> dict[str, tuple[float, float]]:
    """For each client region: (anycast_ms, unicast_ms) using the original (healthy) topology."""
    healthy_nodes, healthy_clients = build_topology()
    table = propagate_routes(healthy_nodes, healthy_clients)
    pinned = healthy_nodes["DNS-US-EAST"]
    return {c.name: (select_node(c.name, table, healthy_nodes)[1], pinned.latency.get(c.name, 9999))
            for c in healthy_clients.values()}


def main() -> None:
    print("=" * 65)
    print("Capstone 12: Design an Anycast DNS HA Infrastructure")
    print("=" * 65)

    nodes, clients = build_topology()
    print(f"\n  Anycast VIP: {VIP}")
    print(f"\n  DNS Nodes ({len(nodes)}):")
    print(f"  {'Node':<16} {'Region':<10} {'ASN':<8} {'Status':<10} {'Adv':<5}")
    for n in nodes.values():
        print(f"  {n.name:<16} {n.region:<10} AS{n.asn:<6} {n.status.value:<10} {str(n.advertising):<5}")

    print(f"\n  Client regions ({len(clients)}):")
    print(f"  {'Region':<10} {'Hosts':<8} {'ASN':<8} {'Connected ASNs'}")
    for c in clients.values():
        print(f"  {c.name:<10} {c.hosts:<8} AS{c.asn:<6} {c.connected}")

    table = propagate_routes(nodes, clients)
    print(f"\n  BGP Route Table (best AS-path per client):")
    for cname in clients:
        print(f"    {cname}:")
        for r in table[cname]:
            path = " ".join(f"AS{a}" for a in r.as_path)
            print(f"      via {r.origin:<16} AS-path=[{path}] active={r.active}")

    print(f"\n  Query routing:")
    print(f"  {'Region':<10} {'Selected Node':<16} {'Latency':<10}")
    for cname in clients:
        winner, lat = select_node(cname, table, nodes)
        print(f"  {cname:<10} {winner:<16} {lat:.0f}ms")

    print(f"\n  Load distribution:")
    total = sum(c.hosts for c in clients.values())
    for n, hosts in ecmp_distribution(nodes, clients).items():
        print(f"    {n:<16} {hosts:>6} hosts ({hosts / total * 100:.0f}%)")

    print(f"\n  --- Failover Simulation: DNS-US-EAST goes down ---")
    events = simulate_failover(nodes, clients, "DNS-US-EAST")
    elapsed = 0.0
    for e in events:
        elapsed = max(elapsed, e.t)
        print(f"    t={e.t:.1f}s  {e.kind}: {e.detail}")

    print(f"\n  Total anycast failover time: {elapsed:.1f}s "
          f"(HC: {HC_STRIKES * HC_INTERVAL:.0f}s, BGP converge: {BGP_CONVERGE}s)")

    print(f"\n  Post-failover routing:")
    table = propagate_routes(nodes, clients)
    for cname in clients:
        winner, lat = select_node(cname, table, nodes)
        print(f"    {cname:<10} -> {winner:<16} {lat:.0f}ms")

    print(f"\n  --- Anycast vs. Unicast Comparison ---")
    print(f"  {'Region':<10} {'Anycast':<10} {'Unicast':<10} {'Improvement'}")
    for cname, (a, u) in compare_with_unicast(nodes, clients).items():
        print(f"  {cname:<10} {a:<10.0f} {u:<10.0f} {(u - a) / u * 100:.0f}%")

    print(f"\n  {'Metric':<22} {'Anycast':<14} {'Unicast':<14}")
    print(f"  {'Nodes':<22} {'4':<14} {'1':<14}")
    print(f"  {'Failover':<22} {f'{elapsed:.1f}s':<14} {f'{UNICAST_TIMEOUT:.0f}s+':<14}")
    print(f"  {'Redundancy':<22} {'N-1':<14} {'None':<14}")
    print(f"  {'SPOF':<22} {'No':<14} {'Yes':<14}")


if __name__ == "__main__":
    main()
