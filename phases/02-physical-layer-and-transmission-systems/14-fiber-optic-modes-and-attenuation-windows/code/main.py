"""
Fiber Optic Modes and Attenuation Windows — runnable models.

Stdlib only. No network calls, no pip dependencies.

This module models the three things an engineer actually has to reason
about when sizing an optical link:

  1. Total internal reflection and the acceptance cone (numerical
     aperture, V-number, single- vs multi-mode cutoff at V = 2.405).
  2. Attenuation budget across the three near-IR windows (0.85, 1.30,
     1.55 um) using the textbook dB-per-km definition
     attenuation(dB) = 10 * log10(P_in / P_out), plus connector and
     splice losses.
  3. Chromatic dispersion and the per-bit "temp slot" budget that
     determines the maximum unrepeated span for a given bitrate.

Run:  python3 code/main.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict

# ---------------------------------------------------------------------------
# Physical constants and standard fiber parameters
# ---------------------------------------------------------------------------

SPEED_OF_LIGHT = 2.997_924_58e8  # m/s

# ITU-T G.652 (standard single-mode) nominal parameters.
# Small index difference -> NA ~0.14, which is what real SMF ships with.
G652_CORE_INDEX = 1.4530  # n_core
G652_CLAD_INDEX = 1.4462  # n_clad  (gives NA ~= 0.14)
G652_CORE_RADIUS_UM = 4.1  # micrometres (8.2 um diameter)

# OM4 laser-optimized multimode: larger delta -> NA ~0.20
OM4_CLAD_INDEX = 1.4392  # paired with G652_CORE_INDEX gives NA ~= 0.20

# Reference attenuation coefficients (dB/km) for the three windows.
# Values are the textbook / industry ballpark for silica fiber.
WINDOW_LOSS_DBKM: Dict[float, float] = {
    0.85: 2.5,  # first window: GaAs lasers, short reach
    1.30: 0.38,  # second window: dispersion minimum ~1310 nm
    1.55: 0.22,  # third window: loss minimum, EDFA gain band
}

# Chromatic dispersion (ps/(nm*km)) at each window for G.652
WINDOW_DISP_PSNMKM: Dict[float, float] = {
    0.85: -85.0,
    1.30: 0.0,  # zero-dispersion wavelength sits here
    1.55: 17.0,
}

CONNECTOR_LOSS_DB = 0.35  # typical physical-contact connector pair
SPLICE_LOSS_DB = 0.1  # typical fusion splice
LAUNCH_POWER_DBM = 0.0  # 1 mW
RECEIVER_SENSITIVITY_DBM = -28.0  # 10G PIN receiver, rough

# V-number below which only the fundamental LP01 mode propagates.
SINGLE_MODE_V_CUTOFF = 2.405


# ---------------------------------------------------------------------------
# 1. Modes: numerical aperture, V-number, single-mode cutoff
# ---------------------------------------------------------------------------

def numerical_aperture(n_core: float, n_clad: float) -> float:
    """Fractional light-gathering power NA = sqrt(n_core^2 - n_clad^2)."""
    return math.sqrt(n_core * n_core - n_clad * n_clad)


def critical_angle_deg(n_core: float, n_clad: float) -> float:
    """Smallest angle (from the normal) at which light is totally trapped."""
    return math.degrees(math.asin(n_clad / n_core))


def acceptance_cone_half_angle_deg(n_core: float, n_clad: float) -> float:
    """Half-angle of the external cone that couples into guided modes."""
    na = numerical_aperture(n_core, n_clad)
    return math.degrees(math.asin(min(na, 1.0)))


def v_number(wavelength_um: float, a_um: float,
             n_core: float, n_clad: float) -> float:
    """Normalized frequency V = (2*pi*a/lambda) * NA. V < 2.405 => single mode."""
    na = numerical_aperture(n_core, n_clad)
    return (2.0 * math.pi * a_um / wavelength_um) * na


def cutoff_wavelength_um(a_um: float, n_core: float, n_clad: float) -> float:
    """Wavelength below which the fiber supports more than one mode."""
    na = numerical_aperture(n_core, n_clad)
    return (2.0 * math.pi * a_um * na) / SINGLE_MODE_V_CUTOFF


@dataclass
class ModeReport:
    name: str
    core_radius_um: float
    na: float
    crit_angle_deg: float
    accept_deg: float
    v_at_1550: float
    cutoff_um: float
    single_mode_at_1550: bool


def analyze_fiber(name: str, core_radius_um: float,
                  n_core: float = G652_CORE_INDEX,
                  n_clad: float = G652_CLAD_INDEX) -> ModeReport:
    na = numerical_aperture(n_core, n_clad)
    v1550 = v_number(1.55, core_radius_um, n_core, n_clad)
    return ModeReport(
        name=name,
        core_radius_um=core_radius_um,
        na=na,
        crit_angle_deg=critical_angle_deg(n_core, n_clad),
        accept_deg=acceptance_cone_half_angle_deg(n_core, n_clad),
        v_at_1550=v1550,
        cutoff_um=cutoff_wavelength_um(core_radius_um, n_core, n_clad),
        single_mode_at_1550=v1550 < SINGLE_MODE_V_CUTOFF,
    )


# ---------------------------------------------------------------------------
# 2. Attenuation budget: dB definition + link power budget
# ---------------------------------------------------------------------------

def db_loss(p_in: float, p_out: float) -> float:
    """attenuation(dB) = 10 * log10(P_in / P_out)."""
    if p_out <= 0 or p_in <= 0:
        raise ValueError("powers must be positive")
    return 10.0 * math.log10(p_in / p_out)


def power_out_from_db(p_in: float, loss_db: float) -> float:
    """Inverse of db_loss: recover output power given a dB loss."""
    return p_in / (10.0 ** (loss_db / 10.0))


@dataclass
class LinkBudget:
    window_um: float
    length_km: float
    fiber_loss_db: float
    connector_loss_db: float
    splice_loss_db: float
    total_loss_db: float
    received_dbm: float
    margin_db: float


def link_budget(window_um: float, length_km: float,
                n_connectors: int = 2, n_splices: int = 0,
                launch_dbm: float = LAUNCH_POWER_DBM,
                sensitivity_dbm: float = RECEIVER_SENSITIVITY_DBM) -> LinkBudget:
    alpha = WINDOW_LOSS_DBKM[window_um]
    fiber = alpha * length_km
    conn = n_connectors * CONNECTOR_LOSS_DB
    spl = n_splices * SPLICE_LOSS_DB
    total = fiber + conn + spl
    rx = launch_dbm - total
    return LinkBudget(
        window_um=window_um,
        length_km=length_km,
        fiber_loss_db=fiber,
        connector_loss_db=conn,
        splice_loss_db=spl,
        total_loss_db=total,
        received_dbm=rx,
        margin_db=rx - sensitivity_dbm,
    )


def max_span_km(window_um: float,
                launch_dbm: float = LAUNCH_POWER_DBM,
                sensitivity_dbm: float = RECEIVER_SENSITIVITY_DBM,
                n_connectors: int = 2) -> float:
    """Longest span before received power hits sensitivity (power-budget limit)."""
    alpha = WINDOW_LOSS_DBKM[window_um]
    available = (launch_dbm - sensitivity_dbm) - n_connectors * CONNECTOR_LOSS_DB
    return available / alpha if alpha > 0 else float("inf")


# ---------------------------------------------------------------------------
# 3. Dispersion limit: bit-period slot budget
# ---------------------------------------------------------------------------

@dataclass
class DispersionReport:
    window_um: float
    bitrate_gbps: float
    spectral_width_nm: float
    length_km: float
    pulse_spread_ps: float
    bit_period_ps: float
    spread_vs_bit: float  # spread / bit period
    max_km_for_30pct: float  # span where spread == 30% of bit period


def dispersion_limit(window_um: float, bitrate_gbps: float,
                     spectral_width_nm: float, length_km: float) -> DispersionReport:
    """Chromatic-dispersion pulse broadening: dT = |D| * L * dLambda."""
    d = WINDOW_DISP_PSNMKM[window_um]
    spread_ps = abs(d) * length_km * spectral_width_nm  # ps
    bit_period_ps = 1e12 / (bitrate_gbps * 1e9)  # ps per bit
    spread_vs_bit = spread_ps / bit_period_ps if bit_period_ps else 0.0
    if d != 0 and spectral_width_nm > 0:
        max_km = (0.30 * bit_period_ps) / (abs(d) * spectral_width_nm)
    else:
        max_km = float("inf")
    return DispersionReport(
        window_um=window_um,
        bitrate_gbps=bitrate_gbps,
        spectral_width_nm=spectral_width_nm,
        length_km=length_km,
        pulse_spread_ps=spread_ps,
        bit_period_ps=bit_period_ps,
        spread_vs_bit=spread_vs_bit,
        max_km_for_30pct=max_km,
    )


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def _print_modes() -> None:
    print("=" * 68)
    print("1. MODES  -- total internal reflection & single-mode cutoff")
    print("=" * 68)
    for r in (analyze_fiber("Single-mode G.652", G652_CORE_RADIUS_UM),
              analyze_fiber("Multimode OM4 (50 um core)", 25.0,
                            n_clad=OM4_CLAD_INDEX)):
        print(f"\n  {r.name}")
        print(f"    core radius        : {r.core_radius_um:6.2f} um")
        print(f"    numerical aperture : {r.na:.4f}")
        print(f"    critical angle     : {r.crit_angle_deg:6.2f} deg (from normal)")
        print(f"    acceptance cone    : {r.accept_deg:6.2f} deg half-angle")
        print(f"    V-number @1.55um   : {r.v_at_1550:8.2f}   (<2.405 => single mode)")
        print(f"    cutoff wavelength  : {r.cutoff_um:6.2f} um")
        print(f"    single-mode @1550? : {r.single_mode_at_1550}")


def _print_db() -> None:
    print("\n" + "=" * 68)
    print("2. ATTENUATION  -- the dB definition and a power budget")
    print("=" * 68)
    print(f"\n  Sanity: half the power -> {db_loss(2.0, 1.0):.2f} dB"
          f"  (textbook says 3 dB)")
    print(f"\n  40 km link, 2 connectors, launched at {LAUNCH_POWER_DBM} dBm, "
          f"receiver needs >= {RECEIVER_SENSITIVITY_DBM} dBm:")
    print(f"  {'window':>8} {'a(dB/km)':>9} {'fiber':>7} {'conn':>6} "
          f"{'total':>7} {'rx(dBm)':>8} {'margin':>7}")
    for w in (0.85, 1.30, 1.55):
        b = link_budget(w, 40.0)
        print(f"  {w:>6.2f}um {WINDOW_LOSS_DBKM[w]:>8.2f} "
              f"{b.fiber_loss_db:>6.2f} {b.connector_loss_db:>5.2f} "
              f"{b.total_loss_db:>6.2f} {b.received_dbm:>7.2f} "
              f"{b.margin_db:>6.2f}")


def _print_span() -> None:
    print("\n" + "=" * 68)
    print("   Max unrepeated span by window (power budget only):")
    print("=" * 68)
    for w in (0.85, 1.30, 1.55):
        print(f"    {w:>5.2f} um : {max_span_km(w):7.1f} km")


def _print_dispersion() -> None:
    print("\n" + "=" * 68)
    print("3. DISPERSION  -- chromatic broadening vs the bit slot")
    print("=" * 68)
    print("\n  10 Gbps laser, 0.1 nm linewidth (narrow), over 80 km:")
    print(f"  {'window':>8} {'D(ps/nm/km)':>12} {'spread(ps)':>11} "
          f"{'bit(ps)':>9} {'spread/bit':>11} {'max km(30%)':>12}")
    for w in (0.85, 1.30, 1.55):
        r = dispersion_limit(w, 10.0, 0.1, 80.0)
        print(f"  {w:>6.2f}um {WINDOW_DISP_PSNMKM[w]:>10.1f} "
              f"{r.pulse_spread_ps:>10.1f} {r.bit_period_ps:>8.1f} "
              f"{r.spread_vs_bit:>10.3%} {r.max_km_for_30pct:>11.1f}")
    print("\n  The 1.30 um window has D ~= 0, so dispersion is not the limiter")
    print("  there -- loss is. At 1.55 um, D = 17 forces dispersion-shifted or")
    print("  compensated fiber, or a narrower laser, for long 10G spans.")


def main() -> None:
    _print_modes()
    _print_db()
    _print_span()
    _print_dispersion()
    print("\nDone.")


if __name__ == "__main__":
    main()
