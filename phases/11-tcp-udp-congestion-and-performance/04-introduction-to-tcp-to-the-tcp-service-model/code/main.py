#!/usr/bin/env python3
"""TCP service-model simulator: socket, connection, byte-stream buffer.

Stdlib only. Demonstrates four concepts from Sec 6.5.1 and 6.5.2:

1. Sockets as (IP, port) pairs and connections as ordered pairs of sockets.
2. The byte-stream abstraction: writes may be coalesced or split on the wire.
3. Well-known / registered / ephemeral port ranges (RFC 6335).
4. The RFC stack that defines modern TCP (793 + 1122 + 1323 + 2018 + 2581
   + 2873 + 2988 + 3168 + 4614 + 6298 + 5681).

Run:  python3 main.py
"""
from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Socket, Connection, port allocator (Sec 6.5.2)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Socket:
    """A TCP endpoint: IP address plus a 16-bit port."""

    ip: str
    port: int

    def __post_init__(self) -> None:
        if not 0 <= self.port <= 65535:
            raise ValueError(f"port out of range: {self.port}")


@dataclass(frozen=True)
class Connection:
    """A TCP connection identified by its two end sockets.

    A single server socket can host many connections because each client
    contributes a different remote socket.
    """

    local: Socket
    remote: Socket


WELL_KNOWN_PORTS = {
    20: "FTP data", 21: "FTP control", 22: "SSH", 25: "SMTP",
    53: "DNS", 80: "HTTP", 110: "POP-3", 143: "IMAP",
    443: "HTTPS", 543: "RTSP", 631: "IPP",
}


class EphemeralPortPool:
    """Kernel-style ephemeral port allocator in 49152-65535 (RFC 6335)."""

    def __init__(self, low: int = 49152, high: int = 65535) -> None:
        self._in_use: set[int] = set()
        self._low, self._high = low, high

    def allocate(self) -> int:
        while True:
            candidate = random.randint(self._low, self._high)
            if candidate not in self._in_use:
                self._in_use.add(candidate)
                return candidate

    def release(self, port: int) -> None:
        self._in_use.discard(port)


# ---------------------------------------------------------------------------
# StreamBuffer: byte-stream semantics with no message boundaries (Sec 6.5.2)
# ---------------------------------------------------------------------------

@dataclass
class StreamBuffer:
    """Byte-stream buffer where writes do not preserve message boundaries.

    Four 512-byte writes can be read back as one 2048-byte read, two
    1024-byte reads, or any other partition the application chooses.
    """

    buffer: deque = field(default_factory=deque)
    total_bytes: int = 0

    def write(self, data: bytes) -> None:
        self.buffer.append(data)
        self.total_bytes += len(data)

    def read(self, n: int) -> bytes:
        out = bytearray()
        while len(out) < n and self.buffer:
            chunk = self.buffer[0]
            take = min(len(chunk), n - len(out))
            out.extend(chunk[:take])
            if take == len(chunk):
                self.buffer.popleft()
            else:
                self.buffer[0] = chunk[take:]
        self.total_bytes -= len(out)
        return bytes(out)


# ---------------------------------------------------------------------------
# RFC stack (Sec 6.5.1)
# ---------------------------------------------------------------------------

RFC_STACK = (
    (793, 1981, "Base TCP specification"),
    (1122, 1989, "Host requirements, error fixes"),
    (1323, 1992, "PAWS, Window Scale, Timestamps"),
    (2018, 1996, "Selective Acknowledgement (SACK)"),
    (2581, 1999, "Congestion control (slow start, AIMD, fast retransmit)"),
    (2873, 2000, "ECN nonce repurposing"),
    (2988, 2000, "Retransmission timer (replaced by 6298)"),
    (3168, 2001, "Explicit Congestion Notification in IP/TCP"),
    (4614, 2006, "TCP-related RFC roadmap"),
    (5681, 2009, "Congestion control update (replaces 2581)"),
    (6298, 2011, "Retransmission timer update (replaces 2988)"),
)


# ---------------------------------------------------------------------------
# Demos
# ---------------------------------------------------------------------------

def _demo_byte_stream() -> None:
    print("=" * 72)
    print("Byte-Stream Semantics (Sec 6.5.2 / Fig 6-35)")
    print("=" * 72)
    buf = StreamBuffer()
    for i in range(4):
        buf.write(bytes([0x41 + i]) * 512)  # four 512-byte writes
    print(f"  total_bytes after 4 writes: {buf.total_bytes}")
    one_read = buf.read(2048)
    print(f"  single read(2048) returns {len(one_read)} bytes  "
          f"(expect 2048: writes coalesced, no message boundary)")

    buf2 = StreamBuffer()
    buf2.write(bytes([0x41]) * 2048)
    r1 = buf2.read(1024)
    r2 = buf2.read(1024)
    print(f"  read(1024) twice -> {len(r1)} + {len(r2)} bytes "
          f"(expect 1024 + 1024: write split on read)")


def _demo_connections() -> None:
    print()
    print("=" * 72)
    print("Socket and Connection Identity (Sec 6.5.2)")
    print("=" * 72)
    server = Socket("10.0.0.1", 80)
    pool = EphemeralPortPool()
    clients = [Socket("10.0.0.99", pool.allocate()) for _ in range(3)]
    connections = {Connection(local=server, remote=c): f"app_{i}"
                   for i, c in enumerate(clients)}
    print(f"  server socket: {server}")
    print(f"  client sockets (ephemeral): {[str(c) for c in clients]}")
    print(f"  distinct connections hosted by one server socket: {len(connections)}")
    for conn, app in connections.items():
        print(f"    {conn} -> {app}")


def _demo_ports() -> None:
    print()
    print("=" * 72)
    print("Port Ranges (RFC 6335)")
    print("=" * 72)
    print(f"  {'Port':>6}  {'Service':<20}")
    for port in sorted(WELL_KNOWN_PORTS):
        print(f"  {port:6d}  {WELL_KNOWN_PORTS[port]}")
    print(f"  Ephemeral range: 49152-65535 ({65535 - 49152 + 1} ports)")
    pool = EphemeralPortPool()
    sample = sorted(pool.allocate() for _ in range(5))
    print(f"  random ephemeral picks: {sample}")


def _demo_rfc_stack() -> None:
    print()
    print("=" * 72)
    print("TCP RFC Stack (Sec 6.5.1)")
    print("=" * 72)
    print(f"  {'RFC':>6}  {'Year':>5}  Topic")
    for num, year, topic in RFC_STACK:
        print(f"  RFC {num:<4d}  {year:5d}  {topic}")


def main() -> None:
    _demo_byte_stream()
    _demo_connections()
    _demo_ports()
    _demo_rfc_stack()


if __name__ == "__main__":
    main()
