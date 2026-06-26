#!/usr/bin/env python3
"""OSPF Multi-Area Convergence and LSA Throttling Simulator (Phase 18, Lesson 08).

Models a multi-area OSPFv2 topology per RFC 2328, counts LSA types per area,
simulates link failure and flap events, applies RFC 4136 throttling
(start / hold / max) and reports SPF run counts and convergence time.

Stdlib only: dataclasses, json.
Run: python3 main.py
"""
from __future__ import annotations

import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Router:
    name: str
    role: str   # internal | abr | asbr
    area: str


@dataclass(frozen=True)
class Link:
    a: str
    b: str
    cost: int
    area: str


@dataclass
class AreaSpec:
    id: str
    kind: str             # standard | stub | nssa
    routers: list[Router]
    links: list[Link]


@dataclass(frozen=True)
class Event:
    kind: str             # link_down | link_flap
    link: tuple[str, str]
    count: int = 1
    window_s: float = 0.0


@dataclass
class Throttle:
    start_ms: int = 50
    hold_ms: int = 200
    max_ms: int = 5000


TOPOLOGY: list[AreaSpec] = [
    AreaSpec("0.0.0.0", "standard", [
        Router("ABR-1", "abr", "0.0.0.0"), Router("ABR-2", "abr", "0.0.0.0"),
        Router("DC-CORE-1", "internal", "0.0.0.0"),
        Router("DC-CORE-2", "internal", "0.0.0.0"),
        Router("DC-EDGE-1", "asbr", "0.0.0.0"),
    ], [
        Link("ABR-1", "DC-CORE-1", 5, "0.0.0.0"),
        Link("ABR-2", "DC-CORE-2", 5, "0.0.0.0"),
        Link("DC-CORE-1", "DC-CORE-2", 2, "0.0.0.0"),
        Link("DC-EDGE-1", "DC-CORE-1", 4, "0.0.0.0"),
    ]),
    AreaSpec("0.0.0.1", "standard", [
        Router("ABR-1", "abr", "0.0.0.1"),
        Router("CAMPUS-E-1", "internal", "0.0.0.1"),
        Router("CAMPUS-E-2", "internal", "0.0.0.1"),
        Router("CAMPUS-E-3", "internal", "0.0.0.1"),
        Router("BR-ACCESS-1", "internal", "0.0.0.1"),
        Router("BR-ACCESS-2", "internal", "0.0.0.1"),
    ], [
        Link("ABR-1", "CAMPUS-E-1", 10, "0.0.0.1"),
        Link("CAMPUS-E-1", "CAMPUS-E-2", 8, "0.0.0.1"),
        Link("CAMPUS-E-1", "CAMPUS-E-3", 12, "0.0.0.1"),
        Link("CAMPUS-E-3", "BR-ACCESS-1", 15, "0.0.0.1"),
        Link("BR-ACCESS-1", "BR-ACCESS-2", 5, "0.0.0.1"),
    ]),
    AreaSpec("0.0.0.2", "stub", [
        Router("ABR-2", "abr", "0.0.0.2"),
        Router("CAMPUS-W-1", "internal", "0.0.0.2"),
        Router("CAMPUS-W-2", "internal", "0.0.0.2"),
        Router("CAMPUS-W-3", "internal", "0.0.0.2"),
        Router("CAMPUS-W-4", "internal", "0.0.0.2"),
    ], [
        Link("ABR-2", "CAMPUS-W-1", 10, "0.0.0.2"),
        Link("CAMPUS-W-1", "CAMPUS-W-3", 8, "0.0.0.2"),
        Link("CAMPUS-W-2", "CAMPUS-W-4", 8, "0.0.0.2"),
    ]),
]
EVENTS = [
    Event("link_down", ("BR-ACCESS-1", "BR-ACCESS-2")),
    Event("link_flap", ("BR-ACCESS-1", "BR-ACCESS-2"), 20, 60.0),
]
THROTTLE = Throttle()
TARGET_DC_MS = 200
TARGET_CAMPUS_MS = 1000


# --- LSDB computation ------------------------------------------------------

def lsdb_for(area: AreaSpec) -> dict[str, int]:
    is_bb = area.id == "0.0.0.0"
    has_abr = any(r.role == "abr" for r in area.routers)
    other_routers = sum(len(a.routers) for a in TOPOLOGY if a.id != area.id)
    internal = sum(1 for r in area.routers if r.role == "internal")
    t3 = min(other_routers, 8) * max(internal, 1) if has_abr else 0
    return {
        "type1_router": len(area.routers),
        "type2_network": len(area.links),
        "type3_summary": t3,
        "type4_asb": sum(1 for r in area.routers if r.role == "asbr"),
        "type5_external": 20 if is_bb else (0 if area.kind == "stub" else 5),
        "type7_nssa": 15 if area.kind == "nssa" else 0,
    }


