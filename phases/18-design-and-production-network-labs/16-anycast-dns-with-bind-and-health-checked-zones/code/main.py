#!/usr/bin/env python3
"""Anycast DNS Planner (Production Lab 16).

Given a list of PoPs, a list of zones, and a user-population distribution,
this script computes the PoP selection, the latency distribution, and emits
a BIND9 configuration, a BGP configuration, a health-check script, and a
cutover runbook.

Stdlib only: dataclasses, ipaddress, json.

Run: python3 main.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from ipaddress import IPv4Network
from typing import Iterable


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

@dataclass
class PoP:
    name: str
    region: str
    ipv4: str                  # the PoP's anycast IPv4
    ipv6: str                  # the PoP's anycast IPv6
    transit_asns: list[int]    # one or more transit ASNs
    median_rtt_ms: int         # typical RTT from a regional user


@dataclass
class Zone:
    name: str
    soa: str
    ns: list[str]
    tsig_key: str


# ---------------------------------------------------------------------------
# Latency distribution
# ---------------------------------------------------------------------------

POP_DIST = {
    "europe":       0.30,
    "north-america": 0.25,
    "asia":         0.25,
    "south-america": 0.10,
    "oceania":      0.05,
    "south-asia":   0.05,
}


def latency_distribution(pops: list[PoP]) -> dict:
    by_region: dict[str, list[PoP]] = {}
    for p in pops:
        by_region.setdefault(p.region, []).append(p)
    out: dict[str, dict] = {}
    for region, fraction in POP_DIST.items():
        ps = by_region.get(region, [])
        if not ps:
            out[region] = {"coverage": 0.0, "median_rtt_ms": None}
            continue
        # Best PoP for the region is the one with the lowest median_rtt_ms
        best = min(ps, key=lambda p: p.median_rtt_ms)
        out[region] = {
            "fraction_of_users": fraction,
            "pop": best.name,
            "median_rtt_ms": best.median_rtt_ms,
        }
    return out


# ---------------------------------------------------------------------------
# BIND9 configuration
# ---------------------------------------------------------------------------

def bind_config(pop: PoP, hidden_primary: str, zones: list[Zone], tsig: str) -> str:
    zone_stanzas = "\n".join(
        f'zone "{z.name}" {{\n'
        f'    type slave;\n'
        f'    masters {{ {hidden_primary}; }};\n'
        f'    allow-transfer {{ none; }};\n'
        f'    file "/var/cache/bind/{z.name}.zone";\n'
        f'    notify no;\n'
        f'}};'
        for z in zones
    )
    return f"""// BIND9 config for {pop.name} ({pop.ipv4})
options {{
    listen-on {{ {pop.ipv4}; }};
    listen-on-v6 {{ {pop.ipv6}; }};
    allow-query {{ any; }};
    allow-transfer {{ key "anycast-tsig"; }};
    recursion no;
    minimal-responses yes;
    edns-udp-size 1232;
    version "none";
}};
key "anycast-tsig" {{
    algorithm hmac-sha256;
    secret "{tsig}";
}};
{zone_stanzas}
"""


# ---------------------------------------------------------------------------
# BGP configuration
# ---------------------------------------------------------------------------

def bgp_config(pop: PoP, anycast_prefix: str, asn: int,
               transit_asns: list[int]) -> str:
    peers = "\n".join(
        f"  neighbor {n}.{n}.{n}.{n} remote-as {t};"
        for n, t in zip(range(1, len(transit_asns) + 1), transit_asns)
    )
    return f"""! BGP config for {pop.name} (anycast {anycast_prefix})
router bgp {asn}
  address-family ipv4 unicast
    network {anycast_prefix}
    neighbor <peer-ip> remote-as <transit-asn>
    neighbor <peer-ip> route-map ANYCAST-OUT out
{peers}
  exit-address-family
route-map ANYCAST-OUT permit 10
  set community {asn}:53
  set metric 50
