#!/usr/bin/env python3
"""Routing Loop Investigation (Integrated Troubleshooting Lab 06).

Simulates a small network of routers, runs a simplified distance-vector/SPF
computation, and demonstrates the routing-table oscillation that produces
a loop. Walks the four-command diagnostic chain for four scenarios:

  misconfigured_aggregate  - aggregate route with wrong next hop
  ibgp_full_mesh_missing   - iBGP route reflection misconfiguration
  static_route_oscillation - static + dynamic redistribution conflict
  healthy                  - clean network, no loop

Run:  python3 main.py [--mode <mode>|all]
"""
from __future__ import annotations

import argparse
import enum
from dataclasses import dataclass, field
from typing import Iterable


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------
class FailureMode(str, enum.Enum):
    MISCONFIGURED_AGGREGATE = "misconfigured_aggregate"
    IBGP_FULL_MESH_MISSING = "ibgp_full_mesh_missing"
    STATIC_ROUTE_OSCILLATION = "static_route_oscillation"
    HEALTHY = "healthy"


# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Link:
    a: str
    b: str
    cost: int = 1


@dataclass
class Router:
    name: str
    static_routes: dict[str, str] = field(default_factory=dict)
    bgp_neighbors: list[str] = field(default_factory=list)
    received_bgp: dict[str, tuple[str, list[str]]] = field(default_factory=dict)
    # received_bgp maps destination -> (next_hop, as_path)


# ---------------------------------------------------------------------------
# Network and simulator
# ---------------------------------------------------------------------------
class Network:
    """A small three-router network used for the four scenarios."""

    def __init__(self, mode: FailureMode) -> None:
        self.mode = mode
        self.links = [
            Link("CORE-A", "CORE-B", cost=1),
            Link("CORE-B", "EDGE-1", cost=1),
            Link("EDGE-1", "ISP-1", cost=5),
            Link("EDGE-1", "ISP-2", cost=5),
        ]
        self.routers: dict[str, Router] = {
            "CORE-A": Router("CORE-A"),
            "CORE-B": Router("CORE-B"),
            "EDGE-1": Router("EDGE-1", bgp_neighbors=["ISP-1", "ISP-2"]),
            "ISP-1": Router("ISP-1", bgp_neighbors=["EDGE-1"]),
            "ISP-2": Router("ISP-2", bgp_neighbors=["EDGE-1"]),
        }
        # Destination we want to reach
        self.dst = "8.8.8.0/24"
        if mode is FailureMode.MISCONFIGURED_AGGREGATE:
            # EDGE-1 has a static route for the dst that points back into the
            # network (misconfigured aggregate). It advertises this via BGP
            # to ISP-1, which advertises it back via ISP-2.
            self.routers["EDGE-1"].static_routes[self.dst] = "CORE-A"
            self.routers["EDGE-1"].received_bgp[self.dst] = ("CORE-A", ["65002", "65001", "65001"])
        elif mode is FailureMode.IBGP_FULL_MESH_MISSING:
            # EDGE-1 receives a route from ISP-1 that came from ISP-2 via
            # EDGE-1 (route reflection miss).
            self.routers["EDGE-1"].received_bgp[self.dst] = ("ISP-2", ["65002", "65001"])
        elif mode is FailureMode.STATIC_ROUTE_OSCILLATION:
            # CORE-A and CORE-B disagree on the next hop for the dst.
            self.routers["CORE-A"].static_routes[self.dst] = "CORE-B"
            self.routers["CORE-B"].static_routes[self.dst] = "CORE-A"
        else:  # HEALTHY
            # EDGE-1 has a clean BGP route to dst via ISP-1
            self.routers["EDGE-1"].received_bgp[self.dst] = ("ISP-1", ["65003"])

    def is_loop(self) -> bool:
        """Detect a routing loop on the path to dst."""
        # Walk the path from EDGE-1 to dst
        path: list[str] = []
        cur = "EDGE-1"
        for _ in range(10):
            path.append(cur)
            nxt = self._next_hop(cur)
            if nxt is None:
                return False
            if nxt in path:
                return True
            cur = nxt
            if cur.startswith("ISP"):
                return False
        return True

    def _next_hop(self, router: str) -> str | None:
        r = self.routers[router]
        if self.dst in r.static_routes:
            return r.static_routes[self.dst]
        if self.dst in r.received_bgp:
            nxt, _as_path = r.received_bgp[self.dst]
            if nxt.startswith("ISP"):
                return None  # destination reached
            return nxt
        # default: send to the next router in the chain
        if router == "CORE-A":
            return "CORE-B"
        if router == "CORE-B":
            return "EDGE-1"
        return None

    def traceroute(self, max_hops: int = 15) -> list[str]:
        path: list[str] = []
        cur = "EDGE-1"
        for _ in range(max_hops):
            path.append(cur)
            nxt = self._next_hop(cur)
            if nxt is None:
                return path
            if nxt in path:
                path.append(nxt)
                return path
            cur = nxt
        return path

    def ip_route_get_chain(self) -> list[str]:
        chain: list[str] = []
        cur = "EDGE-1"
        for _ in range(10):
            chain.append(f"{cur} -> {self._next_hop(cur) or '<destination>'}")
            nxt = self._next_hop(cur)
            if nxt is None:
                return chain
            if nxt in [c.split(' -> ')[0] for c in chain]:
                return chain + [f"{nxt} -> CYCLE DETECTED"]
            cur = nxt
        return chain


