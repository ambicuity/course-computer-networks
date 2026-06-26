#!/usr/bin/env python3
"""Address Plan + VLAN + QoS Policy (Production Lab 05).

Generates IP addressing with VLSM, VLAN design, and QoS markings.

Run:  python3 main.py
"""
from __future__ import annotations


def main() -> None:
    print("=" * 65)
    print("Address Plan + VLAN Design + QoS Policy")
    print("=" * 65)

    print(f"\n  Part 1: IP Address Plan (VLSM)\n")
    subnets = [
        {"name": "Users", "hosts": 500, "subnet": "10.0.0.0/23", "usable": 510},
        {"name": "Servers", "hosts": 100, "subnet": "10.0.2.0/25", "usable": 126},
        {"name": "VoIP", "hosts": 200, "subnet": "10.0.3.0/24", "usable": 254},
        {"name": "IoT", "hosts": 50, "subnet": "10.0.4.0/26", "usable": 62},
        {"name": "Management", "hosts": 30, "subnet": "10.0.4.64/27", "usable": 30},
        {"name": "Point-to-point", "hosts": 2, "subnet": "10.0.4.96/30", "usable": 2},
    ]
    print(f"  {'Name':15s} {'Needed':>7s} {'Allocated':>10s} {'Subnet':18s} {'Utilization'}")
    print(f"  {'-'*15} {'-'*7} {'-'*10} {'-'*18} {'-'*12}")
    for s in subnets:
        util = s["hosts"] / s["usable"] * 100
        print(f"  {s['name']:15s} {s['hosts']:7d} {s['usable']:10d} {s['subnet']:18s} {util:5.0f}%")

    total_used = sum(s["usable"] for s in subnets)
    print(f"\n  Total addresses allocated: {total_used} out of 65536 in 10.0.0.0/16 ({total_used/65536*100:.1f}%)")
    print(f"  Growth capacity: {65536 - total_used} addresses available")

    print(f"\n  Part 2: VLAN Design\n")
    vlans = [
        {"id": 10, "name": "USER-DATA", "subnet": "10.0.0.0/23", "ports": "access"},
        {"id": 20, "name": "VOICE", "subnet": "10.0.3.0/24", "ports": "access+voice"},
        {"id": 30, "name": "SERVER", "subnet": "10.0.2.0/25", "ports": "access"},
        {"id": 40, "name": "IoT", "subnet": "10.0.4.0/26", "ports": "access"},
        {"id": 99, "name": "MGMT", "subnet": "10.0.4.64/27", "ports": "trunk"},
        {"id": 999, "name": "NATIVE", "subnet": "N/A", "ports": "trunk (unused)"},
    ]
    print(f"  {'ID':>4s} {'Name':15s} {'Subnet':18s} {'Port Mode'}")
    print(f"  {'-'*4} {'-'*15} {'-'*18} {'-'*15}")
    for v in vlans:
        print(f"  {v['id']:4d} {v['name']:15s} {v['subnet']:18s} {v['ports']}")
    print(f"\n  STP: RSTP mode, root priority 4096 on core-1, 8192 on core-2")
    print(f"  Native VLAN: 999 (unused, no user traffic)")
    print(f"  Trunk allowed: 10,20,30,40,99 (prune unused)")

    print(f"\n  Part 3: QoS Policy (Voice + Video)\n")
    print(f"  {'Traffic Class':20s} {'DSCP':6s} {'CoS':4s} {'Queue':8s} {'Bandwidth':10s} {'Policy'}")
    print(f"  {'-'*20} {'-'*6} {'-'*4} {'-'*8} {'-'*10} {'-'*25}")
    qos = [
        ("Voice (RTP)", "EF", "5", "Priority", "10%", "LLQ, police to 1Mbps/flow"),
        ("Voice Signaling", "CS3", "3", "Q1", "5%", "Guaranteed, WRED"),
        ("Video (RTP)", "AF41", "4", "Q2", "20%", "Priority 2, WRED"),
        ("Transactional", "AF31", "3", "Q3", "30%", "CBWFQ, WRED"),
        ("Best Effort", "BE", "0", "Q4", "35%", "WRED tail-drop"),
        ("Scavenger", "CS1", "1", "Q5", "0%", "Policed to 1Mbps"),
    ]
    for cls, dscp, cos, q, bw, policy in qos:
        print(f"  {cls:20s} {dscp:6s} {cos:4s} {q:8s} {bw:10s} {policy}")

    print(f"\n  Classification (trust boundary):")
    print(f"    Access ports: trust DSCP from IP phones (mls qos trust dscp)")
    print(f"    Server ports: trust DSCP from application servers")
    print(f"    User ports:   mark on ingress (default to BE)")
    print(f"    Uplink ports: trust DSCP (already classified at edge)")


if __name__ == "__main__":
    main()
