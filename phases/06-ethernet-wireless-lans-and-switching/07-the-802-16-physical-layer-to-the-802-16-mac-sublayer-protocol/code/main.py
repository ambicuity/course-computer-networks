#!/usr/bin/env python3
"""IEEE 802.16 (WiMAX) PHY rate budget, MAC generic-header parser, and a
TDD best-effort contention simulator using binary exponential backoff.

1. rate_budget()          -- PHY bits/sec from subcarriers, symbol time, and
                             modulation order (QPSK/QAM-16/QAM-64).
2. parse_generic_header() -- decode the 6-byte 802.16 MAC generic header and
                             verify the 8-bit header CRC over x^8+x^2+x+1.
3. simulate_contention()  -- best-effort stations contend for ranging slots
                             with the Ethernet binary exponential backoff.

Standard library only. Run:  python3 main.py
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Iterable

# 802.16 MAC header CRC polynomial: x^8 + x^2 + x + 1  ->  0x07 (CRC-8/ATM "HEC").
HEADER_CRC_POLY = 0x07

# Modulation order -> bits carried per OFDM symbol on one subcarrier.
BITS_PER_SYMBOL = {"QPSK": 2, "QAM-16": 4, "QAM-64": 6}


# --------------------------------------------------------------------------- #
# 1. PHY rate budget
# --------------------------------------------------------------------------- #
def rate_budget(
    subcarriers: int,
    symbol_time_us: float,
    modulation: str,
    code_rate: float,
    duplex_fraction: float,
) -> float:
    """Return usable bits/sec for one direction of a TDD link.

    subcarriers     : data subcarriers carrying payload symbols.
    symbol_time_us  : time to send one OFDM symbol (microseconds).
    modulation      : "QPSK" | "QAM-16" | "QAM-64".
    code_rate       : FEC code rate (e.g. 0.5 for rate-1/2 convolutional code).
    duplex_fraction : fraction of frame time given to this direction (TDD split).
    """
    if modulation not in BITS_PER_SYMBOL:
        raise ValueError(f"unknown modulation {modulation!r}")
    if not 0.0 < duplex_fraction <= 1.0:
        raise ValueError("duplex_fraction must be in (0, 1]")

    bits_per_symbol = BITS_PER_SYMBOL[modulation]
    symbols_per_sec = 1_000_000.0 / symbol_time_us
    raw = subcarriers * bits_per_symbol * symbols_per_sec
    return raw * code_rate * duplex_fraction


# --------------------------------------------------------------------------- #
# 2. MAC generic-header parser + header CRC
# --------------------------------------------------------------------------- #
def header_crc8(data: bytes) -> int:
    """CRC-8 over `data` using x^8 + x^2 + x + 1 (init 0x00), MSB-first."""
    crc = 0x00
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = ((crc << 1) ^ HEADER_CRC_POLY) & 0xFF
            else:
                crc = (crc << 1) & 0xFF
    return crc


@dataclass(frozen=True)
class GenericHeader:
    """Decoded 802.16 MAC generic header (Fig. 4-33a)."""

    ht: int            # header type bit: 0 = generic, 1 = bandwidth request
    ec: int            # Encryption Control
    type_field: int    # frame type (packing/fragmentation flags)
    ci: int            # CRC Indicator (full-frame CRC present?)
    ek: int            # Encryption Key index
    length: int        # total frame length including header (11 bits)
    connection_id: int # 16-bit connection identifier
    header_crc: int    # CRC over the 5 preceding header bytes
    crc_ok: bool


def parse_generic_header(header: bytes) -> GenericHeader:
    """Parse the 6-byte generic header and check its 8-bit header CRC.

    Layout (MSB first): HT(1) EC(1) Type(6) | CI/EK/Length-hi | Length-lo |
    CID-hi | CID-lo | HeaderCRC(8).
    """
    if len(header) != 6:
        raise ValueError("generic header must be exactly 6 bytes")

    b0, b1, b2, b3, b4, b5 = header
    ht = (b0 >> 7) & 0x1
    ec = (b0 >> 6) & 0x1
    type_field = b0 & 0x3F
    ci = (b1 >> 6) & 0x1
    ek = (b1 >> 4) & 0x3
    length = ((b1 & 0x0F) << 8) | b2
    connection_id = (b3 << 8) | b4
    header_crc = b5

    computed = header_crc8(header[:5])
    return GenericHeader(
        ht=ht, ec=ec, type_field=type_field, ci=ci, ek=ek,
        length=length, connection_id=connection_id,
        header_crc=header_crc, crc_ok=(computed == header_crc),
    )


def build_generic_header(
    ec: int, type_field: int, ci: int, ek: int, length: int, cid: int
) -> bytes:
    """Encode a valid 6-byte generic header with a correct header CRC."""
    b0 = (0 << 7) | (ec << 6) | (type_field & 0x3F)
    b1 = ((ci & 1) << 6) | ((ek & 0x3) << 4) | ((length >> 8) & 0x0F)
    b2 = length & 0xFF
    b3 = (cid >> 8) & 0xFF
    b4 = cid & 0xFF
    first5 = bytes([b0, b1, b2, b3, b4])
    return first5 + bytes([header_crc8(first5)])


# --------------------------------------------------------------------------- #
# 3. Best-effort contention with binary exponential backoff
# --------------------------------------------------------------------------- #
@dataclass
class ContentionResult:
    stations: int
    slots_per_frame: int
    frames: int
    granted: int
    collisions: int
    avg_grant_delay_frames: float


def simulate_contention(
    stations: int,
    slots_per_frame: int,
    frames: int,
    backoff_cap: int = 10,
    seed: int = 42,
) -> ContentionResult:
    """Simulate best-effort bandwidth requests contending for ranging slots.

    Each station has one pending request. On the i-th collision it backs off a
    random number of frames in [0, 2^i - 1] (capped at 2^backoff_cap - 1),
    exactly the Ethernet binary exponential backoff 802.16 reuses.
    """
    rng = random.Random(seed)
    backoff_until = [0] * stations   # next frame a station may transmit
    collisions_seen = [0] * stations
    granted = [False] * stations
    grant_frame = [-1] * stations
    total_collisions = 0

    for frame in range(frames):
        # Stations whose backoff has expired and still need a grant pick a slot.
        picks: dict[int, list[int]] = {}
        for s in range(stations):
            if granted[s] or backoff_until[s] > frame:
                continue
            slot = rng.randrange(slots_per_frame)
            picks.setdefault(slot, []).append(s)

        for _slot, contenders in picks.items():
            if len(contenders) == 1:
                s = contenders[0]
                granted[s] = True
                grant_frame[s] = frame
            else:
                total_collisions += len(contenders)
                for s in contenders:
                    collisions_seen[s] += 1
                    window = (1 << min(collisions_seen[s], backoff_cap)) - 1
                    backoff_until[s] = frame + 1 + rng.randint(0, window)

        if all(granted):
            break

    delays = [grant_frame[s] for s in range(stations) if granted[s]]
    avg_delay = sum(delays) / len(delays) if delays else float("nan")
    return ContentionResult(
        stations=stations,
        slots_per_frame=slots_per_frame,
        frames=frames,
        granted=sum(granted),
        collisions=total_collisions,
        avg_grant_delay_frames=avg_delay,
    )


# --------------------------------------------------------------------------- #
# Demonstration
# --------------------------------------------------------------------------- #
def _fmt_mbps(bps: float) -> str:
    return f"{bps / 1_000_000:6.2f} Mbps"


def main() -> None:
    print("=" * 64)
    print("1) 802.16 PHY rate budget  (5-MHz mobile WiMAX, 512 subcarriers)")
    print("=" * 64)
    # ~360 data subcarriers of the 512 carry payload after pilots/guard.
    for mod in ("QPSK", "QAM-16", "QAM-64"):
        down = rate_budget(360, 100.0, mod, code_rate=0.75, duplex_fraction=0.67)
        up = rate_budget(360, 100.0, mod, code_rate=0.75, duplex_fraction=0.33)
        print(f"  {mod:7s} -> downlink {_fmt_mbps(down)} | uplink {_fmt_mbps(up)}")
    print("  Near stations ride QAM-64; distant low-SNR stations fall to QPSK.\n")

    print("=" * 64)
    print("2) MAC generic header decode + header CRC (x^8+x^2+x+1)")
    print("=" * 64)
    frame = build_generic_header(
        ec=1, type_field=0x02, ci=1, ek=2, length=44, cid=0x01F4
    )
    print("  raw header bytes :", frame.hex(" "))
    hdr = parse_generic_header(frame)
    print(f"  EC={hdr.ec}  Type=0x{hdr.type_field:02X}  CI={hdr.ci}  EK={hdr.ek}")
    print(f"  Length={hdr.length} bytes  ConnectionID=0x{hdr.connection_id:04X}")
    print(f"  Header CRC=0x{hdr.header_crc:02X}  valid={hdr.crc_ok}")

    corrupted = bytearray(frame)
    corrupted[3] ^= 0x20  # flip a bit in the Connection ID
    bad = parse_generic_header(bytes(corrupted))
    print(f"  after 1-bit flip in CID -> header CRC valid={bad.crc_ok} "
          "(corruption detected)\n")

    print("=" * 64)
    print("3) Best-effort contention with binary exponential backoff")
    print("=" * 64)
    print("  stations | granted | collisions | avg grant delay (frames)")
    print("  ---------+---------+------------+-------------------------")
    for n in (2, 4, 8, 12, 16):
        r = simulate_contention(stations=n, slots_per_frame=4, frames=200)
        print(f"  {r.stations:8d} | {r.granted:7d} | {r.collisions:10d} | "
              f"{r.avg_grant_delay_frames:8.2f}")
    print("  More best-effort stations -> more collisions and longer backoff,")
    print("  which is why latency-sensitive traffic uses CBR/rt-VBR instead.")


if __name__ == "__main__":
    main()
