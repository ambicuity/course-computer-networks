#!/usr/bin/env python3
"""Unguided-transmission toolkit: radio, microwave, and infrared.

Pure-stdlib model of the physics from Tanenbaum CN 5e Sec. 2.3.2-2.3.4:

  * band_of(freq)            -> classify a carrier as radio / microwave /
                                infrared / light and name its propagation mode
  * friis_path_loss(d, f)    -> free-space path loss (the 6 dB-per-doubling rule)
  * microwave_repeater_spacing(h) -> line-of-sight hop length vs tower height
  * rain_margin(freq)        -> extra loss budget needed above ~4 GHz
  * link_budget(...)         -> TX power + gains - losses, then the fade margin
  * recommend_band(...)      -> decision tree mapping requirements to a band

No network calls, no third-party deps. Run: python3 main.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

SPEED_OF_LIGHT_M_S: float = 2.998e8       # propagation speed in air ~ vacuum
EARTH_RADIUS_M: float = 6.371e6           # mean radius, for the LOS horizon
HORIZON_K_FACTOR: float = 4.0 / 3.0       # standard atmospheric refraction
ISM_POWER_CAP_W: float = 1.0              # FCC Part 15 style cap, e.g. 1 watt


class Band(Enum):
    """Coarse spectrum buckets used for unguided communication."""

    RADIO = "radio"
    MICROWAVE = "microwave"
    INFRARED = "infrared"
    LIGHT = "visible-or-optical"


@dataclass(frozen=True)
class BandInfo:
    band: Band
    propagation: str
    licensed: str
    note: str


def wavelength_m(freq_hz: float) -> float:
    """Wavelength from frequency using lambda * f = c (Eq. 2-4)."""
    if freq_hz <= 0:
        raise ValueError("frequency must be positive")
    return SPEED_OF_LIGHT_M_S / freq_hz


def band_of(freq_hz: float) -> BandInfo:
    """Classify a carrier frequency and describe how it propagates.

    Boundaries follow the chapter: below ~100 MHz radio bends/ground-rides,
    above ~100 MHz microwaves go line-of-sight, then IR and light behave
    optically (wall-blocked, directional).
    """
    if freq_hz <= 0:
        raise ValueError("frequency must be positive")

    if freq_hz < 3e6:                      # VLF / LF / MF
        return BandInfo(Band.RADIO, "ground wave (follows earth's curvature)",
                        "licensed", "up to ~1000 km; low bandwidth, AM at MF")
    if freq_hz < 30e6:                     # HF
        return BandInfo(Band.RADIO, "sky wave (refracts off ionosphere)",
                        "licensed", "intercontinental hops, used by hams/military")
    if freq_hz < 1e8:                      # VHF up to 100 MHz
        return BandInfo(Band.RADIO, "line-of-sight (ground wave absorbed)",
                        "licensed", "FM/TV; omnidirectional, penetrates walls")
    if freq_hz < 3e11:                     # 100 MHz .. 300 GHz: microwave/mmwave
        return BandInfo(Band.MICROWAVE, "focused line-of-sight beam",
                        ism_status(freq_hz),
                        "needs aligned dishes + repeaters; multipath/rain prone")
    if freq_hz < 4e14:                     # infrared
        return BandInfo(Band.INFRARED, "directional, blocked by solid walls",
                        "license-free",
                        "IrDA remotes; eavesdrop-resistant, one-room range")
    return BandInfo(Band.LIGHT, "narrow optical beam (free-space optics)",
                    "license-free", "rooftop laser links; rain/fog/heat sensitive")


def ism_status(freq_hz: float) -> str:
    """Report whether a microwave frequency falls in an unlicensed band."""
    f = freq_hz
    if 902e6 <= f <= 928e6:
        return "unlicensed ISM 900 MHz (power cap, spread spectrum)"
    if 2.400e9 <= f <= 2.4835e9:
        return "unlicensed ISM 2.4 GHz (802.11b/g, Bluetooth; oven interference)"
    if 5.15e9 <= f <= 5.825e9:
        return "unlicensed U-NII 5 GHz (802.11a)"
    if 57e9 <= f <= 64e9:
        return "unlicensed 60 GHz (huge bandwidth, oxygen-absorbed, short range)"
    return "licensed"


def friis_path_loss_db(distance_m: float, freq_hz: float) -> float:
    """Free-space path loss in dB via the Friis transmission equation.

    FSPL = 20*log10(d) + 20*log10(f) + 20*log10(4*pi/c).
    Demonstrates the ~6 dB increase per doubling of distance.
    """
    if distance_m <= 0 or freq_hz <= 0:
        raise ValueError("distance and frequency must be positive")
    lam = wavelength_m(freq_hz)
    return 20.0 * math.log10(4.0 * math.pi * distance_m / lam)


def six_db_check(freq_hz: float, d1_m: float, d2_m: float) -> float:
    """Return the loss difference between two ranges (should be ~6 dB if doubled)."""
    return friis_path_loss_db(d2_m, freq_hz) - friis_path_loss_db(d1_m, freq_hz)


def los_horizon_km(tower_height_m: float) -> float:
    """Radio line-of-sight horizon for one antenna (with 4/3 earth refraction)."""
    if tower_height_m <= 0:
        raise ValueError("tower height must be positive")
    eff_r = HORIZON_K_FACTOR * EARTH_RADIUS_M
    return math.sqrt(2.0 * eff_r * tower_height_m) / 1000.0


def microwave_repeater_spacing_km(tower_height_m: float) -> float:
    """Max hop between two equal towers ~ 2x the single-antenna horizon.

    Anchored to the chapter rule of thumb: ~80 km for 100 m towers, and
    spacing scaling roughly with the square root of tower height.
    """
    return 2.0 * los_horizon_km(tower_height_m)


def rain_margin_db(freq_hz: float) -> float:
    """Extra fade budget to reserve for rain absorption above ~4 GHz."""
    if freq_hz < 4e9:
        return 0.0
    # Crude monotonic model: water absorption climbs with frequency.
    ghz = freq_hz / 1e9
    return round(min(25.0, 2.0 * (ghz - 4.0) ** 0.6), 1)


@dataclass(frozen=True)
class LinkBudget:
    rx_level_dbm: float
    fade_margin_db: float
    closes: bool


def link_budget(tx_power_dbm: float, tx_gain_dbi: float, rx_gain_dbi: float,
                distance_m: float, freq_hz: float,
                rx_sensitivity_dbm: float) -> LinkBudget:
    """Compute received power and fade margin for an unguided hop."""
    fspl = friis_path_loss_db(distance_m, freq_hz)
    rain = rain_margin_db(freq_hz)
    rx = tx_power_dbm + tx_gain_dbi + rx_gain_dbi - fspl - rain
    margin = rx - rx_sensitivity_dbm
    return LinkBudget(round(rx, 1), round(margin, 1), margin > 0.0)


def recommend_band(*, must_penetrate_walls: bool, long_range_p2p: bool,
                   needs_license_free: bool, crosses_rain: bool,
                   confine_to_one_room: bool) -> str:
    """Decision tree mapping requirements to radio / microwave / infrared."""
    if confine_to_one_room or (needs_license_free and not long_range_p2p
                               and not must_penetrate_walls):
        return ("INFRARED (IrDA): wall-blocked containment, no license, "
                "eavesdrop-resistant; gives up building-wide coverage")
    if long_range_p2p:
        if crosses_rain:
            return ("MICROWAVE below 4 GHz with aligned dishes: avoid rain-"
                    "absorbed bands and free-space optics in wet weather")
        return ("MICROWAVE: focused beam, repeaters every ~sqrt(height) km, "
                "cheap line-of-sight backhaul without right-of-way")
    if must_penetrate_walls:
        return ("RADIO (lower-frequency, e.g. 2.4 GHz over 5 GHz): "
                "omnidirectional, penetrates walls for whole-building coverage")
    return "RADIO 5 GHz U-NII: more bandwidth where range/walls matter less"


def _rule(title: str) -> None:
    print("\n" + title)
    print("-" * len(title))


def main() -> None:
    print("=" * 64)
    print("UNGUIDED TRANSMISSION: RADIO -> MICROWAVE -> INFRARED")
    print("=" * 64)

    _rule("1. Band classifier (frequency -> band + propagation)")
    samples = [
        ("AM broadcast", 1.0e6),
        ("Ham HF", 14.2e6),
        ("FM radio (VHF)", 98e6),
        ("Wi-Fi 2.4 GHz", 2.45e9),
        ("Wi-Fi 5 GHz", 5.5e9),
        ("60 GHz mmwave", 60e9),
        ("TV remote (IR)", 3.5e14),
    ]
    for name, f in samples:
        info = band_of(f)
        print(f"  {name:18s} {f/1e6:>10.2f} MHz  lambda={wavelength_m(f):.4g} m")
        print(f"      -> {info.band.value:11s} | {info.propagation}")
        print(f"         {info.licensed}")

    _rule("2. Friis path loss and the 6 dB-per-doubling rule")
    f = 2.45e9
    for d in (100, 200, 400, 800):
        print(f"  2.4 GHz @ {d:>4d} m : FSPL = {friis_path_loss_db(d, f):6.2f} dB")
    print(f"  delta(100->200 m) = {six_db_check(f, 100, 200):.2f} dB "
          f"(~6 dB confirms inverse-square law)")

    _rule("3. Microwave line-of-sight repeater spacing")
    for h in (45, 100, 200):
        print(f"  {h:>3d} m towers -> max hop ~ {microwave_repeater_spacing_km(h):6.1f} km")
    print("  (100 m -> ~ matches the textbook ~80 km rule of thumb)")

    _rule("4. Link budget for the 12 km rooftop microwave hop")
    lb = link_budget(tx_power_dbm=20, tx_gain_dbi=28, rx_gain_dbi=28,
                     distance_m=12_000, freq_hz=6.0e9,
                     rx_sensitivity_dbm=-85)
    print(f"  6 GHz, 12 km, 28 dBi dishes, +20 dBm TX, -85 dBm sensitivity")
    print(f"  rain margin reserved : {rain_margin_db(6.0e9)} dB")
    print(f"  received level       : {lb.rx_level_dbm} dBm")
    print(f"  fade margin          : {lb.fade_margin_db} dB  "
          f"(link {'CLOSES' if lb.closes else 'FAILS'})")
    print("  A 20 dB mid-morning multipath fade would erase this margin.")

    _rule("5. Band recommendation decision tree")
    cases = [
        ("Whole-building Wi-Fi",
         dict(must_penetrate_walls=True, long_range_p2p=False,
              needs_license_free=True, crosses_rain=False,
              confine_to_one_room=False)),
        ("12 km rooftop backhaul, rainy region",
         dict(must_penetrate_walls=False, long_range_p2p=True,
              needs_license_free=False, crosses_rain=True,
              confine_to_one_room=False)),
        ("Per-room hospital remote, no cross-talk",
         dict(must_penetrate_walls=False, long_range_p2p=False,
              needs_license_free=True, crosses_rain=False,
              confine_to_one_room=True)),
    ]
    for label, kw in cases:
        print(f"  {label}:")
        print(f"      {recommend_band(**kw)}")

    print("\nDone.")


if __name__ == "__main__":
    main()
