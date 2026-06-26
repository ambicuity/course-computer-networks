"""
CRC Shift-Register Hardware and Live Packet-Trace Lab
=====================================================
Implements two CRC-32 engines and verifies they produce identical results:

  1. Bit-serial LFSR (reflected, LSB-first) — models the actual 802.3 hardware
     that processes bits as they arrive from the wire (LSB first per byte).
     Uses reflected polynomial 0xEDB88320.

  2. Table-driven (reflected, LSB-first) — one 256-entry lookup per byte,
     the standard software optimization used by every OS and NIC driver.

Both engines use IEEE 802.3 pre-conditioning (init = 0xFFFFFFFF) and
post-conditioning (final XOR 0xFFFFFFFF), and both agree with Python's
built-in binascii.crc32.

Also demonstrates:
  - Register-level trace for the first byte of a frame
  - Residue verification (0xDEBB20E3 raw / receiver magic constant)
  - FCS byte-range coverage: Dst MAC through Data+Pad (no preamble, no FCS)
  - The three classes of errors that CRC-32 guarantees to detect

Run:
    python3 main.py
"""

from __future__ import annotations
import binascii
import struct

# ---------------------------------------------------------------------------
# CRC-32 constants (IEEE 802.3 / Ethernet)
# ---------------------------------------------------------------------------
POLY_NORMAL    = 0x04C11DB7  # Generator polynomial (non-reflected / MSB-first notation)
POLY_REFLECTED = 0xEDB88320  # Bit-reversed form used in the wire-order (LSB-first) circuit
INIT_VALUE     = 0xFFFFFFFF  # Pre-conditioning: initialize register to all ones
FINAL_XOR      = 0xFFFFFFFF  # Post-conditioning: invert all 32 register bits

# Residue constants (raw accumulator value after processing a correct frame):
#   RESIDUE_REFLECTED = 0xDEBB20E3  → reflected (802.3 wire) algorithm
#   RESIDUE_NONREFL   = 0xC704DD7B  → non-reflected (MSB-first) academic convention
# Note: many textbooks cite 0xC704DD7B as "the" 802.3 residue; that value
# applies to the non-reflected description. The actual reflected-algorithm
# receiver checks for 0xDEBB20E3 in the raw accumulator.
RESIDUE_REFLECTED = 0xDEBB20E3
RESIDUE_NONREFL   = 0xC704DD7B


# ---------------------------------------------------------------------------
# Engine 1: Bit-serial LFSR — reflected (LSB-first), matching 802.3 wire order
# ---------------------------------------------------------------------------

def crc32_lfsr(data: bytes) -> int:
    """
    Compute CRC-32 bit-serially using the reflected (LSB-first) convention.
    Processes bit 0 of each byte first, using reflected polynomial 0xEDB88320.
    This mirrors the actual LFSR hardware that sees bits arriving LSB-first from
    the Ethernet wire.

    Each clock cycle:
        feedback  = register[0] XOR input_bit   (LSB of register)
        register >>= 1                            (shift right)
        if feedback: register ^= 0xEDB88320      (XOR reflected taps)
    """
    register = INIT_VALUE
    for byte in data:
        for bit_pos in range(0, 8):        # LSB first (reflected)
            bit = (byte >> bit_pos) & 1
            feedback = (register & 1) ^ bit
            register >>= 1
            if feedback:
                register ^= POLY_REFLECTED
    return register ^ FINAL_XOR


def lfsr_trace_byte(byte_val: int, register_in: int) -> list[tuple[int, int, int, int]]:
    """
    Trace LFSR register state for each of the 8 bits in one byte.
    Returns list of (bit_pos, input_bit, feedback, register_after).
    Uses the reflected (LSB-first) convention.
    """
    register = register_in
    trace: list[tuple[int, int, int, int]] = []
    for bit_pos in range(0, 8):            # LSB first
        bit = (byte_val >> bit_pos) & 1
        feedback = (register & 1) ^ bit
        register >>= 1
        if feedback:
            register ^= POLY_REFLECTED
        trace.append((bit_pos, bit, feedback, register))
    return trace


# ---------------------------------------------------------------------------
# Engine 2: Table-driven reflected CRC-32 (IEEE 802.3 standard software form)
# ---------------------------------------------------------------------------

