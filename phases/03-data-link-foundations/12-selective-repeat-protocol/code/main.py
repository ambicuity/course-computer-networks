"""Selective Repeat ARQ (Protocol 6) simulator.

A stdlib-only, runnable model of Tanenbaum's Protocol 6 over a lossy channel.
Implements:
  * Sender with a sliding window capped at NR_BUFS = (MAX_SEQ + 1) / 2.
  * Receiver with a fixed window, per-slot in_buf[] pool and arrived[] bit map.
  * Per-frame independent timers via a heap-ordered virtual clock.
  * NAK generation gated by a no_nak flag (one NAK per lost frame).
  * A separate ack timer so acks fire even with no reverse data traffic.
  * The classic window-overlap hazard: drop the ack on a delivered batch and
    watch a retransmitted old frame be accepted as fresh data when W is too big.

Run:  python3 main.py
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Protocol constants and frame model
# ---------------------------------------------------------------------------

class Kind(Enum):
    DATA = "data"
    ACK = "ack"
    NAK = "nak"


@dataclass
class Frame:
    kind: Kind
    seq: int
    ack: int          # piggyback / standalone ack (cumulative)
    info: Optional[bytes] = None


# ---------------------------------------------------------------------------
# Heap-based virtual clock simulating per-frame independent timers.
# Production kernels (timerfd, BSD callouts) use the same heap shape.
# ---------------------------------------------------------------------------

class HeapTimer:
    def __init__(self) -> None:
        self._now: float = 0.0
        self._pq: list[tuple[float, int, str]] = []
        self._counter = 0  # tiebreaker for equal fire times

    def now(self) -> float:
        return self._now

    def schedule(self, delay: float, label: str) -> None:
        self._counter += 1
        heapq.heappush(self._pq, (self._now + delay, self._counter, label))

    def cancel(self, label: str) -> None:
        self._pq = [(t, c, l) for (t, c, l) in self._pq if l != label]
        heapq.heapify(self._pq)

    def advance_to_next(self) -> Optional[tuple[float, str]]:
        if not self._pq:
            return None
        t, _, label = heapq.heappop(self._pq)
        self._now = t
        return t, label


def inc(n: int, max_seq: int) -> int:
    return (n + 1) % (max_seq + 1)


def between(a: int, b: int, c: int, max_seq: int) -> bool:
    """Circular range test: true if a <= b < c on the mod-(max_seq+1) ring."""
    return ((a <= b) and (b < c)) or ((c < a) and (a <= b)) or ((b < c) and (c < a))


# ---------------------------------------------------------------------------
# Lossy channel: FIFO queue of in-flight frames.
#   * data_drop: DATA frames lost on FIRST transmission only (retransmits pass).
#   * ack_drop:  drop the first N standalone ACK frames (forces sender timeout,
#                used to demonstrate the window-overlap hazard).
# ---------------------------------------------------------------------------

class LossyChannel:
    def __init__(self, data_drop: set[int], ack_drop: int,
                 use_naks: bool) -> None:
        self.data_drop = data_drop
        self._dropped_seen: set[int] = set()
        self.ack_drop = ack_drop
        self.use_naks = use_naks
        self.in_flight: list[Frame] = []

    def send(self, frame: Frame) -> None:
        self.in_flight.append(frame)

    def deliver(self) -> Optional[tuple[Frame, bool]]:
        """Pop the head of the in-flight queue; apply loss/garble."""
        if not self.in_flight:
            return None
        frame = self.in_flight.pop(0)
        if frame.kind == Kind.DATA:
            if frame.seq in self.data_drop and frame.seq not in self._dropped_seen:
                self._dropped_seen.add(frame.seq)
                return None  # lost (first time only)
            return frame, True
        if frame.kind == Kind.ACK and self.ack_drop > 0:
            self.ack_drop -= 1
            return None  # ack lost in flight
        return frame, True


# ---------------------------------------------------------------------------
# Receiver (Protocol 6 receive side)
# ---------------------------------------------------------------------------

class Receiver:
    def __init__(self, max_seq: int, w: int, timer: HeapTimer,
                 channel: LossyChannel) -> None:
        self.max_seq = max_seq
        self.w = w
        self.timer = timer
        self.channel = channel
        self.frame_expected = 0
        self.too_far = w % (max_seq + 1)
        self.in_buf: list[Optional[bytes]] = [None] * w
        self.arrived: list[bool] = [False] * w
        self.no_nak = True
        self.delivered: list[int] = []  # seq numbers handed to network layer
        self.ack_timeout_scheduled = False

    def _send(self, kind: Kind, ack: int) -> None:
        self.channel.send(Frame(kind, 0, ack))

    def on_data(self, frame: Frame, ok: bool) -> None:
        if not ok:
            # cksum_err: emit one NAK for the expected frame.
            if self.no_nak and self.channel.use_naks:
                self._send(Kind.NAK, (self.frame_expected + self.max_seq)
                           % (self.max_seq + 1))
            return
        if frame.seq != self.frame_expected and self.no_nak \
                and self.channel.use_naks:
            # Out of order -> gap detected -> NAK the missing frame.
            self._send(Kind.NAK, (self.frame_expected + self.max_seq)
                       % (self.max_seq + 1))
            self.no_nak = False
        else:
            self._schedule_ack_timer()
        if (between(self.frame_expected, frame.seq, self.too_far, self.max_seq)
                and not self.arrived[frame.seq % self.w]):
            self.arrived[frame.seq % self.w] = True
            self.in_buf[frame.seq % self.w] = frame.info
            # Drain contiguous in-order frames to the network layer.
            while self.arrived[self.frame_expected % self.w]:
                self.delivered.append(self.frame_expected)
                self.no_nak = True
                self.arrived[self.frame_expected % self.w] = False
                self.in_buf[self.frame_expected % self.w] = None
                self.frame_expected = inc(self.frame_expected, self.max_seq)
                self.too_far = inc(self.too_far, self.max_seq)
                self._schedule_ack_timer()

    def fire_ack_timeout(self) -> None:
        self.ack_timeout_scheduled = False
        self._send(Kind.ACK, (self.frame_expected + self.max_seq)
                   % (self.max_seq + 1))

    def _schedule_ack_timer(self) -> None:
        if not self.ack_timeout_scheduled:
            self.timer.schedule(5.0, "ack_timeout")
            self.ack_timeout_scheduled = True


# ---------------------------------------------------------------------------
# Sender (Protocol 6 send side)
# ---------------------------------------------------------------------------

class Sender:
    def __init__(self, max_seq: int, w: int, timer: HeapTimer,
                 channel: LossyChannel, receiver: Receiver) -> None:
        self.max_seq = max_seq
        self.w = w
        self.timer = timer
        self.channel = channel
        self.receiver = receiver
        self.ack_expected = 0
        self.next_frame_to_send = 0
        self.nbuffered = 0
        self.out_buf: list[Optional[bytes]] = [None] * w
        self.retx: dict[int, int] = {}  # seq -> retransmission count
        self.packets_to_send: list[bytes] = []

    def load(self, packets: list[bytes]) -> None:
        self.packets_to_send = list(packets)

    def _send_data(self, seq: int) -> None:
        ack = (self.receiver.frame_expected + self.max_seq) % (self.max_seq + 1)
        self.channel.send(Frame(Kind.DATA, seq, ack, self.out_buf[seq % self.w]))
        self.timer.schedule(10.0, f"timeout:{seq}")

    def send_new(self) -> None:
        while self.nbuffered < self.w and self.packets_to_send:
            seq = self.next_frame_to_send
            self.out_buf[seq % self.w] = self.packets_to_send.pop(0)
            self.nbuffered += 1
            self._send_data(seq)
            self.next_frame_to_send = inc(self.next_frame_to_send, self.max_seq)

    def on_ack(self, ack: int) -> None:
        while between(self.ack_expected, ack, self.next_frame_to_send,
                      self.max_seq):
            self.timer.cancel(f"timeout:{self.ack_expected}")
            self.ack_expected = inc(self.ack_expected, self.max_seq)
            self.nbuffered -= 1

    def on_nak(self, nak: int) -> None:
        target = (nak + 1) % (self.max_seq + 1)
        if between(self.ack_expected, target, self.next_frame_to_send,
                   self.max_seq):
            self.retx[target] = self.retx.get(target, 0) + 1
            self._send_data(target)

    def on_timeout(self, seq: int) -> None:
        self.retx[seq] = self.retx.get(seq, 0) + 1
        self._send_data(seq)

    def done(self) -> bool:
        return (not self.packets_to_send) and self.nbuffered == 0


# ---------------------------------------------------------------------------
# Wire it together: deterministic event-driven simulation.
# ---------------------------------------------------------------------------

def simulate(max_seq: int = 7, w: int = 4, n_packets: int = 8,
             data_drop: Optional[set[int]] = None,
             ack_drop: int = 0,
             use_naks: bool = True) -> dict:
    if data_drop is None:
        data_drop = {1, 4}
    legal_w = (max_seq + 1) // 2
    rule_holds = w <= legal_w

    timer = HeapTimer()
    channel = LossyChannel(data_drop=data_drop, ack_drop=ack_drop,
                           use_naks=use_naks)
    receiver = Receiver(max_seq, w, timer, channel)
    sender = Sender(max_seq, w, timer, channel, receiver)

    packets = [f"pkt{i}".encode() for i in range(n_packets)]
    sender.load(packets)

    log: list[str] = []
    max_events = 2000

    sender.send_new()

    while not sender.done() and max_events > 0:
        max_events -= 1

        # Deliver any frame queued by the opposite side (FIFO).
        delivered = channel.deliver()
        if delivered is not None:
            frame, ok = delivered
            if frame.kind == Kind.DATA:
                log.append(f"DATA seq={frame.seq} {'OK' if ok else 'CKSUM'}")
                receiver.on_data(frame, ok)
            elif frame.kind == Kind.ACK:
                log.append(f"ACK {frame.ack}")
                sender.on_ack(frame.ack)
            elif frame.kind == Kind.NAK:
                log.append(f"NAK {frame.ack}")
                sender.on_nak(frame.ack)
            sender.send_new()
            continue

        # No frame waiting; advance the clock to the next timer event.
        nxt = timer.advance_to_next()
        if nxt is None:
            sender.send_new()
            continue
        _, label = nxt
        if label.startswith("timeout:"):
            seq = int(label.split(":")[1])
            log.append(f"TIMEOUT frame {seq} -> retransmit")
            sender.on_timeout(seq)
        elif label == "ack_timeout":
            log.append("ACK_TIMEOUT -> standalone ack")
            receiver.fire_ack_timeout()
        sender.send_new()

    return {
        "delivered": receiver.delivered,
        "retx": sender.retx,
        "rule_holds": rule_holds,
        "log": log,
        "dup_detected": len(receiver.delivered) != len(set(receiver.delivered)),
    }


# ---------------------------------------------------------------------------
# Bonus: parse a TCP SACK option (RFC 2018, kind 5).
# ---------------------------------------------------------------------------

def parse_sack_option(raw: bytes) -> list[tuple[int, int]]:
    """Decode kind-5 SACK option bytes into [(left_edge, right_edge), ...]."""
    if len(raw) < 2 or raw[0] != 5:
        raise ValueError("not a SACK option")
    length = raw[1]
    blocks: list[tuple[int, int]] = []
    body = raw[2:length]
    for i in range(0, len(body) - 7, 8):
        le = int.from_bytes(body[i:i + 4], "big")
        re = int.from_bytes(body[i + 4:i + 8], "big")
        blocks.append((le, re))
    return blocks


def main() -> None:
    print("=" * 70)
    print("Selective Repeat ARQ -- Protocol 6 simulation")
    print("=" * 70)

    print("\n[1] Legal window (W = (MAX_SEQ+1)/2 = 4), lose DATA frames 1,4:\n")
    res = simulate(max_seq=7, w=4, n_packets=8, data_drop={1, 4}, use_naks=True)
    for line in res["log"]:
        print("  " + line)
    print(f"\n  Delivered to network layer: {res['delivered']}")
    print(f"  Retransmissions per frame : {res['retx']}")
    print(f"  Duplicate delivered?       {res['dup_detected']}")
    print(f"  Window rule holds?         {res['rule_holds']}")

    print("\n[2] NAKs disabled -- recovery waits for per-frame timer:\n")
    res2 = simulate(max_seq=7, w=4, n_packets=8, data_drop={1, 4},
                    use_naks=False)
    for line in res2["log"]:
        print("  " + line)
    print(f"\n  Delivered: {res2['delivered']}")
    print(f"  Retx:      {res2['retx']}")
    print("  (note: NAK path absent, so frame 1 gap is only noticed once 2,3 "
          "arrive and ack timer fires)")

    print("\n[3] Window rule VIOLATED (W=5 > 4), drop the first ACK:\n")
    print("  Receiver delivers 0..4, slides window to [5,6,7,0,1]. ACK lost.")
    print("  Sender times out frame 0 and retransmits -> 0 is inside the NEW")
    print("  receiver window, so it is accepted as fresh data.\n")
    res3 = simulate(max_seq=7, w=5, n_packets=8, data_drop=set(),
                    ack_drop=1, use_naks=False)
    for line in res3["log"]:
        print("  " + line)
    print(f"\n  Delivered: {res3['delivered']}")
    print(f"  Duplicate delivered? {res3['dup_detected']}  <- should be True")
    if res3['dup_detected']:
        dups = [s for s in res3['delivered']
                if res3['delivered'].count(s) > 1]
        print(f"  Duplicated seqs: {sorted(set(dups))}  (silent data corruption)")

    print("\n[4] No losses -- all frames in order, ack timer drains acks:\n")
    res4 = simulate(max_seq=7, w=4, n_packets=8, data_drop=set(),
                    use_naks=True)
    print(f"  Delivered: {res4['delivered']}")
    print(f"  All in order & no dup: "
          f"{res4['delivered'] == sorted(set(res4['delivered']))}")

    print("\n[5] TCP SACK option decode (RFC 2018, kind 5):\n")
    # kind=5, len=18, two blocks: (2000,3000) and (5000,6000)
    sack = (bytes([5, 18])
            + (2000).to_bytes(4, "big") + (3000).to_bytes(4, "big")
            + (5000).to_bytes(4, "big") + (6000).to_bytes(4, "big"))
    print(f"  raw   : {sack.hex()}")
    print(f"  blocks: {parse_sack_option(sack)}")
    print("  -> receiver has 2000..2999 and 5000..5999; sender resends gaps.")


if __name__ == "__main__":
    main()
