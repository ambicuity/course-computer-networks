#!/usr/bin/env python3
"""Capstone 16: sFlow / IPFIX Telemetry and Anomaly Pipeline.

Build a telemetry pipeline: generate synthetic flow records, aggregate
into time-series metrics, compute statistical baselines, detect
anomalies (spike / surge / distribution shift / DDoS), and produce alerts.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random
import math

random.seed(42)
NDEV = 5; NHOST = 50; DUR = 60; BUCKET = 1; BASEWIN = 30


class Proto(Enum):
    TCP = "TCP"; UDP = "UDP"; ICMP = "ICMP"; DNS = "DNS"


class Sev(Enum):
    INFO = "INFO"; WARNING = "WARNING"; CRITICAL = "CRITICAL"


@dataclass
class Flow:
    t: float; dev: str; src: str; dst: str; proto: Proto
    sport: int; dport: int; b: int; p: int; iface: str; dir: str


@dataclass
class Bucket:
    minute: int; bytes: int = 0; pkts: int = 0; flows: int = 0
    proto: dict[str, float] = field(default_factory=dict)
    top_src: dict[str, int] = field(default_factory=dict)


@dataclass
class Baseline:
    metric: str; mean: float; std: float; n: int

    @property
    def t3(self): return self.mean + 3 * self.std


@dataclass
class Anom:
    minute: int; metric: str; val: float; bl_m: float; bl_s: float
    sev: Sev; atype: str; desc: str; evidence: str = ""


def ip(h: int) -> str: return f"10.0.{h//256}.{h%256}"


def gen_normal(m: int) -> list[Flow]:
    rs: list[Flow] = []
    for _ in range(random.randint(4500, 5500)):
        s, d = random.randint(1, NHOST), random.randint(1, NHOST)
        while d == s: d = random.randint(1, NHOST)
        pr = random.choices([Proto.TCP, Proto.UDP, Proto.ICMP, Proto.DNS],
                            weights=[60, 25, 5, 10])[0]
        dp = 53 if pr == Proto.DNS else (random.choice([80, 443, 8080, 22, 3306])
             if pr == Proto.TCP else (random.choice([53, 123, 161, 6379])
             if pr == Proto.UDP else 0))
        bt = random.randint(100, 50000)
        rs.append(Flow(float(m), f"DEV-{random.randint(1, NDEV)}", ip(s), ip(d), pr,
                       random.randint(1024, 65535), dp, bt, max(1, bt//random.randint(100, 1500)),
                       f"eth{random.randint(0, 3)}", random.choice(["in", "out"])))
    return rs


def inj_spike(m: int) -> list[Flow]:  # 3x volume
    return [Flow(float(m), f"DEV-{random.randint(1, NDEV)}", ip(random.randint(1, NHOST)),
                 ip(random.randint(1, NHOST)), Proto.TCP, random.randint(1024, 65535),
                 random.choice([80, 443]), random.randint(1000, 100000), random.randint(1, 70),
                 f"eth{random.randint(0, 3)}", "out") for _ in range(15000)]


def inj_surge(m: int) -> list[Flow]:  # port scan
    a = ip(99)
    return [Flow(float(m), "DEV-1", a, ip(random.randint(1, NHOST)), Proto.TCP,
                 random.randint(1024, 65535), port, 60, 1, "eth0", "in")
            for port in range(1, 500)]


def inj_dns(m: int) -> list[Flow]:  # DNS amplification
    a = ip(99)
    return [Flow(float(m), f"DEV-{random.randint(1, NDEV)}", a, ip(random.randint(1, NHOST)),
                 Proto.DNS, random.randint(1024, 65535), 53, random.randint(200, 4000),
                 random.randint(1, 5), f"eth{random.randint(0, 3)}", "in") for _ in range(30000)]


def inj_ddos(m: int) -> list[Flow]:  # single-source flood
    a = ip(99)
    return [Flow(float(m), f"DEV-{random.randint(1, NDEV)}", a, ip(random.randint(1, NHOST)),
                 Proto.UDP, random.randint(1024, 65535), random.choice([53, 123, 80, 443]),
                 random.randint(100, 2000), random.randint(1, 5),
                 f"eth{random.randint(0, 3)}", "in") for _ in range(40000)]


def aggregate(rs: list[Flow], m: int) -> Bucket:
    b = Bucket(minute=m); pb: dict[str, int] = {}; sb: dict[str, int] = {}
    for r in rs:
        if int(r.t) != m: continue
        b.bytes += r.b; b.pkts += r.p; b.flows += 1
        pb[r.proto.value] = pb.get(r.proto.value, 0) + r.b
        sb[r.src] = sb.get(r.src, 0) + r.b
    tot = sum(pb.values()) or 1
    b.proto = {k: v/tot*100 for k, v in pb.items()}
    b.top_src = dict(sorted(sb.items(), key=lambda x: x[1], reverse=True)[:5])
    return b


def baseline(bs: list[Bucket], metric: str) -> Baseline:
    vs = [getattr(b, "bytes" if metric == "bytes" else "flows") for b in bs[-BASEWIN:]]
    if not vs: return Baseline(metric, 0, 0, 0)
    m = sum(vs)/len(vs)
    s = math.sqrt(sum((v-m)**2 for v in vs)/len(vs)) if len(vs) > 1 else 0
    return Baseline(metric, m, s, len(vs))


def detect(b: Bucket, bls: dict[str, Baseline], m: int) -> list[Anom]:
    out: list[Anom] = []
    bl = bls.get("bytes")
    if bl and bl.std > 0:
        d = (b.bytes - bl.mean) / bl.std
        if d > 3:
            out.append(Anom(m, "bytes", b.bytes, bl.mean, bl.std,
                Sev.CRITICAL if d > 5 else Sev.WARNING, "Traffic Spike",
                f"Traffic {b.bytes/1e6:.0f}MB is {d:.1f} sigma",
                f"bl={bl.mean/1e6:.0f}+/-{bl.std/1e6:.0f}MB"))
    blf = bls.get("flows")
    if blf and blf.mean > 0:
        r = b.flows / blf.mean
        if r > 5:
            out.append(Anom(m, "flows", b.flows, blf.mean, blf.std, Sev.CRITICAL,
                "Flow Surge", f"Flows {b.flows} = {r:.1f}x baseline", f"bl={blf.mean:.0f}"))
    if b.proto.get("DNS", 0) > 50:
        out.append(Anom(m, "dns", b.proto["DNS"], 10, 5, Sev.WARNING, "Protocol Shift",
            f"DNS at {b.proto['DNS']:.0f}% of total", f"dist={b.proto}"))
    if b.top_src and b.bytes > 0:
        ts = list(b.top_src.items())[0]
        if ts[1] / b.bytes > 0.5:
            out.append(Anom(m, "top_src", ts[1]/b.bytes*100, 5, 3, Sev.CRITICAL,
                "DDoS Pattern", f"{ts[0]} sends {ts[1]/b.bytes*100:.0f}%",
                f"{ts[0]}={ts[1]/1e6:.1f}MB of {b.bytes/1e6:.1f}MB"))
    return out


def main() -> None:
    print("=" * 65)
    print("Capstone 16: sFlow / IPFIX Telemetry and Anomaly Pipeline")
    print("=" * 65)
    all_recs: list[Flow] = []; bs: list[Bucket] = []; anoms: list[Anom] = []

    for m in range(DUR):
        recs = gen_normal(m)
        if m == 35:   recs.extend(inj_spike(m))
        elif m == 40: recs.extend(inj_surge(m))
        elif m == 45: recs.extend(inj_dns(m))
        elif m == 50: recs.extend(inj_ddos(m))
        all_recs.extend(recs)
        b = aggregate(recs, m); bs.append(b)
        if m >= 10:
            bls = {"bytes": baseline(bs, "bytes"), "flows": baseline(bs, "flows")}
            anoms.extend(detect(b, bls, m))

    print(f"\n  Generated {len(all_recs):,} flow records over {DUR} min, {NDEV} devices")
    print(f"  Anomalies injected at min 35 (spike), 40 (surge), 45 (DNS), 50 (DDoS)")

    print(f"\n  --- Time-series (selected minutes) ---")
    print(f"  {'Min':<4} {'MB':<7} {'Flows':<7} {'DNS%':<6} {'Top src':<14} {'Share'}")
    for b in bs:
        if b.minute in (0, 10, 20, 30, 34, 35, 36, 39, 40, 41, 44, 45, 46, 49, 50, 51, 59):
            ts = list(b.top_src.items())[0] if b.top_src else ("-", 0)
            sh = ts[1]/b.bytes*100 if b.bytes else 0
            print(f"  {b.minute:<4} {b.bytes/1e6:<7.1f} {b.flows:<7} "
                  f"{b.proto.get('DNS', 0):<6.0f} {ts[0]:<14} {sh:.0f}%")

    bl_b = baseline(bs[:30], "bytes")
    bl_f = baseline(bs[:30], "flows")
    print(f"\n  --- Baselines (first 30 min) ---")
    print(f"  bytes: mean {bl_b.mean/1e6:.1f} MB/min, std {bl_b.std/1e6:.1f} MB/min, 3-sigma {bl_b.t3/1e6:.1f}")
    print(f"  flows: mean {bl_f.mean:.0f}/min,    std {bl_f.std:.0f}/min,    3-sigma {bl_f.t3:.0f}")

    print(f"\n  --- Anomaly Alerts ({len(anoms)}) ---")
    print(f"  {'Min':<4} {'Sev':<10} {'Type':<18} {'Description'}")
    for a in anoms:
        print(f"  {a.minute:<4} {a.sev.value:<10} {a.atype:<18} {a.desc}")
        print(f"  {'':<4} {'':<10} {'':<18} {a.evidence}")

    crit = sum(1 for a in anoms if a.sev == Sev.CRITICAL)
    warn = sum(1 for a in anoms if a.sev == Sev.WARNING)
    print(f"\n  CRITICAL: {crit}, WARNING: {warn}")
    print(f"\n  Summary: collected {len(all_recs):,} records, baselined on {BASEWIN} min,")
    print(f"    detected {len(anoms)} anomalies ({crit} CRITICAL). Pipeline turns raw")
    print(f"    flow records into actionable alerts via statistical baseline comparison.")


if __name__ == "__main__":
    main()
