#!/usr/bin/env python3
"""Channel-capacity calculator: Fourier harmonics, Nyquist, and Shannon limits.

Implements the three results from Tanenbaum, *Computer Networks*, 6th ed.,
sections 2.1.1-2.1.3:

  * Fourier view: a repeating bit pattern has harmonics at n * (b / 8) Hz, and a
    channel of bandwidth B passes only the first 8B / b of them. Fewer harmonics
    -> rounded pulses -> lost data rate even on a perfect channel.
  * Nyquist (noiseless):  C = 2 * B * log2(V)        bits/sec
  * Shannon  (noisy):     C = B * log2(1 + S/N)      bits/sec

The real ceiling on a link is the SMALLER of the Nyquist and Shannon results.
This program computes both for any link, reports which one binds, and prints the
classic harmonics-vs-bit-rate table. Standard library only; runs with
`python3 main.py`.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Repeating-byte model: one byte (8 bits) takes 8 / b seconds, so the
# fundamental of the pattern is b / 8 Hz. Used by harmonics_through().
BITS_PER_BYTE = 8


def db_to_ratio(db: float) -> float:
    """Convert an SNR expressed in decibels to a linear power ratio.

    dB = 10 * log10(S/N)  =>  S/N = 10 ** (dB / 10).
    40 dB -> 10000, 30 dB -> 1000, 20 dB -> 100, 10 dB -> 10.
    """
    return 10.0 ** (db / 10.0)


def ratio_to_db(ratio: float) -> float:
    """Convert a linear power ratio back to decibels."""
    if ratio <= 0:
        raise ValueError("power ratio must be positive")
    return 10.0 * math.log10(ratio)


def nyquist_capacity(bandwidth_hz: float, levels: int) -> float:
    """Nyquist noiseless maximum data rate: C = 2 * B * log2(V) bits/sec.

    `levels` (V) is the number of discrete signal levels per symbol; each symbol
    carries log2(V) bits. A noiseless 3 kHz channel with V=2 gives 6000 bps.
    """
    if bandwidth_hz <= 0:
        raise ValueError("bandwidth must be positive")
    if levels < 2:
        raise ValueError("need at least 2 signal levels to carry data")
    return 2.0 * bandwidth_hz * math.log2(levels)


def shannon_capacity(bandwidth_hz: float, snr_db: float) -> float:
    """Shannon noisy-channel capacity: C = B * log2(1 + S/N) bits/sec.

    `snr_db` is in decibels and is converted to a linear ratio first -- a common
    mistake is plugging the dB value straight into the formula.
    """
    if bandwidth_hz <= 0:
        raise ValueError("bandwidth must be positive")
    snr_linear = db_to_ratio(snr_db)
    return bandwidth_hz * math.log2(1.0 + snr_linear)


def levels_needed(bandwidth_hz: float, target_bps: float) -> float:
    """Inverse Nyquist: signal levels V required to reach a target bit rate.

    From C = 2 * B * log2(V):  V = 2 ** (C / (2 * B)). Returns a float so the
    caller can see whether the required V is realistic (e.g. 1.4e6 levels).
    """
    if bandwidth_hz <= 0:
        raise ValueError("bandwidth must be positive")
    return 2.0 ** (target_bps / (2.0 * bandwidth_hz))


def harmonics_through(bit_rate_bps: float, bandwidth_hz: float) -> int:
    """How many harmonics of the repeating-byte pattern survive bandwidth B.

    One byte takes 8 / b seconds, so harmonics sit at n * (b / 8) Hz. The channel
    passes those with frequency <= B, i.e. n <= 8B / b. Reproduces the textbook
    table for a fixed 3000 Hz channel.
    """
    if bit_rate_bps <= 0 or bandwidth_hz <= 0:
        raise ValueError("bit rate and bandwidth must be positive")
    first_harmonic_hz = bit_rate_bps / BITS_PER_BYTE
    return int(bandwidth_hz // first_harmonic_hz)


@dataclass(frozen=True)
class LinkAnalysis:
    """Result of analyzing a single link against both capacity limits."""

    name: str
    bandwidth_hz: float
    levels: int
    snr_db: float
    nyquist_bps: float
    shannon_bps: float

    @property
    def binding_limit(self) -> str:
        return "Nyquist (level-limited)" if self.nyquist_bps <= self.shannon_bps else "Shannon (noise-limited)"

    @property
    def real_ceiling_bps(self) -> float:
        return min(self.nyquist_bps, self.shannon_bps)


def analyze_link(name: str, bandwidth_hz: float, levels: int, snr_db: float) -> LinkAnalysis:
    """Run both capacity limits on a link and package the result."""
    return LinkAnalysis(
        name=name,
        bandwidth_hz=bandwidth_hz,
        levels=levels,
        snr_db=snr_db,
        nyquist_bps=nyquist_capacity(bandwidth_hz, levels),
        shannon_bps=shannon_capacity(bandwidth_hz, snr_db),
    )


def _fmt_bps(bps: float) -> str:
    """Human-readable bits/sec with units."""
    for unit, scale in (("Gbps", 1e9), ("Mbps", 1e6), ("kbps", 1e3)):
        if bps >= scale:
            return f"{bps / scale:.2f} {unit}"
    return f"{bps:.0f} bps"


def print_link_report(link: LinkAnalysis) -> None:
    """Print a labeled capacity report for one link."""
    print(f"--- {link.name} ---")
    print(f"  bandwidth B   : {link.bandwidth_hz / 1e3:.1f} kHz")
    print(f"  signal levels : V = {link.levels}  ({math.log2(link.levels):.0f} bits/symbol)")
    print(f"  SNR           : {link.snr_db:.0f} dB  (linear S/N = {db_to_ratio(link.snr_db):.0f})")
    print(f"  Nyquist  cap  : {_fmt_bps(link.nyquist_bps)}")
    print(f"  Shannon  cap  : {_fmt_bps(link.shannon_bps)}")
    print(f"  >> real limit : {_fmt_bps(link.real_ceiling_bps)}  -- bound by {link.binding_limit}")
    print()


def print_harmonics_table(bandwidth_hz: float) -> None:
    """Reproduce the harmonics-vs-bit-rate table for a fixed-bandwidth channel."""
    print(f"--- Harmonics through a {bandwidth_hz / 1e3:.0f} kHz channel ---")
    print(f"  {'bit rate':>10} {'T (ms)':>9} {'1st harm (Hz)':>14} {'# harmonics':>12}")
    for bit_rate in (300, 600, 1200, 2400, 4800, 9600, 19200):
        period_ms = (BITS_PER_BYTE / bit_rate) * 1000.0
        first = bit_rate / BITS_PER_BYTE
        n = harmonics_through(bit_rate, bandwidth_hz)
        print(f"  {bit_rate:>10} {period_ms:>9.2f} {first:>14.1f} {n:>12}")
    print()


def main() -> None:
    """Demonstrate the limits on three real links plus the harmonics table."""
    print("=" * 60)
    print("CHANNEL CAPACITY: Nyquist (noiseless) vs Shannon (noisy)")
    print("=" * 60)
    print()

    links = [
        analyze_link("V.22bis phone modem", bandwidth_hz=3000, levels=4, snr_db=30),
        analyze_link("ADSL short loop (1 km)", bandwidth_hz=1_000_000, levels=256, snr_db=40),
        analyze_link("ADSL long loop (3.5 km)", bandwidth_hz=1_000_000, levels=256, snr_db=28),
        analyze_link("Wi-Fi 20 MHz channel", bandwidth_hz=20_000_000, levels=64, snr_db=25),
    ]
    for link in links:
        print_link_report(link)

    print_harmonics_table(3000)

    # Worked inverse example: 48 kbps over a noiseless 4 kHz channel.
    target = 48_000
    band = 4000
    v = levels_needed(band, target)
    print(f"--- Inverse Nyquist: {target} bps over a {band/1e3:.0f} kHz noiseless channel ---")
    print(f"  required signal levels V = {v:.0f}")
    print(f"  (realistic only if noise allows that many distinct levels -- see Shannon)")
    print()

    print("Takeaway: the real ceiling is the SMALLER of Nyquist and Shannon.")
    print("Adding signal levels V helps Nyquist but is useless past the Shannon wall.")


if __name__ == "__main__":
    main()
