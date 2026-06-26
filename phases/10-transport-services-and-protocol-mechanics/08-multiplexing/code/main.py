#!/usr/bin/env python3
"""Transport-layer multiplexing (Tanenbaum 6.2.5).

Implements two multiplexing strategies:

1. Upward multiplexing (Fig 6-17a): Many transport connections share
   one network connection (NSAP). This is the common case -- multiple
   TCP connections over one IP address. The transport entity demuxes
   incoming segments by port/TSAP.

2. Downward (inverse) multiplexing (Fig 6-17b): One transport connection
   distributes traffic across multiple network connections (paths) to
   increase bandwidth. SCTP supports this; TCP does not.

Demonstrates:
- Connection pooling with demultiplexing by TSAP
- Round-robin traffic distribution across k network paths
- Bandwidth aggregation: effective bandwidth ~= k * single_path_bw
- The tradeoff: upward mux saves resources, downward mux increases throughput

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TransportConnection:
    conn_id: int
    local_tsap: int
    remote_tsap: int
    remote_nsap: str
    data_sent: int = 0
    data_received: int = 0
    is_active: bool = True


class UpwardMultiplexer:
    """Many transport connections over one network connection (NSAP)."""

    def __init__(self, local_nsap: str, remote_nsap: str) -> None:
        self.local_nsap = local_nsap
        self.remote_nsap = remote_nsap
        self._connections: dict[int, TransportConnection] = {}
        self._next_id = 1
        self._segments_out: int = 0

    def open_connection(self, local_port: int, remote_port: int) -> TransportConnection:
        cid = self._next_id
        self._next_id += 1
        conn = TransportConnection(cid, local_port, remote_port, self.remote_nsap)
        self._connections[cid] = conn
        return conn

    def send(self, conn_id: int, data: bytes) -> int:
        conn = self._connections[conn_id]
        conn.data_sent += len(data)
        self._segments_out += 1
        return len(data)

    def deliver(self, dst_port: int, data: bytes) -> Optional[int]:
        for conn in self._connections.values():
            if conn.local_tsap == dst_port and conn.is_active:
                conn.data_received += len(data)
                return conn.conn_id
        return None

    def close_connection(self, conn_id: int) -> None:
        if conn_id in self._connections:
            self._connections[conn_id].is_active = False

    def active_count(self) -> int:
        return sum(1 for c in self._connections.values() if c.is_active)


class DownwardMultiplexer:
    """One transport connection over multiple network connections (paths)."""

    def __init__(self, conn_id: int) -> None:
        self.conn_id = conn_id
        self._paths: list[dict] = []
        self._next_path = 0
        self.data_sent = 0

    def add_path(self, nsap: str, bandwidth_mbps: float) -> int:
        path_idx = len(self._paths)
        self._paths.append({
            "nsap": nsap,
            "bw": bandwidth_mbps,
            "bytes_sent": 0,
            "segments_sent": 0,
        })
        return path_idx

    def send(self, data: bytes) -> int:
        if not self._paths:
            raise RuntimeError("No paths available")
        path = self._paths[self._next_path % len(self._paths)]
        self._next_path += 1
        path["bytes_sent"] += len(data)
        path["segments_sent"] += 1
        self.data_sent += len(data)
        return len(data)

    def total_bandwidth(self) -> float:
        return sum(p["bw"] for p in self._paths)

    def path_stats(self) -> list[dict]:
        return list(self._paths)


def run_upward_multiplexing() -> None:
    print("=" * 72)
    print("Upward multiplexing: many transport connections over one NSAP")
    print("=" * 72)
    mux = UpwardMultiplexer("10.0.0.1", "10.0.0.2")

    print(f"\n  Local NSAP: {mux.local_nsap}")
    print(f"  Remote NSAP: {mux.remote_nsap}")
    print("\n  Opening 4 transport connections (different TSAPs/ports):")

    ports = [(1208, 25), (1209, 80), (1210, 21), (1211, 443)]
    conns = []
    for local, remote in ports:
        conn = mux.open_connection(local, remote)
        conns.append(conn)
        print(f"    conn {conn.conn_id}: TSAP {local} -> remote TSAP {remote}")

    print(f"\n  Active connections: {mux.active_count()} (all share one NSAP)")

    print("\n  Sending data on each connection:")
    messages = [b"MAIL DATA", b"HTTP REQUEST", b"FTP COMMAND", b"HTTPS HELLO"]
    for conn, msg in zip(conns, messages):
        mux.send(conn.conn_id, msg)
        print(f"    conn {conn.conn_id}: sent {len(msg)} bytes ({msg!r})")

    print(f"\n  Total segments out: {mux._segments_out}")

    print("\n  Demultiplexing incoming segments by destination TSAP:")
    for port, msg in [(25, b"MAIL OK"), (80, b"HTTP 200"), (443, b"TLS ACK")]:
        cid = mux.deliver(port, msg)
        if cid:
            print(f"    dst port {port} -> conn {cid}: delivered {len(msg)} bytes")

    print("\n  Connection table:")
    for conn in conns:
        print(f"    conn {conn.conn_id}: TSAP {conn.local_tsap} <-> "
              f"{conn.remote_tsap}, sent={conn.data_sent}B, "
              f"recv={conn.data_received}B, active={conn.is_active}")

    print("\n  Close one connection:")
    mux.close_connection(conns[2].conn_id)
    print(f"  Active connections now: {mux.active_count()}")

    print(f"""
  KEY POINT: All 4 transport connections share a single NSAP ({mux.local_nsap}).
  The transport entity demultiplexes by TSAP (port number).
  This is how TCP works: many ports, one IP address.
