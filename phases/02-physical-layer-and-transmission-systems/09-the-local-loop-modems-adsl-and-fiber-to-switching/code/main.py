#!/usr/bin/env python3
"""Local-loop rate models: telephone modems, ADSL/DMT, and PON scheduling.

Pure stdlib. Reproduces the physical-layer reasoning from the lesson:

  1. Nyquist / Shannon limits and the V.32..V.34 modem table.
  2. Why V.90 reaches exactly 56 kbps (7 usable bits x 8000 PCM samples/s).
  3. ADSL DMT: 256 channels of 4312.5 Hz, per-channel SNR -> bits/symbol
     bit-loading, and how the achievable rate collapses with loop length.
  4. PON upstream: TDMA grant scheduling vs. uncoordinated collision.

Run:  python3 main.py
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Tuple

# ---- Constants from the telephone / ADSL physical layer ----------------------

VOICE_CHANNEL_HZ = 4000.0          # quoted voice channel incl. guard bands
PCM_SAMPLES_PER_SEC = 8000         # Nyquist sampling of the 4 kHz channel
PCM_BITS_PER_SAMPLE = 8            # mu-law in the U.S.
SIGNALING_BITS_ROBBED = 1         # 1 of 8 bits may be stolen for signaling

DMT_CHANNELS = 256                 # ADSL discrete-multitone subcarriers
DMT_CHANNEL_HZ = 4312.5            # width of each DMT channel
DMT_SYMBOLS_PER_SEC = 4000.0       # ~4000 QAM symbols/s per channel
DMT_MAX_BITS = 15                  # cap on bits/symbol for a high-SNR channel
DMT_MIN_BITS = 2                   # below this a channel is disabled (0 bits)
POTS_CHANNEL = 0                   # channel 0 carries Plain Old Telephone Svc
GUARD_CHANNELS = range(1, 6)       # channels 1-5 unused to protect voice
SNR_GAP_DB = 9.8                   # Shannon gap + 6 dB margin, typical ADSL


# ---- 1. Nyquist and Shannon -------------------------------------------------

def nyquist_max_baud(bandwidth_hz: float) -> float:
    """Maximum symbol rate (baud) for a noiseless channel: 2 * B."""
    return 2.0 * bandwidth_hz


def shannon_capacity_bps(bandwidth_hz: float, snr_db: float) -> float:
    """Shannon-Hartley capacity in bits/s for a channel of given SNR (dB)."""
    snr_linear = 10.0 ** (snr_db / 10.0)
    return bandwidth_hz * math.log2(1.0 + snr_linear)


def modem_rate_bps(baud: float, data_bits_per_symbol: int) -> int:
    """Modem bit rate = baud * data bits per symbol (check bits excluded)."""
    return int(round(baud * data_bits_per_symbol))


def v90_downstream_bps() -> int:
    """V.90 downstream rate: usable PCM bits * sample rate.

    One analog loop is removed by the ISP's digital feed, so the limit is
    the PCM coding itself: (8 - 1 robbed) bits * 8000 samples/s = 56000.
    """
    usable_bits = PCM_BITS_PER_SAMPLE - SIGNALING_BITS_ROBBED
    return usable_bits * PCM_SAMPLES_PER_SEC


# ---- 2. ADSL DMT bit-loading ------------------------------------------------

def channel_frequency_hz(channel: int) -> float:
    """Center frequency of a DMT channel."""
    return channel * DMT_CHANNEL_HZ


def loop_snr_db(channel: int, loop_km: float, base_snr_db: float) -> float:
    """Model the SNR of a DMT channel after loop attenuation.

    Twisted-pair attenuation grows with both frequency (skin effect) and
    distance. This is a teaching approximation, not a cable spec: loss in dB
    scales with sqrt(frequency) and linearly with length.
    """
    freq_mhz = channel_frequency_hz(channel) / 1_000_000.0
    # ~ attenuation coefficient for Category 3 UTP (illustrative).
    attenuation_db = 13.0 * math.sqrt(max(freq_mhz, 1e-6)) * loop_km
    return base_snr_db - attenuation_db


def bits_for_channel(snr_db: float) -> int:
    """Map a channel's SNR to QAM bits/symbol using a Shannon-gap rule."""
    if snr_db <= 0:
        return 0
    raw = math.log2(1.0 + 10.0 ** ((snr_db - SNR_GAP_DB) / 10.0))
    bits = int(math.floor(raw))
    if bits < DMT_MIN_BITS:
        return 0
    return min(bits, DMT_MAX_BITS)


@dataclass
class DmtResult:
    loop_km: float
    rate_bps: int
    active_channels: int
    dead_channels: int
    first_dead_channel: int


