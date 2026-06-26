"""One-bit sliding window protocol (Tanenbaum's Protocol 4) simulator.

A faithful, stdlib-only port of the bidirectional 1-bit sliding window protocol
from Computer Networks (Tanenbaum & Wetherall, 6th ed., section 3.4.1).
Each frame carries (seq, ack, info); both endpoints maintain two 1-bit state
variables -- next_frame_to_send (sender) and frame_expected (receiver) -- and
exchange frames over a lossy, delayed channel. The simulator reproduces the
textbook's Figure 3-17 scenarios (normal and simultaneous start) and a lossy
mode with timeouts, and prints a utilization calculation.

Run:
    python3 main.py --mode normal
    python3 main.py --mode simultaneous
    python3 main.py --mode lossy --loss 0.2 --seed 7
    python3 main.py --util 50000 0.25 1000
"""

from __future__ import annotations

import argparse
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


# Sequence/ack space is {0,1} for a window of 1.
MAX_SEQ = 1


def inc(bit: int) -> int:
    """Alternate a 1-bit sequence number: 0 -> 1 -> 0."""
    return 1 - bit


class Event(Enum):
    FRAME_ARRIVAL = "frame_arrival"
    CKSUM_ERR = "cksum_err"
    TIMEOUT = "timeout"
    IDLE = "idle"


@dataclass
class Frame:
    seq: int            # sequence number of the data in this frame (0 or 1)
    ack: int            # piggybacked ack: seq of last correctly received frame
    info: str           # payload, e.g. "A0"; "EMPTY" for bare acks
    sender: str         # who sent it ("A" or "B"), for tracing
    damaged: bool = False

    def __repr__(self) -> str:
        tag = "!" if self.damaged else ""
        return f"({self.seq},{self.ack},{self.info}){tag}"


@dataclass
class Endpoint:
    name: str
    nfs: int = 0                       # next_frame_to_send
    fe: int = 0                        # frame_expected
    out_queue: List[str] = field(default_factory=list)
    delivered: List[str] = field(default_factory=list)
    timer_active: bool = False
    timer: int = 0
    last_sent: Optional[Frame] = None

    def fetch_packet(self) -> str:
        return self.out_queue.pop(0) if self.out_queue else "EMPTY"

    def send_initial(self) -> Frame:
        """Bootstrapping transmit done once before the main loop."""
        pkt = self.fetch_packet()
        f = Frame(seq=self.nfs, ack=inc(self.fe), info=pkt, sender=self.name)
        self.last_sent = f
        self.timer_active = True
        self.timer = 0
        return f


class Channel:
    """In-flight frames with one-way propagation delay, loss, and corruption."""

    def __init__(self, delay: int, loss: float, corrupt: float,
                 rng: random.Random) -> None:
        self.delay = delay
        self.loss = loss
        self.corrupt = corrupt
        self.rng = rng
        self.in_flight: List[tuple] = []  # (arrival_time, frame)

    def put(self, f: Frame, now: int) -> None:
        if self.rng.random() < self.loss:
            return  # silently drop
        if self.rng.random() < self.corrupt:
            f = Frame(seq=f.seq, ack=f.ack, info=f.info, sender=f.sender,
                      damaged=True)
        self.in_flight.append((now + self.delay, f))

    def due(self, now: int) -> List[Frame]:
        ready, rest = [], []
        for t, f in self.in_flight:
            (ready if t <= now else rest).append((t, f))
        self.in_flight = rest
        return [f for _, f in ready]


def make_endpoints(a_packets: List[str], b_packets: List[str]) -> tuple:
    return (Endpoint("A", out_queue=list(a_packets)),
            Endpoint("B", out_queue=list(b_packets)))


def transmit(ep: Endpoint) -> Frame:
    """Re-emit current frame (the Protocol 4 main-loop tail)."""
    info = ep.last_sent.info if ep.last_sent else ep.fetch_packet()
    f = Frame(seq=ep.nfs, ack=inc(ep.fe), info=info, sender=ep.name)
    ep.last_sent = f
    ep.timer_active = True
    ep.timer = 0
    return f


