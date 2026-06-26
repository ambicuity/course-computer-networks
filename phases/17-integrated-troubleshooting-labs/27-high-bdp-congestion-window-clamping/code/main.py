#!/usr/bin/env python3
"""Slow start and cwnd clamping across a high-BDP link.

Reference oracle for the integrated troubleshooting lab. Computes
the BDP, the target cwnd, and the buffer requirements; then
prints the verdict for the four scenarios.

Scenarios:

  bdp_clamped
    Default tcp_wmem max=4MB; cwnd peaks at ~30 segments; transfer
    is cwnd-limited, not bandwidth-limited.

  cwnd_grown
    tcp_wmem max=64MB; cwnd grows to BDP; transfer fills the link.

  init_cwnd_high
    initcwnd=32 (or higher) for high-BDP link; fewer RTTs to reach
    the BDP.

  slow_start_after_idle
    cwnd collapses to initcwnd after a 2s idle; transfer is
    inefficient for bulk workloads.

Run:  python3 main.py --scenario bdp_clamped
"""
from __future__ import annotations

import argparse


def bdp_bytes(bandwidth_gbps: float, rtt_ms: int) -> int:
    return int(bandwidth_gbps * 1_000_000_000 / 8 * (rtt_ms / 1000))


def target_cwnd_segments(bdp: int, mss: int) -> int:
    return bdp // mss


def throughput_mbps(cwnd_segments: int, mss: int, rtt_ms: int) -> float:
    """Compute the achieved throughput in Mbps given the cwnd."""
    bytes_in_flight = cwnd_segments * mss
    bits_per_rtt = bytes_in_flight * 8
    rtt_seconds = rtt_ms / 1000.0
    return bits_per_rtt / rtt_seconds / 1_000_000


def initcwnd_rtt_to_bdp(initcwnd: int, bdp_segments: int) -> int:
    """How many RTTs of slow start are needed to reach the BDP."""
    if initcwnd <= 0:
        return 0
    ratio = bdp_segments // initcwnd
    if ratio <= 1:
        return 1
    bits = ratio.bit_length() - 1
    if (1 << bits) < ratio:
        bits += 1
    return bits


def required_tcp_wmem_max(bdp: int, headroom_segments: int = 4) -> int:
    """Compute the right tcp_wmem max for the BDP plus headroom."""
    return bdp * headroom_segments


def self_test() -> bool:
    """Verify the BDP and cwnd arithmetic for the canonical 1Gbps/200ms case."""
    bdp = bdp_bytes(1.0, 200)
    assert bdp == 25_000_000, f"expected 25 MB, got {bdp}"
    target = target_cwnd_segments(bdp, 1460)
    assert target == 17_123, f"expected 17,123 segments, got {target}"
    tput = throughput_mbps(target, 1460, 200)
    assert abs(tput - 1000.0) < 1.0, f"expected ~1000 Mbps, got {tput}"
    rtts = initcwnd_rtt_to_bdp(10, target)
    assert rtts >= 10, f"expected at least 10 RTTs, got {rtts}"
    return True


def render_scenario(scenario: str) -> str:
    out: list[str] = []
    out.append("=" * 64)
    out.append(f"HIGH-BDP DIAGNOSTIC  --  scenario: {scenario}")
    out.append("=" * 64)
    out.append("")
    bdp = bdp_bytes(1.0, 200)
    mss = 1460
    target = target_cwnd_segments(bdp, mss)
    out.append(f"  Link bandwidth  : 1 Gbps")
    out.append(f"  RTT             : 200 ms")
    out.append(f"  BDP             : {bdp:,} bytes (~{bdp // 1_000_000} MB)")
    out.append(f"  MSS             : {mss} bytes")
    out.append(f"  Target cwnd     : {target:,} segments")
    out.append("")
    if scenario == "bdp_clamped":
        out.append("  Default tcp_wmem: 4096 16384 4194304  (max 4 MB)")
        out.append("  Observed cwnd   : 30 segments (= 43 KB)")
        out.append("")
        out.append("Verdict: cwnd is buffer-clamped. Buffer max=4MB; cwnd cannot")
        out.append("exceed the buffer's in-flight portion. The transfer is slow.")
        out.append("Fix: tcp_wmem='4096 87380 67108864' (64 MB max).")
    elif scenario == "cwnd_grown":
        out.append("  tcp_wmem        : 4096 87380 67108864  (max 64 MB)")
        out.append("  Observed cwnd   : 17,000+ segments (= 25 MB)")
        out.append("")
        out.append("Verdict: cwnd reaches the BDP. Transfer fills the 1 Gbps link.")
    elif scenario == "init_cwnd_high":
        out.append("  initcwnd=32  (per-route: ip route change ... initcwnd 32)")
        out.append("")
        out.append("Default initcwnd=10 (RFC 6928) means the cwnd starts at 10 MSS")
        out.append("and reaches the BDP after log2(BDP/initcwnd) RTTs. For 17,000")
        out.append("segments from 10, that is 10.7 RTTs = 2.14 s of under-utilized link.")
        out.append("With initcwnd=32, log2(17000/32) = 9.05 RTTs = 1.81 s. Marginal gain.")
        out.append("Larger initcwnd (64) saves more but risks initial burst loss.")
    else:
        out.append("  tcp_slow_start_after_idle=1  (default)")
        out.append("  After 1 RTT of idle, cwnd collapses to initcwnd=10.")
        out.append("")
        out.append("Verdict: a 2s pause in a bulk transfer triggers cwnd collapse.")
        out.append("Subsequent growth takes 10+ RTTs to recover; throughput dips.")
        out.append("Fix: sysctl -w net.ipv4.tcp_slow_start_after_idle=0")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--scenario",
        choices=("bdp_clamped", "cwnd_grown", "init_cwnd_high", "slow_start_after_idle"),
        default="bdp_clamped",
    )
    parser.add_argument("--self-test", action="store_true", help="Run self-test and exit.")
    args = parser.parse_args()
    if args.self_test:
        ok = self_test()
        print("BDP/cwnd self-test: PASS" if ok else "BDP/cwnd self-test: FAIL")
        return
    print(render_scenario(args.scenario))


if __name__ == "__main__":
    main()
