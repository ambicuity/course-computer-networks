#!/usr/bin/env python3
"""Transmission-media calculator for Tanenbaum 2.2 (magnetic media, twisted pair, coax).

Stdlib-only, no network calls. Four self-contained calculators:

  1. sneakernet_verdict()  - "station wagon full of tapes" vs. a live link.
  2. cat_lookup()          - Cat 3/5/5e/6/6a/7 bandwidth + Ethernet fit.
  3. compute_reflection()  - reflection coefficient, return loss, VSWR for an
                             impedance mismatch on coax (50 Ohm vs 75 Ohm).
  4. run_budget()          - attenuation (dB) and one-way propagation delay for
                             a copper/coax run of a given length.

Run:  python3 main.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

SPEED_OF_LIGHT_M_S: float = 2.998e8  # c in vacuum, m/s
SECONDS_PER_DAY: int = 86_400


# --------------------------------------------------------------------------- #
# 1. Magnetic media: sneakernet vs. live link                                 #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class ShipmentVerdict:
    data_bytes: int
    link_bps: float
    transit_seconds: float
    network_seconds: float
    sneakernet_throughput_bps: float
    ship: bool

    def explain(self) -> str:
        verb = "SHIP THE DRIVES" if self.ship else "USE THE NETWORK"
        return (
            f"  data {self.data_bytes / 1e12:,.1f} TB | link {self.link_bps / 1e9:,.1f} Gbps\n"
            f"  network time {self.network_seconds / SECONDS_PER_DAY:,.2f} days "
            f"({self.network_seconds:,.0f} s) | transit {self.transit_seconds / 3600:,.1f} h\n"
            f"  sneakernet {self.sneakernet_throughput_bps / 1e9:,.0f} Gbps effective | VERDICT: {verb}"
        )


def sneakernet_verdict(
    data_bytes: int,
    link_bps: float,
    transit_seconds: float = float(SECONDS_PER_DAY),
) -> ShipmentVerdict:
    """Decide whether to physically ship data or send it over a link.

    Ship when the link transfer time V/R exceeds the physical transit time.
    """
    if link_bps <= 0:
        raise ValueError("link_bps must be positive")
    if transit_seconds <= 0:
        raise ValueError("transit_seconds must be positive")

    data_bits = data_bytes * 8
    network_seconds = data_bits / link_bps
    sneakernet_throughput = data_bits / transit_seconds
    return ShipmentVerdict(
        data_bytes=data_bytes,
        link_bps=link_bps,
        transit_seconds=transit_seconds,
        network_seconds=network_seconds,
        sneakernet_throughput_bps=sneakernet_throughput,
        ship=network_seconds > transit_seconds,
    )


def tape_box_capacity_bytes(
    tape_gb: int = 800, tapes_per_box: int = 1000
) -> int:
    """Capacity of a 60x60x60 cm box of LTO/Ultrium tapes, in bytes."""
    return tape_gb * tapes_per_box * 1_000_000_000


# --------------------------------------------------------------------------- #
# 2. Twisted pair: category lookup                                            #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class CableCategory:
    name: str
    bandwidth_mhz: int
    shielded: bool
    ethernet: str


CATEGORIES: dict[str, CableCategory] = {
    "cat3": CableCategory("Cat 3", 16, False, "10BASE-T"),
    "cat5": CableCategory("Cat 5", 100, False, "100BASE-TX (2 of 4 pairs)"),
    "cat5e": CableCategory("Cat 5e", 100, False, "1000BASE-T (4 pairs, both ways)"),
    "cat6": CableCategory("Cat 6", 250, False, "1000BASE-T; 10GBASE-T to 55 m"),
    "cat6a": CableCategory("Cat 6a", 500, False, "10GBASE-T to 100 m"),
    "cat7": CableCategory("Cat 7", 600, True, "10GBASE-T, S/FTP shielded"),
}


def cat_lookup(key: str) -> CableCategory:
    """Look up a twisted-pair category by short key (e.g. 'cat6a')."""
    normalized = key.lower().replace(" ", "").replace("-", "")
    try:
        return CATEGORIES[normalized]
    except KeyError as exc:
        raise KeyError(f"unknown category {key!r}; known: {list(CATEGORIES)}") from exc


# --------------------------------------------------------------------------- #
# 3. Coax: impedance mismatch and reflections                                 #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Reflection:
    z0_ohm: float
    zl_ohm: float
    gamma: float            # reflection coefficient (signed)
    return_loss_db: float   # -20 log10|gamma|; inf at perfect match
    vswr: float             # voltage standing-wave ratio
    power_reflected_pct: float

    def explain(self) -> str:
        rl = "inf (perfect match)" if math.isinf(self.return_loss_db) else f"{self.return_loss_db:.1f} dB"
        return (
            f"  Z0 {self.z0_ohm:g} -> ZL {self.zl_ohm:g} Ohm | gamma {self.gamma:+.3f} "
            f"(V {abs(self.gamma) * 100:.0f}%, P {self.power_reflected_pct:.0f}%)\n"
            f"  return loss {rl} | VSWR {self.vswr:.2f}"
        )


def compute_reflection(z0_ohm: float, zl_ohm: float) -> Reflection:
    """Reflection coefficient, return loss, and VSWR at an impedance step.

    gamma = (ZL - Z0) / (ZL + Z0).  zl_ohm = inf models an open (missing terminator).
    """
    if z0_ohm <= 0:
        raise ValueError("z0_ohm must be positive")
    if math.isinf(zl_ohm):
        gamma = 1.0  # open circuit reflects fully in phase
    else:
        if zl_ohm < 0:
            raise ValueError("zl_ohm must be non-negative")
        gamma = (zl_ohm - z0_ohm) / (zl_ohm + z0_ohm)

    mag = abs(gamma)
    return_loss = math.inf if mag == 0 else -20.0 * math.log10(mag)
    vswr = math.inf if mag == 1.0 else (1 + mag) / (1 - mag)
    return Reflection(
        z0_ohm=z0_ohm,
        zl_ohm=zl_ohm,
        gamma=gamma,
        return_loss_db=return_loss,
        vswr=vswr,
        power_reflected_pct=mag * mag * 100.0,
    )


# --------------------------------------------------------------------------- #
# 4. Run budget: attenuation + propagation delay                              #
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class RunBudget:
    length_m: float
    attenuation_db: float
    power_fraction: float
    one_way_delay_ns: float
    rx_power_dbm: Optional[float]
    passes: Optional[bool]

    def explain(self) -> str:
        rx = "" if self.rx_power_dbm is None else f" | rx {self.rx_power_dbm:.1f} dBm"
        ok = "" if self.passes is None else f" | passes {self.passes}"
        return (
            f"  {self.length_m:g} m | atten {self.attenuation_db:.1f} dB "
            f"(power left {self.power_fraction * 100:.3f}%) | delay {self.one_way_delay_ns:.0f} ns"
            f"{rx}{ok}"
        )


def run_budget(
    length_m: float,
    attenuation_db_per_100m: float,
    velocity_factor: float = 0.66,
    tx_power_dbm: Optional[float] = None,
    rx_sensitivity_dbm: Optional[float] = None,
) -> RunBudget:
    """Attenuation and one-way propagation delay for a cable run."""
    if length_m <= 0:
        raise ValueError("length_m must be positive")
    if not 0 < velocity_factor <= 1:
        raise ValueError("velocity_factor must be in (0, 1]")

    attenuation_db = attenuation_db_per_100m * length_m / 100.0
    power_fraction = 10 ** (-attenuation_db / 10.0)
    delay_s = length_m / (velocity_factor * SPEED_OF_LIGHT_M_S)

    rx_power = None
    passes = None
    if tx_power_dbm is not None:
        rx_power = tx_power_dbm - attenuation_db
        if rx_sensitivity_dbm is not None:
            passes = rx_power >= rx_sensitivity_dbm

    return RunBudget(
        length_m=length_m,
        attenuation_db=attenuation_db,
        power_fraction=power_fraction,
        one_way_delay_ns=delay_s * 1e9,
        rx_power_dbm=rx_power,
        passes=passes,
    )


def main() -> None:
    print("=" * 64)
    print("TRANSMISSION-MEDIA CALCULATOR  (Tanenbaum 2.2)")
    print("=" * 64)

    print("\n[1] MAGNETIC MEDIA -- a station wagon full of tapes")
    box = tape_box_capacity_bytes()
    print(f"  one 60x60x60 cm box = {box / 1e12:,.0f} TB ({box * 8 / 1e15:.1f} Pb)")
    v1 = sneakernet_verdict(box, link_bps=10e9, transit_seconds=SECONDS_PER_DAY)
    print(v1.explain())
    print("\n  ...now only 5 TB on the same 10 Gbps link:")
    v2 = sneakernet_verdict(5_000_000_000_000, link_bps=10e9)
    print(v2.explain())

    print("\n[2] TWISTED PAIR -- category lookup")
    for key in ("cat3", "cat5", "cat5e", "cat6", "cat6a", "cat7"):
        c = cat_lookup(key)
        shield = "S/FTP" if c.shielded else "UTP"
        print(f"  {c.name:6s} {c.bandwidth_mhz:>3d} MHz  {shield:5s}  {c.ethernet}")

    print("\n[3] COAX -- impedance mismatch (50 Ohm part on a 75 Ohm feed)")
    print(compute_reflection(75.0, 50.0).explain())
    print("\n  perfect match (75 -> 75):")
    print(compute_reflection(75.0, 75.0).explain())
    print("\n  missing terminator on a 50 Ohm bus (ZL = open):")
    print(compute_reflection(50.0, math.inf).explain())

    print("\n[4] RUN BUDGET -- 100 m UTP and a 185 m 10BASE2 segment")
    print("  100 m Cat 6a @ 35 dB/100m, VF 0.64, tx 0 dBm, rx -20 dBm:")
    print(run_budget(100, 35.0, 0.64, tx_power_dbm=0.0, rx_sensitivity_dbm=-20.0).explain())
    print("\n  185 m 10BASE2 thinnet, VF 0.66:")
    print(run_budget(185, 8.5, 0.66).explain())
    print("\n" + "=" * 64)


if __name__ == "__main__":
    main()
