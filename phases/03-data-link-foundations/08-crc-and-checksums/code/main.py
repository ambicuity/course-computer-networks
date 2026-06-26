"""CRC polynomial division and Internet/Fletcher checksums.

A stdlib-only demonstration of the two error-detecting codes covered in
Tanenbaum & Wetherall, Computer Networks, Section 3.2.2:

  * Cyclic Redundancy Check (CRC) -- polynomial long division modulo 2,
    using the textbook generator G(x) = x^4 + x + 1 (0x13) and the
    IEEE 802 CRC-32 generator.
  * Internet checksum (RFC 1071) -- one's-complement sum of 16-bit words.
  * Fletcher-16 checksum -- a position-weighted running sum.

No network calls, no third-party packages. Run with:

    python3 code/main.py
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# CRC: polynomial arithmetic over GF(2)
# ---------------------------------------------------------------------------

def poly_divmod(dividend: int, divisor: int) -> tuple[int, int]:
    """Divide two polynomials over GF(2), represented as bit strings.

    The most-significant set bit of `dividend` is the coefficient of the
    highest power of x. Subtraction is XOR (no carries, no borrows).
    Returns (quotient, remainder).
    """
    if divisor == 0:
        raise ValueError("divisor polynomial must be non-zero")
    divisor_bits = divisor.bit_length()
    quotient = 0
    remainder = dividend
    # "goes into" means the dividend has at least as many bits as the divisor
    while remainder.bit_length() >= divisor_bits:
        shift = remainder.bit_length() - divisor_bits
        quotient ^= 1 << shift
        remainder ^= divisor << shift
    return quotient, remainder


def crc_encode(data: int, generator: int) -> tuple[int, int]:
    """Append r zero bits to data and return (transmitted_codeword, remainder).

    r is the degree of the generator polynomial.
    """
    r = generator.bit_length() - 1
    shifted = data << r  # x^r * M(x)
    _, remainder = poly_divmod(shifted, generator)
    codeword = shifted ^ remainder  # subtract remainder (== XOR over GF(2))
    return codeword, remainder


def crc_check(received: int, generator: int) -> bool:
    """Return True if `received` is divisible by the generator (no error)."""
    _, remainder = poly_divmod(received, generator)
    return remainder == 0


# Standard generator polynomials (high-order bit first, low-order bit last).
G_X4_X1_1 = 0b10011          # x^4 + x + 1            (textbook example, Fig. 3-9)
G_CRC16_CCITT = 0x11021      # x^16 + x^12 + x^5 + 1  (HDLC, X.25, Bluetooth)
G_CRC32_IEEE = 0x104C11DB7   # IEEE 802 / Ethernet / FDDI


# ---------------------------------------------------------------------------
# Internet checksum (RFC 1071), 16-bit one's-complement sum
# ---------------------------------------------------------------------------

def internet_checksum(message: bytes) -> int:
    """Compute the 16-bit Internet checksum (RFC 1071).

    The message is treated as a sequence of 16-bit words (big-endian).
    If the byte count is odd, a trailing zero byte is appended.
    Returns the one's-complement of the one's-complement sum.
    """
    if len(message) % 2 == 1:
        message = message + b"\x00"
    total = 0
    for i in range(0, len(message), 2):
        word = (message[i] << 8) | message[i + 1]
        total += word
        # fold high-order overflow back into the low 16 bits (end-around carry)
        total = (total & 0xFFFF) + (total >> 16)
    # a second fold handles the case where the first fold produced a carry
    total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def verify_internet_checksum(message: bytes) -> bool:
    """Sum every 16-bit word (including the checksum word); good == 0xFFFF,
    whose one's-complement is 0. Returning True means no error detected."""
    if len(message) % 2 == 1:
        message = message + b"\x00"
    total = 0
    for i in range(0, len(message), 2):
        total += (message[i] << 8) | message[i + 1]
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return total == 0xFFFF


# ---------------------------------------------------------------------------
# Fletcher-16 checksum (Fletcher, 1982) -- position-weighted
# ---------------------------------------------------------------------------

def fletcher16(data: bytes, modulus: int = 255) -> tuple[int, int]:
    """Return (sum1, sum2) for Fletcher-16.

    sum1 is the running sum of bytes mod `modulus`; sum2 is the running
    sum of sum1 values mod `modulus`. The position weighting (sum2) is
    what lets Fletcher catch reordering that a plain sum misses.
    """
    sum1 = 0
    sum2 = 0
    for byte in data:
        sum1 = (sum1 + byte) % modulus
        sum2 = (sum2 + sum1) % modulus
    return sum1, sum2


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def _bin(n: int, width: int) -> str:
    return format(n, f"0{width}b")


