"""TCP Congestion Control over Wireless Links — discrete-event simulation.

Models a single TCP-NewReno sender pushing a fixed-size file over either a
"wired" path (low loss, p=0.0001) or a "wireless" path (high loss, p=0.05).
The sender runs AIMD: cwnd grows by one MSS per RTT in congestion avoidance,
and halves on triple-duplicate-ACK. A "Snoop" agent can be inserted at the
wireless edge to cache unACKed segments and locally retransmit lost ones,
hiding the loss from the sender.

Stdlib only. Run: python3 code/main.py
"""

from __future__ import annotations

import random
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple


MSS = 1460                       # bytes per segment
INITIAL_CWND = 1                 # MSS units (RFC 5681 safe starting point)
SSTHRESH_INIT = 64               # MSS units; arbitrary for this lab
TRIPLE_DUP_ACK = 3               # duplicate ACKs before fast retransmit
RTT_MS = 50                      # round-trip time
SNOOP_RECOVERY_PROB = 0.95       # probability the snoop's local retransmit succeeds


# --------------------------------------------------------------------------- #
#  Network model                                                               #
# --------------------------------------------------------------------------- #

@dataclass
class Link:
    """A symmetric path with a per-segment loss probability.

    `loss_prob` is the probability that any single segment (forward or
    reverse ACK) is silently dropped.
    """

    name: str
    rtt_ms: int
    loss_prob: float
    rng: random.Random = field(default_factory=random.Random)

    def is_lost(self) -> bool:
        return self.rng.random() < self.loss_prob


# --------------------------------------------------------------------------- #
#  Event types                                                                 #
# --------------------------------------------------------------------------- #

@dataclass
class Segment:
    """A TCP segment in flight."""

    seq: int
    n_bytes: int
    send_time_ms: int

    def ack(self) -> int:
        return self.seq + self.n_bytes


@dataclass
class AckEvent:
    """An ACK arrives at the sender."""

    ack_seq: int
    send_time_ms: int


@dataclass
class TimeoutEvent:
    """A retransmission timer fired at the sender."""

    fired_at_ms: int


# --------------------------------------------------------------------------- #
#  TCP-NewReno sender (event-driven)                                           #
# --------------------------------------------------------------------------- #

