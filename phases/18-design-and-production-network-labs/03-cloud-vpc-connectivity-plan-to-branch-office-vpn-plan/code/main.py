#!/usr/bin/env python3
"""Cloud VPC Connectivity + Branch Office VPN Planner (Production Lab 03).

Ingests on-prem CIDRs, AWS VPC CIDRs, and a branch list, then emits a
non-overlapping CIDR plan, IPsec + BGP topology, MTU / MSS plan, DNS resolver
strategy, and a cost estimate for VPN vs Direct Connect vs SD-WAN. Stdlib only.

Run:  python3 main.py
"""
from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field, asdict
from ipaddress import IPv4Network
from itertools import count


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------

@dataclass
class Branch:
    name: str
    cidr: str           # e.g. "10.100.24.0/24"
    bandwidth_mbps: int


@dataclass
class VPC:
    name: str
    cidr: str           # e.g. "10.50.0.0/16"
    az_count: int = 3


@dataclass
class Plan:
    customer: str
    onprem_cidrs: list[str]
    vpcs: list[VPC]
    branches: list[Branch]
    tunnels: list[dict] = field(default_factory=list)
    bgp_peers: list[dict] = field(default_factory=list)
    cost: dict = field(default_factory=dict)
    mtu: dict = field(default_factory=dict)
    dns: list[dict] = field(default_factory=list)


# ---------------------------------------------------------------------------
# CIDR validation
# ---------------------------------------------------------------------------

def overlap(a: str, b: str) -> bool:
    return IPv4Network(a).overlaps(IPv4Network(b))


def validate_non_overlap(cidrs: list[str]) -> list[str]:
    issues: list[str] = []
    for i, a in enumerate(cidrs):
        for b in cidrs[i + 1:]:
            if overlap(a, b):
                issues.append(f"OVERLAP: {a} <-> {b}")
    return issues


def allocate_tunnel_subnets(num_tunnels: int) -> list[str]:
    """Allocate /30 subnets from 169.254.0.0/16 (RFC 3927 link-local alt)."""
    base = IPv4Network("169.254.0.0/16")
    out: list[str] = []
    cursor = 0
    for _ in range(num_tunnels):
        net = IPv4Network((int(base.network_address) + cursor * 4, 30))
        out.append(str(net))
        cursor += 1
    return out


# ---------------------------------------------------------------------------
# IPsec + BGP topology
# ---------------------------------------------------------------------------

def build_topology(plan: Plan) -> None:
    """For each VPC, build 2 redundant tunnels to the on-prem edge + 1 tunnel
    per branch. Assign private ASNs from 64512-65534 (RFC 6996) and tunnel
    /30 subnets from 169.254.0.0/16.
    """
    asn_gen = count(64512)
    vpc_asn = {v.name: next(asn_gen) for v in plan.vpcs}
    branch_asn = {b.name: next(asn_gen) for b in plan.branches}
    onprem_asn = next(asn_gen)

    total_tunnels = 2 * len(plan.vpcs) + len(plan.branches)
    tunnel_subs = allocate_tunnel_subnets(total_tunnels)
    cursor = 0

    for v in plan.vpcs:
        for n in (1, 2):
            sub = tunnel_subs[cursor]
            cursor += 1
            net = IPv4Network(sub)
            local_ip = str(net.network_address + 1)
            remote_ip = str(net.network_address + 2)
            plan.tunnels.append({
                "name": f"vpc-{v.name}-t{n}",
                "type": "vpc",
                "endpoint_local": local_ip,
                "endpoint_remote": remote_ip,
                "vpc": v.name,
                "vpc_cidr": v.cidr,
                "vpc_asn": vpc_asn[v.name],
                "onprem_asn": onprem_asn,
                "ike": "IKEv2",
                "encryption": "AES-256-GCM-16",
                "prf": "SHA-384",
                "dh_group": 20,
                "pfs": True,
                "lifetime_s": 3600,
                "dpd_delay_s": 10,
                "dpd_timeout_s": 30,
                "bfd_ms": 50,
                "bfd_multiplier": 3,
                "auth": "TCP-AO",
                "redundant_with": f"vpc-{v.name}-t{2 if n == 1 else 1}",
            })
            plan.bgp_peers.append({
                "peer_ip": remote_ip,
                "local_asn": onprem_asn,
                "remote_asn": vpc_asn[v.name],
                "vrf": "default",
                "multihop": 2,
                "bfd": True,
                "auth_pwd": "***",
                "announced_prefixes": [v.cidr],
            })

    for b in plan.branches:
        sub = tunnel_subs[cursor]
        cursor += 1
        net = IPv4Network(sub)
        local_ip = str(net.network_address + 1)
        remote_ip = str(net.network_address + 2)
        plan.tunnels.append({
            "name": f"branch-{b.name}",
            "type": "branch",
            "endpoint_local": local_ip,
            "endpoint_remote": remote_ip,
            "branch": b.name,
            "branch_cidr": b.cidr,
            "branch_asn": branch_asn[b.name],
            "onprem_asn": onprem_asn,
            "ike": "IKEv2",
            "encryption": "AES-256-GCM-16",
            "prf": "SHA-384",
            "dh_group": 20,
            "pfs": True,
            "lifetime_s": 28800,
            "dpd_delay_s": 10,
            "dpd_timeout_s": 30,
            "bfd_ms": 100,
            "bfd_multiplier": 3,
            "auth": "TCP-AO",
        })
        plan.bgp_peers.append({
            "peer_ip": remote_ip,
            "local_asn": onprem_asn,
            "remote_asn": branch_asn[b.name],
            "vrf": "default",
            "multihop": 2,
            "bfd": True,
            "auth_pwd": "***",
            "announced_prefixes": [b.cidr],
        })


