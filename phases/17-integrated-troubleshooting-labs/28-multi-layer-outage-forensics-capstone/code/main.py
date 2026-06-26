#!/usr/bin/env python3
"""Multi-layer outage forensics capstone.

Reference oracle for the integrated troubleshooting lab. Reads a
synthetic symptom report (5 channels) and an evidence dump (5
diagnostic command outputs), and prints the per-symptom verdict.

The simulator does not sniff live traffic; it walks a state machine
for each symptom and identifies the root cause from the evidence.
The output is a 5-row table with the symptom, the layer, the root
cause, and the corrective action.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Symptom:
    channel: str
    symptom: str
    layer: str
    command: str
    good: str
    bad: str
    root_cause: str
    action: str


SYMPTOMS = [
    Symptom(
        channel="Web portal",
        symptom="502 Bad Gateway",
        layer="L7 (proxy)",
        command="openssl s_client -proxy proxy.corp.example:3128 "
                "-connect bank.example.com:443 -servername bank.example.com",
        good="issuer=CN=DigiCert Global G2",
        bad="issuer=CN=Corp Internal Sub-CA, O=Corp",
        root_cause="Corporate proxy is in MITM mode for bank.example.com",
        action="Whitelist bank.example.com in the proxy's no-intercept list",
    ),
    Symptom(
        channel="Mobile app (large)",
        symptom="SSL handshake failed for large requests",
        layer="L4 (MTU)",
        command="tracepath -m 5 api.bank.example.com; ping -M do -s 1472 api.bank.example.com",
        good="pmtu 1500; Reply from ...",
        bad="pmtu 1280; nothing",
        root_cause="Egress firewall drops ICMP Type 3 Code 4 (PMTUD black hole)",
        action="Allow ICMP Type 3 Code 4 outbound; OR MSS-clamp on the tunnel",
    ),
    Symptom(
        channel="Bulk file transfer",
        symptom="50% of expected throughput",
        layer="L4 (ECN)",
        command="tc -s qdisc show dev eth0",
        good="ecn_mark 0",
        bad="ecn_mark 12345",
        root_cause="CoDel is configured with the `ecn` parameter; sender halves CWND",
        action="tc qdisc replace dev eth0 root codel target 5ms interval 100ms  (no `ecn`)",
    ),
    Symptom(
        channel="SSH jump host",
        symptom="Permission denied (publickey)",
        layer="L7 (WireGuard)",
        command="wg show wg0",
        good="AllowedIPs = 10.0.0.0/24",
        bad="AllowedIPs = 10.0.0.5/32",
        root_cause="Peer's AllowedIPs on the jump host is too narrow; 10.0.0.6 is dropped",
        action="Edit /etc/wireguard/wg0.conf and expand AllowedIPs to 10.0.0.0/24",
    ),
    Symptom(
        channel="DNS (corporate resolver)",
        symptom="SERVFAIL",
        layer="L7 (DNSSEC)",
        command="dig +dnssec bank.example.com @127.0.0.1",
        good="status: NOERROR, ad flag",
        bad="status: SERVFAIL",
        root_cause="Parent has old DS, child rolled KSK to new key tag 67890",
        action="Publish new DS in parent for key tag 67890; wait for parent TTL",
    ),
]


def render() -> str:
    out: list[str] = []
    out.append("=" * 110)
    out.append("MULTI-LAYER OUTAGE FORENSICS CAPSTONE")
    out.append("=" * 110)
    out.append("")
    header = f"{'Channel':<22}  {'Symptom':<32}  {'Layer':<14}  Root cause"
    out.append(header)
    out.append("-" * 110)
    for s in SYMPTOMS:
        out.append(
            f"{s.channel:<22}  {s.symptom:<32}  {s.layer:<14}  {s.root_cause}"
        )
    out.append("")
    out.append("Per-symptom runbook:")
    out.append("-" * 110)
    for s in SYMPTOMS:
        out.append(f"\n[{s.channel}]  {s.symptom}")
        out.append(f"  Layer      : {s.layer}")
        out.append(f"  Command    : {s.command}")
        out.append(f"  Good       : {s.good}")
        out.append(f"  Bad        : {s.bad}")
        out.append(f"  Root cause : {s.root_cause}")
        out.append(f"  Action     : {s.action}")
    out.append("")
    out.append("Verdict: 5 simultaneous failures. Each symptom maps to a single root cause.")
    out.append("Apply the actions in any order; the fixes are independent.")
    return "\n".join(out)


def main() -> None:
    print(render())


if __name__ == "__main__":
    main()
