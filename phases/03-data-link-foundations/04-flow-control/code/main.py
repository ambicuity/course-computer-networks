#!/usr/bin/env python3
"""Flow-control simulator for the data link layer (Tanenbaum 3.1.4).

Stdlib only, no network calls. Demonstrates the three things an engineer
actually needs to reason about flow control:

  1. stop_and_wait_utilization() -- why one-frame-at-a-time wastes fat links.
  2. min_window_for_full_link()  -- the window size derived from the
     bandwidth-delay product that keeps the pipe full.
  3. SlidingWindowSender         -- a Go-Back-N sender/receiver pair traced
     through normal flow and a single lost-frame recovery.

Plus pause_quanta_to_microseconds() for IEEE 802.3x PAUSE frames.

Run:  python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

# --- Physical constants -----------------------------------------------------

BITS_PER_BYTE = 8
PAUSE_QUANTUM_BIT_TIMES = 512  # one 802.3x pause quantum = 512 bit-times


# --- Stop-and-wait ----------------------------------------------------------

def frame_time_seconds(frame_bytes: int, link_bps: float) -> float:
    """Serialization (transmission) time for one frame."""
    return (frame_bytes * BITS_PER_BYTE) / link_bps


def stop_and_wait_utilization(
    frame_bytes: int,
    link_bps: float,
    one_way_delay_s: float,
    ack_bytes: int = 64,
) -> float:
    """Link utilization for stop-and-wait ARQ.

    utilization = t_frame / (t_frame + 2*t_prop + t_ack)
    """
    t_frame = frame_time_seconds(frame_bytes, link_bps)
    t_ack = frame_time_seconds(ack_bytes, link_bps)
    cycle = t_frame + 2 * one_way_delay_s + t_ack
    return t_frame / cycle


def min_window_for_full_link(
    frame_bytes: int,
    link_bps: float,
    one_way_delay_s: float,
    ack_bytes: int = 64,
) -> int:
    """Smallest sliding window (in frames) that keeps the link fully busy.

    W_min = ceil( (t_frame + 2*t_prop + t_ack) / t_frame )
    """
    t_frame = frame_time_seconds(frame_bytes, link_bps)
    t_ack = frame_time_seconds(ack_bytes, link_bps)
    cycle = t_frame + 2 * one_way_delay_s + t_ack
    # ceiling division without importing math
    ratio = cycle / t_frame
    return int(ratio) + (1 if ratio != int(ratio) else 0)


def bandwidth_delay_product_bytes(link_bps: float, rtt_s: float) -> float:
    """Bytes in flight needed to fill the pipe: bandwidth * RTT."""
    return (link_bps * rtt_s) / BITS_PER_BYTE


# --- IEEE 802.3x PAUSE ------------------------------------------------------

def pause_quanta_to_microseconds(quanta: int, link_bps: float) -> float:
    """Duration a PAUSE frame silences a link.

    Each quantum is 512 bit-times; one bit-time = 1/link_bps seconds.
    """
    bit_time_s = 1.0 / link_bps
    seconds = quanta * PAUSE_QUANTUM_BIT_TIMES * bit_time_s
    return seconds * 1e6


# --- Sliding-window (Go-Back-N) sender/receiver -----------------------------

@dataclass
class GoBackNReceiver:
    """In-order-only receiver: cumulative ACK, no out-of-order buffering."""

    rcv_next: int = 0  # RCV.NXT: next in-order sequence expected
    delivered: List[int] = field(default_factory=list)

    def on_frame(self, seq: int) -> int:
        """Process an arriving frame; return the cumulative ACK number."""
        if seq == self.rcv_next:
            self.delivered.append(seq)
            self.rcv_next += 1
        # else: out of order -> discard (Go-Back-N), re-ACK last in-order
        return self.rcv_next  # ACK = next expected (RFC-style cumulative ACK)


@dataclass
class SlidingWindowSender:
    """Go-Back-N sender. base=SND.UNA, next_seq=SND.NXT, window=SND.WND."""

    window: int
    total_frames: int
    base: int = 0
    next_seq: int = 0

    def can_send(self) -> bool:
        return self.next_seq < self.base + self.window and self.next_seq < self.total_frames

    def send_next(self) -> int:
        seq = self.next_seq
        self.next_seq += 1
        return seq

    def on_ack(self, ack: int) -> None:
        """Cumulative ACK advances base; Go-Back-N rewinds next_seq on loss."""
        if ack > self.base:
            self.base = ack

    def go_back(self) -> None:
        """Timeout: resend everything from base onward."""
        self.next_seq = self.base

    def done(self) -> bool:
        return self.base >= self.total_frames


def simulate_go_back_n(
    total_frames: int, window: int, drop_seq: Optional[int]
) -> List[str]:
    """Trace one Go-Back-N episode. Optionally drop frame `drop_seq` once."""
    sender = SlidingWindowSender(window=window, total_frames=total_frames)
    receiver = GoBackNReceiver()
    trace: List[str] = []
    dropped_once = False
    in_flight: List[int] = []

    while not sender.done():
        # Fill the window.
        while sender.can_send():
            seq = sender.send_next()
            in_flight.append(seq)
            trace.append(f"SEND  seq={seq:<2d}  [base={sender.base} next={sender.next_seq} W={window}]")

        # Deliver in-flight frames to the receiver, possibly dropping one.
        timeout = False
        for seq in list(in_flight):
            in_flight.remove(seq)
            if seq == drop_seq and not dropped_once:
                dropped_once = True
                trace.append(f"  LOSS  seq={seq}  (frame dropped on the link)")
                timeout = True
                break  # later frames are out-of-order -> discarded anyway
            ack = receiver.on_frame(seq)
            sender.on_ack(ack)
            trace.append(f"  ACK   ack={ack:<2d} (rcv_next={receiver.rcv_next})")

        if timeout:
            in_flight.clear()
            trace.append(f"  TIMEOUT at base={sender.base} -> Go-Back-N: resend from {sender.base}")
            sender.go_back()

    trace.append(f"DONE delivered={receiver.delivered}")
    return trace


# --- Demonstration ----------------------------------------------------------

LINKS = [
    ("Gigabit LAN",     1_000_000_000, 0.0001),   # 0.1 ms one-way
    ("Cross-country",     100_000_000, 0.030),    # 30 ms one-way
    ("Trans-Pacific",     100_000_000, 0.080),    # 80 ms one-way
    ("GEO satellite",   1_000_000_000, 0.250),    # 250 ms one-way
]


def main() -> None:
    frame_bytes = 1500

    print("=" * 70)
    print("STOP-AND-WAIT vs SLIDING-WINDOW  (1500-byte frames)")
    print("=" * 70)
    print(f"{'Link':<16}{'1-way':>8}{'util %':>10}{'W to fill':>12}{'BDP (KB)':>11}")
    for name, bps, owd in LINKS:
        util = stop_and_wait_utilization(frame_bytes, bps, owd)
        wmin = min_window_for_full_link(frame_bytes, bps, owd)
        bdp_kb = bandwidth_delay_product_bytes(bps, 2 * owd) / 1024
        print(f"{name:<16}{owd*1000:>6.1f}ms{util*100:>9.3f}%{wmin:>12,d}{bdp_kb:>11,.1f}")

    print()
    print("Note: GEO satellite needs a ~41,000-frame window; TCP's 16-bit")
    print("window (max 65,535 B) requires RFC 7323 Window Scale to fill it.")

    print()
    print("=" * 70)
    print("IEEE 802.3x PAUSE: max pause_time = 0xFFFF quanta (512 bit-times)")
    print("=" * 70)
    for name, bps in [("1 GbE", 1e9), ("10 GbE", 1e10), ("100 GbE", 1e11)]:
        us = pause_quanta_to_microseconds(0xFFFF, bps)
        print(f"  {name:<8} -> link silenced for {us:>10.2f} us ({us/1000:.3f} ms)")

    print()
    print("=" * 70)
    print("GO-BACK-N TRACE: window=4, 7 frames, frame 2 lost once")
    print("=" * 70)
    for line in simulate_go_back_n(total_frames=7, window=4, drop_seq=2):
        print(line)


if __name__ == "__main__":
    main()
