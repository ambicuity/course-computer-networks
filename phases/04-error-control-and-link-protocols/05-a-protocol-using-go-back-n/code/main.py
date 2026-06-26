#!/usr/bin/env python3
"""Go-Back-N (Tanenbaum Protocol 5) simulator and window-sizing calculator.

Stdlib only, no network calls. Demonstrates three things:

1. Bandwidth-delay window sizing: w = 2*BD + 1, and the utilization bound
   w / (1 + 2*BD), reproducing the 50-kbps / 500-ms satellite example
   (BD = 12.5 frames, w = 26, stop-and-wait ~= 4%).
2. The circular `between(a, b, c)` window test used to drain cumulative acks.
3. A deterministic event-driven trace of a Go-Back-N sender and a
   receive-window-of-1 receiver, including a scripted single-frame loss that
   forces the sender to "go back N" and retransmit the whole outstanding window.

Run:  python3 main.py
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Part 1: window sizing from the bandwidth-delay product
# ---------------------------------------------------------------------------

def bandwidth_delay_product(bandwidth_bps: float, one_way_delay_s: float,
                            frame_bits: int) -> float:
    """Frames in flight one-way: bandwidth * one-way delay / frame size."""
    return (bandwidth_bps * one_way_delay_s) / frame_bits


def optimal_window(bd: float) -> int:
    """Smallest window that saturates the link: w = ceil(2*BD + 1)."""
    return math.ceil(2 * bd + 1)


def link_utilization(window: int, bd: float) -> float:
    """Upper bound on utilization for a window: w / (1 + 2*BD), capped at 1.0."""
    return min(1.0, window / (1.0 + 2.0 * bd))


# ---------------------------------------------------------------------------
# Part 2: the circular window test (Protocol 5 `between`)
# ---------------------------------------------------------------------------

def between(a: int, b: int, c: int) -> bool:
    """True if a <= b < c circularly (modulo the sequence space)."""
    return (a <= b < c) or (c < a <= b) or (b < c < a)


# ---------------------------------------------------------------------------
# Part 3: a Go-Back-N data link frame and the endpoint state
# ---------------------------------------------------------------------------

@dataclass
class Frame:
    seq: int          # sequence number, modulo MAX_SEQ + 1
    ack: int          # piggybacked cumulative ack
    info: str         # one network-layer packet


@dataclass
class Sender:
    max_seq: int
    next_frame_to_send: int = 0          # upper window edge
    ack_expected: int = 0                # lower window edge (oldest unacked)
    nbuffered: int = 0                   # frames currently outstanding
    buffer: dict = field(default_factory=dict)   # seq -> info
    timers_running: set = field(default_factory=set)

    def inc(self, x: int) -> int:
        return (x + 1) % (self.max_seq + 1)

    def can_send(self) -> bool:
        return self.nbuffered < self.max_seq


@dataclass
class Receiver:
    max_seq: int
    frame_expected: int = 0              # the only seq it will accept
    delivered: list = field(default_factory=list)

    def inc(self, x: int) -> int:
        return (x + 1) % (self.max_seq + 1)

    def cumulative_ack(self) -> int:
        """The ack value: 'the frame just before the one I'm waiting for'."""
        return (self.frame_expected + self.max_seq) % (self.max_seq + 1)


# ---------------------------------------------------------------------------
# Part 4: the simulation engine
# ---------------------------------------------------------------------------

