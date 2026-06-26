#!/usr/bin/env python3
"""TCP timer simulator.

Implements Jacobson's retransmission timer (RFC 6298), Karn's
backoff, fast retransmit, the persist-timer probe schedule, and the
keepalive deadline with Linux defaults.

No network calls, no third-party packages -- pure stdlib so it runs
anywhere with `python3 main.py`.
"""

from __future__ import annotations

from dataclasses import dataclass

ALPHA = 1.0 / 8.0
BETA = 1.0 / 4.0
K = 4
RTO_MIN_SEC = 1.0
RTO_MAX_SEC = 60.0
KARN_CAP_SEC = 64.0
PERSIST_FIRST_SEC = 5.0
PERSIST_CAP_SEC = 60.0

KEEPALIVE_TIME_SEC = 7200.0
KEEPALIVE_INTVL_SEC = 75.0
KEEPALIVE_PROBES = 9

DUP_ACK_THRESHOLD = 3
INITIAL_CWND_KB = 20
MSS_BYTES = 1460


@dataclass
class JacobsonTimer:
    srtt: float | None = None
    rttvar: float | None = None
    rto: float = RTO_MIN_SEC
    clock_granularity: float = 0.01

    def step(self, r: float, retransmitted: bool = False) -> float:
        if retransmitted:
            return self.rto
        if self.srtt is None:
            self.srtt = r
            self.rttvar = r / 2.0
        else:
            self.rttvar = (1 - BETA) * abs(self.srtt - r) + BETA * self.rttvar
            self.srtt = (1 - ALPHA) * r + ALPHA * self.srtt
        self.rto = self.srtt + max(K * self.rttvar, self.clock_granularity)
        self.rto = min(max(self.rto, RTO_MIN_SEC), RTO_MAX_SEC)
        return self.rto


def karn_backoff(initial_rto: float, attempts: int = 6) -> list[float]:
    """Return the Karn backoff schedule: double RTO each timeout, capped."""
    schedule: list[float] = []
    rto = initial_rto
    for _ in range(attempts):
        schedule.append(round(rto, 3))
        rto = min(rto * 2.0, KARN_CAP_SEC)
    return schedule


def persist_schedule(probes: int = 8) -> list[float]:
    """Exponential backoff for window probes, capped at PERSIST_CAP_SEC."""
    schedule: list[float] = []
    delay = PERSIST_FIRST_SEC
    for _ in range(probes):
        schedule.append(round(delay, 1))
        delay = min(delay * 2.0, PERSIST_CAP_SEC)
    return schedule


def keepalive_deadline(
    idle_seconds: float = 0.0,
    time_sec: float = KEEPALIVE_TIME_SEC,
    intvl_sec: float = KEEPALIVE_INTVL_SEC,
    probes: int = KEEPALIVE_PROBES,
) -> float:
    """Seconds of idle time before the kernel gives up on the peer."""
    return idle_seconds + time_sec + intvl_sec * probes


def fast_retransmit(cwnd_kb: int, mss_bytes: int = MSS_BYTES) -> dict[str, int]:
    """Return the post-fast-retransmit state (RFC 5681)."""
    cwnd_bytes = cwnd_kb * 1024
    ssthresh = cwnd_bytes // 2
    flight = ssthresh
    new_cwnd = ssthresh + DUP_ACK_THRESHOLD * mss_bytes
    return {
        "cwnd_before_bytes": cwnd_bytes,
        "ssthresh_bytes": ssthresh,
        "flight_shrink_bytes": ssthresh,
        "cwnd_after_bytes": new_cwnd,
    }


def duplicate_ack_threshold() -> int:
    return DUP_ACK_THRESHOLD


def main() -> None:
    print("=" * 70)
    print("TCP TIMER MANAGEMENT  --  retransmission, persist, keepalive, fast retransmit")
    print("=" * 70)

    print("\n[1] Jacobson's retransmission timer (RFC 6298):")
    print(f"   alpha = {ALPHA:.4f}   beta = {BETA:.4f}   K = {K}")
    print(f"   RTO = SRTT + max(G, K*RTTVAR), floored at {RTO_MIN_SEC}s, capped at {RTO_MAX_SEC}s")
    timer = JacobsonTimer()
    samples = [0.500, 0.600, 0.450, 0.500, 0.520, 0.480, 0.530, 0.470, 0.510, 0.490]
    print(f"\n   {'R (s)':<10}{'SRTT (s)':<14}{'RTTVAR (s)':<14}{'RTO (s)':<10}")
    for r in samples:
        rto = timer.step(r)
        print(f"   {r:<10.3f}{timer.srtt:<14.4f}{timer.rttvar:<14.4f}{rto:<10.3f}")

    print("\n[2] Karn's backoff after a retransmission timer fires:")
    initial_rto = 1.5
    schedule = karn_backoff(initial_rto, attempts=7)
    elapsed = 0.0
    for idx, rto in enumerate(schedule, 1):
        elapsed += rto
        print(f"   attempt {idx}: RTO = {rto:>5.1f}s   (cumulative ~{elapsed:.1f}s since first timeout)")

    print("\n[3] Karn forbids RTT sampling from retransmitted segments:")
    t = JacobsonTimer(srtt=0.5, rttvar=0.05)
    rtt_real = 0.5
    print(f"   pre-retransmit RTO = {t.rto:.3f}")
    t.step(rtt_real, retransmitted=True)
    print(f"   after sample R={rtt_real:.3f} flagged retransmitted: SRTT/RTTVAR/RTO unchanged at {t.srtt:.3f}/{t.rttvar:.3f}/{t.rto:.3f}")
    t.step(rtt_real, retransmitted=False)
    print(f"   after fresh (non-retransmitted) sample: SRTT={t.srtt:.3f}, RTTVAR={t.rttvar:.3f}, RTO={t.rto:.3f}")

    print("\n[4] Persist timer schedule (zero-window probes):")
    for idx, delay in enumerate(persist_schedule(), 1):
        print(f"   probe {idx}: send 1-byte segment at delay {delay:>5.1f}s from previous probe")

    print("\n[5] Keepalive deadline (Linux defaults):")
    print(f"   tcp_keepalive_time = {KEEPALIVE_TIME_SEC:.0f}s ({KEEPALIVE_TIME_SEC / 3600:.1f} h)")
    print(f"   tcp_keepalive_intvl = {KEEPALIVE_INTVL_SEC:.0f}s")
    print(f"   tcp_keepalive_probes = {KEEPALIVE_PROBES}")
    print(f"   kernel declares connection dead after {keepalive_deadline():.0f}s ({keepalive_deadline() / 3600:.2f} h) idle")

    print("\n[6] Fast retransmit + fast recovery (RFC 5681):")
    state = fast_retransmit(INITIAL_CWND_KB)
    print(f"   before : cwnd = {state['cwnd_before_bytes']:>5} B")
    print(f"   3 dup-acks arrive -> retransmit immediately")
    print(f"   ssthresh set to cwnd/2 = {state['ssthresh_bytes']:>5} B")
    print(f"   cwnd inflated to ssthresh + 3*MSS = {state['cwnd_after_bytes']:>5} B")
    print(f"   stay in congestion avoidance (TCP Reno), do not drop to slow start")

    print("\nDone. Watch `ss -ti` for the rto and timer fields on a live socket.")


if __name__ == "__main__":
    main()