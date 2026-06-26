#!/usr/bin/env python3
"""FIFO vs strict-priority vs WFQ scheduler simulator.

Compares per-flow delay and throughput for the same input trace hitting
one 10 Mbps output link. Run:  python3 main.py
"""

from dataclasses import dataclass, field
from typing import NamedTuple

LESSON = "Packet Scheduling to Admission Control"

LINK_BPS = 10_000_000  # 10 Mbps output link


class Flow(NamedTuple):
    fid: str
    label: str
    priority: int   # 0 = highest
    weight: float   # WFQ weight


FLOWS = {
    "voice": Flow("voice", "VoIP", 0, 8.0),
    "video": Flow("video", "Video", 1, 4.0),
    "bulk":  Flow("bulk",  "FTP",  2, 1.0),
}


@dataclass(frozen=True)
class Packet:
    pid: int
    flow: str
    arrival: float   # seconds
    length: int      # bytes
    seq_in_flow: int = 0


@dataclass
class SentPacket:
    pid: int
    flow: str
    arrival: float
    finish: float
    length: int

    @property
    def delay(self) -> float:
        return self.finish - self.arrival


# ---------------------------------------------------------------------------
# Build a deterministic trace: three flows, bulk burst lands first under FIFO.
# ---------------------------------------------------------------------------
def build_trace() -> list[Packet]:
    pkts: list[Packet] = []
    seq: dict[str, int] = {}
    pid = 0

    def add(flow: str, t: float, nbytes: int) -> None:
        seq[flow] = seq.get(flow, 0) + 1
        nonlocal pid
        pkts.append(Packet(pid, flow, t, nbytes, seq[flow]))
        pid += 1

    # Bulk FTP burst lands first — FIFO would let it dominate.
    for i in range(10):
        add("bulk", 0.000 + i * 0.0001, 1500)
    # Voice: small packets, frequent, real-time.
    for i in range(20):
        add("voice", 0.001 + i * 0.005, 200)
    # Video: medium packets.
    for i in range(10):
        add("video", 0.002 + i * 0.010, 1000)
    # More bulk after a gap.
    for i in range(8):
        add("bulk", 0.050 + i * 0.001, 1500)
    return pkts


def transmit_time(length: int) -> float:
    return length * 8 / LINK_BPS


# ---------------------------------------------------------------------------
# FIFO: one queue, arrival order.
# ---------------------------------------------------------------------------
def simulate_fifo(pkts: list[Packet]) -> list[SentPacket]:
    ordered = sorted(pkts, key=lambda p: (p.arrival, p.pid))
    sent: list[SentPacket] = []
    clock = 0.0
    for p in ordered:
        start = max(clock, p.arrival)
        finish = start + transmit_time(p.length)
        sent.append(SentPacket(p.pid, p.flow, p.arrival, finish, p.length))
        clock = finish
    return sent


# ---------------------------------------------------------------------------
# Strict priority: drain highest-priority non-empty queue first; FIFO within.
# ---------------------------------------------------------------------------
def simulate_priority(pkts: list[Packet]) -> list[SentPacket]:
    queued: dict[str, list[Packet]] = {f: [] for f in FLOWS}
    sent: list[SentPacket] = []
    clock = 0.0
    by_flow = sorted(pkts, key=lambda p: (p.arrival, p.pid))
    idx = 0
    while idx < len(by_flow) or any(queued.values()):
        while idx < len(by_flow) and by_flow[idx].arrival <= clock:
            queued[by_flow[idx].flow].append(by_flow[idx])
            idx += 1
        if not any(queued.values()):
            if idx < len(by_flow):
                clock = by_flow[idx].arrival
                continue
            break
        for fid in sorted(FLOWS, key=lambda f: FLOWS[f].priority):
            if queued[fid]:
                p = queued[fid].pop(0)
                start = max(clock, p.arrival)
                finish = start + transmit_time(p.length)
                sent.append(SentPacket(p.pid, p.flow, p.arrival, finish, p.length))
                clock = finish
                break
    return sent


# ---------------------------------------------------------------------------
# WFQ: virtual finish time F_i = max(A_i, F_{i-1}) + L_i / W_i.
# Transmit in global finish-time order; arrival gating preserved.
# ---------------------------------------------------------------------------
def simulate_wfq(pkts: list[Packet]) -> list[SentPacket]:
    last_finish: dict[str, float] = {f: 0.0 for f in FLOWS}
    finish_records: list[tuple[float, Packet]] = []
    for p in pkts:
        w = FLOWS[p.flow].weight
        f_prev = last_finish[p.flow]
        f_i = max(p.arrival, f_prev) + (p.length * 8 / LINK_BPS) / w
        last_finish[p.flow] = f_i
        finish_records.append((f_i, p))
    finish_records.sort(key=lambda r: (r[0], r[1].pid))
    sent: list[SentPacket] = []
    clock = 0.0
    for f_i, p in finish_records:
        start = max(clock, p.arrival)
        finish = start + transmit_time(p.length)
        sent.append(SentPacket(p.pid, p.flow, p.arrival, finish, p.length))
        clock = finish
    return sent


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def report(name: str, sent: list[SentPacket]) -> None:
    print(f"\n=== {name} ===")
    by_flow: dict[str, list[SentPacket]] = {f: [] for f in FLOWS}
    for s in sent:
        by_flow[s.flow].append(s)
    header = f"{'flow':<8} {'pkts':>5} {'bytes':>8} {'mean_ms':>9} {'max_ms':>9}"
    print(header)
    print("-" * len(header))
    for fid in ["voice", "video", "bulk"]:
        group = by_flow[fid]
        if not group:
            print(f"{fid:<8} {0:>5} {0:>8} {'-':>9} {'-':>9}")
            continue
        bytes_tx = sum(g.length for g in group)
        mean_ms = 1000 * sum(g.delay for g in group) / len(group)
        max_ms = 1000 * max(g.delay for g in group)
        print(f"{fid:<8} {len(group):>5} {bytes_tx:>8} {mean_ms:>9.2f} {max_ms:>9.2f}")
    total_bytes = sum(s.length for s in sent)
    print(f"{'TOTAL':<8} {len(sent):>5} {total_bytes:>8}")


def main() -> None:
    print(f"Lesson: {LESSON}")
    print(f"Link: {LINK_BPS / 1e6:.0f} Mbps | trace: 3 flows (voice/video/bulk)")
    trace = build_trace()
    report("FIFO (tail drop, arrival order)", simulate_fifo(trace))
    report("Strict priority (voice > video > bulk)", simulate_priority(trace))
    report("WFQ (weights voice=8 video=4 bulk=1)", simulate_wfq(trace))
    print("\nExpected: WFQ gives voice lowest max delay; FIFO lets bulk dominate.")


if __name__ == "__main__":
    main()