def handle_arrival(ep: Endpoint, r: Frame, log: List[str]) -> None:
    if r.damaged:
        log.append(f"  {ep.name}: CKSUM_ERR discards {r}")
        return
    if r.seq == ep.fe:
        log.append(f"  {ep.name}: DELIVER {r.info}*  (fe {ep.fe}->"
                   f"{inc(ep.fe)})")
        ep.delivered.append(r.info)
        ep.fe = inc(ep.fe)
    else:
        log.append(f"  {ep.name}: DUPLICATE {r} (expected {ep.fe}, drop)")
    if r.ack == ep.nfs:
        log.append(f"  {ep.name}: ACK matches nfs {ep.nfs}, advance "
                   f"(nfs {ep.nfs}->{inc(ep.nfs)})")
        ep.nfs = inc(ep.nfs)
        if ep.out_queue:
            ep.last_sent = Frame(seq=ep.nfs, ack=inc(ep.fe),
                                 info=ep.fetch_packet(), sender=ep.name)
        ep.timer_active = False
    else:
        log.append(f"  {ep.name}: ack {r.ack} != nfs {ep.nfs}, no advance")


def run(steps: int, mode: str, loss: float, corrupt: float, delay: int,
        timeout: int, seed: int) -> List[str]:
    rng = random.Random(seed)
    A, B = make_endpoints(["A0", "A1", "A2", "A3", "A4"],
                          ["B0", "B1", "B2", "B3", "B4"])
    ch = Channel(delay=delay, loss=loss, corrupt=corrupt, rng=rng)
    log: List[str] = []

    if mode == "simultaneous":
        ch.put(A.send_initial(), 0)
        ch.put(B.send_initial(), 0)
    elif mode in ("normal", "lossy"):
        ch.put(A.send_initial(), 0)
    else:
        raise ValueError(f"unknown mode {mode}")

    for t in range(steps):
        for r in ch.due(t):
            target = B if r.sender == "A" else A
            log.append(f"t={t:02d} {r.sender}->{target.name} {r}")
            handle_arrival(target, r, log)
            for ep in (A, B):
                if ep.last_sent is not None:
                    ch.put(transmit(ep), t)

        for ep in (A, B):
            if ep.timer_active:
                ep.timer += 1
                if ep.timer >= timeout:
                    log.append(f"t={t:02d} {ep.name}: TIMEOUT, retransmit "
                               f"{ep.last_sent}")
                    ep.timer = 0
                    ch.put(transmit(ep), t)

    log.append("")
    log.append(f"A delivered: {A.delivered}")
    log.append(f"B delivered: {B.delivered}")
    for ep in (A, B):
        dups = {p for p in ep.delivered if ep.delivered.count(p) > 1}
        if dups:
            log.append(f"INVARIANT VIOLATION on {ep.name}: dup {dups}")
    return log


def utilization(bps: int, prop_s: float, frame_bits: int) -> float:
    t_frame = frame_bits / bps
    return t_frame / (t_frame + 2 * prop_s)


def main() -> None:
    p = argparse.ArgumentParser(description="Protocol 4 simulator")
    p.add_argument("--mode", choices=["normal", "simultaneous", "lossy"],
                   default="normal")
    p.add_argument("--steps", type=int, default=20)
    p.add_argument("--loss", type=float, default=0.1)
    p.add_argument("--corrupt", type=float, default=0.05)
    p.add_argument("--delay", type=int, default=1,
                   help="propagation delay in ticks")
    p.add_argument("--timeout", type=int, default=4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--util", nargs=3, metavar=("BPS", "PROP_S", "BITS"),
                   help="print utilization and exit")
    args = p.parse_args()

    if args.util:
        bps, prop, bits = int(args.util[0]), float(args.util[1]), int(args.util[2])
        u = utilization(bps, prop, bits)
        print(f"bandwidth={bps} bps  prop={prop}s  frame={bits} bits")
        print(f"t_frame={bits/bps*1000:.2f} ms  U={u:.4f}  "
              f"({u*100:.2f}% of link used, {(1-u)*100:.2f}% idle)")
        return

    print(f"=== Protocol 4, mode={args.mode}, loss={args.loss}, "
          f"corrupt={args.corrupt}, delay={args.delay}, "
          f"timeout={args.timeout} ===")
    log = run(args.steps, args.mode, args.loss, args.corrupt,
              args.delay, args.timeout, args.seed)
    for line in log:
        print(line)


if __name__ == "__main__":
    main()
