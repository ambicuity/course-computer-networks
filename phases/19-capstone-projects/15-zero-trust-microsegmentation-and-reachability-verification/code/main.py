#!/usr/bin/env python3
"""Capstone 15: Zero Trust Microsegmentation and Reachability Verification.

Design a zero-trust microsegmentation policy for a 5-tier app, implement
a distributed firewall rule engine, simulate a reachability scanner, and
verify the policy enforces least privilege (default deny).

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Tier(Enum):
    LB = "load-balancer"; WEB = "web"; APP = "app"
    DB = "database"; CACHE = "cache"; MQ = "message-queue"; ADMIN = "admin"


class Action(Enum):
    ALLOW = "ALLOW"; DENY = "DENY"


@dataclass
class Workload:
    name: str; ip: str; tier: Tier; tags: list[str] = field(default_factory=list)
    ports: list[int] = field(default_factory=list)


@dataclass
class Rule:
    rid: str; src: Tier; dst: Tier; proto: str; port: int
    action: Action; desc: str = ""


@dataclass
class Flow:
    src_ip: str; dst_ip: str; proto: str; dst_port: int


@dataclass
class ScanRes:
    src: str; dst: str; port: int; action: Action; rule: str = ""


def build_workloads() -> dict[str, Workload]:
    return {
        "LB1":  Workload("LB1",  "10.1.0.10", Tier.LB,   ["edge"],      [443, 80]),
        "WEB1": Workload("WEB1", "10.1.1.11", Tier.WEB,  ["frontend"],  [8080]),
        "WEB2": Workload("WEB2", "10.1.1.12", Tier.WEB,  ["frontend"],  [8080]),
        "WEB3": Workload("WEB3", "10.1.1.13", Tier.WEB,  ["frontend"],  [8080]),
        "APP1": Workload("APP1", "10.1.2.21", Tier.APP,  ["backend"],   [8080]),
        "APP2": Workload("APP2", "10.1.2.22", Tier.APP,  ["backend"],   [8080]),
        "DB1":  Workload("DB1",  "10.1.3.31", Tier.DB,   ["sensitive"], [3306]),
        "DB2":  Workload("DB2",  "10.1.3.32", Tier.DB,   ["sensitive"], [3306]),
        "REDIS1": Workload("REDIS1", "10.1.4.41", Tier.CACHE, ["cache"], [6379]),
        "MQ1":  Workload("MQ1",  "10.1.5.51", Tier.MQ,   ["messaging"], [5672]),
        "BAS":  Workload("BAS",  "10.1.0.99", Tier.ADMIN,["admin"],     [22]),
    }


def build_policy() -> list[Rule]:
    return [
        Rule("R01", Tier.LB,    Tier.WEB,  "TCP", 8080, Action.ALLOW, "LB -> Web HTTP"),
        Rule("R02", Tier.WEB,   Tier.APP,  "TCP", 8080, Action.ALLOW, "Web -> App API"),
        Rule("R03", Tier.APP,   Tier.DB,   "TCP", 3306, Action.ALLOW, "App -> DB MySQL"),
        Rule("R04", Tier.APP,   Tier.CACHE,"TCP", 6379, Action.ALLOW, "App -> Redis"),
        Rule("R05", Tier.APP,   Tier.MQ,   "TCP", 5672, Action.ALLOW, "App -> AMQP"),
        Rule("R06", Tier.LB,    Tier.WEB,  "TCP", 443,  Action.ALLOW, "LB -> Web HTTPS"),
        Rule("R07", Tier.ADMIN, Tier.WEB,  "TCP", 22,   Action.ALLOW, "Bastion -> Web SSH"),
        Rule("R08", Tier.ADMIN, Tier.APP,  "TCP", 22,   Action.ALLOW, "Bastion -> App SSH"),
        Rule("R09", Tier.ADMIN, Tier.DB,   "TCP", 22,   Action.ALLOW, "Bastion -> DB SSH"),
        Rule("R10", Tier.ADMIN, Tier.DB,   "TCP", 3306, Action.ALLOW, "Bastion -> DB MySQL"),
        Rule("R11", Tier.APP,   Tier.APP,  "TCP", 8080, Action.ALLOW, "App <-> App"),
        Rule("R12", Tier.MQ,    Tier.APP,  "TCP", 8080, Action.ALLOW, "MQ -> App callback"),
        Rule("R13", Tier.LB,    Tier.LB,   "TCP", 443,  Action.ALLOW, "LB self-health"),
        Rule("R14", Tier.CACHE, Tier.APP,  "TCP", 8080, Action.ALLOW, "Redis -> App invalidate"),
    ]


def evaluate(req: Flow, pol: list[Rule], wls: dict[str, Workload]) -> tuple[Action, str]:
    src = next((w for w in wls.values() if w.ip == req.src_ip), None)
    dst = next((w for w in wls.values() if w.ip == req.dst_ip), None)
    if not src or not dst: return (Action.DENY, "no workload")
    for r in pol:
        if r.src == src.tier and r.dst == dst.tier and r.proto == req.proto \
           and (r.port == req.dst_port or r.port == 0):
            if r.action == Action.ALLOW: return (Action.ALLOW, r.rid)
    return (Action.DENY, "implicit deny (zero trust default)")


def scan(wls: dict[str, Workload], pol: list[Rule],
         ports: list[int]) -> list[ScanRes]:
    out: list[ScanRes] = []
    for s in wls.values():
        for d in wls.values():
            if s == d: continue
            for p in ports:
                if p not in d.ports: continue
                a, r = evaluate(Flow(s.ip, d.ip, "TCP", p), pol, wls)
                out.append(ScanRes(s.name, d.name, p, a, r))
    return out


def verify(res: list[ScanRes], wls: dict[str, Workload]) -> dict:
    bad: list[str] = []
    for r in res:
        if r.action == Action.ALLOW:
            s, d = wls[r.src], wls[r.dst]
            if s.tier == Tier.WEB and d.tier in (Tier.DB, Tier.CACHE):
                bad.append(f"OVER: {r.src}->{r.dst}:{r.port} should be DENY")
    return {"flows": len(res), "allow": sum(1 for r in res if r.action == Action.ALLOW),
            "deny": sum(1 for r in res if r.action == Action.DENY),
            "violations": bad, "ok": not bad}


def mistakes(pol: list[Rule]) -> list[dict]:
    out: list[dict] = []
    for r in pol:
        if r.port == 0:
            out.append({"r": r.rid, "sev": "HIGH", "msg": "wildcard port"})
        if r.port in (22, 3389) and r.src != Tier.ADMIN:
            out.append({"r": r.rid, "sev": "CRITICAL", "msg": f"admin port from {r.src.value}"})
        if r.dst == Tier.DB and r.src == Tier.WEB:
            out.append({"r": r.rid, "sev": "CRITICAL", "msg": "web -> db direct"})
    return out


def attack(wls: dict[str, Workload], pol: list[Rule]) -> list[dict]:
    out: list[dict] = []
    atk = wls["WEB1"]
    for tgt_name, port, desc in [
        ("DB1", 3306, "MySQL"), ("DB2", 3306, "MySQL"),
        ("REDIS1", 6379, "Redis"), ("MQ1", 5672, "AMQP"),
        ("APP2", 22, "SSH"), ("BAS", 22, "Bastion SSH"),
    ]:
        tgt = wls[tgt_name]
        a, r = evaluate(Flow(atk.ip, tgt.ip, "TCP", port), pol, wls)
        out.append({"t": tgt_name, "p": port, "d": desc, "a": a.value,
                    "res": "BLOCKED" if a == Action.DENY else "COMPROMISED"})
    return out


def main() -> None:
    print("=" * 65)
    print("Capstone 15: Zero Trust Microsegmentation")
    print("=" * 65)
    wls, pol = build_workloads(), build_policy()
    print(f"\n  Workloads: {len(wls)} across 5 tiers (+ LB, bastion)")
    print(f"  Policy:    {len(pol)} explicit allow rules (default: deny)")

    print(f"\n  --- Reachability Scan ---")
    res = scan(wls, pol, [22, 80, 443, 3306, 5672, 6379, 8080])
    v = verify(res, wls)
    print(f"  Total flows checked: {v['flows']}, allowed: {v['allow']}, denied: {v['deny']}")
    print(f"  Verification: {'COMPLIANT' if v['ok'] else 'VIOLATIONS'}")

    print(f"\n  Key flows (must be ALLOW):")
    for s, d, p, exp in [
        ("LB1", "WEB1", 8080, "ALLOW"), ("WEB1", "APP1", 8080, "ALLOW"),
        ("APP1", "DB1", 3306, "ALLOW"),  ("APP1", "REDIS1", 6379, "ALLOW"),
        ("BAS", "DB1", 3306, "ALLOW"),
    ]:
        sw, dw = wls[s], wls[d]
        a, r = evaluate(Flow(sw.ip, dw.ip, "TCP", p), pol, wls)
        ok = "OK" if a.value == exp else "FAIL"
        print(f"  {s:<6}-> {d:<6}:{p:<5} {a.value:<6} (rule {r:<5}) {ok}")

    print(f"\n  Forbidden flows (must be DENY):")
    for s, d, p in [("WEB1", "DB1", 3306), ("WEB1", "REDIS1", 6379),
                    ("WEB1", "BAS", 22),   ("WEB1", "APP2", 22)]:
        sw, dw = wls[s], wls[d]
        a, r = evaluate(Flow(sw.ip, dw.ip, "TCP", p), pol, wls)
        ok = "OK" if a == Action.DENY else "FAIL"
        print(f"  {s:<6}-> {d:<6}:{p:<5} {a.value:<6} {ok}")

    print(f"\n  --- Policy Mistakes ---")
    m = mistakes(pol)
    print(f"  Detected: {len(m)}" + (" (none)" if not m else ""))
    for x in m: print(f"    [{x['sev']}] {x['r']}: {x['msg']}")

    print(f"\n  --- Attack: compromised WEB1 attempts lateral movement ---")
    print(f"  {'Target':<8} {'Port':<6} {'Desc':<14} {'Action':<6} {'Result'}")
    blk = 0
    for a in attack(wls, pol):
        print(f"  {a['t']:<8} {a['p']:<6} {a['d']:<14} {a['a']:<6} {a['res']}")
        if a['res'] == "BLOCKED": blk += 1
    print(f"  {blk}/{len(attack(wls, pol))} attack attempts BLOCKED")

    print(f"\n  Summary: {len(pol)} allow rules across {len(wls)} workloads, {v['allow']}")
    print(f"    flows allowed out of {v['flows']} checked. Verification: {len(v['violations'])}")
    print(f"    violations. Attack from WEB1 blocked {blk}/{len(attack(wls,pol))}: web tier")
    print(f"    cannot reach DB, cache, or admin ports. Zero trust contains the blast radius.")


if __name__ == "__main__":
    main()
