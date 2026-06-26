#!/usr/bin/env python3
"""Trace Annotation Runbook — annotate an exported packet trace and emit a verdict.

This stdlib-only tool consumes rows in the shape Wireshark produces via
"Export Packet Dissections > As CSV" (frame number, relative time, the 5-tuple,
TCP flag byte, and the info column). It performs the four annotation passes
described in the lesson:

  pass 2  handshake     -> derive the RTT baseline from SYN / SYN-ACK
  pass 3  anomalies     -> flag retransmissions, zero-window, resets
  pass 4  time math      -> attribute total latency to DNS / RTT / TLS / server

It then prints a per-packet annotated timeline and a single-line verdict naming
the layer that owns the latency. A built-in sample trace makes it runnable with
no arguments: `python3 main.py`.
"""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from typing import Callable, Optional

# TCP flag bit positions within the 1-byte flags field (header byte 13).
FIN = 0x01
SYN = 0x02
RST = 0x04
ACK = 0x10

# Latency-attribution thresholds (seconds) used to phrase the verdict.
RTO_FLOOR_S = 0.9          # a gap near/over the RFC 6298 initial RTO implies a lost SYN
DOMINANT_SHARE = 0.5       # a phase owning >50% of total latency is "the" cause


@dataclass
class Packet:
    """One annotated packet from the exported trace."""

    number: int
    t: float                # frame.time_relative, seconds since first frame
    src: str
    dst: str
    sport: int
    dport: int
    flags: int              # raw TCP flag byte; 0 for non-TCP rows
    info: str
    note: str = ""          # human-readable annotation filled in during analysis

    def flag_names(self) -> str:
        bits = [(SYN, "SYN"), (ACK, "ACK"), (FIN, "FIN"), (RST, "RST")]
        on = [name for bit, name in bits if self.flags & bit]
        return ",".join(on) if on else "-"


def parse_flags(raw: str) -> int:
    """Parse a Wireshark tcp.flags value, which exports as hex like '0x0002'."""
    raw = raw.strip()
    if not raw:
        return 0
    try:
        return int(raw, 16) if raw.lower().startswith("0x") else int(raw)
    except ValueError:
        return 0


def load_rows(text: str) -> list[Packet]:
    """Parse CSV rows exported from Wireshark into Packet objects."""
    reader = csv.DictReader(io.StringIO(text))
    packets: list[Packet] = []
    for row in reader:
        packets.append(
            Packet(
                number=int(row["frame.number"]),
                t=float(row["frame.time_relative"]),
                src=row.get("ip.src", "").strip(),
                dst=row.get("ip.dst", "").strip(),
                sport=int(row["tcp.srcport"] or 0),
                dport=int(row["tcp.dstport"] or 0),
                flags=parse_flags(row.get("tcp.flags", "")),
                info=row.get("info", "").strip(),
            )
        )
    return packets


def find_first(packets: list[Packet], predicate: Callable[[Packet], bool]) -> Optional[Packet]:
    for pkt in packets:
        if predicate(pkt):
            return pkt
    return None


def annotate_handshake(packets: list[Packet]) -> Optional[float]:
    """Pass 2: tag the handshake packets and return the RTT baseline (seconds)."""
    syns = [p for p in packets if p.flags & SYN and not p.flags & ACK]
    syn_ack = find_first(packets, lambda p: bool(p.flags & SYN) and bool(p.flags & ACK))
    first_ack = find_first(
        packets,
        lambda p: bool(p.flags & ACK) and not (p.flags & SYN) and not (p.flags & FIN),
    )

    if not syns or syn_ack is None:
        return None

    syns[0].note = "handshake: initial SYN (client opens, sends ISN + options)"
    for extra in syns[1:]:
        gap = extra.t - syns[0].t
        extra.note = f"handshake: SYN RETRANSMIT (+{gap*1000:.0f} ms) — first SYN likely lost"
    syn_ack.note = "handshake: SYN-ACK (server accepts)"
    if first_ack is not None and first_ack is not syn_ack:
        first_ack.note = "handshake: ACK — connection ESTABLISHED"

    return syn_ack.t - syns[0].t


def annotate_anomalies(packets: list[Packet]) -> dict[str, int]:
    """Pass 3: flag retransmissions, duplicate ACKs, zero-window, resets."""
    counts = {"retransmission": 0, "duplicate_ack": 0, "zero_window": 0, "reset": 0}
    seen_seq_info: set[str] = set()

    for pkt in packets:
        low = pkt.info.lower()
        if pkt.flags & RST:
            counts["reset"] += 1
            pkt.note = "anomaly: RST — abrupt teardown (refused port / firewall / crash)"
        elif "zero window" in low and "update" not in low:
            counts["zero_window"] += 1
            pkt.note = "anomaly: ZERO WINDOW — receiver buffer full, app not reading"
        elif "window update" in low:
            pkt.note = "recovery: WINDOW UPDATE — receiver drained buffer, sender may resume"
        elif "retransmission" in low:
            counts["retransmission"] += 1
            pkt.note = "anomaly: RETRANSMISSION — loss or expired RTO"
        elif "duplicate ack" in low:
            counts["duplicate_ack"] += 1
            if pkt.info in seen_seq_info:
                pkt.note = "anomaly: DUP ACK (repeat) — out-of-order/loss before this point"
            else:
                pkt.note = "anomaly: duplicate ACK — receiver missing a segment"
                seen_seq_info.add(pkt.info)
    return counts


