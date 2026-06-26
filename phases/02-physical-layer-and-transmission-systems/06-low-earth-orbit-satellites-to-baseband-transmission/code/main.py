#!/usr/bin/env python3
"""LEO satellites to baseband transmission: delay and capacity arithmetic.

This module ties orbital geometry to the information-theory ceiling that
governs every link in a satellite constellation. It implements:

  * propagation_delay_ms  -- one-way / round-trip delay from altitude (d / c)
  * db_to_linear          -- convert an SNR quoted in decibels to a power ratio
  * nyquist_capacity_bps  -- noiseless capacity  C = 2 * B * log2(V)
  * shannon_capacity_bps  -- noisy capacity       C = B  * log2(1 + S/N)
  * link_budget           -- run both laws and report which one binds

Everything is stdlib-only and has no network access. Run it directly:

    python3 main.py

The printed demonstration reproduces the LEO vs GEO delay gap (Iridium ~2.5 ms
one-way vs GEO ~119 ms), the classic noiseless 3 kHz channel limits, and the
ADSL ~13.3 Mbps Shannon figure from Tanenbaum Chapter 2.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Speed of light in vacuum, in km/s. Good enough for path-delay arithmetic;
# real RF travels marginally slower through atmosphere but the difference is
# far below the millisecond resolution we care about here.
SPEED_OF_LIGHT_KM_S: float = 299_792.458

# ITU-T G.114 guidance: interactive voice stays comfortable below ~150 ms
# of one-way mouth-to-ear delay.
VOICE_ONE_WAY_BUDGET_MS: float = 150.0


@dataclass(frozen=True)
class Orbit:
    """A circular orbit characterized by name and altitude above ground."""

    name: str
    altitude_km: float
    use_case: str


# Representative orbits. Iridium and Globalstar are the two LEO voice
# constellations from the chapter; GPS is MEO; GEO is the broadcast belt.
ORBITS: tuple[Orbit, ...] = (
    Orbit("Iridium (LEO)", 750.0, "Interactive voice, paging"),
    Orbit("Globalstar (LEO)", 1_400.0, "Voice, low-rate data"),
    Orbit("GPS (MEO)", 20_200.0, "Navigation"),
    Orbit("GEO belt", 35_800.0, "TV, broadcast data"),
)


def propagation_delay_ms(altitude_km: float, hops: int = 1) -> float:
    """One-way propagation delay in milliseconds for a satellite overhead.

    The straight-line distance to a satellite directly overhead equals its
    altitude. ``hops`` counts ground-to-satellite legs: a simple uplink is
    1 hop; a bent-pipe round trip (up then down) is 2 hops.
    """
    if altitude_km < 0:
        raise ValueError("altitude must be non-negative")
    if hops < 1:
        raise ValueError("hops must be at least 1")
    seconds = (altitude_km * hops) / SPEED_OF_LIGHT_KM_S
    return seconds * 1_000.0


def round_trip_ms(altitude_km: float) -> float:
    """Round-trip (up + down) delay in ms for a bent-pipe relay."""
    return propagation_delay_ms(altitude_km, hops=2)


def db_to_linear(snr_db: float) -> float:
    """Convert an SNR in decibels to a linear power ratio: 10 ** (dB / 10).

    A vendor quoting '40 dB SNR' means a power ratio of 10_000, which is what
    Shannon's formula consumes -- never plug the dB number in directly.
    """
    return 10.0 ** (snr_db / 10.0)


def nyquist_capacity_bps(bandwidth_hz: float, levels: int) -> float:
    """Noiseless channel capacity: C = 2 * B * log2(V) bits/sec.

    ``levels`` (V) is the number of discrete symbol levels. Binary is V = 2.
    A noiseless 3 kHz binary channel returns 6000 bps.
    """
    if bandwidth_hz < 0:
        raise ValueError("bandwidth must be non-negative")
    if levels < 2:
        raise ValueError("need at least 2 signal levels")
    return 2.0 * bandwidth_hz * math.log2(levels)


def shannon_capacity_bps(bandwidth_hz: float, snr_db: float) -> float:
    """Noisy channel capacity: C = B * log2(1 + S/N) bits/sec.

    ``snr_db`` is converted to a linear ratio first. No number of levels or
    samples can beat this ceiling once thermal noise is present.
    """
    if bandwidth_hz < 0:
        raise ValueError("bandwidth must be non-negative")
    snr_linear = db_to_linear(snr_db)
    return bandwidth_hz * math.log2(1.0 + snr_linear)


def surviving_harmonics(bit_rate_bps: float, cutoff_hz: float, bits_per_symbol_window: int = 8) -> float:
    """Approximate harmonics that survive a low-pass cutoff for a bit stream.

    For an N-bit window sent one bit at a time at ``bit_rate_bps``, the first
    harmonic sits at bit_rate / N Hz. The channel passes roughly
    cutoff / (bit_rate / N) harmonics. Few surviving harmonics means a rounded
    waveform and inter-symbol interference.
    """
    if bit_rate_bps <= 0:
        raise ValueError("bit rate must be positive")
    first_harmonic_hz = bit_rate_bps / bits_per_symbol_window
    return cutoff_hz / first_harmonic_hz


@dataclass(frozen=True)
class LinkBudget:
    """Result of evaluating both capacity laws on one channel."""

    bandwidth_hz: float
    levels: int
    snr_db: float
    nyquist_bps: float
    shannon_bps: float

    @property
    def binding_bps(self) -> float:
        """The achievable rate is the smaller of the two ceilings."""
        return min(self.nyquist_bps, self.shannon_bps)

    @property
    def binding_law(self) -> str:
        return "Nyquist (levels)" if self.nyquist_bps <= self.shannon_bps else "Shannon (noise)"


def link_budget(bandwidth_hz: float, levels: int, snr_db: float) -> LinkBudget:
    """Run Nyquist and Shannon on one channel and report the binding limit."""
    return LinkBudget(
        bandwidth_hz=bandwidth_hz,
        levels=levels,
        snr_db=snr_db,
        nyquist_bps=nyquist_capacity_bps(bandwidth_hz, levels),
        shannon_bps=shannon_capacity_bps(bandwidth_hz, snr_db),
    )


def _fmt_rate(bps: float) -> str:
    """Human-friendly bit-rate formatting."""
    if bps >= 1_000_000:
        return f"{bps / 1_000_000:.2f} Mbps"
    if bps >= 1_000:
        return f"{bps / 1_000:.2f} kbps"
    return f"{bps:.0f} bps"


def main() -> None:
    print("=" * 70)
    print("LEO satellites to baseband transmission")
    print("=" * 70)

    print("\n[1] Orbital geometry: altitude sets delay")
    print(f"{'Orbit':<18}{'Alt (km)':>10}{'1-way':>10}{'RTT':>10}  Use case")
    print("-" * 70)
    for orbit in ORBITS:
        one_way = propagation_delay_ms(orbit.altitude_km)
        rtt = round_trip_ms(orbit.altitude_km)
        flag = "" if one_way < VOICE_ONE_WAY_BUDGET_MS else "  <-- over voice budget"
        print(
            f"{orbit.name:<18}{orbit.altitude_km:>10.0f}"
            f"{one_way:>9.1f}m{rtt:>9.1f}m  {orbit.use_case}{flag}"
        )
    print(f"\nITU-T G.114 interactive-voice budget: {VOICE_ONE_WAY_BUDGET_MS:.0f} ms one-way")

    print("\n[2] Nyquist on a noiseless 3 kHz channel (more levels -> more bits)")
    for levels in (2, 4, 16):
        cap = nyquist_capacity_bps(3_000, levels)
        print(f"  V = {levels:>2}: {_fmt_rate(cap)}")

    print("\n[3] dB to linear SNR conversion")
    for db in (10, 20, 30, 40):
        print(f"  {db} dB -> S/N ratio {db_to_linear(db):,.0f}")

    print("\n[4] Shannon on ADSL: 1 MHz bandwidth, 40 dB SNR")
    adsl = shannon_capacity_bps(1_000_000, 40)
    print(f"  Capacity ceiling: {_fmt_rate(adsl)} (chapter quotes ~13 Mbps)")

    print("\n[5] Band-limited telemetry: 9600 bps over a 3 kHz voice-grade line")
    harmonics = surviving_harmonics(9_600, 3_000)
    print(f"  Surviving harmonics through cutoff: ~{harmonics:.1f}")
    print("  Too few harmonics -> rounded pulses -> inter-symbol interference.")

    print("\n[6] Link budget: which law binds?")
    scenarios = (
        ("Wide band, low noise", 1_000_000, 64, 40),
        ("Narrow band, high noise", 25_000, 64, 15),
        ("Voice channel, clean", 3_000, 4, 35),
    )
    print(f"{'Scenario':<26}{'Nyquist':>12}{'Shannon':>12}  Binds")
    print("-" * 70)
    for label, bw, lv, snr in scenarios:
        lb = link_budget(bw, lv, snr)
        print(
            f"{label:<26}{_fmt_rate(lb.nyquist_bps):>12}"
            f"{_fmt_rate(lb.shannon_bps):>12}  {lb.binding_law}"
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
