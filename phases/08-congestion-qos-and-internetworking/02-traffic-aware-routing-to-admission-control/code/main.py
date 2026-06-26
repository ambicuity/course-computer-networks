"""Traffic-aware routing and admission control simulator.

Implements, using only the Python standard library:
  1. A discrete-time token bucket shaper/policeer.
  2. A discrete-time leaky bucket policeer.
  3. A traffic-aware routing demo on the Figure 5-23 East/West topology,
     showing the oscillation that naive load-sensitive weights cause and the
     damping that multipath routing provides.

Run:  python3 main.py
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# 1. Token bucket
# ---------------------------------------------------------------------------

@dataclass
class TokenBucket:
    rate: float           # R  : tokens per second (bytes/sec)
    capacity: float       # B  : maximum bucket level (bytes)
    level: float = 0.0    # current token count (bytes)
    tick: float = 1e-3    # dt : clock resolution (seconds)

    def refill(self) -> None:
        self.level = min(self.capacity, self.level + self.rate * self.tick)

    def try_send(self, pkt_bytes: int) -> bool:
        """Return True if the packet can be sent now, decrementing tokens."""
        if self.level + 1e-9 >= pkt_bytes:
            self.level -= pkt_bytes
            return True
        return False

    def shape(self, arrivals: List[Tuple[float, int]]) -> List[Tuple[float, int]]:
        """Shape a trace of (time_s, pkt_bytes) into a smoothed output trace.

        Packets that cannot be sent immediately are queued and released at the
        bucket refill rate. Output packets carry the release timestamp.
        """
        out: List[Tuple[float, int]] = []
        queue: List[int] = []
        t = 0.0
        ai = 0
        while ai < len(arrivals) or queue:
            while ai < len(arrivals) and arrivals[ai][0] <= t + 1e-12:
                queue.append(arrivals[ai][1])
                ai += 1
            self.refill()
            while queue and self.level + 1e-9 >= queue[0]:
                sz = queue.pop(0)
                self.try_send(sz)
                out.append((t, sz))
            t += self.tick
            if not queue and ai >= len(arrivals):
                break
        return out


# ---------------------------------------------------------------------------
# 2. Leaky bucket
# ---------------------------------------------------------------------------

@dataclass
class LeakyBucket:
    rate: float           # R  : drain rate (bytes/sec)
    capacity: float       # B  : queue capacity (bytes)
    queue: float = 0.0    # current backlog (bytes)
    dropped: int = 0      # cumulative dropped bytes

    def arrive(self, pkt_bytes: int) -> None:
        if self.queue + pkt_bytes <= self.capacity + 1e-9:
            self.queue += pkt_bytes
        else:
            self.dropped += pkt_bytes

    def drain(self, dt: float) -> float:
        out = min(self.queue, self.rate * dt)
        self.queue -= out
        return out

    def police(self, arrivals: List[Tuple[float, int]], tick: float = 1e-3
               ) -> List[Tuple[float, float]]:
        """Police a trace; return (time_s, drained_bytes) output samples."""
        out: List[Tuple[float, float]] = []
        t = 0.0
        ai = 0
        end = arrivals[-1][0] if arrivals else 0.0
        while ai < len(arrivals) or self.queue > 1e-9:
            while ai < len(arrivals) and arrivals[ai][0] <= t + 1e-12:
                self.arrive(arrivals[ai][1])
                ai += 1
            d = self.drain(tick)
            if d > 0:
                out.append((t, d))
            t += tick
            if t > end + 10.0 and self.queue < 1e-9:
                break
        return out


# ---------------------------------------------------------------------------
# 3. Traffic-aware routing on the Figure 5-23 topology
# ---------------------------------------------------------------------------

# Nodes: West = {A, B, C, D}, East = {E, F, G, H}; cross-links C-F and D-E.
EDGES: List[Tuple[str, str, float]] = [
    ("A", "B", 1.0), ("A", "C", 1.0),
    ("B", "D", 1.0), ("C", "D", 1.0),
    ("E", "F", 1.0), ("E", "G", 1.0),
    ("F", "H", 1.0), ("G", "H", 1.0),
    ("C", "F", 2.0),   # cross-link CF
    ("D", "E", 2.0),   # cross-link EI (book's EI mapped to D-E here)
]


def _norm(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def dijkstra(src: str, weights: Dict[Tuple[str, str], float]) -> Dict[str, List[str]]:
    """Return single-source shortest paths using a node-pair weight map."""
    adj: Dict[str, List[Tuple[str, float]]] = {}
    base: Dict[Tuple[str, str], float] = {_norm(u, v): w for u, v, w in EDGES}
    for (a, b), w in base.items():
        wt = weights.get((a, b), weights.get((b, a), w))
        adj.setdefault(a, []).append((b, wt))
        adj.setdefault(b, []).append((a, wt))
    dist: Dict[str, float] = {src: 0.0}
    prev: Dict[str, str] = {}
    pq: List[Tuple[float, str]] = [(0.0, src)]
    while pq:
        d, u = heapq.heappop(pq)
        if d > dist.get(u, float("inf")):
            continue
        for v, w in adj.get(u, []):
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(pq, (nd, v))
    paths: Dict[str, List[str]] = {}
    for tgt in dist:
        path = [tgt]
        cur = tgt
        while cur != src and cur in prev:
            cur = prev[cur]
            path.append(cur)
        paths[tgt] = list(reversed(path)) if path[-1] == src else [src, tgt]
    return paths


def run_routing(rounds: int = 6, multipath: bool = False) -> None:
    """Run load-sensitive SPF for several rounds and print oscillation."""
    base: Dict[Tuple[str, str], float] = {_norm(u, v): w for u, v, w in EDGES}
    load: Dict[Tuple[str, str], float] = {k: 0.0 for k in base}
    cf = _norm("C", "F")
    de = _norm("D", "E")

    print(f"--- Traffic-aware routing (multipath={multipath}) ---")
    for r in range(rounds):
        weights = {k: base[k] + load[k] for k in base}
        paths = dijkstra("A", weights)
        path = paths["H"]
        # find which cross-link the A->H path traverses
        chosen = cf if any(_norm(path[i], path[i+1]) == cf for i in range(len(path)-1)) else de
        if multipath and abs(weights[cf] - weights[de]) < 1e-9:
            load[cf] = load[cf] * 0.5 + 50.0
            load[de] = load[de] * 0.5 + 50.0
            print(f"  round {r}: multipath split CF={load[cf]:.0f} EI={load[de]:.0f}")
        else:
            for k in load:
                load[k] *= 0.5  # decay
            load[chosen] += 100.0
            print(f"  round {r}: SPF path={'-'.join(path)} via {chosen}, "
                  f"CF_load={load[cf]:.0f} EI_load={load[de]:.0f}")


# ---------------------------------------------------------------------------
# Demo driver
# ---------------------------------------------------------------------------

def demo_token_bucket() -> None:
    print("--- Token bucket shaping ---")
    arrivals: List[Tuple[float, int]] = []
    t = 0.0
    for _ in range(125):          # 125 ms burst at 125 MB/s -> 125000 bytes/ms
        arrivals.append((round(t, 4), 125000))
        t += 1e-3
    t = 0.500
    for _ in range(250):           # 250 ms at 25 MB/s -> 25000 bytes/ms
        arrivals.append((round(t, 4), 25000))
        t += 1e-3
    tb = TokenBucket(rate=25_000_000.0, capacity=9_600_000.0, level=9_600_000.0)
    out = tb.shape(arrivals)
    total_in = sum(b for _, b in arrivals)
    total_out = sum(b for _, b in out)
    span = out[-1][0] - out[0][0] if out else 0.0
    rate_out = total_out / span / 1e6 if span else 0.0
    print(f"  offered={total_in/1e6:.2f} MB  shaped={total_out/1e6:.2f} MB  "
          f"output_span={span*1e3:.1f} ms  long_term_rate={rate_out:.1f} MB/s")
    s = 9_600_000 / (125_000_000 - 25_000_000) * 1e3
    print(f"  theoretical max burst S = B/(M-R) = {s:.1f} ms")


def demo_leaky_bucket() -> None:
    print("--- Leaky bucket policing ---")
    arrivals: List[Tuple[float, int]] = [(0.000, 5_000_000),
                                         (0.001, 5_000_000),
                                         (0.002, 5_000_000)]
    lb = LeakyBucket(rate=1_000_000.0, capacity=8_000_000.0)
    samples = lb.police(arrivals, tick=1e-3)
    total_in = sum(b for _, b in arrivals)
    total_out = sum(b for _, b in samples)
    print(f"  offered={total_in/1e6:.2f} MB  drained={total_out/1e6:.2f} MB  "
          f"dropped={lb.dropped/1e6:.2f} MB  backlog={lb.queue/1e6:.2f} MB")
    # Whole-packet drop semantics: pkt 2 (queue 4.999+5>8) dropped, pkt 3 dropped
    assert lb.dropped == 10_000_000, f"expected 10 MB dropped, got {lb.dropped/1e6:.2f}"
    assert lb.queue < 1e-6, "backlog should drain to zero"


def main() -> int:
    demo_token_bucket()
    print()
    demo_leaky_bucket()
    print()
    run_routing(rounds=6, multipath=False)
    print()
    run_routing(rounds=6, multipath=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())