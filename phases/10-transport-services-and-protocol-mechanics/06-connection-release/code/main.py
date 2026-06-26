#!/usr/bin/env python3
"""Connection release protocols (Tanenbaum 6.2.3).

Implements and demonstrates:
1. Asymmetric (abrupt) release -- one side sends DR, connection is broken.
   Shows data loss when DR arrives before in-flight data (Fig 6-12).
2. Symmetric (graceful) release -- each direction closed separately.
3. The three-way handshake release protocol (Fig 6-14) with four scenarios:
   (a) Normal: DR -> DR -> ACK -> both release
   (b) Final ACK lost: receiver uses timer to release
   (c) Response DR lost: initiator retransmits DR
   (d) All DRs lost: both sides time out and release independently
4. The two-army problem: proving no protocol can guarantee agreement.
5. Half-open connection detection via inactivity timer.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ReleaseState(Enum):
    ESTABLISHED = "ESTABLISHED"
    DISCONNECT_PENDING = "DISCONNECT_PENDING"
    RELEASED = "RELEASED"


@dataclass
class Segment:
    kind: str
    seq: int = 0
    payload: bytes = b""


class Channel:
    def __init__(self) -> None:
        self._queue: list[tuple[Segment, bool]] = []
        self.drop_next: bool = False
        self.dropped: list[Segment] = []

    def send(self, seg: Segment) -> None:
        if self.drop_next:
            self.drop_next = False
            self.dropped.append(seg)
            return
        self._queue.append((seg, True))

    def receive(self) -> Optional[Segment]:
        if self._queue:
            return self._queue.pop(0)[0]
        return None

    def has_pending(self) -> bool:
        return bool(self._queue)


@dataclass
class Host:
    name: str
    state: ReleaseState = ReleaseState.ESTABLISHED
    timer: int = 0
    timer_running: bool = False
    retransmit_count: int = 0
    max_retransmits: int = 3
    inactivity_timeout: int = 5
    idle_ticks: int = 0
    delivered: list[bytes] = field(default_factory=list)
    log: list[str] = field(default_factory=list)
    is_initiator: bool = False

    def _record(self, msg: str) -> None:
        self.log.append(f"[{self.name}] {msg}")
        print(f"  [{self.name}] {msg}")

    def send_dr(self, ch: Channel) -> None:
        self.state = ReleaseState.DISCONNECT_PENDING
        self.timer_running = True
        self.timer = 0
        self.is_initiator = True
        ch.send(Segment("DR"))
        self._record("send DR + start timer")

    def handle_dr(self, seg: Segment, ch: Channel) -> None:
        if self.state == ReleaseState.ESTABLISHED:
            self._record("recv DR -> send DR + start timer")
            self.state = ReleaseState.DISCONNECT_PENDING
            self.timer_running = True
            self.timer = 0
            ch.send(Segment("DR"))
        elif self.state == ReleaseState.DISCONNECT_PENDING:
            self._record("recv DR (response) -> send ACK")
            ch.send(Segment("ACK"))

    def handle_ack(self, seg: Segment) -> None:
        if self.state == ReleaseState.DISCONNECT_PENDING:
            self._record("recv ACK -> release connection")
            self.state = ReleaseState.RELEASED
            self.timer_running = False

    def handle_data(self, seg: Segment) -> None:
        if self.state == ReleaseState.RELEASED:
            self._record(f"recv DATA after release -> DISCARD (data lost)")
            return
        self.delivered.append(seg.payload)
        self.idle_ticks = 0
        self._record(f"recv DATA ({len(seg.payload)}B) -> deliver to app")

    def tick(self, ch: Channel, is_initiator: bool = False) -> None:
        self.idle_ticks += 1
        if self.timer_running:
            self.timer += 1
            if self.timer >= 3:
                if self.state == ReleaseState.DISCONNECT_PENDING:
                    if is_initiator and self.retransmit_count < self.max_retransmits:
                        self.retransmit_count += 1
                        self._record(f"timer expired -> retransmit DR "
                                     f"(attempt {self.retransmit_count})")
                        ch.send(Segment("DR"))
                        self.timer = 0
                    else:
                        self._record(f"timer expired -> release connection")
                        self.state = ReleaseState.RELEASED
                        self.timer_running = False
        if self.inactivity_timeout and self.idle_ticks >= self.inactivity_timeout:
            if self.state == ReleaseState.ESTABLISHED:
                self._record("inactivity timeout -> release (half-open detection)")
                self.state = ReleaseState.RELEASED


def pump(a: Host, b: Host, ch_ab: Channel, ch_ba: Channel) -> None:
    while ch_ab.has_pending():
        seg = ch_ab.receive()
        if seg:
            if seg.kind == "DR":
                b.handle_dr(seg, ch_ba)
            elif seg.kind == "ACK":
                b.handle_ack(seg)
            elif seg.kind == "DATA":
                b.handle_data(seg)
    while ch_ba.has_pending():
        seg = ch_ba.receive()
        if seg:
            if seg.kind == "DR":
                a.handle_dr(seg, ch_ba)
            elif seg.kind == "ACK":
                a.handle_ack(seg)
            elif seg.kind == "DATA":
                a.handle_data(seg)


def run_abrupt_release_data_loss() -> None:
    print("=" * 72)
    print("Asymmetric (abrupt) release: data loss (Fig 6-12)")
    print("=" * 72)
    ch_ab = Channel()
    ch_ba = Channel()
    h1 = Host("host1")
    h2 = Host("host2")

    print("\n  Host2 sends DR while DATA is still in flight (Fig 6-12)")
    ch_ab.send(Segment("DATA", payload=b"message1"))
    ch_ab.send(Segment("DATA", payload=b"message2"))
    h2.send_dr(ch_ba)
    print("  Host2's DR releases the connection immediately (asymmetric)")
    h2.state = ReleaseState.RELEASED
    pump(h1, h2, ch_ab, ch_ba)
    print(f"\n  host1 state = {h1.state.name}")
    print(f"  host2 state = {h2.state.name}")
    print(f"  host2 delivered = {[d.decode() for d in h2.delivered]}")
    assert len(h2.delivered) == 0, "DATA should be LOST in abrupt release"
    print("\n  CONCLUSION: Abrupt release loses data. Need symmetric release.")


def run_normal_release() -> None:
    print("\n" + "=" * 72)
    print("Three-way handshake release (normal case, Fig 6-14a)")
    print("=" * 72)
    ch_ab = Channel()
    ch_ba = Channel()
    h1 = Host("host1")
    h2 = Host("host2")

    print("\n  Step 1: host1 sends DR, starts timer")
    h1.send_dr(ch_ab)
    pump(h1, h2, ch_ab, ch_ba)

    print("\n  Step 2: host2 gets DR, sends DR back, starts timer")
    pump(h1, h2, ch_ab, ch_ba)

    print("\n  Step 3: host1 gets DR, sends ACK, releases")
    ch_ab.send(Segment("ACK"))
    pump(h1, h2, ch_ab, ch_ba)

    print("\n  Step 4: host2 gets ACK, releases")
    pump(h1, h2, ch_ab, ch_ba)

    print(f"\n  host1 state = {h1.state.name}")
    print(f"  host2 state = {h2.state.name}")
    assert h1.state == ReleaseState.RELEASED
    assert h2.state == ReleaseState.RELEASED
    print("  Both sides released cleanly.")


def run_final_ack_lost() -> None:
    print("\n" + "=" * 72)
    print("Final ACK lost (Fig 6-14b): timer saves the day")
    print("=" * 72)
    ch_ab = Channel()
    ch_ba = Channel()
    h1 = Host("host1")
    h2 = Host("host2")

    print("\n  host1 sends DR, host2 sends DR back, host1 sends ACK (LOST)")
    h1.send_dr(ch_ab)
    pump(h1, h2, ch_ab, ch_ba)
    pump(h1, h2, ch_ab, ch_ba)

    ch_ab.drop_next = True
    ch_ab.send(Segment("ACK"))
    pump(h1, h2, ch_ab, ch_ba)
    print(f"\n  host1 state = {h1.state.name} (released after sending ACK)")

    print("\n  host2 timer expires -> releases anyway")
    for _ in range(5):
        h2.tick(ch_ba, is_initiator=h2.is_initiator)
    print(f"  host2 state = {h2.state.name}")
    assert h2.state == ReleaseState.RELEASED


def run_response_lost() -> None:
    print("\n" + "=" * 72)
    print("Response DR lost (Fig 6-14c): initiator retransmits")
    print("=" * 72)
    ch_ab = Channel()
    ch_ba = Channel()
    h1 = Host("host1")
    h2 = Host("host2")

    print("\n  host1 sends DR, host2 sends DR back (LOST)")
    h1.send_dr(ch_ab)
    pump(h1, h2, ch_ab, ch_ba)
    ch_ba.drop_next = True
    pump(h1, h2, ch_ab, ch_ba)

    print("\n  host1 timer expires -> retransmit DR")
    for _ in range(4):
        h1.tick(ch_ab, is_initiator=h1.is_initiator)
    pump(h1, h2, ch_ab, ch_ba)
    print("\n  host2 gets second DR, sends DR back")
    pump(h1, h2, ch_ab, ch_ba)
    print("\n  host1 sends ACK, releases")
    ch_ab.send(Segment("ACK"))
    pump(h1, h2, ch_ab, ch_ba)
    pump(h1, h2, ch_ab, ch_ba)
    print(f"\n  host1 state = {h1.state.name}")
    print(f"  host2 state = {h2.state.name}")


def run_all_drs_lost() -> None:
    print("\n" + "=" * 72)
    print("All DRs lost (Fig 6-14d): both sides time out independently")
    print("=" * 72)
    ch_ab = Channel()
    ch_ba = Channel()
    h1 = Host("host1", max_retransmits=2)
    h2 = Host("host2", max_retransmits=2)

    print("\n  host1 sends DR, but ALL subsequent DRs are lost")
    h1.send_dr(ch_ab)
    ch_ab.drop_next = True
    pump(h1, h2, ch_ab, ch_ba)

    for i in range(15):
        h1.tick(ch_ab, is_initiator=h1.is_initiator)
        h2.tick(ch_ba, is_initiator=h2.is_initiator)
        pump(h1, h2, ch_ab, ch_ba)
        if h1.state == ReleaseState.RELEASED and h2.state == ReleaseState.RELEASED:
            break

    print(f"\n  host1 state = {h1.state.name} (gave up after retransmits)")
    print(f"  host2 state = {h2.state.name} (timer expired)")
    print("\n  This can leave a HALF-OPEN connection if one side gives up")
    print("  while the other knows nothing. Fixed by inactivity timer.")


def run_half_open_detection() -> None:
    print("\n" + "=" * 72)
    print("Half-open connection detection via inactivity timer")
    print("=" * 72)
    ch_ab = Channel()
    ch_ba = Channel()
    h1 = Host("host1", inactivity_timeout=3)
    h2 = Host("host2", inactivity_timeout=3)

    print("\n  Connection established but one side stops sending entirely")
    for i in range(6):
        h1.tick(ch_ab, is_initiator=h1.is_initiator)
        h2.tick(ch_ba, is_initiator=h2.is_initiator)
        if h1.state == ReleaseState.RELEASED or h2.state == ReleaseState.RELEASED:
            break

    print(f"\n  host1 state = {h1.state.name}")
    print(f"  host2 state = {h2.state.name}")
    print("  Inactivity timer detects the dead connection and releases.")


def run_two_army_proof() -> None:
    print("\n" + "=" * 72)
    print("Two-Army Problem: graceful release is theoretically impossible")
    print("=" * 72)
    print("""
  Theorem: No protocol over an unreliable channel can guarantee that
  both parties agree to release simultaneously.

  Proof sketch:
    1. Assume a correct protocol exists. Remove all non-essential messages.
    2. Now every message is essential. Consider the LAST message.
    3. If the last message is lost, the sender doesn't know it arrived.
    4. The sender won't release because it can't be sure the other will.
    5. The receiver knows the sender can't be sure, so it won't release.
    6. Contradiction: the protocol doesn't work.

  Practical consequence:
    Real protocols (TCP) use timers and give up after N retransmissions.
    This is NOT theoretically safe but works well in practice.
    Each side independently decides when it's done -- the transport user
    makes the call, not the transport entity.
