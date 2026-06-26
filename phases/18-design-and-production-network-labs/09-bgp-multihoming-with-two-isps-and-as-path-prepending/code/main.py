#!/usr/bin/env python3
"""BGP Multihoming Planner (Production Lab 09).

Builds a deterministic multihoming plan for an AS connected to two upstream
ISPs. Produces: AS-path prepend recommendation, prefix-list, community
policy, BFD profile, convergence matrix, and a looking-glass query script.

Stdlib only: dataclasses, ipaddress, json, itertools.

Run: python3 main.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from ipaddress import IPv4Network
from typing import Iterable


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

@dataclass
class ISPProfile:
    name: str
    asn: int
    peer_ip: str             # ISP-side BGP peer IP
    local_ip: str            # customer-side BGP peer IP
    prepend_sensitivity: float  # fraction of inbound traffic shifted per prepend (0.20-0.35)
    med_honored: bool        # whether the ISP honors MED from the customer
    communities: dict[str, str]  # community:value -> human description


@dataclass
class MultihomingPlan:
    customer_asn: int
    prefixes: list[str]
    primary: ISPProfile
    backup: ISPProfile
    target_primary_pct: int  # 0..100
    bfd_interval_ms: int
    bfd_multiplier: int

    def to_dict(self) -> dict:
        return {
            "customer_asn": self.customer_asn,
            "prefixes": self.prefixes,
            "primary_asn": self.primary.asn,
            "backup_asn": self.backup.asn,
            "target_primary_pct": self.target_primary_pct,
            "bfd_interval_ms": self.bfd_interval_ms,
            "bfd_multiplier": self.bfd_multiplier,
        }


# ---------------------------------------------------------------------------
# AS-path prepend calculator
# ---------------------------------------------------------------------------

def recommend_prepends(target_pct: int, sensitivity: float) -> int:
    """Recommend number of prepended AS hops on the backup link.

    The model assumes each prepend shifts ~sensitivity fraction of inbound
    traffic from backup to primary. We want primary to land at target_pct.
    Solve:  primary_share = 1 / (1 + r * s**n)  ->  n = log(r/s) / log(s)
    where r = (100-target)/target backup share ratio and s = 1-sensitivity.
    """
    if not 0 < target_pct < 100:
        raise ValueError("target_pct must be in (0, 100)")
    r = (100 - target_pct) / target_pct  # backup/primary ratio desired
    s = 1.0 - sensitivity                 # remaining backup share per prepend
    if s <= 0 or s >= 1:
        return 3
    # log base change: n = ln(r) / ln(s)
    import math
    n = math.log(r) / math.log(s)
    n_rounded = max(0, min(5, round(n)))
    return n_rounded


# ---------------------------------------------------------------------------
# Prefix list and route-map
# ---------------------------------------------------------------------------

def build_prefix_list(prefixes: Iterable[str]) -> list[str]:
    rules: list[str] = []
    for p in prefixes:
        net = IPv4Network(p)
        rules.append(f"permit {net} ge {net.prefixlen} le {net.prefixlen}")
    # Implicit deny at the end (vendor-default)
    return rules


def build_community_policy(plan: MultihomingPlan) -> dict:
    """Emit a community string per upstream for the documented knobs."""
    out: dict[str, dict[str, str]] = {}
    for isp, role in ((plan.primary, "primary"), (plan.backup, "backup")):
        out[isp.name] = {
            "role": role,
            "geographic_preference": isp.communities.get("geographic", "<unspecified>"),
            "prepend_n_times": isp.communities.get("prepend", "<unspecified>"),
            "ddos_scope": isp.communities.get("ddos", "<unspecified>"),
            "blackhole": isp.communities.get("blackhole", "<unspecified>"),
        }
    return out


# ---------------------------------------------------------------------------
# Convergence matrix
# ---------------------------------------------------------------------------

def convergence_matrix(plan: MultihomingPlan) -> dict:
    det = plan.bfd_interval_ms * plan.bfd_multiplier   # 50 ms * 3 = 150 ms
    best_path_ms = 100   # conservative BGP best-path
    fib_install_ms = 50  # hardware FIB install
    total_ms = det + best_path_ms + fib_install_ms
    return {
        "physical_layer_detection_ms": 200,    # typical fiber link
        "bfd_detection_ms": det,
        "bgp_best_path_ms": best_path_ms,
        "fib_install_ms": fib_install_ms,
        "total_convergence_ms": total_ms,
        "tcp_session_visible_after_ms": total_ms + 200,  # RTO + retransmit
    }


# ---------------------------------------------------------------------------
# Looking-glass query script generator
# ---------------------------------------------------------------------------

LOOKING_GLASSES = [
    ("Cogent", "https://www.cogentco.com/en/looking-glass"),
    ("Hurricane Electric", "https://lg.he.net/"),
    ("NTT", "https://www.gin.ntt.net/looking-glass/"),
    ("Lumen", "https://lookingglass.centurylink.com/"),
    ("Telia", "https://lg.telia.net/"),
    ("GTT", "https://www.gtt.net/looking-glass/"),
    ("Cloudflare", "https://bgp.tools/"),
    ("Google", "https://www.peeringdb.com/"),
]


def looking_glass_script(prefixes: Iterable[str]) -> str:
    lines = ["#!/bin/sh", "# Auto-generated looking-glass query script", "set -e"]
    for p in prefixes:
        lines.append(f'echo "=== Looking-glass queries for {p} ==="')
        for name, url in LOOKING_GLASSES:
            lines.append(f'echo "-- {name}: {url} (query: show ip bgp {p}) --"')
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Print report
# ---------------------------------------------------------------------------

def print_report(plan: MultihomingPlan, n_prepends: int, pre: list[str],
                 comm: dict, conv: dict) -> None:
    print("=" * 72)
    print(f"  BGP MULTIHOMING PLAN  AS{plan.customer_asn}")
    print("=" * 72)
    print(f"  Customer AS     : {plan.customer_asn}")
    print(f"  Prefixes        : {', '.join(plan.prefixes)}")
    print(f"  Primary ISP     : {plan.primary.name} (AS{plan.primary.asn})")
    print(f"  Backup ISP      : {plan.backup.name} (AS{plan.backup.asn})")
    print(f"  Target split    : {plan.target_primary_pct}% / {100-plan.target_primary_pct}%")
    print(f"  AS-path prepends on backup: {n_prepends}")
    print()
    print("--- Prefix list ---")
    for rule in pre:
        print(f"  {rule}")
    print("  deny any (implicit)")
    print()
    print("--- Community policy (per upstream) ---")
    for isp_name, pol in comm.items():
        print(f"  {isp_name} ({pol['role']}):")
        for k, v in pol.items():
            if k == "role":
                continue
            print(f"    {k:24s} = {v}")
    print()
    print("--- BFD profile ---")
    print(f"  interval  : {plan.bfd_interval_ms} ms")
    print(f"  multiplier: {plan.bfd_multiplier}")
    print(f"  detection : {conv['bfd_detection_ms']} ms")
    print()
    print("--- Convergence matrix ---")
    for k, v in conv.items():
        print(f"  {k:32s} = {v}")
    print()
    print("--- Looking-glass endpoints ---")
    for name, url in LOOKING_GLASSES:
        print(f"  {name:24s} {url}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    westlink = ISPProfile(
        name="WestLink Telecom",
        asn=64500,
        peer_ip="198.51.100.1",
        local_ip="198.51.100.2",
        prepend_sensitivity=0.28,
        med_honored=False,
        communities={
            "geographic": "64500:200 (Seattle preference)",
            "prepend":    "64500:100 (prepend once)",
            "ddos":       "64500:666 (DDoS-scope)",
            "blackhole":  "64500:666 (RTBH)",
        },
    )
    northcoast = ISPProfile(
        name="NorthCoast Networks",
        asn=64600,
        peer_ip="203.0.113.1",
        local_ip="203.0.113.2",
        prepend_sensitivity=0.30,
        med_honored=False,
        communities={
            "geographic": "64600:300 (Pacific Northwest preference)",
            "prepend":    "64600:150 (prepend twice)",
            "ddos":       "64600:999 (DDoS-scope)",
            "blackhole":  "64600:999 (RTBH)",
        },
    )
    plan = MultihomingPlan(
        customer_asn=65001,
        prefixes=["198.51.100.0/24", "203.0.113.0/24"],
        primary=westlink,
        backup=northcoast,
        target_primary_pct=70,
        bfd_interval_ms=50,
        bfd_multiplier=3,
    )
    n_prepends = recommend_prepends(plan.target_primary_pct,
                                    plan.backup.prepend_sensitivity)
    pre = build_prefix_list(plan.prefixes)
    comm = build_community_policy(plan)
    conv = convergence_matrix(plan)
    script = looking_glass_script(plan.prefixes)

    print_report(plan, n_prepends, pre, comm, conv)

    print()
    print("--- Looking-glass script (snippet) ---")
    print("\n".join(script.splitlines()[:8]) + "\n  ...")

    out = {
        "plan": plan.to_dict(),
        "n_prepends_on_backup": n_prepends,
        "prefix_list": pre,
        "community_policy": comm,
        "convergence_matrix": conv,
        "looking_glasses": [{"name": n, "url": u} for n, u in LOOKING_GLASSES],
    }
    with open("outputs/multihoming_plan.json", "w") as f:
        json.dump(out, f, indent=2)
    print()
    print("Wrote outputs/multihoming_plan.json")


if __name__ == "__main__":
    main()
