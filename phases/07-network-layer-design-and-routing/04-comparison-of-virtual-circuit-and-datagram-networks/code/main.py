#!/usr/bin/env python3
"""Datagram vs. virtual-circuit forwarding simulator (stdlib only).

This program forwards the same set of flows through two network-layer fabrics
so you can watch the concrete differences from Tanenbaum section 5.1.5:

  * Datagram fabric  -- each packet carries a full destination address; every
    router does a longest-prefix-match (LPM) over a CIDR forwarding table and
    forwards independently. Routers hold no per-flow state.

  * Virtual-circuit fabric -- a setup phase pins a route into per-hop "swap"
    tables and allocates a short, locally-meaningful label. Data packets are
    forwarded by exact label index, and the label is rewritten each hop
    (label switching). Labels are relabeled on clashes.

It also computes per-packet header overhead (full address vs. short label) and
injects a router crash to show the asymmetric blast radius: a datagram crash
loses only queued packets, while a VC crash terminates every circuit through
the failed node.

Run:
    python3 main.py                 # full demo
    python3 main.py --crash C       # crash router C and report survivors
    python3 main.py --size 64       # overhead table for 64-byte packets

No third-party packages, no network calls.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# --- A small fixed topology shared by both fabrics ------------------------
# Adjacency used by the virtual-circuit setup phase. There are TWO paths from
# A to the F/E side: the short path A--C--E--F and a backup A--B--E--F. The
# backup matters for the crash demo: when C dies, the datagram fabric can
# reconverge onto A--B--E, but pinned virtual circuits cannot.
NEIGHBOURS: Dict[str, List[str]] = {
    "A": ["C", "B"],
    "B": ["A", "E"],
    "C": ["A", "E", "D"],
    "D": ["C"],
    "E": ["C", "B", "F"],
    "F": ["E"],
}

IPV4_ADDR_BITS = 32          # one IPv4 address (RFC 791)
IPV6_ADDR_BITS = 128         # one IPv6 address (RFC 8200)
MPLS_LABEL_BITS = 20         # RFC 3032 shim label field
ATM_VPI_VCI_BITS = 24        # ITU-T I.361 (8-bit VPI + 16-bit VCI)
FRAME_RELAY_DLCI_BITS = 10   # ITU-T Q.922 DLCI


# --- Datagram fabric: longest-prefix-match forwarding ---------------------
@dataclass(frozen=True)
class Route:
    """A CIDR forwarding-table entry."""
    prefix: int          # network address as a 32-bit integer
    masklen: int         # prefix length, 0..32
    out_router: str      # next-hop router (our stand-in for an interface)

    def matches(self, addr: int) -> bool:
        if self.masklen == 0:
            return True  # default route 0.0.0.0/0
        mask = (0xFFFFFFFF << (32 - self.masklen)) & 0xFFFFFFFF
        return (addr & mask) == (self.prefix & mask)


def ip_to_int(dotted: str) -> int:
    """Convert dotted-quad IPv4 to a 32-bit integer (manual, no ipaddress)."""
    parts = dotted.split(".")
    if len(parts) != 4:
        raise ValueError(f"bad IPv4 address: {dotted!r}")
    value = 0
    for octet in parts:
        n = int(octet)
        if not 0 <= n <= 255:
            raise ValueError(f"octet out of range in {dotted!r}")
        value = (value << 8) | n
    return value


class DatagramRouter:
    """A stateless router that forwards by longest-prefix match."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.table: List[Route] = []

    def add_route(self, prefix: str, masklen: int, out_router: str) -> None:
        self.table.append(Route(ip_to_int(prefix), masklen, out_router))

    def lookup(self, dest: int) -> Optional[Route]:
        best: Optional[Route] = None
        for route in self.table:
            if route.matches(dest) and (best is None or route.masklen > best.masklen):
                best = route
        return best


