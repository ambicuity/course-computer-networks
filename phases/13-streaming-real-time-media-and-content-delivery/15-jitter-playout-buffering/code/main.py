"""Jitter and Playout Buffering.

A stdlib-only simulation of a playout (jitter) buffer for real-time
media. Demonstrates fixed and adaptive playout delay, late-packet
loss, buffer occupancy, and the latency-vs-loss tradeoff.

Run:  python3 main.py
Exit: 0
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

NUM_PACKETS = 100
FRAME_DURATION_MS = 20  # 20ms per packet (50 pkts/sec)
BASE_DELAY_MS = 30
JITTER_MEAN_MS = 0  # delay variation mean
JITTER_STD_MS = 15


@dataclass
class Packet:
    """An RTP-like packet with sequence number, send time, and arrival time."""
    seq: int
    send_time_ms: float
    arrival_time_ms: float
    played: bool = False
    late: bool = False
    buffer_wait_ms: float = 0.0


def generate_packets(n: int, base_delay: float, jitter_std: float) -> List[Packet]:
    """Generate n packets with variable network delay (jitter)."""
    packets: List[Packet] = []
    for i in range(n):
        send_time = i * FRAME_DURATION_MS
        delay = base_delay + random.gauss(0, jitter_std)
        delay = max(5, delay)  # no negative delays
        # Occasionally inject a big delay spike
        if random.random() < 0.05:
            delay += random.uniform(50, 150)
        arrival = send_time + delay
        packets.append(Packet(seq=i, send_time_ms=send_time, arrival_time_ms=arrival))
    return packets


def simulate_fixed_playout(
    packets: List[Packet], playout_delay_ms: float
) -> Tuple[int, int, List[float]]:
    """Simulate a fixed-delay playout buffer. Returns (played, late, buffer_occupancy)."""
    played = 0
    late = 0
    occupancy: List[float] = []

    first_arrival = packets[0].arrival_time_ms if packets else 0
    base_playout = first_arrival + playout_delay_ms

    for pkt in packets:
        playout_time = base_playout + pkt.seq * FRAME_DURATION_MS
        if pkt.arrival_time_ms > playout_time:
            pkt.late = True
            late += 1
        else:
            pkt.played = True
            pkt.buffer_wait_ms = playout_time - pkt.arrival_time_ms
            played += 1
        # Track buffer occupancy (packets waiting)
        waiting = sum(1 for p in packets if p.arrival_time_ms <= playout_time and not p.played and p.seq <= pkt.seq)
        occupancy.append(pkt.buffer_wait_ms)
    return (played, late, occupancy)


def simulate_adaptive_playout(
    packets: List[Packet], initial_delay: float
) -> Tuple[int, int, List[float]]:
    """Simulate adaptive playout delay that tracks jitter. Returns (played, late, delays)."""
    played = 0
    late = 0
    delays: List[float] = []

    avg_delay = initial_delay
    var_delay = 10.0

    first_arrival = packets[0].arrival_time_ms if packets else 0
    current_playout_delay = initial_delay
    base_playout = first_arrival + current_playout_delay

    for i, pkt in enumerate(packets):
        # Update delay estimate (EWMA)
        measured_delay = pkt.arrival_time_ms - pkt.send_time_ms
        avg_delay = 0.9 * avg_delay + 0.1 * measured_delay
        var_delay = 0.9 * var_delay + 0.1 * abs(measured_delay - avg_delay)

        # Adapt playout delay: average + 4 * deviation
        target_delay = avg_delay + 4 * var_delay
        current_playout_delay = max(20, min(300, target_delay))
        delays.append(current_playout_delay)

        # Adjust base playout (simulating talkspurt boundary every 10 packets)
        if i % 10 == 0 and i > 0:
            base_playout = pkt.arrival_time_ms + current_playout_delay

        playout_time = base_playout + (pkt.seq - (i // 10) * 10 + (i // 10) * 10) * FRAME_DURATION_MS
        # Simplified: use packet's expected playout relative to its group
        playout_time = base_playout + (pkt.seq % 10) * FRAME_DURATION_MS if i % 10 == 0 else base_playout + (pkt.seq % 10) * FRAME_DURATION_MS

        if pkt.arrival_time_ms > playout_time:
            pkt.late = True
            late += 1
        else:
            pkt.played = True
            pkt.buffer_wait_ms = playout_time - pkt.arrival_time_ms
            played += 1

    return (played, late, delays)


def main() -> None:
    print("Jitter and Playout Buffering\n")
    print(f"Packets: {NUM_PACKETS}, frame: {FRAME_DURATION_MS}ms")
    print(f"Base delay: {BASE_DELAY_MS}ms, jitter std: {JITTER_STD_MS}ms\n")
    random.seed(99)

    # Generate packets with jitter
    packets = generate_packets(NUM_PACKETS, BASE_DELAY_MS, JITTER_STD_MS)

    print("=== Network Delay Statistics ===")
    delays = [p.arrival_time_ms - p.send_time_ms for p in packets]
    avg_delay = sum(delays) / len(delays)
    min_delay = min(delays)
    max_delay = max(delays)
    delay_var = sum((d - avg_delay) ** 2 for d in delays) / len(delays)
    delay_std = delay_var ** 0.5
    print(f"  Average delay:  {avg_delay:.1f} ms")
    print(f"  Min delay:      {min_delay:.1f} ms")
    print(f"  Max delay:      {max_delay:.1f} ms")
    print(f"  Delay std dev:  {delay_std:.1f} ms (jitter)")
    print()

    # Trace first 15 packets
    print("=== Packet Trace (first 15) ===")
    print(f"  {'seq':>3}  {'send':>7}  {'arrival':>7}  {'delay':>7}  {'status':>8}")
    print("  " + "-" * 40)
    for pkt in packets[:15]:
        delay = pkt.arrival_time_ms - pkt.send_time_ms
        print(f"  {pkt.seq:3d}  {pkt.send_time_ms:7.1f}  {pkt.arrival_time_ms:7.1f}  {delay:7.1f}  {'sent':>8}")
    print()

    # Fixed playout delay sweep
    print("=== Fixed Playout Delay Sweep ===")
    print(f"  {'delay_ms':>9}  {'played':>7}  {'late':>5}  {'loss%':>6}  {'latency':>8}")
    print("  " + "-" * 50)
    best_delay = 0
    best_score = float("inf")
    for pd in [20, 40, 60, 80, 100, 120, 150, 200]:
        pkts_copy = generate_packets(NUM_PACKETS, BASE_DELAY_MS, JITTER_STD_MS)
        random.seed(99)  # same network conditions
        pkts_copy = [Packet(seq=p.seq, send_time_ms=p.send_time_ms, arrival_time_ms=p.arrival_time_ms)
                     for p in packets]
        played, late, _ = simulate_fixed_playout(pkts_copy, float(pd))
        loss_pct = late / NUM_PACKETS * 100
        # Score: weighted sum of latency and loss
        score = pd + loss_pct * 10
        if score < best_score:
            best_score = score
            best_delay = pd
        print(f"  {pd:9d}  {played:7d}  {late:5d}  {loss_pct:6.1f}  {pd:8d}ms")
    print(f"\n  Optimal fixed delay: {best_delay}ms (score: {best_score:.1f})")
    print()

    # Detailed fixed playout at optimal delay
    print(f"=== Detailed Fixed Playout (delay={best_delay}ms, first 20 packets) ===")
    pkts_detail = [Packet(seq=p.seq, send_time_ms=p.send_time_ms, arrival_time_ms=p.arrival_time_ms)
                   for p in packets]
    played, late, occupancy = simulate_fixed_playout(pkts_detail, float(best_delay))
    print(f"  {'seq':>3}  {'arrival':>7}  {'playout':>7}  {'wait':>7}  {'status':>8}")
    print("  " + "-" * 45)
    first_arrival = pkts_detail[0].arrival_time_ms
    base_pl = first_arrival + best_delay
    for pkt in pkts_detail[:20]:
        pt = base_pl + pkt.seq * FRAME_DURATION_MS
        status = "LATE" if pkt.late else "OK"
        wait = pt - pkt.arrival_time_ms
        print(f"  {pkt.seq:3d}  {pkt.arrival_time_ms:7.1f}  {pt:7.1f}  {wait:7.1f}  {status:>8}")
    print(f"\n  Total: played={played}, late={late}, loss={late/NUM_PACKETS*100:.1f}%")
    print()

    # Adaptive playout
    print("=== Adaptive Playout Delay ===")
    pkts_adapt = [Packet(seq=p.seq, send_time_ms=p.send_time_ms, arrival_time_ms=p.arrival_time_ms)
                  for p in packets]
    played_a, late_a, delays_a = simulate_adaptive_playout(pkts_adapt, 60.0)
    avg_adapt_delay = sum(delays_a) / len(delays_a)
    print(f"  Played: {played_a}, Late: {late_a}, Loss: {late_a/NUM_PACKETS*100:.1f}%")
    print(f"  Average adaptive delay: {avg_adapt_delay:.1f}ms")
    print(f"  Delay range: {min(delays_a):.1f} - {max(delays_a):.1f}ms")
    print()

    # Adaptive delay trace
    print("  Adaptive delay over time (every 10th packet):")
    for i in range(0, NUM_PACKETS, 10):
        bar = "#" * int(delays_a[i] / 5)
        print(f"    pkt {i:3d}: {delays_a[i]:6.1f}ms {bar}")
    print()

    # Comparison
    print("=== Fixed vs Adaptive Comparison ===")
    print(f"  {'metric':>15}  {'fixed':>8}  {'adaptive':>10}")
    print(f"  {'played':>15}  {played:8d}  {played_a:10d}")
    print(f"  {'late':>15}  {late:8d}  {late_a:10d}")
    print(f"  {'loss%':>15}  {late/NUM_PACKETS*100:8.1f}  {late_a/NUM_PACKETS*100:10.1f}")
    print(f"  {'avg delay':>15}  {best_delay:8d}  {avg_adapt_delay:10.1f}")
    print()

    print("Key observations:")
    print("  - Larger playout delay reduces late loss but increases latency")
    print("  - Adaptive delay tracks jitter, shrinking when network is stable")
    print("  - Optimal fixed delay balances latency and loss tradeoff")
    print("  - 5% delay spikes cause most late losses at low delay settings")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
