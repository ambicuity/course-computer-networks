#!/usr/bin/env python3
"""Bluetooth classic radio/baseband toolkit (stdlib only).

This program models the lower Bluetooth layers from Tanenbaum 4.6:

  * Radio-layer constants: 79 channels x 1 MHz, 625-us slots, 1600 hops/sec.
  * The 18-bit baseband header (Addr/Type/Flow/Ack/Seq/HEC) and the 3x
    repetition + majority-vote FEC that expands it to 54 transmitted bits.
  * Adaptive frequency hopping (AFH): pruning busy ISM channels from the
    hop set so Bluetooth coexists with 802.11.
  * SCO vs. ACL link selection given a workload.

Run:  python3 main.py
No third-party packages, no network calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple

# --- Radio-layer constants (Bluetooth classic, 2.4-GHz ISM) ---------------
NUM_CHANNELS: int = 79
CHANNEL_WIDTH_MHZ: float = 1.0
BASE_FREQ_MHZ: float = 2402.0          # channel 0 center
SLOT_US: int = 625                     # dwell time per slot
HOPS_PER_SEC: int = 1600               # 1 / 625us
SETTLING_US: int = 255                 # 250-260 us radio settle per hop
ACCESS_CODE_BITS: int = 72
HEADER_LOGICAL_BITS: int = 18          # Addr(3)+Type(4)+F(1)+A(1)+S(1)+HEC(8)
HEADER_REPEAT: int = 3                 # repeated 3x -> 54 transmitted bits
TX_RATE_BPS: int = 1_000_000           # 1 Mbps gross at basic rate


def channel_center_mhz(index: int) -> float:
    """Center frequency of Bluetooth channel `index` (0..78)."""
    if not 0 <= index < NUM_CHANNELS:
        raise ValueError(f"channel {index} out of range 0..{NUM_CHANNELS - 1}")
    return BASE_FREQ_MHZ + index * CHANNEL_WIDTH_MHZ


@dataclass(frozen=True)
class BasebandHeader:
    """The 18 logical header bits of a Bluetooth baseband frame."""

    addr: int   # 3 bits: which of 8 active devices
    type_: int  # 4 bits: ACL/SCO/poll/null + FEC + slot count
    flow: int   # 1 bit: buffer-full flow control
    ack: int    # 1 bit: piggybacked ack
    seq: int    # 1 bit: stop-and-wait sequence number
    hec: int    # 8 bits: header error check

    def to_bits(self) -> List[int]:
        """Pack the 18 logical fields MSB-first into a bit list."""
        fields: List[Tuple[int, int]] = [
            (self.addr, 3),
            (self.type_, 4),
            (self.flow, 1),
            (self.ack, 1),
            (self.seq, 1),
            (self.hec, 8),
        ]
        bits: List[int] = []
        for value, width in fields:
            for shift in range(width - 1, -1, -1):
                bits.append((value >> shift) & 1)
        assert len(bits) == HEADER_LOGICAL_BITS
        return bits


def encode_header(header: BasebandHeader) -> List[int]:
    """Expand 18 logical bits into 54 transmitted bits (each repeated 3x)."""
    out: List[int] = []
    for bit in header.to_bits():
        out.extend([bit] * HEADER_REPEAT)
    assert len(out) == HEADER_LOGICAL_BITS * HEADER_REPEAT
    return out


def decode_header(tx_bits: List[int]) -> Tuple[List[int], int]:
    """Recover 18 logical bits from 54 transmitted bits by majority vote.

    Returns (logical_bits, corrected_count) where corrected_count is the
    number of positions where the 3 copies disagreed.
    """
    if len(tx_bits) != HEADER_LOGICAL_BITS * HEADER_REPEAT:
        raise ValueError("expected 54 transmitted header bits")
    logical: List[int] = []
    corrected = 0
    for i in range(HEADER_LOGICAL_BITS):
        triple = tx_bits[i * 3:i * 3 + 3]
        ones = sum(triple)
        winner = 1 if ones >= 2 else 0
        if ones not in (0, 3):
            corrected += 1
        logical.append(winner)
    return logical, corrected


def bits_to_int(bits: List[int]) -> int:
    value = 0
    for bit in bits:
        value = (value << 1) | bit
    return value


def afh_hop_set(busy_centers_mhz: List[float], guard_mhz: float = 8.0) -> List[int]:
    """Prune channels within `guard_mhz` of any busy center frequency.

    A Wi-Fi channel is ~22 MHz wide, so +-11 MHz around its center is the
    contaminated region. Returns the surviving channel indices (the AFH set).
    """
    surviving: List[int] = []
    for ch in range(NUM_CHANNELS):
        center = channel_center_mhz(ch)
        if all(abs(center - busy) > guard_mhz for busy in busy_centers_mhz):
            surviving.append(ch)
    return surviving


def frame_efficiency(slots: int, payload_bits: int) -> float:
    """Useful-payload fraction of airtime for an N-slot basic-rate frame."""
    air_us = slots * SLOT_US
    payload_us = payload_bits / TX_RATE_BPS * 1e6
    overhead_us = (ACCESS_CODE_BITS + HEADER_LOGICAL_BITS * HEADER_REPEAT) \
        / TX_RATE_BPS * 1e6 + SETTLING_US
    span = max(air_us, payload_us + overhead_us)
    return payload_us / span


def choose_link(workload: str) -> Tuple[str, str]:
    """Pick SCO or ACL for a workload, with rationale."""
    real_time = workload.lower() in {"voice", "audio", "telephony", "headset"}
    if real_time:
        return "SCO", ("real-time: fixed reserved slots, never retransmitted, "
                       "one 64-kbps PCM channel, FEC for reliability")
    return "ACL", ("bursty data: best-effort, stop-and-wait retransmit, "
                   "fed by L2CAP segmentation of up to 64-KB packets")


def main() -> None:
    print("=" * 64)
    print("Bluetooth radio layer summary")
    print("=" * 64)
    print(f"  channels        : {NUM_CHANNELS} x {CHANNEL_WIDTH_MHZ:.0f} MHz "
          f"({channel_center_mhz(0):.0f}-{channel_center_mhz(78):.0f} MHz)")
    print(f"  slot dwell      : {SLOT_US} us  ->  {HOPS_PER_SEC} hops/sec")
    print(f"  settling/hop    : {SETTLING_US} us")
    print(f"  basic gross rate: {TX_RATE_BPS // 1_000_000} Mbps (GFSK)")
    print(f"  sanity          : {HOPS_PER_SEC} hops x {SLOT_US} us = "
          f"{HOPS_PER_SEC * SLOT_US / 1e6:.1f} s")

    print("\n" + "=" * 64)
    print("18-bit header -> 54 transmitted bits -> majority-vote decode")
    print("=" * 64)
    header = BasebandHeader(addr=0b101, type_=0b0011, flow=1, ack=0,
                            seq=1, hec=0b10110100)
    tx = encode_header(header)
    print(f"  logical header  : {''.join(map(str, header.to_bits()))}")
    print(f"  transmitted (54): {''.join(map(str, tx))}")

    # Corrupt one copy of one bit to show FEC recovery.
    corrupted = list(tx)
    corrupted[7] ^= 1  # flip 2nd copy of logical bit index 2
    logical, fixed = decode_header(corrupted)
    recovered = BasebandHeader(
        addr=bits_to_int(logical[0:3]),
        type_=bits_to_int(logical[3:7]),
        flow=logical[7], ack=logical[8], seq=logical[9],
        hec=bits_to_int(logical[10:18]),
    )
    print(f"  injected error  : flipped 1 of 3 copies (positions disagree)")
    print(f"  positions fixed : {fixed}")
    print(f"  recovered       : addr={recovered.addr:03b} "
          f"type={recovered.type_:04b} F={recovered.flow} "
          f"A={recovered.ack} S={recovered.seq} HEC={recovered.hec:08b}")
    print(f"  matches original: {recovered == header}")

    print("\n" + "=" * 64)
    print("Adaptive frequency hopping (AFH) vs. Wi-Fi 1/6/11")
    print("=" * 64)
    wifi = [2412.0, 2437.0, 2462.0]
    survivors = afh_hop_set(wifi)
    print(f"  Wi-Fi centers   : {wifi} MHz (~22 MHz each)")
    print(f"  surviving chans : {len(survivors)} of {NUM_CHANNELS} "
          f"({100 * len(survivors) / NUM_CHANNELS:.0f}% of hop set kept)")

    print("\n" + "=" * 64)
    print("Frame efficiency: 5-slot vs 1-slot (basic rate)")
    print("=" * 64)
    print(f"  5-slot, 2744 bits payload : "
          f"{100 * frame_efficiency(5, 2744):.1f}% airtime is payload")
    print(f"  1-slot,  240 bits payload : "
          f"{100 * frame_efficiency(1, 240):.1f}% airtime is payload")

    print("\n" + "=" * 64)
    print("Link selection")
    print("=" * 64)
    for workload in ("headset", "bulk-file-transfer"):
        link, why = choose_link(workload)
        print(f"  {workload:20s} -> {link}: {why}")


if __name__ == "__main__":
    main()
