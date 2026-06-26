"""Feedback-based vs rate-based flow control.

A stdlib-only model of the two flow-control philosophies from the data-link
layer (Tanenbaum & Wetherall, Section 3.1.4):

  * SlidingWindowSender / Receiver  -- feedback-based, credit (window) driven.
  * TokenBucket                      -- rate-based, open-loop pacing.

Run `python3 main.py` for a realistic demo that:
  1. Drives a windowed sender against a slow receiver and prints the credit
     drain/refill plus any blocked sends.
  2. Induces a lost data frame and shows the timer-driven retransmission and
     the receiver's duplicate suppression.
  3. Drives a token bucket with a bursty producer and reports the regulated
     output rate and the backlog.

No third-party packages, no network calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple


# ---------------------------------------------------------------------------
# Feedback-based: sliding window
# ---------------------------------------------------------------------------

@dataclass
class SlidingWindowSender:
    """A go-back-n style sliding-window sender.

    Tracks the textbook variables `ack_expected`, `next_frame_to_send`, and the
    available credit. Sequence numbers are k bits wide and wrap modulo 2**k.
    """
    window: int
    k: int = 3
    ack_expected: int = 0          # left edge of the send window
    next_frame_to_send: int = 0    # next seq to transmit
    in_flight: Dict[int, int] = field(default_factory=dict)  # seq -> ticks outstanding
    delivered: List[int] = field(default_factory=list)        # seqs accepted by receiver
    blocked_count: int = 0
    retransmits: int = 0

    @property
    def max_seq(self) -> int:
        return (1 << self.k) - 1

    @property
    def credit(self) -> int:
        outstanding = (self.next_frame_to_send - self.ack_expected) % (self.max_seq + 1)
        return self.window - outstanding

    def can_send(self) -> bool:
        return self.credit > 0

    def send(self, tick: int) -> int:
        """Emit one frame. Returns the sequence number sent, or -1 if blocked."""
        if not self.can_send():
            self.blocked_count += 1
            return -1
        seq = self.next_frame_to_send
        self.in_flight[seq] = 0  # timer for this outstanding frame
        self.next_frame_to_send = (self.next_frame_to_send + 1) % (self.max_seq + 1)
        return seq

    def receive_ack(self, ack: int) -> None:
        """Process a cumulative ACK carrying `frame_expected` (next seq wanted)."""
        # Advance ack_expected to ack, sliding the window forward.
        while self.ack_expected != ack and self.in_flight:
            self.in_flight.pop(self.ack_expected, None)
            self.ack_expected = (self.ack_expected + 1) % (self.max_seq + 1)

    def tick_timers(self, timeout: int, loss_set: Set[int]) -> List[int]:
        """Age outstanding frames; retransmit any that hit the timeout.

        Returns the list of sequence numbers retransmitted this tick.
        """
        retransmitted: List[int] = []
        for seq in list(self.in_flight.keys()):
            self.in_flight[seq] += 1
            if self.in_flight[seq] >= timeout:
                # Frame (or its ACK) is presumed lost -- retransmit.
                self.in_flight[seq] = 0
                self.retransmits += 1
                retransmitted.append(seq)
        return retransmitted


@dataclass
class Receiver:
    """A bounded receiver that accepts only `frame_expected` (go-back-n).

    Drops frames whose seq != frame_expected; emits a cumulative ACK carrying
    the next expected sequence number. Has a finite queue to model overrun.
    """
    k: int = 3
    frame_expected: int = 0
    queue_capacity: int = 4
    queue_depth: int = 0
    drops: int = 0
    delivered: List[int] = field(default_factory=list)
    seen_duplicates: int = 0

    @property
    def max_seq(self) -> int:
        return (1 << self.k) - 1

    def deliver_one(self) -> None:
        """The application drains one queued frame per tick."""
        if self.queue_depth > 0:
            self.queue_depth -= 1

    def receive(self, seq: int) -> int:
        """Accept a frame; return the cumulative ACK (frame_expected)."""
        # Duplicate of an already-delivered frame (retransmission): ACK it but
        # do not deliver again.
        if seq != self.frame_expected:
            # Out of order or a stale duplicate -- count it, do not advance.
            if seq in self.delivered:
                self.seen_duplicates += 1
            return self.frame_expected

        # In-order frame. Can we queue it?
        if self.queue_depth >= self.queue_capacity:
            self.drops += 1
            return self.frame_expected  # no advance; sender's timer will fire

        self.queue_depth += 1
        self.delivered.append(seq)
        self.frame_expected = (self.frame_expected + 1) % (self.max_seq + 1)
        return self.frame_expected


def run_window_demo(window: int = 4,
                    loss_positions: Set[int] | None = None,
                    total_frames: int = 16,
                    timeout: int = 4) -> None:
    """Drive a windowed sender against a slow receiver (drains 1 frame/tick)."""
    loss_positions = loss_positions or set()
    sender = SlidingWindowSender(window=window, k=3)
    rx = Receiver(k=3, queue_capacity=4)
    tick = 0
    seq_counter = 0  # raw frame counter to index loss positions

    print("=" * 72)
    print(f"FEEDBACK-BASED: sliding window N={window}, loss at raw frames {loss_positions}")
    print("=" * 72)
    print(f"{'tick':>4} {'sent':>5} {'credit':>7} {'infl':>5} {'ack':>5} "
          f"{'rxq':>4} {'drops':>6} {'note':<24}")

    produced = 0
    while len(rx.delivered) < total_frames and tick < 200:
        note = ""
        sent_seq = -1
        if produced < total_frames:
            sent_seq = sender.send(tick)
            if sent_seq == -1:
                note = "BLOCKED (no credit)"
            else:
                produced += 1
                if (produced - 1) in loss_positions:
                    note = f"frame {produced-1} LOST (no ACK)"
                else:
                    # Receiver gets the frame.
                    ack = rx.receive(sent_seq)
                    sender.receive_ack(ack)

        # Age timers and retransmit on timeout (models a lost frame/ACK).
        retrans = sender.tick_timers(timeout, loss_positions)
        for rseq in retrans:
            note = f"TIMEOUT retransmit seq={rseq}"
            ack = rx.receive(rseq)
            sender.receive_ack(ack)

        # Application drains one queued frame per tick (slow consumer).
        rx.deliver_one()

        inflight = len(sender.in_flight)
        print(f"{tick:>4} {sent_seq:>5} {sender.credit:>7} {inflight:>5} "
              f"{sender.ack_expected:>5} {rx.queue_depth:>4} {rx.drops:>6} {note:<24}")
        tick += 1

    print(f"\nDelivered {len(rx.delivered)} frames in {tick} ticks; "
          f"retransmits={sender.retransmits}, blocked_ticks={sender.blocked_count}, "
          f"rx_drops={rx.drops}, duplicates_seen={rx.seen_duplicates}\n")


# ---------------------------------------------------------------------------
# Rate-based: token bucket
# ---------------------------------------------------------------------------

@dataclass
class TokenBucket:
    """A classic token-bucket policer (ITU-T I.371 / RFC 3290 shape).

    Tokens accrue at `rate` (units/s) up to `capacity` (units). A sender may
    emit `n` units only if `n <= tokens`, consuming them; otherwise it queues.
    """
    rate: float          # tokens per tick
    capacity: float      # bucket depth in tokens
    tokens: float = 0.0
    backlog: float = 0.0  # queued data waiting for tokens

    def refill(self) -> None:
        self.tokens = min(self.capacity, self.tokens + self.rate)

    def offer(self, amount: float) -> None:
        """Producer offers `amount` units this tick."""
        self.backlog += amount

    def drain(self) -> float:
        """Send as much as tokens allow; return units actually transmitted."""
        send = min(self.backlog, self.tokens)
        self.tokens -= send
        self.backlog -= send
        return send


def run_rate_demo(rate: float = 200.0,
                  capacity: float = 1000.0,
                  link_bps: float = 1000.0,
                  producer_profile: List[Tuple[int, float]] | None = None,
                  ticks: int = 40) -> None:
    """Drive a token bucket with a bursty producer.

    Units are abstract "tokens" (think Mb of data per tick). `link_bps` is the
    peak line rate; the regulated output cannot exceed it.
    """
    if producer_profile is None:
        # (tick, offered units): mostly idle, with a big burst mid-run.
        producer_profile = [(t, 50.0 if t < 10 else (600.0 if t == 10 else 50.0))
                            for t in range(ticks)]

    bucket = TokenBucket(rate=rate, capacity=capacity, tokens=capacity)
    print("=" * 72)
    print(f"RATE-BASED: token bucket R={rate}/tick, C={capacity}, link={link_bps}/tick")
    print("=" * 72)
    print(f"{'tick':>4} {'offered':>9} {'tokens':>9} {'sent':>8} "
          f"{'backlog':>9} {'note':<20}")

    total_offered = 0.0
    total_sent = 0.0
    for tick, offered in producer_profile:
        bucket.refill()
        bucket.offer(offered)
        sent = bucket.drain()
        # Cap at link rate (peak rate cannot exceed the wire).
        sent = min(sent, link_bps)
        total_offered += offered
        total_sent += sent
        note = "BURST" if offered > 2 * rate else ""
        print(f"{tick:>4} {offered:>9.1f} {bucket.tokens:>9.1f} {sent:>8.1f} "
              f"{bucket.backlog:>9.1f} {note:<20}")

    avg_out = total_sent / len(producer_profile)
    print(f"\nTotal offered={total_offered:.1f}, total sent={total_sent:.1f}, "
          f"avg regulated output={avg_out:.1f}/tick (R={rate}/tick), "
          f"final backlog={bucket.backlog:.1f}\n")


# ---------------------------------------------------------------------------
# Link utilization helper (worked numeric example)
# ---------------------------------------------------------------------------

def link_utilization(bandwidth: float, frame_bits: float,
                     prop_delay: float, window: int) -> float:
    """Return utilization for a windowed sender on a single link.

    bandwidth in bits/s, frame_bits in bits, prop_delay in s (one-way).
    """
    transmit = frame_bits / bandwidth
    a = prop_delay * bandwidth / frame_bits
    util = window / (1 + 2 * a)
    return min(1.0, util)


def min_window_for_util(bandwidth: float, frame_bits: float,
                        prop_delay: float, target: float = 0.95) -> int:
    a = prop_delay * bandwidth / frame_bits
    return int((1 + 2 * a) * target) + 1


def main() -> None:
    # 1. Feedback-based: healthy window against a slow receiver.
    run_window_demo(window=4, loss_positions=set(), total_frames=12)

    # 2. Feedback-based: a lost data frame forces a timeout retransmission,
    #    and the receiver's duplicate suppression drops the copy.
    run_window_demo(window=4, loss_positions={5}, total_frames=12)

    # 3. Feedback-based: oversized window overruns the receiver queue.
    run_window_demo(window=8, loss_positions=set(), total_frames=16)

    # 4. Rate-based: token bucket shaping a bursty producer.
    run_rate_demo(rate=200.0, capacity=1000.0, link_bps=1000.0)

    # 5. Worked link-utilization example (the textbook satellite problem).
    bw = 1_000_000.0       # 1 Mb/s
    L = 1000.0             # bits
    tprop = 0.250          # 250 ms satellite
    a = tprop * bw / L
    u_stop_wait = link_utilization(bw, L, tprop, 1)
    n_needed = min_window_for_util(bw, L, tprop, 0.95)
    print("=" * 72)
    print("LINK UTILIZATION (satellite: 1 Mb/s, 1000-bit frames, 250 ms one-way)")
    print("=" * 72)
    print(f"a = T_prop * B / L = {a:.1f}")
    print(f"stop-and-wait (N=1) utilization = {u_stop_wait*100:.3f}%")
    print(f"window N needed for 95% utilization = {n_needed}")
    print(f"utilization at N={n_needed} = "
          f"{link_utilization(bw, L, tprop, n_needed)*100:.2f}%\n")


if __name__ == "__main__":
    main()
