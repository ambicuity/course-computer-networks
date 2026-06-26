#!/usr/bin/env python3
"""Transport-layer error control and flow control (Tanenbaum 6.2.4).

Implements:
1. A transport-layer sliding window protocol with credit-based (dynamic)
   flow control, as described in Fig 6-16. The receiver piggybacks both
   acknowledgements and buffer allocations (credits) on reverse traffic.
2. Checksum validation for end-to-end error detection (the end-to-end
   argument of Saltzer et al. 1984).
3. The sequence number space requirement: sender_window + receiver_window
   <= sequence_space (w + w <= s), with a demonstration of what happens
   when this is violated (ambiguity between old and new segments).
4. A trace reproducing the dynamic buffer allocation scenario of Fig 6-16.

Run:  python3 main.py
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


def checksum16(data: bytes) -> int:
    total = 0
    for i in range(0, len(data) - 1, 2):
        total += (data[i] << 8) + data[i + 1]
    if len(data) % 2:
        total += data[-1] << 8
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return ~total & 0xFFFF


@dataclass
class Segment:
    seq: int
    ack: int
    credit: int
    payload: bytes
    checksum: int

    def is_valid(self) -> bool:
        return self.checksum == checksum16(self.payload)


class UnreliableNet:
    def __init__(self, corrupt_seq: Optional[int] = None,
                 lose_seq: Optional[int] = None) -> None:
        self._queue: list[Segment] = []
        self.corrupt_seq = corrupt_seq
        self.lose_seq = lose_seq
        self._sent_count = 0

    def send(self, seg: Segment) -> None:
        self._sent_count += 1
        if self.lose_seq is not None and seg.seq == self.lose_seq:
            return
        if self.corrupt_seq is not None and seg.seq == self.corrupt_seq:
            corrupted = b"\x00" + seg.payload[1:] if len(seg.payload) > 1 else b"\x00"
            bad = Segment(seg.seq, seg.ack, seg.credit,
                          corrupted, seg.checksum)
            self._queue.append(bad)
            return
        self._queue.append(seg)

    def receive(self) -> Optional[Segment]:
        if self._queue:
            return self._queue.pop(0)
        return None


@dataclass
class CreditSender:
    max_seq: int
    window: int = 0
    next_seq: int = 0
    ack_expected: int = 0
    buffer: dict[int, bytes] = field(default_factory=dict)
    in_flight: int = 0
    delivered_log: list[str] = field(default_factory=list)

    def can_send(self) -> bool:
        return self.in_flight < self.window

    def send_data(self, net: UnreliableNet, data: bytes) -> None:
        if not self.can_send():
            raise RuntimeError("No credit: window exhausted")
        seq = self.next_seq
        self.buffer[seq] = data
        seg = Segment(seq, self.ack_expected, 0, data, checksum16(data))
        net.send(seg)
        self.next_seq = (seq + 1) % (self.max_seq + 1)
        self.in_flight += 1
        self.delivered_log.append(f"TX seq={seq} credit_used={self.in_flight}/{self.window}")

    def process_ack(self, ack: int, credit: int) -> None:
        while self.ack_expected != ack:
            if self.ack_expected in self.buffer:
                del self.buffer[self.ack_expected]
            self.ack_expected = (self.ack_expected + 1) % (self.max_seq + 1)
            self.in_flight = max(0, self.in_flight - 1)
        self.window = credit


@dataclass
class CreditReceiver:
    max_seq: int
    expected: int = 0
    delivered: list[bytes] = field(default_factory=list)
    buffers_available: int = 4
    corrupt_count: int = 0

    def process_data(self, seg: Segment) -> tuple[int, int]:
        if not seg.is_valid():
            self.corrupt_count += 1
            return (self.expected, self.buffers_available)
        if seg.seq == self.expected:
            self.delivered.append(seg.payload)
            self.expected = (self.expected + 1) % (self.max_seq + 1)
            self.buffers_available = max(0, self.buffers_available - 1)
        return (self.expected, self.buffers_available)

    def app_reads(self, n: int) -> None:
        for _ in range(n):
            if self.delivered:
                self.delivered.pop(0)
                self.buffers_available += 1


def run_credit_flow_control() -> None:
    print("=" * 72)
    print("Credit-based flow control (dynamic buffer allocation, Fig 6-16)")
    print("=" * 72)
    max_seq = 15
    net = UnreliableNet()
    sender = CreditSender(max_seq=max_seq, window=4)
    receiver = CreditReceiver(max_seq=max_seq, buffers_available=4)

    print(f"\n  Initial: sender window={sender.window}, "
          f"receiver buffers={receiver.buffers_available}")

    print("\n  --- Phase 1: sender sends 4 segments (window full) ---")
    for i in range(4):
        data = f"msg{i}".encode()
        sender.send_data(net, data)
        print(f"  {sender.delivered_log[-1]}")

    print("\n  --- Phase 2: receiver processes, sends ACK + credit ---")
    for _ in range(4):
        seg = net.receive()
        if seg:
            ack, credit = receiver.process_data(seg)
            print(f"  RX seq={seg.seq} -> ack={ack}, credit={credit}")
            sender.process_ack(ack, credit)

    print(f"\n  Sender: ack_expected={sender.ack_expected}, "
          f"window={sender.window}, in_flight={sender.in_flight}")
    print(f"  Receiver: expected={receiver.expected}, "
          f"buffers={receiver.buffers_available}")
    print(f"  Receiver delivered: {[d.decode() for d in receiver.delivered]}")

    print("\n  --- Phase 3: receiver app reads 2, frees buffers ---")
    receiver.app_reads(2)
    print(f"  Receiver buffers now: {receiver.buffers_available}")
    ack, credit = (receiver.expected, receiver.buffers_available)
    sender.process_ack(ack, credit)
    print(f"  Sender gets new credit: window={sender.window}")

    print("\n  --- Phase 4: sender sends 2 more with new credit ---")
    for i in range(4, 6):
        data = f"msg{i}".encode()
        sender.send_data(net, data)
        print(f"  {sender.delivered_log[-1]}")
    for _ in range(2):
        seg = net.receive()
        if seg:
            ack, credit = receiver.process_data(seg)
            sender.process_ack(ack, credit)
    print(f"\n  Receiver delivered: {[d.decode() for d in receiver.delivered]}")


def run_checksum_validation() -> None:
    print("\n" + "=" * 72)
    print("End-to-end checksum validation (Saltzer et al. end-to-end argument)")
    print("=" * 72)
    net = UnreliableNet(corrupt_seq=2)
    max_seq = 15
    sender = CreditSender(max_seq=max_seq, window=8)
    receiver = CreditReceiver(max_seq=max_seq, buffers_available=8)

    print("\n  Sending 5 segments, segment seq=2 will be corrupted in transit")
    for i in range(5):
        sender.send_data(net, f"data{i}".encode())

    for _ in range(5):
        seg = net.receive()
        if seg:
            if not seg.is_valid():
                print(f"  RX seq={seg.seq} -> CHECKSUM FAIL -> discard")
                receiver.corrupt_count += 1
            else:
                ack, credit = receiver.process_data(seg)
                print(f"  RX seq={seg.seq} -> OK, ack={ack}")
                sender.process_ack(ack, credit)

    print(f"\n  Receiver delivered: {[d.decode() for d in receiver.delivered]}")
    print(f"  Corrupt segments discarded: {receiver.corrupt_count}")
    assert receiver.corrupt_count == 1, "Expected 1 corrupt segment"
    assert len(receiver.delivered) == 2, "Expected 2 valid (seq 0,1) before corrupt gap"
    print("  Checksum caught the corruption. End-to-end check is essential.")
    print("  Note: seq 3,4 discarded as out-of-order (expected=2 after gap).")


def run_sequence_space_requirement() -> None:
    print("\n" + "=" * 72)
    print("Sequence number space requirement: w_sender + w_receiver <= S")
    print("=" * 72)

    print("""
  For a sliding window protocol with sender window Ws and receiver window Wr:
    Ws + Wr <= 2^k  (where k = sequence number bits)

  If Ws + Wr > 2^k, old and new segments can share the same sequence number,
  making it impossible to distinguish a delayed duplicate from a new segment.