"""


# ---------------------------------------------------------------------------
# Health-check script
# ---------------------------------------------------------------------------

HEALTH_CHECK = """#!/bin/sh
# Anycast health check - withdraw BGP route if BIND9 fails
# Polls version.bind every 5s; if 3 consecutive failures, withdraws route
set -e
ANYCAST_IP=192.0.2.53
PROBE="dig +short +tries=1 +time=2 @$ANYCAST_IP version.bind TXT CH"
WITHDRAW_CMD="vtysh -c 'configure terminal' -c 'router bgp 64500' -c 'address-family ipv4' -c 'no network 192.0.2.0/24'"
RESTORE_CMD="vtysh -c 'configure terminal' -c 'router bgp 64500' -c 'address-family ipv4' -c 'network 192.0.2.0/24'"
fail_streak=0
threshold=3
while true; do
    if $PROBE > /dev/null 2>&1; then
        if [ $fail_streak -ge $threshold ]; then
            echo "$(date) BIND recovered, restoring route"
            eval $RESTORE_CMD
            fail_streak=0
        fi
    else
        fail_streak=$((fail_streak + 1))
        if [ $fail_streak -eq $threshold ]; then
            echo "$(date) BIND down, withdrawing route"
            eval $WITHDRAW_CMD
        fi
    fi
    sleep 5
done
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    pops = [
        PoP("fra", "europe", "192.0.2.1", "2001:db8::1", [64500, 64600], 12),
        PoP("lon", "europe", "192.0.2.2", "2001:db8::2", [64500, 64600], 14),
        PoP("ams", "europe", "192.0.2.3", "2001:db8::3", [64600, 64700], 11),
        PoP("par", "europe", "192.0.2.4", "2001:db8::4", [64600, 64700], 13),
        PoP("nyc", "north-america", "192.0.2.5", "2001:db8::5", [64500, 64800], 18),
        PoP("lax", "north-america", "192.0.2.6", "2001:db8::6", [64500, 64800], 22),
        PoP("tor", "north-america", "192.0.2.7", "2001:db8::7", [64800, 64900], 20),
        PoP("gru", "south-america", "192.0.2.8", "2001:db8::8", [64900, 65000], 35),
        PoP("sin", "asia", "192.0.2.9", "2001:db8::9", [65000, 65100], 28),
        PoP("hkg", "asia", "192.0.2.10", "2001:db8::10", [65000, 65100], 30),
        PoP("tyo", "asia", "192.0.2.11", "2001:db8::11", [65100, 65200], 25),
        PoP("syd", "oceania", "192.0.2.12", "2001:db8::12", [65100, 65200], 32),
    ]
    zones = [
        Zone("example.com", "ns1.example.com.", ["ns1.example.com"], "base64=="),
        Zone("customer-a.com", "ns1.example.com.", ["ns1.example.com"], "base64=="),
    ]
    lat = latency_distribution(pops)

    print("=" * 72)
    print("  ANYCAST DNS DEPLOYMENT PLAN")
    print("=" * 72)
    print(f"  PoPs: {len(pops)}")
    for p in pops:
        print(f"    {p.name:5s} {p.region:15s} IPv4 {p.ipv4:14s} RTT {p.median_rtt_ms:3d}ms")
    print()
    print("--- Latency distribution ---")
    for region, info in lat.items():
        print(f"  {region:15s} users={info['fraction_of_users']*100:4.0f}%  pop={info.get('pop','-'):5s}  RTT={info.get('median_rtt_ms','-')}")
    print()
    print("--- Sample BIND9 config (PoP fra) ---")
    print(bind_config(pops[0], "10.0.0.53", zones, "c2VjcmV0")[:500] + "\n  ...")
    print()
    print("--- Sample BGP config (PoP fra) ---")
    print(bgp_config(pops[0], "192.0.2.0/24", 64500, pops[0].transit_asns))

    out = {
        "n_pops": len(pops),
        "latency": lat,
        "anycast_prefix": "192.0.2.0/24",
        "pops": [
            {"name": p.name, "region": p.region, "ipv4": p.ipv4,
             "ipv6": p.ipv6, "transit_asns": p.transit_asns}
            for p in pops
        ],
    }
    with open("outputs/anycast_plan.json", "w") as f:
        json.dump(out, f, indent=2)
    print()
    print("Wrote outputs/anycast_plan.json")


if __name__ == "__main__":
    main()
