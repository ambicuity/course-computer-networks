#!/usr/bin/env python3
"""TCP sliding-window simulator.

Maintains the five TCP variables (SND.UNA, SND.NXT, SND.WND, RCV.NXT,
RCV.WND), tracks bytes in flight, computes bandwidth-delay products,
and walks the receiver through a buffer drain plus a zero-window
deadlock.

No network calls, no third-party packages -- pure stdlib so it runs
anywhere with `python3 main.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


MAX_WINDOW_FIELD = 65535
MAX_WINDOW_SCALE = 14


@dataclass
class Sender:
    snd_una: int
    snd_nxt: int
    snd_wnd: int
    cwnd: int = 65535

    def bytes_in_flight(self) -> int:
        return self.snd_nxt - self.snd_una

    def can_send(self, n: int) -> bool:
        usable = min(self.snd_wnd, self.cwnd) - self.bytes_in_flight()
        return n <= usable

    def send(self, n: int) -> int:
        usable = min(self.snd_wnd, self.cwnd) - self.bytes_in_flight()
        allowed = min(n, max(usable, 0))
        self.snd_nxt += allowed
        return allowed

    def receive_ack(self, ack: int, new_wnd: int) -> None:
        if ack > self.snd_una:
            self.snd_una = ack
        self.snd_wnd = new_wnd


@dataclass
class Receiver:
    rcv_nxt: int
    rcv_wnd: int
    delivered: list[bytes] = field(default_factory=list)

    def receive(self, data: bytes) -> None:
        self.delivered.append(data)
        self.rcv_nxt += len(data)
        self.rcv_wnd = max(0, self.rcv_wnd - len(data))

    def application_read(self, n: int) -> int:
        consumed = 0
        while self.delivered and consumed < n:
            head = self.delivered[0]
            take = min(len(head), n - consumed)
            if take == len(head):
                self.delivered.pop(0)
            else:
                self.delivered[0] = head[take:]
            consumed += take
        self.rcv_wnd += consumed
        return consumed

    def advertised(self) -> int:
        return self.rcv_wnd


def bandwidth_delay_product(bandwidth_bps: int, rtt_seconds: float) -> dict[str, float]:
    bits = bandwidth_bps * rtt_seconds
    bytes_total = bits / 8.0
    return {
        "bandwidth_bps": bandwidth_bps,
        "rtt_seconds": rtt_seconds,
        "bits_in_pipe": bits,
        "bytes_in_pipe": bytes_total,
        "minimum_window_bytes": int(bytes_total),
        "fits_in_legacy_64KB": bytes_total <= MAX_WINDOW_FIELD,
    }


def effective_window(scale: int, raw_field: int) -> int:
    if not 0 <= scale <= MAX_WINDOW_SCALE:
        raise ValueError(f"window scale must be 0..{MAX_WINDOW_SCALE}")
    if not 0 <= raw_field <= MAX_WINDOW_FIELD:
        raise ValueError("raw window field must be 0..65535")
    return raw_field << scale


def zero_window_probe_schedule(max_probes: int = 8) -> list[float]:
    schedule = [5.0]
    for _ in range(1, max_probes):
        schedule.append(round(schedule[-1] * 2.0, 1))
    return schedule


def step_sender(label: str, sender: Sender, n: int) -> None:
    allowed = sender.send(n)
    print(
        f"  {label:<14} requested={n:<6} sent={allowed:<6} "
        f"SND.UNA={sender.snd_una:<8} SND.NXT={sender.snd_nxt:<8} "
        f"in_flight={sender.bytes_in_flight()}  "
        f"usable_wnd={min(sender.snd_wnd, sender.cwnd) - sender.bytes_in_flight()}"
    )


def drain_receiver(label: str, rcv: Receiver, read_bytes: int) -> None:
    consumed = rcv.application_read(read_bytes)
    print(
        f"  {label:<22} app read={read_bytes:<4} consumed={consumed:<4} "
        f"RCV.NXT={rcv.rcv_nxt:<6} RCV.WND={rcv.rcv_wnd:<6} "
        f"advertised={rcv.advertised()}"
    )


def main() -> None:
    print("=" * 70)
    print("TCP SLIDING WINDOW  --  sender/receiver variables, BD product, deadlock")
    print("=" * 70)

    print("\n[1] A sender with SND.WND=8192 sending a series of 1 KB segments:")
    sender = Sender(snd_una=0, snd_nxt=0, snd_wnd=8192)
    for idx in range(10):
        step_sender(f"segment {idx}", sender, 1024)
    print("  ... receiving cumulative acks that advance SND.UNA and grow SND.WND")
    for ack, new_wnd in [(2048, 12288), (4096, 16384), (6144, 16384), (8192, 24576)]:
        sender.receive_ack(ack, new_wnd)
        print(
            f"   <- ACK={ack:<6} WIN={new_wnd:<6}  "
            f"SND.UNA={sender.snd_una:<6} SND.WND={sender.snd_wnd:<6} "
            f"in_flight={sender.bytes_in_flight()}"
        )

    print("\n[2] Bandwidth-delay product on four sample paths:")
    paths = [
        ("Home FTTH 100 Mbps / 10 ms RTT", 100_000_000, 0.010),
        ("Cross-country 1 Gbps / 40 ms RTT", 1_000_000_000, 0.040),
        ("Geostationary 50 Mbps / 540 ms RTT", 50_000_000, 0.540),
        ("Wi-Fi 600 Mbps / 5 ms RTT", 600_000_000, 0.005),
    ]
    for label, bw, rtt in paths:
        bdp = bandwidth_delay_product(bw, rtt)
        print(
            f"  {label:<40}  pipe={bdp['bytes_in_pipe']:>14,.0f} B   "
            f"min_wnd={bdp['minimum_window_bytes']:>10,}   "
            f"fits_64KB?={bdp['fits_in_legacy_64KB']}"
        )

    print("\n[3] Window Scale (RFC 1323) recovers the legacy 64 KB cap:")
    for scale in (0, 3, 7, 14):
        eff = effective_window(scale, MAX_WINDOW_FIELD)
        print(f"  Window Scale = {scale:<2}  -> effective window = {eff:>12,} bytes ({eff / 1024:.1f} KB)")

    print("\n[4] Receiver buffer drain (Linux default ~4 MB, simulated smaller):")
    rcv = Receiver(rcv_nxt=0, rcv_wnd=4096)
    rcv.receive(b"x" * 1024)
    drain_receiver("after first 1 KB arrives", rcv, 0)
    rcv.receive(b"x" * 1024)
    drain_receiver("after second 1 KB arrives", rcv, 0)
    drain_receiver("app reads 512", rcv, 512)
    drain_receiver("app reads 1024", rcv, 1024)
    drain_receiver("app reads 4096", rcv, 4096)
    print(f"  advertised window grows from {4096} to {rcv.advertised()} as the app drains")

    print("\n[5] Zero-window deadlock and persistence probe schedule:")
    schedule = zero_window_probe_schedule()
    print(f"  receiver sets WIN=0; sender enters zero-window state")
    print("  sender's persistence timer fires at:")
    for idx, delay in enumerate(schedule, 1):
        print(f"    probe {idx}: send 1-byte segment at t+{delay:>5.1f}s")
    print("  receiver must respond with current WIN even if it is still 0")

    print("\n[6] Silly-window syndrome (Clark 1982) -- 1-byte reads without threshold:")
    rcv = Receiver(rcv_nxt=0, rcv_wnd=4096)
    rcv.receive(b"y" * 4096)
    print("  buffer starts full; WIN=0")
    for _ in range(4):
        drain_receiver("1-byte app read", rcv, 1)
    print("  without Clark's threshold, every 1-byte read re-opens WIN=1")
    print("  with threshold (>= MSS or half-buffer), receiver waits until WIN >= MSS")

    print("\nDone. Watch tcp.window_size_value in Wireshark while running `nc` between hosts.")


if __name__ == "__main__":
    main()