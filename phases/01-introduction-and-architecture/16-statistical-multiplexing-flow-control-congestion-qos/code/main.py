"""Statistical Multiplexing, Flow Control, Congestion, and QoS — stdlib model.

Implements the four resource-allocation mechanisms of textbook section 1.3.2:
statistical multiplexing of bursty flows, sliding-window flow control with
sequence numbers mod 2^k, AIMD congestion control, and weighted fair queuing.

Run:    python3 main.py
"""

from __future__ import annotations

import heapq
import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


def statistical_multiplexing(
    num_flows: int,
    link_capacity: int,
    slots: int,
    on_prob: float = 0.1,
    seed: int = 42,
) -> Tuple[int, int, int]:
    """Simulate bursty on/off flows sharing one link.

    Each flow is ON with probability on_prob per slot; when ON it offers one
    packet. The link drains `link_capacity` packets/slot; excess queues up.
    Stat-mux sizes the link for the average (N*on_prob), not the peak (N).
    Returns (offered, carried, max_buffer).
    """
    rng = random.Random(seed)
    buffer = offered = carried = max_buffer = 0
    for _ in range(slots):
        incoming = sum(1 for _ in range(num_flows) if rng.random() < on_prob)
        offered += incoming
        buffer += incoming
        drained = min(buffer, link_capacity)
        buffer -= drained
        carried += drained
        max_buffer = max(max_buffer, buffer)
    return offered, carried, max_buffer


def multiplexing_summary(num_flows: int = 10, on_prob: float = 0.1) -> str:
    peak = num_flows
    avg = num_flows * on_prob
    stat_link = int(round(avg * 1.0))   # size for the average (mux gain)
    peak_link = peak                     # circuit/peak reservation mode
    return "\n".join([
        f"{num_flows} on/off flows, each ON with p={on_prob}",
        f"  peak offered load    = {peak} pkt/slot  (all bursts coincide)",
        f"  average offered load = {avg:.2f} pkt/slot",
        f"  stat-mux link         = {stat_link} pkt/slot (sized for average)",
        f"  peak-reservation link = {peak_link} pkt/slot (sized for peak)",
        f"  bandwidth saving      = {(1 - stat_link / peak_link) * 100:.0f}%",
    ])


@dataclass
class WindowEndpoint:
    """One side of a sliding-window protocol (W <= 2^k - 1 avoids ambiguity)."""
    base: int = 0      # oldest unacknowledged sequence number
    next_seq: int = 0    # next sequence number to send
    window: int = 4      # W: max outstanding (unacked) frames
    modulus: int = 8     # 2^k; sequence numbers are seq mod modulus

    def can_send(self) -> bool:
        return (self.next_seq - self.base) % self.modulus < self.window

    def send(self) -> int:
        if not self.can_send():
            raise StopIteration("window full — must wait for an ACK")
        seq = self.next_seq % self.modulus
        self.next_seq += 1
        return seq

    def receive_ack(self, ack: int) -> None:
        # Cumulative ACK: advance base to ack+1 (forward in-order ACKs only).
        advance = (ack + 1 - self.base) % self.modulus
        if 0 < advance < self.modulus:
            self.base = (ack + 1) % self.modulus

    def in_flight(self) -> int:
        return (self.next_seq - self.base) % self.modulus


def sliding_window_trace(window: int, modulus: int, rwnd_cap: int) -> str:
    """Drive a sliding window, honoring a receiver-advertised rwnd."""
    snd = WindowEndpoint(window=window, modulus=modulus)
    rwnd = rwnd_cap
    out: List[str] = [f"sliding window W={window}, seq space 2^k={modulus}"]
    for tick in range(14):
        snd.window = min(snd.window, rwnd)        # rwnd caps the send window
        line = (f"  t={tick:2d} base={snd.base} next={snd.next_seq % modulus} "
                f"in_flight={snd.in_flight()} rwnd={rwnd}")
        if snd.can_send():
            line += f"  -> SEND seq={snd.send()}"
            # Immediate ACK of what we just sent, then receiver shrinks rwnd.
            snd.receive_ack((snd.next_seq - 1) % snd.modulus)
            rwnd = max(0, rwnd - 1)
        else:
            line += "  -> STALL (window/rwnd full)"
        out.append(line)
    out.append(f"  ambiguity deadlock if W>=2^k? {window >= modulus} "
               f"(W={window}, modulus={modulus})")
    return "\n".join(out)


