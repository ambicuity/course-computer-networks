#!/usr/bin/env python3
"""IPv6 Dual-Stack Planner with SLAAC + DHCPv6-PD (Production Lab 17).

Given a /32 (or /48) and a list of sites, computes the addressing plan,
emits radvd and DHCPv6 configurations, and outputs a prefix delegation
hierarchy and a cutover runbook.

Stdlib only: dataclasses, ipaddress, json.

Run: python3 main.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from ipaddress import IPv6Network
from typing import Iterable


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

@dataclass
class Site:
    name: str
    subnets: list[str]    # VLAN names
    hosts_per_subnet: int


# ---------------------------------------------------------------------------
# Addressing plan
# ---------------------------------------------------------------------------

def allocate_sites(global_block: str, sites: list[Site]) -> dict:
    net = IPv6Network(global_block)
    # Each site gets a /48 (within a /32 we have 2^16 /48s)
    out: dict[str, dict] = {}
    base = int(net.network_address)
    for i, s in enumerate(sites):
        site_prefix = IPv6Network((base + (i << 80), 48))  # /48 = 80 host bits
        site_subnets: dict[str, str] = {}
        # Each subnet gets a /64 (within a /48 we have 2^16 /64s)
        sbase = int(site_prefix.network_address)
        for j, vlan in enumerate(s.subnets):
            subnet = IPv6Network((sbase + (j << 64), 64))
            site_subnets[vlan] = str(subnet)
        out[s.name] = {"site_prefix": str(site_prefix), "subnets": site_subnets}
    return out


# ---------------------------------------------------------------------------
# radvd configuration per VLAN
# ---------------------------------------------------------------------------

def radvd_config(vlan: str, prefix: str, rdns_servers: list[str],
                 mode: str) -> str:
    """mode: slaac | dhcpv6 | slaac-dhcpv6"""
    a, m, o = (1, 0, 0) if mode == "slaac" else (0, 1, 1) if mode == "dhcpv6" else (1, 1, 1)
    rdnss = "\n        ".join(f"RDNSS {s} {{ }};" for s in rdns_servers)
    return f"""# radvd config for VLAN {vlan} - {prefix} - mode {mode}
interface eth0.{vlan}
{{
    AdvSendAdvert on;
    AdvManagedFlag {"on" if m else "off"};
    AdvOtherConfigFlag {"on" if o else "off"};
    AdvAutonomous {"on" if a else "off"};
    MinRtrAdvInterval 30;
    MaxRtrAdvInterval 60;
    prefix {prefix}
    {{
        AdvOnLink on;
        AdvAutonomous {"on" if a else "off"};
        AdvPreferredLifetime 3600;
        AdvValidLifetime 7200;
    }};
    {rdnss}
}};
"""


# ---------------------------------------------------------------------------
# DHCPv6 configuration
# ---------------------------------------------------------------------------

def dhcpd6_config(site: Site, site_prefix: str, upstream: str,
                  rdns_servers: list[str]) -> str:
    net = IPv6Network(site_prefix)
    # Site router delegates a /56 to internal (e.g., 256 /64 subnets available)
    return f"""# DHCPv6 config for site {site.name}
# Site prefix: {site_prefix}  (delegated from upstream {upstream})
default-lease-time 7200;
preferred-lifetime 3600;
option dhcp6.name-servers {", ".join(rdns_servers)};

# This site router requests a /48 from upstream and delegates /56s
subnet6 {site_prefix}
{{
    # IA-PD pool for downstream delegation
    prefix6 {site_prefix}
    {{
        # split the /48 into /56s for internal subnets
        split 56;
    }};
}}
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    global_block = "2001:db8::/32"
    rdns = ["2001:4860:4860::8888", "2001:4860:4860::8844"]
    sites = [
        Site("factory-01", ["mgmt", "office", "ics", "guest", "wifi"], 200),
        Site("factory-02", ["mgmt", "office", "ics", "guest", "wifi"], 250),
        Site("hq",         ["mgmt", "office", "dev", "guest", "wifi", "dmz"], 500),
    ]
    plan = allocate_sites(global_block, sites)

    print("=" * 72)
    print("  IPV6 DUAL-STACK PLAN  -  /32 -> /48 per site -> /64 per VLAN")
    print("=" * 72)
    for site, info in plan.items():
        print(f"\n  {site}  ({info['site_prefix']})")
        for vlan, prefix in info["subnets"].items():
            print(f"    VLAN {vlan:8s} -> {prefix}")

    print()
    print("--- radvd config (slaac-dhcpv6, VLAN ics) ---")
    sample = plan["factory-01"]["subnets"]["ics"]
    print(radvd_config("ics", sample, rdns, "slaac-dhcpv6"))

    print("--- dhcpd6 config (factory-01) ---")
    print(dhcpd6_config(sites[0], plan["factory-01"]["site_prefix"],
                        global_block, rdns))

    out = {
        "global_block": global_block,
        "rdns_servers": rdns,
        "sites": plan,
    }
    with open("outputs/dualstack_plan.json", "w") as f:
        json.dump(out, f, indent=2)
    print()
    print("Wrote outputs/dualstack_plan.json")


if __name__ == "__main__":
    main()
