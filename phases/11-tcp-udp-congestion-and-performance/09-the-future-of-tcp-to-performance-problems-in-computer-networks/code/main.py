#!/usr/bin/env python3
"""Network performance problem analyzer and simulator.

Stdlib only. Demonstrates Sec 6.6.1 (Performance Problems) and 6.5.11
(Future of TCP):

1. Throughput, latency, and bandwidth-delay product (BDP) calculations
   for various network scenarios (Ethernet, satellite, transcontinental).
2. Bottleneck analysis: identify the limiting link, compute utilization.
3. Congestion collapse simulation: show goodput dropping as offered load
   exceeds capacity with retransmissions of delayed (not lost) packets.
4. Jitter measurement: demonstrate high-jitter vs low-jitter paths and
   the impact on playback point selection.

Run:  python3 main.py
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


@dataclass
class NetworkPath:
    name: str
    bandwidth_mbps: float
    rtt_ms: float
    mtu: int = 1500

    def bandwidth_delay_product_bits(self) -> float:
        return self.bandwidth_mbps * 1e6 * self.rtt_ms / 1000.0

    def bdp_in_packets(self) -> float:
        return self.bandwidth_delay_product_bits() / (self.mtu * 8)

    def min_window_bytes(self) -> int:
        return int(self.bandwidth_delay_product_bits() / 8)

    def max_throughput_with_window(self, window_bytes: int) -> float:
        return min(self.bandwidth_mbps, (window_bytes * 8) / (self.rtt_ms / 1000.0) / 1e6)

    def transfer_time(self, file_size_bytes: int) -> float:
        """Time to transfer a file: max(transmission, propagation)."""
        transmit = file_size_bytes * 8 / (self.bandwidth_mbps * 1e6)
        propagate = self.rtt_ms / 1000.0
        return max(transmit, propagate)


@dataclass
class BottleneckLink:
    name: str
    capacity_mbps: float
    current_load_mbps: float = 0.0

    def utilization(self) -> float:
        return self.current_load_mbps / self.capacity_mbps if self.capacity_mbps > 0 else 0.0


def find_bottleneck(links: list[BottleneckLink]) -> BottleneckLink:
    return max(links, key=lambda l: l.utilization())


@dataclass
class CongestionCollapseSim:
    capacity: float
    retransmit_prob: float = 0.0

    def goodput(self, offered_load: float) -> float:
        """Goodput as a function of offered load.

        Below capacity, goodput = offered load.
        Above capacity, packets queue and some are retransmitted (wasted),
        causing goodput to drop -- congestion collapse.
        """
        if offered_load <= self.capacity:
            return offered_load
        excess = offered_load - self.capacity
        wasted = excess * (0.5 + self.retransmit_prob)
        return max(0.0, self.capacity - wasted * 0.3)

    def delay(self, offered_load: float) -> float:
        """Delay grows as 1/(1-load) near capacity (queueing theory)."""
        rho = min(offered_load / self.capacity, 0.99)
        base = 1.0
        return base / (1.0 - rho)


@dataclass
class JitterMeasurement:
    delays: list[float] = field(default_factory=list)

    def add_sample(self, delay_ms: float) -> None:
        self.delays.append(delay_ms)

    def mean(self) -> float:
        return sum(self.delays) / len(self.delays) if self.delays else 0.0

    def jitter(self) -> float:
        if len(self.delays) < 2:
            return 0.0
        diffs = [abs(self.delays[i] - self.delays[i-1]) for i in range(1, len(self.delays))]
        return sum(diffs) / len(diffs)

    def percentile(self, p: float) -> float:
        if not self.delays:
            return 0.0
        s = sorted(self.delays)
        idx = int(len(s) * p / 100.0)
        return s[min(idx, len(s) - 1)]


def throughput_vs_loss_rate(rtt_ms: float, mss: int, loss_rate: float) -> float:
    """Padhye model: throughput ~ MSS / (RTT * sqrt(loss_rate))."""
    if loss_rate <= 0 or loss_rate >= 1:
        return float("inf") if loss_rate <= 0 else 0.0
    return mss * 8 / (rtt_ms / 1000.0 * (loss_rate ** 0.5)) / 1e6


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    random.seed(99)
    print("=" * 70)
    print("Bandwidth-Delay Product for Various Network Paths")
    print("=" * 70)
    paths = [
        NetworkPath("Local Ethernet", 1000, 0.1),
        NetworkPath("Transcontinental Fiber", 1000, 40),
        NetworkPath("OC-12 Transcontinental", 600, 50),
        NetworkPath("Satellite (GEO)", 50, 500),
        NetworkPath("1-Mbps ADSL", 1, 100),
    ]
    print(f"  {'Path':>28}  {'BW(Mbps)':>8}  {'RTT(ms)':>7}  {'BDP(bits)':>12}  {'BDP(pkts)':>9}  {'MinWin':>8}")
    for p in paths:
        bdp_bits = p.bandwidth_delay_product_bits()
        bdp_pkts = p.bdp_in_packets()
        min_win = p.min_window_bytes()
        print(f"  {p.name:>28}  {p.bandwidth_mbps:8.0f}  {p.rtt_ms:7.0f}  {bdp_bits:12.0f}  {bdp_pkts:9.1f}  {min_win:8d}")

    print()
    print("  Key insight: window must be >= BDP to fill the pipe.")
    print("  Standard TCP window (64KB) is insufficient for LFNs.")

    print()
    print("=" * 70)
    print("64KB Window Limitation (Fig 6-54 scenario)")
    print("=" * 70)
    p = NetworkPath("1-Gbps transcontinental", 1000, 40)
    throughput_64k = p.max_throughput_with_window(65536)
    print(f"  Path: {p.bandwidth_mbps} Mbps, RTT={p.rtt_ms} ms")
    print(f"  BDP = {p.min_window_bytes()} bytes ({p.bandwidth_delay_product_bits():.0f} bits)")
    print(f"  With 64KB window: throughput = {throughput_64k:.1f} Mbps ({throughput_64k/p.bandwidth_mbps*100:.1f}% util)")
    print(f"  With 5MB window:  throughput = {p.max_throughput_with_window(5*1024*1024):.1f} Mbps")
    print(f"  Efficiency of 64KB window = 65536/{p.min_window_bytes()} = {65536/p.min_window_bytes()*100:.1f}%")

    print()
    print("=" * 70)
    print("File Transfer Time: Delay-Limited vs Bandwidth-Limited (Fig 6-55)")
    print("=" * 70)
    file_size = 1_000_000
    speeds = [(1, "1 Mbps"), (10, "10 Mbps"), (100, "100 Mbps"), (1000, "1 Gbps"), (10000, "10 Gbps")]
    print(f"  Transfer 1 Mbit over 4000 km (~40ms RTT):")
    print(f"  {'Speed':>12}  {'Transmit':>10}  {'RTT':>8}  {'Total':>8}  {'Bottleneck':>12}")
    for bw_mbps, label in speeds:
        p2 = NetworkPath(label, bw_mbps, 40)
        t = p2.transfer_time(file_size // 8)
        transmit = file_size * 8 / (bw_mbps * 1e6)
        bottleneck = "RTT" if p2.rtt_ms / 1000.0 > transmit else "bandwidth"
        print(f"  {label:>12}  {transmit:10.4f}s  {p2.rtt_ms:7.0f}ms  {t:8.4f}s  {bottleneck:>12}")
    print()
    print("  At 1 Gbps+, the 40ms RTT dominates. Speed-of-light delay is the limit.")

    print()
    print("=" * 70)
    print("Congestion Collapse: Goodput vs Offered Load (Fig 6-19a)")
    print("=" * 70)
    sim = CongestionCollapseSim(capacity=100.0, retransmit_prob=0.3)
    loads = [10, 20, 40, 60, 80, 90, 95, 100, 110, 120, 140, 160, 200]
    print(f"  {'Offered':>8}  {'Goodput':>8}  {'Delay':>8}  {'Note':>25}")
    for load in loads:
        gp = sim.goodput(load)
        d = sim.delay(load)
        note = ""
        if load == 100: note = "<-- at capacity"
        if load > 100: note = "<-- collapse (wasted retransmits)"
        if load > 150: note = "<-- severe collapse"
        print(f"  {load:8.0f}  {gp:8.1f}  {d:8.2f}  {note:>25}")

    print()
    print("=" * 70)
    print("Bottleneck Analysis")
    print("=" * 70)
    links = [
        BottleneckLink("Access", 1000, 100),
        BottleneckLink("Core", 10000, 100),
        BottleneckLink("ADSL", 1, 0.8),
        BottleneckLink("Satellite", 50, 10),
    ]
    for l in links:
        print(f"  {l.name:>12}: {l.current_load_mbps:.1f}/{l.capacity_mbps:.0f} Mbps"
              f"  ({l.utilization()*100:.1f}% utilized)")
    bn = find_bottleneck(links)
    print(f"  Bottleneck: {bn.name} at {bn.utilization()*100:.1f}% utilization")

    print()
    print("=" * 70)
    print("Throughput vs Packet Loss (Padhye Model, Sec 6.5.11)")
    print("=" * 70)
    rtt = 100
    mss = 1500
    loss_rates = [0.0001, 0.001, 0.01, 0.02, 0.05, 0.10]
    print(f"  RTT={rtt}ms, MSS={mss}B")
    print(f"  {'Loss Rate':>10}  {'Throughput':>12}  {'Note':>30}")
    for lr in loss_rates:
        tp = throughput_vs_loss_rate(rtt, mss, lr)
        note = ""
        if lr == 0.01: note = "1% = moderate loss"
        if lr == 0.10: note = "10% = connection effectively dead"
        print(f"  {lr:10.4f}  {tp:12.2f} Mbps  {note:>30}")
    print()
    print("  Throughput drops as 1/sqrt(loss_rate). At 1 Gbps, need loss < 2e-8.")
    print("  This is too small for loss-based congestion control at high speeds.")

    print()
    print("=" * 70)
    print("Jitter: High vs Low (Fig 6-33)")
    print("=" * 70)
    low_jitter = JitterMeasurement()
    high_jitter = JitterMeasurement()
    for i in range(20):
        low_jitter.add_sample(100 + random.gauss(0, 2))
        high_jitter.add_sample(100 + random.gauss(0, 30))
    print(f"  Low jitter:  mean={low_jitter.mean():.1f}ms  jitter={low_jitter.jitter():.1f}ms"
          f"  p99={low_jitter.percentile(99):.1f}ms")
    print(f"  High jitter: mean={high_jitter.mean():.1f}ms  jitter={high_jitter.jitter():.1f}ms"
          f"  p99={high_jitter.percentile(99):.1f}ms")
    print()
    print(f"  Playback point for low jitter:  ~{low_jitter.percentile(99):.0f}ms (small buffer)")
    print(f"  Playback point for high jitter: ~{high_jitter.percentile(99):.0f}ms (large buffer)")
    print("  Same average delay, but high jitter needs much larger buffer.")


if __name__ == "__main__":
    main()