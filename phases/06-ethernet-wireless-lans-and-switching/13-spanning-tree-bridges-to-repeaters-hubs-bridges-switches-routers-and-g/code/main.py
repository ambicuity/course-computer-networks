"""IEEE 802.1D Spanning Tree solver and BPDU decoder (stdlib only).

This program models a bridge mesh and runs the classic 802.1D Spanning Tree
Protocol by hand:

  1. Root election     -- the numerically lowest Bridge ID wins.
  2. Root-port choice  -- each non-root bridge keeps its lowest-cost path to
                          the root (Dijkstra-style relaxation), breaking ties
                          on sender Bridge ID then Port ID.
  3. Designated ports  -- the lowest-cost bridge on each segment forwards; every
                          other port on that segment is set to BLOCKING, which
                          is what makes the resulting topology loop-free.

It also decodes a raw Configuration BPDU hex string into its fields and
demonstrates the {Root ID, Root Path Cost, Bridge ID, Port ID} priority-vector
comparison that drives the whole algorithm.

Run:  python3 main.py   (no dependencies, no network access)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

BLOCKING = "BLOCKING"
FORWARDING = "FORWARDING"

# Classic 802.1D path costs, inversely related to link speed (Mbps -> cost).
COST_BY_SPEED_MBPS: dict[int, int] = {10: 100, 100: 19, 1000: 4, 10000: 2}


@dataclass(frozen=True)
class Link:
    """A point-to-point link between two bridges with an 802.1D path cost."""

    a: str
    b: str
    cost: int

    def other(self, bridge: str) -> str:
        return self.b if bridge == self.a else self.a


@dataclass
class Bridge:
    """A bridge identified by its 8-byte Bridge ID (priority + MAC)."""

    name: str
    bridge_id: int  # lower is better; encodes priority then MAC
    root_id: int = field(init=False)
    root_cost: int = field(init=False)
    root_port: Optional[str] = field(init=False, default=None)

    def __post_init__(self) -> None:
        # Every bridge starts by claiming to be the root of its own tree.
        self.root_id = self.bridge_id
        self.root_cost = 0


def cost_for_speed(speed_mbps: int) -> int:
    """Return the 802.1D path cost for a link speed, defaulting to 100 Mbps."""
    return COST_BY_SPEED_MBPS.get(speed_mbps, 19)


def elect_root(bridges: dict[str, Bridge]) -> Bridge:
    """The bridge with the numerically lowest Bridge ID becomes the root."""
    root = min(bridges.values(), key=lambda br: br.bridge_id)
    for br in bridges.values():
        br.root_id = root.bridge_id
    return root


def compute_paths(
    bridges: dict[str, Bridge], links: list[Link], root: Bridge
) -> dict[str, int]:
    """Dijkstra-style shortest path cost from the root to every bridge.

    Ties on equal cost are broken on the neighbour's lower Bridge ID, matching
    the 802.1D tiebreak rules. Each bridge's root_port is set to the link it
    uses to reach the root.
    """
    dist: dict[str, int] = {name: float("inf") for name in bridges}  # type: ignore[misc]
    dist[root.name] = 0
    via: dict[str, Optional[str]] = {name: None for name in bridges}
    settled: set[str] = set()

    while len(settled) < len(bridges):
        # Pick the unsettled bridge with the smallest cost; break ties on ID.
        current = min(
            (n for n in bridges if n not in settled),
            key=lambda n: (dist[n], bridges[n].bridge_id),
        )
        settled.add(current)
        for link in links:
            if current not in (link.a, link.b):
                continue
            neighbour = link.other(current)
            candidate = dist[current] + link.cost
            better = candidate < dist[neighbour]
            tie = candidate == dist[neighbour] and (
                via[neighbour] is None
                or bridges[current].bridge_id < bridges[via[neighbour]].bridge_id
            )
            if better or tie:
                dist[neighbour] = candidate
                via[neighbour] = current

    for name, br in bridges.items():
        br.root_cost = dist[name]
        br.root_port = via[name]
    return dist


def select_port_states(
    bridges: dict[str, Bridge], links: list[Link], root: Bridge
) -> dict[tuple[str, str], str]:
    """Assign FORWARDING/BLOCKING to each (bridge, neighbour) half of a link.

    A link is part of the tree if either endpoint uses it as its root port, or
    if it is the designated link for the segment. The designated bridge on a
    segment is the endpoint offering the lower cost to root (tie: lower ID).
    Every other port goes BLOCKING.
    """
    states: dict[tuple[str, str], str] = {}
    for link in links:
        a, b = link.a, link.b
        a_uses = bridges[a].root_port == b
        b_uses = bridges[b].root_port == a
        if a_uses or b_uses:
            states[(a, b)] = FORWARDING
            states[(b, a)] = FORWARDING
            continue
        # Neither endpoint's root port -- decide the designated end, block other.
        a_key = (bridges[a].root_cost, bridges[a].bridge_id)
        b_key = (bridges[b].root_cost, bridges[b].bridge_id)
        if a_key <= b_key:
            states[(a, b)], states[(b, a)] = FORWARDING, BLOCKING
        else:
            states[(a, b)], states[(b, a)] = BLOCKING, FORWARDING
    return states


def decode_config_bpdu(hex_str: str) -> dict[str, object]:
    """Decode a raw 802.1D Configuration BPDU from a hex string into fields."""
    raw = bytes.fromhex(hex_str.replace(" ", ""))
    if len(raw) < 35:
        raise ValueError(f"BPDU too short: {len(raw)} bytes, need >= 35")

    def be(start: int, length: int) -> int:
        return int.from_bytes(raw[start : start + length], "big")

    def mac(start: int) -> str:
        return ":".join(f"{b:02x}" for b in raw[start : start + 6])

    return {
        "protocol_id": be(0, 2),
        "version": raw[2],
        "bpdu_type": raw[3],
        "flags": raw[4],
        "root_priority": be(5, 2),
        "root_mac": mac(7),
        "root_path_cost": be(13, 4),
        "bridge_priority": be(17, 2),
        "bridge_mac": mac(19),
        "port_id": be(25, 2),
        "message_age_s": be(27, 2) / 256,
        "max_age_s": be(29, 2) / 256,
        "hello_time_s": be(31, 2) / 256,
        "forward_delay_s": be(33, 2) / 256,
    }


def priority_vector_winner(a: dict[str, int], b: dict[str, int]) -> str:
    """Compare two BPDUs on {root, cost, bridge, port}; lower wins."""
    for key in ("root", "cost", "bridge", "port"):
        if a[key] != b[key]:
            return "A" if a[key] < b[key] else "B"
    return "tie"


def main() -> None:
    # Recreate the 5-bridge mesh of Fig. 4-44. The trailing digit is the
    # priority, so B1 has the lowest Bridge ID and should become root.
    bridges = {
        "B1": Bridge("B1", 0x1000),
        "B2": Bridge("B2", 0x2000),
        "B3": Bridge("B3", 0x3000),
        "B4": Bridge("B4", 0x4000),
        "B5": Bridge("B5", 0x5000),
    }
    c100 = cost_for_speed(100)  # 19
    links = [
        Link("B1", "B2", c100),
        Link("B1", "B3", c100),
        Link("B2", "B4", c100),
        Link("B3", "B4", c100),  # redundant path to B4 -> one end will block
        Link("B3", "B5", c100),
        Link("B2", "B3", c100),  # extra mesh link -> must be pruned
    ]

    print("=== IEEE 802.1D Spanning Tree solver ===\n")
    root = elect_root(bridges)
    print(f"Root election: lowest Bridge ID wins -> {root.name} "
          f"(ID 0x{root.bridge_id:04X})\n")

    compute_paths(bridges, links, root)
    print("Root path costs and root ports:")
    for name in sorted(bridges):
        br = bridges[name]
        rp = br.root_port or "(is root)"
        print(f"  {name}: cost={br.root_cost:<3} root_port -> {rp}")
    print()

    states = select_port_states(bridges, links, root)
    print("Link states (BLOCKING ports break the loops):")
    for link in links:
        s_a = states[(link.a, link.b)]
        s_b = states[(link.b, link.a)]
        tree = "  tree" if FORWARDING == s_a == s_b else "  BLOCKED"
        print(f"  {link.a}<->{link.b} (cost {link.cost}): "
              f"{link.a}={s_a:<10} {link.b}={s_b:<10}{tree}")
    blocked = [f"{a}->{b}" for (a, b), st in states.items() if st == BLOCKING]
    print(f"\nBlocked ports (dashed links in the SVG): {blocked or 'none'}\n")

    # Decode a sample Configuration BPDU and show the priority-vector compare.
    print("=== Configuration BPDU decode ===\n")
    sample = (
        "0000 00 00 00"          # proto id, version, type, flags
        "1000 001b0c000001"      # root priority 0x1000 + root MAC
        "00000013"               # root path cost = 19
        "2000 001b0c000002"      # bridge priority 0x2000 + bridge MAC
        "8002"                   # port id
        "0000 1400 0200 0f00"    # msg age, max age=20s, hello=2s, fwd delay=15s
    )
    fields = decode_config_bpdu(sample)
    for key, val in fields.items():
        print(f"  {key:18}: {val}")

    print("\nPriority-vector comparison {root, cost, bridge, port}:")
    a_vec = {"root": 0x1000, "cost": 19, "bridge": 0x2000, "port": 0x8002}
    b_vec = {"root": 0x1000, "cost": 4, "bridge": 0x3000, "port": 0x8001}
    winner = priority_vector_winner(a_vec, b_vec)
    print(f"  A cost=19 vs B cost=4  -> winner: {winner} "
          f"(lower Root Path Cost wins the tie at equal Root ID)")


if __name__ == "__main__":
    main()