""")


def run_downward_multiplexing() -> None:
    print("=" * 72)
    print("Downward (inverse) multiplexing: one connection over many paths")
    print("=" * 72)
    conn = DownwardMultiplexer(conn_id=1)

    print("\n  Adding 3 network paths with different bandwidths:")
    conn.add_path("10.0.0.1", 10.0)
    conn.add_path("10.0.1.1", 10.0)
    conn.add_path("10.0.2.1", 10.0)

    total_bw = conn.total_bandwidth()
    print(f"  Single path bandwidth: 10 Mbps")
    print(f"  Total aggregated bandwidth: {total_bw} Mbps (3x improvement)")

    print("\n  Sending 12 segments round-robin across 3 paths:")
    for i in range(12):
        data = f"segment-{i:02d}".encode()
        conn.send(data)

    print(f"\n  Total data sent: {conn.data_sent} bytes")
    print("\n  Per-path distribution:")
    for i, p in enumerate(conn.path_stats()):
        print(f"    path {i} (NSAP {p['nsap']}, {p['bw']} Mbps): "
              f"{p['segments_sent']} segments, {p['bytes_sent']} bytes")

    print(f"""
  KEY POINT: One transport connection spreads traffic across k paths.
  Effective bandwidth ~= k * single_path_bw = {total_bw} Mbps.
  SCTP supports this (multi-homing); TCP uses a single path.
""")


def run_bandwidth_comparison() -> None:
    print("=" * 72)
    print("Bandwidth comparison: upward vs downward vs no multiplexing")
    print("=" * 72)

    scenarios = [
        ("No multiplexing", 1, 1, 10.0, "1 conn, 1 path, 10 Mbps"),
        ("Upward mux only", 5, 1, 10.0, "5 conns share 1 path, 10 Mbps total"),
        ("Downward mux only", 1, 3, 30.0, "1 conn over 3 paths, 30 Mbps"),
        ("Both (5 conns, 3 paths)", 5, 3, 30.0, "5 conns over 3 paths, 30 Mbps shared"),
    ]

    print(f"\n  {'Scenario':>30s}  {'Conns':>6s}  {'Paths':>6s}  {'BW':>8s}  {'Note'}")
    print(f"  {'-'*30}  {'-'*6}  {'-'*6}  {'-'*8}  {'-'*40}")
    for name, conns, paths, bw, note in scenarios:
        print(f"  {name:>30s}  {conns:>6d}  {paths:>6d}  {bw:>7.1f}M  {note}")

    print(f"""
  Tradeoffs:
    Upward mux:   Saves NSAP addresses, shares one network connection.
                  Pro: efficient resource use. Con: total bandwidth capped.
    Downward mux: Aggregates bandwidth across multiple paths.
                  Pro: higher throughput, fault tolerance.
                  Con: reordering complexity, needs protocol support.
""")


def run_connection_pooling() -> None:
    print("=" * 72)
    print("Connection pooling with upward multiplexing")
    print("=" * 72)
    mux = UpwardMultiplexer("192.168.1.100", "93.184.216.34")

    print(f"\n  Web browser opens 6 connections to the same server:")
    print(f"  All share NSAP 192.168.1.100 -> 93.184.216.34")
    ports = [50000, 50001, 50002, 50003, 50004, 50005]
    conns = []
    for p in ports:
        conn = mux.open_connection(p, 443)
        conns.append(conn)
        mux.send(conn.conn_id, f"GET /object/{p - 49999} HTTP/1.1".encode())

    print(f"\n  6 HTTP requests sent over 6 transport connections")
    print(f"  All multiplexed over ONE network connection (IP pair)")
    print(f"  Active connections: {mux.active_count()}")
    print(f"  Total segments out: {mux._segments_out}")

    for conn in conns:
        mux.deliver(conn.local_tsap, b"HTTP/1.1 200 OK")
    print(f"\n  6 responses received and demultiplexed by destination TSAP")
    for conn in conns:
        print(f"    conn {conn.conn_id}: port {conn.local_tsap}, "
              f"sent={conn.data_sent}B, recv={conn.data_received}B")

    print(f"""
  This is the normal TCP model: many ports multiplexed over one IP.
  The limitation (noted in the text): congestion control is per-connection,
  not across the group. SCTP and SST address this with grouped streams.
""")


def main() -> None:
    print("Transport-Layer Multiplexing (Tanenbaum 6.2.5)")
    print()
    print("Two forms:")
    print("  Upward   (mux):     many transport conns -> one network conn")
    print("  Downward (inv mux): one transport conn  -> many network conns")
    print()

    run_upward_multiplexing()
    run_downward_multiplexing()
    run_bandwidth_comparison()
    run_connection_pooling()

    print("=" * 72)
    print("Summary:")
    print("  Upward mux:   many TSAPs share one NSAP (TCP ports over one IP)")
    print("  Downward mux: one connection over many paths (SCTP multi-homing)")
    print("  Upward saves resources; downward increases bandwidth")
    print("  Both can coexist: many connections over many paths")
    print("=" * 72)


if __name__ == "__main__":
    main()