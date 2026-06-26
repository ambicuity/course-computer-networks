#!/usr/bin/env python3
"""VLAN Trunk Mismatch and STP Root Bridge (Lab 12).

Two simulations:
  1. Trunk allowed-VLAN comparison between two switch ends.
  2. STP root-bridge election over a three-switch topology, with the
     classic failure of an access switch winning root over the core.

Run:  python3 code/main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field


def vlan_set(spec: str) -> set[int]:
    out: set[int] = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-")
            out.update(range(int(lo), int(hi) + 1))
        elif part:
            out.add(int(part))
    return out


@dataclass
class TrunkEnd:
    switch: str
    port: str
    allowed: str
    native: int


def check_trunk(a: TrunkEnd, b: TrunkEnd) -> None:
    print("=" * 64)
    print("802.1Q Trunk Mismatch Check")
    print("=" * 64)
    sa = vlan_set(a.allowed)
    sb = vlan_set(b.allowed)
    common = sa & sb
    only_a = sa - sb
    only_b = sb - sa
    print(f"  {a.switch} {a.port}: allowed '{a.allowed}' native={a.native}")
    print(f"  {b.switch} {b.port}: allowed '{b.allowed}' native={b.native}")
    print(f"  common VLANs      : {sorted(common)}")
    print(f"  only on {a.switch:8s}: {sorted(only_a)} -> dropped at {b.switch}")
    print(f"  only on {b.switch:8s}: {sorted(only_b)} -> dropped at {a.switch}")
    if a.native != b.native:
        print(f"  NATIVE VLAN MISMATCH: {a.native} vs {b.native} "
              f"(native-VLAN hopping risk)")
    if only_a or only_b:
        print("  DIAGNOSIS: TRUNK ALLOWED-VLAN MISMATCH")
        print("  Fix: set the same allowed list on both ends.")
    else:
        print("  DIAGNOSIS: trunk lists match.")
    print()


@dataclass
class Bridge:
    name: str
    priority: int
    mac: str
    ports: dict[str, tuple[str, int]] = field(default_factory=dict)

    @property
    def bridge_id(self) -> tuple[int, str]:
        return (self.priority, self.mac)


def elect_root(bridges: list[Bridge]) -> Bridge:
    return min(bridges, key=lambda b: b.bridge_id)


def stp_topology(bridges: list[Bridge], links: list[tuple[str, str, int]]) -> None:
    print("=" * 64)
    print("STP Root Bridge Election")
    print("=" * 64)
    for b in bridges:
        print(f"  {b.name:8s} priority={b.priority:5d} mac={b.mac}  "
              f"bridge_id=({b.priority},{b.mac})")
    root = elect_root(bridges)
    print(f"\n  ROOT BRIDGE: {root.name}  id={root.bridge_id}")
    if root.name.lower().startswith("access"):
        print("  WARNING: an ACCESS switch is root. Traffic detours through")
        print("  the access layer; core uplinks may block.")
    # Compute root ports on non-root bridges by shortest path cost.
    costs: dict[str, int] = {root.name: 0}
    neigh: dict[str, list[tuple[str, int]]] = {}
    for s, d, c in links:
        neigh.setdefault(s, []).append((d, c))
        neigh.setdefault(d, []).append((s, c))
    # Bellman-Ford over link costs
    changed = True
    while changed:
        changed = False
        for node in bridges:
            for nbr, cost in neigh.get(node.name, []):
                nd = costs.get(node.name, 10**9) + cost
                if nd < costs.get(nbr, 10**9):
                    costs[nbr] = nd
                    changed = True
    print("\n  Path cost to root:")
    for b in bridges:
        print(f"    {b.name:8s} cost={costs.get(b.name, 10**9)}")
    # Block the port on the bridge with the higher cost on each segment
    # that is not on the path to root.
    print("\n  Blocked ports (heuristic: higher-cost end of each link):")
    for s, d, c in links:
        if costs.get(s, 10**9) > costs.get(d, 10**9):
            blocked, kept = s, d
        elif costs.get(d, 10**9) > costs.get(s, 10**9):
            blocked, kept = d, s
        else:
            # tie: block the one with higher bridge id
            bs = next(b for b in bridges if b.name == s)
            bd = next(b for b in bridges if b.name == d)
            blocked, kept = (s, d) if bs.bridge_id > bd.bridge_id else (d, s)
        print(f"    {s}--{d} cost={c}: block on {blocked}, forward on {kept}")
    print()


def main() -> None:
    # Trunk mismatch scenario
    side_a = TrunkEnd("Core-A", "Gi1/0/1", "10-20", 999)
    side_b = TrunkEnd("Core-B", "Gi1/0/1", "10-15", 1)
    check_trunk(side_a, side_b)

    # Misconfigured STP: access switch wins root
    core = Bridge("Core", 32768, "00:11:11:11:11:11")
    dist1 = Bridge("Dist1", 32768, "00:22:22:22:22:22")
    dist2 = Bridge("Dist2", 32768, "00:33:33:33:33:33")
    access = Bridge("Access", 32768, "00:00:00:00:00:01")  # lowest MAC wins
    links = [
        ("Core", "Dist1", 4),
        ("Core", "Dist2", 4),
        ("Dist1", "Dist2", 19),
        ("Dist1", "Access", 19),
        ("Dist2", "Access", 19),
    ]
    stp_topology([core, dist1, dist2, access], links)

    # Fixed: Core is root primary
    print("=" * 64)
    print("After fix: Core priority = 4096")
    print("=" * 64)
    core_fixed = Bridge("Core", 4096, "00:11:11:11:11:11")
    stp_topology([core_fixed, dist1, dist2, access], links)
    print("  Fix: 'spanning-tree vlan 1-100 root primary' on Core.")
    print("  Also: enable BPDU Guard on access ports, Root Guard on uplinks.")


if __name__ == "__main__":
    main()
