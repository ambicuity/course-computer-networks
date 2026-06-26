"""Light transmission and Medium-Earth Orbit (MEO) satellite link calculator.

Two physical-layer engines that share one core: signals propagating through
free space, where the budget is set by geometry and the speed of light.

1. Satellite latency engine
   - propagation_delay():  t = d / c          (one-way, vacuum)
   - slant_range():        line-of-sight distance to a satellite at a given
                           ground-elevation angle (always >= the altitude)
   - rtt():                round-trip time, optionally including switching

2. Free-space optics (FSO) link-budget engine
   - fso_link_budget():    transmit power, beam divergence, distance and an
                           atmospheric loss term -> received power and the
                           link margin (dB). Models the rooftop-laser link:
                           a 1 bit is a pulse of light, a 0 bit is darkness.

Signaling convention (FSO and fiber alike): pulse of light = 1, absence = 0.
MEO reference: the GPS constellation, ~30 satellites at ~20,200 km, between
the lower and upper Van Allen belts.

stdlib only. Run: python3 main.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# Speed of light in vacuum (m/s). Real RF/optical free-space links are
# effectively at vacuum speed; fiber drops to ~2/3 c, which is why we do not
# use fiber speed here.
C_VACUUM_M_S = 299_792_458.0
EARTH_RADIUS_KM = 6_371.0


@dataclass(frozen=True)
class Orbit:
    """A named orbital region with altitude above the Earth's surface."""

    name: str
    altitude_km: float
    sats_for_global_coverage: int


# Canonical regions from Tanenbaum Ch. 2, Fig. 2-15.
GEO = Orbit("GEO (geostationary)", 35_800.0, 3)
MEO_GPS = Orbit("MEO (GPS)", 20_200.0, 10)
LEO_IRIDIUM = Orbit("LEO (Iridium)", 750.0, 66)


def propagation_delay(distance_km: float, speed_m_s: float = C_VACUUM_M_S) -> float:
    """One-way propagation delay in milliseconds for a free-space path.

    t = d / c. Distance dominates; bandwidth has no effect on this number.
    """
    if distance_km < 0:
        raise ValueError("distance must be non-negative")
    seconds = (distance_km * 1_000.0) / speed_m_s
    return seconds * 1_000.0


def slant_range(altitude_km: float, elevation_deg: float) -> float:
    """Line-of-sight distance (km) to a satellite seen at a ground elevation.

    Straight overhead (elevation 90 deg) gives exactly the altitude; lower
    elevations give a longer slant path through more atmosphere and distance.
    Uses the law of cosines on the Earth-center / ground-station / satellite
    triangle.
    """
    if not 0.0 < elevation_deg <= 90.0:
        raise ValueError("elevation must be in (0, 90] degrees")
    re = EARTH_RADIUS_KM
    rs = EARTH_RADIUS_KM + altitude_km
    el = math.radians(elevation_deg)
    # Distance from ground station to satellite via law of cosines:
    #   rs^2 = re^2 + d^2 - 2*re*d*cos(90 + el)  ->  solve quadratic for d.
    # cos(90 + el) = -sin(el), so the middle term is +2*re*d*sin(el).
    a = 1.0
    b = 2.0 * re * math.sin(el)
    c = re * re - rs * rs
    disc = b * b - 4.0 * a * c
    d = (-b + math.sqrt(disc)) / (2.0 * a)
    return d


def rtt(distance_km: float, switching_ms: float = 0.0, hops: int = 1) -> float:
    """Round-trip time (ms): 2 * one-way propagation + per-hop switching."""
    if hops < 1:
        raise ValueError("hops must be >= 1")
    one_way = propagation_delay(distance_km)
    return 2.0 * one_way + switching_ms * hops


def watts_to_dbm(power_w: float) -> float:
    """Convert watts to dBm (decibels relative to 1 mW)."""
    if power_w <= 0:
        raise ValueError("power must be positive")
    return 10.0 * math.log10(power_w * 1_000.0)