def build_datagram_fabric(crashed: Optional[str] = None) -> Dict[str, DatagramRouter]:
    """One stateless router per node, each with a few CIDR entries.

    If ``crashed`` is set, the routing protocol is assumed to have reconverged:
    A prefers the backup path A--B--E for 10.2.0.0/16 instead of A--C--E.
    """
    routers = {name: DatagramRouter(name) for name in NEIGHBOURS}
    # 10.2.0.0/16 hangs off F; 10.3.0.0/16 hangs off D.
    # Each router points one hop closer along the preferred path.
    if crashed == "C":
        routers["A"].add_route("10.2.0.0", 16, "B")   # reconverged: bypass C
        routers["B"].add_route("10.2.0.0", 16, "E")
    else:
        routers["A"].add_route("10.2.0.0", 16, "C")
    routers["A"].add_route("10.3.0.0", 16, "C")
    routers["A"].add_route("0.0.0.0", 0, "B")
    routers["C"].add_route("10.2.0.0", 16, "E")
    routers["C"].add_route("10.3.0.0", 16, "D")
    routers["E"].add_route("10.2.0.0", 16, "F")
    routers["F"].add_route("10.2.0.0", 16, "F")   # locally attached
    routers["D"].add_route("10.3.0.0", 16, "D")   # locally attached
    return routers


def forward_datagram(
    routers: Dict[str, DatagramRouter],
    start: str,
    dest_str: str,
    crashed: Optional[str],
) -> Tuple[List[str], bool]:
    """Walk a packet hop by hop. Returns (path, delivered?).

    Models post-reconvergence delivery: the routers dict already reflects the
    rerouted table, so a packet that does not transit the crashed node still
    reaches its destination (a datagram fabric heals by rerouting).
    """
    dest = ip_to_int(dest_str)
    path = [start]
    hop = start
    for _ in range(16):  # TTL guard
        if hop == crashed:
            return path, False  # packet queued in the crashed router -> lost
        route = routers[hop].lookup(dest)
        if route is None:
            return path, False
        if route.out_router == hop:  # locally attached -> delivered
            return path, True
        hop = route.out_router
        path.append(hop)
    return path, False


# --- Virtual-circuit fabric: setup + label-swap forwarding ----------------
@dataclass
class VCRouter:
    """A router that forwards by exact label index and swaps labels per hop."""
    name: str
    # (in_router, in_label) -> (out_router, out_label)
    swap: Dict[Tuple[str, int], Tuple[str, int]] = field(default_factory=dict)
    next_free_label: int = 1

    def alloc_label(self) -> int:
        label = self.next_free_label
        self.next_free_label += 1
        return label


@dataclass
class Circuit:
    cid: str
    path: List[str]
    in_labels: List[int]  # label each router expects on its incoming interface


def setup_circuit(
    fabric: Dict[str, VCRouter],
    cid: str,
    path: List[str],
    chosen_first_label: int,
) -> Circuit:
    """Pin a route into the per-hop swap tables, relabeling on clashes.

    ``chosen_first_label`` is the label the source host picks; it may clash with
    another circuit's label, which is exactly why routers must swap.
    """
    in_labels = [chosen_first_label]
    in_label = chosen_first_label
    for i in range(len(path) - 1):
        here, nxt = path[i], path[i + 1]
        prev = path[i - 1] if i > 0 else "HOST"
        out_label = fabric[nxt].alloc_label()  # downstream picks a fresh label
        fabric[here].swap[(prev, in_label)] = (nxt, out_label)
        in_labels.append(out_label)
        in_label = out_label
    return Circuit(cid=cid, path=path, in_labels=in_labels)


def forward_vc(
    fabric: Dict[str, VCRouter],
    circuit: Circuit,
    crashed: Optional[str],
) -> Tuple[List[Tuple[str, int]], bool]:
    """Forward a data packet by exact label index. Returns (trace, delivered)."""
    trace: List[Tuple[str, int]] = []
    label = circuit.in_labels[0]
    prev = "HOST"
    for i in range(len(circuit.path) - 1):
        here = circuit.path[i]
        if here == crashed:
            return trace, False  # circuit state lost -> circuit is dead
        trace.append((here, label))
        out = fabric[here].swap.get((prev, label))
        if out is None:
            return trace, False
        prev = here
        _here_next, label = out
    trace.append((circuit.path[-1], label))
    return trace, True


