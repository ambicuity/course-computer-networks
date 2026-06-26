"""
Classic Ethernet Physical Layer Simulator
==========================================
Demonstrates Manchester encoding/decoding, Ethernet preamble structure,
CRC-32 frame check sequence, and minimum frame size constraints as
specified by IEEE 802.3 / DIX Ethernet.

Manchester encoding: each bit is encoded as a mid-bit voltage transition.
  - Logical 1  -> high-to-low transition at mid-bit
  - Logical 0  -> low-to-high transition at mid-bit

The clock runs at 2x the bit rate and is XOR'd with data, guaranteeing
one transition per bit period and enabling receiver clock recovery.
"""

import binascii
import struct
from typing import List, Tuple

# IEEE 802.3 constants
PREAMBLE_BYTES       = bytes([0xAA] * 7)  # 7 x 10101010
SFD_BYTE             = bytes([0xAB])       # 10101011 - Start Frame Delimiter
ETHERNET_MIN_PAYLOAD = 46                  # bytes; pad to this if shorter
ETHERNET_MAX_PAYLOAD = 1500                # bytes
ETHERNET_MIN_FRAME   = 64                 # bytes (Dst+Src+Type+Data+FCS, excl preamble)
SLOT_TIME_BITS       = 512                # 512 bit-times @ 10 Mbps = 51.2 us


# ---------------------------------------------------------------------------
# Manchester encoding / decoding
# ---------------------------------------------------------------------------

def manchester_encode(bits: List[int], samples_per_half: int = 2) -> List[int]:
    """
    Encode a list of bits using Manchester (biphase-L) coding.

    Each bit is two half-bit periods:
      - Bit 1: first half HIGH (-1), second half LOW  (+1)  -> falling edge at mid-bit
      - Bit 0: first half LOW  (+1), second half HIGH (-1)  -> rising  edge at mid-bit

    Returns signal levels (+-1) at samples_per_half samples per half-bit.
    """
    signal: List[int] = []
    for bit in bits:
        if bit == 1:
            first_half, second_half = -1, +1
        else:
            first_half, second_half = +1, -1
        signal.extend([first_half] * samples_per_half)
        signal.extend([second_half] * samples_per_half)
    return signal


def manchester_decode(signal: List[int], samples_per_bit: int = 4) -> List[int]:
    """
    Decode a Manchester-encoded signal back to bits.

    Samples at the 3/4 point of each bit period (second half):
      - second-half +1 means bit=1 (high->low, second half is low => +1 in our convention)
      - second-half -1 means bit=0
    """
    bits: List[int] = []
    i = 0
    while i + samples_per_bit <= len(signal):
        sample_idx = i + (samples_per_bit * 3) // 4
        bits.append(1 if signal[sample_idx] == 1 else 0)
        i += samples_per_bit
    return bits


def signal_to_ascii(signal: List[int], label: str = "") -> str:
    """Render a Manchester signal as two ASCII lines (high / low)."""
    high_line = ""
    low_line  = ""
    for i, level in enumerate(signal):
        if i > 0 and signal[i] != signal[i - 1]:
            high_line += "|"
            low_line  += "|"
        else:
            high_line += " "
            low_line  += " "
        if level == 1:
            high_line += "-"
            low_line  += " "
        else:
            high_line += " "
            low_line  += "_"
    prefix = f"{label:<10}"
    return f"{prefix}{high_line}\n{' ' * len(prefix)}{low_line}"


# ---------------------------------------------------------------------------
# Ethernet preamble
# ---------------------------------------------------------------------------

def encode_preamble() -> Tuple[List[int], List[int]]:
    """
    Return (preamble_bits, manchester_samples) for the 8-byte
    IEEE 802.3 preamble (7 x 0xAA + 1 x 0xAB = SFD).
    """
    raw = PREAMBLE_BYTES + SFD_BYTE
    bits: List[int] = []
    for byte in raw:
        for shift in range(7, -1, -1):
            bits.append((byte >> shift) & 1)
    return bits, manchester_encode(bits)


# ---------------------------------------------------------------------------
# CRC-32 / FCS
# ---------------------------------------------------------------------------

def crc32_ethernet(data: bytes) -> bytes:
    """
    Compute the IEEE 802.3 CRC-32 Frame Check Sequence.
    Python's binascii.crc32 uses the same reflected polynomial (0xEDB88320).
    Returns 4 bytes, little-endian (as appended on the wire).
    """
    crc = binascii.crc32(data) & 0xFFFFFFFF
    return struct.pack("<I", crc)


# ---------------------------------------------------------------------------
# Ethernet frame assembly
# ---------------------------------------------------------------------------

def build_ethernet_frame(
    dst_mac: bytes,
    src_mac: bytes,
    ethertype: int,
    payload: bytes,
) -> bytes:
    """
    Build a DIX Ethernet frame (without preamble/SFD) with padding and FCS.

    Structure: Dst(6) | Src(6) | Type(2) | Data+Pad(46-1500) | FCS(4)
    Minimum payload 46 bytes (zero-padded). Maximum 1500 bytes.
    """
    if len(payload) > ETHERNET_MAX_PAYLOAD:
        raise ValueError(f"Payload {len(payload)} bytes exceeds 1500-byte maximum")
    if len(payload) < ETHERNET_MIN_PAYLOAD:
        payload = payload + bytes(ETHERNET_MIN_PAYLOAD - len(payload))

    header       = dst_mac + src_mac + struct.pack("!H", ethertype)
    frame_no_fcs = header + payload
    fcs          = crc32_ethernet(frame_no_fcs)
    return frame_no_fcs + fcs


