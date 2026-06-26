"""Stop-and-wait ARQ simulator with timers, 1-bit sequence numbers, and retransmission.

Models the data-link-layer reliability mechanism from the textbook's error-control
section: a sender transmits a frame, arms a retransmission timer, waits for an ACK.
On timer expiry it retransmits. A 1-bit sequence number lets the receiver
distinguish a fresh frame from a stale retransmission, so each payload is handed
to the network layer exactly once even when ACKs are lost.

Stdlib only. Run with:  python3 main.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum


class FrameKind(Enum):
    DATA = "DATA"
    ACK = "ACK"


@dataclass
class Frame:
    """A link-layer frame carrying a 1-bit sequence number."""

    kind: FrameKind
    seq: int  # 0 or 1 for DATA; ack number for ACK
    payload: str = ""

    def __repr__(self) -> str:
        if self.kind is FrameKind.DATA:
            return f"DATA(seq={self.seq}, payload={self.payload!r})"
        return f"ACK(ack={self.seq})"


def is_intact(frame: Frame) -> bool:
    """Trivial 'CRC' check: corruption appends a sentinel byte to the payload."""
    return "�" not in frame.payload


@dataclass
class Channel:
    """A lossy, noisy one-way channel.

    Corruption mangles the payload (appending a sentinel the receiver's CRC
    rejects) but leaves the sequence number intact — the receiver drops it via
    its error check rather than mistaking a bit-flipped seq for a valid frame.
    """

    loss_prob: float = 0.0
    corrupt_prob: float = 0.0
    rng: random.Random = field(default_factory=random.Random)

    def deliver(self, frame: Frame) -> Frame | None:
        r = self.rng.random()
        if r < self.loss_prob:
            return None  # frame vanishes entirely
        if r < self.loss_prob + self.corrupt_prob:
            return Frame(frame.kind, frame.seq, frame.payload + "�")  # corrupted payload
        return frame


@dataclass
class Sender:
    """Stop-and-wait sender. State: the bit it is allowed to send next."""

    seq: int = 0
    frame_in_flight: Frame | None = None
    timer_remaining: int = 0
    retransmissions: int = 0
    delivered: list[str] = field(default_factory=list)

    def send(self, payload: str, timeout_ticks: int) -> Frame:
        self.frame_in_flight = Frame(FrameKind.DATA, self.seq, payload)
        self.timer_remaining = timeout_ticks
        return self.frame_in_flight

    def on_ack(self, ack: Frame) -> bool:
        # Accept ACK only if it acknowledges the in-flight frame.
        if self.frame_in_flight is not None and ack.seq == self.frame_in_flight.seq:
            self.delivered.append(self.frame_in_flight.payload)
            self.frame_in_flight = None
            self.seq ^= 1  # flip to next sequence number
            self.timer_remaining = 0
            return True
        return False  # duplicate/stale ACK, ignore

    def tick(self) -> bool:
        """Advance one tick. Returns True iff the timer just expired."""
        if self.frame_in_flight is None:
            return False
        self.timer_remaining -= 1
        if self.timer_remaining == 0:
            self.retransmissions += 1
            return True
        return False

    def resend(self, timeout_ticks: int) -> Frame:
        assert self.frame_in_flight is not None
        self.timer_remaining = timeout_ticks
        return self.frame_in_flight


@dataclass
class Receiver:
    """Stop-and-wait receiver. State: the bit it expects next."""

    expected: int = 0
    delivered: list[str] = field(default_factory=list)

    def on_data(self, frame: Frame) -> Frame | None:
        # Corrupted frame: drop silently. No ACK is sent, so the sender's timer
        # fires and retransmits — the textbook's "receiver has no reason to
        # react" case, recovered by the timer.
        if not is_intact(frame):
            return None
        if frame.seq == self.expected:
            self.delivered.append(frame.payload)
            self.expected ^= 1
            return Frame(FrameKind.ACK, frame.seq)  # ack the just-accepted frame
        # Duplicate of an already-accepted frame: re-ack with frame.seq itself
        # (the LAST accepted seq). ACK(n) means "I have accepted seq=n"; re-acking
        # with the flipped bit would deadlock the sender.
        return Frame(FrameKind.ACK, frame.seq)


def run_stop_and_wait(
    payloads: list[str],
    data_channel: Channel,
    ack_channel: Channel,
    timeout_ticks: int = 4,
    max_ticks: int = 1000,
) -> dict:
    sender = Sender()
    receiver = Receiver()
    queue: list[str] = list(payloads)
    trace: list[str] = []
    ticks = 0

    while (queue or sender.frame_in_flight is not None) and ticks < max_ticks:
        ticks += 1
        # If the sender is idle and has data, send the next frame.
        if sender.frame_in_flight is None and queue:
            f = sender.send(queue.pop(0), timeout_ticks)
            trace.append(f"t={ticks:03d} TX  {f}")
        # Advance sender timer; on expiry, retransmit.
        if sender.frame_in_flight is not None and sender.tick():
            f = sender.resend(timeout_ticks)
            trace.append(f"t={ticks:03d} *TIMER* retransmit {f}")
        # Deliver the in-flight frame across the lossy data channel.
        if sender.frame_in_flight is not None:
            arrived = data_channel.deliver(sender.frame_in_flight)
            if arrived is None:
                trace.append(f"t={ticks:03d}   data channel: frame LOST")
                continue
            ack = receiver.on_data(arrived)
            if ack is None:
                trace.append(f"t={ticks:03d}   RX  {arrived} -> CORRUPT, dropped (no ACK)")
                continue
            trace.append(f"t={ticks:03d}   RX  {arrived} -> emits {ack}")
            ack_arrived = ack_channel.deliver(ack)
            if ack_arrived is None:
                trace.append(f"t={ticks:03d}   ack channel: ACK LOST")
                continue
            accepted = sender.on_ack(ack_arrived)
            trace.append(
                f"t={ticks:03d}   sender got {ack_arrived} "
                f"({'accepted' if accepted else 'ignored'})"
            )

    return {
        "sent": len(payloads),
        "delivered": len(receiver.delivered),
        "retransmissions": sender.retransmissions,
        "ticks": ticks,
        "receiver_payloads": receiver.delivered,
        "trace": trace,
    }


def main() -> None:
    print("=" * 68)
    print("Stop-and-Wait ARQ: timers, 1-bit sequence numbers, retransmission")
    print("=" * 68)

    payloads = ["GET /", "HTTP/1.1", "200 OK", "<html>", "</html>"]
    data_ch = Channel(loss_prob=0.3, corrupt_prob=0.1, rng=random.Random(7))
    ack_ch = Channel(loss_prob=0.3, corrupt_prob=0.0, rng=random.Random(107))
    result = run_stop_and_wait(payloads, data_ch, ack_ch, timeout_ticks=3)

    print("\n--- Trace (first 40 events) ---")
    for line in result["trace"][:40]:
        print(line)

    print("\n--- Summary ---")
    print(f"payloads sent:         {result['sent']}")
    print(f"payloads delivered:    {result['delivered']}")
    print(f"retransmissions:       {result['retransmissions']}")
    print(f"ticks elapsed:         {result['ticks']}")
    print(f"receiver delivery order: {result['receiver_payloads']}")
    print(f"\nDelivered exactly once, in order: {result['receiver_payloads'] == payloads}")

    # Show why a 1-bit window is the minimum: demonstrate duplicate suppression.
    print("\n--- Duplicate-suppression check ---")
    rx = Receiver()
    first = rx.on_data(Frame(FrameKind.DATA, 0, "A"))  # accept
    dup = rx.on_data(Frame(FrameKind.DATA, 0, "A"))  # retransmission -> re-ack, no deliver
    print(f"first  DATA(seq=0): emit {first}, receiver has {rx.delivered}")
    print(f"dup    DATA(seq=0): emit {dup}, receiver still has {rx.delivered} (no duplicate)")


if __name__ == "__main__":
    main()