def attribute_latency(packets: list[Packet], rtt: Optional[float]) -> str:
    """Pass 4: subtract phase deltas and name the dominant latency owner."""
    dns_q = find_first(packets, lambda p: "standard query" in p.info.lower() and "response" not in p.info.lower())
    dns_r = find_first(packets, lambda p: "standard query response" in p.info.lower())
    chello = find_first(packets, lambda p: "client hello" in p.info.lower())
    shello = find_first(packets, lambda p: "server hello" in p.info.lower())
    req = find_first(packets, lambda p: p.info.lower().startswith(("get ", "post ")))
    resp = find_first(packets, lambda p: "http/1" in p.info.lower() and ("200" in p.info or "304" in p.info))

    phases: dict[str, float] = {}
    if dns_q and dns_r:
        phases["DNS resolution"] = dns_r.t - dns_q.t
    if rtt is not None:
        phases["network RTT (SYN-ACK)"] = rtt
    if chello and shello:
        phases["TLS + server setup"] = shello.t - chello.t
    if req and resp:
        phases["server think time"] = resp.t - req.t

    if not phases:
        return "verdict: insufficient markers to attribute latency (need DNS/TLS/HTTP rows)."

    total = sum(v for v in phases.values() if v > 0)
    owner, cost = max(phases.items(), key=lambda kv: kv[1])
    share = cost / total if total > 0 else 0.0
    lines = [f"  {name:<26} {dt*1000:8.1f} ms" for name, dt in phases.items()]
    body = "\n".join(lines)
    qualifier = "DOMINANT" if share >= DOMINANT_SHARE else "largest single phase"
    return (
        f"{body}\n\nverdict: '{owner}' is the {qualifier} cost "
        f"({cost*1000:.0f} ms, {share*100:.0f}% of measured)."
    )


SAMPLE_TRACE = """frame.number,frame.time_relative,ip.src,ip.dst,tcp.srcport,tcp.dstport,tcp.flags,info
1,0.000000,10.0.0.5,10.0.0.1,51000,53,0x0000,Standard query 0x1a2b A example.com
2,0.041000,10.0.0.1,10.0.0.5,53,51000,0x0000,Standard query response 0x1a2b A 93.184.216.34
3,0.050000,10.0.0.5,93.184.216.34,49888,443,0x0002,49888 -> 443 [SYN] Seq=0
4,1.052000,10.0.0.5,93.184.216.34,49888,443,0x0002,[TCP Retransmission] 49888 -> 443 [SYN] Seq=0
5,1.094000,93.184.216.34,10.0.0.5,443,49888,0x0012,443 -> 49888 [SYN, ACK] Seq=0 Ack=1
6,1.095000,10.0.0.5,93.184.216.34,49888,443,0x0010,49888 -> 443 [ACK] Seq=1 Ack=1
7,1.096000,10.0.0.5,93.184.216.34,49888,443,0x0018,Client Hello
8,1.140000,93.184.216.34,10.0.0.5,443,49888,0x0018,Server Hello, Certificate
9,1.150000,10.0.0.5,93.184.216.34,49888,443,0x0018,GET /dashboard HTTP/1.1
10,1.205000,93.184.216.34,10.0.0.5,443,49888,0x0018,HTTP/1.1 200 OK (text/html)
"""


def main() -> None:
    packets = load_rows(SAMPLE_TRACE)

    print("=" * 68)
    print("TRACE ANNOTATION RUNBOOK — automated passes 2-4")
    print("=" * 68)

    rtt = annotate_handshake(packets)
    counts = annotate_anomalies(packets)

    print("\nAnnotated timeline:")
    for pkt in packets:
        stamp = f"{pkt.t*1000:8.1f} ms"
        head = f"  #{pkt.number:<2} {stamp}  {pkt.src:>15} -> {pkt.dst:<15} [{pkt.flag_names()}]"
        print(head)
        annotation = pkt.note or pkt.info
        print(f"        {annotation}")

    print("\nPass 2 — handshake:")
    if rtt is not None:
        print(f"  RTT baseline (SYN-ACK - SYN) = {rtt*1000:.1f} ms")
        if rtt >= RTO_FLOOR_S:
            print("  NOTE: baseline >= initial RTO floor — a lost SYN inflated setup, not the server.")
    else:
        print("  no complete handshake found in trace")

    print("\nPass 3 — anomalies:")
    for name, n in counts.items():
        if n:
            print(f"  {name}: {n}")
    if not any(counts.values()):
        print("  none detected")

    print("\nPass 4 — latency attribution:")
    print(attribute_latency(packets, rtt))


if __name__ == "__main__":
    main()
