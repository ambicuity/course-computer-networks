#!/usr/bin/env python3
"""Client-server vs peer-to-peer interaction models, Metcalfe's law, and the
e-commerce taxonomy from Chapter 1, Section 1.1 (Uses of Computer Networks).

This is a self-contained, stdlib-only demonstration. It makes four ideas
concrete and runnable:

  1. A client-server request/reply exchange (one server answers many clients;
     the client BLOCKS after sending the request until the reply arrives).
  2. Peer-to-peer bootstrap discovery (no central index; a new peer walks a
     known member's neighbor list to accumulate content and more member names).
  3. Metcalfe's law: network value ~ n(n-1)/2 distinct user pairs, contrasted
     with linear link cost.
  4. The e-commerce taxonomy (B2C, B2B, G2C, C2C, P2P) mapped onto whether the
     traffic is client-server or peer-symmetric.

No network calls, no third-party packages. Run: python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple


# --------------------------------------------------------------------------- #
# 1. Client-server request / reply
# --------------------------------------------------------------------------- #
@dataclass
class ClientServerExchange:
    """One request/reply round trip between a client and a server process."""

    client_name: str
    server_name: str
    database: Dict[str, str] = field(default_factory=dict)

    def request_reply(self, key: str) -> Tuple[List[str], str]:
        """Return the ordered message log and the reply payload.

        The client always initiates; the server only responds. Between sending
        the request and receiving the reply the client is BLOCKED.
        """
        log: List[str] = []
        log.append(f"{self.client_name} --Request(GET {key})--> {self.server_name}")
        log.append(f"{self.client_name} BLOCKS, waiting for reply")
        # Server does the requested work: look up the data.
        reply = self.database.get(key, "404 NOT FOUND")
        log.append(f"{self.server_name}: lookup '{key}' -> '{reply}'")
        log.append(f"{self.client_name} <--Reply({reply})-- {self.server_name}")
        log.append(f"{self.client_name} UNBLOCKS")
        return log, reply


def demo_client_server() -> None:
    server = ClientServerExchange(
        client_name="laptop-NYC",
        server_name="web-server-HQ",
        database={
            "/catalog": "200 OK: 4,812 products",
            "/inventory/SG": "200 OK: 137 units in Singapore",
        },
    )
    print("=" * 64)
    print("1. CLIENT-SERVER MODEL  (fixed roles, client initiates)")
    print("=" * 64)
    for path in ("/catalog", "/inventory/SG", "/missing"):
        log, _ = server.request_reply(path)
        print(f"\nRequest path: {path}")
        for line in log:
            print(f"   {line}")
    print(
        "\nProperty: one server answers many clients; if the server dies,\n"
        "every client dies. The client always initiates."
    )


# --------------------------------------------------------------------------- #
# 2. Peer-to-peer bootstrap discovery
# --------------------------------------------------------------------------- #
@dataclass
class Peer:
    """A P2P node: symmetric (both requester and responder), local index only."""

    name: str
    content: Set[str] = field(default_factory=set)
    neighbors: List[str] = field(default_factory=list)


def p2p_discover(
    peers: Dict[str, Peer], seed: str, max_hops: int = 5
) -> Tuple[Set[str], Set[str], int]:
    """Walk outward from a seed peer collecting content and member names.

    Mirrors the textbook bootstrap: go to any member, see what it has, collect
    names of more members, inspect those for more content and more names.
    Returns (known_content, known_members, hops_taken).
    """
    known_content: Set[str] = set()
    known_members: Set[str] = set()
    frontier: List[str] = [seed]
    visited: Set[str] = set()
    hops = 0
    while frontier and hops < max_hops:
        nxt: List[str] = []
        for name in frontier:
            if name in visited or name not in peers:
                continue
            visited.add(name)
            peer = peers[name]
            known_content |= peer.content
            known_members.add(name)
            for neighbor in peer.neighbors:
                known_members.add(neighbor)
                if neighbor not in visited:
                    nxt.append(neighbor)
        frontier = nxt
        if nxt:
            hops += 1
    return known_content, known_members, hops


def demo_p2p() -> None:
    peers = {
        "alice": Peer("alice", {"track-A", "track-B"}, ["bob", "carol"]),
        "bob": Peer("bob", {"track-C"}, ["carol", "dave"]),
        "carol": Peer("carol", {"track-D", "track-E"}, ["dave"]),
        "dave": Peer("dave", {"track-F"}, ["alice"]),
    }
    print("\n" + "=" * 64)
    print("2. PEER-TO-PEER MODEL  (symmetric, no central index)")
    print("=" * 64)
    content, members, hops = p2p_discover(peers, seed="alice")
    print(f"\nNew peer bootstraps from seed 'alice':")
    print(f"   members discovered: {sorted(members)}")
    print(f"   content discovered: {sorted(content)}")
    print(f"   hops to build local index: {hops}")
    print(
        "\nProperty: no server holds the catalog. Cold-start latency = the cost\n"
        "of this walk. Free-riders (download, never share) degrade the swarm."
    )


# --------------------------------------------------------------------------- #
# 3. Metcalfe's law
# --------------------------------------------------------------------------- #
def metcalfe_connections(n: int) -> int:
    """Distinct unordered pairs among n users: the complete graph K_n."""
    if n < 0:
        raise ValueError("user count must be non-negative")
    return n * (n - 1) // 2


def demo_metcalfe() -> None:
    print("\n" + "=" * 64)
    print("3. METCALFE'S LAW  (value ~ n(n-1)/2 pairwise connections)")
    print("=" * 64)
    print(f"\n{'users n':>8} | {'connections':>12} | {'value vs n=10':>14} | {'link cost ~n':>12}")
    print("-" * 56)
    base = metcalfe_connections(10)
    for n in (10, 20, 100, 1000):
        conns = metcalfe_connections(n)
        ratio = conns / base
        print(f"{n:>8} | {conns:>12,} | {ratio:>13.1f}x | {n:>12}")
    print(
        "\nDoubling users 10->20 takes connections 45->190 (~4x): the 'square'\n"
        "effect. Value grows quadratically; link cost only linearly."
    )


# --------------------------------------------------------------------------- #
# 4. E-commerce taxonomy
# --------------------------------------------------------------------------- #
_TAXONOMY = {
    ("business", "consumer"): ("B2C", "client-server", "Ordering books online"),
    ("business", "business"): ("B2B", "client-server", "Carmaker ordering tires"),
    ("government", "consumer"): ("G2C", "client-server", "Distributing tax forms"),
    ("consumer", "consumer"): ("C2C", "peer-symmetric", "Auctioning used goods"),
    ("peer", "peer"): ("P2P", "peer-to-peer", "Music / file sharing"),
}


def classify_ecommerce(initiator: str, responder: str) -> Tuple[str, str, str]:
    """Map an (initiator, responder) role pair onto the e-commerce taxonomy."""
    key = (initiator.lower(), responder.lower())
    if key not in _TAXONOMY:
        return ("UNKNOWN", "n/a", "unrecognized role pair")
    return _TAXONOMY[key]


def demo_taxonomy() -> None:
    print("\n" + "=" * 64)
    print("4. E-COMMERCE TAXONOMY  (tag -> underlying model)")
    print("=" * 64)
    print(f"\n{'tag':>5} | {'model':<14} | example")
    print("-" * 56)
    for (init, resp) in _TAXONOMY:
        tag, model, example = classify_ecommerce(init, resp)
        print(f"{tag:>5} | {model:<14} | {example}")
    print(
        "\nNote: C2C auctions are peer-symmetric because each consumer is both\n"
        "buyer AND seller, even though a site brokers them."
    )


def main() -> None:
    demo_client_server()
    demo_p2p()
    demo_metcalfe()
    demo_taxonomy()
    print("\n" + "=" * 64)
    print("Done. Same request/reply scales from one building to 15,000 km via VPN.")
    print("=" * 64)


if __name__ == "__main__":
    main()
