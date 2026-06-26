"""Static Channel Allocation — M/M/1 delay model for FDM/TDM partitioning.

This program reproduces the analysis in Tanenbaum, *Computer Networks*,
Section 4.1.1. It models a shared channel as an M/M/1 queue and proves,
both analytically and by direct recomputation, that statically splitting
one channel of capacity C into N equal subchannels multiplies the mean
frame delay by exactly N (equation 4-1):

        1                                  N
    T = -------       and       T_N = ---------- = N * T
        muC - lambda                  muC - lambda

Definitions (all consistent with the textbook):
    C       channel capacity in bits/sec
    lambda  mean frame arrival rate in frames/sec
    1/mu    mean frame length in bits  ->  mu = 1 / mean_frame_bits
    muC     channel service rate in frames/sec  (= C / mean_frame_bits)

Textbook worked example: C = 100 Mbps, mean frame = 10,000 bits,
lambda = 5000 frames/sec  ->  T = 200 microseconds. Split into N = 10
subchannels of 10 Mbps each  ->  T = 2 milliseconds.

Pure standard library. Run: python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass


class ChannelSaturated(ValueError):
    """Raised when arrival rate meets or exceeds service rate (lambda >= muC)."""


def service_rate(capacity_bps: float, mean_frame_bits: float) -> float:
    """Return channel service rate muC in frames/sec.

    muC = capacity / mean_frame_size. A 100 Mbps channel carrying
    10,000-bit frames serves 10,000 frames/sec.
    """
    if capacity_bps <= 0 or mean_frame_bits <= 0:
        raise ValueError("capacity and mean frame size must be positive")
    return capacity_bps / mean_frame_bits


def mm1_delay(capacity_bps: float, arrival_rate: float, mean_frame_bits: float) -> float:
    """Mean time in system T = 1 / (muC - lambda), in seconds.

    Combines queueing delay and transmission delay for an M/M/1 channel.
    Raises ChannelSaturated if lambda >= muC, where delay is unbounded.
    """
    if arrival_rate < 0:
        raise ValueError("arrival rate must be non-negative")
    mu_c = service_rate(capacity_bps, mean_frame_bits)
    spare = mu_c - arrival_rate
    if spare <= 0:
        raise ChannelSaturated(
            f"lambda={arrival_rate:g} >= muC={mu_c:g} frames/sec: delay is unbounded"
        )
    return 1.0 / spare


def transmission_only(capacity_bps: float, mean_frame_bits: float) -> float:
    """Naive serialization time for one frame, ignoring contention (seconds).

    This is the *wrong* answer for a shared channel; it omits queueing.
    """
    return mean_frame_bits / capacity_bps


def split_channel_delay(
    capacity_bps: float, arrival_rate: float, mean_frame_bits: float, n: int
) -> float:
    """Mean delay on ONE of N equal static subchannels, recomputed from scratch.

    Each subchannel has capacity C/N and receives a share lambda/N of the
    arrivals. Returned value should equal N * mm1_delay(C, lambda, ...).
    """
    if n < 1:
        raise ValueError("number of subchannels must be >= 1")
    sub_capacity = capacity_bps / n
    sub_lambda = arrival_rate / n
    return mm1_delay(sub_capacity, sub_lambda, mean_frame_bits)


def utilization_waste(
    capacity_bps: float, n: int, active_users: int
) -> tuple[float, float]:
    """Stranded capacity when only `active_users` of N static slices are busy.

    Returns (stranded_bps, stranded_fraction). In static allocation the idle
    slices cannot be lent to busy users, so their bandwidth is simply lost.
    """
    if not 0 <= active_users <= n:
        raise ValueError("active_users must be between 0 and n")
    idle_slices = n - active_users
    stranded = (capacity_bps / n) * idle_slices
    return stranded, idle_slices / n


@dataclass(frozen=True)
class Workload:
    """A traffic description used to recommend static vs dynamic allocation."""

    name: str
    fixed_user_count: bool
    steady_heavy_load: bool
    needs_isolation: bool


def recommend_allocation(w: Workload) -> str:
    """Decide whether static allocation fits, per Section 4.1.1 criteria."""
    if w.fixed_user_count and w.steady_heavy_load:
        if w.needs_isolation:
            return "STATIC ok: fixed user set, steady heavy load, isolation wanted."
        return "STATIC tolerable: fixed/steady, but a dynamic scheme would not hurt."
    return "DYNAMIC needed: variable users or bursty load make static wasteful."


def _us(seconds: float) -> str:
    """Format a delay in seconds as a human-readable microsecond/ms string."""
    micros = seconds * 1e6
    if micros >= 1000:
        return f"{micros / 1000:.3f} ms"
    return f"{micros:.1f} us"


def main() -> None:
    capacity = 100_000_000   # 100 Mbps
    frame_bits = 10_000      # 10,000 bits per frame
    arrivals = 5_000         # 5000 frames/sec

    mu_c = service_rate(capacity, frame_bits)
    base = mm1_delay(capacity, arrivals, frame_bits)
    naive = transmission_only(capacity, frame_bits)

    print("=== Static Channel Allocation: M/M/1 delay model (Sec. 4.1.1) ===")
    print(f"C = {capacity/1e6:.0f} Mbps | mean frame = {frame_bits} bits "
          f"| lambda = {arrivals} frames/sec")
    print(f"service rate muC = {mu_c:.0f} frames/sec")
    print()
    print(f"Naive serialization (ignores contention): {_us(naive)}  <- WRONG for shared link")
    print(f"M/M/1 mean delay  T = 1/(muC - lambda)   : {_us(base)}  <- correct baseline")
    print()

    print("--- Static split into N subchannels: delay grows as N*T (eq. 4-1) ---")
    print(f"{'N':>3} | {'per-chan cap':>13} | {'analytic N*T':>13} | {'recomputed':>11} | match")
    for n in (1, 2, 5, 10, 20):
        analytic = n * base
        recomputed = split_channel_delay(capacity, arrivals, frame_bits, n)
        match = "yes" if abs(analytic - recomputed) < 1e-15 else "NO"
        print(
            f"{n:>3} | {capacity/n/1e6:>10.1f} Mbps | {_us(analytic):>13} |"
            f" {_us(recomputed):>11} | {match}"
        )
    print()
    print("Note the N=10 row: 2.000 ms = 10 x 200.0 us, matching the textbook.")
    print()

    print("--- Wasted capacity when slices sit idle ---")
    for active in (10, 3, 1):
        stranded, frac = utilization_waste(capacity, n=10, active_users=active)
        print(
            f"{active:>2}/10 slices busy -> {stranded/1e6:>5.1f} Mbps stranded "
            f"({frac*100:.0f}% of the link, unusable by busy users)"
        )
    print()

    print("--- Saturation: T -> infinity as lambda -> muC ---")
    for lam in (5_000, 9_000, 9_900, 10_000):
        try:
            d = mm1_delay(capacity, lam, frame_bits)
            print(f"lambda = {lam:>6} frames/sec -> T = {_us(d)}")
        except ChannelSaturated as exc:
            print(f"lambda = {lam:>6} frames/sec -> {exc}")
    print()

    print("--- Allocation recommendation by workload ---")
    workloads = [
        Workload("FM radio band", fixed_user_count=True, steady_heavy_load=True,
                 needs_isolation=True),
        Workload("Voice T1 trunk", fixed_user_count=True, steady_heavy_load=True,
                 needs_isolation=True),
        Workload("Campus LAN", fixed_user_count=False, steady_heavy_load=False,
                 needs_isolation=False),
        Workload("Bursty file servers", fixed_user_count=True, steady_heavy_load=False,
                 needs_isolation=True),
    ]
    for w in workloads:
        print(f"  {w.name:<22}: {recommend_allocation(w)}")


if __name__ == "__main__":
    main()
