#!/usr/bin/env python3
"""TCP timer management and congestion control simulator.

Stdlib only. Demonstrates Sec 6.5.9-6.5.10:

1. Retransmission timer with Jacobson's algorithm (SRTT, RTTVAR, RTO)
   and Karn's algorithm (no update on retransmitted segments, exponential
   backoff).
2. Other timers: persistence timer (zero-window deadlock), keepalive,
   TIME_WAIT 2*MSL timer.
3. Congestion control: slow start (exponential), congestion avoidance
   (additive increase), fast retransmit (3 duplicate ACKs), fast recovery
   (TCP Reno sawtooth), with cwnd and ssthresh.

Run:  python3 main.py
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Part 1: RTT estimation and retransmission timer (Jacobson + Karn)
# ---------------------------------------------------------------------------

@dataclass
class RTTEstimator:
    srtt: float = 0.0
    rttvar: float = 0.0
    rto: float = 1.0
    alpha: float = 7.0 / 8.0
    beta: float = 3.0 / 4.0
    min_rto: float = 1.0
    _first_sample: bool = True

    def update(self, r: float, retransmitted: bool = False) -> None:
        """Update SRTT/RTTVAR/RTO. Karn's algorithm: skip retransmitted samples."""
        if retransmitted:
            self.rto = min(self.rto * 2.0, 60.0)
            return
        if self._first_sample:
            self.srtt = r
            self.rttvar = r / 2.0
            self._first_sample = False
        else:
            self.rttvar = self.beta * self.rttvar + (1 - self.beta) * abs(self.srtt - r)
            self.srtt = self.alpha * self.srtt + (1 - self.alpha) * r
        self.rto = max(self.min_rto, self.srtt + 4.0 * self.rttvar)


@dataclass
class TimerManager:
    rtt_estimator: RTTEstimator = field(default_factory=RTTEstimator)
    persistence_timer: float | None = None
    keepalive_timer: float = 7200.0
    time_wait_timer: float = 0.0
    msl: float = 60.0
    backoff: int = 0

    def start_retransmission(self) -> float:
        return self.rtt_estimator.rto * (2 ** self.backoff)

    def on_timeout(self) -> None:
        self.backoff += 1
        self.rtt_estimator.rto = min(self.rtt_estimator.rto * 2.0, 60.0)

    def on_ack(self, r: float, was_retransmitted: bool) -> None:
        if not was_retransmitted:
            self.backoff = 0
        self.rtt_estimator.update(r, retransmitted=was_retransmitted)

    def start_persistence(self) -> None:
        self.persistence_timer = 1.0

    def start_time_wait(self) -> None:
        self.time_wait_timer = 2.0 * self.msl


# ---------------------------------------------------------------------------
# Part 2: TCP Congestion Control (Tahoe/Reno)
# ---------------------------------------------------------------------------

