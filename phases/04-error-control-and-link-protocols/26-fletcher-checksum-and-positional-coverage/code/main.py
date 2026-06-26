"""Fletcher's checksum, the Internet checksum, and Adler-32: a runnable comparison.

This module implements, in pure standard-library Python, four error-detection
schemes that appear together in real protocols:

    * internet_checksum()  -- RFC 1071 one's-complement 16-bit sum (IPv4/TCP/UDP)
    * fletcher16()         -- Fletcher (1982) two 8-bit accumulators, mod 255
    * fletcher32()         -- Fletcher two 16-bit accumulators, mod 65535
    * adler32()            -- RFC 3309 / RFC 1950 Adler-32 (mod 65521, s1 seeded 1)

The goal is to make the *positional* property of Fletcher/Adler visible against
the position-blindness of the Internet checksum.  The demo at the bottom runs
every scheme on a fixed message, then on five mutated variants -- single-bit
flip, compensating two-word error, word swap, zero-word insertion, and a 16-bit
burst -- and prints DETECTED / MISSED for each.

Run:
    python3 code/main.py
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Detection primitives
# ---------------------------------------------------------------------------

# Modulus constants.  Fletcher uses a Mersenne number 2^k - 1 so that an
# end-around carry is equivalent to folding it back into the low bits -- the
# same one's-complement trick the Internet checksum uses.  Adler swaps the
# Fletcher-32 modulus 65535 for the largest prime below 2^16.
_MOD_FLETCHER16 = 255      # 2^8 - 1
_MOD_FLETCHER32 = 65535    # 2^16 - 1
_MOD_ADLER32 = 65521       # largest prime < 2^16


def internet_checksum(data: bytes) -> int:
    """RFC 1071 Internet checksum: one's-complement 16-bit sum.

    The sum is computed modulo 2^16 with end-around carry (every carry out of
    the high bit is added back into the low half) and the stored value is the
    bitwise NOT of that sum.  Verification folds the stored value into the sum
    and checks for the all-ones sentinel (see verify_internet).
    """
    if len(data) % 2 == 1:
        data = data + b"\x00"   # pad odd-length payload per RFC 1071
    total = 0
    for i in range(0, len(data), 2):
        word = (data[i] << 8) | data[i + 1]
        total += word
    # Fold end-around carry until it fits in 16 bits.
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def verify_internet(data: bytes, stored: int) -> bool:
    """Validate by folding the stored checksum in and checking for all-ones."""
    padded = data if len(data) % 2 == 0 else data + b"\x00"
    total = stored
    for i in range(0, len(padded), 2):
        word = (padded[i] << 8) | padded[i + 1]
        total += word
    while total >> 16:
        total = (total & 0xFFFF) + (total >> 16)
    # A valid frame sums to 0xFFFF (all ones); ~0xFFFF == 0 would also work.
    return total == 0xFFFF


def fletcher16(data: bytes) -> int:
    """Fletcher-16: two 8-bit accumulators mod 255. Returns (s2 << 8) | s1."""
    s1 = 0
    s2 = 0
    for byte in data:
        s1 = (s1 + byte) % _MOD_FLETCHER16
        s2 = (s2 + s1) % _MOD_FLETCHER16
    return (s2 << 8) | s1


def fletcher32(data: bytes) -> int:
    """Fletcher-32: two 16-bit accumulators mod 65535 over 16-bit words."""
    s1 = 0
    s2 = 0
    for i in range(0, len(data) - 1, 2):
        word = (data[i] << 8) | data[i + 1]
        s1 = (s1 + word) % _MOD_FLETCHER32
        s2 = (s2 + s1) % _MOD_FLETCHER32
    if len(data) % 2 == 1:
        # Trailing odd byte: treat as the high byte of a 16-bit word.
        word = data[-1] << 8
        s1 = (s1 + word) % _MOD_FLETCHER32
        s2 = (s2 + s1) % _MOD_FLETCHER32
    return (s2 << 16) | s1


def adler32(data: bytes) -> int:
    """RFC 3309 / RFC 1950 Adler-32: s1 seeded at 1, modulus 65521."""
    s1 = 1
    s2 = 0
    for byte in data:
        s1 = (s1 + byte) % _MOD_ADLER32
        s2 = (s2 + s1) % _MOD_ADLER32
    return (s2 << 16) | s1


# ---------------------------------------------------------------------------
# Mutations used by the demo -- each represents a real-world failure mode.
# ---------------------------------------------------------------------------

def flip_bit(data: bytes, bit_index: int) -> bytes:
    out = bytearray(data)
    byte_index, offset = divmod(bit_index, 8)
    out[byte_index] ^= (1 << (7 - offset))
    return bytes(out)


def flip_two_compensating_bits(data: bytes) -> bytes:
    """Flip bit p of word i 0->1 and bit p of word j 1->0 (net zero to sum)."""
    out = bytearray(data)
    if len(out) >= 11:
        out[0] |= 0x01          # 0 -> 1 at (word0, low bit)
        out[8] &= ~0x01 & 0xFF  # 1 -> 0 at (word4, low bit)
    return bytes(out)


def swap_two_words(data: bytes) -> bytes:
    """Swap the first and fifth 16-bit words (pure position change)."""
    if len(data) < 10:
        return data
    out = bytearray(data)
    out[0:2], out[8:10] = data[8:10], data[0:2]
    return bytes(out)


def insert_zero_word(data: bytes) -> bytes:
    """Inject a 0x0000 word after byte 4 -- a silent word insertion."""
    return data[:4] + b"\x00\x00" + data[4:]


def sixteen_bit_burst(data: bytes) -> bytes:
    """Flip every bit across a 16-bit (2-byte) span starting at byte 6."""
    out = bytearray(data)
    if len(out) >= 8:
        out[6] ^= 0xFF
        out[7] ^= 0xFF
    return bytes(out)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def verdict(original: int, mutated: int) -> str:
    return "DETECTED" if original != mutated else "MISSED"


def trace_fletcher16(data: bytes) -> list[tuple[int, int, int, int]]:
    """Return (step, byte, s1, s2) rows for a small message -- for teaching."""
    rows: list[tuple[int, int, int, int]] = []
    s1 = s2 = 0
    for step, byte in enumerate(data):
        s1 = (s1 + byte) % _MOD_FLETCHER16
        s2 = (s2 + s1) % _MOD_FLETCHER16
        rows.append((step, byte, s1, s2))
    return rows


def print_trace(rows: list[tuple[int, int, int, int]]) -> None:
    print(f"{'step':>4} {'byte':>6} {'s1':>4} {'s2':>4}")
    for step, byte, s1, s2 in rows:
        print(f"{step:>4} {byte:>6} {s1:>4} {s2:>4}")
    final = (rows[-1][3] << 8) | rows[-1][2] if rows else 0
    print(f"  Fletcher-16 checksum = 0x{final:04X}\n")


def main() -> None:
    # A fixed 32-byte test message: 1..16 then 1..16 again.  Non-zero and
    # position-dependent, so a swap actually changes the byte order.
    base = bytes(range(1, 17)) * 2

    print("=== Reference checksums on the clean 32-byte message ===")
    print(f"  Internet checksum (RFC 1071) : 0x{internet_checksum(base):04X}")
    print(f"  Fletcher-16                  : 0x{fletcher16(base):04X}")
    print(f"  Fletcher-32                  : 0x{fletcher32(base):08X}")
    print(f"  Adler-32 (RFC 3309)          : 0x{adler32(base):08X}\n")

    print("=== Hand-trace of Fletcher-16 on {{0x01, 0x02, 0x03}} ===")
    print_trace(trace_fletcher16(b"\x01\x02\x03"))

    mutations = [
        ("single-bit flip at bit 0       ", flip_bit(base, 0)),
        ("compensating two-word bit flips", flip_two_compensating_bits(base)),
        ("swap word0 <-> word4           ", swap_two_words(base)),
        ("insert 0x0000 word after byte 4", insert_zero_word(base)),
        ("16-bit burst at byte 6         ", sixteen_bit_burst(base)),
    ]

    ref_internet = internet_checksum(base)
    ref_f16 = fletcher16(base)
    ref_f32 = fletcher32(base)
    ref_adler = adler32(base)

    print("=== Detection matrix (DETECTED = checksum changed, MISSED = blind) ===")
    print("  Error                             Internet      Fletcher-16   Fletcher-32   Adler-32")
    print("  " + "-" * 92)
    for label, mod in mutations:
        cells = (
            f"{verdict(ref_internet, internet_checksum(mod)):<12} "
            f"{verdict(ref_f16, fletcher16(mod)):<12} "
            f"{verdict(ref_f32, fletcher32(mod)):<12} "
            f"{verdict(ref_adler, adler32(mod)):<12}"
        )
        print(f"  {label}{cells}")

    print("\n=== RFC 1071 fold-and-check verification on the clean message ===")
    stored = internet_checksum(base)
    print(f"  stored checksum = 0x{stored:04X}; verify_internet -> {verify_internet(base, stored)}")

    print("\n=== Adler-32 seed symmetry test (all-zero payload) ===")
    zero_payload = b"\x00" * 32
    print(f"  Adler-32 of 32 zero bytes = 0x{adler32(zero_payload):08X}")
    print("  (s1 starts at 1, so the result is never all-zero for non-empty input)\n")


if __name__ == "__main__":
    main()