def lsdb_total(db: dict[str, int]) -> int:
    return sum(db.values())


# --- Throttling and simulation ---------------------------------------------

def throttle_delay(idx: int, t: Throttle) -> int:
    d = t.start_ms
    for _ in range(idx):
        d = min(t.max_ms, d * 2)
    return d


def sim_link_down(area: AreaSpec) -> dict:
    full_spf = len(area.routers)
    partial = sum(
        len(o.routers) for o in TOPOLOGY
        if o.id != area.id and any(r.role == "abr" for r in area.routers)
    )
    wall_ms = 150 + THROTTLE.start_ms + 20 + 50 + 50
    return {"scenario": "link_down", "area": area.id, "full_spf": full_spf,
            "partial_spf": partial, "convergence_ms": wall_ms}


def sim_link_flap(area: AreaSpec, count: int, window_s: float) -> dict:
    full_per = len(area.routers)
    partial_per = sum(
        len(o.routers) for o in TOPOLOGY
        if o.id != area.id and any(r.role == "abr" for r in area.routers)
    )
    cumulative = 0.0
    last_evt = -10_000.0
    full_total = partial_total = 0
    for i in range(count):
        delay = throttle_delay(i, THROTTLE)
        if cumulative - last_evt < THROTTLE.hold_ms:
            sched = delay
        else:
            sched = THROTTLE.start_ms
        cumulative += sched
        last_evt = cumulative
        if cumulative > window_s * 1000.0:
            break
        full_total += full_per
        partial_total += partial_per
    return {"scenario": "link_flap", "area": area.id, "events": count,
            "full_spf": full_total, "partial_spf": partial_total,
            "wall_clock_ms": int(cumulative), "window_s": window_s}


# --- Verdict and report ----------------------------------------------------

def verdict(ms: int) -> str:
    if ms <= TARGET_DC_MS:
        return f"GREEN dc ({ms} ms <= {TARGET_DC_MS} ms)"
    if ms <= TARGET_CAMPUS_MS:
        return f"YELLOW campus ({ms} ms <= {TARGET_CAMPUS_MS} ms)"
    return f"RED (> {TARGET_CAMPUS_MS} ms)"


def refresh_rate(total_lsa: int, refresh_s: int = 1800) -> float:
    return total_lsa * (3600.0 / refresh_s) / 3600.0


def find_area_for(link_pair: tuple[str, str]) -> tuple[AreaSpec, Link] | None:
    for a in TOPOLOGY:
        for l in a.links:
            if {l.a, l.b} == set(link_pair):
                return a, l
    return None


def run() -> dict:
    lsdb = {a.id: lsdb_for(a) for a in TOPOLOGY}
    lsdb_totals = {k: lsdb_total(v) for k, v in lsdb.items()}
    sims = []
    for ev in EVENTS:
        found = find_area_for(ev.link)
        if not found:
            continue
        owner, _ = found
        if ev.kind == "link_down":
            sims.append(sim_link_down(owner))
        else:
            sims.append(sim_link_flap(owner, ev.count, ev.window_s))
    single = next((s for s in sims if s["scenario"] == "link_down"), {})
    return {
        "lsdb_per_area": lsdb,
        "lsdb_totals": lsdb_totals,
        "area0_total": lsdb_totals.get("0.0.0.0", 0),
        "simulations": sims,
        "verdict": verdict(single.get("convergence_ms", 0)) if single else "no event",
        "refresh_lsa_per_s": round(refresh_rate(sum(lsdb_totals.values())), 3),
        "throttle_ms": vars(THROTTLE),
        "targets_ms": {"dc": TARGET_DC_MS, "campus": TARGET_CAMPUS_MS},
    }


def main() -> None:
    r = run()
    print("=" * 68)
    print("OSPF Multi-Area Convergence and LSA Throttling Report")
    print("=" * 68)
    for area, db in r["lsdb_per_area"].items():
        print(f"  {area}: T1={db['type1_router']} T2={db['type2_network']} "
              f"T3={db['type3_summary']} T4={db['type4_asb']} "
              f"T5={db['type5_external']} T7={db['type7_nssa']} "
              f"total={r['lsdb_totals'][area]}")
    print()
    for s in r["simulations"]:
        if s["scenario"] == "link_down":
            print(f"link_down area {s['area']}: full SPF={s['full_spf']} "
                  f"partial={s['partial_spf']} conv={s['convergence_ms']} ms")
        else:
            print(f"link_flap area {s['area']}: events={s['events']} "
                  f"full SPF={s['full_spf']} partial={s['partial_spf']} "
                  f"wall={s['wall_clock_ms']} ms / {s['window_s']} s")
    print()
    print("Verdict:", r["verdict"])
    print(f"LSA refresh: {r['refresh_lsa_per_s']:.3f} LSA/s across network")
    print("---")
    print(json.dumps(r, indent=2))



if __name__ == "__main__":
    main()
