#!/usr/bin/env python3
"""Bandwidth allocation and sending-rate regulation simulator.

Stdlib only. Demonstrates three concepts from Sec 6.3.1-6.3.2:

1. Max-min fair allocation across flows with overlapping bottleneck links,
   computed with the progressive-filling (water-filling) algorithm.
2. AIMD (Additive Increase Multiplicative Decrease) convergence to the fair
   and efficient operating point under binary congestion feedback.
3. A leaky-bucket rate regulator that shapes a bursty source into a steady
   output rate, the mechanism transport protocols use to regulate sending.

Also includes Padhye's TCP-friendly throughput formula and Jain's fairness
index so you can verify each AIMD step against the textbook formulas.

Run:  python3 main.py
"""
from __future__ import annotations

import math
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Part 1: Max-min fairness via progressive filling (Sec 6.3.1)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Link:
    """A bottleneck link with a capacity and the set of flows on it."""

    name: str
    capacity: float
    flows: tuple[str, ...]


def max_min_fairness(flows: list[str], links: list[Link]) -> dict[str, float]:
    """Compute max-min fair rates by simulating progressive filling.

    Start every flow at zero and increase all rates equally until some
    flow hits a bottleneck. Freeze that flow and continue increasing the
    rest. Repeat until all flows are frozen.
    """
    rates: dict[str, float] = {f: 0.0 for f in flows}
    frozen: set[str] = set()
    while len(frozen) < len(flows):
        active = [f for f in flows if f not in frozen]
        if not active:
            break
        increment = float("inf")
        for link in links:
            contenders = [f for f in link.flows if f not in frozen]
            if not contenders:
                continue
            remaining = link.capacity - sum(rates[f] for f in link.flows)
            share = remaining / len(contenders)
            if share < increment:
                increment = share
        if increment == float("inf") or increment <= 0:
            break
        for f in active:
            rates[f] += increment
        for link in links:
            contenders = [f for f in link.flows if f not in frozen]
            if contenders and sum(rates[f] for f in link.flows) >= link.capacity - 1e-9:
                for f in contenders:
                    frozen.add(f)
    return rates


# ---------------------------------------------------------------------------
# Part 2: AIMD convergence simulation (Sec 6.3.2)
# ---------------------------------------------------------------------------

@dataclass
class AIMDFlow:
    """A flow that grows by `alpha` each step and halves on congestion."""

    name: str
    rate: float = 1.0
    alpha: float = 1.0
    beta: float = 0.5


def simulate_aimd(
    flows: list[AIMDFlow], capacity: float, steps: int = 40
) -> list[dict[str, float]]:
    """Run AIMD on N flows sharing one link of given capacity.

    Each step: additively increase all rates by `alpha`. If the combined
    rate exceeds capacity, multiplicatively decrease every flow by `beta`.
    """
    history: list[dict[str, float]] = []
    for _ in range(steps):
        for fl in flows:
            fl.rate += fl.alpha
        total = sum(fl.rate for fl in flows)
        if total > capacity:
            for fl in flows:
                fl.rate *= fl.beta
        snap: dict[str, float] = {fl.name: round(fl.rate, 2) for fl in flows}
        snap["total"] = round(sum(fl.rate for fl in flows), 2)
        history.append(snap)
    return history


def fairness_index(rates: list[float]) -> float:
    """Jain's fairness index: sum(r)^2 / (n * sum(r^2))."""
    n = len(rates)
    if n == 0:
        return 1.0
    s = sum(rates)
    ss = sum(r * r for r in rates)
    return (s * s) / (n * ss) if ss > 0 else 1.0


def padhye_tcp_rate(mss_bytes: int, rtt_seconds: float, loss_rate: float) -> float:
    """Padhye et al. (1998) TCP-friendly throughput in bytes/sec.

    B  <=  (MSS / RTT) * (1 / sqrt(2 * p / 3))

    A non-TCP sender exceeding this rate is starving its TCP siblings.
    """
    if loss_rate <= 0:
        return float("inf")
    return (mss_bytes / rtt_seconds) * (1.0 / math.sqrt(2.0 * loss_rate / 3.0))


# ---------------------------------------------------------------------------
# Part 3: Leaky-bucket rate regulator (Sec 6.3.2 final paragraph)
# ---------------------------------------------------------------------------

@dataclass
class LeakyBucket:
    """Classic leaky bucket regulator: capacity `beta`, drain rate `rho`."""

    capacity: float
    drain_rate: float
    tokens: float = 0.0

    def send(self, burst: float, dt: float = 1.0) -> float:
        """Attempt to add `burst` tokens; return actual output over dt."""
        self.tokens = min(self.capacity, self.tokens + burst)
        output = min(self.tokens, self.drain_rate * dt)
        self.tokens -= output
        return output


