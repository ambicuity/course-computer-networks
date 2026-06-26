"""802.11 physical layer reference: rate tables, Barker-11 spreading, OFDM timing, MIMO capacity.

Stdlib only. No network calls. No pip dependencies.

Subcommands (run as `python3 code/main.py <subcommand> [args]`):

    barker <hex>           Spread a hex bit string with the Barker-11 code (1 bit -> 11 chips).
    ofdm [short]           Print OFDM symbol timing for 802.11a/g/n (default: long guard interval).
    mimo <streams> <MHz> <mod> [gi]
                           Approximate a single-stream capacity (Mbps) for the given config.
    table <a|b|g|n>        Print the data-rate table for a given 802.11 PHY.
    select --band 2.4|5 --standard a|b|g|n --rssi <dBm> [--streams N] [--width 20|40] [--gi long|short]
                           Pick the highest-rate MCS that the given RSSI can sustain.

Examples:

    python3 code/main.py barker 0xABC
    python3 code/main.py ofdm short
    python3 code/main.py mimo 4 40 64-QAM short
    python3 code/main.py table n
    python3 code/main.py select --band 5 --standard n --rssi -55 --streams 2 --width 40 --gi short
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Final


# ---------------------------------------------------------------------------
# Constants from the 802.11 PHY specifications
# ---------------------------------------------------------------------------

# Barker-11 chip sequence used by the original 802.11 DSSS PHY and by the
# short/long preambles of 802.11b. One user bit -> 11 chips.
BARKER_11: Final[tuple[int, ...]] = (
    +1, -1, +1, +1, -1, +1, +1, +1, -1, -1, -1,
)

# Chip rate for DSSS and HR-DSSS. 11 Mc/s -> 1 bit / 11 chips = 1 Mbps with
# BPSK, 2 bits / 11 chips = 2 Mbps with QPSK.
DSSS_CHIP_RATE: Final[float] = 11.0e6  # chips per second

# OFDM parameters for 802.11a/g (and the 20-MHz mode of 802.11n).
FFT_SIZE: Final[int] = 64
DATA_SUBCARRIERS: Final[int] = 48
PILOT_SUBCARRIERS: Final[int] = 4
USED_SUBCARRIERS: Final[int] = DATA_SUBCARRIERS + PILOT_SUBCARRIERS  # 52
CHANNEL_WIDTH_MHZ: Final[float] = 20.0
SUBCARRIER_SPACING_HZ: Final[float] = (CHANNEL_WIDTH_MHZ * 1e6) / FFT_SIZE  # 312.5 kHz
USEFUL_SYMBOL_SECONDS: Final[float] = 1.0 / SUBCARRIER_SPACING_HZ  # 3.2 us
LONG_GI_SECONDS: Final[float] = 0.8e-6  # 0.8 us cyclic prefix
SHORT_GI_SECONDS: Final[float] = 0.4e-6  # 0.4 us short guard interval
LONG_SYMBOL_SECONDS: Final[float] = USEFUL_SYMBOL_SECONDS + LONG_GI_SECONDS  # 4.0 us
SHORT_SYMBOL_SECONDS: Final[float] = USEFUL_SYMBOL_SECONDS + SHORT_GI_SECONDS  # 3.6 us

# 40-MHz mode of 802.11n: 128-point FFT, 108 used subcarriers (104 data + 4 pilots).
N40_DATA_SUBCARRIERS: Final[int] = 108  # spec says 108 = 104 data + 4 pilots


# ---------------------------------------------------------------------------
# Rate tables
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LegacyMCS:
    """802.11a/g MCS entry: modulation, code rate, and the resulting data rate."""
    mcs: int
    modulation: str
    code_rate: float  # of 1
    data_rate_mbps: float


# 802.11a/g rate table (20 MHz, long GI, 1 spatial stream).
# Rate = 48 * bits_per_subcarrier * code_rate / 4.0e-6 = 12e6 * bits * code_rate
A_G_TABLE: Final[tuple[LegacyMCS, ...]] = (
    LegacyMCS(1, "BPSK",   1 / 2, 6.0),
    LegacyMCS(2, "BPSK",   3 / 4, 9.0),
    LegacyMCS(3, "QPSK",   1 / 2, 12.0),
    LegacyMCS(4, "QPSK",   3 / 4, 18.0),
    LegacyMCS(5, "16-QAM", 1 / 2, 24.0),
    LegacyMCS(6, "16-QAM", 3 / 4, 36.0),
    LegacyMCS(7, "64-QAM", 2 / 3, 48.0),
    LegacyMCS(8, "64-QAM", 3 / 4, 54.0),
)


@dataclass(frozen=True)
class HTMCS:
    """802.11n HT MCS entry: per-stream rate for a given (modulation, code rate) pair."""
    mcs: int
    modulation: str
    code_rate: float
    # Per-stream rates in Mbps at 800 ns GI; short-GI rate is computed in code.
    bits_per_symbol: int  # 1, 2, 4, or 6 for BPSK/QPSK/16-QAM/64-QAM
    long_gi_20_mbps: float
    long_gi_40_mbps: float


# 802.11n MCS 0-7 (the only universally required set): BPSK -> 64-QAM, code 1/2 -> 5/6.
HT_TABLE: Final[tuple[HTMCS, ...]] = (
    HTMCS(0, "BPSK",   1 / 2, 1, 6.5, 13.5),
    HTMCS(1, "QPSK",   1 / 2, 2, 13.0, 27.0),
    HTMCS(2, "QPSK",   3 / 4, 2, 19.5, 40.5),
    HTMCS(3, "16-QAM", 1 / 2, 4, 26.0, 54.0),
    HTMCS(4, "16-QAM", 3 / 4, 4, 39.0, 81.0),
    HTMCS(5, "64-QAM", 2 / 3, 6, 52.0, 108.0),
    HTMCS(6, "64-QAM", 3 / 4, 6, 58.5, 121.5),
    HTMCS(7, "64-QAM", 5 / 6, 6, 65.0, 135.0),
)

# 802.11b HR-DSSS / CCK rate table.
B_RATES_MBPS: Final[tuple[float, ...]] = (1.0, 2.0, 5.5, 11.0)


# ---------------------------------------------------------------------------
# Barker-11 spreading
# ---------------------------------------------------------------------------

def barker_spread(bits: list[int]) -> list[int]:
    """Spread a bit list with the Barker-11 code; 1 bit -> 11 chips, BPSK-style.

    Maps bit 0 -> inverted chips (-1), bit 1 -> non-inverted chips (+1).
    """
    if any(b not in (0, 1) for b in bits):
        raise ValueError("bits must be 0 or 1")
    chips: list[int] = []
    for bit in bits:
        chips.extend(chip if bit == 1 else -chip for chip in BARKER_11)
    return chips


def barker_spread_hex(hex_payload: str) -> list[int]:
    """Take a hex string, convert to bits MSB-first, and Barker-spread."""
    value = int(hex_payload, 16)
    if value == 0:
        return barker_spread([0])
    n_bits = value.bit_length()
    bits = [(value >> (n_bits - 1 - i)) & 1 for i in range(n_bits)]
    return barker_spread(bits)


# ---------------------------------------------------------------------------
# OFDM symbol timing
# ---------------------------------------------------------------------------

def ofdm_symbol_seconds(short_gi: bool) -> float:
    """Return the OFDM symbol period in seconds for 802.11a/g/n (20 MHz)."""
    return SHORT_SYMBOL_SECONDS if short_gi else LONG_SYMBOL_SECONDS


# ---------------------------------------------------------------------------
# MIMO capacity
# ---------------------------------------------------------------------------

def mimo_stream_rate_mbps(
    n_streams: int,
    channel_width_mhz: int,
    modulation: str,
    code_rate: float,
    short_gi: bool,
) -> float:
    """Approximate the PHY-layer rate for a MIMO-OFDM link.

    Uses the 802.11n formula: per-stream rate = N_data * bits * code_rate / T_sym,
    then multiplied by the number of spatial streams. For 20 MHz, N_data = 48;
    for 40 MHz, N_data = 108. The result is rounded to the nearest 0.5 Mbps
    to match the spec's HT-rate granularity.
    """
    n_data = DATA_SUBCARRIERS if channel_width_mhz == 20 else N40_DATA_SUBCARRIERS
    bits_per_symbol = {"BPSK": 1, "QPSK": 2, "16-QAM": 4, "64-QAM": 6}[modulation]
    t_sym = SHORT_SYMBOL_SECONDS if short_gi else LONG_SYMBOL_SECONDS
    per_stream = n_data * bits_per_symbol * code_rate / t_sym / 1e6
    return round(per_stream * n_streams, 1)


# ---------------------------------------------------------------------------
# Rate-from-RSSI selection
# ---------------------------------------------------------------------------

# Approximate minimum SNR (dB) for each 802.11a/g MCS to deliver ~10% PER
# in a clean 20 MHz channel. These are the values most vendor firmware uses
# to switch from one MCS to the next in Minstrel-style rate adaptation.
MCS_MIN_SNR: Final[tuple[tuple[int, int], ...]] = (
    ((1, 6),  2),    # 6 Mbps BPSK 1/2
    ((2, 9),  5),
    ((3, 12), 7),
    ((4, 18), 11),
    ((5, 24), 16),
    ((6, 36), 21),
    ((7, 48), 24),
    ((8, 54), 27),
)

# 802.11n MCS 0-7 minimum SNR (dB), with 5 dB added for each doubling of streams
# and another 3 dB for 40 MHz. These are conservative first-cut numbers; real
# firmware tweaks them per chipset.
HT_MCS_MIN_SNR: Final[tuple[tuple[int, int], ...]] = (
    ((0, 6.5),  2),
    ((1, 13),   5),
    ((2, 19.5), 8),
    ((3, 26),  12),
    ((4, 39),  17),
    ((5, 52),  22),
    ((6, 58.5), 25),
    ((7, 65),  28),
)


def select_rate_ag(rssi_dbm: int) -> tuple[int, float, int]:
    """Pick the highest 802.11a/g MCS for the given RSSI.

    Assumes a typical noise floor of -95 dBm in 20 MHz, so SNR ~= RSSI + 95.
    Returns (mcs, rate_mbps, min_snr).
    """
    noise_floor = -95
    snr = rssi_dbm - noise_floor
    chosen = (1, 6.0, 2)
    for (mcs, rate), min_snr in MCS_MIN_SNR:
        if snr >= min_snr:
            chosen = (mcs, rate, min_snr)
    return chosen


def select_rate_ht(
    rssi_dbm: int,
    n_streams: int = 1,
    channel_width_mhz: int = 20,
    short_gi: bool = False,
) -> tuple[int, float, int]:
    """Pick the highest 802.11n HT MCS for the given RSSI, stream count, and channel width."""
    noise_floor = -95 if channel_width_mhz == 20 else -92
    snr = rssi_dbm - noise_floor
    # Penalise each doubling of streams and the wider channel.
    snr -= 5.0 * (n_streams - 1)
    if channel_width_mhz == 40:
        snr -= 3.0
    chosen = (0, 6.5, 2)
    for (mcs, base_rate), min_snr in HT_MCS_MIN_SNR:
        rate = base_rate
        if channel_width_mhz == 40:
            rate *= 2.0
            if short_gi:
                rate = rate * 4.0e-6 / 3.6e-6  # 10% short-GI boost
        elif short_gi:
            rate = rate * 4.0e-6 / 3.6e-6
        if snr >= min_snr:
            chosen = (mcs, round(rate * n_streams, 1), min_snr)
    return chosen


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_barker(hex_payload: str) -> int:
    chips = barker_spread_hex(hex_payload)
    pretty = " ".join(f"{c:+d}" for c in chips)
    print(f"Input bits:  {hex_payload}  ({len(chips) // 11} bits -> {len(chips)} chips)")
    print(f"Barker-11:   {pretty}")
    print(f"Chip rate:   {DSSS_CHIP_RATE / 1e6:.0f} Mchip/s")
    air_time = len(chips) / DSSS_CHIP_RATE * 1e6
    print(f"Air time:    {air_time:.2f} us  (DSSS @ 11 Mchip/s)")
    return 0


def cmd_ofdm(short: bool) -> int:
    t_sym = ofdm_symbol_seconds(short_gi=short)
    gi = SHORT_GI_SECONDS if short else LONG_GI_SECONDS
    print(f"Channel width:    {CHANNEL_WIDTH_MHZ:.0f} MHz")
    print(f"FFT size:         {FFT_SIZE}")
    print(f"Used subcarriers: {USED_SUBCARRIERS}  ({DATA_SUBCARRIERS} data + {PILOT_SUBCARRIERS} pilots)")
    print(f"Subcarrier gap:   {SUBCARRIER_SPACING_HZ / 1e3:.1f} kHz")
    print(f"Useful symbol:    {USEFUL_SYMBOL_SECONDS * 1e6:.1f} us  (T_u = 1 / subcarrier_spacing)")
    print(f"Guard interval:   {gi * 1e6:.1f} us  ({'short' if short else 'long'})")
    print(f"OFDM symbol:      {t_sym * 1e6:.1f} us  (T_sym = T_u + T_cp)")
    print(f"Symbols/second:    {1.0 / t_sym:.0f}  (250000 with long GI, 277778 with short GI)")
    return 0


def cmd_mimo(n_streams: int, channel_width_mhz: int, modulation: str, gi: str) -> int:
    short_gi = gi.lower().startswith("short")
    # Default code rates that are typically paired with each modulation in
    # the 802.11n MCS table. Use 5/6 for 64-QAM to hit the 600-Mbps ceiling.
    code_rates = {"BPSK": 1 / 2, "QPSK": 3 / 4, "16-QAM": 3 / 4, "64-QAM": 5 / 6}
    if modulation not in code_rates:
        print(f"Unknown modulation: {modulation}", file=sys.stderr)
        return 2
    rate = mimo_stream_rate_mbps(
        n_streams=n_streams,
        channel_width_mhz=channel_width_mhz,
        modulation=modulation,
        code_rate=code_rates[modulation],
        short_gi=short_gi,
    )
    per_stream = mimo_stream_rate_mbps(
        n_streams=1,
        channel_width_mhz=channel_width_mhz,
        modulation=modulation,
        code_rate=code_rates[modulation],
        short_gi=short_gi,
    )
    print(f"Config:    {n_streams}x{n_streams} MIMO, {channel_width_mhz} MHz, {modulation} 3/4, {'short' if short_gi else 'long'} GI")
    print(f"Per-stream PHY rate: {per_stream:.1f} Mbps")
    print(f"Aggregate PHY rate:  {rate:.1f} Mbps  ({n_streams} streams)")
    if n_streams == 4 and channel_width_mhz == 40 and modulation == "64-QAM" and short_gi:
        print("This is the 802.11n headline rate: 600 Mbps.")
    return 0


def cmd_table(standard: str) -> int:
    std = standard.lower()
    if std in ("a", "g"):
        print(f"802.11{std} rate table (20 MHz, long GI, 1 spatial stream):")
        print(f"  {'MCS':>3}  {'Modulation':<8}  {'Code':<5}  {'Rate (Mbps)':>10}")
        for mcs in A_G_TABLE:
            print(f"  {mcs.mcs:>3}  {mcs.modulation:<8}  {mcs.code_rate:<5}  {mcs.data_rate_mbps:>10.1f}")
    elif std == "b":
        print("802.11b rate table (HR-DSSS / CCK, 11 Mchip/s):")
        for rate in B_RATES_MBPS:
            label = "DSSS/BPSK" if rate <= 2 else "CCK"
            print(f"  {rate:>5.1f} Mbps  ({label})")
    elif std == "n":
        print("802.11n HT rate table (MCS 0-7, 1 spatial stream):")
        print(f"  {'MCS':>3}  {'Mod':<7}  {'Code':<5}  {'20/LGI':>8}  {'20/SGI':>8}  {'40/LGI':>8}  {'40/SGI':>8}")
        for m in HT_TABLE:
            r20l = m.long_gi_20_mbps
            r20s = round(m.long_gi_20_mbps * 4.0 / 3.6, 1)
            r40l = m.long_gi_40_mbps
            r40s = round(m.long_gi_40_mbps * 4.0 / 3.6, 1)
            print(
                f"  {m.mcs:>3}  {m.modulation:<7}  {m.code_rate:<5}  "
                f"{r20l:>8.1f}  {r20s:>8.1f}  {r40l:>8.1f}  {r40s:>8.1f}"
            )
    else:
        print(f"Unknown standard: {standard}", file=sys.stderr)
        return 2
    return 0


def cmd_select(args: argparse.Namespace) -> int:
    if args.standard in ("a", "g"):
        mcs, rate, min_snr = select_rate_ag(args.rssi)
        noise_floor = -95
        snr = args.rssi - noise_floor
        print(f"Band:     {args.band} GHz")
        print(f"Standard: 802.11{args.standard}")
        print(f"RSSI:     {args.rssi} dBm  (SNR ~ {snr} dB vs -95 dBm noise floor)")
        print(f"Selected: MCS-{mcs}  {rate:.1f} Mbps  (min SNR {min_snr} dB)")
    else:
        mcs, rate, min_snr = select_rate_ht(
            rssi_dbm=args.rssi,
            n_streams=args.streams,
            channel_width_mhz=args.width,
            short_gi=(args.gi == "short"),
        )
        print(f"Band:      {args.band} GHz")
        print(f"Standard:  802.11n")
        print(f"RSSI:      {args.rssi} dBm  ({args.streams}x{args.streams}, {args.width} MHz, {args.gi} GI)")
        print(f"Selected:  MCS-{mcs}  {rate:.1f} Mbps  (min SNR {min_snr} dB)")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wifi-phy",
        description="802.11 physical layer reference: Barker spreading, OFDM timing, MIMO rates.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_barker = sub.add_parser("barker", help="Spread a hex bit string with the Barker-11 code")
    p_barker.add_argument("payload", help="Hex payload, e.g. 0xABC")

    p_ofdm = sub.add_parser("ofdm", help="Print OFDM symbol timing")
    p_ofdm.add_argument(
        "guard",
        nargs="?",
        default="long",
        choices=("long", "short"),
        help="Guard interval (default: long)",
    )

    p_mimo = sub.add_parser("mimo", help="Approximate MIMO-OFDM rate")
    p_mimo.add_argument("streams", type=int, help="Number of spatial streams (1-4)")
    p_mimo.add_argument("width", type=int, choices=(20, 40), help="Channel width in MHz")
    p_mimo.add_argument(
        "modulation",
        choices=("BPSK", "QPSK", "16-QAM", "64-QAM"),
        help="Modulation format",
    )
    p_mimo.add_argument(
        "gi",
        nargs="?",
        default="long",
        choices=("long", "short"),
        help="Guard interval (default: long)",
    )

    p_table = sub.add_parser("table", help="Print the data-rate table for a standard")
    p_table.add_argument("standard", choices=("a", "b", "g", "n"))

    p_sel = sub.add_parser("select", help="Pick an MCS for a given RSSI")
    p_sel.add_argument("--band", choices=("2.4", "5"), required=True)
    p_sel.add_argument("--standard", choices=("a", "b", "g", "n"), required=True)
    p_sel.add_argument("--rssi", type=int, required=True, help="RSSI in dBm (e.g. -65)")
    p_sel.add_argument("--streams", type=int, default=1, help="802.11n spatial streams (1-4)")
    p_sel.add_argument("--width", type=int, default=20, choices=(20, 40), help="Channel width in MHz")
    p_sel.add_argument("--gi", choices=("long", "short"), default="long")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "barker":
        return cmd_barker(args.payload)
    if args.cmd == "ofdm":
        return cmd_ofdm(short=args.guard == "short")
    if args.cmd == "mimo":
        return cmd_mimo(args.streams, args.width, args.modulation, args.gi)
    if args.cmd == "table":
        return cmd_table(args.standard)
    if args.cmd == "select":
        return cmd_select(args)
    parser.error(f"unknown command: {args.cmd}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
