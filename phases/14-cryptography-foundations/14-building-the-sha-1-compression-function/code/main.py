"""SHA-1 compression function from FIPS 180-4.

Pure-Python, stdlib-only implementation of a single SHA-1 compression step.
Includes the round constants K[t], the 80-word message schedule W[t], the
four non-linear round functions f(t), and a full sha1() driver that matches
the published test vectors (da39a3... for "", a9993e... for "abc").

This file is intentionally line-by-line verbose so each piece of the
compression function is inspectable.
"""

from __future__ import annotations

import struct
from typing import List, Tuple

# Initial hash value H(0) from FIPS 180-4 Sec. 5.3.1.
H0: Tuple[int, int, int, int, int] = (
    0x67452301,
    0xEFCDAB89,
    0x98BADCFE,
    0x10325476,
    0xC3D2E1F0,
)

# Round constants K[t] from FIPS 180-4 Sec. 4.2.1.
K: Tuple[int, ...] = (
    0x5A827999,  # 0..19
    0x6ED9EBA1,  # 20..39
    0x8F1BBCDC,  # 40..59
    0xCA62C1D6,  # 60..79
)


def rotl(x: int, n: int) -> int:
    """32-bit left rotation."""
    x &= 0xFFFFFFFF
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def extend_schedule(block: bytes) -> List[int]:
    """Expand a 64-byte block into the 80-word schedule W[t]."""
    if len(block) != 64:
        raise ValueError("block must be exactly 64 bytes")
    W: List[int] = list(struct.unpack(">16I", block))
    for t in range(16, 80):
        W.append(rotl(W[t - 3] ^ W[t - 8] ^ W[t - 14] ^ W[t - 16], 1))
    return W


def _f(t: int, b: int, c: int, d: int) -> int:
    """The four non-linear round functions selected by phase."""
    if 0 <= t <= 19:
        return ((b & c) | ((~b) & d)) & 0xFFFFFFFF  # Ch
    if 20 <= t <= 39:
        return b ^ c ^ d  # Parity
    if 40 <= t <= 59:
        return (b & c) | (b & d) | (c & d)  # Majority
    return b ^ c ^ d  # Parity again


def sha1_compress(
    H: Tuple[int, int, int, int, int], block: bytes
) -> Tuple[int, int, int, int, int]:
    """Run one 80-round SHA-1 compression step.

    Returns the new chaining value (H0', H1', H2', H3', H4') ready to feed
    into the next block, or to be combined into the final digest.
    """
    if len(block) != 64:
        raise ValueError("block must be 64 bytes (512 bits)")
    W = extend_schedule(block)
    a, b, c, d, e = H
    for t in range(80):
        k = K[t // 20]
        T = (rotl(a, 5) + _f(t, b, c, d) + e + k + W[t]) & 0xFFFFFFFF
        e = d
        d = c
        c = rotl(b, 30)
        b = a
        a = T
    return (
        (H[0] + a) & 0xFFFFFFFF,
        (H[1] + b) & 0xFFFFFFFF,
        (H[2] + c) & 0xFFFFFFFF,
        (H[3] + d) & 0xFFFFFFFF,
        (H[4] + e) & 0xFFFFFFFF,
    )


def _md_pad(message: bytes) -> bytes:
    """SHA-1 padding: append 0x80, zero-fill to 56 mod 64, then 8-byte big-endian length."""
    ml = len(message) * 8
    padded = message + b"\x80"
    while len(padded) % 64 != 56:
        padded += b"\x00"
    padded += struct.pack(">Q", ml)
    return padded


def sha1(message: bytes) -> str:
    """Compute SHA-1 of a byte string. Returns lowercase hex digest."""
    if not isinstance(message, (bytes, bytearray)):
        raise TypeError("sha1() requires bytes")
    H = H0
    data = _md_pad(message)
    for off in range(0, len(data), 64):
        H = sha1_compress(H, data[off : off + 64])
    return "".join(f"{x:08x}" for x in H)


def main() -> None:
    """Run self-tests against the canonical FIPS test vectors."""
    cases = [
        (b"", "da39a3ee5e6b4b0d3255bfef95601890afd80709"),
        (b"abc", "a9993e364706816aba3e25717850c26c9cd0d89d"),
        (
            b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq",
            "84983e441c3bd26ebaae4aa1f95129e5e54670f1",
        ),
    ]
    for msg, expected in cases:
        got = sha1(msg)
        flag = "OK " if got == expected else "FAIL"
        print(f"{flag} sha1({msg!r}) -> {got}")
    # Direct compression step against the empty block, for pedagogy.
    padded_empty = _md_pad(b"")
    H1 = sha1_compress(H0, padded_empty)
    print("One-block empty state:", "".join(f"{x:08x}" for x in H1))


if __name__ == "__main__":
    main()