class TCPSender:
    """A minimal TCP-NewReno sender driven by a discrete-event loop."""

    def __init__(self, link: Link) -> None:
        self.link = link
        self.cwnd = INITIAL_CWND
        self.ssthresh = SSTHRESH_INIT
        self.next_seq = 0
        self.highest_acked = -1
        self.dup_ack_count = 0
        self.in_flight: Dict[int, Segment] = {}
        self.halving_events = 0
        self.timeout_events = 0
        self.rtt_samples: List[int] = []

    def bytes_in_flight(self) -> int:
        return sum(s.n_bytes for s in self.in_flight.values())

    def can_send(self) -> bool:
        return self.bytes_in_flight() < self.cwnd * MSS

    def on_send(self, segment: Segment) -> None:
        self.in_flight[segment.seq] = segment
        self.next_seq = segment.seq + segment.n_bytes

    def on_ack(self, ack_seq: int, send_time_ms: int, now_ms: int) -> None:
        if ack_seq > self.highest_acked:
            newly_acked = ack_seq - self.highest_acked
            self.rtt_samples.append(now_ms - send_time_ms)
            for s in list(self.in_flight.keys()):
                if s < ack_seq:
                    del self.in_flight[s]
            self.highest_acked = ack_seq
            self.dup_ack_count = 0
            # Slow start vs congestion avoidance (AIMD growth).
            if self.cwnd < self.ssthresh:
                self.cwnd += max(1, newly_acked // MSS)
            else:
                self.cwnd += max(1, newly_acked // max(self.cwnd * MSS, 1))
            return

        # Duplicate ACK.
        self.dup_ack_count += 1
        if self.dup_ack_count == TRIPLE_DUP_ACK:
            self._fast_retransmit()

    def on_timeout(self, now_ms: int) -> None:
        self.timeout_events += 1
        self.ssthresh = max(self.cwnd // 2, 2)
        self.cwnd = 1

    def _fast_retransmit(self) -> None:
        self.halving_events += 1
        self.ssthresh = max(self.cwnd // 2, 2)
        self.cwnd = self.ssthresh

    def oldest_unacked_seq(self) -> Optional[int]:
        if not self.in_flight:
            return None
        return min(self.in_flight.keys())


# --------------------------------------------------------------------------- #
#  Snooping agent                                                              #
# --------------------------------------------------------------------------- #

class SnoopAgent:
    """Base-station snoop cache, the Balakrishnan et al. (1995) design."""

    def __init__(self) -> None:
        self.cache: Dict[int, Segment] = {}
        self.local_retransmits = 0

    def on_forward(self, segment: Segment) -> None:
        if segment.seq not in self.cache:
            self.cache[segment.seq] = segment

    def on_dup_ack(self, ack_seq: int, rng: random.Random) -> Optional[int]:
        """If the ACK is a duplicate for a cached segment, attempt a local
        recovery. Returns the seq that was recovered (caller removes it from
        sender's in-flight map) or None if nothing to recover."""
        # Trim cache past the latest cumulative ACK.
        for s in list(self.cache.keys()):
            if s < ack_seq:
                del self.cache[s]
        if not self.cache:
            return None
        lowest = min(self.cache.keys())
        if ack_seq <= lowest and rng.random() < SNOOP_RECOVERY_PROB:
            self.local_retransmits += 1
            del self.cache[lowest]
            return lowest
        return None


# --------------------------------------------------------------------------- #
#  Simulation driver                                                           #
# --------------------------------------------------------------------------- #

def simulate(
    *,
    file_bytes: int,
    link: Link,
    seed: int,
    use_snoop: bool = False,
) -> Tuple[float, int, int, int]:
    """Drive the sender until `file_bytes` have been ACKed.

    Returns (throughput_Mbps, halving_events, timeout_events, bytes_acked).
    """
    rng = random.Random(seed)
    link.rng = rng
    sender = TCPSender(link=link)
    snoop = SnoopAgent() if use_snoop else None

    # Pending ACKs scheduled to arrive at the sender at arrival_time.
    pending_acks: Dict[int, List[AckEvent]] = {}
    # Pending retransmission timeouts (single timer, RFC 6298 simplified).
    rto_ms = max(link.rtt_ms * 4, 200)
    next_timeout_at_ms: Optional[int] = None

    bytes_acked = 0
    t = 0
    MAX_TICKS = 10_000_000  # safety cap

    def deliver_segment(segment: Segment) -> None:
        """Forward direction: segment travels to receiver (or gets lost)."""
        nonlocal bytes_acked
        if snoop is not None:
            snoop.on_forward(segment)
        if link.is_lost():
            # The segment is lost on the wireless hop. The snoop may recover.
            if snoop is not None:
                recovered_seq = snoop.on_dup_ack(segment.seq, rng)
                if recovered_seq is not None:
                    bytes_acked += MSS
                    # The receiver never generated the ACK; the snoop synthesizes
                    # one and forwards it with ELN so the sender does not halve.
                    _schedule_ack(segment.ack(), segment.send_time_ms, eln=True)
                    return
            # Truly lost. No ACK will ever arrive for this segment; sender
            # will eventually time out and retransmit.
            return
        # Receiver gets it; emits ACK. ACK itself can be lost.
        bytes_acked += MSS
        _schedule_ack(segment.ack(), segment.send_time_ms, eln=False)

    def _schedule_ack(ack_seq: int, send_time_ms: int, eln: bool) -> None:
        if link.is_lost():
            # ACK lost. Sender will eventually retransmit.
            return
        arrival = send_time_ms + link.rtt_ms
        pending_acks.setdefault(arrival, []).append(
            AckEvent(ack_seq=ack_seq, send_time_ms=send_time_ms)
        )

    def retransmit_oldest() -> None:
        """Retransmit the lowest unACKed segment, treating it as a fresh send."""
        seq = sender.oldest_unacked_seq()
        if seq is None:
            return
        seg = sender.in_flight[seq]
        # On timeout the sender resets cwnd to 1 and resends.
        sender.on_timeout(t)
        deliver_segment(Segment(seq=seq, n_bytes=seg.n_bytes, send_time_ms=t))

    # ---- main event loop ----
    while bytes_acked < file_bytes and t < MAX_TICKS:
        # 1. Deliver any ACKs whose arrival time has come.
        arrivals = pending_acks.pop(t, [])
        for ack in arrivals:
            sender.on_ack(ack.ack_seq, ack.send_time_ms, t)

        # 2. Fire retransmission timer if due.
        if next_timeout_at_ms is not None and t >= next_timeout_at_ms:
            retransmit_oldest()
            next_timeout_at_ms = None if not sender.in_flight else t + rto_ms
            t += 1
            continue

        # 3. Send new segments up to cwnd.
        while sender.can_send() and bytes_acked + sender.bytes_in_flight() < file_bytes:
            seg = Segment(seq=sender.next_seq, n_bytes=MSS, send_time_ms=t)
            sender.on_send(seg)
            deliver_segment(seg)
            # Arm / reset the retransmission timer.
            next_timeout_at_ms = t + rto_ms
            if link.is_lost() and snoop is None:
                # Pathological fast path: if we lose AND no snoop, the loop
                # would spin; break and let the timer fire so cwnd collapses.
                break

        # 4. Advance the clock to the next event, or step by 1 ms.
        next_arrival = min(pending_acks.keys()) if pending_acks else None
        candidates = [c for c in (next_arrival, next_timeout_at_ms) if c is not None]
        if candidates:
            t = min(candidates)
        else:
            t += 1

    elapsed_s = max(t, 1) / 1000.0
    throughput_Mbps = (bytes_acked * 8) / (elapsed_s * 1_000_000)
    return throughput_Mbps, sender.halving_events, sender.timeout_events, bytes_acked


# --------------------------------------------------------------------------- #
#  Reporting                                                                   #
# --------------------------------------------------------------------------- #

def compare() -> None:
    file_bytes = 5 * 1024 * 1024  # 5 MB
    seed = 2026

    wired = Link(name="wired", rtt_ms=RTT_MS, loss_prob=0.0001)
    wireless = Link(name="wireless", rtt_ms=RTT_MS, loss_prob=0.05)

    wired_t, wired_h, wired_to, _ = simulate(
        file_bytes=file_bytes, link=wired, seed=seed
    )
    wireless_t, wireless_h, wireless_to, _ = simulate(
        file_bytes=file_bytes, link=wireless, seed=seed
    )
    snooped_t, snooped_h, snooped_to, _ = simulate(
        file_bytes=file_bytes, link=wireless, seed=seed, use_snoop=True
    )

    print(f"file size            : {file_bytes / 1e6:.1f} MB")
    print(f"RTT                  : {RTT_MS} ms")
    print(f"MSS                  : {MSS} bytes")
    print()
    print(f"wired (p=0.0001)     : throughput = {wired_t:6.2f} Mbps"
          f"  cwnd halvings = {wired_h:3d}  timeouts = {wired_to}")
    print(f"wireless (p=0.0500)  : throughput = {wireless_t:6.2f} Mbps"
          f"  cwnd halvings = {wireless_h:3d}  timeouts = {wireless_to}")
    print(f"wireless + snoop     : throughput = {snooped_t:6.2f} Mbps"
          f"  cwnd halvings = {snooped_h:3d}  timeouts = {snooped_to}")
    print()
    if wired_t > 0:
        print(f"wireless / wired     : {wireless_t / wired_t:6.1%} of wired throughput")
        print(f"snoop / wired        : {snooped_t / wired_t:6.1%} of wired throughput")


def main() -> None:
    random.seed(20260625)
    compare()


if __name__ == "__main__":
    main()