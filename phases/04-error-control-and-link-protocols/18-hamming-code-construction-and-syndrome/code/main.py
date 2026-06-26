"""(11,7) Hamming code: encoder, single-error channel, syndrome decoder.

A self-contained, stdlib-only implementation of the worked example from
Tanenbaum & Wetherall, *Computer Networks* 6th ed., section 3.2.1 (Fig. 3-6).

Layout (1-based positions, left to right):

    Position:  1   2   3   4   5   6   7   8   9  10  11
    Content:  p1  p2  m1  p4  m2  m3  m4  p8  m5  m6  m7

Check bit pX covers every position k whose binary expansion contains the
power of two X. Equivalently, position k is checked by the check bits
corresponding to the 1-bits of k.

Run:  python3 main.py
"""

from __future__ import annotations

from functools import reduce

# --- Code parameters --------------------------------------------------------

M = 7                      # message bits
R = 4                      # check bits (p1, p2, p4, p8)
N = M + R                  # codeword length = 11
CHECK_POWERS = [1, 2, 4, 8]            # positions occupied by check bits
DATA_POSITIONS = [3, 5, 6, 7, 9, 10, 11]  # positions occupied by message bits


# --- Core construction ------------------------------------------------------

def covered_positions(check_power: int) -> list[int]:
    """Positions covered by the check bit sitting at ``check_power``.

    A position k is covered iff (k & check_power) != 0. This includes the
    check position itself, which is what makes even-parity self-consistent.
    """
    return [k for k in range(1, N + 1) if k & check_power]


def _xor(bits: list[int]) -> int:
    """Reduce a list of bits with XOR (modulo-2 sum)."""
    return reduce(lambda a, b: a ^ b, bits, 0)


def encode(message: list[int]) -> list[int]:
    """Encode 7 message bits into an 11-bit Hamming codeword.

    ``message`` is m1..m7 in order. Returns a list indexed 0..10 corresponding
    to codeword positions 1..11.
    """
    if len(message) != M:
        raise ValueError(f"message must be {M} bits, got {len(message)}")

    # 1-based view: codeword[pos] for pos in 1..11. Position 0 unused.
    codeword: list[int] = [0] * (N + 1)

    # Place the message bits at the non-power-of-two positions.
    for bit, pos in zip(message, DATA_POSITIONS):
        codeword[pos] = bit

    # Compute each check bit as the XOR of the *data* positions it covers
    # (excluding itself, which is initially 0, so the result sets even parity
    # over the full coverage set including itself).
    for cp in CHECK_POWERS:
        covered = covered_positions(cp)
        data_only = [codeword[p] for p in covered if p != cp]
        codeword[cp] = _xor(data_only)

    return codeword[1:]  # drop the unused index-0 slot


def syndrome(received: list[int]) -> int:
    """Compute the 4-bit syndrome of an 11-bit received word.

    Recomputes every parity check over the *entire* received word (check bits
    included) and packs the results with p8 as the most significant bit.
    A syndrome of 0 means no detectable error; otherwise the binary value is
    the 1-based index of the single flipped bit.
    """
    if len(received) != N:
        raise ValueError(f"received word must be {N} bits, got {len(received)}")

    # 1-based view for parity recomputation.
    word = [0] + list(received)

    # Each check result is the XOR of all bits in its coverage set.
    # Convention: MSB = check8, then check4, check2, LSB = check1.
    checks = {cp: _xor([word[k] for k in covered_positions(cp)])
              for cp in CHECK_POWERS}
    return (checks[8] << 3) | (checks[4] << 2) | (checks[2] << 1) | checks[1]


def decode(received: list[int]) -> tuple[list[int], int]:
    """Decode an 11-bit received word into (message_bits, corrected_position).

    ``corrected_position`` is the 1-based index that was flipped, or 0 if the
    word was clean. Returns the 7 recovered message bits.
    """
    s = syndrome(received)
    word = [0] + list(received)

    corrected_position = 0
    if s != 0:
        if s <= N:
            # Single-bit error: flip the indicated position.
            word[s] ^= 1
            corrected_position = s
        else:
            # Syndrome points past the codeword length: uncorrectable
            # multi-bit error in a plain (11,7) code.
            raise ValueError(
                f"syndrome {s:04b} = {s} exceeds codeword length {N}: "
                "uncorrectable multi-bit error (distance-3 code)"
            )

    message = [word[p] for p in DATA_POSITIONS]
    return message, corrected_position