def _make_crc_table() -> list[int]:
    """Precompute 256-entry CRC lookup table using the reflected polynomial."""
    table: list[int] = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ POLY_REFLECTED if crc & 1 else crc >> 1
        table.append(crc)
    return table


_CRC_TABLE = _make_crc_table()


def crc32_table_driven(data: bytes) -> int:
    """
    CRC-32 matching IEEE 802.3: reflected table-driven, pre/post-conditioned.
    One table lookup per byte — folds 8 LFSR steps into a single table access.

        crc = TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)

    The table contains the precomputed CRC effect of every 8-bit input byte
    XOR'd into the low byte of the current accumulator.
    """
    crc = INIT_VALUE
    for byte in data:
        crc = _CRC_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc ^ FINAL_XOR


def fcs_bytes(data: bytes) -> bytes:
    """Return the 4 FCS bytes to append, in little-endian wire order."""
    return struct.pack('<I', crc32_table_driven(data))


def verify_frame_residue(frame_with_fcs: bytes) -> bool:
    """
    Return True if frame (data + 4-byte FCS) has correct CRC.
    After processing a correctly formed frame through the reflected CRC engine,
    the raw accumulator (before post-conditioning) must equal RESIDUE_REFLECTED.
    """
    crc = INIT_VALUE
    for byte in frame_with_fcs:
        crc = _CRC_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc == RESIDUE_REFLECTED      # raw accumulator check (no final XOR)


# ---------------------------------------------------------------------------
# Demo sections
# ---------------------------------------------------------------------------

def demo_lfsr_circuit_explanation() -> None:
    print("=" * 68)
    print("SECTION 1 — THE LFSR HARDWARE CIRCUIT")
    print("=" * 68)
    print()
    print("  A 32-bit shift register with XOR feedback taps computes CRC-32.")
    print("  Bits arrive from the wire LSB-first; the LFSR uses the reflected")
    print("  polynomial 0xEDB88320 (bit-reverse of 0x04C11DB7).")
    print()
    print("  Wire ──►[XOR]──►[b31] ◄──[b30] ◄── ... ◄──[b1] ◄──[b0]")
    print("             ▲                                           │")
    print("             └─────────── XOR feedback taps ────────────┘")
    print("                  (taps match reflected G(x) coefficients)")
    print()
    print("  Each clock cycle (reflected convention, LSB-first):")
    print("    1. feedback  = register[0] XOR input_bit  (LSB of register)")
    print("    2. register >>= 1                          (shift right)")
    print("    3. if feedback: register ^= 0xEDB88320    (XOR reflected taps)")
    print()
    print("  IEEE 802.3 Conventions")
    print("  ─────────────────────────────────────────────────────────────────")
    print(f"  Pre-conditioning : init register = 0x{INIT_VALUE:08X}  (all ones)")
    print(f"  Bit order        : LSB of each byte first (reflected)")
    print(f"  Polynomial       : 0x{POLY_REFLECTED:08X}  (reflected 0x{POLY_NORMAL:08X})")
    print(f"  Post-conditioning: final XOR with 0x{FINAL_XOR:08X}")
    print(f"  Residue (wire)   : 0x{RESIDUE_REFLECTED:08X}  (raw accumulator, correct frame)")
    print()
    print("  Original polynomial G(x):")
    print("  x^32 + x^26 + x^23 + x^22 + x^16 + x^12 + x^11 + x^10")
    print("       + x^8  + x^7  + x^5  + x^4  + x^2  + x   + 1")
    print(f"  Lower 32 coefficients: 0x{POLY_NORMAL:08X}")
    print()


def demo_lfsr_byte_trace() -> None:
    print("=" * 68)
    print("SECTION 2 — LFSR REGISTER TRACE  (reflected, LSB-first)")
    print("=" * 68)
    print()
    # Use the first byte of a broadcast Ethernet frame (0xFF = Dst MAC byte 0)
    byte_val = 0xFF
    register_init = INIT_VALUE

    print(f"  Tracing byte 0x{byte_val:02X} ({byte_val:08b}b) through the reflected LFSR")
    print(f"  Initial register (pre-conditioned): 0x{register_init:08X}")
    print()
    print(f"  {'Bit':>4}  {'Input':>5}  {'Feedback':>8}  {'Register After':>14}")
    print("  " + "-" * 38)
    trace = lfsr_trace_byte(byte_val, register_init)
    for bit_pos, inp, fb, reg_after in trace:
        print(f"  b{bit_pos:<2}   {inp:>4}       {fb:>4}    0x{reg_after:08X}")
    print()
    print(f"  Register after byte 0x{byte_val:02X}: 0x{trace[-1][3]:08X}")
    print()
    print("  The 8 XOR-shift steps above are exactly what the table-driven")
    print("  engine folds into a single entry in the 256-entry lookup table.")
    print()


