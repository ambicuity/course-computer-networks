"""PCM T1/E1 carriers and signaling bits.

Stdlib-only models of the digital telephone trunk hierarchy:
  * DS0 / 64 kbps derivation from the 125 us Nyquist cadence
  * T1 (DS1) 193-bit frame with the framing bit
  * Robbed-bit signaling (RBS) on the 6th frame of a D4 superframe
  * Extended Superframe (ESF): 001011 framing pattern + CRC-6 + FDL
  * E1 256-bit frame: slot 0 alignment, slot 16 CAS multiframe, 30 payload
  * A-law / u-law (G.711) decoders so you can read companded bytes
  * The T-carrier and E-carrier hierarchies up to T4 / E4

No external dependencies, no network calls.  Run:  python3 main.py
"""

from __future__ import annotations

# --- Fixed constants of the digital telephone world -------------------------

SAMPLES_PER_SECOND = 8000          # Nyquist rate for a 4 kHz channel
FRAME_PERIOD_US = 1_000_000 // SAMPLES_PER_SECOND  # 125 us
BITS_PER_SAMPLE = 8
DS0_BPS = BITS_PER_SAMPLE * SAMPLES_PER_SECOND     # 64 000


# --- DS0 / T1 / E1 frame construction ---------------------------------------

def build_t1_frame(samples: list[int], frame_index: int,
                   signaling_mode: str = "rbs") -> list[int]:
    """Pack 24 8-bit samples into a 193-bit T1 frame.

    Bit 1 is the F (framing) bit; bits 2..193 are the 24 channels.
    In RBS mode the LSB of every channel byte is stolen on every 6th frame
    (frames 6 and 12 of the D4 superframe) to carry channel-associated
    signaling.  In 'clear' mode (B8ZS + CCS) no bits are stolen.
    """
    if len(samples) != 24:
        raise ValueError("T1 frame needs exactly 24 channel samples")
    bits: list[int] = []
    # F bit: simple alternating superframe pattern 101010... for D4.
    bits.append(frame_index % 2)
    # D4 superframe: signaling on the 6th and 12th frames (1-indexed),
    # i.e. every 6th frame.  0-indexed that is frames 5, 11, 17, 23.
    sixth_frame = (frame_index % 6) == 5
    for sample in samples:
        if signaling_mode == "rbs" and sixth_frame:
            sample = sample & 0xFE  # steal the LSB
        for b in range(7, -1, -1):
            bits.append((sample >> b) & 1)
    assert len(bits) == 193, len(bits)
    return bits


def t1_gross_bps() -> int:
    return 193 * SAMPLES_PER_SECOND  # 1 544 000


def t1_payload_bps() -> int:
    return 24 * DS0_BPS  # 1 536 000


# --- Extended Superframe (ESF) and CRC-6 ------------------------------------

ESF_FRAMES = 24
ESF_FRAMING_PATTERN = [0, 0, 1, 0, 1, 1]  # bits at frames 4,8,12,16,20,24
ESF_FRAMING_FRAMES = [3, 7, 11, 15, 19, 23]      # 0-indexed
ESF_CRC_FRAMES = [1, 5, 9, 13, 17, 21]           # 0-indexed
ESF_FDL_FRAMES = [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22]


def crc6(payload_bits: list[int]) -> list[int]:
    """Compute the 6-bit CRC-6 (polynomial x^6 + x + 1, 0x03) over payload."""
    crc = 0
    poly = 0x03
    for bit in payload_bits:
        crc ^= bit << 5
        for _ in range(6):
            crc <<= 1
            if crc & (1 << 6):
                crc ^= poly
            crc &= 0x3F
    return [(crc >> b) & 1 for b in range(5, -1, -1)]


def build_esf(payload_blocks: list[list[int]]) -> list[list[int]]:
    """Assemble 24 T1 frames into an ESF with proper F-bit roles.

    Each payload block is 192 bits (24 channels x 8 bits, no F bit).
    Returns the 24 frames as 193-bit lists.
    """
    if len(payload_blocks) != ESF_FRAMES:
        raise ValueError("ESF needs 24 payload blocks")
    # Concatenate payload bits for the CRC computation.
    all_payload = [b for blk in payload_blocks for b in blk]
    crc_bits = crc6(all_payload)
    frames: list[list[int]] = []
    pat_idx = 0
    crc_idx = 0
    for i in range(ESF_FRAMES):
        f_bit = 0
        if i in ESF_FRAMING_FRAMES:
            f_bit = ESF_FRAMING_PATTERN[pat_idx]
            pat_idx += 1
        elif i in ESF_CRC_FRAMES:
            f_bit = crc_bits[crc_idx]
            crc_idx += 1
        # FDL frames carry a fixed idle byte; we keep them 0 for the demo.
        frames.append([f_bit] + payload_blocks[i])
    return frames


