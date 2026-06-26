#!/usr/bin/env python3
"""Dual-mode network-layer simulator: datagram vs virtual-circuit forwarding.

Reproduces the worked examples from Tanenbaum, *Computer Networks* 5e, sec.
5.1.3-5.1.5 (routers A-F, hosts H1/H2/H3).

- Datagram (connectionless): per-router (dest -> line) tables; packet 4
  reroutes after A's table updates (congestion on A-C).
- Virtual circuit (connection-oriented): a setup phase pins a route; tables map
  (in_line, in_id) -> (out_line, out_id). H3 reusing id 1 forces A to *swap*
  the outbound id to 2 -- label switching, as in MPLS (RFC 3031).
- Failure: a datagram crash loses only queued packets; a VC crash tears down
  every circuit through the failed router (Fig. 5-4).

Pure standard library. Run: python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# --- topology -------------------------------------------------------------
# Adjacency: which routers/hosts each router is directly connected to.
LINKS: dict[str, list[str]] = {
    "A": ["H1", "B", "C"],
    "B": ["A", "D"],
    "C": ["A", "E"],
    "D": ["B", "F"],
    "E": ["C", "F"],
    "F": ["D", "E", "H2"],
    "H3": ["A"],
}

IPV6_ADDR_BYTES = 16   # full destination address overhead per datagram (RFC 8200)
MPLS_LABEL_BITS = 20   # short VC identifier carried per VC packet (RFC 3031)


# =========================================================================
# Datagram (connectionless) network
# =========================================================================
DatagramTable = dict[str, str]  # destination -> outgoing line


def initial_datagram_tables() -> dict[str, DatagramTable]:
    """Per-router (dest -> next hop). Only directly connected lines may appear."""
    return {
        "A": {"B": "B", "C": "C", "D": "B", "E": "C", "F": "C"},
        "B": {"A": "A", "D": "D", "F": "D"},
        "C": {"A": "A", "E": "E", "F": "E"},
        "D": {"B": "B", "F": "F"},
        "E": {"C": "C", "F": "F"},
        "F": {"D": "D", "E": "E", "H2": "H2"},
    }


def reroute_a_after_congestion(tables: dict[str, DatagramTable]) -> None:
    """Routing algorithm updates A's table: A-C path congested, prefer B."""
    tables["A"]["C"] = "B"
    tables["A"]["E"] = "B"
    tables["A"]["F"] = "B"


def forward_datagram(
    tables: dict[str, DatagramTable],
    start: str,
    dest: str,
    crashed: Optional[set[str]] = None,
) -> tuple[list[str], bool]:
    """Hop-by-hop forwarding by destination lookup. Returns (path, delivered)."""
    crashed = crashed or set()
    path = [start]
    here = start
    # Bounded by network diameter to avoid loops on a corrupt table.
    for _ in range(len(LINKS) + 1):
        if here == dest:
            if here == "F":
                path.append("H2")
            return path, True
        if here in crashed:
            return path, False  # packet queued in a crashed router is lost
        table = tables.get(here)
        if table is None or dest not in table:
            return path, False
        nxt = table[dest]
        path.append(nxt)
        here = nxt
    return path, False


def run_datagram_demo() -> None:
    print("=" * 64)
    print("DATAGRAM (CONNECTIONLESS) NETWORK  -- IP-style, RFC 791 / 8200")
    print("=" * 64)
    tables = initial_datagram_tables()
    print(f"A's forwarding table (initial): {tables['A']}")

    # Packets 1-3 with the initial table.
    for pkt in (1, 2, 3):
        path, ok = forward_datagram(tables, "A", "F")
        print(f"  packet {pkt}: H1 -> {' -> '.join(path)}   delivered={ok}")

    # Congestion: routing algorithm rewrites A's table before packet 4.
    reroute_a_after_congestion(tables)
    print(f"A's forwarding table (later):   {tables['A']}")
    path, ok = forward_datagram(tables, "A", "F")
    print(f"  packet 4: H1 -> {' -> '.join(path)}   delivered={ok}  (rerouted!)")
    overhead = 4 * IPV6_ADDR_BYTES
    print(f"  per-packet dst-address overhead: {IPV6_ADDR_BYTES} B "
          f"(IPv6) -> {overhead} B across 4 packets")
    print()


# =========================================================================
# Virtual-circuit (connection-oriented) network
# =========================================================================
@dataclass
class VCTable:
    """Keyed by (in_line, in_id) -> (out_line, out_id) per router."""
    entries: dict[tuple[str, int], tuple[str, int]] = field(default_factory=dict)


