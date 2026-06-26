"""IP Multicast and IGMP for Live Media.

A stdlib-only model of a multicast router's IGMP state table. Simulates
host joins, general queries with timeouts, group-specific queries,
IGMPv2/v3 leaves, IGMP snooping on a switch, the 32-to-1 IP-to-MAC
ambiguity, and a bandwidth comparison of unicast vs broadcast vs
multicast delivery.

Run:  python3 main.py
Exit: 0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

# Multicast MAC prefix: low 23 bits of the IP group map into the MAC
MULTICAST_MAC_PREFIX = "01:00:5e"


def ip_to_multicast_mac(group_ip: str) -> str:
    """Map an IPv4 class D address to its Ethernet multicast MAC.

    Only the low 23 bits of the IP group are used, so 32 IP groups share
    one MAC. This produces the documented ambiguity.
    """
    octets = [int(o) for o in group_ip.split(".")]
    if len(octets) != 4 or not (224 <= octets[0] <= 239):
        raise ValueError(f"not a class D address: {group_ip}")
    # Low 23 bits = low 7 bits of octet[1] + octet[2] + octet[3]
    low23 = ((octets[1] & 0x7F) << 16) | (octets[2] << 8) | octets[3]
    mac_third = (low23 >> 16) & 0xFF
    mac_fourth = (low23 >> 8) & 0xFF
    mac_fifth = low23 & 0xFF
    return f"{MULTICAST_MAC_PREFIX}:{mac_third:02x}:{mac_fourth:02x}:{mac_fifth:02x}"


@dataclass
class GroupState:
    """IGMP state for one group on one router interface."""

    group: str
    interface: str
    last_report_ms: float
    sources: Set[str] = field(default_factory=set)  # IGMPv3 SSM
    version: int = 2

    def is_expired(self, now_ms: float, timeout_ms: float) -> bool:
        return (now_ms - self.last_report_ms) > timeout_ms


class MulticastRouter:
    """A first-hop multicast router maintaining IGMP group state."""

    def __init__(self, query_interval_ms: float = 125_000.0,
                 group_timeout_ms: float = 260_000.0) -> None:
        self.query_interval_ms = query_interval_ms
        self.group_timeout_ms = group_timeout_ms
        # state[group][interface] = GroupState
        self.state: Dict[str, Dict[str, GroupState]] = {}
        self.now_ms: float = 0.0

    def tick(self, delta_ms: float) -> None:
        self.now_ms += delta_ms

    def join(self, interface: str, group: str, source: Optional[str] = None,
             version: int = 2) -> None:
        """Host sends a Membership Report."""
        groups = self.state.setdefault(group, {})
        if interface in groups:
            groups[interface].last_report_ms = self.now_ms
            if source:
                groups[interface].sources.add(source)
        else:
            groups[interface] = GroupState(
                group=group, interface=interface,
                last_report_ms=self.now_ms, version=version,
                sources={source} if source else set(),
            )

    def leave(self, interface: str, group: str) -> bool:
        """Host sends a Leave Group (IGMPv2/v3)."""
        groups = self.state.get(group)
        if groups and interface in groups:
            del groups[interface]
            if not groups:
                del self.state[group]
            return True
        return False

    def general_query(self) -> List[Tuple[str, str]]:
        """Router sends a General Query. Return list of (group, iface)
        that timed out and were pruned."""
        pruned: List[Tuple[str, str]] = []
        for group, ifaces in list(self.state.items()):
            for iface, gs in list(ifaces.items()):
                if gs.is_expired(self.now_ms, self.group_timeout_ms):
                    del ifaces[iface]
                    pruned.append((group, iface))
            if not ifaces:
                del self.state[group]
        return pruned

    def group_specific_query(self, group: str) -> bool:
        """Router sends a Group-Specific Query after a leave."""
        return bool(self.state.get(group))

    def forwarding_interfaces(self, group: str) -> List[str]:
        return list(self.state.get(group, {}).keys())

    def group_table(self) -> List[Tuple[str, str, float, int]]:
        rows: List[Tuple[str, str, float, int]] = []
        for group, ifaces in sorted(self.state.items()):
            for iface, gs in sorted(ifaces.items()):
                age = self.now_ms - gs.last_report_ms
                rows.append((group, iface, age, len(gs.sources)))
        return rows


class IGMPSnoopingSwitch:
    """A layer-2 switch that snoops IGMP to map groups to ports."""

    def __init__(self) -> None:
        # group -> set of ports
        self.port_map: Dict[str, Set[str]] = {}

    def observe_join(self, port: str, group: str) -> None:
        self.port_map.setdefault(group, set()).add(port)

    def observe_leave(self, port: str, group: str) -> None:
        ports = self.port_map.get(group)
        if ports:
            ports.discard(port)
            if not ports:
                del self.port_map[group]

    def ports_for(self, group: str) -> Set[str]:
        return self.port_map.get(group, set())


def bandwidth_comparison(viewers: int, stream_mbps: float) -> Dict[str, float]:
    """Compute source egress for unicast, broadcast, and multicast."""
    unicast_egress = viewers * stream_mbps
    broadcast_egress = stream_mbps
    multicast_egress = stream_mbps
    return {
        "viewers": float(viewers),
        "stream_mbps": stream_mbps,
        "unicast_source_gbps": unicast_egress / 1000,
        "broadcast_source_gbps": broadcast_egress / 1000,
        "multicast_source_gbps": multicast_egress / 1000,
    }


def main() -> None:
    print("IP Multicast and IGMP for Live Media\n")
    print("Multicast delivers one copy to a group address; the network")
    print("replicates only where receivers have joined via IGMP.\n")

    # === Part 1: IP-to-MAC mapping and the 32-to-1 ambiguity ===
    print("=== Part 1: Multicast MAC Mapping ===\n")
    test_groups = [
        ("224.1.2.3", "239.1.2.3"),  # share the same low 23 bits
        ("224.0.0.1", "224.128.0.1"),
    ]
    for a, b in test_groups:
        mac_a = ip_to_multicast_mac(a)
        mac_b = ip_to_multicast_mac(b)
        same = mac_a == mac_b
        print(f"  {a:<15} -> {mac_a}")
        print(f"  {b:<15} -> {mac_b}")
        print(f"  Same MAC: {same}  (32 IP groups share one MAC; IP stack filters)\n")
    print("  Only the low 23 bits of the IP group map into the MAC, so bit 24")
    print("  of the third octet is ignored. 32 groups map to each MAC.\n")

    # === Part 2: Router IGMP state simulation ===
    print("=== Part 2: Router IGMP State Simulation ===\n")
    router = MulticastRouter(query_interval_ms=125_000, group_timeout_ms=260_000)
    print("  Host joins:")
    router.tick(0)
    router.join("eth0", "224.1.1.1")
    router.join("eth1", "224.1.1.1")
    router.join("eth0", "224.2.2.2")
    print("    eth0 joined 224.1.1.1")
    print("    eth1 joined 224.1.1.1")
    print("    eth0 joined 224.2.2.2")
    print()
    print(f"  {'group':<15}  {'iface':<6}  {'age_ms':>8}  {'sources':>7}")
    print("  " + "-" * 42)
    for group, iface, age, nsources in router.group_table():
        print(f"  {group:<15}  {iface:<6}  {age:8.0f}  {nsources:7d}")
    print(f"  Forwarding 224.1.1.1 on: {router.forwarding_interfaces('224.1.1.1')}")
    print()

    # Leave on eth0
    print("  Host on eth0 leaves 224.1.1.1 (IGMPv2 Leave Group):")
    router.leave("eth0", "224.1.1.1")
    still = router.group_specific_query("224.1.1.1")
    print(f"    Pruned eth0; group still active (eth1 remains): {still}")
    print(f"    Forwarding 224.1.1.1 on: {router.forwarding_interfaces('224.1.1.1')}")
    print()

    # === Part 3: Query cycle with timeout ===
    print("=== Part 3: General Query and Timeout ===\n")
    router2 = MulticastRouter(group_timeout_ms=260_000)
    router2.join("eth0", "224.5.5.5")
    print("  eth0 joined 224.5.5.5 at t=0")
    router2.tick(300_000)  # 300 seconds, past 260 s timeout
    pruned = router2.general_query()
    print(f"  At t=300 s, General Query pruned: {pruned}")
    print(f"  State empty: {not router2.state}")
    print()

    # Now with a refresh before timeout
    router3 = MulticastRouter(group_timeout_ms=260_000)
    router3.join("eth0", "224.6.6.6")
    print("  eth0 joined 224.6.6.6 at t=0")
    router3.tick(120_000)
    router3.join("eth0", "224.6.6.6")  # refresh at t=120 s
    print("  eth0 refreshed 224.6.6.6 at t=120 s (Membership Report)")
    router3.tick(120_000)  # now t=240 s, still within 260 s of last report
    pruned2 = router3.general_query()
    print(f"  At t=240 s, General Query pruned: {pruned2}")
    print(f"  Group still active: {bool(router3.state)}")
    print()

    # === Part 4: IGMP snooping ===
    print("=== Part 4: IGMP Snooping on a Switch ===\n")
    switch = IGMPSnoopingSwitch()
    ports = ["p1", "p2", "p3", "p4", "p5"]
    print(f"  Ports: {ports}")
    switch.observe_join("p1", "224.10.10.10")
    switch.observe_join("p2", "224.10.10.10")
    switch.observe_join("p3", "224.20.20.20")
    print("  p1 joined 224.10.10.10")
    print("  p2 joined 224.10.10.10")
    print("  p3 joined 224.20.20.20")
    print(f"  Switch forwards 224.10.10.10 to: {sorted(switch.ports_for('224.10.10.10'))}")
    print(f"  Switch forwards 224.20.20.20 to: {sorted(switch.ports_for('224.20.20.20'))}")
    print(f"  Switch forwards 224.30.30.30 to: {sorted(switch.ports_for('224.30.30.30'))}  (none -> flood)")
    switch.observe_leave("p1", "224.10.10.10")
    print("  p1 left 224.10.10.10")
    print(f"  Switch now forwards 224.10.10.10 to: {sorted(switch.ports_for('224.10.10.10'))}")
    print()

    # === Part 5: Bandwidth comparison ===
    print("=== Part 5: Unicast vs Broadcast vs Multicast Bandwidth ===\n")
    stream = 2.0  # Mbps
    print(f"  Stream bitrate: {stream} Mbps\n")
    print(f"  {'viewers':>8}  {'unicast_gbps':>13}  {'broadcast_gbps':>15}  {'multicast_gbps':>14}")
    print("  " + "-" * 58)
    for viewers in [100, 1_000, 10_000, 100_000, 1_000_000]:
        r = bandwidth_comparison(viewers, stream)
        print(f"  {int(r['viewers']):8d}  {r['unicast_source_gbps']:13.1f}  "
              f"{r['broadcast_source_gbps']:15.1f}  {r['multicast_source_gbps']:14.1f}")
    print()
    print("  Observations:")
    print("    - Unicast source egress scales linearly with viewers (200 Gbps at 100k)")
    print("    - Broadcast and multicast source egress stay at one copy regardless of viewers")
    print("    - Multicast wins over broadcast because the network only forwards to joined branches")
    print("    - The savings appear at the network interior, not just the source")
    print()

    print("Key observations:")
    print("  - IGMP joins add an interface to a group's forwarding set; leaves prune it")
    print("  - Without a refresh before the group timeout, the router drops the group")
    print("  - IGMP snooping lets a switch forward multicast only to ports that joined")
    print("  - 32 IP multicast addresses map to each Ethernet MAC; the IP stack disambiguates")
    print("  - Multicast keeps source egress constant as viewership grows, unlike unicast")
    print()
    print("Done.")


if __name__ == "__main__":
    main()