def extract_esf_crc(frames: list[list[int]]) -> list[int]:
    return [frames[i][0] for i in ESF_CRC_FRAMES]


def inject_bit_error(frames: list[list[int]], bit_index: int) -> None:
    """Flip a single payload bit inside the first frame's payload region."""
    # Frame 0, payload starts at index 1.
    frames[0][1 + bit_index] ^= 1


# --- E1 frame and CAS multiframe --------------------------------------------

E1_SLOTS = 32
E1_FRAME_BITS = E1_SLOTS * BITS_PER_SAMPLE  # 256
E1_FRAME_ALIGNMENT = [0, 0, 1, 1, 0, 1, 1, 0]  # FAS in slot 0 (odd frames)


def build_e1_frame(slots: list[int], frame_index: int,
                   cas_nibbles: list[int] | None = None) -> list[int]:
    """Pack 32 8-bit slots into a 256-bit E1 frame.

    Slot 0 carries the frame-alignment signal on odd frames.
    Slot 16 carries CAS signaling nibbles when a multiframe is in use.
    Slots 1-15 and 17-31 are the 30 payload channels.
    """
    if len(slots) != E1_SLOTS:
        raise ValueError("E1 frame needs exactly 32 slots")
    bits: list[int] = []
    for slot in range(E1_SLOTS):
        byte = slots[slot]
        if slot == 0 and (frame_index % 2) == 1:
            byte = 0
            for b in E1_FRAME_ALIGNMENT:
                byte = (byte << 1) | b
        if slot == 16 and cas_nibbles is not None:
            # Replace slot 16 with two CAS nibbles for two channels.
            ch_pair = frame_index % 15
            hi = cas_nibbles[ch_pair * 2] & 0x0F
            lo = cas_nibbles[ch_pair * 2 + 1] & 0x0F
            byte = (hi << 4) | lo
        for b in range(7, -1, -1):
            bits.append((byte >> b) & 1)
    assert len(bits) == E1_FRAME_BITS
    return bits


def e1_gross_bps() -> int:
    return E1_FRAME_BITS * SAMPLES_PER_SECOND  # 2 048 000


def e1_payload_bps() -> int:
    return 30 * DS0_BPS  # 1 920 000


# --- G.711 companding decoders ----------------------------------------------

def mu_to_linear(byte: int) -> int:
    """Decode a u-law sample (G.711) to 14-bit linear PCM."""
    byte = ~byte & 0xFF
    sign = byte & 0x80
    exponent = (byte >> 4) & 0x07
    mantissa = byte & 0x0F
    sample = ((mantissa << 3) + 0x84) << exponent
    sample -= 0x84
    return -sample if sign else sample


def a_to_linear(byte: int) -> int:
    """Decode an A-law sample (G.711) to 13-bit linear PCM."""
    byte ^= 0x55
    sign = byte & 0x80
    exponent = (byte >> 4) & 0x07
    mantissa = byte & 0x0F
    if exponent == 0:
        sample = (mantissa << 1) + 1
    else:
        sample = ((mantissa << 4) + 0x108) << (exponent - 1)
    return -sample if sign else sample


# --- Carrier hierarchies ----------------------------------------------------
# Each row: (level, payload_channels, published_bps).
# Overhead = published - (payload_channels * 64 kbps): the framing/control
# bits added so the receiver can recover from slips and find frame boundaries.

T_HIERARCHY = [
    ("T1", 24,   1_544_000),
    ("T2", 96,   6_312_000),
    ("T3", 672,  44_736_000),
    ("T4", 4032, 274_176_000),
]

E_HIERARCHY = [
    ("E1", 30,   2_048_000),
    ("E2", 120,  8_848_000),
    ("E3", 480,  34_368_000),
    ("E4", 1920, 139_264_000),
]


def print_hierarchy(name: str, rows: list[tuple[str, int, int]]) -> None:
    print(f"\n{name} hierarchy (payload channels -> published rate):")
    for level, channels, published in rows:
        payload = channels * DS0_BPS
        over = published - payload
        print(f"  {level}: {channels} ch ({payload/1e6:.3f} Mbps payload) -> "
              f"published {published/1e6:.3f} Mbps "
              f"(framing overhead {over/1e3:.0f} kbps)")


