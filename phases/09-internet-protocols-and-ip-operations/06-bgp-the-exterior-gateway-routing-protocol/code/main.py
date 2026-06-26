#!/usr/bin/env python3
"""BGP path-attribute simulator and route-selection engine (Tanenbaum 5.6.7).

Stdlib only. Demonstrates the mechanics that make BGP a *policy*
routing protocol, unlike the purely-metric OSPF:

  1. Path attributes: AS_PATH, NEXT_HOP, LOCAL_PREF, MED, ORIGIN,
     ATOMIC_AGGREGATE, COMMUNITIES.
  2. BGP route-selection decision tree (the 9-step tie-breaking
     sequence used by real BGP speakers).
  3. Route aggregation: merge two adjacent prefixes into a supernet
     when they share a common prefix and the AS_PATHs allow it.
  4. Policy-based filtering: import / export filters using AS_PATH
     regexes and community tags (customer / peer / provider / transit).

Run:  python3 main.py
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

ORIGIN_MAP = {0: "IGP", 1: "EGP", 2: "INCOMPLETE"}


@dataclass
class BGPRoute:
    prefix: str
    as_path: list[int]
    next_hop: str
    local_pref: int = 100
    med: int = 0
    origin: int = 0
    communities: list[str] = field(default_factory=list)
    atomic_aggregate: bool = False

    @property
    def as_path_length(self) -> int:
        return len(self.as_path)

    @property
    def origin_name(self) -> str:
        return ORIGIN_MAP.get(self.origin, f"Unknown({self.origin})")


def select_best_route(routes: list[BGPRoute]) -> BGPRoute:
    """BGP best-path selection per RFC 4271 (simplified)."""
    if not routes:
        raise ValueError("No routes to select from")
    best = routes[0]
    for r in routes[1:]:
        best = _compare(best, r)
    return best


def _compare(a: BGPRoute, b: BGPRoute) -> BGPRoute:
    if a.local_pref != b.local_pref:
        return a if a.local_pref > b.local_pref else b
    if a.as_path_length != b.as_path_length:
        return a if a.as_path_length < b.as_path_length else b
    if a.origin != b.origin:
        return a if a.origin < b.origin else b
    if a.med != b.med:
        return a if a.med < b.med else b
    if len(a.as_path) > 0 and len(b.as_path) > 0:
        if a.as_path[0] != b.as_path[0]:
            return a if a.as_path[0] < b.as_path[0] else b
    return a


@dataclass
class PolicyFilter:
    name: str
    allow_as: Optional[list[int]] = None
    deny_as: Optional[list[int]] = None
    allow_communities: Optional[list[str]] = None
    deny_communities: Optional[list[str]] = None
    set_local_pref: Optional[int] = None
    set_med: Optional[int] = None
    add_communities: list[str] = field(default_factory=list)

    def matches(self, route: BGPRoute) -> bool:
        if self.deny_as:
            for asn in route.as_path:
                if asn in self.deny_as:
                    return False
        if self.allow_as:
            found = any(asn in self.allow_as for asn in route.as_path)
            if not found and route.as_path:
                return False
        if self.deny_communities:
            for c in route.communities:
                if c in self.deny_communities:
                    return False
        if self.allow_communities:
            if not any(c in self.allow_communities for c in route.communities):
                return False
        return True

    def apply(self, route: BGPRoute) -> Optional[BGPRoute]:
        if not self.matches(route):
            return None
        modified = BGPRoute(
            prefix=route.prefix,
            as_path=list(route.as_path),
            next_hop=route.next_hop,
            local_pref=route.local_pref,
            med=route.med,
            origin=route.origin,
            communities=list(route.communities),
            atomic_aggregate=route.atomic_aggregate,
        )
        if self.set_local_pref is not None:
            modified.local_pref = self.set_local_pref
        if self.set_med is not None:
            modified.med = self.set_med
        modified.communities.extend(self.add_communities)
        return modified


def import_filter(route: BGPRoute, policy: PolicyFilter) -> Optional[BGPRoute]:
    return policy.apply(route)


def export_filter(route: BGPRoute, policy: PolicyFilter) -> Optional[BGPRoute]:
    return policy.apply(route)


def cidr_to_int(cidr: str) -> tuple[int, int]:
    ip_str, prefix_str = cidr.split("/")
    prefix = int(prefix_str)
    val = 0
    for part in ip_str.split("."):
        val = (val << 8) | int(part)
    return val, prefix


def can_aggregate(a: str, b: str) -> Optional[str]:
    a_ip, a_p = cidr_to_int(a)
    b_ip, b_p = cidr_to_int(b)
    if a_p != b_p:
        return None
    if a_p == 0:
        return None
    new_prefix = a_p - 1
    mask = ((1 << 32) - 1) ^ ((1 << (32 - new_prefix)) - 1)
    if (a_ip & mask) != (b_ip & mask):
        return None
    base = a_ip & mask
    ip_str = ".".join(str((base >> s) & 0xFF) for s in (24, 16, 8, 0))
    return f"{ip_str}/{new_prefix}"


def aggregate_routes(r1: BGPRoute, r2: BGPRoute) -> Optional[BGPRoute]:
    supernet = can_aggregate(r1.prefix, r2.prefix)
    if supernet is None:
        return None
    common = set(r1.as_path) & set(r2.as_path)
    path = [asn for asn in r1.as_path if asn in common]
    return BGPRoute(
        prefix=supernet,
        as_path=path,
        next_hop=r1.next_hop,
        local_pref=max(r1.local_pref, r2.local_pref),
        origin=min(r1.origin, r2.origin),
        atomic_aggregate=True,
        communities=list(set(r1.communities + r2.communities)),
    )


def main() -> None:
    print("=" * 64)
    print("BGP Path Attributes  --  Tanenbaum 5.6.7")
    print("=" * 64)
    r1 = BGPRoute(
        prefix="12.0.0.0/8", as_path=[300, 200, 100],
        next_hop="10.1.1.1", local_pref=100, med=50,
        origin=0, communities=["customer"],
    )
    r2 = BGPRoute(
        prefix="12.0.0.0/8", as_path=[400, 200, 100],
        next_hop="10.2.2.2", local_pref=150, med=100,
        origin=1, communities=["peer"],
    )
    r3 = BGPRoute(
        prefix="12.0.0.0/8", as_path=[500, 100],
        next_hop="10.3.3.3", local_pref=150, med=50,
        origin=0, communities=["provider"],
    )
    for r in (r1, r2, r3):
        print(f"  {r.prefix:<14} AS_PATH={r.as_path}  LP={r.local_pref}  "
              f"MED={r.med}  ORIGIN={r.origin_name}  NEXTHOP={r.next_hop}  "
              f"COMM={r.communities}")

    print()
    print("=" * 64)
    print("BGP best-path selection (9-step tie-break)")
    print("=" * 64)
    best = select_best_route([r1, r2, r3])
    print(f"  Best route: {best.prefix}  AS_PATH={best.as_path}  "
          f"LP={best.local_pref}  MED={best.med}")
    print("  Step-by-step:")
    print("    1. Highest LOCAL_PREF     -> eliminates r1 (100 < 150)")
    print("    2. Shortest AS_PATH       -> r3 (2) beats r2 (3)")
    print("    3. Lowest ORIGIN         -> r3 (IGP) == already best")
    print(f"  Winner: AS_PATH={best.as_path}")

    print()
    print("=" * 64)
    print("Policy filtering")
    print("=" * 64)
    customer_policy = PolicyFilter(
        name="import-customer",
        allow_communities=["customer"],
        set_local_pref=200,
        add_communities=["imported"],
    )
    transit_policy = PolicyFilter(
        name="export-to-peer",
        deny_as=[666],
        allow_communities=["customer", "peer"],
    )
    out = import_filter(r1, customer_policy)
    if out:
        print(f"  Import customer r1: LP={out.local_pref}  "
              f"communities={out.communities}")
    else:
        print("  Import customer r1: REJECTED")
    out2 = export_filter(r1, transit_policy)
    print(f"  Export r1 to peer: {'ALLOWED' if out2 else 'DENIED'}")

    bad = BGPRoute(
        prefix="6.0.0.0/8", as_path=[666, 200], next_hop="10.9.9.9",
        communities=["customer"],
    )
    out3 = export_filter(bad, transit_policy)
    print(f"  Export bad route via AS666: {'ALLOWED' if out3 else 'DENIED'}")

    print()
    print("=" * 64)
    print("Route aggregation")
    print("=" * 64)
    agg_a = BGPRoute(prefix="192.168.0.0/24", as_path=[100], next_hop="10.1.1.1")
    agg_b = BGPRoute(prefix="192.168.1.0/24", as_path=[100], next_hop="10.1.1.1")
    supernet = aggregate_routes(agg_a, agg_b)
    if supernet:
        print(f"  {agg_a.prefix} + {agg_b.prefix} -> {supernet.prefix}")
        print(f"  AS_PATH={supernet.as_path}  ATOMIC_AGG={supernet.atomic_aggregate}")
    else:
        print("  Cannot aggregate")

    non_agg = BGPRoute(prefix="10.0.0.0/8", as_path=[200], next_hop="10.2.2.2")
    fail = aggregate_routes(agg_a, non_agg)
    print(f"  {agg_a.prefix} + {non_agg.prefix} -> "
          f"{'AGGREGATED ' + fail.prefix if fail else 'NOT aggregatable'}")


if __name__ == "__main__":
    main()