@dataclass
class CongestionController:
    cwnd: int = 1
    ssthresh: int = 65535
    mss: int = 1460
    state: str = "slow_start"
    dup_ack_count: int = 0
    last_ack: int = 0
    recovery_point: int = 0

    def on_new_ack(self, ack: int) -> str:
        action = ""
        if self.state == "slow_start":
            self.cwnd += 1
            action = f"slow start: cwnd={self.cwnd}"
            if self.cwnd >= self.ssthresh:
                self.state = "congestion_avoidance"
                action += " -> switch to congestion avoidance"
        elif self.state == "congestion_avoidance":
            self.cwnd += max(1, self.mss * self.mss // (self.cwnd * self.mss))
            action = f"cong. avoid: cwnd={self.cwnd}"
        elif self.state == "fast_recovery":
            if ack >= self.recovery_point:
                self.cwnd = self.ssthresh
                self.state = "congestion_avoidance"
                action = f"fast recovery done: cwnd={self.cwnd} -> cong. avoid"
            else:
                self.cwnd += 1
                action = f"fast recovery: cwnd={self.cwnd}"
        self.dup_ack_count = 0
        self.last_ack = ack
        return action

    def on_dup_ack(self, ack: int) -> str:
        self.dup_ack_count += 1
        if self.dup_ack_count == 3 and self.state != "fast_recovery":
            self.ssthresh = max(self.cwnd // 2, 2)
            self.recovery_point = ack + (self.cwnd * self.mss)
            self.state = "fast_recovery"
            self.cwnd = self.ssthresh + 3
            return f"FAST RETRANMIT: ssthresh={self.ssthresh}, cwnd={self.cwnd}"
        if self.state == "fast_recovery":
            self.cwnd += 1
            return f"fast recovery: dup ack, cwnd={self.cwnd}"
        return f"dup ack #{self.dup_ack_count} (waiting for 3)"

    def on_timeout(self) -> str:
        self.ssthresh = max(self.cwnd // 2, 2)
        self.cwnd = 1
        self.state = "slow_start"
        self.dup_ack_count = 0
        return f"TIMEOUT: ssthresh={self.ssthresh}, cwnd=1 -> slow start"


# ---------------------------------------------------------------------------
# Demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    random.seed(42)
    print("=" * 70)
    print("RTT Estimation: Jacobson's Algorithm (SRTT, RTTVAR, RTO)")
    print("=" * 70)
    est = RTTEstimator()
    samples = [25, 30, 28, 35, 27, 22, 80, 29, 31, 26]
    print(f"  {'Sample':>6}  {'SRTT':>8}  {'RTTVAR':>8}  {'RTO':>8}  {'Note':>25}")
    for i, r in enumerate(samples):
        retrans = (r == 80)
        est.update(r, retransmitted=retrans)
        note = "Karn: skip (retransmitted)" if retrans else ""
        print(f"  {r:6.1f}  {est.srtt:8.2f}  {est.rttvar:8.2f}  {est.rto:8.2f}  {note:>25}")

    print()
    print("  Formula: SRTT = alpha*SRTT + (1-alpha)*R, alpha=7/8")
    print("           RTTVAR = beta*RTTVAR + (1-beta)*|SRTT-R|, beta=3/4")
    print("           RTO = SRTT + 4*RTTVAR (min 1 second)")

    print()
    print("=" * 70)
    print("Karn's Algorithm: Exponential Backoff on Retransmission")
    print("=" * 70)
    tm = TimerManager()
    print(f"  Initial RTO = {tm.rtt_estimator.rto:.2f}s")
    for i in range(5):
        rto_val = tm.start_retransmission()
        tm.on_timeout()
        print(f"  Timeout #{i+1}: RTO = {rto_val:.2f}s -> backoff -> next RTO = {tm.start_retransmission():.2f}s")
    tm.on_ack(30.0, was_retransmitted=False)
    print(f"  After successful ACK (not retransmitted): RTO reset to {tm.rtt_estimator.rto:.2f}s, backoff=0")

    print()
    print("=" * 70)
    print("Other TCP Timers")
    print("=" * 70)
    tm2 = TimerManager()
    tm2.start_persistence()
    print(f"  Persistence timer: started at {tm2.persistence_timer}s")
    print(f"    (prevents zero-window deadlock: sender probes receiver)")
    print(f"  Keepalive timer: {tm2.keepalive_timer}s (2 hours default)")
    print(f"    (checks if peer is still alive; controversial)")
    tm2.start_time_wait()
    print(f"  TIME_WAIT timer: {tm2.time_wait_timer}s = 2*MSL ({tm2.msl}s)")
    print(f"    (ensures old packets die off before reuse)")

    print()
    print("=" * 70)
    print("Congestion Control: Slow Start -> Congestion Avoidance (Fig 6-44/45)")
    print("=" * 70)
    cc = CongestionController(cwnd=1, ssthresh=8, mss=1)
    print(f"  Initial: cwnd={cc.cwnd}, ssthresh={cc.ssthresh}")
    print(f"  {'RTT':>4}  {'Event':>20}  {'cwnd':>6}  {'ssthresh':>8}  {'state':>20}")
    for rtt in range(1, 20):
        ack = rtt * 10
        action = cc.on_new_ack(ack)
        print(f"  {rtt:4d}  {'new ACK':>20}  {cc.cwnd:6d}  {cc.ssthresh:8d}  {cc.state:>20}")
        if cc.state == "congestion_avoidance":
            break

    print()
    print("=" * 70)
    print("TCP Reno: Fast Retransmit + Fast Recovery (Fig 6-47)")
    print("=" * 70)
    cc2 = CongestionController(cwnd=1, ssthresh=16, mss=1)
    print(f"  Initial: cwnd={cc2.cwnd}, ssthresh={cc2.ssthresh}")
    for rtt in range(1, 12):
        cc2.on_new_ack(rtt * 100)
    print(f"  After slow start + cong. avoid: cwnd={cc2.cwnd}, ssthresh={cc2.ssthresh}")

    print(f"  Simulating packet loss at cwnd={cc2.cwnd}...")
    lost_ack = (rtt + 1) * 100
    for dup in range(5):
        action = cc2.on_dup_ack(lost_ack)
        print(f"  dup ACK #{dup+1}: {action}")
        if dup == 2:
            print(f"  *** 3 duplicate ACKs -> FAST RETRANSMIT ***")

    print()
    print(f"  Recovery: cwnd={cc2.cwnd}, ssthresh={cc2.ssthresh}, state={cc2.state}")
    for i in range(3):
        action = cc2.on_new_ack(lost_ack + i * 100 + 100)
        print(f"  new ACK: {action}")
    print(f"  Final: cwnd={cc2.cwnd}, ssthresh={cc2.ssthresh}, state={cc2.state}")

    print()
    print("=" * 70)
    print("Sawtooth Pattern: Timeout vs Fast Retransmit")
    print("=" * 70)
    cc3 = CongestionController(cwnd=1, ssthresh=32, mss=1)
    trace: list[tuple[int, str, int, int, str]] = []
    for step in range(25):
        if step == 10:
            trace.append((step, "3 DUP ACK", cc3.cwnd, cc3.ssthresh, cc3.state))
            cc3.on_dup_ack(0)
            cc3.on_dup_ack(0)
            cc3.on_dup_ack(0)
        elif step == 20:
            trace.append((step, "TIMEOUT", cc3.cwnd, cc3.ssthresh, cc3.state))
            cc3.on_timeout()
        else:
            cc3.on_new_ack(step * 100)
        trace.append((step, "new ACK", cc3.cwnd, cc3.ssthresh, cc3.state))

    print(f"  {'Step':>4}  {'Event':>12}  {'cwnd':>6}  {'ssthresh':>8}  {'state':>20}")
    for step, event, cwnd, ssth, state in trace[::2]:
        print(f"  {step:4d}  {event:>12}  {cwnd:6d}  {ssth:8d}  {state:>20}")
    print()
    print("  Sawtooth: additive increase (up) then multiplicative decrease (down).")
    print("  This AIMD pattern keeps cwnd near the optimal bandwidth-delay product.")


if __name__ == "__main__":
    main()