def fso_link_budget(
    tx_power_w: float,
    divergence_mrad: float,
    distance_m: float,
    rx_aperture_m: float,
    atmospheric_loss_db: float,
    rx_sensitivity_dbm: float,
) -> dict[str, float]:
    """Free-space optics link budget for a rooftop laser link.

    Models geometric (divergence) spreading + atmospheric loss, then compares
    received power against the detector sensitivity to yield a link margin.

    A positive margin means the photodetector can distinguish a light-pulse 1
    from a darkness 0; a negative margin means the link is dark (down).
    """
    if min(tx_power_w, divergence_mrad, distance_m, rx_aperture_m) <= 0:
        raise ValueError("physical inputs must be positive")

    tx_dbm = watts_to_dbm(tx_power_w)

    # Beam radius at the receiver from divergence half-angle (small-angle).
    beam_radius_m = (divergence_mrad / 1_000.0) * distance_m / 2.0
    beam_area = math.pi * beam_radius_m**2
    rx_area = math.pi * (rx_aperture_m / 2.0) ** 2
    # Fraction of beam energy intercepted by the aperture (capped at 1.0).
    capture_fraction = min(1.0, rx_area / beam_area)
    geometric_loss_db = -10.0 * math.log10(capture_fraction)

    rx_dbm = tx_dbm - geometric_loss_db - atmospheric_loss_db
    margin_db = rx_dbm - rx_sensitivity_dbm

    return {
        "tx_dbm": tx_dbm,
        "geometric_loss_db": geometric_loss_db,
        "atmospheric_loss_db": atmospheric_loss_db,
        "rx_dbm": rx_dbm,
        "margin_db": margin_db,
    }


def _print_latency_table() -> None:
    print("Satellite one-way / round-trip latency (straight overhead, vacuum)")
    print(f"{'Region':<22}{'Alt (km)':>10}{'1-way (ms)':>12}{'RTT (ms)':>10}{'Sats':>7}")
    print("-" * 61)
    for orbit in (GEO, MEO_GPS, LEO_IRIDIUM):
        one_way = propagation_delay(orbit.altitude_km)
        round_trip = rtt(orbit.altitude_km)
        print(
            f"{orbit.name:<22}{orbit.altitude_km:>10,.0f}"
            f"{one_way:>12.2f}{round_trip:>10.2f}{orbit.sats_for_global_coverage:>7}"
        )


def _print_slant_demo() -> None:
    print("\nMEO/GPS slant-range latency penalty vs elevation angle (alt 20,200 km)")
    print(f"{'Elevation':>12}{'Slant (km)':>14}{'1-way (ms)':>14}")
    print("-" * 40)
    overhead = propagation_delay(MEO_GPS.altitude_km)
    for el in (90.0, 45.0, 20.0, 10.0):
        d = slant_range(MEO_GPS.altitude_km, el)
        t = propagation_delay(d)
        tag = "  (+%.1f ms)" % (t - overhead) if el != 90.0 else ""
        print(f"{el:>11.0f}{chr(176)}{d:>14,.0f}{t:>14.2f}{tag}")


def _print_fso_demo() -> None:
    print("\nFSO rooftop link budget: 500 m, 2 W laser, 1 mrad beam, 20 cm aperture")
    print(f"{'Weather':<16}{'Atm loss':>10}{'Rx (dBm)':>12}{'Margin':>10}  Verdict")
    print("-" * 60)
    weather = [
        ("clear air", 3.0),
        ("moderate fog", 25.0),
        ("dense fog", 60.0),
    ]
    for name, atm in weather:
        b = fso_link_budget(
            tx_power_w=2.0,
            divergence_mrad=1.0,
            distance_m=500.0,
            rx_aperture_m=0.20,
            atmospheric_loss_db=atm,
            rx_sensitivity_dbm=-30.0,
        )
        verdict = "UP" if b["margin_db"] > 0 else "DOWN (link dark)"
        print(
            f"{name:<16}{atm:>9.1f}dB{b['rx_dbm']:>12.2f}"
            f"{b['margin_db']:>9.2f}dB  {verdict}"
        )


def main() -> None:
    print("=" * 61)
    print("Light & MEO satellite physical-layer calculator")
    print("=" * 61)
    _print_latency_table()
    _print_slant_demo()
    _print_fso_demo()

    print("\nKey takeaways:")
    print(" - GEO RTT (~239 ms) is a speed-of-light floor; no bandwidth fixes it.")
    print(" - MEO/GPS at 20,200 km gives ~67 ms one-way; lower orbit = lower delay.")
    print(" - The FSO link is UP in clear air but goes DARK in dense fog (atm loss).")
    print(" - Lower elevation angles add slant-range distance and extra latency.")


if __name__ == "__main__":
    main()
