"""Peer-to-peer network simulators.

This module demonstrates core P2P ideas using only the Python standard library:

1. BitTorrent-style rarest-first piece selection.
2. A swarm of peers trading chunks with tit-for-tat reciprocity.
3. A Chord DHT logical ring and successor lookup.
4. How download time drops as more peers join a swarm.
5. A printable peer-swarm state table.

All simulations are in-memory and make no network calls.
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class Peer:
    """A peer in a BitTorrent-style swarm.

    Attributes:
        peer_id: Unique identifier for the peer.
        pieces: Set of piece indices this peer currently holds.
        upload_slots: Maximum number of peers this peer will upload to
            in a round (tit-for-tat limit).
        downloaded_from: Counter of how many pieces this peer has received
            from each other peer in the current round.
    """

    peer_id: str
    pieces: set[int] = field(default_factory=set)
    upload_slots: int = 4
    downloaded_from: Counter[str] = field(default_factory=Counter)

    def has_piece(self, piece: int) -> bool:
        """Return True if this peer already holds *piece*."""
        return piece in self.pieces

    def add_piece(self, piece: int) -> None:
        """Record ownership of *piece* and remember it was downloaded."""
        self.pieces.add(piece)

    def record_download(self, source_id: str) -> None:
        """Record that *source_id* sent a piece to this peer."""
        self.downloaded_from[source_id] += 1

    def upload_candidates(self, peers: list[Peer]) -> list[Peer]:
        """Choose peers to upload to using BitTorrent tit-for-tat.

        Peers that have sent us data recently are favored. One optimistic
        unchoke slot is reserved for a random peer to discover new pieces.
        Empty peers are allowed as candidates so the swarm can bootstrap.
        """
        others = [p for p in peers if p.peer_id != self.peer_id]
        if not others:
            return []

        # Tit-for-tat: prioritize peers that uploaded to us this round.
        by_reciprocity = sorted(
            others,
            key=lambda p: self.downloaded_from[p.peer_id],
            reverse=True,
        )
        slots = self.upload_slots
        chosen = by_reciprocity[: slots - 1]

        # Optimistic unchoke: one random peer not already chosen.
        remaining = [p for p in others if p not in chosen]
        if remaining:
            chosen.append(random.choice(remaining))

        return chosen

    def missing_pieces(self, total_pieces: int) -> list[int]:
        """Return indices of pieces this peer does not yet hold."""
        return [i for i in range(total_pieces) if i not in self.pieces]


def rarest_first_piece(
    peer: Peer,
    peers: list[Peer],
    total_pieces: int,
) -> int | None:
    """Select the rarest piece that *peer* needs and someone else has.

    Args:
        peer: The peer choosing its next download.
        peers: All peers in the swarm (including the chooser).
        total_pieces: Total number of pieces in the shared file.

    Returns:
        The index of the rarest missing piece available in the swarm,
        or None if no useful piece can be found.
    """
    missing = set(peer.missing_pieces(total_pieces))
    if not missing:
        return None

    counts = Counter(
        piece
        for other in peers
        if other.peer_id != peer.peer_id
        for piece in other.pieces
        if piece in missing
    )
    if not counts:
        return None

    # Rarest-first: pick the piece with the smallest swarm-wide count.
    rarest_count = min(counts.values())
    rarest = [piece for piece, count in counts.items() if count == rarest_count]
    return random.choice(rarest)


def simulate_swarm_round(
    peers: list[Peer],
    total_pieces: int,
) -> dict[str, list[int]]:
    """Run one round of uploads and return the transfers that occurred.

    In each round every peer that can upload selects upload candidates
    (tit-for-tat plus optimistic unchoke) and each downloader picks the
    rarest missing piece available from its uploaders.
    """
    transfers: dict[str, list[int]] = {p.peer_id: [] for p in peers}

    # Precompute who each peer is willing to upload to.
    upload_map = {p.peer_id: p.upload_candidates(peers) for p in peers}

    for downloader in peers:
        # Find all peers willing to upload to this downloader.
        sources = [
            p
            for p in peers
            if p.peer_id != downloader.peer_id
            and downloader in upload_map[p.peer_id]
        ]
        if not sources:
            continue

        # Rarest-first selection across all available source pieces.
        missing = set(downloader.missing_pieces(total_pieces))
        available = Counter(
            piece
            for source in sources
            for piece in source.pieces
            if piece in missing
        )
        if not available:
            continue

        rarest_count = min(available.values())
        rarest = [
            piece for piece, count in available.items() if count == rarest_count
        ]
        chosen_piece = random.choice(rarest)

        # Prefer a source that actually has the chosen piece.
        candidates = [s for s in sources if chosen_piece in s.pieces]
        source = random.choice(candidates)

        downloader.add_piece(chosen_piece)
        downloader.record_download(source.peer_id)
        transfers[downloader.peer_id].append(chosen_piece)

    return transfers


def run_swarm(
    peer_count: int,
    total_pieces: int,
    seed_pieces: set[int] | None = None,
    rounds: int = 30,
    seed: int | None = None,
) -> tuple[list[Peer], int]:
    """Create a swarm and simulate *rounds* of tit-for-tat trading.

    Args:
        peer_count: Number of peers in the swarm.
        total_pieces: Total number of pieces in the shared file.
        seed_pieces: Pieces owned by the initial seed peer. Defaults to all.
        rounds: Number of trading rounds to simulate.
        seed: Optional random seed for reproducibility.

    Returns:
        A tuple of (peers after the simulation, rounds actually used).
    """
    if seed is not None:
        random.seed(seed)

    if seed_pieces is None:
        seed_pieces = set(range(total_pieces))

    peers = [Peer(peer_id=f"peer-{i:02d}") for i in range(peer_count)]
    peers[0].pieces = set(seed_pieces)

    rounds_used = 0
    for _ in range(rounds):
        simulate_swarm_round(peers, total_pieces)
        rounds_used += 1
        if all(len(p.pieces) == total_pieces for p in peers):
            break

    return peers, rounds_used


def swarm_state_table(peers: list[Peer], total_pieces: int) -> str:
    """Return an ASCII table summarizing each peer's swarm state."""
    header = f"{'Peer':<10} {'Own':>5} {'Missing':>8} {'Complete':>10}"
    lines = [header, "-" * len(header)]
    for peer in peers:
        own = len(peer.pieces)
        missing = total_pieces - own
        complete = "yes" if own == total_pieces else "no"
        lines.append(f"{peer.peer_id:<10} {own:>5} {missing:>8} {complete:>10}")
    return "\n".join(lines)


