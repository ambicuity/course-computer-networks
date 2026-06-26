"""Approaches to Congestion Control — stdlib-only simulator.

Single router output queue fed by N AIMD senders; compares tail-drop vs RED.
Run: python3 main.py   Exit: 0. No pip deps.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

BUFFER_PKTS: int = 200
MIN_THRESH: float = 50.0
MAX_THRESH: float = 150.0
MAX_P: float = 0.10
ALPHA: float = 0.1
LINK_RATE: int = 1000
N_SENDERS: int = 8
SIM_SECONDS: int = 60
RTT_TICKS: int = 10


@dataclass
class RedRouter:
    """Router output queue with optional RED dropping; maintains EWMA `d`."""
    buffer: int = BUFFER_PKTS
    min_thresh: float = MIN_THRESH
    max_thresh: float = MAX_THRESH
    max_p: float = MAX_P
    alpha: float = ALPHA
    use_red: bool = True
    queue: list[int] = field(default_factory=list)
    avg: float = 0.0
    dropped: int = 0
    arrived: int = 0
    dequeued: int = 0

    def _update_avg(self) -> None:
        s = float(len(self.queue))
        self.avg = self.alpha * self.avg + (1.0 - self.alpha) * s

    def _red_drop_prob(self) -> float:
        if self.avg < self.min_thresh:
            return 0.0
        if self.avg >= self.max_thresh:
            return 1.0
        frac = (self.avg - self.min_thresh) / (self.max_thresh - self.min_thresh)
        return frac * self.max_p

    def enqueue(self, pkt: int) -> bool:
        self.arrived += 1
        self._update_avg()
        if self.use_red:
            p = self._red_drop_prob()
            if p >= 1.0 or (p > 0.0 and random.random() < p):
                self.dropped += 1
                return False
        if len(self.queue) >= self.buffer:
            self.dropped += 1
            return False
        self.queue.append(pkt)
        return True

    def dequeue(self) -> int | None:
        if not self.queue:
            return None
        self.dequeued += 1
        return self.queue.pop(0)


@dataclass
class AIMDSender:
    """TCP-Reno-style: +1/RTT on success, ÷2 on loss."""
    sid: int
    window: float = 1.0
    delivered: int = 0
    lost: int = 0
    last_send_tick: int = 0
    window_history: list[float] = field(default_factory=list)

    def maybe_send(self, tick: int) -> int:
        if tick - self.last_send_tick < RTT_TICKS:
            return 0
        self.last_send_tick = tick
        n = max(1, int(self.window))
        dropped_here = 0
        for _ in range(n):
            pkt_id = self.sid * 10_000 + self.delivered + self.lost
            if _ROUTER.enqueue(pkt_id):
                self.delivered += 1
            else:
                self.lost += 1
                dropped_here += 1
        return dropped_here

    def on_ack(self, loss_in_rtt: int) -> None:
        if loss_in_rtt > 0:
            self.window = max(1.0, self.window / 2.0)
        else:
            self.window += 1.0
        self.window_history.append(self.window)


_ROUTER: RedRouter = RedRouter(use_red=True)


def simulate(use_red: bool, seed: int = 42) -> dict:
    global _ROUTER
    random.seed(seed)
    _ROUTER = RedRouter(use_red=use_red)
    router = _ROUTER
    senders = [AIMDSender(sid=i) for i in range(N_SENDERS)]
    rtt_loss = [0] * N_SENDERS
    goodput_per_second: list[int] = []
    TOTAL_TICKS = SIM_SECONDS * 100

    for tick in range(TOTAL_TICKS):
        # Shuffle order so drops distribute across senders; without this the
        # first senders fill the queue and later ones always see the drops,
        # hiding the AIMD sawtooth for any fixed sender.
        order = list(range(N_SENDERS))
        random.shuffle(order)
        for i in order:
            rtt_loss[i] += senders[i].maybe_send(tick)
        for _ in range(LINK_RATE // 100):
            router.dequeue()
        if (tick + 1) % RTT_TICKS == 0:
            for i, s in enumerate(senders):
                s.on_ack(rtt_loss[i])
                rtt_loss[i] = 0
        if (tick + 1) % 100 == 0:
            goodput_per_second.append(router.dequeued - sum(goodput_per_second))

    total_delivered = sum(s.delivered for s in senders)
    total_lost = sum(s.lost for s in senders)
    total_offered = total_delivered + total_lost
    ratio = (total_delivered / total_offered) if total_offered else 0.0
    fw = [s.window for s in senders]
    n = len(fw)
    ssum = sum(fw)
    sq = sum(w * w for w in fw)
    fairness = (ssum * ssum) / (n * sq) if sq > 0 else 0.0
    return {
        "policy": "RED" if use_red else "tail-drop",
        "offered": total_offered,
        "delivered": total_delivered,
        "dropped": router.dropped,
        "goodput_ratio": round(ratio, 4),
        "jain_fairness": round(fairness, 4),
        "window_trace_s0": [round(w, 2) for w in senders[0].window_history[:40]],
    }


def main() -> int:
    print("=" * 72)
    print("Approaches to Congestion Control — router-queue simulator")
    print(f"Config: {N_SENDERS} AIMD senders, link={LINK_RATE} pkts/s, "
          f"buffer={BUFFER_PKTS}, RTT={RTT_TICKS} ticks")
    print(f"RED:    min={MIN_THRESH} max={MAX_THRESH} max_p={MAX_P} alpha={ALPHA}")
    print("=" * 72)
    print()
    results = [simulate(use_red=False, seed=7), simulate(use_red=True, seed=7)]
    header = f"{'policy':<10} {'offered':>10} {'delivered':>10} {'dropped':>10} {'goodput%':>9} {'fairness':>9}"
    print("## Tail-drop vs RED — aggregate")
    print(header)
    print("-" * len(header))
    for r in results:
        print(f"{r['policy']:<10} {r['offered']:>10} {r['delivered']:>10} {r['dropped']:>10} "
              f"{r['goodput_ratio']*100:>8.1f}% {r['jain_fairness']:>9.4f}")
    print()
    print("## AIMD window trace — sender 0 (first 40 RTTs)")
    for r in results:
        print(f"  {r['policy']:<10}: {r['window_trace_s0']}")
    print()
    td, red = results
    print(f"## Interpretation")
    print(f"  RED cut drops {td['dropped']} -> {red['dropped']} "
          f"(goodput ratio {td['goodput_ratio']*100:.1f}% -> {red['goodput_ratio']*100:.1f}%).")
    print(f"  Jain fairness: tail-drop={td['jain_fairness']:.4f} RED={red['jain_fairness']:.4f}.")
    print("  The sawtooth above is AIMD: +1/RTT on success, /2 on loss. Tail-drop")
    print("  synchronizes the /2's (goodput cliff); RED spreads them so the queue")
    print("  stays in the linear region of the goodput curve. Exit 0.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())