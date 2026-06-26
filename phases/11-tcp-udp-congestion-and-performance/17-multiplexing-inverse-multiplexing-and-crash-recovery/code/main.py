#!/usr/bin/env python3
"""Simulator for transport multiplexing, inverse multiplexing (SCTP-style),
and the host-crash-recovery matrix from Tanenbaum Ch. 6 (sections 6.2.5-6.2.6).

The simulator runs four demonstrations:
  1. A 5-tuple hash table that routes incoming segments to the right socket.
  2. A round-robin inverse multiplexer that splits a byte stream across N
     paths and reassembles in order.
  3. The 8 x 6 crash-recovery matrix from Figure 6-18 of the chapter.
  4. A short SCTP vs MPTCP comparison.

No network calls, no third-party packages -- pure stdlib.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Optional


# ----- 1. Multiplexing: many TSAPs to one NSAP -------------------------------


@dataclass(frozen=True)
class Segment:
    proto: int  # 6 = TCP, 17 = UDP
    src_ip: str
    src_port: int
    dst_ip: str
    dst_port: int
    payload: str


@dataclass
class Socket:
    label: str
    recv_queue: list[Segment] = field(default_factory=list)


class Demultiplexer:
    """5-tuple hash table -- the kernel's transport demultiplexer."""

    def __init__(self) -> None:
        self.table: dict[tuple, str] = {}
        self.sockets: dict[str, Socket] = {}

    def listen(self, label: str, proto: int, local_ip: str, local_port: int) -> None:
        key = (proto, local_ip, local_port)
        self.table[key] = label
        self.sockets[label] = Socket(label=label)

    def connect(self, label: str, proto: int, local_ip: str, local_port: int,
                remote_ip: str, remote_port: int) -> None:
        key = (proto, local_ip, local_port, remote_ip, remote_port)
        self.table[key] = label
        self.sockets[label] = Socket(label=label)

    def deliver(self, seg: Segment) -> Optional[str]:
        keys_to_try = [
            (seg.proto, seg.dst_ip, seg.dst_port, seg.src_ip, seg.src_port),
            (seg.proto, seg.dst_ip, seg.dst_port),
        ]
        for key in keys_to_try:
            label = self.table.get(key)
            if label is not None:
                self.sockets[label].recv_queue.append(seg)
                return label
        return None


def demo_multiplexing() -> None:
    print("=" * 72)
    print("1. MULTIPLEXING  (5-tuple hash table, many TSAPs on one NSAP)")
    print("=" * 72)
    dm = Demultiplexer()
    dm.listen("web", 6, "10.0.0.1", 80)
    dm.listen("ssh", 6, "10.0.0.1", 22)
    dm.connect("clientA", 6, "10.0.0.2", 51000, "10.0.0.1", 80)
    dm.connect("clientB", 6, "10.0.0.3", 51001, "10.0.0.1", 80)
    for s in (
        Segment(6, "10.0.0.2", 51000, "10.0.0.1", 80, "GET /"),
        Segment(6, "10.0.0.3", 51001, "10.0.0.1", 80, "POST /api"),
        Segment(6, "10.0.0.4", 55000, "10.0.0.1", 22, "SSH_INIT"),
        Segment(6, "10.0.0.5", 55001, "10.0.0.1", 22, "SSH_INIT2"),
    ):
        label = dm.deliver(s)
        print(f"  delivered to socket {label!r}: {s.payload}")
    print()
    print("  The same 5-tuple (proto, src, sport, dst, dport) always lands")
    print("  in the same socket; different source ports split the stream.")


# ----- 2. Inverse multiplexing: SCTP-style round-robin -----------------------


@dataclass
class PathDelivery:
    path: int
    seq: int
    payload: str
    delivered_at: int


