"""Traffic Throttling — hop-by-hop backpressure simulator + AIMD sawtooth demo.

Two independent simulations, stdlib only:

1. Hop-by-hop backpressure vs end-to-end choke packets.
   Four-hop path A -> E -> F -> D. Each router has a queue, an EWMA
   queueing-delay estimator, and a buffer cap. When D's EWMA crosses
   threshold a choke packet is generated.

   end-to-end: choke travels all the way to A before any throttling.
   hop-by-hop: choke takes effect at F, then E, then A.

2. AIMD sawtooth. Single flow, N RTTs, additive increase alpha,
   multiplicative decrease beta, bottleneck capacity C.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Part 1 — Hop-by-hop backpressure simulator
# ---------------------------------------------------------------------------


@dataclass
class Router:
    name: str
    capacity_per_tick: int
    buffer_cap: int
    queue: int = 0
    drops: int = 0
    ewma_delay: float = 0.0
    threshold: float = 6.0
    alpha: float = 0.75
    peak_queue: int = 0

    def enqueue(self, packets: int) -> None:
        for _ in range(packets):
            if self.queue >= self.buffer_cap:
                self.drops += 1
            else:
                self.queue += 1
        if self.queue > self.peak_queue:
            self.peak_queue = self.queue
        sample = float(self.queue)
        self.ewma_delay = self.alpha * self.ewma_delay + (1.0 - self.alpha) * sample

    def service(self) -> int:
        served = min(self.queue, self.capacity_per_tick)
        self.queue -= served
        return served

    def congested(self) -> bool:
        return self.ewma_delay > self.threshold


@dataclass
class Path:
    hops: List[Router]
    source_rate: int = 10
    ticks: int = 0
    # Choke-packet propagation state.
    choke_in_flight: bool = False
    choke_progress: int = 0  # hops remaining before the choke reaches the source
    choke_delay: int = 4     # ticks for end-to-end choke to travel back to A

    def step(self, mode: str) -> None:
        self.ticks += 1
        self.hops[0].enqueue(self.source_rate)
        for i in range(len(self.hops) - 1):
            forwarded = self.hops[i].service()
            self.hops[i + 1].enqueue(forwarded)
        self.hops[-1].service()
        self._advance_choke(mode)
        if self.hops[-1].congested() and not self.choke_in_flight:
            self._generate_choke(mode)

    def _generate_choke(self, mode: str) -> None:
        self.choke_in_flight = True
        if mode == "hop-by-hop":
            # Choke reaches the hop just upstream of D on the next tick,
            # then propagates one hop back each tick.
            self.choke_progress = len(self.hops) - 1  # will hit F, E, A
        else:
            # Choke travels all the way back to A before taking effect.
            self.choke_progress = self.choke_delay

    def _advance_choke(self, mode: str) -> None:
        if not self.choke_in_flight:
            return
        if self.choke_progress > 0:
            self.choke_progress -= 1
            if mode == "hop-by-hop" and self.choke_progress >= 1:
                idx = self.choke_progress
                self.hops[idx].capacity_per_tick = max(
                    1, self.hops[idx].capacity_per_tick - 4)
            return
        # Choke has reached the source: throttle A.
        self.choke_in_flight = False
        reduction = max(1, self.source_rate // 2)
        self.source_rate = max(1, self.source_rate - reduction)

    def total_drops(self) -> int:
        return sum(h.drops for h in self.hops)

    def peak_buffers(self) -> List[int]:
        return [h.peak_queue for h in self.hops]


def build_path(cap: int, buffer_cap: int, bottleneck_cap: int = 6) -> Path:
    return Path(hops=[
        Router("A", cap, buffer_cap),
        Router("E", cap, buffer_cap),
        Router("F", cap, buffer_cap),
        Router("D", bottleneck_cap, buffer_cap, threshold=5.0),
    ])


def run_backpressure(mode: str, ticks: int = 50, cap: int = 18,
                     buffer_cap: int = 60, source_rate: int = 24) -> Path:
    p = build_path(cap, buffer_cap, bottleneck_cap=8)
    p.source_rate = source_rate
    p.choke_delay = 6
    for _ in range(ticks):
        p.step(mode)
    return p


# ---------------------------------------------------------------------------
# Part 2 — AIMD sawtooth
# ---------------------------------------------------------------------------


@dataclass
class AIMDFlow:
    capacity: int
    alpha: int = 1
    beta: float = 0.5
    window: int = 1
    history: List[int] = field(default_factory=list)

    def step(self) -> None:
        if self.window >= self.capacity:
            self.window = max(1, int(self.window * self.beta))
        else:
            self.window += self.alpha
        self.history.append(self.window)

    def run(self, rtts: int) -> List[int]:
        for _ in range(rtts):
            self.step()
        return self.history

    def average_window(self) -> float:
        return sum(self.history) / len(self.history) if self.history else 0.0


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def report_backpressure() -> None:
    print("=" * 64)
    print("Part 1: Hop-by-hop backpressure vs end-to-end choke packets")
    print("=" * 64)
    for mode in ("end-to-end", "hop-by-hop"):
        p = run_backpressure(mode=mode)
        peaks = p.peak_buffers()
        drops = p.total_drops()
        print(f"\nMode: {mode}")
        print(f"  total drops          : {drops}")
        print(f"  final source rate    : {p.source_rate}")
        print(f"  peak buffer per hop  : {peaks}")
        print(f"  EWMA delay at D      : {p.hops[-1].ewma_delay:.2f}")


def report_aimd() -> None:
    print("\n" + "=" * 64)
    print("Part 2: AIMD sawtooth (additive increase, multiplicative decrease)")
    print("=" * 64)
    flow = AIMDFlow(capacity=20, alpha=1, beta=0.5)
    flow.run(rtts=60)
    print(f"\ncapacity C            : {flow.capacity}")
    print(f"alpha (additive inc)  : {flow.alpha}")
    print(f"beta  (mult. dec)     : {flow.beta}")
    print(f"average window        : {flow.average_window():.2f}"
          f"  (theory ~ C/2 = {flow.capacity / 2})")
    print(f"window series (first 30): {flow.history[:30]}")
    print("\nASCII sawtooth (each # = scaled window):")
    scale = max(flow.history) // 40 + 1
    for w in flow.history:
        bar = "#" * (w // scale)
        print(f"{w:3d} |{bar}")


def main() -> int:
    report_backpressure()
    report_aimd()
    print("\nDone. Exit 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())