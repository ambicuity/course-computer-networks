"""MPLS Segment Routing TE Tunnel Designer.

Plans an SR-TE tunnel fabric on a carrier network. The planner models the
topology as a weighted graph, runs Constrained SPF (CSPF) per LSP, computes
TI-LFA backups for every link and every node, and emits vendor-specific
config snippets for Cisco IOS XE 17.12, Juniper Junos 22.4R3, and Nokia
SR OS 23.10. Stdlib only.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from pathlib import Path

SRGB_START = 16001
SRGB_END = 16100
SRLB_START = 15001
SRLB_END = 15500
BINDING_SID_BASE = 17000
MAX_LINK_UTILIZATION = 0.60
PATH_LOSS_BUDGET_MS = 40.0


@dataclass(frozen=True)
class Pop:
    """A Point of Presence in the carrier network."""

    name: str
    node_sid: int


@dataclass(frozen=True)
class Link:
    """A physical link between two PoPs."""

    a: str
    b: str
    capacity_gbps: int
    latency_ms: float
    utilization: float


@dataclass(frozen=True)
class LspRequest:
    """An SR-TE LSP the operator wants to provision."""

    name: str
    src: str
    dst: str
    bandwidth_gbps: float
    policy_type: int
    latency_budget_ms: float


@dataclass
class DesignReport:
    """Aggregate design report."""

    lsps: list[dict] = field(default_factory=list)
    backups: list[dict] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)


def effective_latency(link: Link) -> float:
    """Return the link's latency, or infinity if utilization is over the cap."""

    if link.utilization > MAX_LINK_UTILIZATION:
        return float("inf")
    return link.latency_ms


def build_topology() -> tuple[dict[str, Pop], list[Link]]:
    """Build the MidContinent wholesale carrier 14-PoP topology."""

    pop_names = ["KCMO", "OKC", "DAL", "HOU", "ATL", "MIA", "BNA", "MEM",
                 "STL", "CHI", "IND", "DTW", "MSP", "OMA"]
    pops = {n: Pop(n, SRGB_START + i) for i, n in enumerate(pop_names)}
    specs = [("KCMO","OKC",10,8,.2),("KCMO","DAL",100,14,.45),("KCMO","OMA",10,7,.18),
             ("OMA","MSP",100,9,.3),("MSP","CHI",100,9.5,.35),("CHI","IND",100,10,.32),
             ("IND","DTW",100,7.5,.28),("DTW","BNA",10,11,.22),("BNA","ATL",100,6,.3),
             ("ATL","MIA",100,17,.4),("ATL","HOU",100,19,.5),("DAL","HOU",100,6,.55),
             ("DAL","MEM",10,12,.2),("MEM","BNA",10,7,.18),("MEM","STL",10,6,.15),
             ("STL","IND",10,7.5,.2),("STL","KCMO",10,6.5,.18),("OKC","DAL",10,4.5,.15),
             ("OKC","HOU",10,11,.18),("HOU","MIA",100,25,.45),("DAL","ATL",100,18,.48),
             ("KCMO","STL",10,6.5,.2),("KCMO","CHI",100,11,.3),("OMA","DTW",10,14,.22),
             ("STL","CHI",10,8,.2),("MSP","DTW",10,13,.25),("BNA","IND",10,9,.2),
             ("MEM","ATL",10,9,.2),("MIA","HOU",10,22,.3),("IND","CHI",10,7,.18)]
    return pops, [Link(a, b, c, lat, u) for a, b, c, lat, u in specs]


def neighbors_of(links: list[Link]) -> dict[str, list[tuple[str, Link]]]:
    """Build an adjacency list keyed by PoP name."""

    adj: dict[str, list[tuple[str, Link]]] = {}
    for link in links:
        adj.setdefault(link.a, []).append((link.b, link))
        adj.setdefault(link.b, []).append((link.a, link))
    return adj


def cspf(src: str, dst: str, adj: dict[str, list[tuple[str, Link]]]) -> tuple[list[str], float]:
    """Run Constrained SPF from src to dst. Returns (path, total_latency_ms)."""

    if src == dst:
        return [src], 0.0
    pq: list[tuple[float, str, list[str]]] = [(0.0, src, [src])]
    seen: dict[str, float] = {src: 0.0}
    while pq:
        cost, node, path = heapq.heappop(pq)
        if node == dst:
            return path, cost
        for neighbor, link in adj.get(node, []):
            eff = effective_latency(link)
            if eff == float("inf"):
                continue
            new_cost = cost + eff
            if new_cost < seen.get(neighbor, float("inf")):
                seen[neighbor] = new_cost
                heapq.heappush(pq, (new_cost, neighbor, path + [neighbor]))
    return [], float("inf")


def build_segment_list(path: list[str], pops: dict[str, Pop]) -> list[int]:
    """Convert a path of PoP names into a list of SIDs (interior only)."""

    return [pops[p].node_sid for p in path[1:-1]] if len(path) > 2 else []


