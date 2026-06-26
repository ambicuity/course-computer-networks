#!/usr/bin/env python3
"""High Latency Video Call to Intermittent Wi-Fi Loss (Integrated Lab 03).

Simulates four failure classes that all produce "video call quality is bad"
and walks a four-step diagnostic chain for each:

  bufferbloat     - standing queue delay on the WAN egress
  rf_interference - 802.11 retransmits from co-channel interference
  roaming         - 802.11r fast-transition blips from misconfigured mobility domain
  codec           - jitter buffer and PLC misconfiguration (network is healthy)

Run:  python3 main.py [--mode bufferbloat|rf_interference|roaming|codec|all]
"""
from __future__ import annotations

import argparse
import enum
import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Iterable


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------
class FailureMode(str, enum.Enum):
    BUFFERBLOAT = "bufferbloat"
    RF_INTERFERENCE = "rf_interference"
    ROAMING = "roaming"
    CODEC = "codec"


# ---------------------------------------------------------------------------
# Synthetic packet trace
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class PacketSample:
    seq: int
    send_ms: float
    recv_ms: float
    lost: bool
    wifi_retries: int


@dataclass
class Trace:
    samples: list[PacketSample] = field(default_factory=list)

    def lost_count(self) -> int:
        return sum(1 for s in self.samples if s.lost)

    def total_count(self) -> int:
        return len(self.samples)

    def loss_pct(self) -> float:
        if not self.samples:
            return 0.0
        return 100.0 * self.lost_count() / self.total_count()

    def jitter_ms(self) -> float:
        if len(self.samples) < 2:
            return 0.0
        arrivals = [s.recv_ms for s in self.samples if not s.lost]
        if len(arrivals) < 2:
            return 0.0
        deltas = [arrivals[i] - arrivals[i - 1]
                  for i in range(1, len(arrivals))]
        deviations = [abs(d - 20.0) for d in deltas]
        return statistics.pstdev(deviations) if len(deviations) > 1 else 0.0

    def one_way_delay_ms(self) -> float:
        if not self.samples:
            return 0.0
        return statistics.mean(s.recv_ms - s.send_ms
                               for s in self.samples if not s.lost)

    def p99_one_way_delay_ms(self) -> float:
        delays = sorted(s.recv_ms - s.send_ms
                        for s in self.samples if not s.lost)
        if not delays:
            return 0.0
        idx = max(0, int(math.ceil(0.99 * len(delays))) - 1)
        return delays[idx]

    def total_wifi_retries(self) -> int:
        return sum(s.wifi_retries for s in self.samples)

    def blip_count(self, threshold_ms: float = 100.0) -> int:
        return sum(1 for s in self.samples
                   if (s.recv_ms - s.send_ms) > threshold_ms)


def gen_bufferbloat_trace(seed: int = 1) -> Trace:
    """Standing queue delay on a 50 Mbps WAN with 200-packet queue."""
    rng = random.Random(seed)
    t = Trace()
    for seq in range(600):
        in_bulk = 100 <= seq < 500
        if in_bulk:
            base = 8.0 + 240.0
        else:
            base = 8.0
        recv_delay = base + rng.gauss(0, 2.0)
        lost = rng.random() < 0.001
        t.samples.append(PacketSample(
            seq=seq, send_ms=seq * 20.0, recv_ms=seq * 20.0 + recv_delay,
            lost=lost, wifi_retries=0,
        ))
    return t


def gen_rf_interference_trace(seed: int = 2) -> Trace:
    """Co-channel interference: 25% of frames need 1-3 retries; some fail."""
    rng = random.Random(seed)
    t = Trace()
    for seq in range(600):
        r = rng.random()
        if r < 0.25:
            retries = rng.randint(1, 3)
            extra = retries * rng.uniform(4.0, 12.0)
        else:
            retries = 0
            extra = rng.gauss(5.0, 1.0)
        lost = rng.random() < 0.05
        t.samples.append(PacketSample(
            seq=seq, send_ms=seq * 20.0,
            recv_ms=seq * 20.0 + extra, lost=lost, wifi_retries=retries,
        ))
    return t


def gen_roaming_trace(seed: int = 3) -> Trace:
    """Periodically the client roams and loses ~500 ms of traffic."""
    rng = random.Random(seed)
    t = Trace()
    roam_starts = {120, 240, 360, 480}
    in_roam_until = -1
    for seq in range(600):
        if seq in roam_starts:
            in_roam_until = seq + 25
        if seq < in_roam_until:
            t.samples.append(PacketSample(
                seq=seq, send_ms=seq * 20.0, recv_ms=seq * 20.0,
                lost=True, wifi_retries=0,
            ))
        else:
            jitter = rng.gauss(0, 2.0)
            t.samples.append(PacketSample(
                seq=seq, send_ms=seq * 20.0,
                recv_ms=seq * 20.0 + 6.0 + jitter,
                lost=False, wifi_retries=0,
            ))
    return t


def gen_codec_trace(seed: int = 4) -> Trace:
    """Healthy network, but the softphone's jitter buffer is misconfigured."""
    rng = random.Random(seed)
    t = Trace()
    for seq in range(600):
        jitter = rng.gauss(0, 1.5)
        t.samples.append(PacketSample(
            seq=seq, send_ms=seq * 20.0,
            recv_ms=seq * 20.0 + 5.0 + jitter, lost=False, wifi_retries=0,
        ))
    return t


# ---------------------------------------------------------------------------
# Four-step diagnostic chain
# ---------------------------------------------------------------------------
@dataclass
class DiagResult:
    step: int
    name: str
    finding: str
    healthy: bool
    layer: str
    decisive: bool


