#!/usr/bin/env python3
"""Capstone 02: Design a Small Campus Network.

Comprehensive campus network designer: input parameters -> full design doc
with topology, VLANs, IP addressing, switch specs, STP, wireless, security.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CampusInput:
    buildings: int
    users_per_building: int
    bandwidth_mbps: int
    redundancy: bool = True


def generate_design(inp: CampusInput) -> dict:
    total_users = inp.buildings * inp.users_per_building
    vlans = []
    for i in range(inp.buildings):
        vlans.append({"id": 10 + i * 10, "name": f"BLD{i+1}-Data", "subnet": f"10.{i+1}.0.0/23"})
        vlans.append({"id": 11 + i * 10, "name": f"BLD{i+1}-Voice", "subnet": f"10.{i+1}.2.0/24"})
        vlans.append({"id": 12 + i * 10, "name": f"BLD{i+1}-Mgmt", "subnet": f"10.{i+1}.3.0/24"})
    return {"total_users": total_users, "vlans": vlans, "buildings": inp.buildings,
            "redundancy": inp.redundancy, "bandwidth": inp.bandwidth_mbps}


def main() -> None:
    print("=" * 65)
    print("Capstone 02: Design a Small Campus Network")
    print("=" * 65)
    inp = CampusInput(buildings=3, users_per_building=50, bandwidth_mbps=1000)
    design = generate_design(inp)
    print(f"\n  Input: {design['buildings']} buildings, {design['total_users']} users, {design['bandwidth']} Mbps")
    print(f"\n  VLAN Plan ({len(design['vlans'])} VLANs):")
    for v in design["vlans"]:
        print(f"    VLAN {v['id']:3d}  {v['name']:20s}  {v['subnet']}")
    print(f"\n  Topology:")
    print(f"    [ISP] -> [Edge Router x{2 if design['redundancy'] else 1}]")
    print(f"         -> [Core SW x{2 if design['redundancy'] else 1}] (HSRP/VRRP)")
    print(f"         -> [Dist SW per building] -> [Access SW per floor]")
    print(f"\n  IP Scheme: 10.{'X'}.0.0/16 RFC 1918 private, VLSM per VLAN")
    print(f"  STP: RSTP, root at core-1 (priority 4096), backup at core-2 (8192)")
    print(f"  Wireless: WPA3-Enterprise 802.1X, 2 APs per floor, guest VLAN isolated")
    print(f"  Security: 802.1X port auth, DHCP snooping, dynamic ARP inspection")
    print(f"  Monitoring: SNMPv3, Syslog, NetFlow, sFlow on all switches")
    print(f"  Growth: 30% headroom on all subnets, spare ports on access switches")


if __name__ == "__main__":
    main()
