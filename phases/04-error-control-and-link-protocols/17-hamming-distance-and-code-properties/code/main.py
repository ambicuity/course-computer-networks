"""Hamming distance, code properties, and the (11,7) Hamming code.

A stdlib-only demo of the error-detection/correction tradeoff covered in the
lesson. It builds a real (11,7) Hamming code (4 parity bits, 7 data bits),
computes the Hamming distance of small codebooks, demonstrates the
"detect d / correct d" tradeoff, and shows the syndrome decoder pin-pointing
and flipping a single-bit error. Run with: python3 main.py
"""

from typing import List, Tuple

Bit = int
Codeword = Tuple[Bit, ...]


def hamming_distance(a: Codeword, b: Codeword) -> int:
    """Number of bit positions in which two equal-length codewords differ."""
    if len(a) != len(b):
        raise ValueError("codewords must be the same length")
    return sum(x ^ y for x, y in zip(a, b))


def code_min_distance(codebook: List[Codeword]) -> int:
    """Minimum Hamming distance across all distinct codeword pairs."""
    if len(codebook) < 2:
        return 0
    best = len(codebook[0])
    for i in range(len(codebook)):
        for j in range(i + 1, len(codebook)):
            best = min(best, hamming_distance(codebook[i], codebook[j]))
    return best


def detect_correct(d_min: int) -> Tuple[int, int]:
    """Given a code's minimum distance, return (max detect, max correct).

    To detect d errors you need d_min >= d + 1; to correct d errors you need
    d_min >= 2d + 1. Correcting d errors and detecting 2d errors are mutually
    exclusive interpretations of the same received word.
    """
    max_detect = d_min - 1
    max_correct = (d_min - 1) // 2
    return max_detect, max_correct


# ---------------------------------------------------------------------------
# (11,7) Hamming code: positions 1..11, parity bits at powers of two (1,2,4,8)
# ---------------------------------------------------------------------------

PARITY_POSITIONS = (1, 2, 4, 8)


def covers(position: int) -> List[int]:
    """Parity-bit positions that cover a given codeword position (1-indexed)."""
    return [p for p in PARITY_POSITIONS if position & p]


def hamming_encode(data: List[Bit]) -> List[Bit]:
    """Encode 7 data bits into an 11-bit Hamming codeword (even parity).

    Positions 3,5,6,7,9,10,11 hold the 7 data bits; positions 1,2,4,8 are parity.
    """
    if len(data) != 7:
        raise ValueError("expected exactly 7 data bits")
    codeword = [0] * 11  # index 0..10 maps to bit position 1..11
    data_iter = iter(data)
    for pos in range(1, 12):
        if pos not in PARITY_POSITIONS:
            codeword[pos - 1] = next(data_iter)
    for p in PARITY_POSITIONS:
        parity = 0
        for pos in range(1, 12):
            if pos == p:
                continue
            if pos & p:
                parity ^= codeword[pos - 1]
        codeword[p - 1] = parity
    return codeword


def hamming_syndrome(received: List[Bit]) -> int:
    """Compute the (11,7) Hamming syndrome: 0 = no error, else the bad position."""
    syndrome = 0
    for p in PARITY_POSITIONS:
        parity = 0
        for pos in range(1, 12):
            if pos & p:
                parity ^= received[pos - 1]
        if parity:
            syndrome += p
    return syndrome


def hamming_decode(received: List[Bit]) -> Tuple[List[Bit], int]:
    """Decode an 11-bit word: correct a single error, return (data, syndrome)."""
    syndrome = hamming_syndrome(received)
    corrected = list(received)
    if syndrome != 0 and syndrome <= 11:
        corrected[syndrome - 1] ^= 1  # flip the offending bit
    data = [corrected[pos - 1] for pos in range(1, 12) if pos not in PARITY_POSITIONS]
    return data, syndrome