""")


def run_symmetric_release_demo() -> None:
    print("=" * 72)
    print("Symmetric release: each direction closed independently")
    print("=" * 72)
    ch_ab = Channel()
    ch_ba = Channel()
    h1 = Host("host1")
    h2 = Host("host2")

    print("\n  host1: 'I have no more data to send' (close my send direction)")
    h1.send_dr(ch_ab)
    pump(h1, h2, ch_ab, ch_ba)

    print("  host2 can still RECEIVE but acknowledges host1's close")
    print("  host2: 'I also have no more data' (close my send direction)")
    h2.send_dr(ch_ba)
    pump(h1, h2, ch_ab, ch_ba)
    pump(h1, h2, ch_ab, ch_ba)

    ch_ab.send(Segment("ACK"))
    pump(h1, h2, ch_ab, ch_ba)
    pump(h1, h2, ch_ab, ch_ba)
    print(f"\n  host1 state = {h1.state.name}")
    print(f"  host2 state = {h2.state.name}")


def main() -> None:
    print("Connection Release (Tanenbaum 6.2.3)")
    print()
    print("Two styles of release:")
    print("  Asymmetric: one side hangs up -> connection broken (may lose data)")
    print("  Symmetric:  each direction closed separately (like TCP FIN)")
    print()

    run_abrupt_release_data_loss()
    run_normal_release()
    run_final_ack_lost()
    run_response_lost()
    run_all_drs_lost()
    run_half_open_detection()
    run_two_army_proof()
    run_symmetric_release_demo()

    print("=" * 72)
    print("Summary:")
    print("  - Abrupt release loses data (Fig 6-12)")
    print("  - Three-way handshake release works in normal cases (Fig 6-14a)")
    print("  - Timer handles lost ACK (6-14b) and lost DR (6-14c)")
    print("  - All messages lost -> half-open connections (6-14d)")
    print("  - Two-army problem: perfect agreement is impossible")
    print("  - Practice: transport USER decides when to disconnect, not entity")
    print("=" * 72)


if __name__ == "__main__":
    main()