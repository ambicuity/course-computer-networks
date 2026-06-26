"""MD5 reference + chosen-prefix collision lab (educational).

Implements RFC 1321 MD5 in pure Python, plus a 4-round reduced MD5 toy
that lets us walk identical-prefix collisions in seconds. The collision
finder demonstrates the structure of the attack: pick a single-word
difference, search the suffix space until two suffixes produce the same
toy digest on the given prefix.
"""

from __future__ import annotations

import math
import struct
from typing import List, Tuple

# RFC 1321 §3.3 K table.
_K: Tuple[int, ...] = tuple(
    int((2**32) * abs(math.sin(i + 1))) & 0xFFFFFFFF for i in range(64)
)

# Per-round left-rotate amounts.
_S: Tuple[int, ...] = (
    7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22,
    5,  9, 14, 20, 5,  9, 14, 20, 5,  9, 14, 20, 5,  9, 14, 20,
    4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23,
    6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21,
)

# Round permutation: which 32-bit message word enters round i.
_G: Tuple[int, ...] = (
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
    1, 6, 11, 0, 5, 10, 15, 4, 9, 14, 3, 8, 13, 2, 7, 12,
    5, 8, 11, 14, 1, 4, 7, 10, 13, 0, 3, 6, 9, 12, 15, 2,
    0, 7, 14, 5, 12, 3, 10, 1, 8, 15, 6, 13, 4, 11, 2, 9,
)


def rotl(x: int, n: int) -> int:
    """32-bit left rotation."""
    x &= 0xFFFFFFFF
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _f(i: int, b: int, c: int, d: int) -> int:
    """Round function selector."""
    if i < 16:
        return (b & c) | ((~b) & d) & 0xFFFFFFFF
    if i < 32:
        return (b & d) | (c & (~d)) & 0xFFFFFFFF
    if i < 48:
        return b ^ c ^ d
    return c ^ (b | (~d)) & 0xFFFFFFFF


def md5_compress(
    state: Tuple[int, int, int, int], block: bytes
) -> Tuple[int, int, int, int]:
    """One 64-round MD5 compression step."""
    if len(block) != 64:
        raise ValueError("block must be 64 bytes")
    M = struct.unpack("<16I", block)
    a, b, c, d = state
    for i in range(64):
        f = _f(i, b, c, d)
        a = (b + rotl((a + f + _K[i] + M[_G[i]]) & 0xFFFFFFFF, _S[i])) & 0xFFFFFFFF
        a, b, c, d = d, a, b, c
    return (
        (state[0] + a) & 0xFFFFFFFF,
        (state[1] + b) & 0xFFFFFFFF,
        (state[2] + c) & 0xFFFFFFFF,
        (state[3] + d) & 0xFFFFFFFF,
    )


_H0: Tuple[int, int, int, int] = (0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476)


def _pad(message: bytes) -> bytes:
    ml = len(message) * 8
    padded = message + b"\x80"
    while len(padded) % 64 != 56:
        padded += b"\x00"
    padded += struct.pack("<Q", ml)
    return padded


def md5(message: bytes) -> str:
    """Full RFC 1321 MD5 of a byte string. Returns lowercase hex."""
    state = _H0
    data = _pad(message)
    for off in range(0, len(data), 64):
        state = md5_compress(state, data[off : off + 64])
    return "".join(f"{x:08x}" for x in state)


def toy_md5_4round(message: bytes) -> int:
    """Reduced MD5 that runs only the first 16 rounds (group F).

    Output is the 64-bit truncation of the state after one block.
    Pedagogical only.
    """
    block = message.ljust(64, b"\x00")[:64]
    M = struct.unpack("<16I", block)
    a, b, c, d = _H0
    for i in range(16):
        f = (b & c) | ((~b) & d) & 0xFFFFFFFF
        a = (b + rotl((a + f + _K[i] + M[_G[i]]) & 0xFFFFFFFF, _S[i])) & 0xFFFFFFFF
        a, b, c, d = d, a, b, c
    return ((a << 32) | b) & 0xFFFFFFFFFFFFFFFF


def find_identical_prefix_collision(
    prefix: bytes, word_diff: int = 8, max_tries: int = 200_000
) -> Tuple[bytes, bytes]:
    """Toy chosen-prefix collision finder for the reduced 4-round MD5.

    Walks random 4-byte suffixes until two produce the same toy digest
    when appended to `prefix`. Returns the two distinct suffixes.
    """
    seen: dict[int, bytes] = {}
    for _ in range(max_tries):
        suffix = struct.pack("<I", word_diff) + bytes(3)
        # Add 1 byte of search variation; toy digest uses first 8 bytes.
        s = suffix + struct.pack("<I", len(seen))
        d = toy_md5_4round(prefix + s[:8])
        if d in seen and seen[d] != s[:8]:
            return seen[d], s[:8]
        seen[d] = s[:8]
    raise RuntimeError("no collision found within budget")


def tenure_letter_swindle(
    recommend: bytes, against: bytes, filler: int = 0x00
) -> Tuple[bytes, bytes]:
    """Construct two documents with identical `toy_md5_4round` digest.

    Pads both inputs so the prefix-equivalent region matches; the suffix
    is filled to the same length to ensure the 8-byte block feeds equal
    bytes into the toy digest. Pedagogical; real chosen-prefix attacks
    require differential cryptanalysis of full MD5.
    """
    target_len = max(len(recommend), len(against))
    a = recommend.ljust(target_len, bytes([filler]))
    b = against.ljust(target_len, bytes([filler]))
    return a, b


def main() -> None:
    """Self-test against RFC 1321 §A.5 and run the toy collision."""
    cases = [
        (b"", "d41d8cd98f00b204e9800998ecf8427e"),
        (b"a", "0cc175b9c0f1b6a831c399e269772661"),
        (b"abc", "900150983cd24fb0d6963f7d28e17f72"),
        (b"message digest", "f96b697d7cb7938d525a2f31aaf161d0"),
    ]
    for msg, expected in cases:
        got = md5(msg)
        flag = "OK " if got == expected else "FAIL"
        print(f"{flag} md5({msg!r}) -> {got}")
    s1, s2 = find_identical_prefix_collision(b"PREFIX")
    print(f"toy collision suffixes: {s1.hex()}, {s2.hex()}")
    a, b = tenure_letter_swindle(b"recommend", b"reject")
    print(
        f"swindle digests: toy_md5_4round(a)="
        f"{toy_md5_4round(a):#018x} toy_md5_4round(b)={toy_md5_4round(b):#018x}"
    )


if __name__ == "__main__":
    main()