def dmt_loadable_rate(loop_km: float, base_snr_db: float = 62.0,
                      max_channel: int = DMT_CHANNELS) -> DmtResult:
    """Sum per-channel bit-loading across the usable DMT channels."""
    total_bits_per_symbol = 0
    active = 0
    dead = 0
    first_dead = -1
    for channel in range(max_channel):
        if channel == POTS_CHANNEL or channel in GUARD_CHANNELS:
            continue
        snr = loop_snr_db(channel, loop_km, base_snr_db)
        bits = bits_for_channel(snr)
        if bits == 0:
            dead += 1
            if first_dead == -1:
                first_dead = channel
        else:
            active += 1
            total_bits_per_symbol += bits
    rate = int(round(total_bits_per_symbol * DMT_SYMBOLS_PER_SEC))
    return DmtResult(loop_km, rate, active, dead, first_dead)


# ---- 3. PON upstream TDMA scheduling ----------------------------------------

@dataclass
class UpstreamRequest:
    onu_id: str
    bytes_to_send: int
    ranging_offset_us: float  # measured by OLT so bursts arrive aligned


def pon_schedule(requests: List[UpstreamRequest], line_mbps: float = 1200.0,
                 guard_us: float = 1.0) -> List[Tuple[str, float, float]]:
    """Grant non-overlapping upstream time slots (us) to each ONU.

    Returns a list of (onu_id, start_us, end_us). Because the OLT serializes
    grants, no two ONUs transmit at once -- the upstream collision is avoided.
    """
    bytes_per_us = (line_mbps * 1_000_000 / 8.0) / 1_000_000.0
    grants: List[Tuple[str, float, float]] = []
    cursor = 0.0
    for req in requests:
        duration = req.bytes_to_send / bytes_per_us
        start = cursor
        end = start + duration
        grants.append((req.onu_id, round(start, 2), round(end, 2)))
        cursor = end + guard_us
    return grants


def detect_collision(grants: List[Tuple[str, float, float]]) -> bool:
    """True if any two granted slots overlap in time."""
    ordered = sorted(grants, key=lambda g: g[1])
    for earlier, later in zip(ordered, ordered[1:]):
        if later[1] < earlier[2]:
            return True
    return False


# ---- Demonstration ----------------------------------------------------------

def _print_modem_table() -> None:
    print("=== Telephone modems: baud 2400, more bits/symbol ===")
    rows = [
        ("V.32", 2400, 4), ("V.32 bis", 2400, 6),
        ("V.34", 2400, 12), ("V.34 bis", 2400, 14),
    ]
    for name, baud, bits in rows:
        print(f"  {name:9s} {baud} baud x {bits:2d} data bits/sym "
              f"= {modem_rate_bps(baud, bits):>6d} bps")
    print(f"  Nyquist cap on a perfect 3000 Hz line: "
          f"{int(nyquist_max_baud(3000)):d} baud")
    print(f"  Shannon limit (~35 dB SNR voice loop): "
          f"{int(shannon_capacity_bps(3100, 35)):d} bps\n")


def _print_v90() -> None:
    print("=== V.90 downstream: break 35 kbps via digital ISP feed ===")
    print(f"  ({PCM_BITS_PER_SAMPLE} - {SIGNALING_BITS_ROBBED} robbed) bits "
          f"x {PCM_SAMPLES_PER_SEC} samples/s = "
          f"{v90_downstream_bps()} bps downstream")
    print("  Upstream stays analog -> 33.6 kbps. Hence the asymmetry.\n")


def _print_adsl() -> None:
    print("=== ADSL2+ DMT achievable rate vs. loop length ===")
    print(f"  {DMT_CHANNELS} channels x {DMT_CHANNEL_HZ} Hz, "
          f"ch0=POTS, ch1-5=guard, 2-15 bits/symbol by SNR")
    for km in (0.5, 1.0, 2.0, 3.0, 4.2, 5.0):
        r = dmt_loadable_rate(km)
        first = r.first_dead_channel if r.first_dead_channel >= 0 else "-"
        print(f"  loop={km:>3.1f} km  rate={r.rate_bps/1e6:5.2f} Mbps  "
              f"active={r.active_channels:3d}  dead={r.dead_channels:3d}  "
              f"first-dead-ch={first}")
    print()


def _print_pon() -> None:
    print("=== PON upstream: OLT grants serialize ONU bursts ===")
    reqs = [
        UpstreamRequest("ONU-A", bytes_to_send=1500, ranging_offset_us=12.3),
        UpstreamRequest("ONU-B", bytes_to_send=4000, ranging_offset_us=31.7),
        UpstreamRequest("ONU-C", bytes_to_send=800, ranging_offset_us=5.1),
    ]
    grants = pon_schedule(reqs)
    for onu, start, end in grants:
        print(f"  {onu}: slot {start:7.2f}-{end:7.2f} us")
    print(f"  collision among granted slots? {detect_collision(grants)}")
    clashing = [("ONU-A", 0.0, 10.0), ("ONU-B", 4.0, 14.0)]
    print(f"  without grants (two ONUs at once)? "
          f"{detect_collision(clashing)}\n")


def main() -> None:
    print("Local loop: modems, ADSL, and fiber to switching\n")
    _print_modem_table()
    _print_v90()
    _print_adsl()
    _print_pon()


if __name__ == "__main__":
    main()
