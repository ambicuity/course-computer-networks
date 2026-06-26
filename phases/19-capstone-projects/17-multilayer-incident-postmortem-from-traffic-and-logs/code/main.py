#!/usr/bin/env python3
"""Capstone 17: Multilayer Incident Postmortem from Traffic and Logs.

Correlate evidence from packet captures, syslog, application logs, and
BGP updates to reconstruct a 45-minute outage, identify the root cause
via causal chain analysis, and generate a postmortem document.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Layer(Enum):
    L2 = "L2"; L3 = "L3"; L4 = "L4"; L7 = "L7"; BGP = "BGP"; DNS = "DNS"


class Ev(Enum):
    BGP_WD = "BGP Withdrawal"; BGP_RE = "BGP Re-announce"
    BGP_CV = "BGP Convergence"; IF_FLAP = "Interface Flap"
    RST = "TCP Reset"; NX = "DNS NXDOMAIN"; DBF = "DB Fail"
    APE = "App Error"; RETRY = "Retry Storm"; OSPF = "OSPF Reconv"
    NMS = "Monitor Alert"; BHOLE = "Route Black Hole"; OK = "Recovery"


@dataclass
class E:
    t: float; src: str; L: Layer; et: Ev; d: str
    sev: str = "INFO"; dev: str = ""; ip: str = ""; det: str = ""


@dataclass
class Lk:
    c: E; e: E; rel: str; conf: float


def pcap() -> list[E]:
    es: list[E] = [
        E(5, "pcap", Layer.BGP, Ev.BGP_WD, "BGP withdraw 10.50.0.0/24", "CRITICAL",
          "core-1", "10.50.0.0/24", "best path lost"),
        E(12, "pcap", Layer.L3, Ev.BHOLE, "Packets to /24 -> null0", "CRITICAL",
          "core-1", "10.50.0.0/24", "no next-hop")]
    es += [E(15+i*0.5, "pcap", Layer.L4, Ev.RST, "TCP RST 10.50.0.10:3306", "ERROR",
             "core-1", "10.50.0.10", f"rst #{i+1}") for i in range(20)]
    es += [E(18, "pcap", Layer.DNS, Ev.NX, "DNS NXDOMAIN payments", "WARNING",
             "dns-1", "10.50.0.53", "unreachable"),
           E(105, "pcap", Layer.BGP, Ev.BGP_RE, "BGP re-announce /24", "INFO",
            "core-1", "10.50.0.0/24", "restored")]
    es += [E(120+i*2, "pcap", Layer.L4, Ev.OK, "TCP SYN-ACK 10.50.0.10", "INFO",
             "core-1", "10.50.0.10", f"hs #{i+1}") for i in range(5)]
    return es


def syslog() -> list[E]:
    return [E(3, "syslog", Layer.L2, Ev.IF_FLAP, "Gi0/1 flapped", "WARNING", "edge-1", "", "200ms"),
            E(5, "syslog", Layer.BGP, Ev.BGP_WD, "BGP reset after route-map", "CRITICAL", "core-1", "", "FILTER-PAYMENTS"),
            E(10, "syslog", Layer.L3, Ev.OSPF, "OSPF SPF 3 LSA", "WARNING", "core-1", "", "12ms"),
            E(25, "syslog", Layer.L7, Ev.NMS, "NMS: /24 unreachable", "CRITICAL", "nms-1", "10.50.0.0/24", "all probes failed"),
            E(120, "syslog", Layer.L7, Ev.OK, "NMS cleared: /24 ok", "INFO", "nms-1", "10.50.0.0/24", "all ok")]


def app() -> list[E]:
    return [E(20, "app", Layer.L7, Ev.DBF, "DB 10.50.0.10:3306 fail", "ERROR", "pay-1", "10.50.0.10", "ECONNREFUSED"),
            E(25, "app", Layer.L7, Ev.APE, "100% error rate", "CRITICAL", "pay-1", "", "retries out"),
            E(30, "app", Layer.L7, Ev.RETRY, "retry storm 5000/s", "CRITICAL", "pay-1", "10.50.0.10", "100ms"),
            E(35, "app", Layer.L7, Ev.APE, "tx TXN-98765 timeout", "ERROR", "pay-1", "", ""),
            E(130, "app", Layer.L7, Ev.OK, "DB restored, 0% err", "INFO", "pay-1", "10.50.0.10", "pool ok")]


def bgp() -> list[E]:
    return [E(4, "bgp", Layer.BGP, Ev.BGP_WD, "FILTER-PAYMENTS applied", "CRITICAL", "core-1", "", "denies /24"),
            E(5, "bgp", Layer.BGP, Ev.BGP_WD, "WITHDRAW 10.50.0.0/24", "CRITICAL", "core-1", "10.50.0.0/24", "no alt"),
            E(10, "bgp", Layer.BGP, Ev.BGP_CV, "BGP convergence", "WARNING", "core-1", "10.50.0.0/24", "FIB no route"),
            E(100, "bgp", Layer.BGP, Ev.BGP_RE, "FILTER-PAYMENTS removed", "INFO", "core-1", "", "operator removed"),
            E(105, "bgp", Layer.BGP, Ev.BGP_RE, "ANNOUNCE /24 restored", "INFO", "core-1", "10.50.0.0/24", "via 10.0.0.1")]


def merge(*ss: list[E]) -> list[E]:
    all_e: list[E] = []
    for s in ss: all_e.extend(s)
    all_e.sort(key=lambda e: e.t)
    return all_e


def link(parent: E, child: E, rel: str, conf: float) -> Lk | None:
    """Return a Lk if child is after parent within 10s, else None."""
    return Lk(parent, child, rel, conf) if child.t > parent.t and child.t - parent.t < 10 else None


def chain(tl: list[E]) -> list[Lk]:
    """Pattern: BGP_WD -> BHOLE -> RST -> DBF -> APE -> RETRY."""
    bws = [e for e in tl if e.et == Ev.BGP_WD and "WITHDRAW" in e.d.upper()]
    bhs = [e for e in tl if e.et == Ev.BHOLE]
    rsts = [e for e in tl if e.et == Ev.RST]
    dbs = [e for e in tl if e.et == Ev.DBF]
    aps = [e for e in tl if e.et == Ev.APE and "100%" in e.d]
    rss = [e for e in tl if e.et == Ev.RETRY]
    ls: list[Lk] = []
    if bws and bhs: ls.append(link(bws[0], bhs[0], "BGP withdraw -> black hole", 0.95))
    if bhs and rsts: ls.append(link(bhs[0], rsts[0], "black hole -> TCP RST", 0.90))
    if rsts and dbs: ls.append(Lk(rsts[0], dbs[0], "TCP RST -> DB fail", 0.85)) if dbs[0].t > rsts[0].t else None
    if dbs and aps: ls.append(Lk(dbs[0], aps[0], "DB fail -> app error", 0.90)) if aps[0].t > dbs[0].t else None
    if aps and rss: ls.append(Lk(aps[0], rss[0], "app error -> retry storm", 0.80)) if rss[0].t > aps[0].t else None
    return [x for x in ls if x is not None]


def root(tl: list[E], ls: list[Lk]) -> E:
    fx = {id(l.e) for l in ls}
    for e in tl:
        if id(e) not in fx and e.et in (Ev.BGP_WD, Ev.IF_FLAP): return e
    for e in tl:
        if e.sev == "CRITICAL": return e
    return tl[0]


PM_HEAD = ["# Postmortem: Payment Outage 2024-06-24 14:32 UTC", "",
           "## Summary", "  45-min complete outage, 100% error. Root cause:",
           "  BGP route-map withdrew /24 with payment DB -> black hole.", ""]
PM_CF = ["", "## Contributing Factors",
         "  - No BGP route change monitoring / alerting",
         "  - No automatic failover to different /24",
         "  - Aggressive retry timer (100ms) caused storm",
         "  - Route-map change without peer review",
         "  - DNS resolver in same /24 (correlated failure)",
         "", "## Impact", "  45 min, 100% error, ~50k failed transactions",
         "", "## Action Items",
         "  1. BGP route-map change monitoring + alerts",
         "  2. Multi-prefix DB failover (replica in different /24)",
         "  3. Retry: 1s exp backoff (not 100ms)",
         "  4. Peer review required for all BGP route-map changes",
         "  5. DNS resolvers in multiple prefixes",
         "  6. Synthetic payment probes every 10s",
         "  7. Route-map canary: one peer first, then roll out",
         "", "## Lessons Learned",
         "  - One route-map can black-hole an entire /24",
         "  - Correlated placement (DNS+DB same /24) amplifies outages",
         "  - Retry storms multiply damage",
         "  - BGP changes need code-style review/canary/rollback",
         "  - Multilayer evidence correlation = fast RCA"]


def pm(tl: list[E], ls: list[Lk], rc: E) -> str:
    L = PM_HEAD + [f"## Root Cause  (+{rc.t:.0f}s, {rc.L.value})",
                   f"  {rc.d}", f"  Details: {rc.det}", "", "## Causal Chain"]
    for x in ls:
        L.append(f"  {x.c.et.value} (+{x.c.t:.0f}s) -> {x.e.et.value} "
                 f"(+{x.e.t:.0f}s)  conf={x.conf:.0%}  {x.rel}")
    L += PM_CF + ["", "## Evidence",
                  f"  pcap {sum(1 for e in tl if e.src=='pcap')}  "
                  f"syslog {sum(1 for e in tl if e.src=='syslog')}  "
                  f"applog {sum(1 for e in tl if e.src=='app')}  "
                  f"bgp {sum(1 for e in tl if e.src=='bgp')}",
                  f"  Total: {len(tl)} events, {len(ls)} causal links"]
    return "\n".join(L)


def main() -> None:
    print("=" * 65)
    print("Capstone 17: Multilayer Incident Postmortem")
    print("=" * 65)
    p, s, a, b = pcap(), syslog(), app(), bgp()
    tl = merge(p, s, a, b)
    print(f"\n  Evidence: pcap {len(p)}, syslog {len(s)}, app {len(a)}, bgp {len(b)}")
    print(f"  Timeline: {len(tl)} events")

    print(f"\n  --- Correlated Timeline (key events) ---")
    print(f"  {'Time':<6} {'Src':<7} {'L':<5} {'Event':<20} {'Sev':<9} {'Desc'}")
    for e in tl:
        if e.et == Ev.RST and e.t > 18: continue
        if e.et == Ev.OK and e.t > 125: continue
        print(f"  +{e.t:<4.0f} {e.src:<7} {e.L.value:<5} {e.et.value:<20} "
              f"{e.sev:<9} {e.d[:50]}")

    ls = chain(tl)
    print(f"\n  --- Causal Chain ({len(ls)} links) ---")
    for l in ls:
        print(f"  {l.c.et.value} (+{l.c.t:.0f}s) -> {l.e.et.value} (+{l.e.t:.0f}s)  conf={l.conf:.0%}")
        print(f"    {l.rel}")

    rc = root(tl, ls)
    recs = [e for e in tl if e.et == Ev.OK]
    dur = (max(recs, key=lambda x: x.t).t - rc.t) / 60 if recs else 45
    print(f"\n  --- Root Cause ---")
    print(f"  +{rc.t:.0f}s [{rc.src}/{rc.L.value}] {rc.et.value}: {rc.d}")
    print(f"  Outage ~{dur:.0f} min, 100% error, ~50k failed txns")

    print(f"\n  --- Postmortem ---")
    for line in pm(tl, ls, rc).split("\n"):
        print(f"  {line}")

    print(f"\n  Summary: {len(tl)} events from 4 sources, {len(ls)} causal links.")
    print(f"    Root cause at +{rc.t:.0f}s: route-map withdrew /24 prefix.")


if __name__ == "__main__":
    main()
