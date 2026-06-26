"""Go-Back-N ARQ simulator (stdlib-only).

Models a sliding-window pipelined ARQ protocol with a sender window of size W
and a receiver window of size 1, exactly the discipline of Tanenbaum &
Wetherall "Protocol 5" (chapter 3.4.2). Sequence numbers occupy an n-bit field
(0 .. 2**n - 1); at most MAX_SEQ = 2**n - 1 frames may be outstanding at once.

The simulator:
  * Builds a frame with seq/ack/info fields and a CRC-style checksum.
  * Drives a discrete-event loop over a lossy one-way channel with a single
    retransmission timer per outstanding frame.
  * Implements the circular `between()` test, piggybacked cumulative ACKs,
    in-order-only acceptance at the receiver, and the go-back-N retransmit
    rule (on timeout, resend *all* unacknowledged frames starting at ack_expected).
  * Computes the link-utilization bound U <= W / (1 + 2*BD) for a given
    bandwidth-delay product, so you can see *why* a large window matters.

Run:  python3 main.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Sequence-number arithmetic on an n-bit field (mod 2**n).
# ---------------------------------------------------------------------------

N_BITS = 3                       # 3-bit sequence field, like the textbook.
MAX_SEQ = (1 << N_BITS) - 1      # 7. At most MAX_SEQ frames outstanding.
MOD = 1 << N_BITS                # 8 distinct sequence numbers.


def inc(seq: int) -> int:
    """Advance a sequence number by one, wrapping at 2**n."""
    return (seq + 1) % MOD


def between(a: int, b: int, c: int) -> bool:
    """Circular test a <= b < c on the sequence-number ring.

    Mirrors the `between()` helper in Protocol 5. True iff b lies on the
    arc from a (inclusive) to c (exclusive) walking clockwise.
    """
    return ((a <= b < c) or (c < a <= b) or (b < c < a))


# ---------------------------------------------------------------------------
# Frame and a tiny CRC-style checksum.
# ---------------------------------------------------------------------------

@dataclass
class Frame:
    seq: int            # sequence number of THIS frame's payload
    ack: int            # piggybacked cumulative ACK: "all through ack-1 ok"
    info: bytes         # payload handed up by the network layer
    cksum: int = 0      # 8-bit checksum over seq/ack/info

    def compute_cksum(self) -> int:
        s = self.seq * 31 + self.ack * 17
        for byte in self.info:
            s = (s * 7 + byte) & 0xFFFF
        return s & 0xFF

    def seal(self) -> "Frame":
        self.cksum = self.compute_cksum()
        return self

    def is_valid(self) -> bool:
        return self.cksum == self.compute_cksum()


# ---------------------------------------------------------------------------
# Sender (Go-Back-N, window = MAX_SEQ, single cumulative ACK expected).
# ---------------------------------------------------------------------------

@dataclass
class GoBackNSender:
    window: int                       # W, max outstanding frames (<= MAX_SEQ)
    buffer: list[bytes] = field(default_factory=list)  # packets awaiting send
    outstanding: dict[int, bytes] = field(default_factory=dict)  # seq -> payload
    next_frame_to_send: int = 0       # upper window edge
    ack_expected: int = 0             # lower window edge (oldest unacked)
    frame_expected: int = 0           # receiver side, used for piggyback ACK
    delivered: list[int] = field(default_factory=list)  # seqs ACKed so far

    def can_send(self) -> bool:
        in_flight = (self.next_frame_to_send - self.ack_expected) % MOD
        return in_flight < self.window and bool(self.buffer)

    def send_one(self) -> Frame:
        payload = self.buffer.pop(0)
        seq = self.next_frame_to_send
        self.outstanding[seq] = payload
        self.next_frame_to_send = inc(seq)
        # Piggyback the ACK for the last in-order frame we received.
        ack = (self.frame_expected + MAX_SEQ) % MOD
        return Frame(seq, ack, payload).seal()

    def receive_ack(self, frame: Frame) -> list[int]:
        """Process a piggybacked cumulative ACK; return seqs newly ACKed."""
        newly = []
        while between(self.ack_expected, frame.ack, self.next_frame_to_send):
            self.outstanding.pop(self.ack_expected, None)
            self.delivered.append(self.ack_expected)
            newly.append(self.ack_expected)
            self.ack_expected = inc(self.ack_expected)
        # Also accept data the peer sent us (in-order receiver).
        if frame.seq == self.frame_expected and frame.is_valid():
            self.frame_expected = inc(self.frame_expected)
        return newly

    def timeout(self) -> list[Frame]:
        """Go-Back-N rule: resend EVERY outstanding frame from ack_expected."""
        resent = []
        seq = self.ack_expected
        # Walk the outstanding window in order; the receiver discards
        # everything after a gap anyway, so resending in order is mandatory.
        while seq != self.next_frame_to_send:
            payload = self.outstanding.get(seq, b"")
            ack = (self.frame_expected + MAX_SEQ) % MOD
            resent.append(Frame(seq, ack, payload).seal())
            seq = inc(seq)
        return resent


# ---------------------------------------------------------------------------
# Receiver (window = 1: accept ONLY the next expected frame, in order).
# ---------------------------------------------------------------------------

@dataclass
class GoBackNReceiver:
    frame_expected: int = 0
    delivered: list[bytes] = field(default_factory=list)

    def receive(self, frame: Frame) -> tuple[bool, Frame]:
        """Return (accepted?, ack_frame_to_send).

        Discard out-of-order or damaged frames, but still ACK the last
        in-order frame we hold (cumulative). This is the heart of GBN:
        a receive window of 1 means any frame != expected is dropped.
        """
        accepted = False
        if frame.is_valid() and frame.seq == self.frame_expected:
            self.delivered.append(frame.info)
            self.frame_expected = inc(self.frame_expected)
            accepted = True
        # ACK = next expected (i.e. "everything before this is fine").
        ack = (self.frame_expected + MAX_SEQ) % MOD
        # Piggyback a dummy data seq so it looks like a real frame.
        return accepted, Frame(self.frame_expected, ack, b"").seal()


# ---------------------------------------------------------------------------
# Discrete-event simulation over a lossy channel.
# ---------------------------------------------------------------------------

def simulate(packets: list[bytes], loss_prob: float, seed: int = 7) -> dict:
    random.seed(seed)
    sender = GoBackNSender(window=MAX_SEQ, buffer=list(packets))
    receiver = GoBackNReceiver()
    log: list[str] = []
    ticks = 0
    max_ticks = 2000
    timeout_every = 6   # timer ticks before a frame is presumed lost

    last_send_tick: dict[int, int] = {}
    while sender.buffer or sender.outstanding:
        if ticks > max_ticks:
            log.append("ABORT: exceeded tick budget")
            break
        # (1) Send while the window has room.
        while sender.can_send():
            f = sender.send_one()
            last_send_tick[f.seq] = ticks
            log.append(f"tx frame seq={f.seq} ack={f.ack}")
        # (2) Channel: deliver a random outstanding frame, maybe corrupt/lose.
        if sender.outstanding:
            seq = random.choice(list(sender.outstanding))
            f = Frame(seq, (sender.frame_expected + MAX_SEQ) % MOD,
                      sender.outstanding[seq]).seal()
            roll = random.random()
            if roll < loss_prob:
                log.append(f"   ! frame seq={seq} LOST in channel")
            elif roll < loss_prob + 0.05:
                f.ack = (f.ack + 1) % MOD  # corrupt the ack field
                accepted, ack = receiver.receive(f)
                log.append(f"   x frame seq={seq} CORRUPT -> drop")
                _ = sender.receive_ack(ack)
            else:
                accepted, ack = receiver.receive(f)
                tag = "ACCEPT" if accepted else "DROP (out of order)"
                log.append(f"   rx frame seq={seq} -> {tag}")
                acked = sender.receive_ack(ack)
                if acked:
                    log.append(f"   ack advances: {acked}")
        # (3) Timers: if the oldest outstanding has aged out, go back N.
        if sender.outstanding:
            oldest = min(sender.outstanding,
                         key=lambda s: last_send_tick.get(s, 0))
            if ticks - last_send_tick.get(oldest, ticks) >= timeout_every:
                log.append(f"*** TIMEOUT seq={oldest}: go back N, resend "
                           f"{len(sender.outstanding)} frames")
                for rf in sender.timeout():
                    last_send_tick[rf.seq] = ticks
                    log.append(f"tx (resend) seq={rf.seq}")
        ticks += 1

    return {
        "log": log,
        "ticks": ticks,
        "delivered": receiver.delivered,
        "expected": list(packets),
        "ok": receiver.delivered == list(packets),
    }


# ---------------------------------------------------------------------------
# Link-utilization bound: U <= W / (1 + 2*BD).
# ---------------------------------------------------------------------------

def utilization(window: int, bandwidth_bps: int, one_way_delay_s: float,
                frame_bits: int) -> float:
    bd = (bandwidth_bps * one_way_delay_s) / frame_bits  # frames in flight
    return min(1.0, window / (1 + 2 * bd))


def main() -> None:
    print("=" * 64)
    print("Go-Back-N ARQ -- Protocol 5 simulator")
    print(f"Sequence field: {N_BITS} bits  (0..{MAX_SEQ}),  "
          f"max outstanding = {MAX_SEQ}")
    print("=" * 64)

    # --- Worked numeric example from the textbook (50 kbps satellite) ---
    bw, delay, frame_bits = 50_000, 0.250, 1000
    bd = bw * delay / frame_bits
    print("\n[Satellite link] 50 kbps, 250 ms one-way, 1000-bit frames")
    print(f"  bandwidth-delay product BD = {bd:.1f} frames")
    print(f"  recommended window 2BD+1   = {2*bd+1:.1f} frames")
    for w in (1, 7, 26):
        u = utilization(w, bw, delay, frame_bits)
        print(f"  W={w:<3} -> utilization <= {u*100:5.1f}%")

    # --- between() sanity: the circular ACK test ---
    print("\n[between(a,b,c)] circular test on a 0..7 ring")
    print(f"  between(0, 5, 7) = {between(0,5,7)}   (5 in [0,7))")
    print(f"  between(6, 0, 2) = {between(6,0,2)}   (0 wraps past 7)")
    print(f"  between(3, 7, 1) = {between(3,7,1)}   (7 wraps past 0)")

    # --- Run a lossy simulation ---
    print("\n[Simulation] 8 packets, loss prob 0.20, GBN window 7")
    pkts = [bytes([i]) for i in range(8)]
    result = simulate(pkts, loss_prob=0.20, seed=11)
    for line in result["log"][:40]:
        print("  " + line)
    if len(result["log"]) > 40:
        print(f"  ... ({len(result['log'])-40} more events)")
    print(f"\n  ticks used      : {result['ticks']}")
    print(f"  receiver got    : {list(p[0] for p in result['delivered'])}")
    print(f"  expected        : {list(p[0] for p in result['expected'])}")
    print(f"  correct order?  : {result['ok']}")

    # --- Show the go-back-N retransmit set explicitly ---
    print("\n[Timeout behaviour] sender has ack_expected=2, "
          "next_frame_to_send=6")
    s = GoBackNSender(window=MAX_SEQ)
    s.ack_expected = 2
    s.next_frame_to_send = 6
    for seq in range(2, 6):
        s.outstanding[seq] = bytes([seq])
    resent = s.timeout()
    print(f"  resend seqs     : {[f.seq for f in resent]}  "
          f"(must be the full window 2,3,4,5)")


if __name__ == "__main__":
    main()
