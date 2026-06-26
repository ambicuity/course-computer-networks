"""Single-hop data-link service-class simulator.

Demonstrates the three services a data link layer can offer the network layer
(Tanenbaum, Computer Networks, Sec. 3.1.1):

  1. Unacknowledged connectionless   -> Ethernet (IEEE 802.3)
  2. Acknowledged connectionless     -> Wi-Fi   (IEEE 802.11)
  3. Acknowledged connection-oriented -> HDLC / PPP numbered mode

It drives the same fixed network-layer "message" (a list of frames) across a
lossy channel under each service class and reports the on-the-wire evidence:
frames transmitted, ACKs sent, retransmissions, timer expirations, frames
actually delivered to the peer network layer, duplicates delivered, and
duplicates suppressed by sequence numbers.

Pure standard library. No network calls. Deterministic via a seeded PRNG so a
given (seed, frame_loss, ack_loss) reproduces exactly.

Run:  python3 main.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class ServiceClass:
    """Configuration selecting one of the three data-link service classes."""

    name: str
    connection_oriented: bool  # phase 1/2/3 setup-transfer-release
    acknowledged: bool         # receiver returns an ACK per frame
    sequence_numbers: bool     # frames carry seq numbers to suppress duplicates
    real_protocol: str


UNACK_CONNECTIONLESS = ServiceClass(
    name="Unacknowledged connectionless",
    connection_oriented=False,
    acknowledged=False,
    sequence_numbers=False,
    real_protocol="Ethernet / IEEE 802.3",
)

ACK_CONNECTIONLESS = ServiceClass(
    name="Acknowledged connectionless",
    connection_oriented=False,
    acknowledged=True,
    sequence_numbers=False,  # toggle to True to see duplicate suppression
    real_protocol="Wi-Fi / IEEE 802.11",
)

ACK_CONNECTION_ORIENTED = ServiceClass(
    name="Acknowledged connection-oriented",
    connection_oriented=True,
    acknowledged=True,
    sequence_numbers=True,
    real_protocol="HDLC / PPP numbered mode",
)

MAX_RETRIES = 8  # retransmit cap before the link gives up on a frame


@dataclass
class Channel:
    """A lossy one-hop channel with independent data-frame and ACK loss."""

    frame_loss: float
    ack_loss: float
    rng: random.Random

    def frame_survives(self) -> bool:
        return self.rng.random() >= self.frame_loss

    def ack_survives(self) -> bool:
        return self.rng.random() >= self.ack_loss


@dataclass
class Stats:
    """On-the-wire evidence collected during a transfer."""

    frames_transmitted: int = 0      # every send, including retransmissions
    acks_sent: int = 0
    acks_lost: int = 0
    retransmissions: int = 0
    timer_expirations: int = 0
    delivered_unique: int = 0        # frames handed to peer network layer once
    duplicates_delivered: int = 0    # peer saw the same frame more than once
    duplicates_suppressed: int = 0   # retransmit recognized, not re-delivered
    frames_dropped_forever: int = 0  # lost and never recovered
    setup_frames: int = 0            # connection establish + release
    log: list = field(default_factory=list)


class Receiver:
    """Models the peer data-link layer handing frames up to its network layer."""

    def __init__(self, use_sequence_numbers: bool) -> None:
        self.use_sequence_numbers = use_sequence_numbers
        self.expected_seq = 0
        self.delivered_payloads: list[str] = []

    def accept(self, seq: int, payload: str, stats: Stats) -> bool:
        """Return True if an ACK should be produced for this frame."""
        if not self.use_sequence_numbers:
            # No way to tell a retransmission from an original: deliver blindly.
            self.delivered_payloads.append(payload)
            return True

        if seq == self.expected_seq:
            self.delivered_payloads.append(payload)
            self.expected_seq += 1
            stats.delivered_unique += 1
            return True

        # Duplicate (already-delivered) sequence number: re-ACK, do not deliver.
        stats.duplicates_suppressed += 1
        return True


def _transmit_unacked(frames: list[str], channel: Channel, stats: Stats) -> Receiver:
    """Service class 1: fire frames, never wait, never recover."""
    receiver = Receiver(use_sequence_numbers=False)
    for payload in frames:
        stats.frames_transmitted += 1
        if channel.frame_survives():
            receiver.delivered_payloads.append(payload)
            stats.delivered_unique += 1
            stats.log.append(f"  TX {payload!r:>10} -> delivered")
        else:
            stats.frames_dropped_forever += 1
            stats.log.append(f"  TX {payload!r:>10} -> LOST (no recovery)")
    return receiver


def _transmit_acked(
    frames: list[str], channel: Channel, stats: Stats, service: ServiceClass
) -> Receiver:
    """Service classes 2 and 3: ACK per frame, retransmit on timer expiry."""
    receiver = Receiver(use_sequence_numbers=service.sequence_numbers)

    if service.connection_oriented:
        stats.setup_frames += 1  # phase 1: establishment
        stats.log.append("  [connection established: counters initialized]")

    for seq, payload in enumerate(frames):
        acked = False
        for attempt in range(MAX_RETRIES):
            stats.frames_transmitted += 1
            if attempt > 0:
                stats.retransmissions += 1

            if not channel.frame_survives():
                stats.timer_expirations += 1
                stats.log.append(
                    f"  TX#{seq} {payload!r:>8} attempt {attempt + 1}: frame LOST -> timer fires"
                )
                continue

            # Frame arrived; receiver processes and ACKs.
            receiver.accept(seq if service.sequence_numbers else 0, payload, stats)
            if not service.sequence_numbers and attempt == 0:
                stats.delivered_unique += 1
            elif not service.sequence_numbers and attempt > 0:
                # Lost ACK previously: receiver re-delivers (no seq protection).
                stats.duplicates_delivered += 1

            stats.acks_sent += 1
            if channel.ack_survives():
                acked = True
                stats.log.append(
                    f"  TX#{seq} {payload!r:>8} attempt {attempt + 1}: delivered + ACK ok"
                )
                break
            else:
                stats.acks_lost += 1
                stats.timer_expirations += 1
                stats.log.append(
                    f"  TX#{seq} {payload!r:>8} attempt {attempt + 1}: ACK LOST -> timer fires"
                )

        if not acked:
            stats.frames_dropped_forever += 1
            stats.log.append(f"  TX#{seq} {payload!r:>8}: gave up after {MAX_RETRIES} tries")

    if service.connection_oriented:
        stats.setup_frames += 1  # phase 3: release
        stats.log.append("  [connection released: buffers freed]")

    return receiver


def send_message(frames: list[str], service: ServiceClass, channel: Channel) -> Stats:
    """Drive one network-layer message across the link under a service class."""
    stats = Stats()
    if service.acknowledged:
        _transmit_acked(frames, channel, stats, service)
    else:
        _transmit_unacked(frames, channel, stats)
    return stats


def _report(service: ServiceClass, stats: Stats, n_frames: int) -> None:
    print(f"\n=== {service.name} ===")
    print(f"    real protocol : {service.real_protocol}")
    print(f"    message size  : {n_frames} frames")
    print(f"    frames TX'd   : {stats.frames_transmitted}  (incl. retransmissions)")
    print(f"    retransmits   : {stats.retransmissions}")
    print(f"    ACKs sent     : {stats.acks_sent}   ACKs lost: {stats.acks_lost}")
    print(f"    timer expiry  : {stats.timer_expirations}")
    print(f"    setup frames  : {stats.setup_frames}  (establish + release)")
    print(f"    delivered once: {stats.delivered_unique}")
    print(f"    DUP delivered : {stats.duplicates_delivered}  (network layer saw twice)")
    print(f"    DUP suppressed: {stats.duplicates_suppressed}  (seq-number caught retransmit)")
    print(f"    lost forever  : {stats.frames_dropped_forever}")


def main() -> None:
    message = [f"pkt{i:02d}" for i in range(10)]  # the "10 frames" example
    seed = 42
    frame_loss = 0.20  # 2 of 10 lost on average
    ack_loss = 0.20

    print("Data-link service-class comparison")
    print(f"channel: frame_loss={frame_loss}, ack_loss={ack_loss}, seed={seed}")
    print("network-layer message broken into", len(message), "frames")

    for service in (UNACK_CONNECTIONLESS, ACK_CONNECTIONLESS, ACK_CONNECTION_ORIENTED):
        channel = Channel(frame_loss, ack_loss, random.Random(seed))
        stats = send_message(message, service, channel)
        _report(service, stats, len(message))

    # Spotlight: the duplicate-delivery failure mode and how seq numbers fix it.
    print("\n--- Duplicate-delivery failure mode (ack_loss=0.5) ---")
    no_seq = ServiceClass("Ack-connectionless, NO seq#", False, True, False, "802.11 (broken)")
    with_seq = ServiceClass("Ack-connectionless, seq#", False, True, True, "802.11 (fixed)")
    for svc in (no_seq, with_seq):
        ch = Channel(0.0, 0.5, random.Random(7))
        st = send_message(message, svc, ch)
        print(
            f"  {svc.name:30} duplicates_delivered={st.duplicates_delivered} "
            f"duplicates_suppressed={st.duplicates_suppressed}"
        )


if __name__ == "__main__":
    main()
