#!/usr/bin/env python3
"""Ephemeral port exhaustion and TIME_WAIT tuning diagnostic.

Reference oracle for the integrated troubleshooting lab. Computes
the ephemeral port capacity given a configurable range and rate,
and prints the verdict for the four scenarios.

Scenarios:

  port_exhausted
    Default range 32768-60999, 1000 conn/s, 60 s TIME_WAIT.
    Required ports: 60,000. Available: 28,232. EADDRNOTAVAIL.

  range_expanded
    Range expanded to 1024-65535. Available: 64,512. Sufficient.

  tw_reuse
    tcp_tw_reuse=1. Kernel can recycle TIME_WAIT sockets for new
    outgoing connections to the same destination.

  tw_recycle_removed
    tcp_tw_recycle=1 was removed in 4.12; causes NAT breakage.
    Modern kernels do not have this knob.

Run:  python3 main.py --scenario port_exhausted
"""
from __future__ import annotations

import argparse


def port_count(min_port: int, max_port: int) -> int:
    return max_port - min_port + 1


def required_ports(rate_per_sec: int, time_wait_sec: int) -> int:
    return rate_per_sec * time_wait_sec


def has_capacity(avail: int, need: int) -> bool:
    """True iff the ephemeral port range has enough capacity."""
    return avail >= need


def utilization_pct(need: int, avail: int) -> float:
    """Compute the port utilization as a percentage."""
    if avail <= 0:
        return 0.0
    return 100.0 * need / avail


def headroom_seconds(avail: int, rate_per_sec: int) -> int:
    """How many seconds of capacity remain at the given rate."""
    if rate_per_sec <= 0:
        return 0
    return avail // rate_per_sec


def self_test() -> bool:
    """Verify the port arithmetic with the canonical example."""
    avail = port_count(32768, 60999)
    need = required_ports(1000, 60)
    assert avail == 28_232, f"expected 28,232, got {avail}"
    assert need == 60_000, f"expected 60,000, got {need}"
    assert not has_capacity(avail, need), "default range should be insufficient"
    expanded = port_count(1024, 65535)
    assert expanded == 64_512, f"expected 64,512, got {expanded}"
    assert has_capacity(expanded, need), "expanded range should be sufficient"
    return True


def render_scenario(scenario: str) -> str:
    out: list[str] = []
    out.append("=" * 64)
    out.append(f"PORT EXHAUSTION DIAGNOSTIC  --  scenario: {scenario}")
    out.append("=" * 64)
    out.append("")
    if scenario == "port_exhausted":
        rng = (32768, 60999)
        rate = 1000
        tw = 60
        avail = port_count(*rng)
        need = required_ports(rate, tw)
        out.append(f"  ip_local_port_range : {rng[0]} {rng[1]}   (Linux default)")
        out.append(f"  Available ports     : {avail}")
        out.append(f"  Outgoing rate       : {rate}/s")
        out.append(f"  TIME_WAIT duration  : {tw} s")
        out.append(f"  Required ports      : {need}")
        out.append("")
        out.append(f"Verdict: {need} > {avail} -> EADDRNOTAVAIL on connect(2).")
        out.append("ss -s shows inuse ~60,000, almost all in TIME_WAIT.")
    elif scenario == "range_expanded":
        rng = (1024, 65535)
        rate = 1000
        tw = 60
        avail = port_count(*rng)
        need = required_ports(rate, tw)
        out.append(f"  ip_local_port_range : {rng[0]} {rng[1]}")
        out.append(f"  Available ports     : {avail}")
        out.append(f"  Required ports      : {need}")
        out.append("")
        out.append(f"Verdict: {need} <= {avail} -> capacity is sufficient.")
        out.append("Fix: sysctl -w net.ipv4.ip_local_port_range='1024 65535'")
    elif scenario == "tw_reuse":
        out.append("  tcp_tw_reuse=1")
        out.append("")
        out.append("Kernel can recycle a TIME_WAIT socket for a new outgoing")
        out.append("connection to the same destination IP:port.")
        out.append("Constraint: peer must be the same; safe because the peer")
        out.append("has already moved on, so straggling packets are ignored.")
        out.append("Verdict: outgoing connections can re-use TIME_WAIT ports.")
    else:
        out.append("  tcp_tw_recycle=1 was REMOVED in Linux 4.12")
        out.append("")
        out.append("Reason: caused widespread breakage for NATed clients. The")
        out.append("TIME_WAIT shortcut applied to incoming connections, but NATs")
        out.append("make many clients look like the same IP, breaking their flows.")
        out.append("Verdict: do not use this knob; use tcp_tw_reuse for outgoing")
        out.append("connections, ip_local_port_range to expand capacity.")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--scenario",
        choices=("port_exhausted", "range_expanded", "tw_reuse", "tw_recycle_removed"),
        default="port_exhausted",
    )
    parser.add_argument("--self-test", action="store_true", help="Run self-test and exit.")
    args = parser.parse_args()
    if args.self_test:
        ok = self_test()
        print("Port arithmetic self-test: PASS" if ok else "Port arithmetic self-test: FAIL")
        return
    print(render_scenario(args.scenario))


if __name__ == "__main__":
    main()
