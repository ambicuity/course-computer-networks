#!/usr/bin/env python3
"""Distance Vector Routing (distributed Bellman-Ford) simulator.

This stdlib-only program demonstrates the two mechanisms from the Network Layer
chapter's Distance Vector Routing section:

  1. relax_step()  -- one Bellman-Ford relaxation: rebuild a router's table from
     the cost to each neighbor plus the delay vectors received from neighbors.
     Reproduces router J's new table from Figure 5-9.

  2. count_to_infinity() -- the five-node linear topology of Figure 5-10. A
     destination goes down and we watch the metric climb one unit per exchange
     toward "infinity" (capped, as RIP caps it at 16). Optionally enables the
     split-horizon mitigation to show what it does and does not fix.

Run:  python3 main.py
No third-party dependencies, no network access.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

# RIP uses 16 as "infinity" (hop count) so the count-to-infinity loop
# terminates.  The Figure 5-9 delay example uses millisecond metrics that can
# exceed 16, so its relaxation uses a much larger ceiling.
RIP_INFINITY: int = 16
DELAY_INFINITY: int = 9999


@dataclass
class Entry:
    """One routing-table entry: best metric to a destination and the next hop."""

    metric: int
    next_hop: Optional[str]


# A received vector (what a neighbor advertises) is destination -> metric.
Vector = Dict[str, int]
Table = Dict[str, Entry]


def relax_step(
    neighbor_costs: Dict[str, int],
    received: Dict[str, Vector],
    infinity: int = DELAY_INFINITY,
) -> Table:
    """Run one Bellman-Ford relaxation for a single router.

    neighbor_costs: cost from this router to each directly connected neighbor.
    received:       neighbor -> (destination -> advertised metric) vector.
    infinity:       metric ceiling (unreachable marker).

    Returns a fresh table.  The router's OLD table is deliberately not consulted;
    only neighbor costs and freshly received vectors feed the computation.
    """
    destinations = {dest for vec in received.values() for dest in vec}
    table: Table = {}
    for dest in sorted(destinations):
        best_metric = infinity
        best_hop: Optional[str] = None
        for neigh, cost in neighbor_costs.items():
            advertised = received.get(neigh, {}).get(dest, infinity)
            candidate = min(cost + advertised, infinity)
            if candidate < best_metric:
                best_metric = candidate
                best_hop = neigh
        table[dest] = Entry(best_metric, best_hop)
    return table


def figure_5_9_demo() -> None:
    """Reproduce router J's new routing table from Figure 5-9.

    J's neighbors are A, I, H, K with measured delays 8, 10, 12, 6 msec.
    Each neighbor advertises a delay vector to every destination A..L.
    """
    neighbor_costs = {"A": 8, "I": 10, "H": 12, "K": 6}

    # Delay vectors received from J's four neighbors (Figure 5-9, part b).
    received: Dict[str, Vector] = {
        "A": {"A": 0, "B": 12, "C": 25, "D": 40, "E": 14, "F": 23,
              "G": 18, "H": 17, "I": 21, "J": 9, "K": 24, "L": 29},
        "I": {"A": 24, "B": 36, "C": 18, "D": 27, "E": 7, "F": 20,
              "G": 31, "H": 20, "I": 0, "J": 11, "K": 22, "L": 33},
        "H": {"A": 20, "B": 31, "C": 19, "D": 8, "E": 30, "F": 19,
              "G": 6, "H": 0, "I": 14, "J": 7, "K": 22, "L": 9},
        "K": {"A": 21, "B": 28, "C": 36, "D": 24, "E": 22, "F": 40,
              "G": 31, "H": 19, "I": 22, "J": 10, "K": 0, "L": 9},
    }

    table = relax_step(neighbor_costs, received)

    print("=" * 64)
    print("Figure 5-9: router J rebuilds its table (delay metric, msec)")
    print("J->neighbor delays:  A=8  I=10  H=12  K=6")
    print("=" * 64)
    print(f"{'Dest':<5}{'Metric':>7}{'NextHop':>9}   candidates (via A/I/H/K)")
    for dest in sorted(table):
        if dest == "J":
            continue
        cands: List[str] = []
        for n, c in neighbor_costs.items():
            adv = received[n].get(dest, DELAY_INFINITY)
            cands.append(f"{n}:{c + adv}")
        e = table[dest]
        print(f"{dest:<5}{e.metric:>7}{str(e.next_hop):>9}   {'  '.join(cands)}")

    g = table["G"]
    assert g.metric == 18 and g.next_hop == "H", "G should be 18 via H"
    print("\nCheck: J reaches G in 18 msec via H  (8+18=26 via A, 12+6=18 via H wins)")


# ---------------------------------------------------------------------------
# Count-to-infinity on a five-node line: A - B - C - D - E
# Each non-A router learns its distance to A from its adjacent neighbors.
# ---------------------------------------------------------------------------

LINE: List[str] = ["A", "B", "C", "D", "E"]


def neighbors_on_line(node: str) -> List[str]:
    """Return the directly adjacent routers of `node` on the linear topology."""
    i = LINE.index(node)
    out: List[str] = []
    if i > 0:
        out.append(LINE[i - 1])
    if i + 1 < len(LINE):
        out.append(LINE[i + 1])
    return out


def count_to_infinity(a_down: bool, split_horizon: bool, exchanges: int) -> None:
    """Trace each router's metric to destination A over several exchanges.

    a_down=True simulates A failing after the network had converged (bad news).
    a_down=False simulates A coming back up from an all-infinity state (good news).
    """
    dist: Dict[str, Tuple[int, Optional[str]]]
    if a_down:
        # Pre-failure converged state: B,C,D,E at 1,2,3,4 toward A; then A dies
        # so B can no longer reach A directly.
        dist = {
            "A": (RIP_INFINITY, None),  # A is gone
            "B": (1, "A"), "C": (2, "B"), "D": (3, "C"), "E": (4, "D"),
        }
    else:
        # A was down, now comes up (good news): everyone starts at infinity.
        dist = {n: (RIP_INFINITY, None) for n in LINE}
        dist["A"] = (0, None)

    label = "BAD NEWS (A goes down)" if a_down else "GOOD NEWS (A comes up)"
    sh = "  [split horizon ON]" if split_horizon else ""
    print("\n" + "=" * 64)
    print(f"Count-to-infinity on A-B-C-D-E: {label}{sh}")
    print("=" * 64)
    print("exchange   " + "  ".join(f"{n}:dA" for n in LINE))
    print("init       " + "  ".join(_fmt(dist[n][0]) for n in LINE))

    for ex in range(1, exchanges + 1):
        new_dist = dict(dist)
        for node in LINE:
            if node == "A":
                continue
            best = RIP_INFINITY
            best_hop: Optional[str] = None
            # A is directly reachable only if A is up and adjacent.
            if not a_down and "A" in neighbors_on_line(node):
                best, best_hop = 1, "A"
            for neigh in neighbors_on_line(node):
                if neigh == "A":
                    continue
                n_metric, n_hop = dist[neigh]
                # Split horizon: a neighbor does not advertise a route back over
                # the link it learned that route from.
                if split_horizon and n_hop == node:
                    continue
                cand = min(n_metric + 1, RIP_INFINITY)
                if cand < best:
                    best, best_hop = cand, neigh
            new_dist[node] = (best, best_hop)
        dist = new_dist
        print(f"after {ex:>2}   " + "  ".join(_fmt(dist[n][0]) for n in LINE))

    if a_down:
        print(f"Bad news rises +1 per exchange until the metric hits "
              f"INFINITY={RIP_INFINITY} and the route is declared unreachable.")
    else:
        print("Good news spreads one hop per exchange; converges in <= N rounds.")


def _fmt(metric: int) -> str:
    return " inf" if metric >= RIP_INFINITY else f"{metric:>4}"


def main() -> None:
    figure_5_9_demo()
    # Good news: A revives, truth spreads one hop per exchange.
    count_to_infinity(a_down=False, split_horizon=False, exchanges=4)
    # Bad news without mitigation: classic count-to-infinity.
    count_to_infinity(a_down=True, split_horizon=False, exchanges=8)
    # Bad news with split horizon: the 2-node bounce is suppressed.
    count_to_infinity(a_down=True, split_horizon=True, exchanges=8)


if __name__ == "__main__":
    main()