def run_gbn(packets: list[str], max_seq: int,
            lose_seq: Optional[int] = None) -> list[str]:
    """Run a one-directional Go-Back-N transfer with an optional single loss.

    `lose_seq` is the sequence number whose first transmission is dropped on
    the wire, forcing a timeout and a go-back-N retransmission of the window.
    Returns the list of packets the receiver delivered, in order.
    """
    sender = Sender(max_seq=max_seq)
    receiver = Receiver(max_seq=max_seq)
    in_flight: list[Frame] = []          # frames currently on the wire
    already_lost = lose_seq is None

    def send_data(seq: int) -> None:
        nonlocal already_lost
        ack = receiver.cumulative_ack()
        frame = Frame(seq=seq, ack=ack, info=sender.buffer[seq])
        sender.timers_running.add(seq)
        if (not already_lost) and seq == lose_seq:
            already_lost = True
            print(f"  TX seq={seq:<2} ack={ack}  -> [LOST ON WIRE]")
            return
        print(f"  TX seq={seq:<2} ack={ack}  info={frame.info!r}")
        in_flight.append(frame)

    def deliver_in_flight() -> None:
        """Receiver processes everything on the wire, accepting in order only."""
        while in_flight:
            r = in_flight.pop(0)
            if r.seq == receiver.frame_expected:
                receiver.delivered.append(r.info)
                receiver.frame_expected = receiver.inc(r.seq)
                print(f"     RX accept seq={r.seq}  deliver {r.info!r}; "
                      f"frame_expected -> {receiver.frame_expected}")
            else:
                print(f"     RX discard seq={r.seq}  "
                      f"(out of order; expecting {receiver.frame_expected})")

    def process_ack() -> None:
        """Cumulative ack: retire every outstanding frame the ack covers."""
        ack = receiver.cumulative_ack()
        retired = []
        while between(sender.ack_expected, ack, sender.next_frame_to_send):
            sender.timers_running.discard(sender.ack_expected)
            retired.append(sender.ack_expected)
            sender.nbuffered -= 1
            sender.ack_expected = sender.inc(sender.ack_expected)
        if retired:
            print(f"     <- cumulative ACK {ack}; retired {retired}; "
                  f"ack_expected -> {sender.ack_expected}, "
                  f"nbuffered={sender.nbuffered}")

    def go_back_n() -> None:
        print(f"  !! TIMEOUT on seq={sender.ack_expected}; GO BACK N: "
              f"retransmit window from {sender.ack_expected}")
        sender.next_frame_to_send = sender.ack_expected
        count, sender.nbuffered = sender.nbuffered, 0
        for _ in range(count):
            seq = sender.next_frame_to_send
            sender.nbuffered += 1
            send_data(seq)
            sender.next_frame_to_send = sender.inc(seq)

    queue = list(packets)
    timed_out = False

    while queue or sender.nbuffered > 0:
        # Feed new frames while the window has room and packets remain.
        while sender.can_send() and queue:
            pkt = queue.pop(0)
            sender.buffer[sender.next_frame_to_send] = pkt
            sender.nbuffered += 1
            send_data(sender.next_frame_to_send)
            sender.next_frame_to_send = sender.inc(sender.next_frame_to_send)

        deliver_in_flight()
        process_ack()

        # Stall: window non-empty, nothing in flight, no new packets -> timeout.
        if sender.nbuffered > 0 and not queue and not in_flight:
            if timed_out:
                break                    # avoid infinite loop in pathological case
            timed_out = True
            go_back_n()
            deliver_in_flight()
            process_ack()

    print(f"  RESULT delivered in order: {receiver.delivered}")
    return receiver.delivered


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 68)
    print("Go-Back-N  --  window sizing for the 50-kbps satellite link")
    print("=" * 68)
    bw, owd, fbits = 50_000, 0.250, 1000
    bd = bandwidth_delay_product(bw, owd, fbits)
    w = optimal_window(bd)
    print(f"bandwidth           = {bw / 1000:.0f} kbps")
    print(f"one-way delay       = {owd * 1000:.0f} ms  (RTT = {2 * owd * 1000:.0f} ms)")
    print(f"frame size          = {fbits} bits")
    print(f"bandwidth-delay BD  = {bd:.1f} frames")
    print(f"optimal window w    = 2*BD + 1 = {w} frames")
    print()
    print("Utilization vs window size (upper bound = w / (1 + 2*BD)):")
    for win in (1, 4, 8, 13, 26):
        util = link_utilization(win, bd)
        tag = "  <- stop-and-wait" if win == 1 else (
              "  <- saturates link" if util >= 0.999 else "")
        print(f"   w={win:<3} utilization <= {util * 100:5.1f}%{tag}")

    print()
    print("=" * 68)
    print("between(a, b, c) circular window test  (sequence space 0..7)")
    print("=" * 68)
    for a, b, c in [(0, 3, 7), (6, 7, 2), (6, 1, 2), (6, 5, 2)]:
        print(f"   between({a}, {b}, {c}) = {between(a, b, c)}")

    print()
    print("=" * 68)
    print("Clean run: 6 packets, MAX_SEQ=7, no loss")
    print("=" * 68)
    run_gbn(["P0", "P1", "P2", "P3", "P4", "P5"], max_seq=7)

    print()
    print("=" * 68)
    print("Loss run: frame seq=2 dropped -> timeout -> GO BACK N")
    print("=" * 68)
    run_gbn(["A", "B", "C", "D", "E"], max_seq=7, lose_seq=2)


if __name__ == "__main__":
    main()
