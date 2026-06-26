"""Adaptive Tree Walk Protocol simulator (limited-contention MAC, Tanenbaum 4.2.4).

This stdlib-only program demonstrates the two ideas behind limited-contention
protocols:

  1. Symmetric contention success  Pr = k * p * (1 - p)**(k - 1)  is maximized at
     p = 1/k and decays toward 1/e (~0.368) as the number of ready stations k
     grows. Lowering competition k is the only way to raise per-slot success.

  2. The Adaptive Tree Walk Protocol (Capetanakis, 1979) lowers k dynamically by
     arranging stations as leaves of a binary tree and probing nodes depth-first:
     a collision recurses into left then right child; an idle or single-station
     slot prunes the subtree. Under a load estimate q, the walk starts at level
     floor(log2(q)) so the expected contenders per node 2**(-i) * q is about 1.

Run:  python3 main.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable

# Outcome labels for a single contention slot.
IDLE = "idle"
SINGLE = "single"
COLLISION = "collision"


def symmetric_success(k: int) -> float:
    """Per-slot success probability for k symmetric contenders using p = 1/k.

    Returns k * p * (1 - p)**(k - 1) with the optimal p = 1/k. For k <= 1 the
    channel is trivially acquired, so we return 1.0.
    """
    if k <= 1:
        return 1.0
    p = 1.0 / k
    return k * p * (1.0 - p) ** (k - 1)


def optimal_start_level(q: int) -> int:
    """Tree level where expected contenders per node ~= 1, i.e. floor(log2 q).

    q is the estimated number of ready stations; level 0 is the root.
    """
    if q <= 1:
        return 0
    return int(math.floor(math.log2(q)))


@dataclass(frozen=True)
class SlotRecord:
    """One contention slot of a tree walk (immutable)."""

    slot: int
    node: int
    span: tuple[str, ...]
    contenders: tuple[str, ...]
    outcome: str
    action: str


def build_leaves(n_levels: int) -> tuple[str, ...]:
    """Return 2**n_levels leaf labels A, B, C, ... for a full binary tree."""
    count = 2 ** n_levels
    labels = []
    for i in range(count):
        labels.append(chr(ord("A") + i) if i < 26 else f"S{i}")
    return tuple(labels)


def leaves_under(node: int, leaves: tuple[str, ...]) -> tuple[str, ...]:
    """Leaves beneath a breadth-first numbered node (root = 1).

    A node at depth d = floor(log2 node) spans a contiguous block of leaves.
    """
    depth = int(math.floor(math.log2(node)))
    block = len(leaves) // (2 ** depth)
    index_in_level = node - (2 ** depth)
    start = index_in_level * block
    return leaves[start:start + block]


def classify(contenders: tuple[str, ...]) -> str:
    """Map a contender set to a slot outcome."""
    if not contenders:
        return IDLE
    if len(contenders) == 1:
        return SINGLE
    return COLLISION


def tree_walk(
    n_levels: int,
    ready: Iterable[str],
    start_level: int = 0,
    prune: bool = True,
) -> list[SlotRecord]:
    """Walk the binary tree depth-first, one SlotRecord per probed contention slot.

    n_levels    : tree has 2**n_levels leaf stations.
    ready       : labels of stations that have a frame to send.
    start_level : tree level to begin probing (0 = root).
    prune       : apply the guaranteed-collision sibling-skip optimization.
                  (The idle-subtree stop is inherent: idle nodes never recurse.)
    """
    leaves = build_leaves(n_levels)
    ready_set = set(ready)
    records: list[SlotRecord] = []
    slot = 0
    leaf_depth = n_levels  # nodes at this depth are leaves

    def probe(node: int) -> str:
        nonlocal slot
        span = leaves_under(node, leaves)
        contenders = tuple(s for s in span if s in ready_set)
        outcome = classify(contenders)
        if outcome == IDLE:
            action = "stop subtree (no ready station below)"
        elif outcome == SINGLE:
            action = f"{contenders[0]} transmits — subtree done"
        else:
            action = "descend to children"
        records.append(SlotRecord(slot, node, span, contenders, outcome, action))
        slot += 1
        return outcome

    def is_leaf(node: int) -> bool:
        return int(math.floor(math.log2(node))) >= leaf_depth

    def descend(node: int) -> str:
        """Probe a node; on collision recurse into children. Return this node's outcome."""
        outcome = probe(node)
        if outcome != COLLISION or is_leaf(node):
            return outcome
        left, right = 2 * node, 2 * node + 1
        left_outcome = descend(left)
        # Guaranteed-collision skip: parent collided and left child was idle =>
        # the right child must contain >=2 ready stations, so it WILL collide.
        # Skip probing `right` and recurse straight into its children.
        if prune and left_outcome == IDLE and not is_leaf(right):
            descend(2 * right)
            descend(2 * right + 1)
        else:
            descend(right)
        return outcome

    for node in range(2 ** start_level, 2 ** (start_level + 1)):
        descend(node)
    return records


def print_trace(trace: list[SlotRecord]) -> None:
    """Pretty-print a tree-walk trace as one row per contention slot."""
    print(f"{'slot':>4} | {'node':>4} | {'span':<10} | {'contenders':<12} | "
          f"{'outcome':<9} | action")
    print("-" * 80)
    for r in trace:
        span = "".join(r.span)
        cont = ",".join(r.contenders) or "-"
        print(f"{r.slot:>4} | {r.node:>4} | {span:<10} | {cont:<12} | "
              f"{r.outcome:<9} | {r.action}")


def main() -> None:
    print("=" * 64)
    print("Symmetric contention: success = k*(1/k)*(1-1/k)^(k-1) -> 1/e")
    print("=" * 64)
    print(f"{'k ready':>8} | {'Pr[success]':>12}")
    print("-" * 26)
    for k in (1, 2, 3, 5, 10, 25, 50):
        print(f"{k:>8} | {symmetric_success(k):>12.4f}")
    print(f"{'1/e':>8} | {1 / math.e:>12.4f}  (asymptote)\n")

    print("=" * 64)
    print("Tree walk on 8 stations (A-H), ready = {C, E}")
    print("=" * 64)
    print_trace(tree_walk(n_levels=3, ready={"C", "E"}, start_level=0))

    print("\n" + "=" * 64)
    print("Pruning demo: ready = {G, H}  (guaranteed-collision skip fires)")
    print("=" * 64)
    pruned = tree_walk(n_levels=3, ready={"G", "H"}, start_level=0, prune=True)
    unpruned = tree_walk(n_levels=3, ready={"G", "H"}, start_level=0, prune=False)
    print_trace(pruned)
    print(f"\nSlots without pruning: {len(unpruned)}   "
          f"with pruning: {len(pruned)}   saved: {len(unpruned) - len(pruned)}")

    print("\n" + "=" * 64)
    print("Adaptive start level under load estimate q")
    print("=" * 64)
    for q in (1, 2, 4, 7, 18, 60):
        lvl = optimal_start_level(q)
        print(f"q={q:>3} ready -> start at level {lvl} "
              f"(expected contenders/node = {q / (2 ** lvl):.2f})")


if __name__ == "__main__":
    main()