# --- Demo -------------------------------------------------------------------

def main() -> None:
    print("=== DS0 building block ===")
    print(f"Sampling rate    : {SAMPLES_PER_SECOND} samples/s (Nyquist for 4 kHz)")
    print(f"Frame period     : {FRAME_PERIOD_US} us")
    print(f"Bits per sample  : {BITS_PER_SAMPLE}")
    print(f"DS0 rate         : {DS0_BPS} bps = {DS0_BPS/1000:.0f} kbps")

    print("\n=== T1 (DS1) frame ===")
    samples = [(0x81 + 2 * ch) & 0xFF for ch in range(24)]  # all odd LSBs
    build_t1_frame(samples, frame_index=5, signaling_mode="rbs")
    print("Frame length     : 193 bits (24x8 + 1 F bit)")
    print(f"Gross rate       : {t1_gross_bps()} bps = {t1_gross_bps()/1e6:.3f} Mbps")
    print(f"Payload rate     : {t1_payload_bps()} bps = {t1_payload_bps()/1e6:.3f} Mbps")
    print(f"Overhead (F bit) : {t1_gross_bps() - t1_payload_bps()} bps = 8 kbps")
    # Show RBS stealing on frame 5 (0-indexed) = the 6th frame of the superframe.
    rb_frame = build_t1_frame(samples, frame_index=5, signaling_mode="rbs")
    clear_frame = build_t1_frame(samples, frame_index=5, signaling_mode="clear")
    stolen = sum(1 for a, b in zip(rb_frame, clear_frame) if a != b)
    print(f"RBS 6th-frame    : {stolen} LSBs stolen across 24 channels -> "
          f"data ceiling 56 kbps/slot")
    # And a non-signaling frame for contrast.
    plain_frame = build_t1_frame(samples, frame_index=0, signaling_mode="rbs")
    clear0 = build_t1_frame(samples, frame_index=0, signaling_mode="clear")
    stolen0 = sum(1 for a, b in zip(plain_frame, clear0) if a != b)
    print(f"RBS frame 0      : {stolen0} LSBs stolen (non-signaling frame, expected 0)")

    print("\n=== Extended Superframe (ESF) + CRC-6 ===")
    payload_blocks = [[0] * 192 for _ in range(ESF_FRAMES)]
    esf = build_esf(payload_blocks)
    crc_good = extract_esf_crc(esf)
    pattern = [esf[i][0] for i in ESF_FRAMING_FRAMES]
    print(f"ESF framing bits : {pattern}  (expected {ESF_FRAMING_PATTERN})")
    print(f"ESF CRC-6        : {crc_good}")
    inject_bit_error(esf, bit_index=40)
    # Recompute CRC over the (now corrupted) payload and compare.
    corrupted_payload = [b for fr in esf for b in fr[1:]]
    crc_bad = crc6(corrupted_payload)
    print(f"After 1-bit flip : recomputed CRC-6 = {crc_bad}")
    print(f"CRC mismatch     : {crc_good != crc_bad}  -> receiver flags loss of sync")

    print("\n=== E1 frame ===")
    slots = [0x55] * E1_SLOTS
    build_e1_frame(slots, frame_index=1, cas_nibbles=[0x8, 0x1] * 15)
    print("Frame length     : 256 bits (32 x 8)")
    print(f"Gross rate       : {e1_gross_bps()} bps = {e1_gross_bps()/1e6:.3f} Mbps")
    print(f"Payload rate     : {e1_payload_bps()} bps = {e1_payload_bps()/1e6:.3f} Mbps")
    print("Slot 0           : frame alignment (FAS on odd frames)")
    print("Slot 16          : CAS multiframe signaling (4 bits/channel)")
    print("Payload slots    : 30 (1-15, 17-31) at 64 kbps each")

    print("\n=== G.711 companding decoders ===")
    for code in (0xFF, 0x87, 0x00):
        print(f"  u-law 0x{code:02X} -> linear {mu_to_linear(code):+6d}")
    for code in (0x54, 0xA8, 0x15):
        print(f"  A-law 0x{code:02X} -> linear {a_to_linear(code):+6d}")

    print_hierarchy("T-carrier (US/Japan)", T_HIERARCHY)
    print_hierarchy("E-carrier (CEPT/ITU)", E_HIERARCHY)


if __name__ == "__main__":
    main()
