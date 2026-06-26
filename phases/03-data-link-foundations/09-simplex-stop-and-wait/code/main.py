"""Simplex stop-and-wait protocol simulator (Tanenbaum & Wetherall Sec. 3.3).

A discrete-event, stdlib-only implementation of the three elementary data-link
protocols:

  * Protocol 1 (Utopia)            -- error-free, no flow control
  * Protocol 2 (stop-and-wait)     -- error-free, ACK-based flow control
  * Protocol 3 (stop-and-wait, ARQ)-- noisy channel, 1-bit seq + timer

The simulator is intentionally verbose: every state transition prints a line so
the trace can be read as evidence that the 1-bit sequence number actually closes
the duplicate-delivery hole that a naive timer-only scheme leaves open.

Run:  python3 main.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List, Optional

MAX_PKT = 1024


class FrameKind(Enum):
    DATA = "data"
    ACK = "ack"
    NAK = "nak"


@dataclass
class Frame:
    kind: FrameKind
    seq: int = 0
    ack: int = 0
    info: bytes = b""
    damaged: bool = False  # set by a noisy link after CRC "failure"

    def __repr__(self) -> str:
        if self.kind is FrameKind.DATA:
            tag = "DAMAGED" if self.damaged else "ok"
            return f"DATA(seq={self.seq},info={self.info!r},{tag})"
        return f"{self.kind.name}(seq={self.seq})"


@dataclass
class Link:
    """A bidirectional, lossy, damaging channel between two data-link entities."""

    loss_prob: float = 0.0
    damage_prob: float = 0.0
    _rng: random.Random = field(default_factory=random.Random)

    def send(self, frame: Frame) -> Optional[Frame]:
        """Deliver a frame, or None if lost. May flip the `damaged` flag."""
        if self._rng.random() < self.loss_prob:
            return None  # entire frame lost in the channel
        out = Frame(frame.kind, frame.seq, frame.ack, frame.info)
        if self._rng.random() < self.damage_prob:
            out.damaged = True  # CRC will fail at the receiver
        return out


@dataclass
class PacketLog:
    """Records every packet the receiver hands to its network layer."""

    delivered: List[bytes] = field(default_factory=list)

    def deliver(self, info: bytes) -> None:
        self.delivered.append(info)


class StopAndWaitSimulator:
    """Runs Protocols 2 and 3 against a shared clock and injectable link.

    `use_seq` toggles the 1-bit sequence-number discipline of Protocol 3.
    With it off, the simulator reproduces the textbook's duplicate-delivery
    failure on a lost ACK.
    """

    def __init__(
        self,
        packets: List[bytes],
        link: Link,
        use_seq: bool,
        t_frame_ms: float = 1.0,
        t_prop_ms: float = 2.0,
        t_ack_ms: float = 0.5,
        timeout_ms: float = 8.0,
        trace: Callable[[str], None] = print,
    ) -> None:
        self.packets = list(packets)
        self.link = link
        self.use_seq = use_seq
        self.t_frame = t_frame_ms
        self.t_prop = t_prop_ms
        self.t_ack = t_ack_ms
        self.timeout = timeout_ms
        self.trace = trace
        self.clock = 0.0
        self.log = PacketLog()
        self._sent_bytes = 0
        self._busy_time = 0.0

    # ---- helpers ---------------------------------------------------------
    def _say(self, who: str, msg: str) -> None:
        self.trace(f"[t={self.clock:6.1f}ms] {who}: {msg}")

    def _max_seq(self) -> int:
        return 1 if self.use_seq else 0

    # ---- the three scenarios --------------------------------------------
    def run_utopia(self) -> None:
        """Protocol 1: pump frames as fast as possible, no ACK, no errors."""
        self.trace("\n=== Protocol 1 (Utopia) ===")
        for i, pkt in enumerate(self.packets):
            self.clock += self.t_frame + self.t_prop
            self._say("SENDER", f"sent frame info={pkt!r}")
            self._say("RECEIVER", f"delivered info={pkt!r}")
            self.log.deliver(pkt)
            self._sent_bytes += len(pkt)
            self._busy_time += self.t_frame

    def run_stop_and_wait(self) -> None:
        """Protocol 2 or 3: send one frame, wait for ACK, resend on timeout."""
        title = "Protocol 3 (noisy, 1-bit seq + timer)" if self.use_seq \
            else "Protocol 2/naive-timer (no seq)"
        self.trace(f"\n=== {title} ===")
        max_seq = self._max_seq()
        next_frame_to_send = 0
        frame_expected = 0
        idx = 0
        attempts = 0
        max_total_attempts = 20 * (len(self.packets) + 1)

        while idx < len(self.packets) and attempts < max_total_attempts:
            attempts += 1
            pkt = self.packets[idx]
            frame = Frame(FrameKind.DATA, seq=next_frame_to_send, info=pkt)
            self.clock += self.t_frame
            self._busy_time += self.t_frame
            self._sent_bytes += len(pkt)
            self._say("SENDER", f"sent {frame}")

            delivered = self.link.send(frame)
            self.clock += self.t_prop
            if delivered is None:
                self._say("LINK", "data frame LOST")
            else:
                self._say("LINK", f"delivered {delivered}")

            # Receiver side. NOTE: the receiver delivering a packet does NOT
            # advance the sender's packet pointer -- the sender only learns of
            # acceptance when the ACK arrives. Keeping idx unchanged here is
            # what makes a timeout resend the SAME packet, which is the whole
            # point of the lost-ACK scenario.
            ack_to_send: Optional[Frame] = None
            if delivered is not None and not delivered.damaged:
                if not self.use_seq or delivered.seq == frame_expected:
                    self._say("RECEIVER",
                              f"accepted seq={delivered.seq}, "
                              f"deliver info={delivered.info!r}")
                    self.log.deliver(delivered.info)
                    if self.use_seq:
                        frame_expected ^= 1
                    ack_to_send = Frame(FrameKind.ACK, seq=delivered.seq)
                else:
                    self._say("RECEIVER",
                              f"discarded duplicate seq={delivered.seq} "
                              f"(expected {frame_expected}); re-ACK")
                    ack_to_send = Frame(FrameKind.ACK, seq=delivered.seq ^ 1)
            elif delivered is not None and delivered.damaged:
                self._say("RECEIVER", "cksum_err: damaged frame dropped, "
                          "no ACK sent")
            else:
                self._say("RECEIVER", "nothing received, no ACK")

            if ack_to_send is None:
                # Wait out the timeout, then resend the same frame/seq.
                self.clock += self.timeout
                self._say("SENDER", "timeout -> will resend same seq")
                continue

            # ACK travels back
            self.clock += self.t_ack + self.t_prop
            ack = self.link.send(ack_to_send)
            if ack is None:
                self._say("LINK", "ACK LOST")
                self.clock += self.timeout
                self._say("SENDER", "timeout (ACK lost) -> resend same seq")
                continue
            self._say("LINK", f"delivered {ack}")
            # ACK arrived: the sender finally knows the packet was accepted.
            idx += 1
            if self.use_seq:
                next_frame_to_send ^= 1
            self._say("SENDER", f"ACK received, advance to "
                      f"next_frame_to_send={next_frame_to_send}")

        if attempts >= max_total_attempts:
            self._say("SYSTEM", "ABORT: exceeded attempt budget")

    # ---- reporting -------------------------------------------------------
    def utilization(self) -> float:
        if self.clock <= 0:
            return 0.0
        return self._busy_time / self.clock

    def report(self) -> None:
        self.trace("\n--- summary ---")
        self.trace(f"delivered packets: {self.log.delivered}")
        self.trace(f"duplicates: "
                   f"{len(self.log.delivered) - len(set(self.log.delivered))}")
        self.trace(f"link utilization U = {self.utilization():.4f}")


class LostFirstAckLink(Link):
    """Loses the first ACK only, to trigger the textbook failure scenario."""

    def __init__(self, seed: int = 0) -> None:
        super().__init__(loss_prob=0.0, damage_prob=0.0,
                         _rng=random.Random(seed))
        self._ack_count = 0

    def send(self, frame: Frame) -> Optional[Frame]:
        if frame.kind is FrameKind.ACK and self._ack_count == 0:
            self._ack_count += 1
            return None  # first ACK vanishes
        if frame.kind is FrameKind.ACK:
            self._ack_count += 1
        return super().send(frame)


class DamageFirstDataLink(Link):
    """Damages the first data frame so the receiver reports cksum_err."""

    def __init__(self, seed: int = 0) -> None:
        super().__init__(loss_prob=0.0, damage_prob=0.0,
                         _rng=random.Random(seed))
        self._data_count = 0

    def send(self, frame: Frame) -> Optional[Frame]:
        if frame.kind is FrameKind.DATA and self._data_count == 0:
            self._data_count += 1
            out = Frame(frame.kind, frame.seq, frame.ack, frame.info)
            out.damaged = True
            return out
        if frame.kind is FrameKind.DATA:
            self._data_count += 1
        return super().send(frame)


def scenario_clean() -> None:
    sim = StopAndWaitSimulator(
        packets=[b"P0", b"P1", b"P2"],
        link=Link(loss_prob=0.0, damage_prob=0.0, _rng=random.Random(1)),
        use_seq=True,
        t_prop_ms=2.0,
        trace=print,
    )
    sim.run_stop_and_wait()
    sim.report()


def scenario_lost_ack_no_seq() -> None:
    """Naive timer-only scheme: a lost ACK silently duplicates a packet."""
    sim = StopAndWaitSimulator(
        packets=[b"P0", b"P1"],
        link=LostFirstAckLink(),
        use_seq=False,  # the bug
        t_prop_ms=2.0,
        trace=print,
    )
    sim.run_stop_and_wait()
    sim.report()


def scenario_lost_ack_with_seq() -> None:
    """Protocol 3: the same lost ACK, but the 1-bit seq discards the dup."""
    sim = StopAndWaitSimulator(
        packets=[b"P0", b"P1"],
        link=LostFirstAckLink(),
        use_seq=True,  # the fix
        t_prop_ms=2.0,
        trace=print,
    )
    sim.run_stop_and_wait()
    sim.report()


def scenario_damaged_frame() -> None:
    """A data frame is damaged; receiver reports cksum_err; sender resends."""
    sim = StopAndWaitSimulator(
        packets=[b"P0", b"P1"],
        link=DamageFirstDataLink(),
        use_seq=True,
        t_prop_ms=2.0,
        trace=print,
    )
    sim.run_stop_and_wait()
    sim.report()


def scenario_satellite_utilization() -> None:
    """Long-fat pipe: show stop-and-wait utilization collapse (~0.1%)."""
    sim = StopAndWaitSimulator(
        packets=[b"P0", b"P1"],
        link=Link(loss_prob=0.0, damage_prob=0.0, _rng=random.Random(0)),
        use_seq=True,
        t_frame_ms=1.0,    # 1000 bits @ 1 Mbit/s
        t_prop_ms=500.0,   # GEO satellite one-way
        t_ack_ms=0.04,     # 40-bit ACK @ 1 Mbit/s
        timeout_ms=1100.0,
        trace=print,
    )
    sim.run_stop_and_wait()
    sim.report()
    expected = 1.0 / (1.0 + 2 * 500.0 + 0.04)
    print(f"closed-form U = T_frame/(T_frame+2*T_prop+T_ack) "
          f"= {expected:.6f}")


def main() -> None:
    print("=" * 70)
    print(" Simplex Stop-and-Wait Protocol Simulator (Tanenbaum 3.3) ")
    print("=" * 70)

    print("\n############ 1. Utopia (Protocol 1) ############")
    sim = StopAndWaitSimulator(
        packets=[b"P0", b"P1", b"P2"],
        link=Link(_rng=random.Random(0)),
        use_seq=False,
        trace=print,
    )
    sim.run_utopia()
    sim.report()

    print("\n############ 2. Clean channel, Protocol 3 ############")
    scenario_clean()

    print("\n############ 3. Lost ACK WITHOUT seq (the bug) ############")
    scenario_lost_ack_no_seq()

    print("\n############ 4. Lost ACK WITH 1-bit seq (the fix) ############")
    scenario_lost_ack_with_seq()

    print("\n############ 5. Damaged data frame, Protocol 3 ############")
    scenario_damaged_frame()

    print("\n############ 6. Satellite link utilization ############")
    scenario_satellite_utilization()


if __name__ == "__main__":
    main()
