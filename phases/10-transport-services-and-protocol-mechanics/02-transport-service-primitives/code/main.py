#!/usr/bin/env python3
"""Transport service state machine and primitive flow (Tanenbaum 6.1.2).

Implements the five transport service primitives -- LISTEN, CONNECT,
SEND, RECEIVE, DISCONNECT -- and the state machine that governs them:
IDLE -> CONNECTING -> READY -> DISCONNECTING -> IDLE.

The four message types exchanged by transport entities map to the four
primitive types at the service interface:

    .request   - transport user -> transport entity (local action)
    .indication- transport entity -> transport user (remote triggered)
    .response  - transport user -> transport entity (reply to indication)
    .confirm   - transport entity -> transport user (reply confirmed)

Demonstrates:
1. A full client-server connection lifecycle driven by primitives.
2. The state diagram of Fig 6-4 (passive/active establishment and release).
3. The difference between symmetric and asymmetric disconnect.
4. Failure modes: connect to a non-listening server, duplicate CR rejection.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TSState(Enum):
    IDLE = "IDLE"
    PASSIVE_ESTABLISHMENT_PENDING = "PASSIVE_EST_PENDING"
    ACTIVE_ESTABLISHMENT_PENDING = "ACTIVE_EST_PENDING"
    ESTABLISHED = "ESTABLISHED"
    PASSIVE_DISCONNECT_PENDING = "PASSIVE_DISC_PENDING"
    ACTIVE_DISCONNECT_PENDING = "ACTIVE_DISC_PENDING"


@dataclass
class Segment:
    kind: str
    seq: int
    ack: int
    payload: bytes = b""


@dataclass
class TransportEndpoint:
    name: str
    state: TSState = TSState.IDLE
    send_seq: int = 0
    recv_seq: int = 0
    listening: bool = False
    inbox: list[Segment] = field(default_factory=list)
    delivered: list[bytes] = field(default_factory=list)
    log: list[str] = field(default_factory=list)

    def _record(self, msg: str) -> None:
        self.log.append(f"[{self.name}] {msg}")
        print(f"  [{self.name}] {msg}")


class TransportService:
    def __init__(self) -> None:
        self._wire_a_to_b: list[Segment] = []
        self._wire_b_to_a: list[Segment] = []

    def _deliver(self, src: TransportEndpoint, dst: TransportEndpoint,
                wire: list[Segment]) -> None:
        while wire:
            seg = wire.pop(0)
            dst.inbox.append(seg)

    def listen(self, ep: TransportEndpoint) -> None:
        if ep.state != TSState.IDLE:
            raise RuntimeError(f"{ep.name}: LISTEN requires IDLE, got {ep.state.name}")
        ep.listening = True
        ep.state = TSState.PASSIVE_ESTABLISHMENT_PENDING
        ep._record("LISTEN (block until CONNECT arrives)")

    def connect(self, ep: TransportEndpoint, dst: TransportEndpoint) -> None:
        if ep.state != TSState.IDLE:
            raise RuntimeError(f"{ep.name}: CONNECT requires IDLE, got {ep.state.name}")
        ep.state = TSState.ACTIVE_ESTABLISHMENT_PENDING
        ep._record(f"CONNECT.request -> send CR seq={ep.send_seq}")
        self._wire_a_to_b.append(Segment("CR", ep.send_seq, 0))
        ep.send_seq += 1

    def _handle_cr(self, src: TransportEndpoint, dst: TransportEndpoint) -> None:
        seg = dst.inbox.pop(0)
        if dst.state == TSState.PASSIVE_ESTABLISHMENT_PENDING and dst.listening:
            dst._record(f"T_CONNECT.indication <- CR seq={seg.seq}")
            dst.state = TSState.ESTABLISHED
            dst.recv_seq = seg.seq + 1
            dst._record("T_CONNECT.response(accept) -> send CC")
            self._wire_b_to_a.append(Segment("CC", dst.send_seq, seg.seq + 1))
            dst.send_seq += 1
        else:
            dst._record(f"CR arrived but not listening (state={dst.state.name}) -> DR")
            self._wire_b_to_a.append(Segment("DR", 0, 0))

    def _handle_cc(self, src: TransportEndpoint, dst: TransportEndpoint) -> None:
        seg = dst.inbox.pop(0)
        if dst.state == TSState.ACTIVE_ESTABLISHMENT_PENDING:
            dst._record(f"T_CONNECT.confirm <- CC seq={seg.seq} ack={seg.ack}")
            dst.state = TSState.ESTABLISHED
            dst.recv_seq = seg.seq + 1

    def send(self, ep: TransportEndpoint, dst: TransportEndpoint, data: bytes) -> None:
        if ep.state != TSState.ESTABLISHED:
            raise RuntimeError(f"{ep.name}: SEND requires ESTABLISHED, got {ep.state.name}")
        ep._record(f"SEND.request -> DATA seq={ep.send_seq} ({len(data)}B)")
        if ep.name < dst.name:
            self._wire_a_to_b.append(Segment("DATA", ep.send_seq, ep.recv_seq, data))
        else:
            self._wire_b_to_a.append(Segment("DATA", ep.send_seq, ep.recv_seq, data))
        ep.send_seq += 1

    def _handle_data(self, src: TransportEndpoint, dst: TransportEndpoint) -> None:
        seg = dst.inbox.pop(0)
        if seg.seq == dst.recv_seq:
            dst.delivered.append(seg.payload)
            dst._record(f"T_DATA.indication <- DATA seq={seg.seq} -> deliver to app")
            dst.recv_seq += 1
        else:
            dst._record(f"DATA seq={seg.seq} out of order (expected {dst.recv_seq}) -> discard")
        if dst.name < src.name:
            self._wire_b_to_a.append(Segment("ACK", 0, dst.recv_seq))
        else:
            self._wire_a_to_b.append(Segment("ACK", 0, dst.recv_seq))

    def _handle_ack(self, ep: TransportEndpoint) -> None:
        seg = ep.inbox.pop(0)
        if ep.state == TSState.ACTIVE_DISCONNECT_PENDING:
            ep._record("ACK for DR received -> release connection")
            ep.state = TSState.IDLE
        else:
            ep._record(f"ACK ack={seg.ack} (cumulative)")

    def disconnect(self, ep: TransportEndpoint, dst: TransportEndpoint) -> None:
        if ep.state not in (TSState.ESTABLISHED, TSState.PASSIVE_DISCONNECT_PENDING):
            raise RuntimeError(f"{ep.name}: DISCONNECT requires ESTABLISHED or PASSIVE_DISC, got {ep.state.name}")
        ep.state = TSState.ACTIVE_DISCONNECT_PENDING
        ep._record("DISCONNECT.request -> send DR")
        if ep.name < dst.name:
            self._wire_a_to_b.append(Segment("DR", ep.send_seq, ep.recv_seq))
        else:
            self._wire_b_to_a.append(Segment("DR", ep.send_seq, ep.recv_seq))

    def _handle_dr(self, src: TransportEndpoint, dst: TransportEndpoint) -> None:
        seg = dst.inbox.pop(0)
        if dst.state == TSState.ESTABLISHED:
            dst._record("T_DISCONNECT.indication <- DR -> PASSIVE_DISC_PENDING")
            dst.state = TSState.PASSIVE_DISCONNECT_PENDING
            if src.state == TSState.ACTIVE_DISCONNECT_PENDING:
                self._wire_b_to_a.append(Segment("ACK", 0, 0))
        elif dst.state == TSState.ACTIVE_ESTABLISHMENT_PENDING:
            dst._record("T_DISCONNECT.indication <- DR (connect refused) -> IDLE")
            dst.state = TSState.IDLE
        elif dst.state == TSState.PASSIVE_DISCONNECT_PENDING:
            dst._record("T_DISCONNECT.indication <- DR (symmetric) -> release")
            dst.state = TSState.IDLE

    def _handle_dr_ack(self, ep: TransportEndpoint) -> None:
        seg = ep.inbox.pop(0)
        if ep.state == TSState.ACTIVE_DISCONNECT_PENDING:
            ep._record("ACK for DR received -> release connection")
            ep.state = TSState.IDLE

    def pump(self, a: TransportEndpoint, b: TransportEndpoint) -> None:
        for _ in range(4):
            self._deliver(a, b, self._wire_a_to_b)
            self._deliver(b, a, self._wire_b_to_a)
            had_work = False
            while a.inbox:
                seg = a.inbox[0]
                if seg.kind == "CR":
                    self._handle_cr(b, a)
                elif seg.kind == "CC":
                    self._handle_cc(b, a)
                elif seg.kind == "DATA":
                    self._handle_data(b, a)
                elif seg.kind == "ACK":
                    self._handle_ack(a)
                elif seg.kind == "DR":
                    self._handle_dr(b, a)
                else:
                    break
                had_work = True
            while b.inbox:
                seg = b.inbox[0]
                if seg.kind == "CR":
                    self._handle_cr(a, b)
                elif seg.kind == "CC":
                    self._handle_cc(a, b)
                elif seg.kind == "DATA":
                    self._handle_data(a, b)
                elif seg.kind == "ACK":
                    self._handle_ack(b)
                elif seg.kind == "DR":
                    self._handle_dr(a, b)
                else:
                    break
                had_work = True
            if not had_work and not self._wire_a_to_b and not self._wire_b_to_a:
                break


def run_normal_lifecycle() -> None:
    print("=" * 72)
    print("Normal connection lifecycle: LISTEN, CONNECT, SEND, DISCONNECT")
    print("=" * 72)
    svc = TransportService()
    server = TransportEndpoint("server")
    client = TransportEndpoint("client")

    print("\nStep 1: Server LISTEN (passive open)")
    svc.listen(server)

    print("\nStep 2: Client CONNECT (active open) -> CR segment")
    svc.connect(client, server)

    print("\nStep 3: Pump network -> server gets CR, sends CC")
    svc.pump(client, server)

    print(f"\n  States: client={client.state.name}, server={server.state.name}")
    assert client.state == TSState.ESTABLISHED
    assert server.state == TSState.ESTABLISHED

    print("\nStep 4: Data exchange (SEND / T_DATA.indication)")
    for msg in [b"Hello", b"World", b"Test"]:
        svc.send(client, server, msg)
        svc.pump(client, server)
    print(f"\n  Server delivered: {[d.decode() for d in server.delivered]}")
    assert server.delivered == [b"Hello", b"World", b"Test"]

    print("\nStep 5: Asymmetric DISCONNECT (client initiates)")
    svc.disconnect(client, server)
    svc.pump(client, server)
    svc.pump(client, server)
    print(f"\n  Final states: client={client.state.name}, server={server.state.name}")
    assert client.state == TSState.IDLE
    assert server.state in (TSState.IDLE, TSState.PASSIVE_DISCONNECT_PENDING)

    print("\nState sequence (server):")
    print("  IDLE -> PASSIVE_EST_PENDING -> ESTABLISHED -> IDLE")
    print("State sequence (client):")
    print("  IDLE -> ACTIVE_EST_PENDING -> ESTABLISHED -> ACTIVE_DISC_PENDING -> IDLE")


def run_connect_refused() -> None:
    print("\n" + "=" * 72)
    print("Failure mode: CONNECT to a non-listening server -> DR (rejected)")
    print("=" * 72)
    svc = TransportService()
    server = TransportEndpoint("server")
    client = TransportEndpoint("client")

    print("\nClient CONNECTs, but server has NOT called LISTEN")
    svc.connect(client, server)
    svc.pump(client, server)
    svc.pump(client, server)
    print(f"\n  client state = {client.state.name} (should be IDLE after DR)")
    assert client.state == TSState.IDLE


def run_duplicate_cr() -> None:
    print("\n" + "=" * 72)
    print("Failure mode: Duplicate/delayed CR rejected")
    print("=" * 72)
    svc = TransportService()
    server = TransportEndpoint("server")
    client = TransportEndpoint("client")

    svc.listen(server)
    svc.connect(client, server)
    svc.pump(client, server)
    print(f"\n  Established: client={client.state.name}, server={server.state.name}")

    print("\n  Now inject a stale duplicate CR (old seq=0)...")
    stale = Segment("CR", 0, 0)
    server.inbox.append(stale)
    svc.pump(client, server)
    svc.pump(client, server)
    print(f"  server state = {server.state.name} (stays ESTABLISHED, stale rejected)")


def run_symmetric_disconnect() -> None:
    print("\n" + "=" * 72)
    print("Symmetric release: both sides DISCONNECT independently")
    print("=" * 72)
    svc = TransportService()
    server = TransportEndpoint("server")
    client = TransportEndpoint("client")

    svc.listen(server)
    svc.connect(client, server)
    svc.pump(client, server)

    print("\n  Client sends DISCONNECT (I have no more data to send)")
    svc.disconnect(client, server)
    svc.pump(client, server)

    print("  Server can still send data after its DR indication? No --")
    print("  In symmetric mode each direction closes separately.")
    print("  Server now sends its own DISCONNECT")
    svc.disconnect(server, client)
    svc.pump(client, server)
    svc.pump(client, server)
    print(f"\n  Final: client={client.state.name}, server={server.state.name}")


def main() -> None:
    print("Transport Service Primitives & State Machine (Tanenbaum 6.1.2)")
    print()
    print("Primitives:  LISTEN  CONNECT  SEND  RECEIVE  DISCONNECT")
    print("States:      IDLE -> CONNECTING -> ESTABLISHED -> DISCONNECTING -> IDLE")
    print("Messages:    CR (connection req)  CC (connection confirm)")
    print("             DATA                   ACK (internal, not visible to app)")
    print("             DR (disconnect req)    DC (disconnect confirm)")
    print()

    run_normal_lifecycle()
    run_connect_refused()
    run_duplicate_cr()
    run_symmetric_disconnect()

    print("\n" + "=" * 72)
    print("Key insight: To the transport USER, a connection is a reliable pipe.")
    print("The transport ENTITY manages CR/CC/ACK/DR segments, sequence numbers,")
    print("and state transitions. The user never sees acknowledgements or timers.")
    print("=" * 72)


if __name__ == "__main__":
    main()
