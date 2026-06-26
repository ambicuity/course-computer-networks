"""Row parity and interleaving to detect burst errors.

This module models the two parity schemes the textbook describes in
Sec. 3.2.2 ("Error-Detecting Codes"):

  * row parity           -- a parity bit per row of a k x n matrix
  * interleaved column parity -- a parity bit per column, with the
    matrix transmitted row-by-row and the n parity bits sent last

It also implements a textbook-style 32-bit CRC (the IEEE 802.3
generator) to give a concrete contrast: a CRC detects *any* burst of
length <= r where r is the degree of the generator, with a hard
residual probability of 2^(-r) for longer bursts.

Run with ``python3 main.py`` (stdlib only, no network calls).
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Block geometry, as in Tanenbaum & Wetherall Figure 3-8.
# ---------------------------------------------------------------------------
DATA: bytes = b"Network"          # 7 ASCII characters -> a 7 x 7 matrix
N_COLS: int = len(DATA)            # width of the matrix (columns / parity bits)
N_ROWS: int = len(DATA)            # height of the matrix (rows of data bits)

# IEEE 802.3 32-bit CRC polynomial (normal form), x^32 + ... + 1.
CRC32_POLY: int = 0x04C11DB7


# ---------------------------------------------------------------------------
# Bit helpers.
# ---------------------------------------------------------------------------
def char_bits(ch: str) -> list[int]:
    """Return the 8 bits of an ASCII character, MSB first."""
    return [(ord(ch) >> (7 - i)) & 1 for i in range(8)]


def parity(bitlist: list[int]) -> int:
    """Even parity: XOR of all the bits. 1 if an odd number of 1s."""
    p = 0
    for b in bitlist:
        p ^= b
    return p


# ---------------------------------------------------------------------------
# Matrix construction.
# ---------------------------------------------------------------------------
def build_matrix(data: bytes, n_cols: int) -> list[list[int]]:
    """Pack the data into a k x n matrix using the low n bits of each char.

    The textbook uses 7-bit ASCII laid out across 7 columns, so we take
    the low 7 bits of each byte.  For wider matrices we just use the low
    n_cols bits, which keeps the geometry clean and the demo small.
    """
    matrix: list[list[int]] = []
    for ch in data:
        row = char_bits(chr(ch))[1:1 + n_cols]  # drop the MSB for 7-bit ASCII
        matrix.append(row)
    return matrix


# ---------------------------------------------------------------------------
# Two encoders: row parity and interleaved column parity.
# ---------------------------------------------------------------------------
@dataclass
class Codeword:
    transmitted: list[int]            # bits as placed on the wire
    row_parity: list[int]             # k parity bits (one per row)
    col_parity: list[int]             # n parity bits (one per column)
    n_cols: int
    n_rows: int


def encode(matrix: list[list[int]]) -> Codeword:
    """Compute both row parity and column parity for the same matrix."""
    n_rows = len(matrix)
    n_cols = len(matrix[0]) if n_rows else 0

    row_parity = [parity(row) for row in matrix]
    # Column parity walks each column top-to-bottom.
    col_parity = [parity([matrix[r][c] for r in range(n_rows)])
                  for c in range(n_cols)]

    # Transmission order, as in Fig. 3-8: each data row, MSB-to-LSB,
    # rows top to bottom, then the n column parity bits sent last.
    transmitted: list[int] = []
    for row in matrix:
        transmitted.extend(row)
    transmitted.extend(col_parity)

    return Codeword(transmitted, row_parity, col_parity, n_cols, n_rows)


# ---------------------------------------------------------------------------
# Burst injection.
# ---------------------------------------------------------------------------
def inject_burst(cw: Codeword, start: int, length: int,
                  pattern: list[int] | None = None) -> list[int]:
    """Return a received codeword with a burst applied from ``start``.

    ``pattern`` is a list of length ``length`` of 0/1; bit i in the burst
    is XORed with pattern[i].  If pattern is None the "interior" bits are
    left alone and only the first and last bits flip -- this is exactly
    the pathological n+1 burst the textbook warns about.
    """
    received = list(cw.transmitted)
    end = min(start + length, len(received))
    if pattern is None:
        pattern = [0] * (end - start)
        if len(pattern) >= 2:
            pattern[0] = 1
            pattern[-1] = 1
    for offset, flip in enumerate(pattern):
        if start + offset >= len(received):
            break
        received[start + offset] ^= flip
    return received


# ---------------------------------------------------------------------------
# Decoding / checking.
# ---------------------------------------------------------------------------
def decode_row_parity(received: list[int], cw: Codeword) -> list[int]:
    """Recompute row parity on the received data rows; 1 => error."""
    errs: list[int] = []
    idx = 0
    for r in range(cw.n_rows):
        row = received[idx:idx + cw.n_cols]
        idx += cw.n_cols
        errs.append(parity(row) ^ cw.row_parity[r])
    return errs


def decode_col_parity(received: list[int], cw: Codeword) -> list[int]:
    """Recompute column parity; 1 => error in that column."""
    data = received[:cw.n_rows * cw.n_cols]
    rx_col_parity = received[cw.n_rows * cw.n_cols:]
    errs: list[int] = []
    for c in range(cw.n_cols):
        column = [data[r * cw.n_cols + c] for r in range(cw.n_rows)]
        errs.append(parity(column) ^ rx_col_parity[c])
    return errs


# ---------------------------------------------------------------------------
# CRC-32 (textbook bit-by-bit polynomial division) for contrast.
# ---------------------------------------------------------------------------
def crc32(bits: list[int]) -> int:
    """Textbook 32-bit CRC using the IEEE 802.3 generator, bit by bit."""
    remainder = 0xFFFFFFFF
    for bit in bits:
        top = (remainder >> 31) & 1
        remainder = ((remainder << 1) | bit) & 0xFFFFFFFF
        if top:
            remainder ^= CRC32_POLY
    return remainder


def crc32_detect(data: list[int], transmitted_crc: int) -> bool:
    """Return True if the burst inside ``data`` would be detected.

    Detection means the division of data||crc leaves a nonzero
    remainder; clean data divides to zero.  Returns True on mismatch.
    """
    appended = data + [(transmitted_crc >> (31 - i)) & 1 for i in range(32)]
    return crc32(appended) != 0


# ---------------------------------------------------------------------------
# Demo.
# ---------------------------------------------------------------------------
def _matrix_str(matrix: list[list[int]], tag: str = "") -> str:
    out = [f"  {tag}".rstrip()]
    for r, row in enumerate(matrix):
        out.append(f"    row {r}: " + " ".join(str(b) for b in row))
    return "\n".join(out)


def main() -> None:
    matrix = build_matrix(DATA, N_COLS)
    print(f"Building a {N_ROWS} x {N_COLS} matrix from: {DATA.decode()!r}")
    print(_matrix_str(matrix, "matrix:"))
    print()

    cw = encode(matrix)
    print("Row parity bits (even, per row): ", cw.row_parity)
    print("Col parity bits (even, per col): ", cw.col_parity)
    print(f"Transmitted codeword length: {len(cw.transmitted)} bits")
    print("  ", "".join(str(b) for b in cw.transmitted))
    print()

    # --- Burst 1: length 7 spread across all 7 columns (interleaving catches it).
    burst1_start = 0
    burst1_len = N_COLS
    pattern1 = [1, 0, 1, 0, 0, 0, 1]   # 4 flips spread across 7 columns
    rx1 = inject_burst(cw, burst1_start, burst1_len, pattern1)

    print(f"Burst 1: length {burst1_len} spread across {N_COLS} columns")
    print("  pattern:", pattern1)
    print("  received:", "".join(str(b) for b in rx1))
    row_err1 = decode_row_parity(rx1, cw)
    col_err1 = decode_col_parity(rx1, cw)
    print("  row parity errs:", row_err1, "-> detected?", any(row_err1))
    print("  col parity errs:", col_err1, "-> detected?", any(col_err1))
    print()

    # --- Burst 2: length n+1 with only endpoints flipped (the hole).
    burst2_start = 0
    burst2_len = N_COLS + 1
    rx2 = inject_burst(cw, burst2_start, burst2_len, pattern=None)
    print(f"Burst 2: length {burst2_len} (n+1), only endpoints flipped")
    print("  received:", "".join(str(b) for b in rx2))
    row_err2 = decode_row_parity(rx2, cw)
    col_err2 = decode_col_parity(rx2, cw)
    print("  row parity errs:", row_err2, "-> detected?", any(row_err2))
    print("  col parity errs:", col_err2, "-> detected?", any(col_err2))
    print("  *** interleaved parity MISSES this pathological n+1 burst ***")
    print()

    # --- CRC-32 catches both bursts regardless of pattern.
    data_bits = cw.transmitted[:-N_COLS]
    crc_val = crc32(data_bits)
    print(f"CRC-32 of the data bits: 0x{crc_val:08X}")
    print("  Burst 1 -> CRC detected?", crc32_detect(rx1[:-N_COLS], crc_val))
    print("  Burst 2 -> CRC detected?", crc32_detect(rx2[:-N_COLS], crc_val))
    print()

    # --- Empirical residual probability for long random bursts.
    import random
    random.seed(42)
    trials = 4096
    long_burst_len = N_COLS * 3          # well past n
    accepted = 0
    for _ in range(trials):
        start = random.randint(0, len(cw.transmitted) - long_burst_len)
        pattern = [random.randint(0, 1) for _ in range(long_burst_len)]
        # enforce the textbook definition: first and last must be flipped
        pattern[0] = 1
        pattern[-1] = 1
        rx = inject_burst(cw, start, long_burst_len, pattern)
        if not any(decode_col_parity(rx, cw)):
            accepted += 1
    empirical = accepted / trials
    expected = 2 ** (-N_COLS)
    print(f"Empirical escape (long bursts of length {long_burst_len}): "
          f"{accepted}/{trials} = {empirical:.4e}")
    print(f"Theoretical residual 2^(-n) for n={N_COLS}:  {expected:.4e}")
    print()

    # --- Wider matrix sweep: residual converges to 2^(-n).
    # To get enough rows for wider columns we generate synthetic random data
    # of k = n rows so the matrix stays square; the residual probability
    # depends only on n (the number of independent parity checks), not on k.
    print("Wider matrices: empirical vs 2^(-n)")
    random.seed(7)
    for n in (7, 16, 32):
        k = n
        wide_matrix = [[random.randint(0, 1) for _ in range(n)]
                       for _ in range(k)]
        wide_cw = encode(wide_matrix)
        accepted = 0
        random.seed(1)
        t = 8192
        bl = n * 2
        for _ in range(t):
            s = random.randint(0, len(wide_cw.transmitted) - bl)
            p = [random.randint(0, 1) for _ in range(bl)]
            p[0] = 1
            p[-1] = 1
            rx = inject_burst(wide_cw, s, bl, p)
            if not any(decode_col_parity(rx, wide_cw)):
                accepted += 1
        print(f"  n={n:2d}: empirical {accepted}/{t} = {accepted/t:.3e}"
              f"   vs 2^(-n) = {2**-n:.3e}")


if __name__ == "__main__":
    main()