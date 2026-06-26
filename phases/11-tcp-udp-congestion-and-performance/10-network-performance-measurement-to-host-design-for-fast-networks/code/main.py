#!/usr/bin/env python3
"""Network performance measurement toolkit and host design factors.

Stdlib only. Demonstrates Sec 6.6.2-6.6.3:

1. Bandwidth measurement via packet pairs (spacing of acks reveals
   bottleneck bandwidth).
2. RTT measurement with EWMA (Exponentially Weighted Moving Average)
   smoothing, the same technique used by TCP's SRTT estimator.
3. Measurement pitfalls: sample size, caching, coarse clocks, and
   buffering effects (from Mogul 1993).
4. Host design factors: interrupt coalescing, zero-copy, context-switch
   counting, and the rule that host speed matters more than network speed.

Run:  python3 main.py
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Part 1: Bandwidth measurement via packet pairs
# ---------------------------------------------------------------------------

@dataclass
class PacketPairMeasurement:
    bottleneck_bw_mbps: float

    def send_pair(self, pkt_size: int = 1500) -> tuple[float, float]:
        """Simulate sending two back-to-back packets through a bottleneck.

        The spacing at the receiver reveals the bottleneck bandwidth:
        delta_t = pkt_size / bottleneck_bw
        """
        spacing_s = (pkt_size * 8) / (self.bottleneck_bw_mbps * 1e6)
        jitter = random.gauss(0, spacing_s * 0.05)
        return 0.0, spacing_s + jitter

    def estimate_bandwidth(self, pkt_size: int, num_samples: int = 100) -> float:
        estimates: list[float] = []
        for _ in range(num_samples):
            _, delta = self.send_pair(pkt_size)
            if delta > 0:
                bw = (pkt_size * 8) / delta / 1e6
                estimates.append(bw)
        estimates.sort()
        mid = len(estimates) // 2
        return estimates[mid] if estimates else 0.0


# ---------------------------------------------------------------------------
# Part 2: RTT measurement with EWMA smoothing
# ---------------------------------------------------------------------------

@dataclass
class RTTSmoother:
    alpha: float = 0.125
    srtt: float = 0.0
    min_samples: int = 10
    _count: int = 0

    def sample(self, r: float) -> float:
        if self._count == 0:
            self.srtt = r
        else:
            self.srtt = self.alpha * r + (1 - self.alpha) * self.srtt
        self._count += 1
        return self.srtt

    def ready(self) -> bool:
        return self._count >= self.min_samples


@dataclass
class BandwidthEstimator:
    alpha: float = 0.1
    estimate: float = 0.0
    _count: int = 0

    def sample(self, bw: float) -> float:
        if self._count == 0:
            self.estimate = bw
        else:
            self.estimate = self.alpha * bw + (1 - self.alpha) * self.estimate
        self._count += 1
        return self.estimate


# ---------------------------------------------------------------------------
# Part 3: Measurement pitfalls
# ---------------------------------------------------------------------------

@dataclass
class MeasurementPitfalls:
    @staticmethod
    def small_sample_error(values: list[float]) -> tuple[float, float]:
        """Show how small samples have high uncertainty."""
        n = len(values)
        mean = sum(values) / n
        var = sum((v - mean) ** 2 for v in values) / max(n - 1, 1)
        std = var ** 0.5
        ci = 1.96 * std / (n ** 0.5)
        return mean, ci

    @staticmethod
    def cache_effect(cached: bool) -> float:
        return 0.001 if cached else 50.0

    @staticmethod
    def coarse_clock(true_us: float, clock_resolution_ms: float = 1.0) -> float:
        """Simulate coarse clock: sub-resolution events read as 0 or resolution."""
        res_us = clock_resolution_ms * 1000
        ticks = round(true_us / res_us)
        return ticks * res_us

    @staticmethod
    def buffering_effect(send_calls: int, buffer_capacity: int) -> dict[str, int]:
        """Show how kernel buffering inflates apparent UDP throughput."""
        accepted = 0
        for i in range(send_calls):
            if i < buffer_capacity:
                accepted += 1
        return {"calls": send_calls, "accepted_by_kernel": accepted, "actually_sent": min(accepted, buffer_capacity)}


# ---------------------------------------------------------------------------
# Part 4: Host design factors
# ---------------------------------------------------------------------------

@dataclass
class HostDesign:
    cpu_mips: float = 3000
    nic_speed_gbps: float = 1.0
    interrupt_coalesce_count: int = 1
    zero_copy: bool = False
    context_switches_per_pkt: int = 4

    def per_packet_overhead_us(self) -> float:
        base = 5.0
        if not self.zero_copy:
            base += 10.0
        base += self.context_switches_per_pkt * 2.0
        return base

    def max_pps(self) -> float:
        overhead = self.per_packet_overhead_us()
        return 1e6 / overhead

    def max_throughput_mbps(self, pkt_size: int = 1500) -> float:
        pps = self.max_pps()
        wire_pps = (self.nic_speed_gbps * 1e9) / (pkt_size * 8)
        effective_pps = min(pps, wire_pps) / self.interrupt_coalesce_count * self.interrupt_coalesce_count
        return min(effective_pps * pkt_size * 8 / 1e6, self.nic_speed_gbps * 1000)


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    random.seed(7)
    print("=" * 70)
    print("Bandwidth Measurement: Packet Pair Method")
    print("=" * 70)
    pp = PacketPairMeasurement(bottleneck_bw_mbps=10.0)
    print(f"  True bottleneck bandwidth: {pp.bottleneck_bw_mbps} Mbps")
    print(f"  {'Sample':>6}  {'Delta(us)':>10}  {'Est(Bps)':>10}")
    for i in range(10):
        _, delta = pp.send_pair(1500)
        est = (1500 * 8) / delta / 1e6 if delta > 0 else 0
        print(f"  {i+1:6d}  {delta*1e6:10.1f}  {est:10.2f}")
    median_est = pp.estimate_bandwidth(1500, 200)
    print(f"  Median estimate over 200 samples: {median_est:.2f} Mbps")

    print()
    print("=" * 70)
    print("RTT Measurement: EWMA Smoothing (TCP SRTT)")
    print("=" * 70)
    smoother = RTTSmoother(alpha=0.125)
    true_rtt = 30.0
    samples = [true_rtt + random.gauss(0, 5) for _ in range(20)]
    print(f"  True RTT = {true_rtt}ms, noise std = 5ms, alpha = {smoother.alpha}")
    print(f"  {'Sample':>6}  {'Raw(ms)':>8}  {'SRTT(ms)':>8}")
    for i, s in enumerate(samples[:10]):
        smoothed = smoother.sample(s)
        print(f"  {i+1:6d}  {s:8.2f}  {smoothed:8.2f}")
    for s in samples[10:]:
        smoother.sample(s)
    print(f"  After 20 samples: SRTT = {smoother.srtt:.2f}ms (true = {true_rtt}ms)")
    print(f"  EWMA filters noise; alpha=0.125 weights new sample as 1/8.")

    print()
    print("=" * 70)
    print("Measurement Pitfalls (Mogul 1993)")
    print("=" * 70)
    mp = MeasurementPitfalls()

    print("\n  1. Sample Size Too Small:")
    small = [random.gauss(50, 10) for _ in range(5)]
    large = [random.gauss(50, 10) for _ in range(1000)]
    m1, ci1 = mp.small_sample_error(small)
    m2, ci2 = mp.small_sample_error(large)
    print(f"     5 samples:   mean={m1:.2f} +/- {ci1:.2f} (95% CI)")
    print(f"     1000 samples: mean={m2:.2f} +/- {ci2:.2f} (95% CI)")

    print("\n  2. Caching Wreaks Havoc:")
    print(f"     First fetch (network): {mp.cache_effect(False):.0f}ms")
    print(f"     Second fetch (cached): {mp.cache_effect(True):.0f}ms")
    print(f"     Repeating measurement returns cache hit, not network time!")

    print("\n  3. Coarse Clock Resolution:")
    true_times = [0.3, 0.5, 0.8, 1.2, 0.1]
    print(f"     True(us):  {true_times}")
    coarse = [mp.coarse_clock(t, 1.0) for t in true_times]
    print(f"     1ms clock: {coarse}")
    print(f"     Single measurement is 0 or 1000us. Must average many samples.")

    print("\n  4. Buffering Inflates Apparent UDP Throughput:")
    buf = mp.buffering_effect(1000, 100)
    print(f"     1000 send() calls, kernel buffer=100: {buf}")
    print(f"     App sees 1000 'sent' but only 100 hit the wire immediately.")

    print()
    print("=" * 70)
    print("Host Design for Fast Networks (Sec 6.6.3)")
    print("=" * 70)
    configs = [
        HostDesign(cpu_mips=3000, nic_speed_gbps=1, interrupt_coalesce_count=1, zero_copy=False, context_switches_per_pkt=4),
        HostDesign(cpu_mips=3000, nic_speed_gbps=1, interrupt_coalesce_count=8, zero_copy=False, context_switches_per_pkt=4),
        HostDesign(cpu_mips=3000, nic_speed_gbps=1, interrupt_coalesce_count=8, zero_copy=True, context_switches_per_pkt=2),
        HostDesign(cpu_mips=3000, nic_speed_gbps=10, interrupt_coalesce_count=16, zero_copy=True, context_switches_per_pkt=1),
    ]
    labels = ["Baseline (1Gbps)", "+Int. Coalesce(8)", "+Zero-copy+fewer ctx", "10Gbps optimized"]
    print(f"  {'Config':>25}  {'Overhead(us)':>12}  {'Max PPS':>10}  {'Max Mbps':>9}")
    for cfg, label in zip(configs, labels):
        print(f"  {label:>25}  {cfg.per_packet_overhead_us():12.1f}  {cfg.max_pps():10.0f}  {cfg.max_throughput_mbps():9.0f}")

    print()
    print("  Rules of thumb (Mogul/Metcalfe):")
    print("  1. Host speed matters more than network speed (software overhead dominates)")
    print("  2. Reduce packet count to reduce overhead (use large segments)")
    print("  3. Minimize data touching (avoid copies; use zero-copy)")
    print("  4. Minimize context switches (kernel-level protocol processing)")
    print("  5. Avoid congestion (prevention > recovery)")
    print("  6. Avoid timeouts (conservative RTO prevents spurious retransmits)")


if __name__ == "__main__":
    main()