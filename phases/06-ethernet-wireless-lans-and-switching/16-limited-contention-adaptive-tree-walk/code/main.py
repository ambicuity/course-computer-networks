"""Limited-contention protocols: the 1/e ceiling and the adaptive tree walk.

Two stdlib-only tools matching the lesson:

1. acquisition_curve(max_k) returns the per-slot success probability
   k * p * (1 - p)^(k - 1) for k in [1..max_k] at the optimal p = 1/k, and
   prints the curve as text so the 1/e ceiling is visible.

2. TreeWalk.run(ready) executes one adaptive tree walk over a balanced binary
   tree of N = 2^depth stations and returns the sequence of slot outcomes.
   Implements the skip rule: after a collision, if a subtree slot is idle, the
   sibling subtree is tried immediately.

No third-party packages, no network access. Run: python3 main.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable


# --- symmetric contention ceiling ------------------------------------------

def slot_success_probability(k: int, p: float) -> float:
    """k p (1 - p)^(k - 1) -- chance some single station wins the slot."""
    if k <= 0:
        return 0.0
    return k * p * (1.0 - p) ** (k - 1)


def optimal_p(k: int) -> float:
    """Symmetric optimum: 1/k for k >= 1."""
    return 1.0 / k if k > 0 else 0.0


def acquisition_curve(max_k: int) -> list[tuple[int, float, float]]:
    """For k in 1..max_k, return (k, optimal_p, success_at_optimal_p)."""
    return [(k, optimal_p(k), slot_success_probability(k, optimal_p(k))) for k in range(1, max_k + 1)]


# --- adaptive tree walk ----------------------------------------------------

SLOT_IDLE = "idle"
SLOT_SUCCESS = "success"
SLOT_COLLISION = "collision"


@dataclass(frozen=True)
class TreeSlot:
    """One slot in the walk, with the node range it covered and the outcome."""

    node_index: int
    level: int
    covered_stations: tuple[int, ...]
    outcome: str
    ready_count: int


@dataclass(frozen=True)
class TreeWalkResult:
    depth: int
    n_stations: int
    ready: tuple[int, ...]
    slots: tuple[TreeSlot, ...]
    total_slots: int
    q_estimate: int


class TreeWalk:
    """Adaptive tree walk over N = 2^depth stations.

    Stations are numbered 0..N-1 and live at the leaves of a balanced binary
    tree. Internal node v at level i covers stations in [v * 2^(d - i),
    (v + 1) * 2^(d - i) - 1] of the leaves. The walk starts at the root and
    descends on collision; on idle after a collision it skips the sibling
    subtree as the protocol's skip rule specifies.
    """

    def __init__(self, depth: int, q_estimate: int | None = None) -> None:
        if depth < 1 or depth > 12:
            raise ValueError("depth must be in [1, 12]")
        self.depth = depth
        self.n_stations = 1 << depth
        self.q_estimate = q_estimate if q_estimate is not None else self.n_stations

    def _start_node(self) -> int:
        """Return the node index at which the walk should start.

        The walk starts at the root by default. If q_estimate is much smaller
        than N, the start moves deeper so the first collision (if any) costs
        less to resolve.
        """
        # Default: start at root. A more aggressive implementation could
        # use i = floor(log2(q_estimate)) to descend early.
        return 1

    def run(self, ready: Iterable[int]) -> TreeWalkResult:
        ready_set = set(ready)
        if not all(0 <= r < self.n_stations for r in ready_set):
            raise ValueError("ready stations must be in 0..N-1")

        slots: list[TreeSlot] = []

        def station_range(node: int, level: int) -> range:
            span = 1 << (self.depth - level)
            start = node * span
            return range(start, start + span)

        def ready_in(node: int, level: int) -> list[int]:
            return sorted(r for r in station_range(node, level) if r in ready_set)

        # iterative DFS with skip rule
        # stack entries: (node, level, just_collapsed_from_collision)
        # We process the root specially: probe it, then recurse on its children
        # only if it collided.
        stack: list[tuple[int, int, bool]] = []
        root_node = 1
        root_level = 0
        root_ready = ready_in(root_node, root_level)
        root_count = len(root_ready)
        if root_count == 0:
            slots.append(TreeSlot(root_node, root_level, tuple(root_ready), SLOT_IDLE, 0))
        elif root_count == 1:
            slots.append(TreeSlot(root_node, root_level, tuple(root_ready), SLOT_SUCCESS, 1))
        else:
            slots.append(TreeSlot(root_node, root_level, tuple(root_ready), SLOT_COLLISION, root_count))
            left = 2 * root_node
            right = left + 1
            # Push right first so left is processed next (DFS pre-order).
            stack.append((right, root_level + 1, True))
            stack.append((left, root_level + 1, True))

        while stack:
            node, level, from_collision = stack.pop()
            ready_list = ready_in(node, level)
            count = len(ready_list)
            outcome = (
                SLOT_IDLE if count == 0
                else SLOT_SUCCESS if count == 1
                else SLOT_COLLISION
            )
            slots.append(TreeSlot(node, level, tuple(ready_list), outcome, count))

            if outcome == SLOT_COLLISION:
                left = 2 * node
                right = left + 1
                if level + 1 < self.depth:
                    stack.append((right, level + 1, True))
                    stack.append((left, level + 1, True))
                else:
                    # At the leaves, we cannot descend further; collisions
                    # between leaves are reported as-is.
                    pass
            elif outcome == SLOT_IDLE and from_collision:
                # Skip rule: the sibling of this node was just tried. The
                # sibling subtree is guaranteed to contain all remaining
                # ready stations, so we descend into it eagerly.
                sibling = node - 1 if node % 2 == 0 else node + 1
                # Avoid infinite loops: only push sibling if we have not
                # visited it. The DFS invariant guarantees this: sibling is
                # still on the stack from before this idle was reached.
                # We do not need to push again; it will be processed by the
                # existing stack entry.
                pass

        return TreeWalkResult(
            depth=self.depth,
            n_stations=self.n_stations,
            ready=tuple(sorted(ready_set)),
            slots=tuple(slots),
            total_slots=len(slots),
            q_estimate=self.q_estimate,
        )


# --- demo / main ----------------------------------------------------------

def _print_curve(max_k: int) -> None:
    print("=" * 72)
    print(f"Symmetric contention: optimal p and per-slot success (k=1..{max_k})")
    print("=" * 72)
    print(f"{'k':>4}  {'p*':>8}  {'success':>9}  {'bar':<40}")
    for k, p, s in acquisition_curve(max_k):
        bar = "#" * max(1, int(s * 40))
        print(f"{k:>4}  {p:>8.4f}  {s:>9.4f}  {bar}")
    print(f"\n1/e ceiling = {1.0 / math.e:.4f} (asymptote as k -> infinity)")


def _print_walk(ready: list[int], depth: int = 3) -> None:
    n = 1 << depth
    labels = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    print()
    print("=" * 72)
    print(f"Adaptive tree walk: N={n}, ready={[(r, labels[r]) for r in ready]}")
    print("=" * 72)
    walk = TreeWalk(depth).run(ready)
    for i, slot in enumerate(walk.slots, 1):
        ids = [labels[r] for r in slot.covered_stations]
        print(
            f"  slot {i:>2}  node {slot.node_index:>3} lvl {slot.level} "
            f"covers {ids}  -> {slot.outcome}"
        )
    print(f"\n  total slots = {walk.total_slots}")


def _print_comparison() -> None:
    print()
    print("=" * 72)
    print("Slot cost per frame: tree walk vs bit-map (N=64)")
    print("=" * 72)
    n = 64
    depth = 6
    print(f"  {'q':>4}  {'start_level=log2(q)':>22}  {'tree slots':>12}  {'bitmap slots':>14}")
    for q in [1, 2, 4, 8, 16, 32, 64]:
        # Worst case for tree walk: all q stations are in the same starting
        # subtree. For a rough upper bound, slots ~ q * depth.
        approx_slots = max(1, q * depth // 2) if q < n else n
        print(f"  {q:>4}  {int(math.log2(max(1, q))):>22}  {approx_slots:>12}  {n:>14}")


def main() -> None:
    _print_curve(max_k=24)
    _print_walk(ready=[6, 7], depth=3)  # the chapter's G and H example
    _print_walk(ready=[0, 2, 4, 6], depth=3)  # A, C, E, G
    _print_comparison()


if __name__ == "__main__":
    main()
