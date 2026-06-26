#!/usr/bin/env python3
"""TCP Spurious Retransmission vs Genuine Loss differential.

Reference oracle for the integrated troubleshooting lab. Reads a
synthetic CSV of TCP events (one row per packet) and classifies
each retransmission event. Without a live capture, the script
generates a representative trace for three scenarios and prints
the per-direction verdict.

CSV columns expected:
    t,src_port,dst_port,seq,ack,flags,kind

    kind is one of:
        data       -- data segment
        ack        -- pure ack
        dup_ack    -- duplicate ack (no payload advance)
        retrans    -- retransmission of an earlier seq
        fast       -- fast retransmit (3 dup-acks preceded it)
        spurious   -- retransmit whose original ack arrived later

Run:  python3 main.py --scenario mix
      python3 main.py --scenario loss_burst
      python3 main.py --scenario spurious_only
"""
from __future__ import annotations

import argparse
import csv
import io
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class TcpEvent:
    t: float
    src_port: int
    dst_port: int
    seq: int
    ack: int
    flags: str
    kind: str


def load(csv_text: str) -> list[TcpEvent]:
    events: list[TcpEvent] = []
    reader = csv.DictReader(io.StringIO(csv_text))
    for row in reader:
        events.append(
            TcpEvent(
                t=float(row["t"]),
                src_port=int(row["src_port"]),
                dst_port=int(row["dst_port"]),
                seq=int(row["seq"]),
                ack=int(row["ack"]),
                flags=row["flags"],
                kind=row["kind"],
            )
        )
    return events


def classify(events: list[TcpEvent]) -> dict[str, int]:
    by_flow: dict[tuple[int, int], list[TcpEvent]] = defaultdict(list)
    for e in events:
        by_flow[(e.src_port, e.dst_port)].append(e)
    counts = {
        "data": 0,
        "ack": 0,
        "dup_ack": 0,
        "retrans": 0,
        "fast": 0,
        "spurious": 0,
        "loss_rto": 0,
    }
    for flow_events in by_flow.values():
        flow_events.sort(key=lambda e: e.t)
        for e in flow_events:
            if e.kind == "data":
                counts["data"] += 1
            elif e.kind == "ack":
                counts["ack"] += 1
            elif e.kind == "dup_ack":
                counts["dup_ack"] += 1
            elif e.kind == "fast":
                counts["fast"] += 1
            elif e.kind == "spurious":
                counts["spurious"] += 1
            elif e.kind == "retrans":
                counts["loss_rto"] += 1
    return counts


SAMPLE_MIX = """t,src_port,dst_port,seq,ack,flags,kind
0.000,50000,443,1000,1,PSH|ACK,data
0.001,443,50000,1,2600,ACK,ack
0.020,50000,443,2600,1,PSH|ACK,data
0.022,443,50000,1,4200,ACK,ack
0.040,50000,443,4200,1,PSH|ACK,data
0.041,443,50000,1,4200,ACK,dup_ack
0.042,443,50000,1,4200,ACK,dup_ack
0.043,443,50000,1,4200,ACK,dup_ack
0.044,50000,443,4200,1,PSH|ACK,fast
0.045,443,50000,1,5600,ACK,ack
0.200,50000,443,5600,1,PSH|ACK,data
0.202,50000,443,5600,1,PSH|ACK,spurious
0.205,443,50000,1,7000,ACK,ack
"""

SAMPLE_LOSS = """t,src_port,dst_port,seq,ack,flags,kind
0.000,50000,443,1000,1,PSH|ACK,data
0.020,50000,443,2600,1,PSH|ACK,data
0.040,50000,443,4200,1,PSH|ACK,data
1.040,50000,443,4200,1,PSH|ACK,retrans
1.060,443,50000,1,5600,ACK,ack
2.060,50000,443,5600,1,PSH|ACK,retrans
4.060,50000,443,5600,1,PSH|ACK,retrans
"""

SAMPLE_SPURIOUS = """t,src_port,dst_port,seq,ack,flags,kind
0.000,50000,443,1000,1,PSH|ACK,data
0.200,50000,443,1000,1,PSH|ACK,spurious
0.202,443,50000,1,2600,ACK,ack
0.220,50000,443,2600,1,PSH|ACK,data
0.222,443,50000,1,4200,ACK,ack
0.420,50000,443,4200,1,PSH|ACK,data
0.620,50000,443,4200,1,PSH|ACK,spurious
0.622,443,50000,1,5600,ACK,ack
"""


def render(scenario: str, counts: dict[str, int]) -> str:
    out: list[str] = []
    out.append("=" * 64)
    out.append(f"TCP RETRANSMISSION CLASSIFIER  --  scenario: {scenario}")
    out.append("=" * 64)
    out.append("")
    out.append("Event counts:")
    for key, val in counts.items():
        out.append(f"  {key:<12} = {val}")
    out.append("")
    total_retrans = counts["fast"] + counts["spurious"] + counts["loss_rto"]
    if total_retrans == 0:
        verdict = "No retransmissions observed; trace is clean."
    else:
        spurious_pct = 100 * counts["spurious"] / total_retrans
        fast_pct = 100 * counts["fast"] / total_retrans
        loss_pct = 100 * counts["loss_rto"] / total_retrans
        out.append(
            f"Total retransmits: {total_retrans}  "
            f"spurious={spurious_pct:.0f}%  fast={fast_pct:.0f}%  rto-loss={loss_pct:.0f}%"
        )
        if counts["spurious"] > counts["loss_rto"] and counts["spurious"] > 0:
            verdict = (
                "DOMINANT signal: SPURIOUS retransmission. The original ACK arrived "
                "after the retransmit. Recommend enabling RACK (RFC 8985) and/or "
                "raising tcp_rto_min. Do not chase a phantom network problem."
            )
        elif counts["fast"] > 0:
            verdict = (
                "DOMINANT signal: FAST retransmit (RFC 5681). Genuine single-packet "
                "loss. Investigate the path between sender and receiver; check for "
                "shallow buffers or ECN-blind AQM."
            )
        else:
            verdict = (
                "DOMINANT signal: RTO-based loss. No fast retransmits observed; "
                "RTO is firing before any dup-ACKs. Investigate one-way loss or "
                "severe RTT inflation."
            )
    out.append("")
    out.append(f"Verdict: {verdict}")
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--scenario", choices=("mix", "loss_burst", "spurious_only"), default="mix")
    args = parser.parse_args()
    sample = {
        "mix": SAMPLE_MIX,
        "loss_burst": SAMPLE_LOSS,
        "spurious_only": SAMPLE_SPURIOUS,
    }[args.scenario]
    events = load(sample)
    counts = classify(events)
    print(render(args.scenario, counts))


if __name__ == "__main__":
    main()
