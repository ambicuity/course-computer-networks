#!/usr/bin/env python3
"""Stop-and-wait ARQ / PAR (Protocol 3) simulator over a noisy channel.

Models Tanenbaum's Protocol 3 (Positive Acknowledgement with Retransmission):
a one-directional data flow protected by a 1-bit sequence number and a
retransmission timer. The simulation makes the lost-ACK duplicate-delivery
bug visible: with a sequence number the receiver drops the duplicate
(DUP-DROP) instead of double-delivering, and a too-short timeout produces a
counted storm of premature retransmissions.

Frame header fields mirror the textbook:
    seq  - 1-bit sequence number (0 or 1) on a data frame
    ack  - 1-bit acknowledgement number on an ACK frame
    kind - "data" or "ack"

Run:  python3 main.py
No third-party dependencies, no network access.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

MAX_SEQ = 1  # 1-bit sequence space: values are 0 and 1


def inc(seq: int) -> int:
    """Advance a 1-bit sequence number circularly (0->1, 1->0)."""
    return (seq + 1) % (MAX_SEQ + 1)


@dataclass
class Frame:
    """A data or acknowledgement frame on the wire."""

    kind: str             # "data" or "ack"
    seq: int = 0          # sequence number (data frames)
    ack: int = 0          # acknowledgement number (ack frames)
    payload: str = ""     # network-layer packet contents
    corrupt: bool = False  # set by the channel when checksum would fail


@dataclass
class Stats:
    """Counters that stand in for the evidence you would read from a trace."""

    data_tx: int = 0
    retransmissions: int = 0
    premature_retx: int = 0
    acks_sent: int = 0
    delivered: int = 0
    dup_dropped: int = 0
    cksum_errors: int = 0
    log: List[str] = field(default_factory=list)

    def record(self, line: str) -> None:
        self.log.append(line)


class NoisyChannel:
    """A lossy, corrupting channel with independent control over directions."""

    def __init__(
        self,
        rng: random.Random,
        data_loss: float = 0.0,
        data_corrupt: float = 0.0,
        ack_loss: float = 0.0,
        ack_corrupt: float = 0.0,
    ) -> None:
        self.rng = rng
        self.data_loss = data_loss
        self.data_corrupt = data_corrupt
        self.ack_loss = ack_loss
        self.ack_corrupt = ack_corrupt

    def transmit(self, frame: Frame) -> Optional[Frame]:
        """Return the (possibly corrupted) frame, or None if it was lost."""
        loss = self.data_loss if frame.kind == "data" else self.ack_loss
        corrupt = self.data_corrupt if frame.kind == "data" else self.ack_corrupt
        if self.rng.random() < loss:
            return None
        delivered = Frame(frame.kind, frame.seq, frame.ack, frame.payload)
        if self.rng.random() < corrupt:
            delivered.corrupt = True
        return delivered


class Receiver:
    """Protocol 3 receiver: accepts in-order frames, re-acks the last good one."""

    def __init__(self, stats: Stats) -> None:
        self.frame_expected = 0
        self.stats = stats

    def on_data(self, frame: Optional[Frame]) -> Optional[Frame]:
        """Process an inbound data frame; return the ACK frame to send back."""
        if frame is None:
            self.stats.record("RX   <lost>            (no data arrived)")
            return None
        if frame.corrupt:
            self.stats.cksum_errors += 1
            self.stats.record(f"RX   CKSUM-ERR seq={frame.seq}    -> discard, no ack")
            return None
        if frame.seq == self.frame_expected:
            self.stats.delivered += 1
            self.stats.record(
                f"RX   seq={frame.seq} '{frame.payload}'  -> DELIVER to network layer"
            )
            self.frame_expected = inc(self.frame_expected)
        else:
            self.stats.dup_dropped += 1
            self.stats.record(
                f"RX   seq={frame.seq}                -> DUP-DROP "
                f"(expected {self.frame_expected})"
            )
        # Ack the LAST correctly received frame: 1 - frame_expected.
        ack_no = (1 - self.frame_expected) % (MAX_SEQ + 1)
        self.stats.acks_sent += 1
        self.stats.record(f"ACK  ack={ack_no}              -> sent to sender")
        return Frame("ack", ack=ack_no)


def run_par(
    packets: List[str],
    channel: NoisyChannel,
    timeout_is_premature: bool = False,
) -> Stats:
    """Drive Protocol 3 sender against a receiver over the noisy channel.

    `timeout_is_premature=True` forces the sender to behave as if its timer is
    shorter than one RTT: even when a valid ACK arrives, the sender counts the
    redundant resend the early timer would have triggered.
    """
    stats = Stats()
    receiver = Receiver(stats)
    next_frame_to_send = 0
    index = 0
    attempts_for_current = 0

    while index < len(packets):
        frame = Frame("data", seq=next_frame_to_send, payload=packets[index])
        stats.data_tx += 1
        attempts_for_current += 1
        if attempts_for_current > 1:
            stats.retransmissions += 1
        stats.record(
            f"TX   seq={frame.seq} '{frame.payload}'  "
            f"(attempt {attempts_for_current})"
        )

        delivered = channel.transmit(frame)
        ack_frame = receiver.on_data(delivered)
        ack_back = channel.transmit(ack_frame) if ack_frame is not None else None

        valid_ack = (
            ack_back is not None
            and not ack_back.corrupt
            and ack_back.ack == next_frame_to_send
        )

        if valid_ack and not timeout_is_premature:
            stats.record(f"     ACK ok (ack={ack_back.ack}) -> advance window")
            next_frame_to_send = inc(next_frame_to_send)
            index += 1
            attempts_for_current = 0
        elif timeout_is_premature and valid_ack:
            # ACK actually arrived, but the short timer fired first: the sender
            # still advances (the ack is valid) yet wastes a retransmission.
            stats.premature_retx += 1
            stats.record("     TIMEOUT (premature) -> advance anyway, retx counted")
            next_frame_to_send = inc(next_frame_to_send)
            index += 1
            attempts_for_current = 0
        else:
            reason = (
                "ack lost" if ack_back is None
                else "ack corrupt" if ack_back.corrupt
                else "timeout"
            )
            stats.record(f"     TIMEOUT ({reason}) -> retransmit same frame")

    return stats


def summarize(title: str, stats: Stats, expected_unique: int) -> None:
    print(f"\n=== {title} ===")
    for line in stats.log:
        print("  " + line)
    print("  " + "-" * 52)
    print(f"  data frames sent      : {stats.data_tx}")
    print(f"  retransmissions       : {stats.retransmissions}")
    print(f"  premature retransmits : {stats.premature_retx}")
    print(f"  acks sent             : {stats.acks_sent}")
    print(f"  checksum errors       : {stats.cksum_errors}")
    print(f"  duplicates dropped    : {stats.dup_dropped}")
    print(f"  packets delivered     : {stats.delivered} (expected {expected_unique})")
    correct = stats.delivered == expected_unique
    print(f"  exactly-once delivery : {'OK' if correct else 'FAILED'}")


def utilization(frame_bits: int, link_bps: float, rtt_s: float) -> Tuple[float, float]:
    """Stop-and-wait link utilization = Tframe / (Tframe + RTT)."""
    t_frame = frame_bits / link_bps
    return t_frame, t_frame / (t_frame + rtt_s)


def main() -> None:
    packets = ["A0", "A1", "A2", "A3", "A4"]

    # 1) Clean channel: every frame and ack get through, no duplicates.
    clean = NoisyChannel(random.Random(1))
    summarize("Clean channel", run_par(packets, clean), len(packets))

    # 2) ACKs lost 40% of the time: the lost-ACK trap. Sequence numbers turn
    #    retransmissions into DUP-DROP events, preserving exactly-once delivery.
    lossy_ack = NoisyChannel(random.Random(7), ack_loss=0.4)
    summarize("Lossy ACK channel (40% ack loss)", run_par(packets, lossy_ack),
              len(packets))

    # 3) Damaged data frames: caught by checksum, discarded, retransmitted.
    noisy = NoisyChannel(random.Random(11), data_corrupt=0.3, ack_loss=0.1)
    summarize("Noisy data + ack loss", run_par(packets, noisy), len(packets))

    # 4) Premature timeout: timer < RTT. Correct delivery, wasted bandwidth.
    clean2 = NoisyChannel(random.Random(3))
    summarize("Premature timeout (timer < RTT)",
              run_par(packets, clean2, timeout_is_premature=True), len(packets))

    # 5) Throughput intuition: why window size 1 starves a long-RTT link.
    print("\n=== Stop-and-wait utilization ===")
    for label, bits, bps, rtt in [
        ("RS-485 9600bps, 2048b frame, ~1ms RTT", 2048, 9600, 0.001),
        ("LAN 100Mbps, 12000b frame, 0.4ms RTT", 12000, 100_000_000, 0.0004),
        ("GEO sat 1Mbps, 1000b frame, 540ms RTT", 1000, 1_000_000, 0.540),
    ]:
        t_frame, u = utilization(bits, bps, rtt)
        print(f"  {label}: Tframe={t_frame*1000:.3f}ms  utilization={u*100:.2f}%")


if __name__ == "__main__":
    main()
