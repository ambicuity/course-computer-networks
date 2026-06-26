"""Distance Vector Failure Lab to Link State Flooding Lab.

Stdlib-only simulator: count-to-infinity, split horizon with poisoned reverse,
and link-state flooding with sequence-number de-duplication + Dijkstra SPF.

Run:  python3 main.py   (exits 0)
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

INFINITY: int = 16  # RIP's magic metric: anything >= 16 is unreachable.


# ---------------------------------------------------------------------------
# Distance-vector node
# ---------------------------------------------------------------------------

@dataclass
class DVNode:
    """A distance-vector router running Bellman-Ford."""

    name: str
    neighbors: Dict[str, int] = field(default_factory=dict)  # neighbor -> link cost
    table: Dict[str, Tuple[int, Optional[str]]] = field(default_factory=dict)
    # table[dest] = (cost, next_hop)

    def init_self(self) -> None:
        self.table[self.name] = (0, None)
        for nbr, cost in self.neighbors.items():
            self.table[nbr] = (cost, nbr)

    def advertise(self, to_neighbor: str, poison: bool) -> Dict[str, int]:
        """Build the vector to send to `to_neighbor`.

        poison=False: naive — advertise every route at its real cost (no
        split horizon). poison=True: split horizon with poisoned reverse —
        routes learned via `to_neighbor` are echoed back at cost INFINITY.
        """
        vec: Dict[str, int] = {}
        for dest, (cost, nhop) in self.table.items():
            if nhop == to_neighbor and poison:
                vec[dest] = INFINITY
            else:
                vec[dest] = cost
        return vec

    def receive(self, from_neighbor: str, vec: Dict[str, int]) -> bool:
        """Bellman-Ford update; return True if the table changed."""
        if from_neighbor not in self.neighbors:
            return False
        link_cost = self.neighbors[from_neighbor]
        changed = False
        for dest, adv_cost in vec.items():
            if adv_cost >= INFINITY:
                if dest in self.table and self.table[dest][1] == from_neighbor:
                    if self.table[dest] != (INFINITY, from_neighbor):
                        self.table[dest] = (INFINITY, from_neighbor)
                        changed = True
                continue
            new_cost = link_cost + adv_cost
            if new_cost >= INFINITY:
                new_cost = INFINITY
            cur_cost, cur_nhop = self.table.get(dest, (INFINITY, None))
            if new_cost < cur_cost:
                self.table[dest] = (new_cost, from_neighbor)
                changed = True
            elif from_neighbor == cur_nhop and new_cost != cur_cost:
                self.table[dest] = (new_cost, from_neighbor)
                changed = True
        return changed


# ---------------------------------------------------------------------------
# Demo 1: count-to-infinity on A-B-C
# ---------------------------------------------------------------------------

def _dv_round(nodes: Dict[str, DVNode], poison: bool) -> bool:
    """One Bellman-Ford round (synchronous snapshot). Each node advertises its
    pre-round vector; receivers then update. This models periodic 30s updates
    where all vectors cross in flight — the condition that produces
    count-to-infinity."""
    advs: Dict[str, Dict[str, Dict[str, int]]] = {}
    for name, node in nodes.items():
        advs[name] = {}
        for nbr in node.neighbors:
            advs[name][nbr] = node.advertise(nbr, poison=poison)
    changed_any = False
    for name, node in nodes.items():
        for nbr, vec in advs.get(name, {}).items():
            if nodes[nbr].receive(name, vec):
                changed_any = True
    return changed_any


def run_count_to_infinity() -> None:
    print("=" * 70)
    print("DEMO 1: count-to-infinity (naive distance-vector, no fixes)")
    print("=" * 70)
    print("Topology: A --1-- B --1-- C   |   link A-B fails at round 0\n")

    A = DVNode("A", neighbors={"B": 1})
    B = DVNode("B", neighbors={"A": 1, "C": 1})
    C = DVNode("C", neighbors={"B": 1})
    nodes = {"A": A, "B": B, "C": C}
    for n in nodes.values():
        n.init_self()

    # Run to steady state before the failure.
    for _ in range(10):
        if not _dv_round(nodes, poison=False):
            break

    print(f"{'Round':>5} | {'B->A':>10} | {'C->A':>10} | comment")
    print("-" * 55)
    b_cost = B.table.get("A", (INFINITY, None))[0]
    c_cost = C.table.get("A", (INFINITY, None))[0]
    print(f"{'init':>5} | {b_cost:>10} | {c_cost:>10} | steady state")

    # Fail the A-B link.
    del B.neighbors["A"]
    del A.neighbors["B"]
    B.table["A"] = (INFINITY, None)

    rounds = 0
    while rounds < 40:
        _dv_round(nodes, poison=False)

        rounds += 1
        b_cost = B.table.get("A", (INFINITY, None))[0]
        c_cost = C.table.get("A", (INFINITY, None))[0]
        b_via = B.table.get("A", (INFINITY, None))[1] or "-"
        c_via = C.table.get("A", (INFINITY, None))[1] or "-"
        climbing = min(b_cost, c_cost)
        print(f"{rounds:>5} | {str(b_cost)+' via '+str(b_via):>10} | "
              f"{str(c_cost)+' via '+str(c_via):>10} | "
              f"{'converged' if climbing >= INFINITY else f'min={climbing} climbing'}")
        if b_cost >= INFINITY and c_cost >= INFINITY:
            break
    print(f"\nRounds to converge: {rounds}\n")


# ---------------------------------------------------------------------------
# Demo 2: split horizon with poisoned reverse on the same failure
# ---------------------------------------------------------------------------

def run_split_horizon() -> None:
    print("=" * 70)
    print("DEMO 2: split horizon + poisoned reverse")
    print("=" * 70)
    print("Topology: A --1-- B --1-- C   |   link A-B fails at round 0\n")

    A = DVNode("A", neighbors={"B": 1})
    B = DVNode("B", neighbors={"A": 1, "C": 1})
    C = DVNode("C", neighbors={"B": 1})
    nodes = {"A": A, "B": B, "C": C}
    for n in nodes.values():
        n.init_self()

    for _ in range(10):
        if not _dv_round(nodes, poison=False):
            break

    # Fail the A-B link.
    del B.neighbors["A"]
    del A.neighbors["B"]
    B.table["A"] = (INFINITY, None)

    print(f"{'Round':>5} | {'B->A':>10} | {'C->A':>10} | comment")
    print("-" * 55)
    b_cost = B.table.get("A", (INFINITY, None))[0]
    c_cost = C.table.get("A", (INFINITY, None))[0]
    print(f"{'init':>5} | {b_cost:>10} | {c_cost:>10} | A-B failed, B poisons A to 16")

    rounds = 0
    while rounds < 10:
        changed_any = _dv_round(nodes, poison=True)

        rounds += 1
        b_cost = B.table.get("A", (INFINITY, None))[0]
        c_cost = C.table.get("A", (INFINITY, None))[0]
        status = "loop prevented" if not changed_any else "poison propagating"
        print(f"{rounds:>5} | {b_cost:>10} | {c_cost:>10} | {status}")
        if not changed_any:
            break
    print(f"\nRounds to converge: {rounds} (vs ~15 without poisoned reverse)\n")


# ---------------------------------------------------------------------------
# Link-state: LSA, flooding, LSDB, Dijkstra
# ---------------------------------------------------------------------------

@dataclass
class LSA:
    origin: str
    seq: int
    age: int
    links: Dict[str, int]  # neighbor -> cost

    def key(self) -> Tuple[str, int]:
        return (self.origin, self.seq)


@dataclass
class LSNode:
    name: str
    neighbors: Dict[str, int] = field(default_factory=dict)
    lsdb: Dict[str, LSA] = field(default_factory=dict)  # origin -> newest LSA
    seq: int = 0

    def originate(self) -> LSA:
        self.seq += 1
        lsa = LSA(origin=self.name, seq=self.seq, age=0,
                  links=dict(self.neighbors))
        self.lsdb[self.name] = lsa
        return lsa

    def receive(self, lsa: LSA, arrived_from: str) -> List["LSNode"]:
        """Install if newer; return list of (re-flood targets). Pure function here."""
        existing = self.lsdb.get(lsa.origin)
        if existing is not None and lsa.seq <= existing.seq:
            return []  # stale or duplicate: drop, do not re-flood
        self.lsdb[lsa.origin] = lsa
        return [n for n in self.neighbors if n != arrived_from]

    def dijkstra(self, all_nodes: Dict[str, "LSNode"]) -> Dict[str, Tuple[int, Optional[str]]]:
        """SPF rooted at self over the synchronized LSDB."""
        dist: Dict[str, int] = {self.name: 0}
        first_hop: Dict[str, Optional[str]] = {self.name: None}
        visited: set = set()
        # Build adjacency from the LSDB.
        adj: Dict[str, List[Tuple[str, int]]] = {}
        for origin, lsa in self.lsdb.items():
            adj[origin] = [(n, c) for n, c in lsa.links.items()]
        # Ensure every known node appears.
        for n in all_nodes:
            dist.setdefault(n, INFINITY)
            first_hop.setdefault(n, None)
            adj.setdefault(n, [])
        heap: List[Tuple[int, str]] = [(0, self.name)]
        while heap:
            d, u = heapq.heappop(heap)
            if u in visited:
                continue
            visited.add(u)
            for v, c in adj.get(u, []):
                nd = d + c
                if nd < dist.get(v, INFINITY):
                    dist[v] = nd
                    if u == self.name:
                        first_hop[v] = v
                    else:
                        first_hop[v] = first_hop.get(u)
                    heapq.heappush(heap, (nd, v))
        return {n: (dist.get(n, INFINITY), first_hop.get(n)) for n in all_nodes}


def flood(origin_node: LSNode, all_nodes: Dict[str, LSNode]) -> int:
    """Reliable flooding of origin_node's LSA; return total re-flood hops."""
    lsa = origin_node.originate()
    hops = 0
    # Wave-front BFS: (arrived_at, lsa_copy, arrived_from)
    wave: List[Tuple[str, LSA, Optional[str]]] = [
        (n, lsa, origin_node.name) for n in origin_node.neighbors
    ]
    while wave:
        here_name, incoming, came_from = wave.pop(0)
        here = all_nodes[here_name]
        targets = here.receive(incoming, came_from or "")
        hops += len(targets)
        for t in targets:
            wave.append((t, incoming, here_name))
    return hops


