"""Cellular generations lab: AMPS (1G) capacity, GSM (2G) TDMA framing, CDMA (3G) spreading.

This stdlib-only program models the three multiple-access schemes that define the
1G -> 2G -> 3G evolution described in Tanenbaum's Mobile Telephone System section:

  1G AMPS  -- FDD/FDMA: 832 full-duplex 30 kHz channels, analog voice, digital control.
  2G GSM   -- FDD + TDMA: 200 kHz carriers split into 8 time slots; 270.833 kbit/s gross.
  3G UMTS  -- W-CDMA: every user shares a 5 MHz band, separated by orthogonal chip codes.

The CDMA section is the heart of the lesson: it builds orthogonal Walsh chip
sequences, spreads each station's bits, sums the channels onto one wire (as the air
does), and recovers each station by correlating against its own code. This is exactly
why a 3G base station can hear many unsynchronized handsets on one frequency.

Run:  python3 main.py
No third-party dependencies, no network access.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple


# --------------------------------------------------------------------------- #
# 1G / 2G capacity facts (real numbers from the AMPS and GSM air interfaces)   #
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Generation:
    name: str
    access: str            # multiple-access scheme
    carrier_khz: float     # channel width in kHz
    users_per_carrier: int
    gross_kbps: float      # raw bit rate per carrier (0 = analog voice)
    note: str


GENERATIONS: Tuple[Generation, ...] = (
    Generation("1G AMPS", "FDMA/FDD", 30.0, 1, 0.0,
               "analog FM voice; 30 kHz simplex pairs, 832 full-duplex channels"),
    Generation("2G GSM", "TDMA/FDD", 200.0, 8, 270.833,
               "200 kHz carrier, 8 slots, 577 us/slot, 13 kbit/s speech after FEC"),
    Generation("3G UMTS", "W-CDMA", 5000.0, 0, 3840.0,
               "5 MHz shared, 3.84 Mchip/s, codes separate users, power-controlled"),
)


def amps_voice_channels_per_cell(total_duplex: int = 832,
                                 operators: int = 2,
                                 control_per_cell: int = 21,
                                 reuse_cluster: int = 7) -> int:
    """Estimate AMPS voice channels available in one cell.

    The 832 channels were split between two competing carriers (operators), so each
    carrier owns ~416. Frequencies are reused on a 7-cell cluster, and 21 control
    channels are reserved per cell. The textbook quotes "typically about 45"; this
    model reproduces that figure.
    """
    per_operator = total_duplex // operators          # ~416 channels per carrier
    per_cell_total = per_operator // reuse_cluster     # split across the 7-cell cluster
    return per_cell_total - (control_per_cell // reuse_cluster)


def gsm_payload_kbps(gross_kbps: float = 270.833, users: int = 8) -> float:
    """Per-user gross share of a GSM carrier before framing/FEC overhead."""
    return round(gross_kbps / users, 3)


def print_generation_table() -> None:
    print("Cellular multiple-access evolution")
    print("-" * 78)
    header = f"{'Generation':<10} {'Access':<10} {'Carrier':>9} {'Users':>6} {'Gross kbps':>11}"
    print(header)
    print("-" * 78)
    for g in GENERATIONS:
        users = "shared" if g.users_per_carrier == 0 else str(g.users_per_carrier)
        gross = "analog" if g.gross_kbps == 0 else f"{g.gross_kbps:.0f}"
        print(f"{g.name:<10} {g.access:<10} {g.carrier_khz:>7.0f}k {users:>6} {gross:>11}")
        print(f"           ^ {g.note}")
    print("-" * 78)
    print(f"AMPS voice channels per cell (7-cell reuse): {amps_voice_channels_per_cell()}")
    print(f"GSM gross bits per user (270.833 / 8):       {gsm_payload_kbps()} kbit/s")
    print()


# --------------------------------------------------------------------------- #
# 3G CDMA core: Walsh codes, spreading, channel summation, correlation decode  #
# --------------------------------------------------------------------------- #

def walsh_codes(order: int) -> List[List[int]]:
    """Generate `order` x `order` orthogonal Walsh-Hadamard chip sequences (+/-1).

    Built recursively: H(2n) = [[H, H], [H, -H]]. Rows are pairwise orthogonal,
    which is precisely the property a 3G base station relies on to separate users.
    `order` must be a power of two.
    """
    if order < 1 or (order & (order - 1)) != 0:
        raise ValueError("Walsh order must be a power of two")
    matrix = [[1]]
    while len(matrix) < order:
        n = len(matrix)
        bigger = [[0] * (2 * n) for _ in range(2 * n)]
        for r in range(n):
            for c in range(n):
                v = matrix[r][c]
                bigger[r][c] = v
                bigger[r][c + n] = v
                bigger[r + n][c] = v
                bigger[r + n][c + n] = -v
        matrix = bigger
    return matrix


def spread(bits: Sequence[int], code: Sequence[int]) -> List[int]:
    """Spread a bitstream with a chip sequence.

    Bit 1 transmits the chip sequence; bit 0 transmits its negation. This is the
    +/-1 bipolar convention from the textbook (A = its code, A-bar = negated code).
    """
    chips: List[int] = []
    for bit in bits:
        if bit not in (0, 1):
            raise ValueError(f"bit must be 0 or 1, got {bit!r}")
        sign = 1 if bit == 1 else -1
        chips.extend(sign * c for c in code)
    return chips


def air_combine(channels: Sequence[Sequence[int]]) -> List[int]:
    """Sum all stations' chip streams chip-by-chip, as the radio channel does."""
    if not channels:
        return []
    length = len(channels[0])
    if any(len(ch) != length for ch in channels):
        raise ValueError("all channels must have equal chip length")
    return [sum(ch[i] for ch in channels) for i in range(length)]


