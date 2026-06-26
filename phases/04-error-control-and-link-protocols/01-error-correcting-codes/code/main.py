"""Error-correcting codes: (11,7) Hamming encoder/decoder and Hamming-distance tools.

This module implements, with the bit numbering used by Tanenbaum Fig. 3-6, a
single-error-correcting (11,7) Hamming code:

    - Codeword bits are numbered 1..11 from the left.
    - Bit positions that are powers of two (1, 2, 4, 8) are CHECK bits.
    - The remaining positions (3, 5, 6, 7, 9, 10, 11) carry the 7 DATA bits.
    - Each check bit forces EVEN parity over the positions whose binary
      expansion includes that power of two (e.g. bit 11 = 1+2+8 is covered by
      check bits 1, 2 and 8).

On the receive side we recompute the four parity sums. The four results, read
as a binary number (p8 p4 p2 p1), form the SYNDROME. A non-zero syndrome names
exactly the position that flipped, so we invert it and recover the message.
This construction has Hamming distance 3: it corrects any single-bit error or
detects (without correcting) any double-bit error.

The module also includes Hamming-distance utilities used in section 3.2.1 to
reason about how many errors a code can detect (d-1) or correct (floor((d-1)/2)).

Pure standard library. No network calls. Run: python3 main.py
"""

from __future__ import annotations

from typing import Iterable

# Positions (1-indexed) that hold check bits in an 11-bit codeword.
CHECK_POSITIONS: tuple[int, ...] = (1, 2, 4, 8)
# Positions (1-indexed) that hold the 7 data bits, in order.
DATA_POSITIONS: tuple[int, ...] = (3, 5, 6, 7, 9, 10, 11)
CODEWORD_LEN: int = 11
DATA_LEN: int = 7


def _covers(check_pos: int, target_pos: int) -> bool:
    """True if `check_pos` (a power of two) appears in the binary expansion of `target_pos`."""
    return (target_pos & check_pos) != 0


def encode_hamming_11_7(data_bits: list[int]) -> list[int]:
    """Encode 7 data bits into an 11-bit even-parity Hamming codeword.

    Returns a list of 11 ints (each 0 or 1), indexed 0..10 for codeword
    positions 1..11.
    """
    if len(data_bits) != DATA_LEN or any(b not in (0, 1) for b in data_bits):
        raise ValueError(f"expected {DATA_LEN} bits each 0 or 1, got {data_bits!r}")

    codeword = [0] * CODEWORD_LEN
    # Drop the data bits into their non-power-of-two slots.
    for bit, pos in zip(data_bits, DATA_POSITIONS):
        codeword[pos - 1] = bit

    # Each check bit = XOR of the data bits it covers (forces even parity).
    for check in CHECK_POSITIONS:
        parity = 0
        for pos in range(1, CODEWORD_LEN + 1):
            if pos != check and _covers(check, pos):
                parity ^= codeword[pos - 1]
        codeword[check - 1] = parity
    return codeword


def syndrome(codeword: list[int]) -> int:
    """Recompute parity over every check bit and return the syndrome integer.

    A syndrome of 0 means all parity sums are even (no detected error). A
    non-zero value equals the 1-indexed position the decoder believes flipped.
    """
    if len(codeword) != CODEWORD_LEN:
        raise ValueError(f"codeword must be {CODEWORD_LEN} bits, got {len(codeword)}")

    result = 0
    for check in CHECK_POSITIONS:
        parity = 0
        for pos in range(1, CODEWORD_LEN + 1):
            if _covers(check, pos):
                parity ^= codeword[pos - 1]
        if parity != 0:  # this check failed -> add its weight to the syndrome
            result += check
    return result


def decode_hamming_11_7(received: list[int]) -> tuple[list[int], int]:
    """Correct at most one bit error and return (7 data bits, syndrome).

    The returned syndrome is the position that was corrected (0 = clean).
    """
    s = syndrome(received)
    corrected = list(received)
    if s != 0:
        corrected[s - 1] ^= 1  # flip the offending bit
    data = [corrected[pos - 1] for pos in DATA_POSITIONS]
    return data, s


