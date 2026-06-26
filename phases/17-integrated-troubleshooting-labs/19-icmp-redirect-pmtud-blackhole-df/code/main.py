#!/usr/bin/env python3
"""ICMP Redirect and Path MTU Discovery Blackhole with DF.

Reference oracle for the integrated troubleshooting lab. Computes
the expected ICMP Type 3 Code 4 message that a working path should
return when a DF-bit packet is too large, and prints the verdict
for the three scenarios. Stdlib only; no scapy.

Scenarios:

  black_hole
    A tunnel MTU of 1420 sits on the path, the egress firewall
    drops ICMP Type 3 Code 4 outbound, the host never hears about
    the failure, and the TCP connection stalls for tcp_retries2
    rounds.

  pmtud_ok
    A router on the path returns ICMP Type 3 Code 4 with the
    next-hop MTU; the host updates its path MTU cache and retries
    at the smaller size.

  mss_clamp
    The router clamps the MSS in the TCP SYN to path_MTU - 40;
    the host never sends a segment larger than the path can carry,
    so PMTUD is not needed.

Run:  python3 main.py --scenario black_hole
      python3 main.py --scenario pmtud_ok
      python3 main.py --scenario mss_clamp
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass


@dataclass(frozen=True)
class IcmpType3Code4:
    type: int = 3
    code: int = 4
    unused: int = 0
    next_hop_mtu: int = 0
    original_packet_first_8_bytes: bytes = b""

    def layout(self) -> str:
        return (
            f"  Type        : {self.type}\n"
            f"  Code        : {self.code}   (Fragmentation Needed and DF was set)\n"
            f"  Checksum    : (computed by the kernel)\n"
            f"  Unused      : 0x{self.unused:04x}\n"
            f"  Next-Hop MTU: {self.next_hop_mtu}\n"
            f"  Inner IP    : (original packet's IP header + 64 bits of payload)\n"
        )


def compute_mss(path_mtu: int, ip_version: int = 4) -> int:
    """MSS = path_MTU - IP_header - TCP_header. 40 for IPv4, 60 for IPv6."""
    overhead = 40 if ip_version == 4 else 60
    return path_mtu - overhead


def render(scenario: str) -> str:
    out: list[str] = []
    out.append("=" * 64)
    out.append(f"PMTUD BLACK HOLE DIAGNOSTIC  --  scenario: {scenario}")
    out.append("=" * 64)
    out.append("")
    out.append("Path:")
    out.append("  host --(eth0 MTU 1500)--> router --(ipsec0 MTU 1420)--> remote")
    out.append("")
    if scenario == "black_hole":
        out.append("Symptom: host sends 1500-byte DF-bit packet; packet vanishes.")
        out.append("Egress firewall: icmp type 3 code 4 OUTBOUND policy = DROP")
        out.append("")
        out.append("Expected ICMP Type 3 Code 4 reply (which never arrives):")
        icmp = IcmpType3Code4(next_hop_mtu=1420)
        out.append(icmp.layout())
        out.append("Verdict: PMTUD black hole. The host's path_MTU cache stays at 1500.")
        out.append("Action: enable ICMP Type 3 Code 4 outbound on the egress firewall,")
        out.append("        OR add an iptables MSS-clamp rule on the tunnel egress.")
    elif scenario == "pmtud_ok":
        mtu = 1420
        out.append("Symptom: host sends 1500-byte DF-bit packet.")
        out.append("Router on the path returns ICMP Type 3 Code 4 with next-hop MTU.")
        out.append("")
        out.append("Expected ICMP Type 3 Code 4 reply (which the host receives):")
        icmp = IcmpType3Code4(next_hop_mtu=mtu)
        out.append(icmp.layout())
        out.append("Host updates path_MTU cache to 1420; next probe is at 1420 - 1.")
        out.append("Iteration converges in log2(1500-1280) = ~4 probes (RFC 1191 sec. 4).")
        out.append("Verdict: PMTUD is healthy. No action required.")
    elif scenario == "mss_clamp":
        path_mtu = 1420
        mss_v4 = compute_mss(path_mtu, 4)
        mss_v6 = compute_mss(path_mtu, 6)
        out.append("Symptom: PMTUD is broken; ICMP Type 3 Code 4 is filtered.")
        out.append("Workaround: MSS clamp on the tunnel egress.")
        out.append("")
        out.append("Rule:")
        out.append("  iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN \\")
        out.append("      -j TCPMSS --clamp-mss-to-pmtu")
        out.append("")
        out.append(f"MSS for IPv4 TCP: {mss_v4} bytes (path_MTU - 40)")
        out.append(f"MSS for IPv6 TCP: {mss_v6} bytes (path_MTU - 60)")
        out.append("Verdict: connection is capped at the path MTU. Slower on bulk")
        out.append("transfers, but reliable. Long-term fix is to repair PMTUD.")
    else:
        out.append(f"Unknown scenario: {scenario}")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--scenario",
        choices=("black_hole", "pmtud_ok", "mss_clamp"),
        default="black_hole",
    )
    args = parser.parse_args()
    print(render(args.scenario))


if __name__ == "__main__":
    main()
