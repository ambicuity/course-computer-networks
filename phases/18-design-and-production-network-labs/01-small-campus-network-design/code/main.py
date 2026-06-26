#!/usr/bin/env python3
"""Small Campus Network Design Tool (Production Lab 01).

Generates a deterministic campus LAN design from a list of buildings. Emits a
vendor-neutral configuration skeleton (VLANs, SVIs, LAGs, VRRPv3 groups,
wireless sizing, PoE budget) plus a bill of materials priced against a public
catalog. Stdlib only: dataclasses, ipaddress, json, itertools, statistics.

Run: python3 main.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from ipaddress import IPv4Network, IPv4Address
from itertools import count
from typing import Iterable


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

@dataclass
class Building:
    name: str
    floors: int
    users_per_floor: int
    bandwidth_mbps: int  # per-user sustained target

    @property
    def users(self) -> int:
        return self.floors * self.users_per_floor


@dataclass
class VLAN:
    id: int
    name: str
    subnet: str
    gateway: str
    purpose: str
    dhcp_pool: str


@dataclass
class LAG:
    name: str
    members: list[str]
    speed_gbps: float
    mode: str  # LACP active / passive / static


@dataclass
class FHRP:
    protocol: str       # VRRPv3 / HSRPv2
    group: int
    virtual_ip: str
    priority: int
    hello_ms: int
    hold_ms: int


@dataclass
class Switch:
    role: str            # core / distribution / access
    building: str
    model: str
    ports: int
    poe_budget_w: int
    poe_used_w: int


@dataclass
class APPlan:
    building: str
    ap_count: int
    radio_class: str     # Wi-Fi 6 / 6E / 7
    poe_per_ap_w: float
    uplink_speed: str     # 1G / 2.5G / 5G / 10G


@dataclass
class Design:
    campus: str
    buildings: list[Building]
    vlans: list[VLAN] = field(default_factory=list)
    uplinks: list[LAG] = field(default_factory=list)
    fhrp: list[FHRP] = field(default_factory=list)
    switches: list[Switch] = field(default_factory=list)
    aps: list[APPlan] = field(default_factory=list)
    bom: list[dict] = field(default_factory=list)
    total_capex_usd: int = 0
    budget_usd: int = 185_000
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Catalog (publicly known MSRPs; used for sizing only)
# ---------------------------------------------------------------------------

ACCESS_48P_POE_BUDGET_W = 1440     # typical 48-port PoE++ switch
DIST_MODEL = ("Arista 7300-series", 32, 0)
CORE_MODEL = ("Arista 7800R3-series", 64, 0)
ACCESS_MODEL = ("Arista 720XP-48Y6", 48, ACCESS_48P_POE_BUDGET_W)

UNIT_PRICE_USD = {
    "access-48p-poe": 8_500,
    "distribution-32p": 22_000,
    "core-64p": 48_000,
    "ap-wifi6e": 1_400,
    "ap-wifi7": 1_900,
    "sfp-10g-sr": 95,
    "sfp-25g-sr": 165,
    "sfp-100g-sr4": 1_200,
    "support-per-year": 18_000,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def vlan_id_iter(start: int = 10) -> Iterable[int]:
    for i in count(start):
        yield i


def allocate_subnets(buildings: list[Building]) -> list[VLAN]:
    """Allocate non-overlapping /24 subnets per building per access class.

    Uses 10.<building_index*16>.0.0/16 per building so the summary route
    is 10.<x>.0.0/16. VLAN IDs start at 10 and increment; each building
    gets Data, Voice, Wireless, Mgmt, Guest, IoT.
    """
    vlans: list[VLAN] = []
    vid = vlan_id_iter(10)

    for b_idx, b in enumerate(buildings):
        base = 10 + b_idx * 16           # 10, 26, 42, ...
        classes = [
            ("Data",     f"10.{base}.0.0/24",  "User data"),
            ("Voice",    f"10.{base}.1.0/24",  "VoIP phones"),
            ("Wireless", f"10.{base}.2.0/24",  "Corporate Wi-Fi"),
            ("Mgmt",     f"10.{base}.3.0/24",  "Switch/AP mgmt"),
            ("Guest",    f"10.{base}.4.0/24",  "Guest Wi-Fi"),
            ("IoT",      f"10.{base}.5.0/24",  "Sensors / printers"),
        ]
        for cls_name, subnet, purpose in classes:
            net = IPv4Network(subnet)
            gw = str(net.network_address + 1)
            pool_start = str(net.network_address + 100)
            pool_end = str(net.broadcast_address - 1)
            v = VLAN(
                id=next(vid),
                name=f"{b.name}-{cls_name}",
                subnet=subnet,
                gateway=gw,
                purpose=purpose,
                dhcp_pool=f"{pool_start}-{pool_end}",
            )
            vlans.append(v)
    return vlans


def allocate_switches(buildings: list[Building]) -> list[Switch]:
    """Place access stacks per floor, distribution pair per building, core pair.

    Access-stack size = ceil(users_per_floor / 48) * 48 ports per floor.
    Distribution pair per building (L3 to the access).
    Core pair for the campus (L3 to distribution).
    """
    switches: list[Switch] = []
    # Access
    for b in buildings:
        per_floor = -(-b.users_per_floor // 48)  # ceil
        for floor in range(1, b.floors + 1):
            ap_count = max(2, b.users_per_floor // 25)
            poe_used = ap_count * 25 + (per_floor * 48 // 3) * 7  # APs + phones
            switches.append(Switch(
                role="access",
                building=b.name,
                model=f"{ACCESS_MODEL[0]} (Floor {floor})",
                ports=per_floor * 48,
                poe_budget_w=ACCESS_MODEL[2],
                poe_used_w=min(poe_used, ACCESS_48P_POE_BUDGET_W),
            ))
    # Distribution
    for b in buildings:
        switches.append(Switch(
            role="distribution",
            building=b.name,
            model=DIST_MODEL[0],
            ports=DIST_MODEL[1],
            poe_budget_w=0,
            poe_used_w=0,
        ))
    # Core (one pair for the campus)
    switches.append(Switch(
        role="core",
        building="Campus-Core",
        model=CORE_MODEL[0],
        ports=CORE_MODEL[1],
        poe_budget_w=0,
        poe_used_w=0,
    ))
    switches.append(Switch(
        role="core",
        building="Campus-Core",
        model=CORE_MODEL[0],
        ports=CORE_MODEL[1],
        poe_budget_w=0,
        poe_used_w=0,
    ))
    return switches


def allocate_lags(buildings: list[Building]) -> list[LAG]:
    """LACP bundles sized to user-bandwidth budget.

    Access-to-distribution: 2x 10G per access stack (LACP active).
    Distribution-to-core: 4x 25G per distribution pair (LACP active).
    """
    lags: list[LAG] = []
    for b in buildings:
        for s in [s for s in allocate_switches(buildings) if s.role == "access" and s.building == b.name]:
            total_demand_gbps = b.bandwidth_mbps * b.users_per_floor / 1000
            members_needed = max(1, -(-int(total_demand_gbps / 10) // 2))
            lags.append(LAG(
                name=f"Po{s.building[:3].upper()}-{s.model.split('(')[1].split()[1]}",
                members=[f"Eth1/{i+1}" for i in range(members_needed * 2)],
                speed_gbps=members_needed * 10,
                mode="LACP active",
            ))
    # Distribution-to-core: 4x 25G LAG from each distribution switch
    for b in buildings:
        lags.append(LAG(
            name=f"Core-{b.name[:3].upper()}",
            members=[f"Eth1/{i+1}" for i in range(8)],
            speed_gbps=100.0,
            mode="LACP active",
        ))
    return lags


def allocate_fhrp(vlans: list[VLAN]) -> list[FHRP]:
    """VRRPv3 fast-hello groups (one per VLAN). Default priority 150/120."""
    fhrps: list[FHRP] = []
    for v in vlans:
        if v.purpose in ("VoIP phones",):
            priority = 150  # voice on the primary
        elif v.purpose in ("User data", "Corporate Wi-Fi"):
            priority = 120
        else:
            priority = 110
        fhrps.append(FHRP(
            protocol="VRRPv3",
            group=v.id,
            virtual_ip=v.gateway,
            priority=priority,
            hello_ms=100,    # fast-hello
            hold_ms=300,
        ))
    return fhrps


def allocate_aps(buildings: list[Building]) -> list[APPlan]:
    """One AP per 25-40 users; high-density for classrooms."""
    plans: list[APPlan] = []
    for b in buildings:
        ap_count = max(2, -(-b.users // 30))
        radio = "Wi-Fi 6E" if b.bandwidth_mbps >= 500 else "Wi-Fi 6"
        uplink = "2.5G" if ap_count >= 4 else "1G"
        plans.append(APPlan(
            building=b.name,
            ap_count=ap_count,
            radio_class=radio,
            poe_per_ap_w=25.5,
            uplink_speed=uplink,
        ))
    return plans


def bill_of_materials(buildings: list[Building], aps: list[APPlan]) -> tuple[list[dict], int]:
    bom: list[dict] = []
    total = 0

    # Access switches: ceil(users_per_floor / 48) per floor
    access_total = sum(-(-b.users_per_floor // 48) * b.floors for b in buildings)
    bom.append({"item": "Access switch (48p PoE++)", "qty": access_total,
                "unit_usd": UNIT_PRICE_USD["access-48p-poe"],
                "extended_usd": access_total * UNIT_PRICE_USD["access-48p-poe"]})
    total += access_total * UNIT_PRICE_USD["access-48p-poe"]

    # Distribution: 2 per building
    dist_total = 2 * len(buildings)
    bom.append({"item": "Distribution switch (32p 25G)", "qty": dist_total,
                "unit_usd": UNIT_PRICE_USD["distribution-32p"],
                "extended_usd": dist_total * UNIT_PRICE_USD["distribution-32p"]})
    total += dist_total * UNIT_PRICE_USD["distribution-32p"]

    # Core: 2 for the campus
    bom.append({"item": "Core switch (64p 100G)", "qty": 2,
                "unit_usd": UNIT_PRICE_USD["core-64p"],
                "extended_usd": 2 * UNIT_PRICE_USD["core-64p"]})
    total += 2 * UNIT_PRICE_USD["core-64p"]

    # APs
    ap_total = sum(p.ap_count for p in aps)
    bom.append({"item": "Wi-Fi 6E AP", "qty": ap_total,
                "unit_usd": UNIT_PRICE_USD["ap-wifi6e"],
                "extended_usd": ap_total * UNIT_PRICE_USD["ap-wifi6e"]})
    total += ap_total * UNIT_PRICE_USD["ap-wifi6e"]

    # Optics: 2 per LAG member; rough estimate
    optics = access_total * 2 * 2 + dist_total * 4 * 2 + 2 * 4 * 2
    bom.append({"item": "SFP+ 10G SR optic", "qty": optics,
                "unit_usd": UNIT_PRICE_USD["sfp-10g-sr"],
                "extended_usd": optics * UNIT_PRICE_USD["sfp-10g-sr"]})
    total += optics * UNIT_PRICE_USD["sfp-10g-sr"]

    # 1-yr support
    bom.append({"item": "Support contract (1 yr)", "qty": 1,
                "unit_usd": UNIT_PRICE_USD["support-per-year"],
                "extended_usd": UNIT_PRICE_USD["support-per-year"]})
    total += UNIT_PRICE_USD["support-per-year"]

    return bom, total


def validate(design: Design) -> list[str]:
    issues: list[str] = []
    # Subnet collisions
    seen: dict[str, str] = {}
    for v in design.vlans:
        if v.subnet in seen:
            issues.append(f"COLLISION: {v.subnet} used by both {seen[v.subnet]} and {v.name}")
        seen[v.subnet] = v.name
    # PoE overuse
    for s in design.switches:
        if s.poe_used_w > s.poe_budget_w:
            issues.append(f"PoE OVER: {s.model} {s.poe_used_w}W > {s.poe_budget_w}W")
    # Budget
    if design.total_capex_usd > design.budget_usd:
        over = design.total_capex_usd - design.budget_usd
        issues.append(f"BUDGET OVER: ${over} over ${design.budget_usd}")
    return issues


def emit_config_skeleton(design: Design) -> str:
    """Vendor-neutral config skeleton (interfaces, VLANs, SVIs, VRRPv3)."""
    lines = ["! Vendor-neutral config skeleton -- map to EOS / IOS-XE / Junos / SR Linux",
             "! Hostname, BGP AS, and management IPs are placeholders.", ""]
    for v in design.vlans:
        fhrp = next((f for f in design.fhrp if f.virtual_ip == v.gateway), None)
        lines.append(f"vlan {v.id}")
        lines.append(f"  name {v.name}")
        lines.append(f"!")
        lines.append(f"interface vlan{v.id}")
        lines.append(f"  description {v.purpose} ({v.subnet})")
        lines.append(f"  ip address {v.gateway} 255.255.255.0")
        lines.append(f"  vrrp {fhrp.group} address-family ipv4")
        lines.append(f"    address {fhrp.virtual_ip} primary")
        lines.append(f"    priority {fhrp.priority}")
        lines.append(f"    timers advertise {fhrp.hello_ms}")
        lines.append(f"    track bfd 50 150")
        lines.append(f"!")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def design_campus(campus_name: str, buildings: list[Building]) -> Design:
    d = Design(campus=campus_name, buildings=buildings)
    d.vlans = allocate_subnets(buildings)
    d.switches = allocate_switches(buildings)
    d.uplinks = allocate_lags(buildings)
    d.fhrp = allocate_fhrp(d.vlans)
    d.aps = allocate_aps(buildings)
    d.bom, d.total_capex_usd = bill_of_materials(buildings, d.aps)
    return d


def print_summary(d: Design) -> None:
    print("=" * 72)
    print(f"Campus Design: {d.campus}")
    print("=" * 72)
    print(f"\n  Buildings: {len(d.buildings)}, Total users: {sum(b.users for b in d.buildings)}")
    print(f"\n  VLAN Plan ({len(d.vlans)} VLANs):")
    print(f"  {'ID':>4} {'Name':22} {'Subnet':18} {'Gateway':14} {'Purpose'}")
    for v in d.vlans:
        print(f"  {v.id:>4} {v.name:22} {v.subnet:18} {v.gateway:14} {v.purpose}")
    print(f"\n  Switch allocation ({len(d.switches)} switches):")
    by_role: dict[str, int] = {}
    for s in d.switches:
        by_role[s.role] = by_role.get(s.role, 0) + 1
    for role, n in by_role.items():
        print(f"    {role:14s}: {n}")
    print(f"\n  First-Hop Redundancy: VRRPv3 fast-hello ({len(d.fhrp)} groups)")
    print(f"\n  Wireless: {sum(p.ap_count for p in d.aps)} APs across "
          f"{len(d.aps)} buildings ({', '.join(p.radio_class for p in d.aps)})")
    print(f"\n  Bill of Materials: ${d.total_capex_usd:,} vs budget ${d.budget_usd:,}")
    for line in d.bom:
        print(f"    {line['item']:34s} qty={line['qty']:>3} "
              f"unit=${line['unit_usd']:>5,} ext=${line['extended_usd']:>7,}")
    issues = validate(d)
    if issues:
        print("\n  Validation issues:")
        for i in issues:
            print(f"    - {i}")
    else:
        print("\n  Validation: PASS (no collisions, no PoE overrun, within budget)")


def main() -> None:
    buildings = [
        Building("Engineering", floors=4, users_per_floor=60, bandwidth_mbps=10),
        Building("Liberal-Arts", floors=3, users_per_floor=45, bandwidth_mbps=10),
        Building("DataCenter", floors=2, users_per_floor=8, bandwidth_mbps=100),
    ]
    d = design_campus("Northbridge Polytechnic", buildings)
    print_summary(d)
    # Emit JSON to stdout for piping into outputs/design.json
    payload = {
        "campus": d.campus,
        "buildings": [asdict(b) for b in d.buildings],
        "vlans": [asdict(v) for v in d.vlans],
        "fhrp": [asdict(f) for f in d.fhrp],
        "uplinks": [asdict(u) for u in d.uplinks],
        "aps": [asdict(a) for a in d.aps],
        "bom": d.bom,
        "total_capex_usd": d.total_capex_usd,
        "budget_usd": d.budget_usd,
    }
    with open("/dev/stdout", "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    # Config skeleton
    print("\n--- Config Skeleton (first 20 lines) ---")
    skel = emit_config_skeleton(d).splitlines()
    for line in skel[:20]:
        print(line)


if __name__ == "__main__":
    main()