""")

    cases = [
        (1, 1, 2, 1, "Stop-and-wait: 1-bit seq is enough"),
        (4, 1, 8, 3, "Go-Back-N: receiver window=1, 3-bit seq OK"),
        (4, 4, 8, 3, "Selective Repeat: 4+4=8=2^3, exactly fits"),
        (5, 4, 8, 3, "Selective Repeat: 5+4=9 > 8 -> AMBIGUITY!"),
        (7, 7, 16, 4, "Selective Repeat: 7+7=14 < 16, safe"),
    ]

    print(f"  {'Ws':>4s}  {'Wr':>4s}  {'2^k':>6s}  {'k':>3s}  {'Status':}")
    print(f"  {'----':>4s}  {'----':>4s}  {'----':>6s}  {'---':>3s}  {'------':}")
    for ws, wr, space, k, note in cases:
        total = ws + wr
        if total <= space:
            status = f"OK ({note})"
        else:
            status = f"FAIL: {total} > {space} -- {note}"
        print(f"  {ws:>4d}  {wr:>4d}  {space:>6d}  {k:>3d}  {status}")

    print(f"""
  Demonstration of ambiguity when Ws+Wr > S:
    Suppose k=3 (S=8), Ws=5, Wr=4. Total=9 > 8.
    Sender sends seq 0..4 (window 5). Receiver accepts 0..3 (window 4).
    Receiver advances to expect 4, and could accept 4..7.
    But seq 0 could be a RETRANSMISSION of old seq 0, or a NEW seq 0
    (wrapped around). The receiver cannot tell. -> DATA CORRUPTION.
