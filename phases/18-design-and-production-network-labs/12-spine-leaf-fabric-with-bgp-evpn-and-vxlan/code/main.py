#!/usr/bin/env python3
"""Spine-Leaf Fabric Planner with BGP EVPN and VXLAN (Production Lab 12).

Given a leaf count, a server count, a port density, and an oversubscription
target, this script computes the spine count, the fabric capacity, the
bisectional bandwidth, and emits a VTEP/loopback/anycast gateway plan, a
BGP EVPN NLRI sample, a VXLAN bridge-domain table, and a cutover runbook.

Stdlib only: dataclasses, ipaddress, json.

Run: python3 main.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from ipaddress import IPv4Network, IPv4Address
from typing import Iterable


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

@dataclass
class FabricInputs:
    leaves: int
    servers_per_leaf: int
    server_link_gbps: int
    leaf_spine_link_gbps: int
    target_oversubscription: float  # e.g. 4.0
    n_rr: int                       # number of route-reflectors (1 or 2)
    vtep_subnet: str                # e.g. 10.255.0.0/24
    loopback_subnet: str            # e.g. 10.254.0.0/24
    tenants: list[tuple[int, str]]  # (VNI, tenant name)


# ---------------------------------------------------------------------------
# Fabric sizing
# ---------------------------------------------------------------------------

def spine_count(fi: FabricInputs) -> int:
    """Compute minimum spine count for the target oversubscription."""
    server_bw = fi.leaves * fi.servers_per_leaf * fi.server_link_gbps
    # 1 spine = fi.leaves leaf-facing links of leaf_spine_link_gbps
    # We want: server_bw / (n_spines * leaves * leaf_spine_link) <= target
    import math
    n = math.ceil(server_bw / (fi.target_oversubscription * fi.leaves * fi.leaf_spine_link_gbps))
    return n


def fabric_summary(fi: FabricInputs) -> dict:
    n_spines = spine_count(fi)
    server_bw = fi.leaves * fi.servers_per_leaf * fi.server_link_gbps
    fabric_bw = n_spines * fi.leaves * fi.leaf_spine_link_gbps
    over = server_bw / fabric_bw
    bisection = (n_spines * fi.leaves * fi.leaf_spine_link_gbps) // 2
    return {
        "n_leaves": fi.leaves,
        "n_spines": n_spines,
        "server_facing_bw_tbps": server_bw / 1000.0,
        "fabric_bw_tbps": fabric_bw / 1000.0,
        "oversubscription": round(over, 2),
        "bisectional_bw_tbps": bisection / 1000.0,
    }


# ---------------------------------------------------------------------------
# VTEP / loopback / anycast gateway plan
# ---------------------------------------------------------------------------

def vtep_plan(fi: FabricInputs) -> list[dict]:
    net = IPv4Network(fi.vtep_subnet)
    out = []
    for i in range(fi.leaves):
        ip = IPv4Address(int(net.network_address) + 1 + i)
        out.append({"leaf": f"leaf-{i+1:02d}", "vtep_ip": str(ip)})
    return out


def loopback_plan(fi: FabricInputs) -> list[dict]:
    net = IPv4Network(fi.loopback_subnet)
    out = []
    for i in range(fi.leaves):
        ip = IPv4Address(int(net.network_address) + 1 + i)
        out.append({"leaf": f"leaf-{i+1:02d}", "loopback_ip": str(ip)})
    return out


def anycast_gateways(fi: FabricInputs) -> list[dict]:
    out = []
    for vni, tenant in fi.tenants:
        # derived from VNI: 172.{vni>>8}.{vni&0xFF}.1
        b1 = 172
        b2 = min(31, (vni >> 8) & 0xFF)
        b3 = vni & 0xFF
        gw = f"{b1}.{b2}.{b3}.1"
        rd = f"10.254.0.254:{vni}"
        rt_import = f"route-target:{vni}:100"
        rt_export = f"route-target:{vni}:100"
        out.append({
            "vni": vni,
            "tenant": tenant,
            "anycast_gw": gw,
            "rd": rd,
            "rt_import": rt_import,
            "rt_export": rt_export,
        })
    return out


# ---------------------------------------------------------------------------
# BGP EVPN NLRI sample (Type 2)
# ---------------------------------------------------------------------------

def bgp_evpn_type2_sample(mac: str, ip: str, vni: int, vtep: str) -> dict:
    return {
        "afi": "l2vpn evpn",
        "nlri_type": 2,
        "rd": f"10.254.0.254:{vni}",
        "esi": "00:00:00:00:00:00:00:00:00:00",
        "eth_tag_id": 0,
        "mac_length": 48,
        "mac": mac,
        "ip_length": 32,
        "ip": ip,
        "vni": vni,
        "next_hop": vtep,
    }


# ---------------------------------------------------------------------------
# Route-reflector session count
# ---------------------------------------------------------------------------

def rr_sessions(fi: FabricInputs) -> dict:
    full_mesh = fi.leaves * (fi.leaves - 1) // 2
    with_rr = fi.leaves * fi.n_rr
    return {
        "full_mesh_sessions": full_mesh,
        "with_rr_sessions": with_rr,
        "reduction_pct": round(100 * (1 - with_rr / full_mesh), 1),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    fi = FabricInputs(
        leaves=32,
        servers_per_leaf=80,         # 32 * 80 = 2560 server-facing ports
        server_link_gbps=25,
        leaf_spine_link_gbps=100,
        target_oversubscription=4.0,
        n_rr=2,
        vtep_subnet="10.255.0.0/24",
        loopback_subnet="10.254.0.0/24",
        tenants=[(10001, "tenant-a"), (10002, "tenant-b"),
                 (10003, "tenant-c"), (10100, "tenant-d")],
    )

    summary = fabric_summary(fi)
    vteps = vtep_plan(fi)
    loops = loopback_plan(fi)
    gws = anycast_gateways(fi)
    nlri = bgp_evpn_type2_sample(
        mac="00:1A:2B:3C:4D:5E",
        ip="172.16.1.42",
        vni=10001,
        vtep=vteps[4]["vtep_ip"],
    )
    rr = rr_sessions(fi)

    print("=" * 72)
    print(f"  SPINE-LEAF FABRIC PLAN")
    print("=" * 72)
    print(f"  Leaves              : {summary['n_leaves']}")
    print(f"  Spines (computed)   : {summary['n_spines']}")
    print(f"  Server-facing BW    : {summary['server_facing_bw_tbps']} Tbps")
    print(f"  Fabric BW           : {summary['fabric_bw_tbps']} Tbps")
    print(f"  Oversubscription    : {summary['oversubscription']}")
    print(f"  Bisectional BW      : {summary['bisectional_bw_tbps']} Tbps")
    print()
    print("--- VTEP plan (first 5 leaves) ---")
    for v in vteps[:5]:
        print(f"  {v['leaf']:10s} vtep={v['vtep_ip']}")
    print("  ...")
    print()
    print("--- Loopback plan (first 5 leaves) ---")
    for v in loops[:5]:
        print(f"  {v['leaf']:10s} lo={v['loopback_ip']}")
    print("  ...")
    print()
    print("--- Anycast gateways ---")
    for g in gws:
        print(f"  VNI {g['vni']:5d} ({g['tenant']:8s}) gw={g['anycast_gw']:15s} RD={g['rd']}  RT={g['rt_import']}")
    print()
    print("--- BGP EVPN Type 2 NLRI sample ---")
    for k, v in nlri.items():
        print(f"  {k:14s}: {v}")
    print()
    print("--- Route-reflector session count ---")
    print(f"  Full mesh : {rr['full_mesh_sessions']} sessions")
    print(f"  With {fi.n_rr} RRs  : {rr['with_rr_sessions']} sessions")
    print(f"  Reduction : {rr['reduction_pct']}%")

    out = {
        "summary": summary,
        "vtep_plan": vteps,
        "loopback_plan": loops,
        "anycast_gateways": gws,
        "nlri_sample": nlri,
        "rr_sessions": rr,
    }
    with open("outputs/fabric_plan.json", "w") as f:
        json.dump(out, f, indent=2)
    print()
    print("Wrote outputs/fabric_plan.json")


if __name__ == "__main__":
    main()