def hamming_distance(a: Iterable[int], b: Iterable[int]) -> int:
    """Number of bit positions in which two equal-length bit vectors differ."""
    a_list, b_list = list(a), list(b)
    if len(a_list) != len(b_list):
        raise ValueError("vectors must be equal length")
    return sum(1 for x, y in zip(a_list, b_list) if x != y)


def min_distance(codewords: list[list[int]]) -> int:
    """Minimum Hamming distance over all pairs -> the distance of the code."""
    best: int | None = None
    for i in range(len(codewords)):
        for j in range(i + 1, len(codewords)):
            d = hamming_distance(codewords[i], codewords[j])
            best = d if best is None else min(best, d)
    if best is None:
        raise ValueError("need at least two codewords")
    return best


def char_to_bits(ch: str) -> list[int]:
    """Return the 7 data bits (MSB-first) of a 7-bit ASCII character."""
    value = ord(ch)
    if value > 0x7F:
        raise ValueError("only 7-bit ASCII is supported")
    return [(value >> (6 - i)) & 1 for i in range(DATA_LEN)]


def bits_to_char(bits: list[int]) -> str:
    value = 0
    for b in bits:
        value = (value << 1) | b
    return chr(value)


def _fmt(bits: list[int]) -> str:
    return "".join(str(b) for b in bits)


def main() -> None:
    print("=" * 64)
    print("(11,7) HAMMING CODE  -  single-error correction (Tanenbaum 3.2.1)")
    print("=" * 64)

    # --- Encode the ASCII letter 'A' (1000001), as in Fig. 3-6. ---------------
    message = "A"
    data = char_to_bits(message)
    codeword = encode_hamming_11_7(data)
    print(f"\nMessage char          : {message!r}  (ASCII {ord(message)})")
    print(f"7 data bits           : {_fmt(data)}")
    print(f"11-bit codeword sent  : {_fmt(codeword)}  (positions 1..11)")
    print("Check bits p1 p2 p4 p8:",
          codeword[0], codeword[1], codeword[3], codeword[7])

    # --- Inject a single-bit error on the channel (flip position 5). ----------
    flip_pos = 5
    received = list(codeword)
    received[flip_pos - 1] ^= 1
    print(f"\nChannel flips bit     : position {flip_pos}")
    print(f"Received codeword     : {_fmt(received)}")

    recovered, s = decode_hamming_11_7(received)
    print(f"Syndrome (p8p4p2p1)   : {s}  -> bit {s} corrected")
    print(f"Recovered data bits   : {_fmt(recovered)}")
    print(f"Recovered char        : {bits_to_char(recovered)!r}  "
          f"({'OK' if bits_to_char(recovered) == message else 'MISMATCH'})")

    # --- Show every single-bit error is uniquely correctable. -----------------
    print("\nSyndrome for a flip at each position (distance-3 guarantee):")
    for pos in range(1, CODEWORD_LEN + 1):
        trial = list(codeword)
        trial[pos - 1] ^= 1
        print(f"  flip pos {pos:>2}  ->  syndrome {syndrome(trial):>2}")

    # --- Double-bit error: detected but mis-corrected (distance-3 limit). -----
    double = list(codeword)
    double[2] ^= 1
    double[6] ^= 1
    d_data, d_s = decode_hamming_11_7(double)
    print(f"\nDouble error at pos 3 & 7 -> syndrome {d_s} (non-zero = detected),")
    print(f"  but 'correction' yields {bits_to_char(d_data)!r}: "
          "distance 3 cannot correct two errors.")

    # --- Distance reasoning from 3.2.1: the four-codeword example. ------------
    print("\nThe four-codeword distance-5 example from section 3.2.1:")
    book_codewords = [
        [int(c) for c in "0000000000"],
        [int(c) for c in "0000011111"],
        [int(c) for c in "1111100000"],
        [int(c) for c in "1111111111"],
    ]
    d = min_distance(book_codewords)
    print(f"  minimum Hamming distance = {d}")
    print(f"  detects up to {d - 1} errors (d-1), "
          f"corrects up to {(d - 1) // 2} (floor((d-1)/2))")

    print("\nDone.")


if __name__ == "__main__":
    main()
