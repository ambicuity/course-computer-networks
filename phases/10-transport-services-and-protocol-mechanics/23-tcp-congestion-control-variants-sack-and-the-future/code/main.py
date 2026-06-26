#!/usr/bin/env python3
"""TCP congestion control variants: Reno, CUBIC, SACK, ECN, BBR.

Simulates the AIMD saw-tooth, walks CUBIC's cubic window growth,
plans a SACK-aware retransmission, traces an ECN session, and
estimates BBR's bandwidth-delay product.

No network calls, no third-party packages -- pure stdlib so it runs
anywhere with `python3 main.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

CUBIC_C = 0.4
SACK_MAX_RANGES = 3


@dataclass(frozen=True)
class WindowEvent:
    rtt_index: int
    cwnd_mss: float
    state: str


def reno_sawtooth(
    initial_cwnd_mss: float,
    loss_at_cwnd_mss: float,
    rtts: int,
) -> list[WindowEvent]:
    """Linear growth from initial_cwnd_mss to loss_at_cwnd_mss, then halve."""
    events: list[WindowEvent] = [WindowEvent(0, initial_cwnd_mss, "slow-start")]
    cwnd = initial_cwnd_mss
    for rtt in range(1, rtts + 1):
        if cwnd < loss_at_cwnd_mss:
            cwnd = min(cwnd + 1.0, loss_at_cwnd_mss)
            events.append(WindowEvent(rtt, cwnd, "congestion-avoidance"))
        else:
            cwnd = cwnd / 2.0
            events.append(WindowEvent(rtt, cwnd, "loss -> cwnd halved (fast recovery)"))
    return events


def cubic_window(
    w_max_mss: float,
    t_seconds: list[float],
    k_seconds: float,
    c: float = CUBIC_C,
) -> list[float]:
    """W(t) = C * (t - K)^3 + W_max (RFC 8312)."""
    return [c * (t - k_seconds) ** 3 + w_max_mss for t in t_seconds]


def sack_retransmit_plan(
    cumulative_ack: int,
    sack_blocks: list[tuple[int, int]],
    sent_segments: list[int],
) -> tuple[list[int], list[int]]:
    """Return (without_sack_retransmits, with_sack_retransmits) byte counts."""
    if cumulative_ack < 0:
        raise ValueError("cumulative_ack must be non-negative")
    sorted_sent = sorted(sent_segments)
    without_sack = [seq for seq in sorted_sent if seq >= cumulative_ack]
    missing: set[int] = set()
    for sack_left, sack_right in sack_blocks[:SACK_MAX_RANGES]:
        covered = {seq for seq in sorted_sent if sack_left <= seq < sack_right}
        missing.difference_update(covered)
    seq = cumulative_ack
    while seq < max(sorted_sent, default=0):
        if seq in set(sorted_sent) and seq not in _covered(sack_blocks):
            missing.add(seq)
        seq += 1
    with_sack = sorted(missing)
    return without_sack, with_sack


def _covered(sack_blocks: list[tuple[int, int]]) -> set[int]:
    out: set[int] = set()
    for left, right in sack_blocks[:SACK_MAX_RANGES]:
        out.update(range(left, right))
    return out


def ecn_session() -> list[tuple[str, str, str]]:
    """Return the four-segment exchange of an ECN-marked session (RFC 3168)."""
    return [
        ("sender -> receiver", "data, IP.ECT(0) set", "ECT bit signals this segment can carry ECN"),
        ("router", "marks IP.ECT(1) -- CE codepoint", "queue approaching threshold; mark instead of drop"),
        ("receiver -> sender", "ACK with ECE=1", "ECE echoes congestion to sender"),
        ("sender -> receiver", "data with CWR=1", "CWR says sender has reacted (halved cwnd)"),
    ]


def bbr_model(bottleneck_bps: int, rtprop_seconds: float) -> dict[str, float]:
    """Bandwidth-delay product and BBR's target inflight."""
    bdp_bits = bottleneck_bps * rtprop_seconds
    bdp_bytes = bdp_bits / 8.0
    return {
        "bottleneck_bps": bottleneck_bps,
        "rtprop_seconds": rtprop_seconds,
        "bdp_bytes": bdp_bytes,
        "bdp_packets_1460": bdp_bytes / 1460,
        "target_inflight_bytes": bdp_bytes,
    }


def main() -> None:
    print("=" * 70)
    print("TCP CONGESTION CONTROL VARIANTS  --  Reno, CUBIC, SACK, ECN, BBR")
    print("=" * 70)

    print("\n[1] TCP Reno saw-tooth (initial=1 MSS, loss at 64 MSS):")
    events = reno_sawtooth(initial_cwnd_mss=1.0, loss_at_cwnd_mss=64.0, rtts=20)
    for ev in events:
        print(f"   RTT {ev.rtt_index:>3}: cwnd = {ev.cwnd_mss:>6.1f} MSS   ({ev.state})")

    print("\n[2] CUBIC window growth (W_max = 100 MSS, K = 5 s, C = 0.4):")
    for t, w in zip([0, 1, 2, 3, 5, 7, 10, 15, 20], cubic_window(100, [0, 1, 2, 3, 5, 7, 10, 15, 20], 5.0)):
        print(f"   t = {t:>3}s  ->  W(t) = {w:>8.2f} MSS")

    print("\n[3] SACK vs cumulative ACK (sender lost seq 30 and seq 50):")
    sent = list(range(1, 65))
    sack_blocks = [(31, 50), (51, 65)]
    without, with_sack = sack_retransmit_plan(cumulative_ack=30, sack_blocks=sack_blocks, sent_segments=sent)
    print(f"   sent window : seq 1..64 (one MSS per seq)")
    print(f"   lost        : 30 and 50")
    print(f"   SACK blocks : {sack_blocks}")
    print(f"   cumulative ACK only -> retransmit {len(without)} segments (seq 30..64)")
    print(f"   with SACK    -> retransmit {len(with_sack)} segments (seq {with_sack})")
    print(f"   bandwidth saved: {(len(without) - len(with_sack)) * 1460 / 1024:.1f} KB")

    print("\n[4] ECN session (RFC 3168):")
    for arrow, action, note in ecn_session():
        print(f"   {arrow:<25} {action:<28} -- {note}")

    print("\n[5] BBR model (BtlBw = 1 Gbps, RTprop = 80 ms):")
    model = bbr_model(bottleneck_bps=1_000_000_000, rtprop_seconds=0.080)
    print(f"   bandwidth-delay product = {model['bdp_bytes']:>12,.0f} bytes "
          f"({model['bdp_packets_1460']:>6.1f} packets of 1460 B)")
    print(f"   target inflight        = {model['target_inflight_bytes']:>12,.0f} bytes")
    print(f"   BBR paces at {model['bottleneck_bps']/1e6:.0f} Mbps and tries to hold {model['bdp_bytes']/1e6:.2f} MB in flight")

    print("\n[6] Reno vs CUBIC vs BBR reaction to loss / delay:")
    print("   Reno   : drops cwnd on any loss, saw-tooth under bufferbloat")
    print("   CUBIC  : cubic window growth, RTT-fair, reacts to loss only")
    print("   BBR    : model-based, paces at BtlBw, reacts to delay growth not loss")
    print("   DCTCP  : marks ECN at very low queue threshold; data-center friendly")

    print("\nDone. Try `sysctl net.ipv4.tcp_congestion_control=cubic|bbr` and compare.")


if __name__ == "__main__":
    main()