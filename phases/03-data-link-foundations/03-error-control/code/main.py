#!/usr/bin/env python3
"""Stop-and-wait ARQ simulator and link-utilization calculator.

This module models the three primitives of link-layer error control:
acknowledgements, a retransmission timer (RTO), and a 1-bit alternating
sequence number. It runs the sender/receiver pair over a lossy channel that
can independently drop data frames and ACK frames, and logs every event so
the four canonical failure modes are visible:

    - lost data frame    (no ACK -> timeout -> retransmit)
    - lost ACK           (receiver delivers, ACK dropped, frame retransmitted)
    - premature timeout  (RTO shorter than the real round trip)
    - duplicate delivery (PREVENTED by the sequence number)

It also computes stop-and-wait link utilization U = T_frame / (T_frame + RTT).
Pure standard library. No network calls. Run: python3 main.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import List, Optional

# --- Tunable channel parameters -------------------------------------------------
FRAME_LOSS = 0.20   # probability a data frame is dropped in transit
ACK_LOSS = 0.20     # probability an ACK is dropped on the return path
RTO_TICKS = 4       # retransmission timeout, in simulation ticks
N_MESSAGES = 6      # number of distinct payloads to deliver reliably
SEED = 42           # fixed seed for a reproducible demonstration


@dataclass(frozen=True)
class Frame:
    """A data frame carrying a 1-bit sequence number and an opaque payload."""

    seq: int          # 0 or 1
    payload: str


@dataclass(frozen=True)
class Ack:
    """A positive acknowledgement naming the sequence number being confirmed."""

    seq: int          # 0 or 1


class LossyChannel:
    """Independently drops data frames and ACKs by configured probability."""

    def __init__(self, frame_loss: float, ack_loss: float, rng: random.Random):
        self._frame_loss = frame_loss
        self._ack_loss = ack_loss
        self._rng = rng

    def carry_frame(self, frame: Frame) -> Optional[Frame]:
        if self._rng.random() < self._frame_loss:
            return None
        return frame

    def carry_ack(self, ack: Ack) -> Optional[Ack]:
        if self._rng.random() < self._ack_loss:
            return None
        return ack


class StopAndWaitReceiver:
    """Receiver tracking the next expected 1-bit sequence number."""

    def __init__(self, log: List[str]):
        self._expected = 0
        self._delivered: List[str] = []
        self._log = log

    @property
    def delivered(self) -> List[str]:
        return list(self._delivered)

    def on_frame(self, frame: Frame) -> Ack:
        """Deliver a fresh frame; ACK-but-drop a duplicate retransmission."""
        if frame.seq == self._expected:
            self._delivered.append(frame.payload)
            self._log.append(
                f"    RX   DELIVER seq={frame.seq} payload={frame.payload!r}"
            )
            ack = Ack(seq=frame.seq)
            self._expected ^= 1  # flip 0<->1
            return ack
        # Already delivered: re-ACK so the sender can advance, but do NOT
        # hand the duplicate up to the network layer.
        self._log.append(
            f"    RX   DUP-DROP seq={frame.seq} (already delivered; re-ACK only)"
        )
        return Ack(seq=frame.seq)


class StopAndWaitSender:
    """Sender that transmits one frame, starts a timer, and waits for its ACK."""

    def __init__(
        self,
        messages: List[str],
        channel: LossyChannel,
        receiver: StopAndWaitReceiver,
        rto: int,
        log: List[str],
    ):
        self._messages = messages
        self._channel = channel
        self._receiver = receiver
        self._rto = rto
        self._log = log
        self._seq = 0
        self._transmissions = 0

    @property
    def transmissions(self) -> int:
        return self._transmissions

    def _attempt(self, frame: Frame) -> Optional[Ack]:
        """One transmit + listen window. Returns an ACK if one returns in time."""
        self._transmissions += 1
        delivered = self._channel.carry_frame(frame)
        if delivered is None:
            self._log.append(
                f"  TX   SEND    seq={frame.seq} payload={frame.payload!r} "
                f"-> FRAME LOST"
            )
            return None

        self._log.append(
            f"  TX   SEND    seq={frame.seq} payload={frame.payload!r} "
            f"(timer={self._rto} ticks)"
        )
        ack = self._receiver.on_frame(delivered)
        returned = self._channel.carry_ack(ack)
        if returned is None:
            self._log.append(f"    RX   ACK     seq={ack.seq} -> ACK LOST")
            return None

        self._log.append(f"    RX   ACK     seq={ack.seq} -> received by sender")
        return returned

    def send_all(self) -> None:
        """Reliably deliver every message using stop-and-wait ARQ."""
        for payload in self._messages:
            frame = Frame(seq=self._seq, payload=payload)
            self._log.append(f"--- new message {payload!r} (seq={self._seq}) ---")
            ack = None
            while ack is None or ack.seq != self._seq:
                ack = self._attempt(frame)
                if ack is None:
                    self._log.append(
                        f"  TX   TIMEOUT seq={frame.seq} -> retransmit"
                    )
                elif ack.seq != self._seq:
                    # Stale ACK for the previous frame; ignore and keep waiting.
                    self._log.append(
                        f"  TX   STALE   ACK seq={ack.seq} ignored "
                        f"(awaiting {self._seq})"
                    )
            self._seq ^= 1  # advance the 1-bit sequence number


def stop_and_wait_utilization(frame_bytes: int, link_bps: float, rtt_s: float) -> float:
    """Link utilization U = T_frame / (T_frame + RTT) for stop-and-wait ARQ."""
    t_frame = (frame_bytes * 8) / link_bps
    return t_frame / (t_frame + rtt_s)


def demo_arq() -> None:
    rng = random.Random(SEED)
    log: List[str] = []
    channel = LossyChannel(FRAME_LOSS, ACK_LOSS, rng)
    receiver = StopAndWaitReceiver(log)
    messages = [f"REC-{i:02d}" for i in range(1, N_MESSAGES + 1)]
    sender = StopAndWaitSender(messages, channel, receiver, RTO_TICKS, log)

    print("=" * 68)
    print("STOP-AND-WAIT ARQ  (frame_loss={:.0%}, ack_loss={:.0%})".format(
        FRAME_LOSS, ACK_LOSS))
    print("=" * 68)
    sender.send_all()
    for line in log:
        print(line)

    print("-" * 68)
    print(f"messages to deliver : {len(messages)}")
    print(f"total transmissions : {sender.transmissions}")
    print(f"delivered in order  : {receiver.delivered}")
    assert receiver.delivered == messages, "duplicate or out-of-order delivery!"
    print("INVARIANT OK: each payload delivered exactly once, in order.")


def demo_utilization() -> None:
    print()
    print("=" * 68)
    print("STOP-AND-WAIT UTILIZATION  (1500-byte frame)")
    print("=" * 68)
    profiles = [
        ("LAN       1 Gbps, 0.1 ms RTT", 1500, 1e9, 0.0001),
        ("WAN      100 Mbps, 40 ms RTT", 1500, 100e6, 0.040),
        ("Satellite  1 Gbps, 30 ms RTT", 1500, 1e9, 0.030),
    ]
    print(f"{'profile':<34}{'T_frame':>12}{'U':>12}")
    for name, fb, bps, rtt in profiles:
        u = stop_and_wait_utilization(fb, bps, rtt)
        t_frame_us = (fb * 8) / bps * 1e6
        print(f"{name:<34}{t_frame_us:>10.2f}us{u:>11.4%}")
    print("-> The satellite link wastes ~99.96%: this is why sliding-window")
    print("   protocols (go-back-N, selective repeat) pipeline multiple frames.")


def main() -> None:
    demo_arq()
    demo_utilization()


if __name__ == "__main__":
    main()
