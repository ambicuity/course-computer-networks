"""Traffic shaping simulators: leaky bucket, token bucket, and WFQ scheduler.

Stdlib only. Run `python3 main.py` to compare shaped vs. unshaped traces
and verify the maximum burst length formula S = B / (M - R).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

# --- Simulation constants (units: bytes, seconds) ---------------------------

HOST_PEAK_RATE: int = 125_000_000          # 1000 Mbps -> 125 MB/s
TOKEN_RATE: int = 25_000_000               # 200 Mbps  -> 25 MB/s
TOKEN_CAPACITY: int = 9_600_000            # 9600 KB
BURST_BYTES: int = 16_000_000              # 16000 KB burst
TICK: float = 0.001                        # 1 ms clock
SIM_SECONDS: float = 1.0                   # 1 second of simulation


# --- Traffic source ---------------------------------------------------------

@dataclass
class BurstSource:
    """Emits one burst of BURST_BYTES at HOST_PEAK_RATE, then goes idle."""

    peak_rate: int = HOST_PEAK_RATE
    burst_bytes: int = BURST_BYTES
    delivered: int = 0
    done: bool = False

    def offer(self, dt: float) -> int:
        """Return bytes available to send in the next dt seconds."""
        if self.done:
            return 0
        chunk = int(self.peak_rate * dt)
        remaining = self.burst_bytes - self.delivered
        if chunk >= remaining:
            self.done = True
            self.delivered = self.burst_bytes
            return remaining
        self.delivered += chunk
        return chunk


# --- Leaky bucket shaper ----------------------------------------------------

@dataclass
class LeakyBucket:
    """Constant outflow rate R; capacity B; overflow spills (lost)."""

    rate: int                          # bytes/sec outflow
    capacity: int                      # bytes held in bucket
    level: int = 0                     # current water level (bytes)
    spilled: int = 0                   # bytes lost to overflow
    sent: int = 0

    def admit(self, offered: int, dt: float) -> int:
        """Accept offered bytes, return bytes actually emitted in this tick."""
        space = self.capacity - self.level
        if offered > space:
            self.spilled += offered - space
            self.level = self.capacity
        else:
            self.level += offered
        out = int(self.rate * dt)
        if out > self.level:
            out = self.level
        self.level -= out
        self.sent += out
        return out


# --- Token bucket shaper ----------------------------------------------------

@dataclass
class TokenBucket:
    """Tokens fill at R up to B; a packet needs tokens to leave; excess queues."""

    rate: int                          # token fill rate (bytes/sec)
    capacity: int                      # max tokens stored (bytes)
    tokens: int = field(default=None)  # current tokens (defaults to full)
    queued: int = 0                    # bytes waiting for tokens
    sent: int = 0
    delayed_ticks: int = 0

    def __post_init__(self) -> None:
        if self.tokens is None:
            self.tokens = self.capacity

    def admit(self, offered: int, dt: float) -> int:
        """Refill tokens, accept offered bytes into queue, emit what tokens allow."""
        self.tokens = min(self.capacity, self.tokens + int(self.rate * dt))
        self.queued += offered
        out = min(self.queued, self.tokens)
        self.queued -= out
        self.tokens -= out
        if self.queued > 0:
            self.delayed_ticks += 1
        self.sent += out
        return out


# --- WFQ scheduler ----------------------------------------------------------

@dataclass
class Flow:
    """A WFQ flow with a weight and a backlog of packet lengths."""

    flow_id: int
    weight: int
    packets: List[int] = field(default_factory=list)
    virtual_finish: float = 0.0


def wfq_schedule(flows: List[Flow]) -> List[Tuple[int, int]]:
    """Schedule packets by virtual finish time F = max(A, F_prev) + L / W.

    Returns a list of (flow_id, packet_length) in send order.
    Arrival times are integers 0..N-1 in the order packets are presented.
    """
    events: List[Tuple[int, int, int]] = []
    for flow in flows:
        for idx, length in enumerate(flow.packets):
            events.append((idx, flow.flow_id, length))
    events.sort(key=lambda e: (e[0], e[1]))

    prev_finish: dict[int, float] = {f.flow_id: 0.0 for f in flows}
    flow_map = {f.flow_id: f for f in flows}
    scheduled: List[Tuple[float, int, int]] = []
    for arrival, fid, length in events:
        f_prev = prev_finish[fid]
        finish = max(arrival, f_prev) + length / flow_map[fid].weight
        prev_finish[fid] = finish
        scheduled.append((finish, fid, length))
    scheduled.sort(key=lambda s: s[0])
    return [(fid, length) for _, fid, length in scheduled]


# --- Trace runner -----------------------------------------------------------

def run_shaper(source: BurstSource, shaper: object, dt: float, duration: float) -> List[int]:
    """Run a shaper over a source for `duration` seconds at tick `dt`."""
    trace: List[int] = []
    ticks = int(duration / dt)
    for _ in range(ticks):
        offered = source.offer(dt)
        emitted = shaper.admit(offered, dt)  # type: ignore[attr-defined]
        trace.append(emitted)
    return trace


def peak_rate(trace: List[int], dt: float) -> float:
    """Highest per-tick emission rate in bytes/sec."""
    return max(trace) / dt if trace else 0.0


def total(trace: List[int]) -> int:
    return sum(trace)


# --- Main -------------------------------------------------------------------

def main() -> int:
    print("=== Traffic Shaping Simulation ===")
    print(f"Host peak rate M = {HOST_PEAK_RATE/1e6:.0f} Mbps")
    print(f"Token/leaky rate R = {TOKEN_RATE/1e6:.0f} Mbps")
    print(f"Bucket capacity B = {TOKEN_CAPACITY/1000:.0f} KB")
    print(f"Burst size       = {BURST_BYTES/1000:.0f} KB")
    print(f"Tick             = {TICK*1000:.0f} ms")
    print()

    s_theory = TOKEN_CAPACITY / (HOST_PEAK_RATE - TOKEN_RATE)
    print(f"Theoretical max burst S = B/(M-R) = {s_theory*1000:.1f} ms")
    print()

    # Unshaped baseline: passthrough at host peak rate.
    src0 = BurstSource()
    passthrough = LeakyBucket(rate=HOST_PEAK_RATE, capacity=10**9)
    unshaped = run_shaper(src0, passthrough, TICK, SIM_SECONDS)
    print("--- Unshaped (passthrough) ---")
    print(f"total sent     = {total(unshaped)/1000:.0f} KB")
    print(f"peak tick rate = {peak_rate(unshaped, TICK)/1e6:.0f} Mbps")
    print(f"active ticks   = {sum(1 for b in unshaped if b > 0)}")
    print()

    # Leaky bucket: strict smoothing.
    src1 = BurstSource()
    leaky = LeakyBucket(rate=TOKEN_RATE, capacity=TOKEN_CAPACITY)
    leaky_trace = run_shaper(src1, leaky, TICK, SIM_SECONDS)
    print("--- Leaky Bucket (R=200 Mbps, B=9600 KB) ---")
    print(f"total sent     = {leaky.sent/1000:.0f} KB")
    print(f"spilled        = {leaky.spilled/1000:.0f} KB")
    print(f"peak tick rate = {peak_rate(leaky_trace, TICK)/1e6:.0f} Mbps")
    print(f"active ticks   = {sum(1 for b in leaky_trace if b > 0)}")
    print()

    # Token bucket: burst capability.
    src2 = BurstSource()
    bucket = TokenBucket(rate=TOKEN_RATE, capacity=TOKEN_CAPACITY)
    token_trace = run_shaper(src2, bucket, TICK, SIM_SECONDS)
    burst_ticks = 0
    for b in token_trace:
        if b >= HOST_PEAK_RATE * TICK * 0.99:
            burst_ticks += 1
        elif b > 0:
            break
    s_empirical = burst_ticks * TICK
    print("--- Token Bucket (R=200 Mbps, B=9600 KB) ---")
    print(f"total sent     = {bucket.sent/1000:.0f} KB")
    print(f"queued remain  = {bucket.queued/1000:.0f} KB")
    print(f"peak tick rate = {peak_rate(token_trace, TICK)/1e6:.0f} Mbps")
    print(f"burst ticks    = {burst_ticks} ({s_empirical*1000:.1f} ms)")
    print(f"empirical S    = {s_empirical*1000:.1f} ms  (theory {s_theory*1000:.1f} ms)")
    print(f"delayed ticks  = {bucket.delayed_ticks}")
    print()

    # WFQ demonstration: three flows, weights 1, 2, 3.
    print("--- WFQ Scheduler (weights 1, 2, 3) ---")
    flows = [
        Flow(flow_id=1, weight=1, packets=[1500, 1500, 1500, 1500]),
        Flow(flow_id=2, weight=2, packets=[1500, 1500, 1500, 1500]),
        Flow(flow_id=3, weight=3, packets=[1500, 1500, 1500, 1500]),
    ]
    order = wfq_schedule(flows)
    counts = {1: 0, 2: 0, 3: 0}
    for fid, length in order:
        counts[fid] += 1
        print(f"  send flow {fid}  {length} B  (cumulative flow{fid}: {counts[fid]})")
    print(f"packets sent per flow: {counts}")
    print("  weight ratio 1:2:3  ->  bandwidth share should follow.")
    print()

    print("=== Simulation complete ===")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())