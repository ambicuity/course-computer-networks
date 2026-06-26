"""Hamming codes and forward error correction (FEC).

A stdlib-only demo of the (11, 7) Hamming code from Hamming (1950):
encode 7 data bits into an 11-bit codeword, transmit across a noisy
channel that may flip a single bit, then decode by computing the
error syndrome whose integer value IS the 1-based index of the
flipped bit. Extended with an overall parity bit to build a distance-4
SEC-DED (single-error-correction, double-error-detection) code, the
scheme used in ECC DRAM.

Run:  python3 main.py
"""

from __future__ import annotations

from typing import List, Sequence, Tuple


# ---------------------------------------------------------------------------
# Core algebra
# ---------------------------------------------------------------------------

def is_power_of_two(k: int) -> bool:
    """True iff k >= 1 is a power of two (1, 2, 4, 8, ...)."""
    return k >= 1 and (k & (k - 1)) == 0


def xor_bits(bits: Sequence[int]) -> int:
    """XOR a sequence of 0/1 bits together (even parity)."""
    acc = 0
    for b in bits:
        acc ^= b & 1
    return acc


def min_check_bits(m: int) -> int:
    """Smallest r satisfying the Hamming bound  2^r >= m + r + 1.

    That is the lower limit on check bits to correct every single-bit
    error in a block of m data bits; the resulting code is (m+r, m).
    """
    if m <= 0:
        raise ValueError("m must be positive")
    r = 0
    while (1 << r) < (m + r + 1):
        r += 1
    return r


# ---------------------------------------------------------------------------
# (11, 7) Hamming code: encode / decode
# ---------------------------------------------------------------------------

def hamming_layout(m: int) -> Tuple[List[int], List[int]]:
    """Return (check_positions, data_positions) for a Hamming code
    over m data bits, using the minimal r from min_check_bits.

    Positions are 1-based: powers of two are check bits, the rest
    hold data bits.
    """
    r = min_check_bits(m)
    n = m + r
    checks = [p for p in range(1, n + 1) if is_power_of_two(p)]
    data = [p for p in range(1, n + 1) if not is_power_of_two(p)]
    return checks, data


def cover_set(check_pos: int, n: int) -> List[int]:
    """Positions covered by the check bit at 1-based position
    `check_pos` (a power of two): every position whose binary
    decomposition includes check_pos.
    """
    return [j for j in range(1, n + 1) if (j & check_pos)]


def encode_hamming(data: Sequence[int]) -> List[int]:
    """Encode m data bits into an (m+r) Hamming codeword (even parity)."""
    m = len(data)
    checks, data_pos = hamming_layout(m)
    r = len(checks)
    n = m + r
    if len(data_pos) != m:
        raise ValueError("data length does not match layout")

    # Place data bits at non-check positions; check bits start at 0.
    codeword = [0] * n
    for dp, bit in zip(data_pos, data):
        codeword[dp - 1] = bit & 1

    # Each check bit is the XOR of all covered bits (check included,
    # but it is still 0 at this point so it contributes nothing).
    for cp in checks:
        covers = cover_set(cp, n)
        codeword[cp - 1] = xor_bits(codeword[j - 1] for j in covers)
    return codeword


def syndrome(codeword: Sequence[int], m: int) -> int:
    """Compute the Hamming syndrome of a received codeword.

    The syndrome is a binary number with one bit per check position
    (p1 is the least-significant bit). For a single-bit error the
    syndrome equals the 1-based index of the flipped bit; 0 means
    no error.
    """
    checks, _ = hamming_layout(m)
    r = len(checks)
    n = m + r
    if len(codeword) != n:
        raise ValueError(f"expected {n}-bit codeword, got {len(codeword)}")

    syn = 0
    for cp in checks:
        covers = cover_set(cp, n)
        if xor_bits(codeword[j - 1] for j in covers):  # check failed
            syn |= cp
    return syn


def strip_checks(codeword: Sequence[int], m: int) -> List[int]:
    """Return just the data bits from a codeword."""
    _, data_pos = hamming_layout(m)
    return [codeword[j - 1] for j in data_pos]


def decode_hamming(codeword: Sequence[int], m: int) -> Tuple[List[int], int]:
    """Decode and correct a single error. Returns (data, syndrome)."""
    cw = list(codeword)
    syn = syndrome(cw, m)
    if syn != 0 and syn <= len(cw):
        cw[syn - 1] ^= 1  # flip the offending bit
    return strip_checks(cw, m), syn


# ---------------------------------------------------------------------------
# SEC-DED: Hamming + one overall parity bit -> distance 4
# ---------------------------------------------------------------------------

def encode_secded(data: Sequence[int]) -> List[int]:
    """Encode data as a Hamming codeword plus an overall even-parity bit."""
    cw = encode_hamming(data)
    return cw + [xor_bits(cw)]


