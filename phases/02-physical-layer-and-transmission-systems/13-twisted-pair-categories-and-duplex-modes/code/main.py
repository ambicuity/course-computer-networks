"""Twisted-pair categories, duplex modes, and IEEE 802.3 auto-negotiation.

Stdlib-only model of:
  * the TIA/ISO category table (bandwidth, shielding, max PHY, ACR-limited reach),
  * per-PHY pair usage for 10/100/1000/10GBASE-T,
  * the clause-28 auto-negotiation priority resolution,
  * 10GBASE-T reach estimation from alien-crosstalk margin.

No network calls, no third-party packages. Run: python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Tuple


# --- Category table ---------------------------------------------------------

@dataclass(frozen=True)
class Category:
    name: str
    bandwidth_mhz: int
    shielding: str          # XX/YTP code
    max_phy: str
    ten_g_reach_m: int      # 0 if 10GBASE-T not supported
    notes: str


CATEGORIES: Tuple[Category, ...] = (
    Category("Cat 3",   16,   "UTP",    "10BASE-T",         0,  "Legacy voice; 2-3 twists/m"),
    Category("Cat 5",   100,  "UTP",    "1000BASE-T",       0,  "Superseded by 5e"),
    Category("Cat 5e",  100,  "UTP",    "1000BASE-T",       0,  "100 m 1G; office default"),
    Category("Cat 6",   250,  "U/UTP",  "10GBASE-T",       55,  "10G to 37-55 m; mixed pitch"),
    Category("Cat 6A",  500,  "U/FTP",  "10GBASE-T",      100,  "10G full 100 m; PSANEXT rated"),
    Category("Cat 7",   600,  "S/FTP",  "10GBASE-T",      100,  "Per-pair foil + braid"),
    Category("Cat 7A",  1000, "S/FTP",  "10GBASE-T",      100,  "Class Fa; 1 GHz"),
    Category("Cat 8.1", 2000, "U/FTP",  "40GBASE-T",       30,  "25/40G switch-to-switch"),
    Category("Cat 8.2", 2000, "S/FTP",  "40GBASE-T",       30,  "Shielded 25/40G"),
)


# --- PHY / pair usage -------------------------------------------------------

@dataclass(frozen=True)
class Phy:
    name: str
    speed_mbps: int
    pairs_used: int
    duplex_modes: FrozenSet[str]
    baud_msym: int
    line_code: str


PHYS: Tuple[Phy, ...] = (
    Phy("10BASE-T",    10,   2, frozenset({"half", "full"}),   10,  "Manchester"),
    Phy("100BASE-TX",  100,  2, frozenset({"half", "full"}),  125,  "MLT-3, 4B5B"),
    Phy("1000BASE-T",  1000, 4, frozenset({"full"}),          125,  "PAM-5, Trellis"),
    Phy("10GBASE-T",   10000, 4, frozenset({"full"}),         800,  "PAM-16, DSQ128"),
)

PAIR_USAGE: Dict[str, Dict[int, str]] = {
    "10/100BASE-T": {1: "TX+", 2: "TX-", 3: "RX+", 6: "RX-"},
    "1000BASE-T":   {1: "BI_DA+", 2: "BI_DA-", 3: "BI_DB+",
                     6: "BI_DB-", 4: "BI_DC+", 5: "BI_DC-",
                     7: "BI_DD+", 8: "BI_DD-"},
}

# RJ-45 T568B pin -> (pair, color)
T568B: Dict[int, Tuple[str, str]] = {
    1: ("pair2", "white/orange"),
    2: ("pair2", "orange"),
    3: ("pair3", "white/green"),
    6: ("pair3", "green"),
    4: ("pair1", "blue"),
    5: ("pair1", "white/blue"),
    7: ("pair4", "white/brown"),
    8: ("pair4", "brown"),
}


# --- Auto-negotiation (clause 28) -------------------------------------------

# Technology Ability Field bit -> (mode, duplex), with priority rank (1=best)
ABILITY_BITS: List[Tuple[int, str, str, int]] = [
    (0, "10BASE-T",       "half", 7),
    (1, "10BASE-T",       "full", 6),
    (2, "100BASE-TX",     "half", 5),
    (3, "100BASE-TX",     "full", 3),
    (5, "100BASE-T4",     "half", 4),
]
# 1000BASE-T abilities arrive via a Next-Page word; model with rank too.
NEXT_PAGE_BITS: List[Tuple[int, str, str, int]] = [
    (0, "1000BASE-T", "full", 1),
    (1, "1000BASE-T", "half", 2),
]


def advertised_modes(base_word: int, np_word: int) -> List[Tuple[str, str, int]]:
    """Decode ability bits into (phy, duplex, rank)."""
    out: List[Tuple[str, str, int]] = []
    for bit, phy, dx, rank in ABILITY_BITS:
        if base_word & (1 << bit):
            out.append((phy, dx, rank))
    for bit, phy, dx, rank in NEXT_PAGE_BITS:
        if np_word & (1 << bit):
            out.append((phy, dx, rank))
    return out


def resolve_auto_neg(local: int, local_np: int,
                     remote: int, remote_np: int,
                     forced: Tuple[str, str] | None = None
                     ) -> Tuple[str, str, str]:
    """Return (chosen_phy, chosen_duplex, status).

    If `forced` is set on the local side, auto-neg is disabled there; the
    remote falls back to parallel detection (10BASE-T half-duplex default),
    which is the classic duplex-mismatch trap.
    """
    if forced is not None:
        f_phy, f_dx = forced
        det_phy = f_phy if f_phy in ("10BASE-T", "100BASE-TX") else "10BASE-T"
        det_dx = "half"
        status = ("DUPLEX_MISMATCH" if f_dx != det_dx
                  else f"FORCED/{det_phy} matched")
        return f_phy, f_dx, status
    a = advertised_modes(local, local_np)
    b = advertised_modes(remote, remote_np)
    local_set = {(phy, dx): rank for phy, dx, rank in a}
    remote_set = {(phy, dx): rank for phy, dx, rank in b}
    common = [(phy, dx, local_set[(phy, dx)])
              for (phy, dx) in local_set if (phy, dx) in remote_set]
    if not common:
        return "10BASE-T", "half", "NO_COMMON -> fallback 10/half"
    common.sort(key=lambda t: t[2])           # lower rank = higher priority
    phy, dx, _ = common[0]
    return phy, dx, "OK"


# --- 10GBASE-T reach from alien crosstalk margin ----------------------------

# Reference insertion loss per meter (dB/m) at 500 MHz, by category.
INS_LOSS_DB_PER_M: Dict[str, float] = {
    "Cat 6": 0.230, "Cat 6A": 0.180, "Cat 7": 0.160,
    "Cat 7A": 0.150, "Cat 8.1": 0.140, "Cat 8.2": 0.130,
}
# ACR floor (dB) at the PHY's operating margin for 10GBASE-T.
ACR_FLOOR_DB = 6.0
# Alien crosstalk coupling (dB per 30 m of bundled exposure).
ALIEN_XT_DB_PER_30M = 3.0


def ten_gb_reach(cat_name: str) -> int:
    """Acr-limited 10GBASE-T reach in meters (integer)."""
    if cat_name not in INS_LOSS_DB_PER_M:
        return 0
    loss = INS_LOSS_DB_PER_M[cat_name]
    per_m = loss + ALIEN_XT_DB_PER_30M / 30.0
    ceiling = {"Cat 6": 55, "Cat 6A": 100, "Cat 7": 100,
               "Cat 7A": 100, "Cat 8.1": 30, "Cat 8.2": 30}[cat_name]
    acr_bound = ACR_FLOOR_DB / per_m
    return min(ceiling, int(acr_bound))


# --- Demo -------------------------------------------------------------------

def _print_categories() -> None:
    print("TIA/ISO category table")
    print("=" * 92)
    print(f"{'Cat':8} {'BW(MHz)':>9} {'Shield':8} {'Max PHY':12} "
          f"{'10G reach':>10}  Notes")
    print("-" * 92)
    for c in CATEGORIES:
        reach = f"{c.ten_g_reach_m} m" if c.ten_g_reach_m else "n/a"
        print(f"{c.name:8} {c.bandwidth_mhz:>9} {c.shielding:8} "
              f"{c.max_phy:12} {reach:>10}  {c.notes}")


def _print_phys() -> None:
    print("\nEthernet PHY pair usage and duplex support")
    print("=" * 70)
    print(f"{'PHY':14} {'Mbps':>6} {'Pairs':>6} {'Baud(M)':>8} "
          f"{'Duplex':14} {'Line code'}")
    print("-" * 70)
    for p in PHYS:
        dx = ",".join(sorted(p.duplex_modes))
        print(f"{p.name:14} {p.speed_mbps:>6} {p.pairs_used:>6} "
              f"{p.baud_msym:>8} {dx:14} {p.line_code}")


def _print_pairmap() -> None:
    print("\nRJ-45 T568B pinout and per-PHY pair assignment")
    print("=" * 60)
    for pin in sorted(T568B):
        pair, color = T568B[pin]
        fast = PAIR_USAGE["10/100BASE-T"].get(pin, "-")
        gig = PAIR_USAGE["1000BASE-T"][pin]
        print(f"pin {pin}: {color:16} {fast:8} {gig}")


def _print_autoneg() -> None:
    print("\nClause 28 auto-negotiation resolution")
    print("=" * 60)
    a_base = (1 << 1) | (1 << 3)            # bits 1 (10-full), 3 (100-full)
    a_np = (1 << 0)                         # 1000BASE-T full (next page)
    b_base = (1 << 0) | (1 << 2) | (1 << 3)  # 10-half, 100-half, 100-full
    b_np = 0
    phy, dx, status = resolve_auto_neg(a_base, a_np, b_base, b_np)
    print("Side A abilities: 10/full, 100/full, 1000/full")
    print("Side B abilities: 10/half, 100/half, 100/full")
    print(f"Resolved -> {phy} {dx}   [{status}]")

    print("\nDuplex-mismatch trap (one side forced 100/full):")
    f_phy, f_dx, status = resolve_auto_neg(0, 0, b_base, b_np,
                                           forced=("100BASE-TX", "full"))
    print(f"Forced side: {f_phy} {f_dx}")
    print("Auto side (parallel detection): 100BASE-TX half")
    print(f"Result: {status}  (forced=full vs detected=half)")


def _print_reach() -> None:
    print("\n10GBASE-T ACR-limited reach by category")
    print("=" * 50)
    print(f"{'Cat':8} {'Reach (m)':>10}")
    for c in ("Cat 6", "Cat 6A", "Cat 7", "Cat 7A", "Cat 8.1", "Cat 8.2"):
        print(f"{c:8} {ten_gb_reach(c):>10}")


def main() -> None:
    _print_categories()
    _print_phys()
    _print_pairmap()
    _print_autoneg()
    _print_reach()


if __name__ == "__main__":
    main()
