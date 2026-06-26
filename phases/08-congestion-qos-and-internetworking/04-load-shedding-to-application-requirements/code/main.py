"""Load shedding simulator with priority classes and QoS requirement classifier.

Models an overloaded output link fed by three application classes (real-time,
streaming, elastic) and compares three shedding policies: random (tail drop),
priority (wine/milk), and RED with DSCP drop precedence.

Run with:  python3 main.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# --------------------------------------------------------------------------- #
# QoS 4-tuple and application classes                                          #
# --------------------------------------------------------------------------- #

BANDWIDTH = "bandwidth"      # bits per second the flow needs
DELAY = "delay"              # max one-way delay the flow tolerates (ms)
JITTER = "jitter"            # max delay variation the flow tolerates (ms)
LOSS = "loss"                # max loss fraction the flow tolerates (0..1)


@dataclass(frozen=True)
class QoSRequirement:
    bandwidth_kbps: int
    delay_ms: int
    jitter_ms: int
    loss: float

    def violated(self, measured_delay: float, measured_jitter: float,
                 measured_loss: float) -> list[str]:
        out: list[str] = []
        if measured_delay > self.delay_ms:
            out.append(f"delay {measured_delay:.1f}ms > {self.delay_ms}ms")
        if measured_jitter > self.jitter_ms:
            out.append(f"jitter {measured_jitter:.1f}ms > {self.jitter_ms}ms")
        if measured_loss > self.loss:
            out.append(f"loss {measured_loss:.3f} > {self.loss:.3f}")
        return out


# DiffServ codepoints (high-level labels; real 6-bit values in parentheses).
EF = "EF"            # Expedited Forwarding  (real-time)
AF_GOLD = "AF_GOLD"
AF_SILVER = "AF_SILVER"
AF_BRONZE = "AF_BRONZE"
BEST_EFFORT = "BE"


@dataclass(frozen=True)
class AppClass:
    name: str
    dscp: str
    qos: QoSRequirement
    drop_policy: str   # "milk" (oldest first) | "wine" (newest first) | "excess"


# Three operational classes derived from Tanenbaum Fig. 5-27.
REAL_TIME = AppClass("real-time", EF,
                     QoSRequirement(64, 150, 30, 0.05), "milk")
STREAMING = AppClass("streaming", AF_SILVER,
                     QoSRequirement(2000, 2000, 500, 0.01), "excess")
ELASTIC = AppClass("elastic", AF_BRONZE,
                   QoSRequirement(500, 1000, 200, 0.001), "wine")


def classify(app_name: str) -> AppClass:
    """Map a human application name to a DiffServ class + drop policy."""
    mapping: dict[str, AppClass] = {
        "telephony": REAL_TIME,
        "videoconferencing": REAL_TIME,
        "audio_on_demand": STREAMING,
        "video_on_demand": STREAMING,
        "email": ELASTIC,
        "file_transfer": ELASTIC,
        "web": ELASTIC,
        "remote_login": ELASTIC,
    }
    if app_name not in mapping:
        raise ValueError(f"unknown application: {app_name}")
    return mapping[app_name]


# --------------------------------------------------------------------------- #
# Packet and router model                                                      #
# --------------------------------------------------------------------------- #


@dataclass
class Packet:
    seq: int
    app: AppClass
    arrival: float        # ms (simulated time)
    size_bytes: int = 1500
    drop_precedence: int = 0   # 0=low, 1=medium, 2=high (policer sets this)
    dropped: bool = False


@dataclass
class RouterConfig:
    link_kbps: int = 1500          # output link capacity
    queue_capacity: int = 80       # packets the buffer holds
    red_min_thresh: int = 25       # queue depth at which RED starts dropping
    red_max_thresh: int = 60       # queue depth at which RED drops max fraction
    red_max_drop_prob: float = 0.1
    policy: str = "random"        # "random" | "priority" | "red"


@dataclass
class ClassStats:
    sent: int = 0
    dropped: int = 0
    delivered_delays: list[float] = field(default_factory=list)

    @property
    def loss(self) -> float:
        return self.dropped / self.sent if self.sent else 0.0

    @property
    def avg_delay(self) -> float:
        return (sum(self.delivered_delays) / len(self.delivered_delays)
                if self.delivered_delays else 0.0)

    @property
    def jitter(self) -> float:
        if len(self.delivered_delays) < 2:
            return 0.0
        m = self.avg_delay
        return (sum((d - m) ** 2 for d in self.delivered_delays)
                / len(self.delivered_delays)) ** 0.5


def generate_traffic(rng: random.Random, n_packets: int,
                     mix: dict[AppClass, float], t_start: float = 0.0,
                     offered_kbps: int = 4500) -> list[Packet]:
    """Generate a traffic mix at a fixed aggregate offered rate (default 3x
    a 1500 kbps link so the router is overloaded). Each app contributes a
    fraction of packets proportional to its mix weight."""
    classes = list(mix.keys())
    weights = [mix[c] for c in classes]
    pkts: list[Packet] = []
    t = t_start
    avg_interarrival_ms = 1500 * 8 / offered_kbps   # ~2.67ms at 4500 kbps
    for seq in range(n_packets):
        cls = rng.choices(classes, weights=weights, k=1)[0]
        # Poisson-like arrival: exponential inter-arrival, clamped.
        gap = rng.expovariate(1.0 / avg_interarrival_ms)
        t += max(gap, 0.05)
        # policer marks ~20% of packets high-drop-precedence (out of contract)
        dp = 2 if rng.random() < 0.2 else 0
        pkts.append(Packet(seq, cls, round(t, 3), drop_precedence=dp))
    return pkts


# --------------------------------------------------------------------------- #
# Shedding policies                                                             #
# --------------------------------------------------------------------------- #


def _shed_random(queue: list[Packet], needed: int, cfg: RouterConfig,
                 rng: random.Random) -> list[Packet]:
    """Tail drop: drop arriving packets until the queue fits capacity."""
    dropped: list[Packet] = []
    while len(queue) > cfg.queue_capacity:
        p = queue.pop()
        p.dropped = True
        dropped.append(p)
    return dropped


def _shed_priority(queue: list[Packet], needed: int, cfg: RouterConfig,
                   rng: random.Random) -> list[Packet]:
    """Priority drop: shed elastic (wine = newest) first, then streaming,
    then real-time (milk = oldest within the class)."""
    dropped: list[Packet] = []
    overflow = len(queue) - cfg.queue_capacity
    if overflow <= 0:
        return dropped
    # Order classes from most-droppable to least-droppable.
    order = [ELASTIC, STREAMING, REAL_TIME]
    for cls in order:
        if overflow <= 0:
            break
        members = [p for p in queue if p.app is cls and not p.dropped]
        if cls.drop_policy == "wine":
            members.sort(key=lambda p: -p.seq)   # newest first
        else:                                       # milk / excess: oldest first
            members.sort(key=lambda p: p.seq)
        for p in members[:overflow]:
            p.dropped = True
            dropped.append(p)
            queue.remove(p)
            overflow -= 1
    return dropped


def _shed_red(queue: list[Packet], needed: int, cfg: RouterConfig,
              rng: random.Random) -> list[Packet]:
    """RED: drop a random fraction scaled by queue depth, preferring high
    drop-precedence packets within the affected class."""
    avg_depth = len(queue)
    if avg_depth < cfg.red_min_thresh:
        return []
    if avg_depth >= cfg.red_max_thresh:
        prob = cfg.red_max_drop_prob
    else:
        span = cfg.red_max_thresh - cfg.red_min_thresh
        prob = cfg.red_max_drop_prob * (avg_depth - cfg.red_min_thresh) / span
    dropped: list[Packet] = []
    for p in list(queue):
        if p.dropped:
            continue
        # High drop-precedence packets are 3x more likely to be dropped.
        weight = 1.0 + 2.0 * p.drop_precedence
        if rng.random() < prob * weight:
            p.dropped = True
            dropped.append(p)
            queue.remove(p)
    return dropped


POLICIES: dict[str, callable] = {
    "random": _shed_random,
    "priority": _shed_priority,
    "red": _shed_red,
}


# --------------------------------------------------------------------------- #
# Simulation driver                                                            #
# --------------------------------------------------------------------------- #


def simulate(cfg: RouterConfig, pkts: list[Packet]) -> dict[str, ClassStats]:
    rng = random.Random(42)
    stats: dict[str, ClassStats] = {c.name: ClassStats() for c in
                                     (REAL_TIME, STREAMING, ELASTIC)}
    shed_fn = POLICIES[cfg.policy]
    service_time = 1500 * 8 / cfg.link_kbps      # ms per packet at link rate
    queue: list[Packet] = []
    next_free = 0.0
    for p in pkts:
        stats[p.app.name].sent += 1
        # Drain all packets whose service finished before p arrives.
        while queue and next_free <= p.arrival:
            done = queue.pop(0)
            if not done.dropped:
                stats[done.app.name].delivered_delays.append(
                    max(next_free - done.arrival, 0.0) + service_time)
            next_free += service_time
        if next_free <= p.arrival:
            next_free = p.arrival
        queue.append(p)
        # Shed if over capacity.
        if len(queue) > cfg.queue_capacity:
            shed_fn(queue, len(queue) - cfg.queue_capacity, cfg, rng)
    # Drain remaining queue after last arrival.
    while queue:
        done = queue.pop(0)
        if not done.dropped:
            stats[done.app.name].delivered_delays.append(
                max(next_free - done.arrival, 0.0) + service_time)
        next_free += service_time
    # Count dropped.
    for p in pkts:
        if p.dropped:
            stats[p.app.name].dropped += 1
    return stats


def report(cfg: RouterConfig, stats: dict[str, ClassStats]) -> None:
    print(f"\n=== Policy: {cfg.policy} "
          f"(link {cfg.link_kbps} kbps, queue {cfg.queue_capacity} pkts) ===")
    print(f"{'class':<12}{'sent':>6}{'dropped':>9}{'loss':>8}"
          f"{'delay(ms)':>11}{'jitter(ms)':>12}  verdict")
    for cls in (REAL_TIME, STREAMING, ELASTIC):
        s = stats[cls.name]
        violations = cls.qos.violated(s.avg_delay, s.jitter, s.loss)
        verdict = "OK" if not violations else "VIOLATED: " + "; ".join(violations)
        print(f"{cls.name:<12}{s.sent:>6}{s.dropped:>9}{s.loss:>8.3f}"
              f"{s.avg_delay:>11.2f}{s.jitter:>12.2f}  {verdict}")


def main() -> int:
    rng = random.Random(7)
    mix = {REAL_TIME: 0.2, STREAMING: 0.3, ELASTIC: 0.5}
    pkts = generate_traffic(rng, n_packets=2000, mix=mix, offered_kbps=2100)
    print(f"Generated {len(pkts)} packets. "
          f"Mix: " + ", ".join(f"{c.name}={w:.0%}" for c, w in mix.items()))
    for policy in ("random", "priority", "red"):
        cfg = RouterConfig(policy=policy)
        stats = simulate(cfg, pkts)
        report(cfg, stats)

    # QoS classifier smoke test.
    print("\n=== QoS classifier ===")
    for app in ("telephony", "video_on_demand", "file_transfer", "web"):
        cls = classify(app)
        print(f"{app:<18}-> {cls.name:<10} dscp={cls.dscp:<10} "
              f"policy={cls.drop_policy:<7} "
              f"qos=(bw {cls.qos.bandwidth_kbps}kbps, "
              f"delay {cls.qos.delay_ms}ms, jitter {cls.qos.jitter_ms}ms, "
              f"loss {cls.qos.loss:.3f})")
    print("\nDone. exit 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