""")


def run_dynamic_window_deadlock() -> None:
    print("=" * 72)
    print("Dynamic buffer allocation deadlock (Fig 6-16, line 16)")
    print("=" * 72)
    print("""
  Problem: If control segments (ACK + credit) can be lost, the sender
  can deadlock when the receiver allocates more buffers but the credit
  message is lost. The sender thinks it has 0 credit and stops; the
  receiver thinks it granted credit and waits for data.

  Solution: Periodically send control segments with current ACK and
  buffer status. This breaks the deadlock eventually.

  This is why TCP uses persistent timers and window updates.
""")
    max_seq = 15
    net = UnreliableNet(lose_seq=99)
    sender = CreditSender(max_seq=max_seq, window=4)
    receiver = CreditReceiver(max_seq=max_seq, buffers_available=4)

    print("  Simulating: sender fills window, receiver acks with credit=0")
    for i in range(4):
        sender.send_data(net, f"m{i}".encode())
    for _ in range(4):
        seg = net.receive()
        if seg:
            ack, credit = receiver.process_data(seg)
    sender.process_ack(receiver.expected, 0)
    print(f"  Sender window = {sender.window} (blocked, 0 credit)")
    print(f"  Receiver buffers = {receiver.buffers_available}")

    print("\n  Receiver app reads all data, frees buffers, sends credit=4")
    receiver.app_reads(4)
    print(f"  Receiver buffers now = {receiver.buffers_available}")

    print("  BUT the credit update is LOST on the network...")
    print("  Sender is still blocked with window=0. DEADLOCK!")
    print(f"  Sender window = {sender.window}")

    print("\n  Fix: periodic control segment retransmits the credit")
    sender.process_ack(receiver.expected, receiver.buffers_available)
    print(f"  After periodic update: sender window = {sender.window}")
    print("  Deadlock broken. Sender can continue.")


def main() -> None:
    print("Error Control and Flow Control (Tanenbaum 6.2.4)")
    print()
    print("Mechanisms:")
    print("  1. Checksum -- end-to-end error detection")
    print("  2. Sequence numbers -- identify and discard duplicates")
    print("  3. ARQ -- retransmit until ACKed")
    print("  4. Sliding window -- pipeline multiple segments")
    print("  5. Credit-based flow control -- dynamic buffer allocation")
    print()

    run_credit_flow_control()
    run_checksum_validation()
    run_sequence_space_requirement()
    run_dynamic_window_deadlock()

    print("\n" + "=" * 72)
    print("Key insights:")
    print("  - Transport checksum is END-TO-END (unlike link-layer CRC)")
    print("  - Credit-based flow control decouples ACK from buffer allocation")
    print("  - Sequence space must satisfy Ws + Wr <= 2^k")
    print("  - Lost credit updates can deadlock; periodic refresh fixes this")
    print("=" * 72)


if __name__ == "__main__":
    main()