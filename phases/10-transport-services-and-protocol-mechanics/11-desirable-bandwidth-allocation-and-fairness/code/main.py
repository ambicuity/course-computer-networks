"""Max-min fair bandwidth allocation with water-filling.

This module computes max-min fair rates for a set of flows over a small
network using the water-filling (uniform increase + freeze at bottleneck)
algorithm. It includes a verification routine for the textbook's Fig. 6-20
example, where four flows A, B, C, D through six routers R1..R6 each get
the rate 2/3, 1/3, 1/3, 1/3.

Stdlib only, no third-party packages, no network access. Run with
``python3 main.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Iterable


# ---------------------------------------------------------------------------
# Graph primitives
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Link:
    """An undirected link between two nodes with a fixed capacity."""

    u: Hashable
    v: Hashable
    capacity: float = 1.0

    def endpoints(self) -> tuple[Hashable, Hashable]:
        return (self.u, self.v)

    def traverses(self, a: Hashable, b: Hashable) -> bool:
        return {self.u, self.v} == {a, b}


@dataclass(frozen=True)
class Flow:
    """A flow described by a fixed path through the network."""

    flow_id: str
    path: tuple[Hashable, ...]


@dataclass(frozen=True)
class Allocation:
    """The result of a max-min allocation for one flow."""

    flow_id: str
    rate: float
    bottleneck_link: tuple[Hashable, Hashable] | None
    frozen: bool


@dataclass
class Graph:
    """A small undirected graph of ``Link`` objects."""

    links: tuple[Link, ...]

    def link_for_pair(self, a: Hashable, b: Hashable) -> Link:
        for link in self.links:
            if link.traverses(a, b):
                return link
        raise KeyError(f"no link between {a!r} and {b!r}")

    def links_on_path(self, path: Iterable[Hashable]) -> list[Link]:
        nodes = list(path)
        result: list[Link] = []
        for i in range(len(nodes) - 1):
            result.append(self.link_for_pair(nodes[i], nodes[i + 1]))
        return result


# ---------------------------------------------------------------------------
# Max-min fair allocation by water-filling
# ---------------------------------------------------------------------------


def max_min_fair(graph: Graph, flows: Iterable[Flow]) -> list[Allocation]:
    """Compute the max-min fair allocation for ``flows`` over ``graph``.

    Water-filling by progressive filling. In each round, compute for every
    unfrozen flow the smallest ``residual / n_unfrozen_users`` ratio on
    its path: that is the rate at which its tightest link will saturate.
    Pick the smallest such ratio across all unfrozen flows; that is the
    next bottleneck event. Any flow whose own ratio matches that value
    jumps to its new rate (= old rate + ratio) and freezes. Flows whose
    ratio is *larger* keep their old rate and stay unfrozen; they have
    headroom and will be handled in a later round. The procedure ends
    when every flow is frozen.
    """
    flows_list = list(flows)
    path_links: dict[str, list[Link]] = {
        f.flow_id: graph.links_on_path(f.path) for f in flows_list
    }
    rate: dict[str, float] = {f.flow_id: 0.0 for f in flows_list}
    frozen: dict[str, bool] = {f.flow_id: False for f in flows_list}
    bottleneck: dict[str, tuple[Hashable, Hashable] | None] = {
        f.flow_id: None for f in flows_list
    }

    while not all(frozen[f.flow_id] for f in flows_list):
        # Residual capacity of each link after subtracting frozen flows.
        residual: dict[int, float] = {id(link): link.capacity for link in graph.links}
        for f in flows_list:
            if not frozen[f.flow_id]:
                continue
            for link in path_links[f.flow_id]:
                residual[id(link)] -= rate[f.flow_id]

        # Number of unfrozen flows using each link.
        users: dict[int, int] = {id(link): 0 for link in graph.links}
        for f in flows_list:
            if frozen[f.flow_id]:
                continue
            for link in path_links[f.flow_id]:
                users[id(link)] += 1

        # For each unfrozen flow, the smallest residual/users ratio on its
        # path is the rate at which its tightest link saturates next.
        ratios: dict[str, float] = {}
        for f in flows_list:
            if frozen[f.flow_id]:
                continue
            ratios[f.flow_id] = min(
                residual[id(link)] / users[id(link)]
                for link in path_links[f.flow_id]
                if users[id(link)] > 0
            )

        assert ratios, "no unfrozen flows left"
        next_rate = min(ratios.values())

        # The next bottleneck event is ``next_rate``. Every flow whose own
        # ratio equals this value freezes at its new total rate. Other
        # unfrozen flows keep their current rate and wait for the next
        # event.
        for fid, r in ratios.items():
            if abs(r - next_rate) < 1e-12:
                rate[fid] += next_rate
                frozen[fid] = True
                path = path_links[fid]
                best: Link | None = None
                best_ratio = float("inf")
                for link in path:
                    if users[id(link)] == 0:
                        continue
                    ratio = residual[id(link)] / users[id(link)]
                    if abs(ratio - next_rate) < 1e-12 and ratio < best_ratio:
                        best = link
                        best_ratio = ratio
                if best is not None:
                    bottleneck[fid] = best.endpoints()

    return [
        Allocation(
            flow_id=f.flow_id,
            rate=rate[f.flow_id],
            bottleneck_link=bottleneck[f.flow_id],
            frozen=True,
        )
        for f in flows_list
    ]


# ---------------------------------------------------------------------------
# Textbook example (Fig. 6-20)
# ---------------------------------------------------------------------------


TEXTBOOK_LINKS: tuple[Link, ...] = (
    Link("R1", "R2"),
    Link("R2", "R3"),
    Link("R3", "R5"),
    Link("R3", "R6"),
    Link("R1", "R4"),
    Link("R4", "R5"),
    Link("R5", "R6"),
)


TEXTBOOK_FLOWS: tuple[Flow, ...] = (
    # A: R1 -> R2 -> R3 -> R6
    Flow("A", ("R1", "R2", "R3", "R6")),
    # B: R1 -> R2 -> R3 -> R5 -> R4 (and uses R4-R5 too)
    Flow("B", ("R1", "R2", "R3", "R5", "R4")),
    # C: R1 -> R4 -> R5 (and uses R5-R6)
    Flow("C", ("R1", "R4", "R5", "R6")),
    # D: R3 -> R5 -> R6 (and uses R4-R5)
    Flow("D", ("R3", "R5", "R4")),
)


def verify_textbook_example() -> list[Allocation]:
    """Reproduce Fig. 6-20's allocation 2/3, 1/3, 1/3, 1/3."""
    graph = Graph(TEXTBOOK_LINKS)
    return max_min_fair(graph, TEXTBOOK_FLOWS)


