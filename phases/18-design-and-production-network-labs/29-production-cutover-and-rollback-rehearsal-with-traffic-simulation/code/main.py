#!/usr/bin/env python3
"""Production cutover and rollback rehearsal with traffic simulation (Phase 18, Lesson 29).

Simulates a blue/green/canary cutover of an edge router pair. A synthetic traffic
generator emits request records against blue (current) and green (candidate) pools.
A weighted load balancer routes a configurable percent to each pool. The candidate
returns 2xx or 5xx at a configurable error rate. A SloGate auto-aborts on a
1-percent 5xx window, a /healthz probe aborts on 3 consecutive failures. Output
is a runbook-ready report and JSON.

Stdlib only: dataclasses, json, random, statistics.
Run: python3 main.py
"""
from __future__ import annotations

import json
import random
import statistics
from dataclasses import dataclass, field

@dataclass(frozen=True)
class HealthCheck:
    name: str
    interval_s: float = 1.0
    failure_threshold: int = 3

@dataclass(frozen=True)
class BackendPool:
    name: str
    instances: tuple[str, ...]
    base_error_rate: float
    base_latency_ms: float

    def synthetic_response(self, rng: random.Random) -> tuple[int, float]:
        latency = max(1.0, rng.gauss(self.base_latency_ms, self.base_latency_ms * 0.15))
        if rng.random() < self.base_error_rate:
            return (503 if rng.random() < 0.7 else 504), latency
        return 200, latency

@dataclass(frozen=True)
class CanaryStep:
    green_weight: int
    hold_s: float
    ramp_kind: str   # canary | abort | promote

@dataclass
class Runbook:
    change_id: str
    service: str
    steps: list[CanaryStep] = field(default_factory=list)
    error_budget_pct: float = 1.0
    window_s: float = 5.0
    min_requests: int = 50

# --- SloGate: sliding-window error budget ----------------------------------

class SloGate:
    def __init__(self, window_s: float, budget_pct: float, min_requests: int) -> None:
        self.window_s = window_s
        self.budget_pct = budget_pct
        self.min_requests = min_requests
        self.events: list[tuple[float, bool]] = []

    def record(self, t: float, status: int) -> None:
        self.events.append((t, status >= 500))
        cutoff = t - self.window_s
        self.events = [(ts, e) for ts, e in self.events if ts >= cutoff]

    def status(self) -> tuple[float, int]:
        n = len(self.events)
        if n == 0:
            return 0.0, 0
        errs = sum(1 for _, e in self.events if e)
        return (errs / n) * 100.0, n

    def should_rollback(self) -> tuple[bool, str]:
        rate, n = self.status()
        if n < self.min_requests:
            return False, f"warmup n={n}"
        if rate > self.budget_pct:
            return True, f"burned rate={rate:.2f}% n={n}"
        return False, f"ok rate={rate:.2f}% n={n}"

# --- Traffic generation and dispatch ---------------------------------------

def gen_arrivals(rps: int, duration_s: float, rng: random.Random) -> list[float]:
    n = int(rps * duration_s)
    if n <= 0:
        return []
    return [rng.expovariate(rps) for _ in range(n)]

def dispatch(arrivals: list[float], blue: BackendPool, green: BackendPool,
             green_weight: int, rng: random.Random) -> list[dict]:
    records: list[dict] = []
    t = 0.0
    for dt in arrivals:
        t += dt
        pool = green if rng.randint(1, 100) <= green_weight else blue
        status, latency = pool.synthetic_response(rng)
        records.append({"t_s": round(t, 4), "pool": pool.name,
                        "status": status, "latency_ms": round(latency, 2)})
    return records

# --- Cutover simulator -----------------------------------------------------

