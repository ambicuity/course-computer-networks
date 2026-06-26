"""802.11 physical-layer data-rate calculator and PHY identifier.

This module reconstructs the published 802.11b/a/g/n data rates from their
underlying physical-layer parameters instead of hard-coding a lookup table:

  * 802.11b (DSSS): an 11-chip Barker sequence at 11 Mchips/s with BPSK/QPSK
    for 1/2 Mbps, and CCK (Complementary Code Keying) 8-chip codes carrying
    4 or 8 bits for 5.5/11 Mbps -- all in the 2.4-GHz ISM band.
  * 802.11a (OFDM): 52 subcarriers (48 data + 4 pilot), 4-microsecond symbols,
    1/2/4/6 bits per subcarrier (BPSK/QPSK/16-QAM/64-QAM) coded at 1/2, 2/3,
    or 3/4 -- eight rates from 6 to 54 Mbps in the 5-GHz band.
  * 802.11g: the same OFDM as 802.11a but in the 2.4-GHz band.
  * 802.11n: 802.11a/g OFDM scaled by channel width (20/40 MHz) and the number
    of MIMO spatial streams (1..4), reaching up to 600 Mbps.

It also identifies which PHY a captured frame is likely using from the band,
observed data rate, channel width, and spatial-stream count -- the same
reasoning an engineer applies to a Wireshark radiotap header.

Stdlib only. No network calls. Run: python3 main.py
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

# --- 802.11b DSSS constants ---------------------------------------------------
CHIP_RATE_MCHIPS = 11.0          # 11 Mchips/s
BARKER_LEN = 11                  # 11-chip Barker spreading sequence
CCK_CODE_LEN = 8                 # 8-chip CCK codes for 5.5 and 11 Mbps

# --- 802.11a/g OFDM constants -------------------------------------------------
OFDM_DATA_SUBCARRIERS = 48       # of 52 total; the other 4 are pilots
OFDM_SYMBOL_US = 4.0             # symbol duration in microseconds

# Modulation -> bits carried per subcarrier (per chip for DSSS BPSK/QPSK)
BITS_PER_SYMBOL = {"BPSK": 1, "QPSK": 2, "16-QAM": 4, "64-QAM": 6}


@dataclass(frozen=True)
class Phy:
    """One physical-layer operating point."""

    standard: str
    band_ghz: float
    mbps: float
    detail: str


def b_barker_rate(modulation: str) -> float:
    """802.11b rate using the 11-chip Barker sequence (1 or 2 Mbps).

    bits/chip = bits_per_symbol(modulation); chips/bit = 11.
    rate = chip_rate / Barker_len * bits_per_symbol.
    """
    bits = BITS_PER_SYMBOL[modulation]
    return CHIP_RATE_MCHIPS / BARKER_LEN * bits


def b_cck_rate(bits_per_code: int) -> float:
    """802.11b CCK rate (5.5 or 11 Mbps): bits_per_code per 8-chip code."""
    codes_per_sec = CHIP_RATE_MCHIPS / CCK_CODE_LEN  # Mcodes/s
    return codes_per_sec * bits_per_code


def ofdm_rate(modulation: str, code_rate: float,
              width_mhz: int = 20, streams: int = 1) -> float:
    """OFDM data rate for 802.11a/g (and n when scaled).

    bits/symbol = data_subcarriers * bits_per_subcarrier * code_rate
    rate(Mbps)  = bits/symbol / symbol_duration_us
    802.11n scales subcarriers by channel width and multiplies by streams.
    """
    # A 40-MHz channel roughly doubles usable data subcarriers (48 -> 108);
    # we model the standard's published scaling factor.
    subcarriers = OFDM_DATA_SUBCARRIERS if width_mhz == 20 else 108
    bits = BITS_PER_SYMBOL[modulation]
    bits_per_symbol = subcarriers * bits * code_rate
    return bits_per_symbol / OFDM_SYMBOL_US * streams


def build_11b() -> list[Phy]:
    return [
        Phy("802.11b", 2.4, b_barker_rate("BPSK"), "Barker-11 + BPSK, 1 bit/11 chips"),
        Phy("802.11b", 2.4, b_barker_rate("QPSK"), "Barker-11 + QPSK, 2 bits/11 chips"),
        Phy("802.11b", 2.4, b_cck_rate(4), "CCK, 4 bits/8-chip code"),
        Phy("802.11b", 2.4, b_cck_rate(8), "CCK, 8 bits/8-chip code"),
    ]


def build_11ag(standard: str, band: float) -> list[Phy]:
    """The eight OFDM rates shared by 802.11a (5 GHz) and 802.11g (2.4 GHz)."""
    combos = [
        ("BPSK", 1 / 2), ("BPSK", 3 / 4),
        ("QPSK", 1 / 2), ("QPSK", 3 / 4),
        ("16-QAM", 1 / 2), ("16-QAM", 3 / 4),
        ("64-QAM", 2 / 3), ("64-QAM", 3 / 4),
    ]
    out: list[Phy] = []
    for mod, rate in combos:
        mbps = ofdm_rate(mod, rate)
        out.append(Phy(standard, band, mbps, f"OFDM {mod} R={rate:.2f}"))
    return out


def build_11n() -> list[Phy]:
    """Selected 802.11n points: 64-QAM 3/4 across width x streams."""
    out: list[Phy] = []
    for width in (20, 40):
        for streams in (1, 2, 3, 4):
            mbps = ofdm_rate("64-QAM", 5 / 6, width_mhz=width, streams=streams)
            out.append(
                Phy("802.11n", 2.4, round(mbps, 1),
                    f"OFDM 64-QAM R=0.83, {width} MHz, {streams} stream(s)")
            )
    return out


def identify_phy(band_ghz: float, mbps: float,
                 width_mhz: int = 20, streams: int = 1) -> str:
    """Infer the likely PHY from observed evidence (radiotap-style facts)."""
    if streams > 1 or width_mhz > 20:
        return "802.11n (MIMO / wide channel signature)"
    if mbps in (1.0, 2.0, 5.5, 11.0):
        return "802.11b (DSSS/CCK rate set)"
    if 6.0 <= mbps <= 54.0:
        return "802.11a (5 GHz OFDM)" if band_ghz >= 5.0 else "802.11g (2.4 GHz OFDM)"
    return "unknown"


def _print_table(title: str, rows: list[Phy]) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    print(f"{'Std':<9}{'Band':>6}  {'Mbps':>7}  Detail")
    for p in rows:
        print(f"{p.standard:<9}{p.band_ghz:>5.1f}G  {p.mbps:>7.1f}  {p.detail}")


def main() -> None:
    print("802.11 PHYSICAL-LAYER RATE RECONSTRUCTION")
    print("=========================================")

    _print_table("802.11b -- 2.4 GHz DSSS (Barker + CCK)", build_11b())
    _print_table("802.11a -- 5 GHz OFDM", build_11ag("802.11a", 5.0))
    _print_table("802.11g -- 2.4 GHz OFDM (a-compatible)", build_11ag("802.11g", 2.4))
    _print_table("802.11n -- MIMO + wide channels", build_11n())

    print("\nWORKED CHECK: 802.11a 54 Mbps")
    print("  48 data subcarriers x 6 bits (64-QAM) x 3/4 code / 4 us")
    print(f"  = {ofdm_rate('64-QAM', 3/4):.1f} Mbps")

    print("\nPHY IDENTIFICATION FROM A CAPTURE")
    print("---------------------------------")
    samples = [
        (2.4, 11.0, 20, 1),
        (5.0, 54.0, 20, 1),
        (2.4, 24.0, 20, 1),
        (5.0, 300.0, 40, 2),
    ]
    for band, rate, width, streams in samples:
        phy = identify_phy(band, rate, width, streams)
        print(f"  band={band:>3}GHz rate={rate:>6.1f}Mbps "
              f"width={width}MHz streams={streams} -> {phy}")

    print("\nRANGE / INTERFERENCE TRADE-OFF")
    print("------------------------------")
    print("  2.4 GHz: ~7x the range of 5 GHz (802.11b vs 802.11a), but crowded")
    print("           (microwaves, cordless phones, Bluetooth, garage openers).")
    print("  5.0 GHz: cleaner spectrum, more channels, shorter reach.")


if __name__ == "__main__":
    main()