# --- Header overhead -------------------------------------------------------
def overhead_table(packet_bytes: int) -> List[Tuple[str, int, float]]:
    total_bits = packet_bytes * 8
    rows = [
        ("IPv4 src+dst address", 2 * IPV4_ADDR_BITS),
        ("IPv6 src+dst address", 2 * IPV6_ADDR_BITS),
        ("MPLS label", MPLS_LABEL_BITS),
        ("ATM VPI/VCI", ATM_VPI_VCI_BITS),
        ("Frame Relay DLCI", FRAME_RELAY_DLCI_BITS),
    ]
    return [(name, bits, 100.0 * bits / total_bits) for name, bits in rows]


# --- Demo ------------------------------------------------------------------
# (flow id, datagram dest, vc path, host-chosen first label)
FLOWS: List[Tuple[str, str, List[str], int]] = [
    ("f1-cardauth", "10.2.5.9", ["A", "C", "E", "F"], 1),
    ("f2-replica", "10.2.7.1", ["A", "C", "E", "F"], 1),  # same label 1 -> clash!
    ("f3-branchD", "10.3.0.4", ["A", "C", "D"], 1),
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Datagram vs. virtual-circuit demo")
    parser.add_argument("--crash", metavar="ROUTER", default=None,
                        help="crash a transit router (e.g. C) and report blast radius")
    parser.add_argument("--size", type=int, default=64,
                        help="packet size in bytes for the overhead table")
    args = parser.parse_args()
    crashed: Optional[str] = args.crash

    print("=" * 66)
    print(" DATAGRAM FABRIC  (full address, longest-prefix match, no state)")
    print("=" * 66)
    dgram = build_datagram_fabric(crashed)
    for fid, dest, _path, _lbl in FLOWS:
        path, ok = forward_datagram(dgram, "A", dest, crashed)
        status = "DELIVERED" if ok else "LOST"
        print(f"  {fid:14s} dst={dest:9s}  {' -> '.join(path):20s}  {status}")

    print()
    print("=" * 66)
    print(" VIRTUAL-CIRCUIT FABRIC  (setup, short label, per-hop swap)")
    print("=" * 66)
    vc = {name: VCRouter(name) for name in NEIGHBOURS}
    circuits: List[Circuit] = [
        setup_circuit(vc, fid, path, first) for fid, _dest, path, first in FLOWS
    ]
    print("  Setup complete. Per-hop swap tables (in_label -> out_label):")
    for name in ("A", "C", "E"):
        for (prev, inl), (nxt, outl) in vc[name].swap.items():
            print(f"    router {name}: from {prev:5s} label {inl} "
                  f"-> to {nxt:4s} label {outl}")
    print("  Note: f1 and f2 both entered A as label 1; downstream labels")
    print("  were swapped to keep them distinct (label switching).")
    print()
    for circuit in circuits:
        trace, ok = forward_vc(vc, circuit, crashed)
        rendered = " -> ".join(f"{r}:L{l}" for r, l in trace)
        status = "DELIVERED" if ok else "TERMINATED"
        print(f"  {circuit.cid:14s} {rendered:34s}  {status}")

    if crashed:
        print()
        print("-" * 66)
        d_lost = sum(
            1 for f in FLOWS if not forward_datagram(dgram, "A", f[1], crashed)[1]
        )
        v_lost = sum(1 for c in circuits if not forward_vc(vc, c, crashed)[1])
        print(f"  Router {crashed} crashed.")
        print(f"  Datagram flows still LOST after reconvergence: "
              f"{d_lost}/{len(FLOWS)} (flows with a backup path rerouted and "
              f"healed; senders retransmit the few queued packets)")
        print(f"  Virtual circuits torn down: {v_lost}/{len(circuits)} "
              f"(every VC through {crashed} is dead and must be re-set-up)")

    print()
    print("=" * 66)
    print(f" PER-PACKET HEADER OVERHEAD  (packet size = {args.size} bytes)")
    print("=" * 66)
    for name, bits, pct in overhead_table(args.size):
        print(f"  {name:24s} {bits:4d} bits  {pct:6.1f}% of packet")


if __name__ == "__main__":
    main()
