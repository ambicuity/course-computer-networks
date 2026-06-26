#!/usr/bin/env python3
"""Capstone 09: Build and Verify a BGP Route Reflector Topology.

Simulates a 12-router AS (65001) with two RRs, eight clients, two
non-clients, and three eBGP neighbor ASes. Verifies the three RR
advertisement rules (RFC 4456), runs BGP best-path selection (RFC 4271),
and compares session counts/convergence to a full-mesh iBGP design.

Run:  python3 main.py
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum


class PeerType(Enum):
    EBGP = "eBGP"
    IBGP_CLIENT = "iBGP-Client"
    IBGP_NONCLIENT = "iBGP-NonClient"
    IBGP_RR = "iBGP-RR"


class Origin(Enum):
    IGP = 0
    EGP = 1
    INCOMPLETE = 2


@dataclass
class PathAttributes:
    local_pref: int = 100
    as_path: list = field(default_factory=list)
    origin: Origin = Origin.IGP
    med: int = 0
    next_hop: str = ""
    originator_id: str = ""
    cluster_list: list = field(default_factory=list)


@dataclass
class BgpRoute:
    prefix: str
    attrs: PathAttributes
    learned_from: str
    learned_via: PeerType
    is_best: bool = False


@dataclass
class BgpPeer:
    peer_id: str
    peer_type: PeerType
    remote_as: int


@dataclass
class Router:
    router_id: str
    as_num: int
    is_rr: bool = False
    cluster_id: str = ""
    peers: list = field(default_factory=list)
    rib: dict = field(default_factory=dict)
    ebgp_routes: dict = field(default_factory=dict)


# ---------- Topology ----------
def build_topology() -> dict:
    """12 routers: 2 RRs (R1,R2), 8 clients (R3..R10), 2 non-clients (R11,R12)."""
    rs = {f"10.0.0.{i}": Router(f"10.0.0.{i}", 65001, is_rr=(i <= 2),
                                 cluster_id="10.0.0.255" if i <= 2 else "")
          for i in range(1, 13)}
    for k in (1, 2):
        rr = rs[f"10.0.0.{k}"]
        rr.peers += [BgpPeer(f"10.0.0.{3-k}", PeerType.IBGP_RR, 65001)]
        rr.peers += [BgpPeer(f"10.0.0.{i}", PeerType.IBGP_CLIENT, 65001) for i in range(3, 11)]
        rr.peers += [BgpPeer(f"10.0.0.{i}", PeerType.IBGP_NONCLIENT, 65001) for i in range(11, 13)]
    rs["10.0.0.1"].peers += [BgpPeer("10.1.0.1", PeerType.EBGP, 65002),
                              BgpPeer("10.1.0.2", PeerType.EBGP, 65003)]
    for i in range(3, 11):
        rs[f"10.0.0.{i}"].peers += [BgpPeer("10.0.0.1", PeerType.IBGP_RR, 65001),
                                     BgpPeer("10.0.0.2", PeerType.IBGP_RR, 65001)]
    for i in range(11, 13):
        rs[f"10.0.0.{i}"].peers += [BgpPeer("10.0.0.1", PeerType.IBGP_NONCLIENT, 65001),
                                     BgpPeer("10.0.0.2", PeerType.IBGP_NONCLIENT, 65001)]
    return rs


def inject_ebgp_routes(rs: dict) -> None:
    """Four eBGP-learned prefixes driving every best-path tie-breaker."""
    def _r(prefix, lp, as_path, med, nh, src, from_id):
        return BgpRoute(prefix, PathAttributes(lp, as_path, Origin.IGP, med, nh, src), from_id, PeerType.EBGP)
    rs["10.0.0.1"].ebgp_routes.update({
        "192.168.1.0/24": _r("192.168.1.0/24", 100, [65002], 0, "10.1.0.1", "10.0.0.1", "10.1.0.1"),
        "192.168.2.0/24": _r("192.168.2.0/24", 100, [65010, 65003], 50, "10.1.0.2", "10.0.0.1", "10.1.0.2"),
        "192.168.3.0/24": _r("192.168.3.0/24", 200, [65002], 100, "10.1.0.1", "10.0.0.1", "10.1.0.1"),
    })
    rs["10.0.0.12"].ebgp_routes["172.16.0.0/16"] = _r("172.16.0.0/16", 100, [65099], 0, "10.2.0.1", "10.0.0.12", "10.2.0.1")


# ---------- Best-path (RFC 4271 tie-breaker chain) ----------
def best_path_select(routes: list) -> BgpRoute:
    """BGP best-path: LP, AS-path length, origin, MED, eBGP-over-iBGP, router-ID, neighbor IP."""
    if len(routes) == 1:
        return routes[0]

    def key(r: BgpRoute):
        a = r.attrs
        ebgp = r.learned_via == PeerType.EBGP
        return (-a.local_pref, len(a.as_path), a.origin.value, a.med,
                0 if ebgp else 1, a.originator_id, r.learned_from)

    return min(routes, key=key)


# ---------- Three RR advertisement rules (RFC 4456) ----------
def should_reflect(route: BgpRoute, peer: BgpPeer) -> bool:
    if route.learned_via == PeerType.EBGP:
        return peer.peer_type in (PeerType.IBGP_CLIENT, PeerType.IBGP_NONCLIENT, PeerType.IBGP_RR)
    if route.learned_via == PeerType.IBGP_CLIENT:
        return peer.peer_type in (PeerType.IBGP_CLIENT, PeerType.IBGP_NONCLIENT, PeerType.IBGP_RR)
    if route.learned_via in (PeerType.IBGP_NONCLIENT, PeerType.IBGP_RR):
        return peer.peer_type == PeerType.IBGP_CLIENT
    return False


# ---------- Convergence ----------
def run_convergence(rs: dict, max_rounds: int = 10) -> dict:
    """Propagate routes round-by-round until no router learns a new route."""
    log: list = []
    for r in rs.values():
        for p, rt in r.ebgp_routes.items():
            r.rib.setdefault(p, []).append(rt)
    rounds_used = 0
    for rnd in range(1, max_rounds + 1):
        rounds_used = rnd
        changes = 0
        for rid, r in rs.items():
            if not r.is_rr:
                continue
            for prefix, routes in r.rib.items():
                best = next((x for x in routes if x.is_best), routes[0])
                for peer in r.peers:
                    if peer.peer_type == PeerType.EBGP or not should_reflect(best, peer):
                        continue
                    tgt = rs.get(peer.peer_id)
                    if not tgt or best.attrs.originator_id == tgt.router_id:
                        continue
                    if r.cluster_id and r.cluster_id in best.attrs.cluster_list:
                        continue
                    a = best.attrs
                    new_clusters = list(a.cluster_list) + ([r.cluster_id] if r.cluster_id else [])
                    via = PeerType.IBGP_CLIENT if best.learned_via != PeerType.EBGP else PeerType.EBGP
                    new_rt = BgpRoute(best.prefix, PathAttributes(a.local_pref, list(a.as_path),
                                                                   a.origin, a.med, a.next_hop,
                                                                   a.originator_id, new_clusters), rid, via)
                    if not any(rt.attrs.originator_id == new_rt.attrs.originator_id
                               for rt in tgt.rib.get(prefix, [])):
                        tgt.rib.setdefault(prefix, []).append(new_rt)
                        changes += 1
                        log.append(f"  Round {rnd}: {rid} -> {peer.peer_id} prefix={prefix} via={peer.peer_type.value}")
        for r in rs.values():
            for routes in r.rib.values():
                if len(routes) > 1:
                    bp = best_path_select(routes)
                    for rt in routes:
                        rt.is_best = (rt is bp)
        if changes == 0:
            log.append(f"  Round {rnd}: CONVERGED (no changes)")
            break
    return {"rounds": rounds_used, "log": log, "changes": sum(1 for l in log if "->" in l)}


# ---------- Session counts ----------
def full_mesh_count(n: int) -> int:
    return n * (n - 1) // 2


def count_sessions(rs: dict) -> dict:
    """Count iBGP (deduped) and eBGP sessions in the RR topology."""
    ibgp, ebgp = set(), 0
    for rid, r in rs.items():
        for p in r.peers:
            if p.peer_type == PeerType.EBGP:
                ebgp += 1
            else:
                ibgp.add(tuple(sorted([rid, p.peer_id])))
    return {"ibgp": len(ibgp), "ebgp": ebgp, "total": len(ibgp) + ebgp}


# ---------- Output writers ----------
def write_outputs(rs, result, rr_sess, fm):
    """Persist the four portfolio artifacts: topology, route tables, session comparison, runbook."""
    os.makedirs("outputs", exist_ok=True)
    pct = (fm - rr_sess["ibgp"]) / fm * 100
    topo = "AS 65001 topology (12 routers, cluster 10.0.0.255)\n" + \
        "".join(f"  {rid} [{'RR' if rs[rid].is_rr else 'R'}] cluster={rs[rid].cluster_id or '-'} peers={len(rs[rid].peers)}\n"
                for rid in sorted(rs))
    open("outputs/topology-diagram.txt", "w").write(topo)
    tables = "".join(
        f"\nRouter {rid}:\n" + "".join(
            f"  {p:<18} LP={rt.attrs.local_pref:<4} AS=[{' '.join(str(a) for a in rt.attrs.as_path)}] "
            f"ORIGIN={rt.attrs.origin.name:<10} MED={rt.attrs.med:<3} NH={rt.attrs.next_hop:<10} "
            f"BEST={'*' if rt.is_best else ' '}\n"
            for p in sorted(rs[rid].rib) for rt in rs[rid].rib[p])
        for rid in sorted(rs))
    open("outputs/route-tables.txt", "w").write(tables)
    open("outputs/session-comparison.txt", "w").write(
        f"full-mesh iBGP sessions: {fm}\n"
        f"route-reflector iBGP sessions: {rr_sess['ibgp']}\n"
        f"savings: {fm - rr_sess['ibgp']} ({pct:.0f}% reduction)\n"
        f"convergence (RR): {result['rounds']} rounds\n")
    open("outputs/convergence-trace.txt", "w").write("\n".join(result["log"]))
    open("outputs/path-selection-runbook.md", "w").write(
        "# BGP Best-Path Runbook\n\n"
        "1. Highest LOCAL_PREF wins.\n2. Shortest AS_PATH wins.\n"
        "3. Lowest ORIGIN code (IGP<EGP<Incomplete).\n4. Lowest MED wins.\n"
        "5. eBGP-learned beats iBGP-learned.\n6. Lowest ORIGINATOR_ID wins.\n"
        "7. Lowest neighbor IP wins.\n\n"
        "Route reflection (RFC 4456): eBGP-to-all, client-to-all, "
        "non-client-to-clients-only. Loop guard: ORIGINATOR_ID, CLUSTER_LIST.\n")


def main() -> None:
    print("=" * 65)
    print("Capstone 09: Build and Verify a BGP Route Reflector Topology")
    print("=" * 65)
    rs = build_topology()
    inject_ebgp_routes(rs)
    rr_n = sum(1 for r in rs.values() if r.is_rr)
    c_n = sum(1 for r in rs.values() if not r.is_rr
              and any(p.peer_type == PeerType.IBGP_RR for p in r.peers)
              and not any(p.peer_type == PeerType.IBGP_NONCLIENT for p in r.peers))
    nc_n = sum(1 for r in rs.values() if any(p.peer_type == PeerType.IBGP_NONCLIENT for p in r.peers)
               and not r.is_rr)
    print(f"\nAS 65001: {len(rs)} routers, {rr_n} RRs, {c_n} clients, {nc_n} non-clients, cluster 10.0.0.255")
    result = run_convergence(rs, max_rounds=10)
    sess = count_sessions(rs)
    fm = full_mesh_count(len(rs))
    pct = (fm - sess["ibgp"]) / fm * 100
    print(f"Convergence: {result['rounds']} rounds, {result['changes']} propagations")
    print(f"Full-mesh iBGP: {fm} | RR topology: {sess['ibgp']} iBGP + {sess['ebgp']} eBGP = {sess['total']}")
    print(f"Session savings: {fm - sess['ibgp']} ({pct:.0f}% reduction)")
    r1 = rs["10.0.0.1"]
    if "192.168.3.0/24" in r1.rib:
        bp = best_path_select(r1.rib["192.168.3.0/24"])
        print(f"Best 192.168.3.0/24 on R1: LP={bp.attrs.local_pref} AS=[{' '.join(str(a) for a in bp.attrs.as_path)}] "
              f"NH={bp.attrs.next_hop} ORIGINATOR={bp.attrs.originator_id}")
    write_outputs(rs, result, sess, fm)
    print("Wrote outputs/{topology-diagram,route-tables,session-comparison,convergence-trace,path-selection-runbook}")


if __name__ == "__main__":
    main()