def demo_two_engines_comparison() -> None:
    print("=" * 68)
    print("SECTION 3 — REFLECTED LFSR vs TABLE-DRIVEN vs PYTHON stdlib")
    print("=" * 68)
    print()
    # Minimal Ethernet-shaped frame: Dst(6) + Src(6) + EtherType(2) + Payload(46)
    dst       = bytes([0xFF] * 6)                           # broadcast Dst MAC
    src       = bytes([0x00, 0x11, 0x22, 0x33, 0x44, 0x55])
    ethertype = bytes([0x08, 0x00])                         # IPv4 EtherType
    payload   = b'Hello, Ethernet!' + bytes(30)             # 46-byte payload
    frame     = dst + src + ethertype + payload

    print("  Frame (Dst MAC through Data+Pad):")
    print(f"    Dst MAC   : {dst.hex(':')}")
    print(f"    Src MAC   : {src.hex(':')}")
    print(f"    EtherType : {ethertype.hex()}")
    print(f"    Payload   : {payload[:16]!r} + 30 zero bytes  ({len(payload)} B)")
    print(f"    Total     : {len(frame)} bytes")
    print()

    lfsr_result   = crc32_lfsr(frame)
    table_result  = crc32_table_driven(frame)
    stdlib_result = binascii.crc32(frame) & 0xFFFFFFFF

    print(f"  Reflected bit-serial LFSR : 0x{lfsr_result:08X}")
    print(f"  Table-driven (256 entry)  : 0x{table_result:08X}")
    print(f"  Python binascii.crc32     : 0x{stdlib_result:08X}")
    print()

    all_agree = (lfsr_result == table_result == stdlib_result)
    status = "PASS — all three identical" if all_agree else "FAIL — mismatch detected"
    print(f"  All three agree: {all_agree}  ← {status}")
    print()

    fcs = fcs_bytes(frame)
    print(f"  FCS (4 bytes, little-endian / wire order): {fcs.hex(' ')}")
    print(f"  Wire transmits LSB byte first: {' '.join(f'{b:02x}' for b in fcs)}")
    print(f"  CRC value as 32-bit integer  : 0x{table_result:08X}")
    print()
    print("  The table-driven engine processes one byte per lookup instead of")
    print("  8 individual XOR-shift steps, giving ~8× fewer operations.")
    print()


def demo_residue_check() -> None:
    print("=" * 68)
    print("SECTION 4 — RESIDUE VERIFICATION")
    print("=" * 68)
    print()
    print("  After the receiver runs a correct frame (data + 4-byte FCS) through")
    print("  the reflected CRC engine, the raw accumulator must equal:")
    print(f"    0x{RESIDUE_REFLECTED:08X}   (reflected / wire-order algorithm)")
    print()
    print("  Note: many textbooks cite 0xC704DD7B as the residue.  That value")
    print("  is correct for the NON-reflected (MSB-first) academic description.")
    print("  The reflected 802.3 hardware checks for 0xDEBB20E3.")
    print()

    dst        = bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF])
    src        = bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66])
    ethertype  = bytes([0x08, 0x00])
    payload    = b'CRC residue test' + bytes(30)
    frame_data = dst + src + ethertype + payload

    fcs = fcs_bytes(frame_data)
    frame_with_fcs = frame_data + fcs

    ok = verify_frame_residue(frame_with_fcs)
    print(f"  Frame data  : {len(frame_data)} bytes")
    print(f"  FCS appended: {fcs.hex(' ')}")
    print(f"  Full frame  : {len(frame_with_fcs)} bytes")
    verdict = "PASS — raw accumulator = 0xDEBB20E3" if ok else "FAIL"
    print(f"  Residue check: {verdict}")
    print()

    # Corrupt one bit and verify detection
    corrupted = bytearray(frame_with_fcs)
    corrupted[20] ^= 0x01            # flip one bit deep in payload
    ok_corrupt = verify_frame_residue(bytes(corrupted))
    verdict2 = "PASS (undetected!)" if ok_corrupt else "DETECTED — accumulator changed"
    print(f"  After 1-bit flip at payload byte 20:")
    print(f"  Residue check: {verdict2}")
    print()