def main() -> None:
    print("=" * 70)
    print("CRC with the textbook generator G(x) = x^4 + x + 1 (0x13)")
    print("=" * 70)
    data = 0b1101011111  # the 10-bit frame from Figure 3-9
    gen = G_X4_X1_1
    codeword, remainder = crc_encode(data, gen)
    print(f"  data frame M(x)   : {_bin(data, 10)}")
    print(f"  generator G(x)    : {_bin(gen, 5)}  (degree 4, so 4 zero bits appended)")
    print(f"  remainder         : {_bin(remainder, 4)}")
    print(f"  transmitted T(x)  : {_bin(codeword, 14)}  (data || remainder)")
    print(f"  receiver divides  : good={crc_check(codeword, gen)}")
    corrupted = codeword ^ 0b00000000000010  # single-bit error at position 1
    print(f"  single-bit error  : {_bin(corrupted, 14)}  detected={not crc_check(corrupted, gen)}")
    print()

    print("=" * 70)
    print("IEEE 802 CRC-32 generator on a 48-byte payload stub")
    print("=" * 70)
    payload = b"The quick brown fox jumps over the lazy dog!!!!!!"  # 48 bytes
    data_int = int.from_bytes(payload, "big")
    cw32, rem32 = crc_encode(data_int, G_CRC32_IEEE)
    print(f"  payload length    : {len(payload)} bytes")
    print(f"  CRC-32 remainder  : {rem32:#010x}")
    print(f"  transmitted check : good={crc_check(cw32, G_CRC32_IEEE)}")
    flipped = cw32 ^ (1 << 200)  # flip one bit deep in the payload
    print(f"  1-bit corruption  : detected={not crc_check(flipped, G_CRC32_IEEE)}")
    print()

    print("=" * 70)
    print("Internet checksum (RFC 1071) on a mock IPv4 header")
    print("=" * 70)
    # A minimal 20-byte IPv4 header with checksum field zeroed.
    header = bytes([
        0x45, 0x00, 0x00, 0x14,        # version/IHL, TOS, total length 20
        0x1c, 0x46, 0x40, 0x00,        # id, flags/frag
        0x40, 0x06, 0x00, 0x00,        # TTL=64, proto=TCP, checksum=0 (placeholder)
        0xc0, 0xa8, 0x01, 0x01,        # src 192.168.1.1
        0xc0, 0xa8, 0x01, 0x02,        # dst 192.168.1.2
    ])
    cksum = internet_checksum(header)
    print(f"  computed checksum : {cksum:#06x}")
    full = header[:10] + cksum.to_bytes(2, "big") + header[12:]
    print(f"  full header       : {full.hex()}")
    print(f"  receiver verify   : good={verify_internet_checksum(full)}")
    bad = bytearray(full)
    bad[8] ^= 0xFF
    bad[9] ^= 0xFF  # flip all bits in word 5: changes the sum, is caught
    print(f"  two-bit corruption: detected={not verify_internet_checksum(bytes(bad))}")
    print()

    print("=" * 70)
    print("Fletcher-16 vs Internet checksum: reordering detection")
    print("=" * 70)
    block = b"\x01\x02\x03\x04"
    s1a, s2a = fletcher16(block)
    print(f"  bytes [1,2,3,4]   : fletcher16 sum1={s1a} sum2={s2a}")
    reordered = b"\x04\x03\x02\x01"
    s1b, s2b = fletcher16(reordered)
    print(f"  bytes [4,3,2,1]   : fletcher16 sum1={s1b} sum2={s2b}")
    print(f"  fletcher detects reorder: {s2a != s2b}")
    print(f"  internet([1,2,3,4])     = {internet_checksum(block):#06x}")
    print(f"  internet([4,3,2,1])     = {internet_checksum(reordered):#06x}")
    print("  (Internet checksum is position-blind within 16-bit words -> misses reorder)")
    print()

    print("=" * 70)
    print("Burst-error reach of CRC with r check bits")
    print("=" * 70)
    r = G_CRC32_IEEE.bit_length() - 1
    print(f"  CRC-32 has r={r} check bits.")
    print(f"  Detects ALL bursts of length <= {r}: guaranteed by theory.")
    print(f"  Burst of length {r+1} slips through with probability 2^(-{r-1}).")
    print(f"  Longer / multiple bursts slip with probability ~2^(-{r}).")


if __name__ == "__main__":
    main()