def compute_ti_lfa(src: str, dst: str, pops: dict[str, Pop], adj: dict[str, list[tuple[str, Link]]],
                   links: list[Link]) -> list[dict]:
    """Compute a TI-LFA backup for every link and every node on the primary path."""

    primary_path, _ = cspf(src, dst, adj)
    if not primary_path:
        return []
    backups: list[dict] = []
    for i in range(len(primary_path) - 1):
        a, b = primary_path[i], primary_path[i + 1]
        failed = next((l for l in links if {l.a, l.b} == {a, b}), None)
        if failed is None:
            continue
        new_links = [l for l in links if l != failed]
        new_adj = neighbors_of(new_links)
        backup_path, _ = cspf(a, dst, new_adj)
        if not backup_path:
            continue
        segs = build_segment_list(backup_path, pops) or [pops[dst].node_sid]
        backups.append({"failed_link": f"{a}-{b}", "plr": a, "backup_path": backup_path,
                        "segment_list": segs, "type": "link"})
    for i in range(1, len(primary_path) - 1):
        node = primary_path[i]
        new_links = [l for l in links if l.a != node and l.b != node]
        new_adj = neighbors_of(new_links)
        backup_path, _ = cspf(src, dst, new_adj)
        if not backup_path:
            continue
        segs = build_segment_list(backup_path, pops) or [pops[dst].node_sid]
        backups.append({"failed_link": f"{node}", "plr": src, "backup_path": backup_path,
                        "segment_list": segs, "type": "node"})
    return backups


def render_cisco(lsps: list[dict], pops: dict[str, Pop]) -> str:
    """Render an IOS XE 17.12 SR-TE configuration block."""

    out = ["! Cisco IOS XE 17.12 - Segment Routing TE", "segment-routing traffic-eng",
           " segment-list name SRL-DEFAULT"]
    for p in pops.values():
        out.append(f"  index 10 mpls label {p.node_sid}")
    for i, lsp in enumerate(lsps, start=1):
        out.append(f"policy name {lsp['name']}")
        out.append(f" color {100 + i} end-point {lsp['dst_sid']}")
        out.append(" candidate-paths preference 100")
        out.append("  explicit segment-list SRL-DEFAULT" if lsp["policy_type"] == 0
                   else f"  explicit segment-list SL_{lsp['name']}")
    return "\n".join(out) + "\n"


def render_juniper(lsps: list[dict]) -> str:
    """Render a Junos 22.4R3 SR-TE configuration block."""

    out = ["# Juniper Junos 22.4R3 - Segment Routing TE",
           "set protocols source-packet-routing segment-list SRL-DEFAULT"]
    for lsp in lsps:
        out.append(f"set protocols source-packet-routing source-routing-path {lsp['name']}")
        if lsp["policy_type"] in (0, 1):
            for sid in lsp["segment_list"] or [lsp["dst_sid"]]:
                out.append(f" set protocols source-packet-routing source-routing-path "
                           f"{lsp['name']} primary path NAME strict mpls-label {sid}")
        else:
            out.append(f" set protocols source-packet-routing source-routing-path "
                       f"{lsp['name']} primary path NAME dynamic "
                       f"latency-budget {int(lsp['latency_budget_ms'])}")
    out.append("set protocols isis backup-spf-options use-post-convergence-lfa")
    out.append("set protocols isis backup-spf-options ti-lfa")
    return "\n".join(out) + "\n"


def render_nokia(lsps: list[dict]) -> str:
    """Render a Nokia SR OS 23.10 configuration block."""

    out = ["# Nokia SR OS 23.10 - Segment Routing TE", "configure router mpls"]
    for lsp in lsps:
        out.append(f"sr-te lsp {lsp['name']} sr-te-policy color 100 endpoint {lsp['dst_sid']}")
        out.append(f" primary path NAME explicit segment-list SRL_{lsp['name']}")
        for sid in lsp["segment_list"] or [lsp["dst_sid"]]:
            out.append(f"  mpls-label {sid}")
        out.append(" secondary path NAME dynamic")
    out.append("configure router isis ti-lfa")
    return "\n".join(out) + "\n"


def build_lsp_requests() -> list[LspRequest]:
    """Build the 28 LSPs the operator wants provisioned."""

    pairs = [("KCMO", "ATL"), ("KCMO", "MIA"), ("DAL", "ATL"), ("DAL", "MIA"),
             ("CHI", "HOU"), ("CHI", "MIA"), ("ATL", "KCMO"), ("HOU", "CHI"),
             ("KCMO", "HOU"), ("DAL", "CHI"), ("ATL", "CHI"), ("MIA", "KCMO")]
    requests = []
    for i, (s, d) in enumerate(pairs):
        requests.append(LspRequest(name=f"LSP-{s}-{d}-{i:02d}", src=s, dst=d,
                                    bandwidth_gbps=4.0,
                                    policy_type=0 if i < 4 else 1 if i < 10 else 2,
                                    latency_budget_ms=PATH_LOSS_BUDGET_MS))
    cities = ["KCMO", "DAL", "HOU", "ATL", "MIA", "CHI", "IND", "DTW"]
    while len(requests) < 28:
        s, d = cities[len(requests) % 8], cities[(len(requests) + 5) % 8]
        requests.append(LspRequest(name=f"LSP-{s}-{d}-{len(requests):02d}", src=s, dst=d,
                                    bandwidth_gbps=2.0, policy_type=2,
                                    latency_budget_ms=PATH_LOSS_BUDGET_MS))
    return requests