def aimd_trace(start_cwnd: int, rtts: int, loss_every: int) -> str:
    """Slow start (exp), then additive +1/RTT, multiplicative /2 on loss."""
    cwnd = start_cwnd
    ssthresh = 8
    lines: List[str] = [f"AIMD over {rtts} RTTs (loss every {loss_every} RTT)"]
    for r in range(1, rtts + 1):
        if cwnd < ssthresh:
            cwnd *= 2                 # slow start: exponential growth
        else:
            cwnd += 1                 # congestion avoidance: additive growth
        if r % loss_every == 0:
            ssthresh = max(2, cwnd // 2)   # multiplicative decrease + new ssthresh
            cwnd = ssthresh
            lines.append(f"rtt{r:2d} cwnd={cwnd:2d} |{'#' * cwnd} LOSS (halve)")
            continue
        lines.append(f"rtt{r:2d} cwnd={cwnd:2d} |{'#' * cwnd}")
    lines.append("classic sawtooth: cwnd grows linearly, collapses by half on loss.")
    return "\n".join(lines)


@dataclass(order=True)
class QosPacket:
    finish: float
    seq: int
    flow_id: str = field(compare=False)
    length: int = field(default=1, compare=False)


def weighted_fair_queuing(
    flows: Dict[str, Tuple[int, int]], weights: Dict[str, int]
) -> List[str]:
    """Schedule packets with WFQ.

    flows: flow_id -> (num_packets, packet_length). Virtual finish time
    F = V + len/weight; the flow with smallest F goes next, guaranteeing each
    flow at least its weighted share while leftover bandwidth is reclaimed.
    """
    heap: List[QosPacket] = []
    vtime = 0.0
    cursors = {fid: 0 for fid in flows}

    def enqueue(fid: str, v: float) -> None:
        if cursors[fid] < flows[fid][0]:
            length = flows[fid][1]
            finish = v + length / weights[fid]
            heapq.heappush(heap, QosPacket(finish, len(heap), fid, length))
            cursors[fid] += 1

    out = [f"WFQ schedule (weights: {weights})"]
    for fid in flows:
        enqueue(fid, vtime)

    scheduled: List[str] = []
    while heap:
        pkt = heapq.heappop(heap)
        vtime = pkt.finish
        scheduled.append(pkt.flow_id)
        if cursors[pkt.flow_id] < flows[pkt.flow_id][0]:
            enqueue(pkt.flow_id, vtime)

    out.append("  order: " + " -> ".join(scheduled))
    counts: Dict[str, int] = {fid: scheduled.count(fid) for fid in weights}
    total = sum(counts.values())
    for fid in sorted(weights):
        out.append(
            f"  {fid}: weight={weights[fid]:2d} "
            f"fair_share={weights[fid]/sum(weights.values())*100:3.0f}% "
            f"realized={counts[fid]/total*100:3.0f}%"
        )
    return out


def main() -> None:
    print("=" * 72)
    print("1) STATISTICAL MULTIPLEXING")
    print("=" * 72)
    print(multiplexing_summary(num_flows=10, on_prob=0.1))
    print()
    offered, carried, maxbuf = statistical_multiplexing(
        num_flows=10, link_capacity=1, slots=10_000, on_prob=0.1)
    print(f"  link sized for avg ~1/slot over 10000 slots: "
          f"offered={offered} carried={carried} ({carried/offered*100:.1f}%) "
          f"max_buffer={maxbuf}\n")

    print("=" * 72)
    print("2) SLIDING-WINDOW FLOW CONTROL")
    print("=" * 72)
    print(sliding_window_trace(window=4, modulus=8, rwnd_cap=4))
    print()
    print("  note: if W==2^k (e.g. W=8, modulus=8) a cumulative ACK cannot")
    print("  tell 'all 8 acked' from 'none acked' -> the sequence deadlock.\n")

    print("=" * 72)
    print("3) CONGESTION CONTROL (AIMD sawtooth)")
    print("=" * 72)
    print(aimd_trace(start_cwnd=1, rtts=20, loss_every=7))
    print()

    print("=" * 72)
    print("4) QUALITY OF SERVICE (Weighted Fair Queuing)")
    print("=" * 72)
    wfq = weighted_fair_queuing(
        flows={"video": (12, 2), "bulk": (20, 1), "voice": (8, 1)},
        weights={"video": 4, "bulk": 1, "voice": 2})
    for line in wfq:
        print("  " + line)
    print()


if __name__ == "__main__":
    main()