def decode_secded(word: Sequence[int], m: int) -> Tuple[List[int], int, str]:
    """Decode a SEC-DED word. Returns (data, syndrome, tag).

    tag is one of:
      OK            - no error detected
      CORRECTED     - single error corrected (syndrome names the bit)
      DOUBLE_ERROR  - two errors detected, data NOT trusted
    """
    n = m + min_check_bits(m)
    if len(word) != n + 1:
        raise ValueError(f"expected {n+1}-bit SEC-DED word, got {len(word)}")
    cw, overall = word[:n], word[n]
    syn = syndrome(cw, m)

    overall_ok = (xor_bits(cw) == overall)

    if syn == 0 and overall_ok:
        return strip_checks(cw, m), syn, "OK"
    if syn != 0 and not overall_ok:
        # odd overall-parity change => single error
        fixed, _ = decode_hamming(cw, m)
        return fixed, syn, "CORRECTED"
    if syn != 0 and overall_ok:
        # syndrome nonzero but overall parity even => double error
        return strip_checks(cw, m), syn, "DOUBLE_ERROR"
    # syn == 0 but overall parity mismatch => error in the parity bit
    return strip_checks(cw, m), syn, "OK"


# ---------------------------------------------------------------------------
# Channel helpers
# ---------------------------------------------------------------------------

def inject_error(codeword: Sequence[int], pos: int) -> List[int]:
    """Flip the 1-based position `pos` of a codeword."""
    if not 1 <= pos <= len(codeword):
        raise IndexError("pos out of range")
    out = list(codeword)
    out[pos - 1] ^= 1
    return out


def fmt(bits: Sequence[int]) -> str:
    return "".join(str(b & 1) for b in bits)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def main() -> None:
    print("=== Forward Error Correction: (11,7) Hamming code ===\n")

    # 1. Check-bit budget table for several message sizes.
    print("Check-bit budget (Hamming bound  2^r >= m + r + 1):")
    print(f"  {'m':>6} {'r':>4} {'n=m+r':>7} {'rate=m/n':>10}")
    for m in (7, 64, 1024, 4096):
        r = min_check_bits(m)
        n = m + r
        print(f"  {m:>6} {r:>4} {n:>7} {m / n:>10.4f}")
    print()

    # 2. Encode ASCII 'A' = 1000001 (7 data bits).
    data = [1, 0, 0, 0, 0, 0, 1]
    print(f"Message bits      : {fmt(data)}   (ASCII 'A')")
    cw = encode_hamming(data)
    checks, data_pos = hamming_layout(len(data))
    print(f"Check positions   : {checks}")
    print(f"Data positions    : {data_pos}")
    print(f"Codeword (11 bits): {fmt(cw)}")
    print("Layout (1-based)  : "
          + " ".join(f"p{p}" if is_power_of_two(p) else f"d{p}"
                     for p in range(1, len(cw) + 1)))
    print()

    # 3. Transmit, flip position 5, decode.
    corrupted = inject_error(cw, 5)
    print(f"Channel flips pos 5: {fmt(corrupted)}")
    rec_data, syn = decode_hamming(corrupted, len(data))
    print(f"Syndrome          : {syn}  (binary {syn:04b}) -> flip pos {syn}")
    print(f"Recovered data    : {fmt(rec_data)}")
    print(f"Matches original  : {rec_data == data}\n")

    # 4. SEC-DED: single error corrected, double error detected.
    print("=== SEC-DED (Hamming + overall parity) ===\n")
    sd = encode_secded(data)
    print(f"SEC-DED word      : {fmt(sd)}  (last bit = overall parity)")

    single = inject_error(sd, 9)
    rec, syn, tag = decode_secded(single, len(data))
    print(f"Single error @9   : {fmt(single)}")
    print(f"  syndrome={syn}  tag={tag}  data={fmt(rec)}  ok={rec == data}")

    # Inject TWO errors (positions 3 and 7) -> must be detected, not corrected.
    double = inject_error(inject_error(sd, 3), 7)
    rec, syn, tag = decode_secded(double, len(data))
    print(f"Double error @3,7 : {fmt(double)}")
    print(f"  syndrome={syn}  tag={tag}  data_trusted={rec == data}")

    # 5. Exhaustive single-error correction proof for (11,7).
    print("\n=== Exhaustive single-error test ===")
    ok = 0
    for pos in range(1, len(cw) + 1):
        bad = inject_error(cw, pos)
        rec, syn = decode_hamming(bad, len(data))
        if syn == pos and rec == data:
            ok += 1
    print(f"Corrected {ok}/{len(cw)} single-bit error positions "
          f"(every position self-heals).")


if __name__ == "__main__":
    main()