def single_bottleneck_example() -> list[Allocation]:
    """Three flows share a 10 Mbps link, each has a private 1 Mbps egress."""
    links = (
        Link("ingress", "core", 10.0),
        Link("core", "egress_a", 1.0),
        Link("core", "egress_b", 1.0),
        Link("core", "egress_c", 1.0),
    )
    flows = (
        Flow("A", ("ingress", "core", "egress_a")),
        Flow("B", ("ingress", "core", "egress_b")),
        Flow("C", ("ingress", "core", "egress_c")),
    )
    return max_min_fair(Graph(links), flows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _format(allocation: Allocation) -> str:
    bottleneck = (
        "n/a"
        if allocation.bottleneck_link is None
        else f"{allocation.bottleneck_link[0]}-{allocation.bottleneck_link[1]}"
    )
    return (
        f"  flow {allocation.flow_id}: rate = {allocation.rate:.4f}  "
        f"bottleneck = {bottleneck}"
    )


def main() -> None:
    print("Textbook Fig. 6-20 max-min allocation (capacity = 1.0 on every link):")
    for a in verify_textbook_example():
        print(_format(a))
    print()
    print("Three flows sharing a 10 Mbps ingress, each with a 1 Mbps egress:")
    for a in single_bottleneck_example():
        print(_format(a))


if __name__ == "__main__":
    main()