def _free_outbound_id(
    vc_tables: dict[str, VCTable],
    router: str,
    out_line: str,
    preferred: int,
) -> int:
    """Smallest unused id on (router -> out_line); enables the label swap."""
    used = {
        out_id
        for (line, out_id) in vc_tables.get(router, VCTable()).entries.values()
        if line == out_line
    }
    candidate = preferred
    while candidate in used:
        candidate += 1
    return candidate


def setup_circuit(
    vc_tables: dict[str, VCTable],
    route: list[str],
    source: str,
    requested_id: int,
) -> list[tuple[str, int, str, int]]:
    """Pin a route into every router, swapping ids to avoid link collisions.

    Returns the list of installed entries as (router, in_id, out_line, out_id).
    """
    installed: list[tuple[str, int, str, int]] = []
    in_line = source
    in_id = requested_id
    for i, router in enumerate(route):
        out_line = route[i + 1] if i + 1 < len(route) else "H2"
        # Choose an outbound id that is free on this outgoing link.
        out_id = _free_outbound_id(vc_tables, router, out_line, preferred=in_id)
        vc_tables.setdefault(router, VCTable()).entries[(in_line, in_id)] = (
            out_line,
            out_id,
        )
        installed.append((router, in_id, out_line, out_id))
        in_line, in_id = router, out_id
    return installed


def forward_vc(
    vc_tables: dict[str, VCTable],
    start: str,
    source: str,
    vc_id: int,
    crashed: Optional[set[str]] = None,
) -> tuple[list[str], bool]:
    """Follow a pinned circuit by index-and-swap. Returns (path, delivered)."""
    crashed = crashed or set()
    path = [start]
    in_line, here, in_id = source, start, vc_id
    for _ in range(len(LINKS) + 1):
        if here in crashed:
            return path, False  # lost VC state -> circuit aborted
        entry = vc_tables.get(here, VCTable()).entries.get((in_line, in_id))
        if entry is None:
            return path, False
        out_line, out_id = entry
        path.append(out_line)
        if out_line == "H2":
            return path, True
        in_line, here, in_id = here, out_line, out_id
    return path, False


def run_vc_demo() -> dict[str, VCTable]:
    print("=" * 64)
    print("VIRTUAL-CIRCUIT (CONNECTION-ORIENTED) NETWORK -- MPLS-style")
    print("=" * 64)
    vc_tables: dict[str, VCTable] = {}
    route = ["A", "C", "E", "F"]

    print("Setup connection 1: H1 -> H2, requested id=1")
    e1 = setup_circuit(vc_tables, route, source="H1", requested_id=1)
    for router, in_id, out_line, out_id in e1:
        print(f"  {router}: in_id={in_id} -> out({out_line}, id={out_id})")

    print("Setup connection 2: H3 -> H2, also requests id=1 (collision risk)")
    e2 = setup_circuit(vc_tables, route, source="H3", requested_id=1)
    for router, in_id, out_line, out_id in e2:
        swap = "  <- SWAPPED" if in_id != out_id else ""
        print(f"  {router}: in_id={in_id} -> out({out_line}, id={out_id}){swap}")

    print(f"  short VC id is {MPLS_LABEL_BITS} bits (vs {IPV6_ADDR_BYTES}-B address)")
    path, ok = forward_vc(vc_tables, "A", "H1", 1)
    print(f"  data on conn1: {' -> '.join(path)}   delivered={ok}")
    path, ok = forward_vc(vc_tables, "A", "H3", 1)
    print(f"  data on conn2: {' -> '.join(path)}   delivered={ok}")
    print()
    return vc_tables


# =========================================================================
# Failure comparison (Fig. 5-4 "effect of router failures")
# =========================================================================
def run_failure_demo(vc_tables: dict[str, VCTable]) -> None:
    print("=" * 64)
    print("FAILURE: router C crashes and loses memory")
    print("=" * 64)
    crashed = {"C"}

    tables = initial_datagram_tables()
    reroute_a_after_congestion(tables)  # A already prefers B for F
    _, ok = forward_datagram(tables, "A", "F", crashed=crashed)
    print(f"  datagram flow to F (A prefers B): delivered={ok}  "
          f"-> survives, no per-flow state lost")

    _, ok1 = forward_vc(vc_tables, "A", "H1", 1, crashed=crashed)
    _, ok2 = forward_vc(vc_tables, "A", "H3", 1, crashed=crashed)
    print(f"  VC conn1 (A-C-E-F): delivered={ok1}  -> torn down (state in C lost)")
    print(f"  VC conn2 (A-C-E-F): delivered={ok2}  -> torn down (state in C lost)")
    print("  Verdict: datagrams reroute; every VC through C is aborted.")
    print()


def main() -> None:
    run_datagram_demo()
    vc_tables = run_vc_demo()
    run_failure_demo(vc_tables)


if __name__ == "__main__":
    main()