def simulate_leaky_bucket(
    arrivals: list[float], rate: float, capacity: float
) -> list[tuple[float, float, float]]:
    """Feed bursty arrivals through a leaky bucket; return (input, output, backlog)."""
    bucket = LeakyBucket(capacity=capacity, drain_rate=rate)
    results: list[tuple[float, float, float]] = []
    for burst in arrivals:
        out = bucket.send(burst)
        results.append((burst, round(out, 2), round(bucket.tokens, 2)))
    return results


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 72)
    print("Max-Min Fair Allocation (Fig 6-20: four flows, unit links)")
    print("=" * 72)
    flows = ["A", "B", "C", "D"]
    links = [
        Link("R1-R2", 1.0, ("A",)),
        Link("R2-R3", 1.0, ("A", "B")),
        Link("R4-R5", 1.0, ("B", "C", "D")),
        Link("R5-R6", 1.0, ("C", "D")),
    ]
    rates = max_min_fairness(flows, links)
    for f in flows:
        frac = f"{rates[f]:.4f}".rstrip("0").rstrip(".")
        print(f"  Flow {f}: {frac}  (expected: A=2/3, B=1/3, C=1/3, D=1/3)")
    total = sum(rates.values())
    print(f"  Sum:      {total:.4f}  (<4.0 - spare capacity on R1-R2 and R5-R6)")
    print("  Spare on R1-R2 (only A uses it):", round(1.0 - rates["A"], 4))
    print("  Spare on R5-R6 (only C,D use it):", round(1.0 - rates["C"] - rates["D"], 4))

    print()
    print("=" * 72)
    print("AIMD Convergence: 2 flows on a 100-Mbps link, alpha=1, beta=0.5")
    print("=" * 72)
    f1, f2 = AIMDFlow("F1"), AIMDFlow("F2")
    history = simulate_aimd([f1, f2], capacity=100, steps=30)
    print(f"  {'Step':>4}  {'F1':>8}  {'F2':>8}  {'Total':>8}  {'Fairness':>9}")
    for i, snap in enumerate(history):
        fi = fairness_index([snap["F1"], snap["F2"]])
        mark = " <-- congestion" if snap["total"] < 99.5 else ""
        if i < 8 or i >= 25 or i % 4 == 0:
            print(
                f"  {i:4d}  {snap['F1']:8.2f}  {snap['F2']:8.2f}"
                f"  {snap['total']:8.2f}  {fi:9.4f}{mark}"
            )

    final_fi = fairness_index([f1.rate, f2.rate])
    print(
        f"  Final F1={f1.rate:.2f} F2={f2.rate:.2f}  Jain={final_fi:.4f}"
        f"  (close to 1.0 means the two flows converged to fair share)"
    )

    print()
    print("=" * 72)
    print("Padhye TCP-Friendly Rate: MSS=1460, RTT=80ms, p=0.001")
    print("=" * 72)
    bps = padhye_tcp_rate(1460, 0.080, 0.001)
    print(f"  B_TCP  = (1460 / 0.080) * 1/sqrt(2*0.001/3) bytes/sec")
    print(f"        = {bps:,.0f} bytes/sec = {bps * 8 / 1e6:,.2f} Mbps")
    bps_1pct = padhye_tcp_rate(1460, 0.080, 0.01)
    print(f"  At p=0.01 (10x worse loss):  {bps_1pct * 8 / 1e6:,.2f} Mbps")
    print("  -> 10x worse loss gives sqrt(10) ~= 3.16x less fair share.")

    print()
    print("=" * 72)
    print("Leaky-Bucket Rate Regulator: capacity=10, drain_rate=3")
    print("=" * 72)
    arrivals = [8, 2, 0, 12, 0, 0, 5, 1, 0, 0]
    results = simulate_leaky_bucket(arrivals, rate=3.0, capacity=10.0)
    print(f"  {'Step':>4}  {'Input':>8}  {'Output':>8}  {'Backlog':>8}  Note")
    overflow_total = 0.0
    for i, (inp, out, back) in enumerate(results):
        prev_back = back - max(0.0, inp - (10.0 - (back - out)))
        note = ""
        if inp > 0 and back >= 9.99 and inp > out + 0.01:
            note = " (bucket full -> some arrivals dropped)"
            overflow_total += inp - (10.0 - (back - out)) - 0
        print(f"  {i:4d}  {inp:8.1f}  {out:8.1f}  {back:8.1f}  {note}")
    print(
        f"  Output rate: {sum(r[1] for r in results):.1f} over {len(results)} steps,"
        f"  drain rate 3/step -> target {3 * len(results):.1f}"
    )
    print(
        "  Bursts are absorbed by the bucket; arrivals beyond capacity are dropped"
        " -- the regulator enforces a steady drain regardless of source burstiness."
    )


if __name__ == "__main__":
    main()
