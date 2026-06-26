"""Internet 16-bit checksum in one's complement arithmetic.

This module implements the 16-bit Internet checksum exactly as specified in
RFC 1071 ("Computing the Internet Checksum") and used by IP, TCP, UDP, ICMP
and IGMP. Two routines are provided:

  * ``folded_ones_complement_sum`` -- sum 16-bit words using one's-complement
    arithmetic with end-around carry, returning the pre-folded 32-bit
    accumulator and the final 16-bit value.
  * ``internet_checksum`` / ``verify_checksum`` -- compute and verify the
    checksum exactly as a packet implementation would.

The "end-around carry" (folding overflow bits back into the low-order bits)
and the final one's complement are what distinguish this from a plain
modulo-2**16 sum; see the accompanying lesson for why.
"""

from __future__ import annotations

MASK16 = 0xFFFF


def _byte_align(data: bytes) -> bytes:
    """Pad odd-length data with a trailing zero byte so it forms whole words.

    Internet protocols operate on 16-bit words; a trailing odd byte is
    conceptually zero-extended (RFC 1071, Sec. 1) so the sum is well-defined.
    """
    if len(data) % 2 == 1:
        return data + b"\x00"
    return data


def fold_carry(total: int) -> int:
    """Fold carry bits from a 32-bit accumulator into the low 16 bits.

    Equivalent to adding the high half to the low half repeatedly until no
    overflow remains (the "end-around carry" of one's-complement arithmetic).
    """
    while total >> 16:
        total = (total & MASK16) + (total >> 16)
    return total & MASK16


def folded_ones_complement_sum(data: bytes) -> tuple[int, int]:
    """Sum 16-bit big-endian words in one's-complement arithmetic.

    Returns (pre_fold_accumulator, final_16_bit_value).

    The procedure, per RFC 1071:
      1. Interpret the bytes as a sequence of 16-bit big-endian words.
      2. Add them as ordinary integers. Carry bits simply accumulate
         in the upper half of the 32-bit accumulator.
      3. Fold all carry bits back into the low 16 bits until no
         high-order bits remain ("end-around carry").
      4. The final value is the 32-bit accumulator masked to 16 bits;
         the checksum itself is its one's complement.
    """
    words = _byte_align(data)
    total = 0
    for i in range(0, len(words), 2):
        word = (words[i] << 8) | words[i + 1]  # big-endian: high byte first
        total += word
    return total, fold_carry(total)


def internet_checksum(data: bytes) -> int:
    """Return the 16-bit Internet checksum.

    The checksum is the *one's complement* of the one's-complement sum of the
    data treated as 16-bit words. When computed over a packet, the checksum
    field must be zero; the returned value goes into that field on the wire.
    """
    _, folded = folded_ones_complement_sum(data)
    return (~folded) & MASK16


def verify_checksum(data: bytes) -> bool:
    """Return True iff data's combined data+checksum sums to all-ones (0xFFFF).

    A correct Internet checksum means the receiver's one's-complement sum over
    the entire packet (including the sender's checksum field) is 0xFFFF, whose
    one's complement is 0 -- the "result is zero" property described in
    RFC 1071.
    """
    _, folded = folded_ones_complement_sum(data)
    return folded == MASK16


def flip_bits(buf: bytes, positions: list[int]) -> bytes:
    """Return a copy of ``buf`` with the given bit positions inverted."""
    out = bytearray(buf)
    for pos in positions:
        byte_index, bit_index = divmod(pos, 8)
        out[byte_index] ^= 1 << (7 - bit_index)
    return bytes(out)


def to_16bit_words(data: bytes) -> list[int]:
    """Human-readable list of 16-bit big-endian words (with zero padding)."""
    padded = _byte_align(data)
    return [(padded[i] << 8) | padded[i + 1] for i in range(0, len(padded), 2)]


def build_ip_header_checksum_demo() -> None:
    """Emit the worked numeric example printed in the lesson Build-It step."""
    print("== Worked example: 20-byte IPv4 header ==")
    # A fictitious IPv4 header (checksum field set to 0 while computing).
    header = bytes([
        0x45, 0x00, 0x00, 0x14,
        0x00, 0x01, 0x00, 0x00,
        0x40, 0x06, 0x00, 0x00,  # checksum field == 0 during computation
        0x7f, 0x00, 0x00, 0x01,
        0x7f, 0x00, 0x00, 0x02,
    ])
    words = to_16bit_words(header)
    print("  16-bit words:", " ".join(f"{w:04x}" for w in words))
    total, folded = folded_ones_complement_sum(header)
    print(f"  raw 32-bit accumulator: 0x{total:08x}")
    print(f"  sum (folded)         : 0x{folded:04x}")
    cksum = internet_checksum(header)
    print(f"  checksum (~folded)   : 0x{cksum:04x}")
    wire = header[:10] + bytes([cksum >> 8, cksum & 0xFF]) + header[12:]
    print(f"  wire header          : {wire.hex()}")
    print(f"  verify (sum=0xFFFF)  : {verify_checksum(wire)}")


def build_error_detection_demo() -> None:
    """Show which corruptions survive (undetected) and which are caught."""
    print("\n== Failure modes of a simple sum ==")
    payload = b"\x00\x01\x00\x02\x00\x03"
    cksum = internet_checksum(payload)
    good = payload + bytes([cksum >> 8, cksum & 0xFF])
    print(f"  payload  ={payload.hex()} checksum=0x{cksum:04x}")
    print(f"  good packet verifies : {verify_checksum(good)}")

    # undetected: insert a 0x0000 word -- adding zero does not change the sum
    inserted = good[:4] + b"\x00\x00" + good[4:]
    print(f"  +0x0000 inserted     : {inserted.hex()}")
    print(f"     still verifies?   : {verify_checksum(_byte_align(inserted))}  (insertion undetected!)")

    # undetected: swap two adjacent 16-bit words -- sum is order-independent
    swapped = good[2:4] + good[0:2] + good[4:]
    print(f"  swap first two words : {swapped.hex()}")
    print(f"     still verifies?   : {verify_checksum(_byte_align(swapped))}  (reorder undetected!)")

    # detected: flip one data bit (bit 7, i.e. the LSB of byte 0)
    corrupted = flip_bits(good, [7])
    print(f"  one data bit flipped : {corrupted.hex()}")
    print(f"     still verifies?   : {verify_checksum(_byte_align(corrupted))}  (detected)")


def main() -> None:
    print("16-bit Internet checksum -- one's complement arithmetic demo\n")
    build_ip_header_checksum_demo()
    build_error_detection_demo()
    print("\nDone.")


if __name__ == "__main__":
    main()