# --- Channel helpers --------------------------------------------------------

def inject_error(codeword: list[int], position: int) -> list[int]:
    """Return a copy of ``codeword`` with the bit at 1-based ``position`` flipped."""
    if not 1 <= position <= N:
        raise ValueError(f"position must be 1..{N}, got {position}")
    corrupted = list(codeword)
    corrupted[position - 1] ^= 1
    return corrupted


# --- Demo -------------------------------------------------------------------

def _bits_to_str(bits: list[int]) -> str:
    return "".join(str(b) for b in bits)


def main() -> None:
    print("(11,7) Hamming code — encode, corrupt, syndrome-decode")
    print("=" * 64)

    # ASCII 'A' = 0x41 = 1000001 (7 bits, m1..m7).
    message = [1, 0, 0, 0, 0, 0, 1]
    print(f"Message (m1..m7): {_bits_to_str(message)}  (ASCII '{chr(0b1000001)}')")

    codeword = encode(message)
    print(f"Codeword  (1..11): {_bits_to_str(codeword)}")
    print(f"  check bits at 1,2,4,8 = "
          f"{codeword[0]}{codeword[1]}{codeword[3]}{codeword[7]}")

    # Fig. 3-6: inject a single error in position 5.
    error_pos = 5
    received = inject_error(codeword, error_pos)
    print(f"\nInjected 1-bit error at position {error_pos}")
    print(f"Received  (1..11): {_bits_to_str(received)}")

    s = syndrome(received)
    print(f"Syndrome  (p8p4p2p1): {s:04b} = {s}")

    recovered, corrected = decode(received)
    print(f"Decoder flipped position: {corrected}")
    print(f"Recovered message: {_bits_to_str(recovered)}  "
          f"(ASCII '{chr(int(_bits_to_str(recovered), 2))}')")
    assert recovered == message, "recovery failed!"
    print("=> Single-bit error corrected cleanly.")

    # Monte-Carlo: every single-bit error must decode back to the original.
    print("\n" + "-" * 64)
    print("Sweep: inject one error at each position 1..11")
    print(f"{'pos':>4}  {'syndrome':>8}  {'corrected':>9}  {'ok':>4}")
    all_ok = True
    for pos in range(1, N + 1):
        rx = inject_error(codeword, pos)
        sv = syndrome(rx)
        rec, corr = decode(rx)
        ok = rec == message and corr == pos
        all_ok &= ok
        print(f"{pos:>4}  {sv:>08b}  {corr:>9}  {'yes' if ok else 'NO':>4}")
    print(f"\nAll 11 single-bit errors corrected: {all_ok}")

    # Clean codeword: syndrome must be zero.
    print("\n" + "-" * 64)
    s_clean = syndrome(codeword)
    print(f"Syndrome of the clean codeword: {s_clean:04b} (0 = no error)")
    rec_clean, corr_clean = decode(codeword)
    print(f"Recovered without correction: {_bits_to_str(rec_clean)}")

    # Demonstrate the uncorrectable case: two errors.
    print("\n" + "-" * 64)
    print("Double-bit error (positions 3 and 5) — distance-3 code:")
    double = inject_error(inject_error(codeword, 3), 5)
    s2 = syndrome(double)
    print(f"  received     : {_bits_to_str(double)}")
    print(f"  syndrome     : {s2:04b} = {s2}")
    try:
        rec2, corr2 = decode(double)
        print(f"  decoder says : flip position {corr2}  "
              f"(WRONG — a 2-bit error masquerades as a 1-bit error elsewhere)")
        print(f"  recovered    : {_bits_to_str(rec2)}  "
              f"(corrupted: expected {_bits_to_str(message)})")
    except ValueError as exc:
        print(f"  decoder says : {exc}")
    print("  => A distance-3 code cannot correct 2 errors; this is why "
          "ECC DRAM adds an overall parity bit for SEC-DED.")


if __name__ == "__main__":
    main()