def demo_inverse_multiplexing(num_paths: int = 3, num_segments: int = 12) -> None:
    print()
    print("=" * 72)
    print(f"2. INVERSE MULTIPLEXING  (round-robin over {num_paths} paths)")
    print("=" * 72)
    latency = {1: 5, 2: 12, 3: 7}
    sent: list[PathDelivery] = []
    arrival: list[PathDelivery] = []
    for i in range(num_segments):
        path = (i % num_paths) + 1
        d = PathDelivery(path=path, seq=i, payload=f"m{i}", delivered_at=0)
        sent.append(d)
        arrival.append(d)
    arrival.sort(key=lambda d: d.delivered_at + latency[d.path])
    print(f"  {'send order':<12}  -> path  ->  {'arrive order':<12}")
    for s, a in zip(sent, arrival):
        print(f"  seq={s.seq:<3} m{s.payload:<4}  -> path {s.path}  ->  arrived at "
              f"t={latency[s.path]:>2} (order {a.seq})")

    print()
    print("  Receiver reassembly buffer (heap by sequence number):")
    heap: list[tuple[int, PathDelivery]] = []
    for d in arrival:
        heapq.heappush(heap, (d.seq, d))
    reassembled: list[PathDelivery] = []
    while heap:
        reassembled.append(heapq.heappop(heap)[1])
    print("  in-order payload:", " ".join(d.payload for d in reassembled))


# ----- 3. Crash recovery: the 8 x 6 matrix ------------------------------------


def demo_crash_recovery() -> None:
    print()
    print("=" * 72)
    print("3. CRASH RECOVERY MATRIX  (Tanenbaum Fig. 6-18)")
    print("=" * 72)
    print("  Events: A = send ACK, W = write to user, C = crash.")
    print("  Parens mark orderings where C is last; A and W cannot follow C.")
    print()
    print("  Client strategy         | AC(W) | AWC   | C(AW) | C(WA) | WAC  | WC(A)")
    print("  ------------------------+-------+-------+-------+-------+------+------")
    matrix = {
        ("ACK first",  "always"):     ["OK",   "DUP", "OK",   "OK",   "DUP", "DUP"],
        ("ACK first",  "never"):      ["LOST", "OK",  "LOST", "LOST", "OK",  "OK"],
        ("ACK first",  "S0"):         ["OK",   "DUP", "LOST", "LOST", "DUP", "OK"],
        ("ACK first",  "S1"):         ["LOST", "OK",  "OK",   "OK",   "OK",  "DUP"],
        ("Write first","always"):     ["OK",   "DUP", "OK",   "OK",   "DUP", "DUP"],
        ("Write first","never"):      ["LOST", "OK",  "LOST", "LOST", "OK",  "OK"],
        ("Write first","S0"):         ["OK",   "DUP", "LOST", "LOST", "DUP", "OK"],
        ("Write first","S1"):         ["LOST", "OK",  "OK",   "OK",   "OK",  "DUP"],
    }
    orderings = ["AC(W)", "AWC", "C(AW)", "C(WA)", "WAC", "WC(A)"]
    for (server, client), row in matrix.items():
        cells = " | ".join(f"{c:<5}" for c in row)
        print(f"  {server:>11} {client:<6}| {cells}")
    print()
    print("  Every cell has at least one LOST or DUP. Conclusion:")
    print("  'Recovery from a layer N crash can only be done by layer N+1'.")


# ----- 4. SCTP vs MPTCP comparison --------------------------------------------


def demo_sctp_vs_mptcp() -> None:
    print()
    print("=" * 72)
    print("4. SCTP vs MPTCP")
    print("=" * 72)
    print("  SCTP  (RFC 4960)")
    print("    - association: one state, many streams, many paths")
    print("    - multi-homing: primary + failover paths")
    print("    - 4-way handshake (INIT, INIT-ACK, COOKIE-ECHO, COOKIE-ACK)")
    print("    - 32-bit verification tag closes the SYN-flood gap")
    print("    - use case: SS7-over-IP, Diameter, telecom signalling")
    print()
    print("  MPTCP  (RFC 8684)")
    print("    - extends TCP, not a new wire format")
    print("    - default scheduler: lowest smoothed RTT first")
    print("    - aggregate Wi-Fi + cellular on phones")
    print("    - Apple iOS and Samsung Android enable by default")
    print("    - use case: bandwidth aggregation, seamless path failover")


def main() -> None:
    demo_multiplexing()
    demo_inverse_multiplexing()
    demo_crash_recovery()
    demo_sctp_vs_mptcp()
    print()
    print("=" * 72)
    print("Lesson complete. See docs/en.md for the full multiplexing,")
    print("inverse-multiplexing, and crash-recovery discussion.")
    print("=" * 72)


if __name__ == "__main__":
    main()