def measure_iperf(trace: Trace) -> DiagResult:
    loss = trace.loss_pct()
    jitter = trace.jitter_ms()
    healthy = loss < 0.5 and jitter < 10.0
    decisive = not healthy
    if healthy:
        finding = f"loss={loss:.2f}%, jitter={jitter:.2f} ms (healthy)"
        layer = "L1-L2 OK; keep going"
    elif jitter > 30.0 and loss < 5.0:
        finding = (f"loss={loss:.2f}%, jitter={jitter:.2f} ms "
                   f"(high jitter, low loss -> queue)")
        layer = "L2/L3 queue"
    else:
        finding = (f"loss={loss:.2f}%, jitter={jitter:.2f} ms "
                   f"(high loss -> RF or link)")
        layer = "L2 RF or L1"
    return DiagResult(1, "iperf3 -u -b 5M -t 30 -c <gw> -J",
                       finding, healthy, layer, decisive)


def measure_rtt_idle_vs_loaded(trace: Trace) -> DiagResult:
    idle_samples = [s for s in trace.samples
                    if not s.lost and s.seq < 100]
    loaded_samples = [s for s in trace.samples
                      if not s.lost and 200 <= s.seq < 400]
    if not idle_samples or not loaded_samples:
        idle = loaded = 0.0
    else:
        idle = statistics.mean(s.recv_ms - s.send_ms for s in idle_samples)
        loaded = statistics.mean(s.recv_ms - s.send_ms for s in loaded_samples)
    delta = loaded - idle
    healthy = delta < 50.0
    decisive = not healthy
    if healthy:
        finding = f"idle={idle:.1f}ms, loaded={loaded:.1f}ms, delta={delta:.1f}ms (healthy)"
        layer = "queue OK; keep going"
    else:
        finding = f"idle={idle:.1f}ms, loaded={loaded:.1f}ms, delta={delta:.1f}ms (bufferbloat)"
        layer = "L3 queue (bufferbloat)"
    return DiagResult(2, "ping (idle vs loaded)", finding, healthy, layer, decisive)


def measure_rf_retransmits(trace: Trace) -> DiagResult:
    total = trace.total_count()
    retries = trace.total_wifi_retries()
    ratio = (retries / total) if total > 0 else 0.0
    healthy = ratio < 0.05
    decisive = not healthy
    if healthy:
        finding = f"tx_retries/tx_packets={ratio:.3f} (healthy)"
        layer = "RF OK; keep going"
    else:
        finding = f"tx_retries/tx_packets={ratio:.3f} (RF problem)"
        layer = "L2 RF interference / distance"
    return DiagResult(3, "iw dev wlan0 station dump",
                       finding, healthy, layer, decisive)


def measure_codec(trace: Trace) -> DiagResult:
    if trace.loss_pct() < 0.1 and trace.jitter_ms() < 3.0:
        return DiagResult(4, "softphone MOS / PLC log",
                           "network clean; app reports MOS=3.2, PLC events spiking",
                           healthy=False, layer="L7 codec / jitter buffer",
                           decisive=True)
    return DiagResult(4, "softphone MOS / PLC log",
                       "network anomalies - app behavior secondary",
                       healthy=True, layer="L7", decisive=False)


def run_diag(mode: FailureMode, trace: Trace) -> list[DiagResult]:
    return [measure_iperf(trace),
            measure_rtt_idle_vs_loaded(trace),
            measure_rf_retransmits(trace),
            measure_codec(trace)]


# ---------------------------------------------------------------------------
# Presentation
# ---------------------------------------------------------------------------
def render(mode: FailureMode, trace: Trace, results: list[DiagResult]) -> None:
    print("=" * 78)
    print(f"High-Latency Video Call Diagnostic  [mode={mode.value}]")
    print("=" * 78)
    print(f"  packets:    {trace.total_count()}")
    print(f"  loss:       {trace.loss_pct():.2f}%")
    print(f"  jitter:     {trace.jitter_ms():.2f} ms")
    print(f"  one-way:    {trace.one_way_delay_ms():.1f} ms (mean), "
          f"{trace.p99_one_way_delay_ms():.1f} ms (p99)")
    print(f"  wifi ret:   {trace.total_wifi_retries()}")
    print()
    print(f"{'#':<3}  {'finding':<60}  decisive?  layer")
    print("-" * 78)
    for r in results:
        first_line = r.finding[:58]
        marker = "YES" if r.decisive else "no"
        print(f"{r.step:<3}  {first_line:<60}  {marker:<9}  {r.layer}")
    print()
    decisive = next((r for r in results if r.decisive), None)
    if decisive:
        print(f"  First decisive evidence: step {decisive.step} ({decisive.name})")
        print(f"  Layer:                    {decisive.layer}")
        print(f"  Verdict:                  {decisive.finding}")
    else:
        print("  No decisive evidence in chain; deeper inspection needed.")


def main(argv: Iterable[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", default="all",
                    choices=[m.value for m in FailureMode] + ["all"])
    args = ap.parse_args(list(argv) if argv is not None else None)

    factories = {
        FailureMode.BUFFERBLOAT: gen_bufferbloat_trace,
        FailureMode.RF_INTERFERENCE: gen_rf_interference_trace,
        FailureMode.ROAMING: gen_roaming_trace,
        FailureMode.CODEC: gen_codec_trace,
    }
    modes = (list(FailureMode) if args.mode == "all"
             else [FailureMode(args.mode)])
    for mode in modes:
        trace = factories[mode]()
        results = run_diag(mode, trace)
        render(mode, trace, results)
        print()


if __name__ == "__main__":
    main()