# ---------------------------------------------------------------------------
# MTU / MSS
# ---------------------------------------------------------------------------

def mtu_plan() -> dict:
    return {
        "ethernet_default": 1500,
        "ipsec_overhead_bytes": 50,
        "gre_overhead_bytes": 24,
        "internet_vpn_path_mtu": 1400,
        "direct_connect_path_mtu": 1500,
        "internet_vpn_mss": 1360,
        "direct_connect_mss": 1460,
        "pmtud_required": True,
        "iptables_mss_clamp_rule": (
            "iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN "
            "-j TCPMSS --set-mss 1360"
        ),
        "nft_mss_clamp_rule": (
            "nft add rule inet mangle forward tcp flags syn tcp option maxseg size set 1360"
        ),
    }


# ---------------------------------------------------------------------------
# DNS strategy
# ---------------------------------------------------------------------------

def dns_plan(vpcs: list[VPC]) -> list[dict]:
    rules: list[dict] = []
    for v in vpcs:
        rules.append({
            "vpc": v.name,
            "inbound_endpoint": f"in-{v.name}.resolver.example.com",
            "outbound_endpoint": f"out-{v.name}.resolver.example.com",
            "forward_to_onprem_for_zones": ["corp.northbeam.io", "internal.local"],
            "forward_from_onprem_for_zones": [
                f"{v.name}.example.com",
                "amazonaws.com",
                "ec2.internal",
            ],
        })
    return rules


# ---------------------------------------------------------------------------
# Cost estimator
# ---------------------------------------------------------------------------

RATE = {
    "site_to_site_vpn_tunnel_per_hour": 0.05,
    "direct_connect_port_1g_per_hour": 0.30,
    "direct_connect_data_per_gb": 0.02,
    "vpn_data_out_per_gb": 0.09,
    "tgw_attachment_per_hour": 0.07,
    "route53_resolver_endpoint_per_hour": 0.125,
    "sdwan_appliance_capex": 2_500,
    "sdwan_subscription_per_month": 250,
}