class ChordRing:
    """A tiny logical Chord DHT ring.

    The ring uses a fixed identifier space of ``2 ** bits`` nodes.
    Real Chord node IDs are hashed; here they are integers for clarity.
    """

    def __init__(self, bits: int = 6) -> None:
        """Initialize a ring with identifier space ``2 ** bits``."""
        self.bits = bits
        self.max_nodes = 2**bits
        self.nodes: list[int] = []

    def add_node(self, node_id: int) -> None:
        """Add a node identifier to the ring if it is in range."""
        if not 0 <= node_id < self.max_nodes:
            raise ValueError(
                f"node_id {node_id} out of range [0, {self.max_nodes})"
            )
        if node_id not in self.nodes:
            self.nodes.append(node_id)
            self.nodes.sort()

    def successor(self, key: int) -> int | None:
        """Return the first node clockwise from *key* on the ring.

        The result is the node responsible for *key* in Chord terminology.
        Returns None if the ring is empty.
        """
        if not self.nodes:
            return None

        key = key % self.max_nodes
        for node in self.nodes:
            if node >= key:
                return node
        # Wrap around to the first node.
        return self.nodes[0]


def download_time_scaling(
    total_pieces: int,
    file_size_mb: float,
    upload_mbps: float,
    max_peers: int = 8,
    seed: int | None = None,
) -> dict[int, float]:
    """Estimate how download time falls as more peers join the swarm.

    The model assumes each peer contributes its upload capacity, so with
    ``n`` peers the aggregate upload capacity is roughly ``n`` times the
    upload_mbps of a single peer. The seed always starts with all pieces.

    Args:
        total_pieces: Number of pieces in the shared file.
        file_size_mb: Total size of the file in megabytes.
        upload_mbps: Upload speed of one peer in megabits per second.
        max_peers: Largest swarm size to evaluate.
        seed: Optional random seed for reproducibility.

    Returns:
        Mapping from peer count to estimated download time in seconds.
    """
    if seed is not None:
        random.seed(seed)

    results: dict[int, float] = {}
    for peer_count in range(1, max_peers + 1):
        _, complete_rounds = run_swarm(
            peer_count=peer_count,
            total_pieces=total_pieces,
            rounds=100,
        )

        file_size_megabits = file_size_mb * 8
        # Aggregate capacity scales with participating peers.
        aggregate_mbps = upload_mbps * peer_count
        ideal_time = file_size_megabits / aggregate_mbps if aggregate_mbps else 0.0

        # Add a small coordination overhead per peer so the benefit is realistic.
        overhead = 1.0 + 0.05 * peer_count
        results[peer_count] = round(ideal_time * overhead + complete_rounds * 0.2, 2)

    return results


def _demo() -> None:
    """Run interactive demonstrations of all five topics."""
    print("=" * 60)
    print("1. Rarest-first piece selection")
    print("=" * 60)
    total_pieces = 8
    peers = [
        Peer(peer_id="peer-00", pieces={0, 1, 2, 3, 4, 5, 6, 7}),
        Peer(peer_id="peer-01", pieces={0, 1, 2}),
        Peer(peer_id="peer-02", pieces={1, 2, 3}),
        Peer(peer_id="peer-03", pieces={2, 3, 4}),
    ]
    rarest = rarest_first_piece(peers[1], peers, total_pieces)
    print(f"Peer-01 missing pieces: {peers[1].missing_pieces(total_pieces)}")
    print(f"Rarest-first next piece for peer-01: {rarest}")

    print()
    print("=" * 60)
    print("2. Tit-for-tat swarm simulation")
    print("=" * 60)
    swarm, rounds_used = run_swarm(peer_count=6, total_pieces=12, rounds=30, seed=42)
    print(f"Rounds to complete: {rounds_used}")
    print(swarm_state_table(swarm, 12))

    print()
    print("=" * 60)
    print("3. Chord DHT successor lookup")
    print("=" * 60)
    ring = ChordRing(bits=6)
    for node in [5, 18, 30, 45, 56]:
        ring.add_node(node)
    print(f"Ring nodes: {ring.nodes}")
    for key in [3, 15, 35, 50, 60]:
        print(f"Key {key} -> successor {ring.successor(key)}")

    print()
    print("=" * 60)
    print("4. Download time vs. swarm size")
    print("=" * 60)
    scaling = download_time_scaling(
        total_pieces=20,
        file_size_mb=50.0,
        upload_mbps=2.0,
        max_peers=8,
        seed=42,
    )
    print(f"{'Peers':>6} | {'Time (s)':>10}")
    print("-" * 21)
    for peers_count, seconds in scaling.items():
        print(f"{peers_count:>6} | {seconds:>10.2f}")

    print()
    print("=" * 60)
    print("5. Peer-swarm state table")
    print("=" * 60)
    print(swarm_state_table(swarm, 12))


if __name__ == "__main__":
    _demo()