def simulate(runbook: Runbook, blue: BackendPool, green: BackendPool,
             rps: int, rng: random.Random) -> dict:
    gate = SloGate(runbook.window_s, runbook.error_budget_pct, runbook.min_requests)
    health = HealthCheck(name=f"{green.name}-http")
    consec_fail = 0
    last_health_t = -1.0
    timeline: list[dict] = []
    health_log: list[dict] = []
    current_weight = 0
    aborted = promoted = False
    abort_t: float | None = None
    promote_t: float | None = None
    wall = 0.0

    for step_idx, step in enumerate(runbook.steps):
        if aborted or promoted:
            break
        current_weight = step.green_weight
        records = dispatch(gen_arrivals(rps, step.hold_s, rng), blue, green, current_weight, rng)
        per_pool_lat: dict[str, list[float]] = {}
        step_summary: dict = {"step": step_idx, "green_weight_pct": current_weight,
                              "hold_s": step.hold_s, "requests": len(records),
                              "errors": 0, "by_pool": {}}
        for r in records:
            wall = max(wall, r["t_s"])
            gate.record(r["t_s"], r["status"])
            per_pool_lat.setdefault(r["pool"], []).append(r["latency_ms"])
            p = r["pool"]
            agg = step_summary["by_pool"].setdefault(p, {"n": 0, "errors": 0, "p50_ms": 0.0, "p95_ms": 0.0})
            agg["n"] += 1
            if r["status"] >= 500:
                step_summary["errors"] += 1
                agg["errors"] += 1
        for p, agg in step_summary["by_pool"].items():
            lats = sorted(per_pool_lat[p])
            if lats:
                agg["p50_ms"] = round(statistics.median(lats), 2)
                agg["p95_ms"] = round(lats[int(0.95 * (len(lats) - 1))], 2)
        if wall - last_health_t >= health.interval_s:
            last_health_t = wall
            consec_fail = 0 if rng.random() > green.base_error_rate * 4 else consec_fail + 1
            healthy = consec_fail < health.failure_threshold
            health_log.append({"t_s": round(wall, 2), "check": health.name,
                               "ok": healthy, "consec_failures": consec_fail})
            if not healthy:
                step_summary["healthcheck"] = "FAIL"
                aborted = True
                abort_t = wall
        trip, reason = gate.should_rollback()
        step_summary["slo_gate"] = reason
        if trip:
            aborted = True
            abort_t = wall
        timeline.append(step_summary)
        if step.ramp_kind == "promote" and not aborted:
            promoted = True
            promote_t = wall

    return {
        "change_id": runbook.change_id,
        "service": runbook.service,
        "final_weight_pct": current_weight,
        "aborted": aborted,
        "promoted": promoted,
        "abort_t_s": round(abort_t, 2) if abort_t is not None else None,
        "promote_t_s": round(promote_t, 2) if promote_t is not None else None,
        "wall_clock_s": round(wall, 2),
        "timeline": timeline,
        "health_log": health_log,
        "final_error_rate_pct": round(gate.status()[0], 3),
    }

# --- Runbook + main -------------------------------------------------------

def build_standard_runbook() -> Runbook:
    return Runbook(
        change_id="CHG-2025-04219",
        service="payments-edge-gateway",
        steps=[
            CanaryStep(1, 30.0, "canary"),
            CanaryStep(5, 60.0, "canary"),
            CanaryStep(25, 90.0, "canary"),
            CanaryStep(50, 120.0, "canary"),
            CanaryStep(100, 60.0, "promote"),
        ],
        error_budget_pct=1.0,
        window_s=5.0,
        min_requests=50,
    )

def main() -> None:
    rng = random.Random(20250625)
    blue = BackendPool("blue-v1", ("edge-b-1a", "edge-b-1b", "edge-b-1c"),
                       base_error_rate=0.002, base_latency_ms=42.0)
    green = BackendPool("green-v2", ("edge-g-2a", "edge-g-2b", "edge-g-2c"),
                        base_error_rate=0.015, base_latency_ms=38.0)
    report = simulate(build_standard_runbook(), blue, green, 200, rng)
    print("=" * 72)
    print(f"Change {report['change_id']} - service {report['service']}")
    print("=" * 72)
    print(f"  Final green weight : {report['final_weight_pct']}%")
    print(f"  Aborted            : {report['aborted']} (at t = {report['abort_t_s']} s)")
    print(f"  Promoted           : {report['promoted']} (at t = {report['promote_t_s']} s)")
    print(f"  Wall clock         : {report['wall_clock_s']} s")
    print(f"  Final 5xx rate     : {report['final_error_rate_pct']:.3f}%")
    print("  Step timeline:")
    for s in report["timeline"]:
        print(f"    step {s['step']}: weight={s['green_weight_pct']}% hold={s['hold_s']}s "
              f"reqs={s['requests']} errs={s['errors']} gate={s.get('slo_gate', '')} "
              f"hc={s.get('healthcheck', 'ok')}")
    print(f"  Health checks logged: {len(report['health_log'])}")
    print("---")
    print(json.dumps(report, indent=2))
if __name__ == "__main__":
    main()
