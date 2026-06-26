"""
CRC Polynomial Arithmetic and Generator Standards
==================================================
Demonstrates CRC computation using modulo-2 polynomial long division.
Covers the textbook worked example (G(x)=x^4+x+1), CRC-16-CCITT,
IEEE 802.3 CRC-32, and Castagnoli CRC-32C. Shows error detection in action.

Run:
    python3 main.py
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Standard generator polynomials
# Stored as (full_polynomial_integer_with_leading_1, degree).
# Example: CRC-4 x^4+x+1 → binary 10011 → 0b10011, degree=4
# ---------------------------------------------------------------------------
GENERATORS: dict[str, tuple[int, int]] = {
    "CRC-4-textbook":        (0b10011,       4),   # x^4+x+1  (Tanenbaum Fig 3-9)
    "CRC-16-IBM":            (0x18005,       16),   # x^16+x^15+x^2+1 (BISYNC, USB)
    "CRC-16-CCITT":          (0x11021,       16),   # x^16+x^12+x^5+1 (HDLC, X.25, Bluetooth)
    "CRC-32-IEEE":           (0x104C11DB7,   32),   # IEEE 802.3 / Ethernet / ZIP  HD=4
    "CRC-32C-Castagnoli":    (0x11EDC6F41,   32),   # iSCSI, SCTP, Btrfs           HD=6
}


def int_to_bits(value: int, width: int) -> list[int]:
    """Return `width` bits MSB-first from integer `value`."""
    return [(value >> (width - 1 - i)) & 1 for i in range(width)]


def bits_to_int(bits: list[int]) -> int:
    result = 0
    for b in bits:
        result = (result << 1) | b
    return result


def bits_to_str(bits: list[int]) -> str:
    return "".join(str(b) for b in bits)


def str_to_bits(s: str) -> list[int]:
    return [int(c) for c in s if c in "01"]


def poly_notation(poly_int: int, degree: int) -> str:
    """Format integer polynomial as human-readable string, e.g. 'x^16+x^12+x^5+1'."""
    bits = int_to_bits(poly_int, degree + 1)
    terms: list[str] = []
    for i, b in enumerate(bits):
        if b:
            exp = degree - i
            if exp == 0:
                terms.append("1")
            elif exp == 1:
                terms.append("x")
            else:
                terms.append(f"x^{exp}")
    return " + ".join(terms)


def xor_divide(dividend: list[int], divisor: list[int]) -> list[int]:
    """
    Modulo-2 XOR long division.
    Performs polynomial division over GF(2).
    Returns the remainder — exactly len(divisor)-1 bits.
    """
    d = list(dividend)
    deg = len(divisor)
    for i in range(len(d) - deg + 1):
        if d[i] == 1:
            for j in range(deg):
                d[i + j] ^= divisor[j]
    return d[-(deg - 1):]


def compute_crc(frame_bits: list[int], gen_name: str) -> tuple[list[int], list[int]]:
    """
    Compute CRC for frame_bits using the named generator.

    Algorithm (per Tanenbaum §3.2.2):
      1. Let r = degree(G(x)). Append r zero bits → x^r * M(x).
      2. Divide x^r*M(x) by G(x) using modulo-2 division.
      3. Subtract (XOR) remainder into the r appended zeros → T(x).

    Returns: (transmitted_frame_bits, crc_bits)
    """
    poly_int, degree = GENERATORS[gen_name]
    gen_bits = int_to_bits(poly_int, degree + 1)  # degree+1 bits including leading 1
    padded = frame_bits + [0] * degree            # step 1
    remainder = xor_divide(list(padded), gen_bits)  # step 2
    transmitted = frame_bits + remainder          # step 3: XOR 0s with remainder = remainder
    return transmitted, remainder


def verify_crc(received_bits: list[int], gen_name: str) -> bool:
    """Divide received frame by G(x); no error detected if remainder is zero."""
    poly_int, degree = GENERATORS[gen_name]
    gen_bits = int_to_bits(poly_int, degree + 1)
    remainder = xor_divide(list(received_bits), gen_bits)
    return all(b == 0 for b in remainder)


def inject_burst_error(frame: list[int], start: int, length: int) -> list[int]:
    """Flip `length` consecutive bits starting at position `start`."""
    corrupted = list(frame)
    for i in range(start, min(start + length, len(frame))):
        corrupted[i] ^= 1
    return corrupted


# ---------------------------------------------------------------------------
# Demo sections
# ---------------------------------------------------------------------------

def demo_textbook_example() -> None:
    """Reproduce Tanenbaum Figure 3-9 step by step."""
    print("=" * 64)
    print("SECTION 1 — TEXTBOOK WORKED EXAMPLE (Tanenbaum Fig 3-9)")
    print("=" * 64)
    frame = str_to_bits("1101011111")
    gen_name = "CRC-4-textbook"
    poly_int, degree = GENERATORS[gen_name]
    gen_bits = int_to_bits(poly_int, degree + 1)

    print(f"  Frame M(x)      : {bits_to_str(frame)}  ({len(frame)} bits)")
    print(f"  Generator G(x)  : {bits_to_str(gen_bits)}  "
          f"(degree {degree} → {poly_notation(poly_int, degree)})")
    print(f"  Appended frame  : {bits_to_str(frame + [0]*degree)}")

    transmitted, remainder = compute_crc(frame, gen_name)
    print(f"  Remainder (CRC) : {bits_to_str(remainder)}")
    print(f"  Transmitted T(x): {bits_to_str(transmitted)}  ({len(transmitted)} bits)")
    print(f"    (frame + CRC = {bits_to_str(frame)} | {bits_to_str(remainder)})")

    ok = verify_crc(transmitted, gen_name)
    print(f"  Receiver verify (clean)       : {'PASS — remainder all-zero' if ok else 'FAIL'}")

    c1 = inject_burst_error(transmitted, 3, 1)
    ok1 = verify_crc(c1, gen_name)
    print(f"  Receiver verify (1-bit flip)  : {'PASS (undetected!)' if ok1 else 'DETECTED ERROR'}")

    c2 = inject_burst_error(transmitted, 1, 3)
    ok2 = verify_crc(c2, gen_name)
    print(f"  Receiver verify (3-bit burst) : {'PASS (undetected!)' if ok2 else 'DETECTED ERROR'}")
    print()


def demo_standard_generators() -> None:
    """Show all standard polynomials with their adoption context."""
    print("=" * 64)
    print("SECTION 2 — STANDARD GENERATOR POLYNOMIALS")
    print("=" * 64)
    meta = [
        ("CRC-4-textbook",       "Tanenbaum §3.2.2",  "Teaching / textbook example"),
        ("CRC-16-IBM",           "IBM SNA / USB",      "BISYNC, USB bulk transfer"),
        ("CRC-16-CCITT",         "ITU-T V.41",         "HDLC, X.25, Bluetooth"),
        ("CRC-32-IEEE",          "IEEE 802.3  HD=4",   "Ethernet, 802.11, ZIP, PNG"),
        ("CRC-32C-Castagnoli",   "RFC 3720  HD=6",     "iSCSI, SCTP, Btrfs, ext4"),
    ]
    header = f"  {'Name':<26} {'Polynomial':<38} {'Standard / Use'}"
    print(header)
    print("  " + "-" * 80)
    for name, std, usage in meta:
        poly_int, degree = GENERATORS[name]
        poly_str = poly_notation(poly_int, degree)
        print(f"  {name:<26} {poly_str:<38} {std}")
        print(f"  {'':26} {'':38} → {usage}")
    print()


def demo_crc32_error_detection() -> None:
    """Show CRC-32-IEEE burst-error detection on a short payload."""
    print("=" * 64)
    print("SECTION 3 — CRC-32-IEEE BURST ERROR DETECTION")
    print("=" * 64)
    payload = str_to_bits("11010111001011001101")  # 20-bit simulated payload
    gen_name = "CRC-32-IEEE"

    transmitted, fcs = compute_crc(payload, gen_name)
    print(f"  Payload              : {bits_to_str(payload)} ({len(payload)} bits)")
    print(f"  FCS / CRC-32         : 0x{bits_to_int(fcs):08X}  ({len(fcs)} check bits appended)")
    print(f"  Transmitted frame    : {len(transmitted)} bits total")
    print()

    tests = [
        ("clean receive",      transmitted,                               "PASS (correct)"),
        ("single-bit flip",    inject_burst_error(transmitted, 7, 1),    "DETECTED"),
        ("burst 8 bits",       inject_burst_error(transmitted, 4, 8),    "DETECTED"),
        ("burst 16 bits",      inject_burst_error(transmitted, 2, 16),   "DETECTED"),
        ("burst 32 bits",      inject_burst_error(transmitted, 0, 32),   "DETECTED"),
    ]
    print(f"  {'Test':<22} {'Result'}")
    print("  " + "-" * 40)
    for label, frame, expected in tests:
        ok = verify_crc(frame, gen_name)
        result = "PASS (no error detected)" if ok else "ERROR DETECTED"
        print(f"  {label:<22} {result}")
    print()
    print("  Theorem: CRC with r check bits detects ALL bursts of length ≤ r.")
    print("  CRC-32 (r=32) → all single-bit, all burst ≤ 32 bits guaranteed caught.")
    print()


def demo_hamming_distance_comparison() -> None:
    """Explain HD=4 vs HD=6 and why Castagnoli CRC-32C was standardized for iSCSI."""
    print("=" * 64)
    print("SECTION 4 — HAMMING DISTANCE: CRC-32 vs CRC-32C")
    print("=" * 64)
    rows = [
        ("CRC-32-IEEE",        "4", "≤ 11,454 bytes", "Misses some 4-bit error combos"),
        ("CRC-32C-Castagnoli", "6", "≤ 32,767 bytes", "Detects all 1–5 bit errors"),
    ]
    print(f"  {'Polynomial':<26} {'HD':<4} {'Message range':<18} {'Implication'}")
    print("  " + "-" * 72)
    for name, hd, rng, note in rows:
        print(f"  {name:<26} {hd:<4} {rng:<18} {note}")
    print()
    print("  Koopman & Chakravarty (2004) exhaustively searched all degree-32 polys.")
    print("  CRC-32C adopted in RFC 3720 (iSCSI), RFC 4960 (SCTP), Linux Btrfs/ext4.")
    print("  IEEE 802.3 retains CRC-32-IEEE for backwards compatibility with Ethernet.")
    print()


def main() -> None:
    print()
    print("CRC POLYNOMIAL ARITHMETIC AND GENERATOR STANDARDS")
    print("Computer Networks — Phase 04, Lesson 27")
    print()
    demo_textbook_example()
    demo_standard_generators()
    demo_crc32_error_detection()
    demo_hamming_distance_comparison()
    print("See docs/en.md for full theoretical background and exercises.")


if __name__ == "__main__":
    main()