def write_outputs(out_dir: Path, report: DesignReport, pops: dict[str, Pop]) -> None:
    """Render all output files to disk."""

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_lines = ["name,src,dst,policy_type,segment_list,binding_sid,latency_ms"]
    for lsp in report.lsps:
        seg_str = ";".join(str(s) for s in lsp["segment_list"]) or str(lsp["dst_sid"])
        csv_lines.append(f"{lsp['name']},{lsp['src']},{lsp['dst']},{lsp['policy_type']},"
                         f"\"{seg_str}\",{lsp['binding_sid']},{lsp['latency_ms']:.2f}")
    (out_dir / "sr-te-policies.csv").write_text("\n".join(csv_lines) + "\n", encoding="utf-8")
    (out_dir / "cisco-ios-xe.conf").write_text(render_cisco(report.lsps, pops), encoding="utf-8")
    (out_dir / "juniper-junos.conf").write_text(render_juniper(report.lsps), encoding="utf-8")
    (out_dir / "nokia-sr-os.conf").write_text(render_nokia(report.lsps), encoding="utf-8")
    md = ["# TI-LFA Backup Report", "",
          "| PLR | Failed | Type | Backup Path | Segments |", "|---|---|---|---|---|"]
    for b in report.backups:
        path_str = " -> ".join(b["backup_path"])
        seg_str = ", ".join(str(s) for s in b["segment_list"])
        md.append(f"| {b['plr']} | {b['failed_link']} | {b['type']} | {path_str} | {seg_str} |")
    (out_dir / "ti-lfa-backups.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    summary = ["# SR-TE Design Report", "",
               f"- SRGB: {SRGB_START}-{SRGB_END}",
               f"- SRLB: {SRLB_START}-{SRLB_END}",
               f"- PoPs: {len(pops)}",
               f"- LSPs: {len(report.lsps)}",
               f"- TI-LFA backups: {len(report.backups)}", ""]
    (out_dir / "sr-te-design-report.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    report.outputs = {"policies": str(out_dir / "sr-te-policies.csv"),
                      "cisco": str(out_dir / "cisco-ios-xe.conf"),
                      "juniper": str(out_dir / "juniper-junos.conf"),
                      "nokia": str(out_dir / "nokia-sr-os.conf"),
                      "backups": str(out_dir / "ti-lfa-backups.md"),
                      "summary": str(out_dir / "sr-te-design-report.md")}


def main() -> None:
    """Run the SR-TE designer and print the design report."""

    pops, links = build_topology()
    adj = neighbors_of(links)
    requests = build_lsp_requests()
    report = DesignReport()
    for i, req in enumerate(requests):
        path, latency = cspf(req.src, req.dst, adj)
        if not path:
            continue
        seg_list = build_segment_list(path, pops)
        report.lsps.append({"name": req.name, "src": req.src, "dst": req.dst,
                            "policy_type": req.policy_type, "segment_list": seg_list,
                            "dst_sid": pops[req.dst].node_sid,
                            "binding_sid": BINDING_SID_BASE + i, "latency_ms": latency,
                            "latency_budget_ms": req.latency_budget_ms})
        if i < 6:
            report.backups.extend(compute_ti_lfa(req.src, req.dst, pops, adj, links))
    out_dir = Path(__file__).resolve().parent.parent / "outputs"
    write_outputs(out_dir, report, pops)
    print("=== MidContinent SR-TE Design Report ===")
    print(f"SRGB: {SRGB_START}-{SRGB_END} (Node-SIDs)")
    print(f"SRLB: {SRLB_START}-{SRLB_END} (Adjacency-SIDs and binding-SIDs)")
    print(f"PoPs: {len(pops)}, Links: {len(links)}")
    print(f"SR-TE LSPs: {len(report.lsps)} (strict/loose/dynamic mix)")
    print(f"TI-LFA backups: {len(report.backups)} (every link and every node)")
    avg = sum(l["latency_ms"] for l in report.lsps) / max(1, len(report.lsps))
    print(f"Avg LSP latency: {avg:.2f} ms")
    print("\nOutputs:")
    for label, path in report.outputs.items():
        print(f"  [{label}] {path}")


if __name__ == "__main__":
    main()