# ---------------------------------------------------------------------------
# Four-command diagnostic chain
# ---------------------------------------------------------------------------
@dataclass
class DiagResult:
    step: int
    name: str
    finding: str
    layer: str
    decisive: bool


def cmd_traceroute(net: Network) -> DiagResult:
    path = net.traceroute()
    is_loop = net.is_loop()
    path_str = " -> ".join(path)
    if is_loop:
        return DiagResult(1, "traceroute -n 8.8.8.8",
                           f"cycle detected: {path_str}",
                           "L3 routing loop", True)
    return DiagResult(1, "traceroute -n 8.8.8.8",
                       f"path: {path_str}",
                       "L3 path", False)


def cmd_ip_route_get(net: Network) -> DiagResult:
    chain = net.ip_route_get_chain()
    chain_str = " / ".join(chain)
    if net.is_loop():
        return DiagResult(2, "ip route get 8.8.8.8 (recursive)",
                           f"chain: {chain_str}",
                           "L3 source router", True)
    return DiagResult(2, "ip route get 8.8.8.8",
                       f"chain: {chain_str}",
                       "L3 next hop", False)


def cmd_show_ospf_db(net: Network) -> DiagResult:
    if net.mode is FailureMode.MISCONFIGURED_AGGREGATE:
        return DiagResult(3, "show ip ospf database",
                           "Type-5 LSA with forwarding-address 10.0.0.1 (CORE-A, internal!)",
                           "L3 OSPF LSA", True)
    if net.mode is FailureMode.STATIC_ROUTE_OSCILLATION:
        return DiagResult(3, "show ip ospf database",
                           "OSPF LSDB consistent; fault is in static routes, not OSPF",
                           "L3 OSPF OK", False)
    return DiagResult(3, "show ip ospf database",
                       "LSDB consistent; no suspicious LSAs",
                       "L3 OSPF OK", False)


def cmd_show_bgp(net: Network) -> DiagResult:
    if net.mode is FailureMode.MISCONFIGURED_AGGREGATE:
        return DiagResult(4, "show ip bgp 8.8.8.0/24",
                           "AS path 65002 65001 65001 (own AS in path - route reflection miss)",
                           "L3 BGP", True)
    if net.mode is FailureMode.IBGP_FULL_MESH_MISSING:
        return DiagResult(4, "show ip bgp 8.8.8.0/24",
                           "AS path 65002 65001 (received from ISP-2)",
                           "L3 BGP", True)
    if net.mode is FailureMode.STATIC_ROUTE_OSCILLATION:
        return DiagResult(4, "show ip bgp 8.8.8.0/24",
                           "BGP table clean; fault is in static routes",
                           "L3 BGP OK", False)
    return DiagResult(4, "show ip bgp 8.8.8.0/24",
                       "BGP table clean",
                       "L3 BGP OK", False)


def run_diag(net: Network) -> list[DiagResult]:
    return [cmd_traceroute(net), cmd_ip_route_get(net),
            cmd_show_ospf_db(net), cmd_show_bgp(net)]


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------
def render(mode: FailureMode, net: Network, results: list[DiagResult]) -> None:
    print("=" * 78)
    print(f"Routing Loop Diagnostic  [mode={mode.value}]")
    print("=" * 78)
    print("  topology: CORE-A <-> CORE-B <-> EDGE-1 <-> ISP-1/ISP-2")
    print("  destination: 8.8.8.0/24")
    print()
    print("  EDGE-1 static routes:")
    for r in ("CORE-A", "CORE-B", "EDGE-1"):
        for dst, nxt in net.routers[r].static_routes.items():
            print(f"    {r}: ip route {dst} -> {nxt}")
    if net.routers["EDGE-1"].received_bgp:
        print("  EDGE-1 received BGP:")
        for dst, (nxt, asp) in net.routers["EDGE-1"].received_bgp.items():
            print(f"    {dst} via {nxt} AS-path={asp}")
    print()
    print(f"{'#':<3}  {'finding':<60}  decisive?  layer")
    print("-" * 78)
    for r in results:
        first_line = r.finding[:58]
        marker = "YES" if r.decisive else "no"
        print(f"{r.step:<3}  {first_line:<60}  {marker:<9}  {r.layer}")
    print()
    decisive = next((r for r in results if r.decisive), None)
    if decisive:
        print(f"  First decisive evidence: step {decisive.step} ({decisive.name})")
        print(f"  Layer:                    {decisive.layer}")
        print(f"  Verdict:                  {decisive.finding}")
    else:
        print("  No decisive evidence in chain; deeper inspection needed.")


def main(argv: Iterable[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", default="all",
                    choices=[m.value for m in FailureMode] + ["all"])
    args = ap.parse_args(list(argv) if argv is not None else None)
    modes = (list(FailureMode) if args.mode == "all"
             else [FailureMode(args.mode)])
    for mode in modes:
        net = Network(mode)
        results = run_diag(net)
        render(mode, net, results)
        print()


if __name__ == "__main__":
    main()
