#!/usr/bin/env python3
"""Spectrum and channel calculator for the physical layer.

Connects two ideas from Tanenbaum Chapter 2: power-line networking (the worst
guided medium) and the electromagnetic spectrum (the medium with the most
bandwidth). Everything keys off two relations:

    lambda * f = c          (wave relation; c ~ 3e8 m/s in vacuum)
    C = B * log2(1 + SNR)   (Shannon capacity)

Stdlib only, no network calls. Run:  python3 main.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Speed of light in vacuum (m/s). In copper/fiber, propagation is ~2/3 of this.
C_VACUUM: float = 3.0e8

# ITU band table: (name, full_name, f_low_hz, f_high_hz).
ITU_BANDS: list[tuple[str, str, float, float]] = [
    ("ELF", "Extremely Low Frequency", 3.0, 30.0),
    ("VLF", "Very Low Frequency", 3.0e3, 30.0e3),
    ("LF", "Low Frequency", 30.0e3, 300.0e3),
    ("MF", "Medium Frequency", 300.0e3, 3.0e6),
    ("HF", "High Frequency", 3.0e6, 30.0e6),
    ("VHF", "Very High Frequency", 30.0e6, 300.0e6),
    ("UHF", "Ultra High Frequency", 300.0e6, 3.0e9),
    ("SHF", "Super High Frequency", 3.0e9, 30.0e9),
    ("EHF", "Extremely High Frequency", 30.0e9, 300.0e9),
    ("THF", "Tremendously High Frequency", 300.0e9, 3.0e12),
]

# HomePlug AV / IEEE 1901 occupies roughly 2-28 MHz on the mains.
POWER_LINE_LOW_HZ: float = 2.0e6
POWER_LINE_HIGH_HZ: float = 28.0e6

# HF amateur-radio segments the HomePlug spectral mask notches out (Hz).
HAM_NOTCHES: list[tuple[str, float, float]] = [
    ("40 m band", 7.0e6, 7.3e6),
    ("30 m band", 10.1e6, 10.15e6),
    ("20 m band", 14.0e6, 14.35e6),
]


def freq_to_wavelength(freq_hz: float, speed: float = C_VACUUM) -> float:
    """Return wavelength (m) for a frequency (Hz): lambda = c / f."""
    if freq_hz <= 0:
        raise ValueError("frequency must be positive")
    return speed / freq_hz


def wavelength_to_frequency(wavelength_m: float, speed: float = C_VACUUM) -> float:
    """Return frequency (Hz) for a wavelength (m): f = c / lambda."""
    if wavelength_m <= 0:
        raise ValueError("wavelength must be positive")
    return speed / wavelength_m


def rule_of_thumb_300(freq_mhz: float) -> float:
    """Approximate wavelength (m) using lambda[m] * f[MHz] ~ 300."""
    if freq_mhz <= 0:
        raise ValueError("frequency must be positive")
    return 300.0 / freq_mhz


def classify_band(freq_hz: float) -> tuple[str, str]:
    """Return the (abbrev, full_name) ITU band containing freq_hz."""
    for abbrev, full, low, high in ITU_BANDS:
        if low <= freq_hz < high:
            return abbrev, full
    if freq_hz >= ITU_BANDS[-1][3]:
        return "IR+", "Infrared / visible / above"
    return "?", "below ELF"


def shannon_capacity(bandwidth_hz: float, snr_db: float) -> float:
    """Shannon capacity in bits/sec from bandwidth (Hz) and SNR (dB)."""
    snr_linear = 10.0 ** (snr_db / 10.0)
    return bandwidth_hz * math.log2(1.0 + snr_linear)


def quarter_wave_antenna(freq_hz: float, speed: float = C_VACUUM) -> float:
    """Length (m) of a quarter-wave monopole antenna for freq_hz."""
    return freq_to_wavelength(freq_hz, speed) / 4.0


@dataclass(frozen=True)
class Signal:
    """A named carrier somewhere on the spectrum."""

    name: str
    freq_hz: float


def _eng(value: float, unit: str) -> str:
    """Format a value with an engineering (SI) prefix."""
    prefixes = [
        (1e12, "T"), (1e9, "G"), (1e6, "M"), (1e3, "k"),
        (1.0, ""), (1e-3, "m"), (1e-6, "u"), (1e-9, "n"),
    ]
    for scale, pfx in prefixes:
        if abs(value) >= scale:
            return f"{value / scale:7.3f} {pfx}{unit}"
    return f"{value:.3e} {unit}"


def report_signals(signals: list[Signal]) -> None:
    """Print frequency, wavelength, ITU band, and antenna size per signal."""
    print(f"{'signal':<22}{'frequency':>14}{'wavelength':>16}"
          f"{'band':>7}{'1/4-wave ant':>16}")
    print("-" * 75)
    for sig in signals:
        wl = freq_to_wavelength(sig.freq_hz)
        abbrev, _ = classify_band(sig.freq_hz)
        ant = quarter_wave_antenna(sig.freq_hz)
        print(f"{sig.name:<22}{_eng(sig.freq_hz, 'Hz'):>14}"
              f"{_eng(wl, 'm'):>16}{abbrev:>7}{_eng(ant, 'm'):>16}")


def power_line_band_report() -> None:
    """Place the HomePlug 2-28 MHz band on the spectrum and flag notches."""
    low_wl = freq_to_wavelength(POWER_LINE_HIGH_HZ)
    high_wl = freq_to_wavelength(POWER_LINE_LOW_HZ)
    band_low, _ = classify_band(POWER_LINE_LOW_HZ)
    band_high, _ = classify_band(POWER_LINE_HIGH_HZ)
    print(f"HomePlug AV / IEEE 1901 band: "
          f"{_eng(POWER_LINE_LOW_HZ, 'Hz')} - {_eng(POWER_LINE_HIGH_HZ, 'Hz')}")
    print(f"  wavelengths: {_eng(low_wl, 'm')} - {_eng(high_wl, 'm')}")
    print(f"  ITU bands spanned: {band_low} (low) -> {band_high} (high)")
    print("  notched licensed segments (must transmit zero power here):")
    for name, lo, hi in HAM_NOTCHES:
        print(f"    - {name:<12} {_eng(lo, 'Hz')} - {_eng(hi, 'Hz')}")


def channel_comparison() -> None:
    """Contrast mains vs. fiber capacity to expose the spectrum gap."""
    # Mains: ~26 MHz usable band, modest SNR after notching and noise.
    mains_band = POWER_LINE_HIGH_HZ - POWER_LINE_LOW_HZ
    mains_snr_db = 15.0
    mains_c = shannon_capacity(mains_band, mains_snr_db)

    # Fiber 1.30-micron window: 0.17 micron wide -> ~30,000 GHz band.
    wl_center = 1.30e-6
    wl_width = 0.17e-6
    f_high = wavelength_to_frequency(wl_center - wl_width / 2.0)
    f_low = wavelength_to_frequency(wl_center + wl_width / 2.0)
    fiber_band = f_high - f_low
    fiber_snr_db = 10.0
    fiber_c = shannon_capacity(fiber_band, fiber_snr_db)

    print(f"{'channel':<18}{'bandwidth':>16}{'SNR':>8}{'capacity':>18}")
    print("-" * 60)
    print(f"{'mains (HomePlug)':<18}{_eng(mains_band, 'Hz'):>16}"
          f"{mains_snr_db:>6.0f}dB{_eng(mains_c, 'b/s'):>18}")
    print(f"{'fiber 1.30um win':<18}{_eng(fiber_band, 'Hz'):>16}"
          f"{fiber_snr_db:>6.0f}dB{_eng(fiber_c, 'b/s'):>18}")
    ratio = fiber_c / mains_c
    print(f"\n  fiber carries ~{ratio:,.0f}x the mains channel "
          f"(driven by {fiber_band / mains_band:,.0f}x more bandwidth)")


def main() -> None:
    """Run a realistic demonstration tying mains to the spectrum."""
    print("=" * 75)
    print("  PHYSICAL LAYER: POWER LINES TO THE ELECTROMAGNETIC SPECTRUM")
    print("=" * 75)

    print("\n[1] lambda * f = c  -- common carriers on the spectrum\n")
    signals = [
        Signal("AM broadcast", 1.0e6),
        Signal("HF / amateur 40m", 7.1e6),
        Signal("FM broadcast", 100.0e6),
        Signal("UHF TV ch.30", 566.0e6),
        Signal("GPS L1", 1.57542e9),
        Signal("Wi-Fi 2.4 GHz", 2.4e9),
        Signal("Wi-Fi 5 GHz", 5.0e9),
        Signal("mmWave 5G n258", 26.0e9),
    ]
    report_signals(signals)

    print("\n[2] rule-of-thumb cross-check: lambda[m] * f[MHz] ~ 300\n")
    for fmhz in (100.0, 1000.0, 2400.0):
        exact = freq_to_wavelength(fmhz * 1e6)
        approx = rule_of_thumb_300(fmhz)
        print(f"  f = {fmhz:8.0f} MHz -> exact {exact:7.4f} m, "
              f"rule-of-thumb {approx:7.4f} m")

    print("\n[3] power-line networking sits inside the noisy HF band\n")
    power_line_band_report()

    print("\n[4] Shannon: why fiber dwarfs the mains channel\n")
    channel_comparison()

    print("\n" + "=" * 75)
    print("  Takeaway: data rate tracks how much SPECTRUM a medium owns.")
    print("  The mains gives ~26 MHz of hostile band; fiber gives ~30,000 GHz.")
    print("=" * 75)


if __name__ == "__main__":
    main()