# ---------------------------------------------------------------------------
# Slot time / minimum frame analysis
# ---------------------------------------------------------------------------

def slot_time_analysis(line_rate_mbps: float = 10.0, segment_m: float = 2500.0) -> dict:
    """
    Compute key CSMA/CD timing values for classic Ethernet.
    RG-8/U velocity factor: 0.77c (IEEE 802.3 spec).
    Slot time: 512 bit-times -> minimum frame must be 64 bytes.
    """
    prop_speed_ms = 0.77 * 3e8 / 1e3          # m/ms -> km/s units
    one_way_us    = (segment_m / (0.77 * 3e8)) * 1e6
    round_trip_us = 2 * one_way_us
    bit_time_ns   = 1000.0 / line_rate_mbps
    slot_time_us  = SLOT_TIME_BITS * bit_time_ns / 1000.0

    return {
        "one_way_us":      round(one_way_us, 2),
        "round_trip_us":   round(round_trip_us, 2),
        "slot_time_us":    slot_time_us,
        "min_frame_bytes": SLOT_TIME_BITS // 8,
        "fits_in_slot":    round_trip_us < slot_time_us,
    }


# ---------------------------------------------------------------------------
# Main demonstration
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 65)
    print("Classic Ethernet Physical Layer -- IEEE 802.3 Simulator")
    print("=" * 65)

    # 1. Preamble: show first 16 bits encoded as Manchester
    print("\n[1] Manchester Encoding -- first 16 preamble bits (10101010 10101010)")
    preamble_bits, _ = encode_preamble()
    first16  = preamble_bits[:16]
    encoded16 = manchester_encode(first16, samples_per_half=2)
    print("    Bits:  " + " ".join(str(b) for b in first16))
    for line in signal_to_ascii(encoded16, label="Signal:").splitlines():
        print("    " + line)

    # 2. SFD detection
    print("\n[2] Start Frame Delimiter (SFD) -- byte 8 = 0xAB = 10101011")
    sfd_bits = preamble_bits[56:64]
    print("    SFD bits:    " + " ".join(str(b) for b in sfd_bits))
    print("    Last 2 bits: '1 1' -- receiver: data frame starts now")

    # 3. Round-trip encode -> decode verification
    print("\n[3] Manchester Round-Trip Verification")
    test_bits = [1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 1, 0, 0, 1, 0, 0]
    encoded   = manchester_encode(test_bits, samples_per_half=2)
    decoded   = manchester_decode(encoded, samples_per_bit=4)
    print(f"    Original: {test_bits}")
    print(f"    Decoded:  {decoded}")
    print(f"    Match:    {test_bits == decoded}")

    # 4. Frame construction with CRC-32
    print("\n[4] Ethernet Frame Assembly (DIX format)")
    dst      = bytes([0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF])  # broadcast
    src      = bytes([0x00, 0x1A, 0x2B, 0x3C, 0x4D, 0x5E])
    etype    = 0x0800                                         # IPv4
    payload  = b"Hello, Ethernet!"                            # 16 bytes -> padded to 46

    frame = build_ethernet_frame(dst, src, etype, payload)
    print(f"    Dst MAC:    {':'.join(f'{b:02X}' for b in dst)}")
    print(f"    Src MAC:    {':'.join(f'{b:02X}' for b in src)}")
    print(f"    EtherType:  0x{etype:04X}  (IPv4)")
    print(f"    Payload in: {len(payload)} bytes -> padded to {ETHERNET_MIN_PAYLOAD} bytes")
    print(f"    Frame len:  {len(frame)} bytes  (min {ETHERNET_MIN_FRAME})")
    print(f"    FCS (CRC-32): 0x{frame[-4:].hex().upper()}")
    print(f"    802.3 compliant: {len(frame) >= ETHERNET_MIN_FRAME}")

    # 5. Bandwidth overhead
    print("\n[5] Manchester vs NRZ Bandwidth @ 10 Mbps")
    print("    NRZ minimum bandwidth:         5 MHz  (B/2 Nyquist)")
    print("    Manchester required bandwidth: 10 MHz (clock at 2x bit rate)")
    print("    Overhead factor:               2x  -- traded for embedded clock recovery")

    # 6. Slot time
    print("\n[6] CSMA/CD Slot Time (2500 m end-to-end, 10 Mbps)")
    t = slot_time_analysis(10.0, 2500.0)
    print(f"    One-way propagation:    {t['one_way_us']} us")
    print(f"    Round-trip propagation: {t['round_trip_us']} us")
    print(f"    Slot time (512 bits):   {t['slot_time_us']} us")
    print(f"    Round-trip < slot:      {t['fits_in_slot']}")
    print(f"    Min frame size:         {t['min_frame_bytes']} bytes")

    # 7. 5-4-3 rule
    print("\n[7] 5-4-3 Rule (IEEE 802.3 multi-segment constraints)")
    rules = [
        ("Segments total",     "5",    "max cable segments per collision domain"),
        ("Repeaters on path",  "4",    "max regenerative hops between any two stations"),
        ("Populated segments", "3",    "segments with attached stations"),
        ("Max span",           "2500 m", "end-to-end transceiver distance"),
    ]
    for label, value, reason in rules:
        print(f"    {label:<22} {value:<8}  {reason}")

    print("\n" + "=" * 65)


if __name__ == "__main__":
    main()
