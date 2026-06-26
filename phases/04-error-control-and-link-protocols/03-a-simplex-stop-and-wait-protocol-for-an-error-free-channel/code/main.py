"""Simplex Stop-and-Wait protocol simulator (Tanenbaum Protocol 2).

Models flow control over an *error-free* channel: the sender transmits one
DATA frame, then blocks until a content-free ACK frame returns before fetching
the next packet. This enforces strict DATA/ACK alternation and caps throughput
at one frame per round-trip time (RTT).

The simulator is a small discrete-event engine over a virtual time axis (all
times in milliseconds). It prints:
  * a timing ledger showing each DATA departure and the idle gap before the
    next frame can start (proving the sender is blocked for 2 * Tprop), and
  * an efficiency report:  U = Tframe / (Tframe + 2*Tprop + Tack).

Set lossy=True to drop a chosen ACK and watch the sender deadlock -- concrete
evidence for why an error-free channel needs no seq/checksum but a real channel
needs timers and sequence numbers (Protocol 3).

Stdlib only. Runs under: python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Frame:
    """A link-layer frame.

    On an error-free channel, DATA frames need only the network-layer packet
    in `info`; there is no `seq` and no `checksum` field, because nothing can
    be lost, reordered, or corrupted by assumption. ACK frames carry nothing --
    their *arrival* is the entire signal.
    """

    kind: str  # "DATA" or "ACK"
    info: Optional[str] = None  # network-layer packet, DATA frames only

    def size_bits(self) -> int:
        # Modeled: tiny header + payload. ACKs are header-only.
        header_bits = 48
        payload_bits = len(self.info.encode()) * 8 if self.info else 0
        return header_bits + payload_bits


@dataclass
class Channel:
    """A one-way propagation delay, optionally lossy for a single frame."""

    prop_ms: float
    lossy: bool = False
    drop_ack_at_frame: int = -1  # 1-based index of the ACK to drop, -1 = none
    _ack_count: int = field(default=0, init=False)

    def deliver_data(self) -> float:
        """Return the time (ms) for a DATA frame to propagate to the receiver."""
        return self.prop_ms

    def deliver_ack(self, frame_index: int) -> Optional[float]:
        """Return propagation time for the ACK, or None if it is dropped."""
        self._ack_count += 1
        if self.lossy and frame_index == self.drop_ack_at_frame:
            return None
        return self.prop_ms


@dataclass
class LedgerEntry:
    frame_index: int
    data_depart_ms: float
    data_arrive_ms: float
    ack_depart_ms: float
    ack_arrive_ms: Optional[float]  # None => lost
    idle_gap_ms: float


class StopAndWaitSimulator:
    """Discrete-event simulation of Protocol 2 over one point-to-point link."""

    def __init__(
        self,
        line_rate_bps: int,
        prop_ms: float,
        n_frames: int,
        payload: str = "PKT",
        lossy: bool = False,
        drop_ack_at_frame: int = -1,
        receiver_proc_ms: float = 0.0,
    ) -> None:
        self.line_rate_bps = line_rate_bps
        self.n_frames = n_frames
        self.payload = payload
        self.receiver_proc_ms = receiver_proc_ms
        self.channel = Channel(
            prop_ms=prop_ms, lossy=lossy, drop_ack_at_frame=drop_ack_at_frame
        )
        self.ledger: list[LedgerEntry] = []
        self.deadlocked = False
        self.deadlock_reason = ""

    def _tx_time_ms(self, frame: Frame) -> float:
        return 1000.0 * frame.size_bits() / self.line_rate_bps

    def run(self) -> None:
        """Run the strict DATA/ACK alternation until done or deadlocked."""
        prev_ack_in = 0.0  # time the previous frame's ACK arrived (sender unblock)
        for i in range(1, self.n_frames + 1):
            # Sender: from_network_layer -> build frame -> to_physical_layer.
            # The sender cannot start frame i until the ACK for i-1 arrived.
            data = Frame(kind="DATA", info=f"{self.payload}{i}")
            data_tx = self._tx_time_ms(data)
            data_depart = prev_ack_in
            idle_gap = data_depart - self._link_free_after_prev()

            # DATA propagates to the receiver.
            data_arrive = data_depart + data_tx + self.channel.deliver_data()

            # Receiver: from_physical_layer -> to_network_layer -> send dummy ACK.
            ack = Frame(kind="ACK")
            ack_tx = self._tx_time_ms(ack)
            ack_depart = data_arrive + self.receiver_proc_ms
            ack_prop = self.channel.deliver_ack(i)

            if ack_prop is None:
                # Lost ACK: sender blocks forever in wait_for_event (no timer).
                self.ledger.append(
                    LedgerEntry(i, data_depart, data_arrive, ack_depart, None, idle_gap)
                )
                self.deadlocked = True
                self.deadlock_reason = (
                    f"ACK for frame {i} was lost; sender blocked in "
                    f"wait_for_event with no timer -> permanent deadlock."
                )
                self._last_link_free = data_depart + data_tx
                return

            ack_arrive = ack_depart + ack_tx + ack_prop
            self.ledger.append(
                LedgerEntry(i, data_depart, data_arrive, ack_depart, ack_arrive, idle_gap)
            )
            self._last_link_free = data_depart + data_tx
            prev_ack_in = ack_arrive

    def _link_free_after_prev(self) -> float:
        return getattr(self, "_last_link_free", 0.0)

    # ---- reporting -------------------------------------------------------

    def efficiency(self) -> float:
        data = Frame(kind="DATA", info=f"{self.payload}1")
        ack = Frame(kind="ACK")
        t_frame = self._tx_time_ms(data)
        t_ack = self._tx_time_ms(ack)
        two_prop = 2.0 * self.channel.prop_ms
        return t_frame / (t_frame + two_prop + t_ack + self.receiver_proc_ms)

    def print_report(self) -> None:
        data = Frame(kind="DATA", info=f"{self.payload}1")
        ack = Frame(kind="ACK")
        print("=" * 68)
        print("STOP-AND-WAIT SIMULATION (Protocol 2, error-free channel)")
        print("=" * 68)
        print(f"line rate          : {self.line_rate_bps:,} bps")
        print(f"one-way prop delay : {self.channel.prop_ms:.3f} ms")
        print(
            f"DATA frame size    : {data.size_bits()} bits "
            f"(Tframe = {self._tx_time_ms(data):.4f} ms)"
        )
        print(
            f"ACK frame size     : {ack.size_bits()} bits "
            f"(Tack = {self._tx_time_ms(ack):.4f} ms)"
        )
        print(f"frames to send     : {self.n_frames}")
        print("-" * 68)
        print(
            f"{'frame':>5} {'DATA out':>10} {'DATA in':>10} "
            f"{'ACK out':>10} {'ACK in':>10} {'idle gap':>10}"
        )
        for e in self.ledger:
            ack_in = (
                f"{e.ack_arrive_ms:.3f}" if e.ack_arrive_ms is not None else "LOST"
            )
            print(
                f"{e.frame_index:>5} {e.data_depart_ms:>10.3f} "
                f"{e.data_arrive_ms:>10.3f} {e.ack_depart_ms:>10.3f} "
                f"{ack_in:>10} {e.idle_gap_ms:>10.3f}"
            )
        print("-" * 68)
        if self.deadlocked:
            print(f"DEADLOCK: {self.deadlock_reason}")
        else:
            u = self.efficiency()
            print(
                f"line efficiency U  : {u:.6f}  ({u * 100:.4f}% of link time "
                f"carries useful data)"
            )
            print(
                f"interpretation     : link idles ~{(1 - u) * 100:.2f}% of the "
                f"time waiting on RTT -> motivates sliding windows."
            )
        print("=" * 68)
        print()


def main() -> None:
    # Demo 1: a healthy LAN-ish link -- decent but not full efficiency.
    print("DEMO 1: short terrestrial link (1 Mbps, 1 ms prop)")
    sim1 = StopAndWaitSimulator(
        line_rate_bps=1_000_000, prop_ms=1.0, n_frames=4, payload="LOG"
    )
    sim1.run()
    sim1.print_report()

    # Demo 2: a geostationary satellite link -- catastrophic efficiency.
    print("DEMO 2: geostationary satellite link (1 Mbps, 270 ms prop)")
    sim2 = StopAndWaitSimulator(
        line_rate_bps=1_000_000, prop_ms=270.0, n_frames=3, payload="LOG"
    )
    sim2.run()
    sim2.print_report()

    # Demo 3: drop the ACK for frame 2 -> sender deadlocks (error-control gap).
    print("DEMO 3: lossy channel, ACK #2 dropped -> sender deadlock")
    sim3 = StopAndWaitSimulator(
        line_rate_bps=1_000_000,
        prop_ms=5.0,
        n_frames=5,
        payload="LOG",
        lossy=True,
        drop_ack_at_frame=2,
    )
    sim3.run()
    sim3.print_report()


if __name__ == "__main__":
    main()
