"""VoIP Packetization and Delay Budget.

A stdlib-only delay-budget calculator for Voice over IP. Models each
delay stage (capture, encode, packetization, network, jitter buffer,
decode, render, look-ahead), sums the total one-way mouth-to-ear delay,
classifies it per ITU-T G.114, and compares codec profiles and
packetization intervals.

Run:  python3 main.py
Exit: 0
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# Header overhead for IP + UDP + RTP (uncompressed)
IP_UDP_RTP_HEADER_BYTES = 40


@dataclass
class DelayBudget:
    """A set of named delay stages that sum to the one-way delay."""

    stages: Dict[str, float] = field(default_factory=dict)

    def total(self) -> float:
        return sum(self.stages.values())

    def dominant_component(self) -> Tuple[str, float]:
        if not self.stages:
            return ("none", 0.0)
        name = max(self.stages, key=self.stages.get)
        return (name, self.stages[name])

    def breakdown(self) -> List[Tuple[str, float]]:
        return sorted(self.stages.items(), key=lambda kv: kv[1], reverse=True)


def classify_g114(one_way_ms: float) -> str:
    """Classify one-way delay per ITU-T G.114."""
    if one_way_ms <= 150:
        return "Good (<=150 ms): acceptable for nearly all users"
    if one_way_ms <= 300:
        return "Acceptable (150-300 ms): noticeable on interactive calls"
    if one_way_ms <= 700:
        return "Poor (300-700 ms): talk-over and echo issues"
    return f"Unusable (>700 ms): half-duplex walkie-talkie behavior"


def packet_overhead_fraction(payload_bytes: int, header_bytes: int = IP_UDP_RTP_HEADER_BYTES) -> float:
    """Fraction of total packet bandwidth consumed by headers."""
    return header_bytes / (payload_bytes + header_bytes)


def payload_bytes_for(sample_rate_hz: int, interval_ms: float, bytes_per_sample: int) -> int:
    """Compute payload size for a given codec and packetization interval."""
    samples = int(sample_rate_hz * interval_ms / 1000)
    return samples * bytes_per_sample


def packets_per_second(interval_ms: float) -> float:
    return 1000.0 / interval_ms


def bandwidth_kbps(payload_bytes: int, interval_ms: float, header_bytes: int = IP_UDP_RTP_HEADER_BYTES) -> float:
    """Total bandwidth (payload + headers) in kbps."""
    bits_per_packet = (payload_bytes + header_bytes) * 8
    return bits_per_packet * packets_per_second(interval_ms) / 1000.0


# Codec profiles: (name, sample_rate_hz, bytes_per_sample, encode_ms, lookahead_ms, decode_ms)
CODEC_PROFILES: Dict[str, Tuple[int, int, float, float, float]] = {
    "G.711": (8000, 1, 0.0, 0.0, 1.0),
    "G.729": (8000, 1, 5.0, 5.0, 2.0),  # 10 ms frames, 5 ms look-ahead
    "Opus": (16000, 1, 3.0, 5.0, 2.0),   # wideband, 20 ms frames, 5 ms look-ahead
}


def build_budget(
    codec: str,
    interval_ms: float,
    network_ms: float,
    jitter_buffer_ms: float,
    capture_ms: float = 1.0,
    render_ms: float = 1.0,
) -> DelayBudget:
    """Build a delay budget for a given codec and path."""
    sample_rate, bps, encode_ms, lookahead_ms, decode_ms = CODEC_PROFILES[codec]
    return DelayBudget(stages={
        "capture": capture_ms,
        "encode": encode_ms,
        "lookahead": lookahead_ms,
        "packetization": interval_ms,
        "network": network_ms,
        "jitter_buffer": jitter_buffer_ms,
        "decode": decode_ms,
        "render": render_ms,
    })


def main() -> None:
    print("VoIP Packetization and Delay Budget\n")
    print("Each stage adds to the one-way mouth-to-ear delay. The total must")
    print("stay within the G.114 budget to keep the call interactive.\n")

    # === Part 1: Component breakdown for three codecs ===
    print("=== Part 1: Delay Budget by Codec (20 ms packetization, 30 ms network) ===\n")
    interval = 20.0
    network = 30.0
    jitter = 40.0
    print(f"  Packetization: {interval} ms, Network: {network} ms, Jitter buffer: {jitter} ms\n")
    print(f"  {'codec':>7}  {'total':>7}  {'class':<55}")
    print("  " + "-" * 75)
    results: List[Tuple[str, DelayBudget]] = []
    for codec in CODEC_PROFILES:
        budget = build_budget(codec, interval, network, jitter)
        total = budget.total()
        cls = classify_g114(total)
        results.append((codec, budget))
        print(f"  {codec:>7}  {total:7.1f}  {cls}")
    print()

    # Detailed breakdown for G.711
    print("  Detailed breakdown (G.711):")
    g711 = results[0][1]
    dom_name, dom_val = g711.dominant_component()
    for stage, val in g711.breakdown():
        pct = val / g711.total() * 100 if g711.total() else 0
        bar = "#" * int(val / 2)
        print(f"    {stage:>14}: {val:6.1f} ms  ({pct:4.1f}%) {bar}")
    print(f"    {'TOTAL':>14}: {g711.total():6.1f} ms")
    print(f"    Dominant component: {dom_name} ({dom_val:.1f} ms)")
    print()

    # === Part 2: Packetization sweep ===
    print("=== Part 2: Packetization Interval Sweep (G.711) ===\n")
    sample_rate, bps = CODEC_PROFILES["G.711"][0], CODEC_PROFILES["G.711"][1]
    print(f"  G.711: {sample_rate} Hz, {bps} byte/sample, header {IP_UDP_RTP_HEADER_BYTES} bytes\n")
    print(f"  {'interval':>9}  {'payload':>8}  {'overhead':>9}  {'bw_kbps':>8}  {'delay_ms':>9}")
    print("  " + "-" * 55)
    for interval_ms in [10, 20, 30, 40, 60, 80, 120]:
        payload = payload_bytes_for(sample_rate, interval_ms, bps)
        oh = packet_overhead_fraction(payload)
        bw = bandwidth_kbps(payload, interval_ms)
        delay = interval_ms
        print(f"  {interval_ms:9.1f}  {payload:8d}  {oh*100:8.1f}%  {bw:8.1f}  {delay:9.1f}")
    print()
    print("  Observations:")
    print("    - 10 ms packets: 50 pps, 37.5% overhead, low delay but costly on slow links")
    print("    - 60 ms packets: ~17 pps, 7.7% overhead, but 60 ms added to the delay budget")
    print("    - 20 ms is the common VoIP default: balance of delay and overhead")
    print()

    # === Part 3: Codec comparison on the same path ===
    print("=== Part 3: Codec Comparison on a 100 ms Congested Path ===\n")
    network_congested = 100.0
    jitter_wide = 60.0
    print(f"  Network: {network_congested} ms, Jitter buffer: {jitter_wide} ms\n")
    print(f"  {'codec':>7}  {'interval':>9}  {'total':>7}  {'bw_kbps':>8}  {'class':<45}")
    print("  " + "-" * 80)
    for codec in CODEC_PROFILES:
        budget = build_budget(codec, 20.0, network_congested, jitter_wide)
        total = budget.total()
        sample_rate, bps = CODEC_PROFILES[codec][0], CODEC_PROFILES[codec][1]
        payload = payload_bytes_for(sample_rate, 20.0, bps)
        bw = bandwidth_kbps(payload, 20.0)
        cls = classify_g114(total)
        print(f"  {codec:>7}  {20.0:9.1f}  {total:7.1f}  {bw:8.1f}  {cls}")
    print()

    # === Part 4: G.114 boundary analysis ===
    print("=== Part 4: Maximum Network Delay for 'Good' Class (<=150 ms) ===\n")
    print("  Given fixed packetization and jitter buffer, find the max network delay.\n")
    for codec in CODEC_PROFILES:
        budget_zero_net = build_budget(codec, 20.0, 0.0, 40.0)
        non_network = budget_zero_net.total()
        max_network = 150.0 - non_network
        print(f"  {codec:>7}: non-network delay = {non_network:.1f} ms, max network = {max_network:.1f} ms")
    print()

    # === Part 5: Echo threshold ===
    print("=== Part 5: Echo Cancellation Threshold ===\n")
    print("  Echo cancellation becomes mandatory as one-way delay grows.\n")
    thresholds = [(0, "Tolerable (sounds like sidetone)"),
                  (25, "Mandatory: echo becomes annoying above ~25 ms one-way"),
                  (50, "Strongly recommended: long-delay echo is very disruptive")]
    for t, desc in thresholds:
        print(f"  {t:>4} ms: {desc}")
    print()

    # Worked example
    print("=== Worked Example: G.711, 40 ms packetization, 30 ms network ===\n")
    budget_example = build_budget("G.711", 40.0, 30.0, 40.0)
    for stage, val in budget_example.breakdown():
        print(f"  {stage:>14}: {val:6.1f} ms")
    print(f"  {'TOTAL':>14}: {budget_example.total():6.1f} ms")
    print(f"  G.114 class: {classify_g114(budget_example.total())}")
    print()

    print("Key observations:")
    print("  - Packetization interval adds directly to delay; double it, add that many ms")
    print("  - Header overhead falls as payload grows, but delay grows by the same amount")
    print("  - Network delay usually dominates; no codec change can fix a slow path")
    print("  - Jitter buffer is the second largest controllable component")
    print("  - Look-ahead codecs (G.729, Opus) add one frame of unavoidable delay")
    print("  - Stay under 150 ms one-way for the best interactive experience")
    print()
    print("Done.")


if __name__ == "__main__":
    main()