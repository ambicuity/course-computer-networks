#!/usr/bin/env python3
"""Datagram vs virtual-circuit service models — a side-by-side simulator.

Reproduces Tanenbaum & Wetherall §5.1.2-5.1.5 (Fig. 5-2, 5-3, 5-4) on the
six-router topology A-F. It forwards the same four-packet message through
both network-layer service models and proves their differences:

  * Connectionless (datagram): each packet routed independently, full
    destination address per packet, NO router state, packet 4 can diverge.
  * Connection-oriented (virtual circuit): one route chosen at setup, short
    label per packet, per-VC router state, label rewriting on collision.

A simulated failure of router C then demonstrates the key contrast from
Fig. 5-4: datagrams lose only in-flight packets, but every VC crossing the
dead router is torn down.

Pure standard library. No network calls. Run: python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field

# --- Topology (Fig. 5-2 / 5-3): adjacency of directly connected lines ------
# A router may only forward onto a directly connected line.
ADJACENCY: dict[str, set[str]] = {
    "A": {"B", "C"},
    "B": {"A", "D"},
    "C": {"A", "E"},
    "D": {"B", "E"},
    "E": {"C", "D", "F"},
    "F": {"E"},
}

# A's initial next-hop table (Fig. 5-2, "initially"): dest -> outgoing line.
A_TABLE_INITIAL: dict[str, str] = {"B": "B", "C": "C", "D": "B", "E": "C", "F": "C"}
# A's table "later" after learning of congestion on the A-C-E path.
A_TABLE_LATER: dict[str, str] = {"B": "B", "C": "C", "D": "B", "E": "B", "F": "B"}

# Static next-hop tables for the other routers toward destination F.
NEXT_HOP_TO_F: dict[str, str] = {"B": "D", "C": "E", "D": "E", "E": "F"}


@dataclass
class Router:
    """A router holds NO connection state in datagram mode; VC rows are added
    only when a virtual circuit is set up through it."""

    name: str
    up: bool = True
    # VC table: (in_line, in_label) -> (out_line, out_label)
    vc_table: dict[tuple[str, int], tuple[str, int]] = field(default_factory=dict)


def build_routers() -> dict[str, Router]:
    return {name: Router(name) for name in ADJACENCY}


# --- Datagram (connectionless) forwarding ----------------------------------
def datagram_next_hop(router: str, dest: str, a_table: dict[str, str]) -> str | None:
    """Independent next-hop lookup. Each packet carries the FULL dest address;
    routers keep no per-flow state."""
    if router == "A":
        return a_table.get(dest)
    return NEXT_HOP_TO_F.get(router) if dest == "F" else None


def forward_datagram(
    routers: dict[str, Router],
    dest: str,
    a_table: dict[str, str],
    failed: set[str],
) -> tuple[list[str], bool]:
    """Walk one datagram hop-by-hop from A to dest. Returns (path, delivered)."""
    path = ["A"]
    here = "A"
    for _ in range(12):  # loop guard
        if here in failed:
            return path, False  # lost: it was at the failed router
        if here == dest:
            return path, True
        nxt = datagram_next_hop(here, dest, a_table)
        if nxt is None or nxt not in routers:
            return path, False
        path.append(nxt)
        here = nxt
    return path, False


def run_datagram_demo(failed: set[str] | None = None) -> None:
    failed = failed or set()
    routers = build_routers()
    print("== Connectionless (datagram) forwarding, dest = F ==")
    print("Each packet routed independently; full dest address per packet.\n")
    # Packets 1-3 use A's initial table; packet 4 uses the rerouted "later" table.
    lost: list[int] = []
    for pid in (1, 2, 3):
        path, ok = forward_datagram(routers, "F", A_TABLE_INITIAL, failed)
        status = "delivered" if ok else "LOST"
        if not ok:
            lost.append(pid)
        print(f"  packet {pid}: {' -> '.join(path)}   [{status}]")
    path4, ok4 = forward_datagram(routers, "F", A_TABLE_LATER, failed)
    status4 = "delivered" if ok4 else "LOST"
    if not ok4:
        lost.append(4)
    note = "  <-- rerouted A->B (A learned of congestion on A-C-E)"
    print(f"  packet 4: {' -> '.join(path4)}   [{status4}]{note}")
    if failed:
        print(f"\n  Router(s) down: {sorted(failed)} -> only in-flight packets lost: {lost}")
    print()


# --- Virtual-circuit (connection-oriented) service -------------------------
def setup_virtual_circuit(
    routers: dict[str, Router],
    path: list[str],
    src_label: int,
    in_line_at_first: str,
) -> list[int]:
    """Install (in_line,in_label)->(out_line,out_label) rows along `path`,
    rewriting the label whenever the requested one is already used at a hop.
    Returns the per-hop outgoing labels actually assigned."""
    in_line = in_line_at_first
    in_label = src_label
    assigned: list[int] = []
    for i, name in enumerate(path):
        router = routers[name]
        out_line = path[i + 1] if i + 1 < len(path) else "host"
        # Pick an outgoing label free on this (router, out_line); relabel if needed.
        out_label = in_label
        used = {lbl for (ol, lbl) in router.vc_table.values() if ol == out_line}
        while out_label in used:
            out_label += 1  # relabel to avoid downstream clash (Fig. 5-3)
        router.vc_table[(in_line, in_label)] = (out_line, out_label)
        assigned.append(out_label)
        in_line, in_label = name, out_label
    return assigned


def run_vc_demo(failed: set[str] | None = None) -> None:
    failed = failed or set()
    routers = build_routers()
    print("== Connection-oriented (virtual-circuit) service, path A-C-E-F ==")
    print("Route chosen at setup; short label per packet; per-VC router state.\n")
    path = ["A", "C", "E", "F"]
    # H1 opens VC with label 1.
    setup_virtual_circuit(routers, path, src_label=1, in_line_at_first="H1")
    # H3 also opens a VC and also picks label 1 -> collision must be relabeled.
    setup_virtual_circuit(routers, path, src_label=1, in_line_at_first="H3")

    for name in path:
        r = routers[name]
        if not r.vc_table:
            continue
        print(f"  {name}'s VC table:")
        for (il, ilbl), (ol, olbl) in sorted(r.vc_table.items()):
            tag = "  <-- relabeled" if olbl != ilbl else ""
            print(f"      ({il:>2}, {ilbl}) -> ({ol:>4}, {olbl}){tag}")
    if failed:
        terminated = [name for name in path if name in failed]
        if terminated:
            print(f"\n  Router(s) down: {sorted(failed)} -> EVERY VC crossing them"
                  f" is torn down (path A-C-E-F includes {terminated}).")
            print("  Both circuits (H1 and H3) terminate; must re-signal.")
    print()


# --- Fig. 5-4 comparison ----------------------------------------------------
def print_comparison_table() -> None:
    rows = [
        ("Circuit setup", "Not needed", "Required before any data"),
        ("Addressing", "Full src+dest per packet", "Short VC number per packet"),
        ("Router state", "None about connections", "One entry per VC per router"),
        ("Routing", "Each packet independently", "Chosen at setup; all follow"),
        ("Router-failure effect", "Only in-flight packets lost", "All crossing VCs terminate"),
        ("QoS / congestion ctrl", "Difficult", "Easy if reserved in advance"),
    ]
    print("== Fig. 5-4: Datagram vs Virtual-Circuit ==")
    print(f"  {'Issue':<24}{'Datagram':<30}{'Virtual circuit'}")
    print("  " + "-" * 78)
    for issue, dg, vc in rows:
        print(f"  {issue:<24}{dg:<30}{vc}")
    print()


def main() -> None:
    print("Network-layer service models on the six-router topology A-F\n")
    print("--- Normal operation ---\n")
    run_datagram_demo()
    run_vc_demo()
    print("--- Inject failure: router C reboots ---\n")
    run_datagram_demo(failed={"C"})
    run_vc_demo(failed={"C"})
    print_comparison_table()
    print("Takeaway: same outage, opposite blast radius. The service model the")
    print("network layer hands the transport layer decides the impact.")


if __name__ == "__main__":
    main()
