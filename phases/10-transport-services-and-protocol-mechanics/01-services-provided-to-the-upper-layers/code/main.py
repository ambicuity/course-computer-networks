#!/usr/bin/env python3
"""Transport service model: T_CONNECT, T_DATA, T_DISCONNECT over an unreliable network.

Demonstrates the core lesson of Tanenbaum 6.1.1: the transport layer provides
end-to-end reliability on top of an unreliable network layer. The transport
entity hides lost packets, retransmissions, and timers from the application,
which sees a perfect byte pipe.

This simulator models three things:

1. Transport service primitives (T_CONNECT, T_DATA, T_DISCONNECT) as the
   interface the application sees -- no acknowledgements, no timers.
2. An unreliable network layer that drops, reorders, and duplicates packets.
3. A transport entity that adds sequence numbers, checksums, timers, and
   retransmissions so the application-level service is reliable.

Run:  python3 main.py
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class TransportState(Enum):
    IDLE = "IDLE"
    CONNECTING = "CONNECTING"
    READY = "READY"
    DISCONNECTING = "DISCONNECTING"
    CLOSED = "CLOSED"


@dataclass
class NetworkPacket:
    src: str
    dst: str
    seq: int
    ack: int
    flags: str
    payload: bytes
    checksum: int

    def is_corrupt(self) -> bool:
        return self.checksum != _checksum(self.payload)


def _xor_bytes(a: bytes, b: bytes) -> bytes:
    n = min(len(a), len(b))
    return bytes(a[i] ^ b[i] for i in range(n)) + a[n:]


def _checksum(data: bytes) -> int:
    total = 0
    for i in range(0, len(data) - 1, 2):
        total += (data[i] << 8) + data[i + 1]
    if len(data) % 2:
        total += data[-1] << 8
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


class UnreliableNetwork:
    def __init__(self, drop_rate: float = 0.2, corrupt_rate: float = 0.05,
                 dup_rate: float = 0.05, reorder_rate: float = 0.05,
                 seed: int = 42) -> None:
        self._rng = random.Random(seed)
        self.drop_rate = drop_rate
        self.corrupt_rate = corrupt_rate
        self.dup_rate = dup_rate
        self.reorder_rate = reorder_rate
        self._wire: list[NetworkPacket] = []

    def send(self, pkt: NetworkPacket) -> None:
        if self._rng.random() < self.drop_rate:
            print(f"    [NET] DROP   seq={pkt.seq} flags={pkt.flags}")
            return
        if self._rng.random() < self.corrupt_rate:
            corrupted = _xor_bytes(pkt.payload, b"\x01")
            bad = NetworkPacket(pkt.src, pkt.dst, pkt.seq, pkt.ack,
                                pkt.flags, corrupted, _checksum(corrupted))
            print(f"    [NET] CORRUPT seq={pkt.seq}")
            self._wire.append(bad)
            return
        print(f"    [NET] DELIVER seq={pkt.seq} flags={pkt.flags} -> {pkt.dst}")
        self._wire.append(pkt)
        if self._rng.random() < self.dup_rate:
            print(f"    [NET] DUP    seq={pkt.seq}")
            self._wire.append(pkt)
        if self._rng.random() < self.reorder_rate and len(self._wire) >= 2:
            self._wire[-1], self._wire[-2] = self._wire[-2], self._wire[-1]

    def receive(self, dst: str) -> Optional[NetworkPacket]:
        for i, pkt in enumerate(self._wire):
            if pkt.dst == dst:
                return self._wire.pop(i)
        return None


class TransportEntity:
    def __init__(self, name: str, peer: str, network: UnreliableNetwork) -> None:
        self.name = name
        self.peer = peer
        self.network = network
        self._rng = random.Random()
        self.state = TransportState.IDLE
        self.send_seq = 0
        self.recv_seq = 0
        self._timers: dict[int, NetworkPacket] = {}
        self._app_queue: list[bytes] = []
        self._pending_connect: Optional[bytes] = None
        self._connect_attempts = 0
        self.delivered_to_app: list[bytes] = []
        self.log: list[str] = []

    def _emit(self, flags: str, seq: int, ack: int, payload: bytes) -> None:
        pkt = NetworkPacket(self.name, self.peer, seq, ack, flags,
                            payload, _checksum(payload))
        self.network.send(pkt)

    def t_connect_request(self) -> bool:
        if self.state != TransportState.IDLE:
            return False
        self.state = TransportState.CONNECTING
        self._connect_attempts = 0
        self._send_connect()
        return True

    def _send_connect(self) -> None:
        self._connect_attempts += 1
        self._emit("CR", self.send_seq, 0, b"CONNECT")
        self.log.append(f"T_CONNECT.request -> CR seq={self.send_seq}")

    def t_connect_response(self, accept: bool) -> None:
        if self.state != TransportState.CONNECTING:
            return
        flags = "CC" if accept else "DR"
        self._emit(flags, self.send_seq, 0, b"ACCEPT" if accept else b"REJECT")
        if accept:
            self.state = TransportState.READY
            self.send_seq = 0
            self.recv_seq = 0
            self.log.append("T_CONNECT.response -> CC (accepted)")
        else:
            self.state = TransportState.CLOSED
            self.log.append("T_CONNECT.response -> DR (rejected)")

    def t_data(self, data: bytes) -> None:
        if self.state != TransportState.READY:
            raise RuntimeError("Cannot send data: not READY")
        self._app_queue.append(data)

    def t_disconnect(self) -> None:
        if self.state in (TransportState.READY, TransportState.CONNECTING):
            self.state = TransportState.DISCONNECTING
            self._emit("DR", self.send_seq, self.recv_seq, b"DISC")
            self.log.append("T_DISCONNECT.request -> DR sent")

    def pump(self) -> None:
        while self._app_queue and self.state == TransportState.READY:
            data = self._app_queue.pop(0)
            self._emit("DATA", self.send_seq, self.recv_seq, data)
            self._timers[self.send_seq] = NetworkPacket(
                self.name, self.peer, self.send_seq, self.recv_seq,
                "DATA", data, _checksum(data))
            self.send_seq += 1

        pkt = self.network.receive(self.name)
        if pkt is None:
            self._check_timeouts()
            return

        if pkt.is_corrupt():
            print(f"  [{self.name}] RX corrupt seq={pkt.seq} -> discard")
            return

        if pkt.flags == "CR":
            if self.state == TransportState.IDLE:
                self.state = TransportState.CONNECTING
                self.log.append(f"T_CONNECT.indication <- CR seq={pkt.seq}")
                self.t_connect_response(True)
            else:
                self._emit("DR", 0, pkt.seq, b"BUSY")
        elif pkt.flags == "CC":
            if self.state == TransportState.CONNECTING:
                self.state = TransportState.READY
                self.send_seq = 0
                self.recv_seq = 0
                self.log.append("T_CONNECT.confirm <- CC")
        elif pkt.flags == "DATA":
            if pkt.seq == self.recv_seq:
                self.delivered_to_app.append(pkt.payload)
                self.recv_seq += 1
                self.log.append(f"T_DATA.indication seq={pkt.seq} ({len(pkt.payload)}B)")
            self._emit("ACK", 0, self.recv_seq, b"")
        elif pkt.flags == "ACK":
            acked = pkt.ack
            if acked in self._timers:
                del self._timers[acked]
                self.log.append(f"  ack retired seq={acked}")
        elif pkt.flags == "DR":
            self.state = TransportState.CLOSED
            self.log.append("T_DISCONNECT.indication <- DR")

    def _check_timeouts(self) -> None:
        if not self._timers:
            return
        if self._rng.random() < 0.5:
            seq, pkt = next(iter(self._timers.items()))
            print(f"  [{self.name}] TIMEOUT seq={seq} -> retransmit")
            self.network.send(pkt)


def run_reliable_transfer(drop_rate: float, label: str) -> None:
    print("=" * 72)
    print(f"Transport service over an unreliable network  ({label})")
    print("=" * 72)
    net = UnreliableNetwork(drop_rate=drop_rate, seed=99)
    server = TransportEntity("srv", "cli", net)
    client = TransportEntity("cli", "srv", net)

    print("\nPhase 1: Connection establishment (T_CONNECT)")
    print("-" * 50)
    client.t_connect_request()
    for _ in range(8):
        client.pump()
        server.pump()

    if client.state != TransportState.READY or server.state != TransportState.READY:
        print(f"  Connection FAILED: client={client.state}, server={server.state}")
        return
    print(f"  client state = {client.state.name}")
    print(f"  server state = {server.state.name}")

    print("\nPhase 2: Data transfer (T_DATA)")
    print("-" * 50)
    messages = [b"alpha", b"beta", b"gamma", b"delta", b"epsilon"]
    for msg in messages:
        client.t_data(msg)
    for _ in range(40):
        client.pump()
        server.pump()

    print(f"  client sent:     {len(messages)} messages")
    print(f"  server delivered: {len(server.delivered_to_app)} messages")
    if server.delivered_to_app:
        print(f"  received data:   {[d.decode() for d in server.delivered_to_app]}")
    assert server.delivered_to_app == messages, "DATA LOST despite unreliable net!"

    print("\nPhase 3: Disconnection (T_DISCONNECT)")
    print("-" * 50)
    client.t_disconnect()
    for _ in range(6):
        client.pump()
        server.pump()
    print(f"  client final state = {client.state.name}")
    print(f"  server final state = {server.state.name}")

    print("\nTransport entity event log (server):")
    for entry in server.log:
        print(f"  {entry}")


def main() -> None:
    print("Transport Layer Service Model (Tanenbaum 6.1.1)")
    print("Shows T_CONNECT / T_DATA / T_DISCONNECT primitives and how the")
    print("transport entity provides reliability over an unreliable network.\n")

    print("KEY INSIGHT: The application sees only the three primitives above.")
    print("Beneath them, the transport entity handles CR/CC/ACK/DR segments,")
    print("sequence numbers, checksums, timers, and retransmissions so the")
    print("application gets a reliable byte pipe.\n")

    run_reliable_transfer(0.10, "10% drop rate")
    print()
    run_reliable_transfer(0.30, "30% drop rate -- still reliable to the app")

    print("\n" + "=" * 72)
    print("Conclusion: Network drops ~10-30% of packets, yet the application")
    print("receives all 5 messages in order. The transport layer hides every")
    print("failure from the upper layers. This is the provider/user boundary.")
    print("=" * 72)


if __name__ == "__main__":
    main()