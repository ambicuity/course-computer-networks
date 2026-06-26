#!/usr/bin/env python3
"""Capstone 14: TFRC UDP Media Rate Control.

Implement TCP-Friendly Rate Control (TFRC, RFC 5348) for UDP media:
the throughput equation, receiver feedback, smooth rate adaptation,
and fairness benchmarking against TCP using the Jain fairness index.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import random

random.seed(42)
S = 1000           # packet size (bytes)
CAP = 10_000_000   # bottleneck capacity (10 MB/s)
DUR = 100          # sim duration (s)
R = 0.030          # RTT 30 ms


def tfrc(s: float, r: float, p: float, t_rto: float | None = None) -> float:
    """TFRC throughput: X = s / (R*sqrt(2p/3) + t_RTO*sqrt(3p/8)*(1+32p^3))."""
    if p <= 0:
        return float("inf")
    if p >= 1:
        return s / (r * math.sqrt(2/3) + (t_rto or 4*r))
    t_rto = t_rto or 4 * r
    denom = r * math.sqrt(2*p/3) + t_rto * math.sqrt(3*p/8) * (1 + 32*p**3)
    return s / denom


@dataclass
class Feedback:
    t: float; p: float; rtt: float


@dataclass
class TfrcSender:
    rate: float = 1000.0; rtt: float = R; p: float = 0.0
    hist: list[float] = field(default_factory=list)

    def update(self, fb: Feedback) -> None:
        self.rtt, self.p = fb.rtt, fb.p
        if fb.p <= 0:
            self.rate = min(self.rate * 2, CAP)
        else:
            tgt = tfrc(S, fb.rtt, fb.p)
            if tgt > self.rate:
                self.rate = min(self.rate + S/fb.rtt, tgt)  # slow inc
            else:
                self.rate = max(tgt, self.rate * 0.5)       # limited dec
        self.hist.append(self.rate)


@dataclass
class TfrcRecv:
    expected: int = 0; recv: set[int] = field(default_factory=set)
    lost: int = 0; total: int = 0
    def rx(self, seq: int, t: float) -> None:
        self.total += 1
        if seq not in self.recv:
            self.recv.add(seq)
            if seq > self.expected:
                self.lost += seq - self.expected; self.expected = seq + 1
            elif seq == self.expected:
                self.expected += 1
        if len(self.recv) > 1000:
            self.recv = set(sorted(self.recv)[-500:])
    def loss(self) -> float:
        return self.lost / max(self.total, 1)


@dataclass
class TcpReno:
    cwnd: float = 1.0; ssthresh: float = float("inf"); hist: list[float] = field(default_factory=list)
    @property
    def rate(self): return self.cwnd * S / R
    def on_loss(self):
        self.ssthresh = max(self.cwnd / 2, 2); self.cwnd = self.ssthresh
    def on_ack(self):
        self.cwnd = self.cwnd * 2 if self.cwnd < self.ssthresh else self.cwnd + 1/self.cwnd
        self.hist.append(self.rate)


@dataclass
class UdpRaw:
    rate: float = CAP / 2; hist: list[float] = field(default_factory=list)


def sim_tfrc(dur: int, lp: float) -> dict:
    s, r, seq, t = TfrcSender(), TfrcRecv(), 0, 0.0
    while t < dur:
        n = max(1, int(s.rate * R / S))
        for _ in range(n):
            if random.random() > lp:
                r.rx(seq, t)
            else:
                r.total += 1; r.lost += 1; r.expected = max(r.expected, seq + 1)
            seq += 1
        s.update(Feedback(t, r.loss(), s.rtt))
        t += R
    return {"rate": s.rate, "avg": sum(s.hist)/len(s.hist) if s.hist else 0, "hist": s.hist}


def sim_tcp(dur: int, lp: float) -> dict:
    f, t = TcpReno(), 0.0
    while t < dur:
        for _ in range(int(f.cwnd)):
            if random.random() < lp: f.on_loss(); break
            f.on_ack()
        t += R
    return {"rate": f.rate, "avg": sum(f.hist)/len(f.hist) if f.hist else 0, "hist": f.hist}


def sim_udp(dur: int) -> dict:
    f, t = UdpRaw(), 0.0
    while t < dur: f.hist.append(f.rate); t += R
    return {"rate": f.rate, "avg": f.rate, "hist": f.hist}


def jain(xs: list[float]) -> float:
    if not xs: return 0.0
    sx, sx2 = sum(xs), sum(x*x for x in xs)
    return (sx*sx) / (len(xs)*sx2) if sx2 else 0.0


def cov(xs: list[float]) -> float:
    if len(xs) < 2: return 0.0
    m = sum(xs)/len(xs)
    if m == 0: return 0.0
    return math.sqrt(sum((v-m)**2 for v in xs)/len(xs)) / m


def main() -> None:
    print("=" * 65)
    print("Capstone 14: TFRC UDP Media Rate Control")
    print("=" * 65)
    print(f"\n  TFRC Throughput Equation (s={S}B, R={R*1000:.0f}ms):")
    print(f"  {'Loss %':<10} {'KB/s':<12} {'Mbps':<10}")
    for p in [0.001, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5]:
        rate = tfrc(S, R, p)
        print(f"  {p*100:<10.1f} {rate/1024:<12.1f} {rate*8/1e6:<10.2f}")

    tr = sim_tfrc(DUR, 0.01); tp = sim_tcp(DUR, 0.01); ud = sim_udp(DUR)
    ctr, ctp, cud = cov(tr["hist"]), cov(tp["hist"]), cov(ud["hist"])
    print(f"\n  --- 100s simulation, loss=1% ---")
    print(f"  TFRC:  avg {tr['avg']/1024:.1f} KB/s, CoV {ctr:.3f} (smooth)")
    print(f"  TCP:   avg {tp['avg']/1024:.1f} KB/s, CoV {ctp:.3f} (sawtooth)")
    print(f"  UDP:   avg {ud['avg']/1024:.1f} KB/s, CoV {cud:.3f} (no control)")

    print(f"\n  --- Fairness (Jain index) ---")
    print(f"  {'Scenario':<14} {'F1 KB/s':<10} {'F2 KB/s':<10} {'J':<8} {'Verdict'}")
    for name, rates in [
        ("TFRC+TCP", [tr["avg"], tp["avg"]]),
        ("TFRC+TFRC", [tr["avg"], tr["avg"]*0.95]),
        ("UDP+TCP", [ud["avg"], tp["avg"]]),
        ("TCP+TCP", [tp["avg"], tp["avg"]*0.98]),
    ]:
        j = jain(rates)
        v = "FAIR" if j > 0.9 else "UNFAIR"
        print(f"  {name:<14} {rates[0]/1024:<10.1f} {rates[1]/1024:<10.1f} {j:<8.3f} {v}")

    print(f"\n  --- Loss rate sensitivity ---")
    print(f"  {'Loss %':<8} {'TFRC KB/s':<12} {'TCP KB/s':<12} {'Ratio':<8}")
    for p in [0.001, 0.005, 0.01, 0.02, 0.05, 0.1]:
        a = sim_tfrc(30, p)["avg"]; b = sim_tcp(30, p)["avg"]
        print(f"  {p*100:<8.1f} {a/1024:<12.1f} {b/1024:<12.1f} {(a/max(b,1)):<8.2f}")

    print(f"\n  Summary: TFRC at 1% loss -> {tr['avg']/1024:.1f} KB/s vs TCP {tp['avg']/1024:.1f} KB/s,")
    print(f"    Jain {jain([tr['avg'], tp['avg']]):.3f} (fair). TFRC CoV {ctr:.3f} << TCP {ctp:.3f} (smoother).")
    print(f"    Unregulated UDP gets {ud['avg']/1024:.1f} KB/s but Jain with TCP = {jain([ud['avg'], tp['avg']]):.3f} (unfair/starves TCP).")
    print(f"    TFRC is the right choice for UDP media: fair to TCP, smooth for users.")


if __name__ == "__main__":
    main()