def despread(combined: Sequence[int], code: Sequence[int]) -> List[int]:
    """Recover one station's bits by correlating the summed signal with its code.

    For each bit interval we compute the normalized inner product of the received
    chips with the station's chip sequence. Orthogonal codes from other users sum
    to 0, leaving +1 (bit 1) or -1 (bit 0) for the wanted user.
    """
    m = len(code)
    if len(combined) % m != 0:
        raise ValueError("combined length must be a multiple of the code length")
    recovered: List[int] = []
    for start in range(0, len(combined), m):
        window = combined[start:start + m]
        inner = sum(window[i] * code[i] for i in range(m))
        normalized = inner / m
        recovered.append(1 if normalized > 0 else 0)
    return recovered


def cdma_demo() -> None:
    print("3G W-CDMA spreading demo (orthogonal Walsh codes)")
    print("-" * 78)
    codes = walsh_codes(8)
    # Assign three handsets distinct orthogonal codes (rows 1..3; row 0 is all +1).
    stations: Dict[str, Tuple[List[int], List[int]]] = {
        "Handset-A": (codes[1], [1, 0, 1, 1]),
        "Handset-B": (codes[3], [0, 0, 1, 0]),
        "Handset-C": (codes[5], [1, 1, 0, 1]),
    }

    channels = []
    for name, (code, bits) in stations.items():
        chips = spread(bits, code)
        channels.append(chips)
        print(f"{name}: code={fmt(code)}  bits={bits}")

    combined = air_combine(channels)
    print()
    print(f"Summed air signal (first 8 chips): {fmt(combined[:8])}")
    print("Each handset transmits over the FULL band at the SAME time.")
    print()

    all_ok = True
    for name, (code, bits) in stations.items():
        out = despread(combined, code)
        ok = out == bits
        all_ok = all_ok and ok
        flag = "OK" if ok else "MISMATCH"
        print(f"Recover {name}: {out}  [{flag}]")

    print()
    # Show that a wrong/unassigned code recovers noise, not a clean bitstream.
    intruder = codes[7]
    leaked = despread(combined, intruder)
    print(f"Eavesdrop with unassigned code {fmt(intruder)} -> {leaked}")
    print("Without the right chip code, the signal looks like background noise.")
    print("-" * 78)
    print(f"All assigned handsets recovered cleanly: {all_ok}")
    print()


def fmt(seq: Sequence[int]) -> str:
    """Render a +/-1 chip sequence compactly, e.g. (- + - + ...)."""
    return "(" + " ".join("+" if v > 0 else ("-" if v < 0 else "0") for v in seq) + ")"


# --------------------------------------------------------------------------- #

def main() -> None:
    print()
    print_generation_table()
    cdma_demo()
    print("Takeaway: 1G splits by frequency, 2G adds time slots, 3G overlays codes.")


if __name__ == "__main__":
    main()