def run_link_state() -> None:
    print("=" * 70)
    print("DEMO 3: link-state flooding + Dijkstra SPF")
    print("=" * 70)
    print("Topology: A -1- B -1- C -1- D -1- A  (4-node ring)\n")

    A = LSNode("A", neighbors={"B": 1, "D": 1})
    B = LSNode("B", neighbors={"A": 1, "C": 1})
    C = LSNode("C", neighbors={"B": 1, "D": 1})
    D = LSNode("D", neighbors={"C": 1, "A": 1})
    nodes = {"A": A, "B": B, "C": C, "D": D}

    print("Flooding each node's LSA (re-flood hops counted, de-dup by origin+seq):")
    total_hops = 0
    for name in ["A", "B", "C", "D"]:
        before = {n.name: len(n.lsdb) for n in nodes.values()}
        hops = flood(nodes[name], nodes)
        total_hops += hops
        after = {n.name: len(n.lsdb) for n in nodes.values()}
        print(f"  {name} originated seq={nodes[name].seq}: re-flood hops={hops}, "
              f"LSDB sizes {before} -> {after}")
    print(f"  Total re-flood hops: {total_hops}  (ring diameter = 2)")

    # Verify every node has the same LSDB keys.
    keys = [set(n.lsdb.keys()) for n in nodes.values()]
    print(f"\nLSDB synchronized across all nodes: {all(k == keys[0] for k in keys)}")
    print(f"LSDB contents at A: "
          f"{sorted([(o, l.seq, dict(l.links)) for o, l in A.lsdb.items()])}")

    # Dijkstra at A.
    print("\nDijkstra SPF at A:")
    table = A.dijkstra(nodes)
    print(f"  {'dest':>5} | {'cost':>5} | {'next-hop':>8}")
    print("  " + "-" * 26)
    for dest in sorted(table):
        cost, nhop = table[dest]
        print(f"  {dest:>5} | {cost:>5} | {str(nhop):>8}")

    # Now fail link A-B and re-flood.
    print("\nSimulating A-B link failure: A and B re-originate LSAs.")
    del A.neighbors["B"]
    del B.neighbors["A"]
    hops_a = flood(A, nodes)
    hops_b = flood(B, nodes)
    print(f"  re-flood hops: A={hops_a}, B={hops_b}")
    table2 = A.dijkstra(nodes)
    print(f"  A's new route to B: cost={table2['B'][0]} via {table2['B'][1]} "
          f"(was 1 via B; now {table2['B'][0]} via {table2['B'][1]})")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    run_count_to_infinity()
    run_split_horizon()
    run_link_state()
    print("=" * 70)
    print("All three demos complete. Distance-vector loops; link-state does not.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