def to_bits(text: str) -> List[Bit]:
    """7-bit ASCII bits, MSB first, of each character."""
    bits: List[Bit] = []
    for ch in text:
        for shift in range(6, -1, -1):
            bits.append((ord(ch) >> shift) & 1)
    return bits


def to_text(bits: List[Bit]) -> str:
    out = []
    for i in range(0, len(bits), 7):
        val = 0
        for b in bits[i:i + 7]:
            val = (val << 1) | b
        out.append(chr(val))
    return "".join(out)


def inject_error(codeword: List[Bit], position: int) -> List[Bit]:
    """Return a copy of codeword with the 1-indexed position flipped."""
    noisy = list(codeword)
    noisy[position - 1] ^= 1
    return noisy


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_distance_and_tradeoff() -> None:
    print("=== Hamming distance and the detect/correct tradeoff ===")
    codebook = [
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),
        (0, 0, 0, 0, 0, 1, 1, 1, 1, 1),
        (1, 1, 1, 1, 1, 0, 0, 0, 0, 0),
        (1, 1, 1, 1, 1, 1, 1, 1, 1, 1),
    ]
    d_min = code_min_distance(codebook)
    print("Codewords:")
    for c in codebook:
        print("  ", "".join(map(str, c)))
    print(f"Minimum Hamming distance d_min = {d_min}")
    det, corr = detect_correct(d_min)
    print(f"  can detect up to {det} errors, OR correct up to {corr} errors")
    print("  (correcting 2 and detecting 4 simultaneously is impossible)")
    print()


def demo_hamming_code() -> None:
    print("=== (11,7) Hamming code ===")
    message = "A"  # ASCII 0b1000001
    data = to_bits(message)
    print(f"Message '{message}' -> 7 data bits: {data}")
    cw = hamming_encode(data)
    print("Encoded 11-bit codeword (p1 p2 d3 p4 d5 d6 d7 p8 d9 d10 d11):")
    print(f"  {''.join(map(str, cw))}")
    print(f"  parity bits at positions {PARITY_POSITIONS}: "
          f"{[cw[p-1] for p in PARITY_POSITIONS]}")

    data0, syn0 = hamming_decode(cw)
    print(f"\nNo error:  syndrome={syn0} -> decoded '{to_text(data0)}'")

    noisy = inject_error(cw, 5)
    print(f"\nInject 1-bit error at position 5: {''.join(map(str, noisy))}")
    data1, syn1 = hamming_decode(noisy)
    print(f"  syndrome={syn1} (binary {syn1:04b}) -> flip position {syn1}")
    print(f"  decoded '{to_text(data1)}'  (recovered: {data1 == data})")

    noisy2 = inject_error(cw, 4)
    data2, syn2 = hamming_decode(noisy2)
    print(f"\nInject 1-bit error at position 4 (parity): syndrome={syn2} -> "
          f"decoded '{to_text(data2)}'  (recovered: {data2 == data})")

    # Two-bit error: syndrome is nonzero and points at a THIRD position, so the
    # single-error decoder miscorrects. This is exactly why distance-3 codes
    # detect 2 but cannot correct 2.
    noisy3 = inject_error(inject_error(cw, 3), 7)
    data3, syn3 = hamming_decode(noisy3)
    print(f"\nInject 2-bit error at positions 3 and 7: syndrome={syn3}")
    print(f"  decoder 'corrects' position {syn3} -> data {data3} "
          f"(recovered: {data3 == data})  <- miscorrection!")


def demo_min_check_bits() -> None:
    print("\n=== Hamming bound: check bits for single-error correction ===")
    print("  (m + r + 1) <= 2^r")
    for m in (1, 4, 7, 8, 16, 32, 64):
        r = 0
        while (m + r + 1) > (1 << r):
            r += 1
        rate = m / (m + r)
        print(f"  m={m:>3} data bits -> need r={r} check bits, "
              f"n={m+r}, code rate={rate:.3f}")


def main() -> None:
    demo_distance_and_tradeoff()
    demo_hamming_code()
    demo_min_check_bits()


if __name__ == "__main__":
    main()
