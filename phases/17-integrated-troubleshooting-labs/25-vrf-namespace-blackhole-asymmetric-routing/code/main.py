#!/usr/bin/env python3
"""VRF / Network Namespace conntrack and asymmetric routing diagnostic.

Reference oracle for the integrated troubleshooting lab. Walks the
conntrack state machine (NEW -> ESTABLISHED -> INVALID) and prints
the verdict that matches a production `conntrack -L` output.

Scenarios:

  asymmetric
    Reply leaves via a different interface than the original;
    conntrack marks the reply INVALID; the connection stalls.

  vrf
    Customer is in its own VRF; reply leaves via the same interface
    as the original; conntrack ESTABLISHED.

  notrack
    Bypass conntrack with `iptables -t raw -j NOTRACK`; the
    connection works but is not statefully inspected.

  policy_routing
    `ip rule` forces the reply to leave via the original interface;
    conntrack is consistent.

Run:  python3 main.py --scenario asymmetric
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class ConntrackEntry:
    protocol: str
    src: str
    dst: str
    sport: int
    dport: int
    state: str
    orig_interface: str
    reply_interface: str


# The conntrack state machine (RFC 1034 and Linux nf_conntrack).
CONNTRACK_STATES = {
    "NEW",
    "ESTABLISHED",
    "RELATED",
    "INVALID",
    "UNTRACKED",
}


def interfaces_match(orig: str, reply: str) -> bool:
    """True iff the reply's egress matches the original's ingress."""
    return orig == reply


def is_invalid_state(entry: ConntrackEntry) -> bool:
    """A conntrack entry is INVALID when the interfaces do not match."""
    if entry.state == "INVALID":
        return True
    if entry.orig_interface and entry.reply_interface:
        return not interfaces_match(entry.orig_interface, entry.reply_interface)
    return False


def fix_recommendation(state: str) -> str:
    """Map a conntrack state to the right Linux fix."""
    if state == "INVALID":
        return "use a VRF, OR add a policy routing rule, OR NOTRACK the flow"
    if state == "UNTRACKED":
        return "no fix needed; the flow is intentionally bypassed"
    return "no fix needed; conntrack is consistent"


def self_test() -> bool:
    """Run a self-test on the conntrack state machine."""
    asymmetric = ConntrackEntry(
        protocol="tcp", src="198.51.100.42", dst="203.0.113.10",
        sport=54321, dport=443, state="INVALID",
        orig_interface="eth0", reply_interface="br-cust-a",
    )
    symmetric = ConntrackEntry(
        protocol="tcp", src="198.51.100.42", dst="203.0.113.10",
        sport=54321, dport=443, state="ESTABLISHED",
        orig_interface="eth0", reply_interface="eth0",
    )
    assert is_invalid_state(asymmetric), "asymmetric should be INVALID"
    assert not is_invalid_state(symmetric), "symmetric should not be INVALID"
    return True


def render_scenario(scenario: str) -> str:
    out: list[str] = []
    out.append("=" * 64)
    out.append(f"VRF / CONNTRACK DIAGNOSTIC  --  scenario: {scenario}")
    out.append("=" * 64)
    out.append("")
    out.append("Topology:")
    out.append("  public client 198.51.100.42 --eth0-->  host  -->  br-cust-a  -->  ns-cust-a pod")
    out.append("")
    if scenario == "asymmetric":
        entry = ConntrackEntry(
            protocol="tcp", src="198.51.100.42", dst="203.0.113.10",
            sport=54321, dport=443, state="INVALID",
            orig_interface="eth0", reply_interface="br-cust-a",
        )
        out.append("conntrack -L (filtered for the flow):")
        out.append(f"  {entry.protocol} {entry.state} src={entry.src} dst={entry.dst} "
                   f"sport={entry.sport} dport={entry.dport}")
        out.append(f"  original ingress: {entry.orig_interface}")
        out.append(f"  reply egress    : {entry.reply_interface}")
        out.append("")
        out.append("Verdict: reply egress does not match original ingress.")
        out.append("Conntrack marks the reply INVALID and drops it.")
        out.append("Fix: use a VRF, OR add a policy routing rule, OR NOTRACK the flow.")
    elif scenario == "vrf":
        out.append("Customer is in `vrf-cust-a` with its own routing table.")
        out.append("The reply from the pod is routed via vrf-cust-a; it leaves")
        out.append("via the vrf-cust-a interface on the host.")
        out.append("")
        out.append("conntrack -L:")
        out.append("  tcp ESTABLISHED src=198.51.100.42 dst=203.0.113.10 ...")
        out.append("  original ingress: vrf-cust-a   reply egress: vrf-cust-a")
        out.append("")
        out.append("Verdict: conntrack ESTABLISHED; connection is healthy.")
    elif scenario == "notrack":
        out.append("`iptables -t raw -A PREROUTING -s 198.51.100.42 -j NOTRACK`")
        out.append("disables stateful inspection for the flow.")
        out.append("")
        out.append("conntrack -L: no entry (the flow is not tracked).")
        out.append("")
        out.append("Verdict: the connection works; no anti-spoofing protection.")
    else:
        out.append("ip rule add from 192.168.100.0/24 lookup 100 prio 100")
        out.append("ip route add default via 203.0.113.1 dev eth0 table 100")
        out.append("")
        out.append("Customer's pod sends reply; kernel consults table 100 because")
        out.append("the source is 192.168.100.0/24; table 100's default route is via eth0.")
        out.append("")
        out.append("conntrack -L:")
        out.append("  tcp ESTABLISHED src=198.51.100.42 dst=203.0.113.10 ...")
        out.append("  original ingress: eth0   reply egress: eth0")
        out.append("")
        out.append("Verdict: conntrack ESTABLISHED; the policy routing rule fixes the asymmetry.")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--scenario",
        choices=("asymmetric", "vrf", "notrack", "policy_routing"),
        default="asymmetric",
    )
    parser.add_argument("--self-test", action="store_true", help="Run self-test and exit.")
    args = parser.parse_args()
    if args.self_test:
        ok = self_test()
        print("Conntrack self-test: PASS" if ok else "Conntrack self-test: FAIL")
        return
    print(render_scenario(args.scenario))


if __name__ == "__main__":
    main()