def cost_estimate(plan: Plan, monthly_egress_gb: int) -> dict:
    vpn_tunnels = 2 * len(plan.branches)
    vpn_monthly = vpn_tunnels * 720 * RATE["site_to_site_vpn_tunnel_per_hour"]
    vpn_monthly += max(0, monthly_egress_gb - 100) * RATE["vpn_data_out_per_gb"]

    dx_monthly = 720 * RATE["direct_connect_port_1g_per_hour"]
    dx_monthly += monthly_egress_gb * RATE["direct_connect_data_per_gb"]

    tgw_att = len(plan.vpcs) + len(plan.branches)
    tgw_monthly = tgw_att * 720 * RATE["tgw_attachment_per_hour"]
    r53_monthly = 2 * len(plan.vpcs) * 720 * RATE["route53_resolver_endpoint_per_hour"]

    sdwan_capex = len(plan.branches) * RATE["sdwan_appliance_capex"]
    sdwan_opex = (len(plan.branches) * RATE["sdwan_subscription_per_month"]
                  + vpn_monthly + tgw_monthly + r53_monthly)

    return {
        "vpn_monthly_usd": round(vpn_monthly, 2),
        "direct_connect_monthly_usd": round(dx_monthly + tgw_monthly + r53_monthly, 2),
        "direct_connect_capex_usd": 5_000,
        "sdwan_monthly_opex_usd": round(sdwan_opex, 2),
        "sdwan_capex_usd": sdwan_capex,
        "vpn_tunnels": vpn_tunnels,
        "egress_gb_per_month": monthly_egress_gb,
        "recommendation": (
            "Direct Connect" if monthly_egress_gb > 8000 else
            "Site-to-Site VPN with future DX migration" if monthly_egress_gb > 1000 else
            "Site-to-Site VPN only"
        ),
    }


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def emit_ipsec_strongswan(tunnel: dict) -> str:
    return textwrap.dedent(f"""\
        conn {tunnel['name']}
          keyexchange=ikev2
          left={tunnel['endpoint_local']}
          leftsubnet=0.0.0.0/0
          right={tunnel['endpoint_remote']}
          rightsubnet=0.0.0.0/0
          ike={tunnel['encryption']}-{tunnel['prf']}-dh{tunnel['dh_group']}
          esp={tunnel['encryption']}
          ikelifetime={tunnel['lifetime_s']}s
          lifetime={tunnel['lifetime_s']}s
          dpdaction=restart
          dpddelay={tunnel['dpd_delay_s']}s
          dpdtimeout={tunnel['dpd_timeout_s']}s
          authby=secret
        """)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    plan = Plan(
        customer="Northbeam Software",
        onprem_cidrs=["10.10.0.0/16", "10.20.0.0/16"],
        vpcs=[
            VPC("prod", "10.50.0.0/16"),
            VPC("staging", "10.51.0.0/16"),
            VPC("shared-services", "10.52.0.0/16"),
        ],
        branches=[
            Branch("seattle", "10.100.1.0/24", 100),
            Branch("austin", "10.100.2.0/24", 50),
            Branch("boston", "10.100.3.0/24", 50),
            Branch("denver", "10.100.4.0/24", 25),
        ],
    )

    all_cidrs = plan.onprem_cidrs + [v.cidr for v in plan.vpcs] + [b.cidr for b in plan.branches]
    issues = validate_non_overlap(all_cidrs)
    if issues:
        print("CIDR issues:")
        for i in issues:
            print(f"  - {i}")
        return

    build_topology(plan)
    plan.mtu = mtu_plan()
    plan.dns = dns_plan(plan.vpcs)
    plan.cost = cost_estimate(plan, monthly_egress_gb=5_000)

    print("=" * 72)
    print(f"Cloud Connectivity Plan: {plan.customer}")
    print("=" * 72)
    print(f"  On-prem CIDRs: {plan.onprem_cidrs}")
    print(f"  VPCs:          {[(v.name, v.cidr) for v in plan.vpcs]}")
    print(f"  Branches:      {[(b.name, b.cidr) for b in plan.branches]}")
    print(f"  Tunnels:       {len(plan.tunnels)}  BGP peers: {len(plan.bgp_peers)}")
    print(f"\n  MTU plan:")
    for k, v in plan.mtu.items():
        if k.endswith("_rule"):
            print(f"    {k:32s} {v}")
        else:
            print(f"    {k:32s} {v}")
    print(f"\n  DNS resolver rules (per VPC):")
    for r in plan.dns:
        print(f"    {r['vpc']:18s} in={r['inbound_endpoint']} out={r['outbound_endpoint']}")
    print(f"\n  Cost estimate:")
    for k, v in plan.cost.items():
        print(f"    {k:32s} {v}")
    print(f"\n  Sample strongSwan config for first tunnel:")
    print(emit_ipsec_strongswan(plan.tunnels[0]))

    payload = {
        "customer": plan.customer,
        "onprem_cidrs": plan.onprem_cidrs,
        "vpcs": [asdict(v) for v in plan.vpcs],
        "branches": [asdict(b) for b in plan.branches],
        "tunnels": plan.tunnels,
        "bgp_peers": plan.bgp_peers,
        "mtu": plan.mtu,
        "dns": plan.dns,
        "cost": plan.cost,
    }
    print("\n--- JSON plan (first 30 lines) ---")
    for line in json.dumps(payload, indent=2).splitlines()[:30]:
        print(line)


if __name__ == "__main__":
    main()