def demo_fcs_coverage() -> None:
    print("=" * 68)
    print("SECTION 5 — FCS BYTE-RANGE COVERAGE AND WIRE ORDER")
    print("=" * 68)
    print()
    print("  IEEE 802.3 Ethernet frame layout:")
    print()
    print("  ┌──────────┬─────────┬─────────┬──────────┬──────────────┬───────┐")
    print("  │ Preamble │ Dst MAC │ Src MAC │ Type/Len │  Data + Pad  │  FCS  │")
    print("  │  8 bytes │ 6 bytes │ 6 bytes │  2 bytes │  46–1500 B   │ 4 B   │")
    print("  └──────────┴─────────┴─────────┴──────────┴──────────────┴───────┘")
    print("             │     CRC-32 covers this range               │")
    print("             └────────────────────────────────────────────┘")
    print("  NOT covered: Preamble (8 bytes) and FCS field itself (4 bytes).")
    print()
    print("  Wire-order: CRC value 0x12345678 is sent on wire as bytes: 78 56 34 12")
    print("  (least-significant byte first — little-endian byte order).")
    print()

    dst        = bytes([0xFF] * 6)
    src        = bytes([0x00, 0x11, 0x22, 0x33, 0x44, 0x55])
    ethertype  = bytes([0x08, 0x00])
    payload    = b'coverage demo!  ' + bytes(30)
    frame_data = dst + src + ethertype + payload

    correct   = crc32_table_driven(frame_data)
    no_dst    = crc32_table_driven(src + ethertype + payload)
    preamble  = bytes([0x55] * 7 + [0xD5])
    w_pream   = crc32_table_driven(preamble + frame_data)

    print(f"  Correct CRC (Dst MAC → Data)     : 0x{correct:08X}")
    print(f"  BUG A — CRC starts at Src MAC    : 0x{no_dst:08X}  (Dst MAC excluded)")
    print(f"  BUG B — CRC includes Preamble    : 0x{w_pream:08X}  (Preamble included)")
    print()
    print("  Both bugs produce a CRC mismatch at the receiver — exactly the")
    print("  appliance fault described in the problem statement.")
    print()


def demo_error_detection_guarantees() -> None:
    print("=" * 68)
    print("SECTION 6 — ERROR DETECTION GUARANTEES")
    print("=" * 68)
    print()
    rows = [
        ("All single-bit errors",       "100%",               "Any 1-bit flip alters the CRC"),
        ("All double-bit errors",        "100%",               "HD ≥ 4 for frames ≤ 11,454 bytes"),
        ("All odd-count-bit errors",     "100%",               "(x+1) is a factor of G(x)"),
        ("All burst errors ≤ 32 bits",   "100%",               "r=32 → all bursts of length ≤ r"),
        ("Burst of exactly 33 bits",     "all but 1 in 2^31",  "≈ 1 in 2.1 billion undetected"),
        ("Burst > 33 bits",              "all but 1 in 2^32",  "≈ 1 in 4.3 billion undetected"),
    ]
    print(f"  {'Error Type':<35} {'Detection':<26} {'Reason'}")
    print("  " + "-" * 90)
    for etype, det, reason in rows:
        print(f"  {etype:<35} {det:<26} {reason}")
    print()
    print("  For a typical Ethernet frame:")
    print("    P(undetected random error) ≈ 1 in 4.3 × 10^9")
    print()


def main() -> None:
    print()
    print("CRC SHIFT-REGISTER HARDWARE AND LIVE PACKET-TRACE LAB")
    print("Computer Networks — Phase 04, Lesson 28")
    print()
    demo_lfsr_circuit_explanation()
    demo_lfsr_byte_trace()
    demo_two_engines_comparison()
    demo_residue_check()
    demo_fcs_coverage()
    demo_error_detection_guarantees()
    print("See docs/en.md for full theoretical background and exercises.")


if __name__ == "__main__":
    main()
