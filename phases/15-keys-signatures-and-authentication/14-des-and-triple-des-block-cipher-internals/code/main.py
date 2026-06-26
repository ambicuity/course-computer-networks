#!/usr/bin/env python3
"""Pure-Python DES and Triple-DES (3DES / EDE) implementation.

Implements, with stdlib only:

  * DES tables: IP, FP, E, P, PC1, PC2, eight S-boxes (FIPS 46-3)
  * Key schedule producing 16 round keys from a 56-bit effective key
  * Single-block DES encrypt / decrypt
  * ECB mode for an arbitrary-length byte string (must be 8-byte aligned)
  * 2-key Triple-DES (EDE) for legacy interop

Run with `python3 main.py`. Verified against the FIPS 46-3 Known Answer Tests.
"""

from __future__ import annotations

from typing import List, Tuple

IP = [
    58, 50, 42, 34, 26, 18, 10, 2,
    60, 52, 44, 36, 28, 20, 12, 4,
    62, 54, 46, 38, 30, 22, 14, 6,
    64, 56, 48, 40, 32, 24, 16, 8,
    57, 49, 41, 33, 25, 17, 9, 1,
    59, 51, 43, 35, 27, 19, 11, 3,
    61, 53, 45, 37, 29, 21, 13, 5,
    63, 55, 47, 39, 31, 23, 15, 7,
]
FP = [0] * 64
for i, p in enumerate(IP):
    FP[p - 1] = i + 1

E = [
    32, 1, 2, 3, 4, 5,
    4, 5, 6, 7, 8, 9,
    8, 9, 10, 11, 12, 13,
    12, 13, 14, 15, 16, 17,
    16, 17, 18, 19, 20, 21,
    20, 21, 22, 23, 24, 25,
    24, 25, 26, 27, 28, 29,
    28, 29, 30, 31, 32, 1,
]
P = [
    16, 7, 20, 21,
    29, 12, 28, 17,
    1, 15, 23, 26,
    5, 18, 31, 10,
    2, 8, 24, 14,
    32, 27, 3, 9,
    19, 13, 30, 6,
    22, 11, 4, 25,
]

PC1 = [
    57, 49, 41, 33, 25, 17, 9,
    1, 58, 50, 42, 34, 26, 18,
    10, 2, 59, 51, 43, 35, 27,
    19, 11, 3, 60, 52, 44, 36,
    63, 55, 47, 39, 31, 23, 15,
    7, 62, 54, 46, 38, 30, 22,
    14, 6, 61, 53, 45, 37, 29,
    21, 13, 5, 28, 20, 12, 4,
]
PC2 = [
    14, 17, 11, 24, 1, 5,
    3, 28, 15, 6, 21, 10,
    23, 19, 12, 4, 26, 8,
    16, 7, 27, 20, 13, 2,
    41, 52, 31, 37, 47, 55,
    30, 40, 51, 45, 33, 48,
    44, 49, 39, 56, 34, 53,
    46, 42, 50, 36, 29, 32,
]

ROTATIONS = [1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1]

SBOXES = [
    [
        [14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7],
        [0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11, 9, 5, 3, 8],
        [4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0],
        [15, 12, 8, 2, 4, 9, 1, 7, 5, 11, 3, 14, 10, 0, 6, 13],
    ],
    [
        [15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10],
        [3, 13, 4, 7, 15, 2, 8, 14, 12, 0, 1, 10, 6, 9, 11, 5],
        [0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15],
        [13, 8, 10, 1, 3, 15, 4, 2, 11, 6, 7, 12, 0, 5, 14, 9],
    ],
    [
        [10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8],
        [13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14, 12, 11, 15, 1],
        [13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7],
        [1, 10, 13, 0, 6, 9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12],
    ],
    [
        [7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15],
        [13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12, 1, 10, 14, 9],
        [10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4],
        [3, 15, 0, 6, 10, 1, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14],
    ],
    [
        [2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9],
        [14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10, 3, 9, 8, 6],
        [4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14],
        [11, 8, 12, 7, 1, 14, 2, 13, 6, 15, 0, 9, 10, 4, 5, 3],
    ],
    [
        [12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11],
        [10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14, 0, 11, 3, 8],
        [9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6],
        [4, 3, 2, 12, 9, 5, 15, 10, 11, 14, 1, 7, 6, 0, 8, 13],
    ],
    [
        [4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1],
        [13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12, 2, 15, 8, 6],
        [1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2],
        [6, 11, 13, 8, 1, 4, 10, 7, 9, 5, 0, 15, 14, 2, 3, 12],
    ],
    [
        [13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7],
        [1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11, 0, 14, 9, 2],
        [7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8],
        [2, 1, 14, 7, 4, 10, 8, 13, 15, 12, 9, 0, 3, 5, 6, 11],
    ],
]


def _permute(bits: int, table: List[int], in_width: int) -> int:
    out = 0
    for i, src in enumerate(table):
        out = (out << 1) | ((bits >> (in_width - src)) & 1)
    return out


def _key_schedule(key64: int) -> List[int]:
    key56 = _permute(key64, PC1, 64)
    c = (key56 >> 28) & ((1 << 28) - 1)
    d = key56 & ((1 << 28) - 1)
    subkeys: List[int] = []
    for r in ROTATIONS:
        c = ((c << r) | (c >> (28 - r))) & ((1 << 28) - 1)
        d = ((d << r) | (d >> (28 - r))) & ((1 << 28) - 1)
        subkeys.append(_permute((c << 28) | d, PC2, 56))
    return subkeys


def _round_function(r32: int, k48: int) -> int:
    expanded = _permute(r32, E, 32)
    mixed = expanded ^ k48
    out = 0
    for i in range(8):
        chunk = (mixed >> (42 - 6 * i)) & 0x3F
        row = ((chunk >> 5) << 1) | (chunk & 1)
        col = (chunk >> 1) & 0xF
        out = (out << 4) | SBOXES[i][row][col]
    return _permute(out, P, 32)


def des_block(block8: bytes, key8: bytes, decrypt: bool = False) -> bytes:
    block = int.from_bytes(block8, "big")
    key = int.from_bytes(key8, "big")
    subkeys = _key_schedule(key)
    if decrypt:
        subkeys = subkeys[::-1]
    state = _permute(block, IP, 64)
    left = (state >> 32) & 0xFFFFFFFF
    right = state & 0xFFFFFFFF
    for k in subkeys:
        new_right = left ^ _round_function(right, k)
        left = right
        right = new_right
    preoutput = (right << 32) | left
    return _permute(preoutput, FP, 64).to_bytes(8, "big")


def des_encrypt(plaintext: bytes, key: bytes) -> bytes:
    if len(plaintext) % 8 != 0:
        raise ValueError("plaintext length must be a multiple of 8")
    out = bytearray()
    for i in range(0, len(plaintext), 8):
        out.extend(des_block(plaintext[i:i + 8], key, decrypt=False))
    return bytes(out)


def des_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    if len(ciphertext) % 8 != 0:
        raise ValueError("ciphertext length must be a multiple of 8")
    out = bytearray()
    for i in range(0, len(ciphertext), 8):
        out.extend(des_block(ciphertext[i:i + 8], key, decrypt=True))
    return bytes(out)


def triple_des_encrypt(plaintext: bytes, k1: bytes, k2: bytes) -> bytes:
    if len(plaintext) % 8 != 0:
        raise ValueError("plaintext length must be a multiple of 8")
    return des_encrypt(des_decrypt(des_encrypt(plaintext, k1), k2), k1)


def triple_des_decrypt(ciphertext: bytes, k1: bytes, k2: bytes) -> bytes:
    return des_decrypt(des_encrypt(des_decrypt(ciphertext, k1), k2), k1)


def nist_kat() -> bool:
    """Run a FIPS 46-3 Known Answer Test (single block).

    Plaintext 0x4E6F772069732074, key 0x0123456789ABCDEF,
    expected ciphertext 0x3FA40E8A984D4815 (FIPS 46-3 example).
    """
    pt = bytes.fromhex("4E6F772069732074")
    expected_ct = bytes.fromhex("3FA40E8A984D4815")
    key = bytes.fromhex("0123456789ABCDEF")
    actual_ct = des_block(pt, key)
    if actual_ct != expected_ct:
        return False
    if des_block(actual_ct, key, decrypt=True) != pt:
        return False
    return True


def demo_round_trace() -> None:
    """Show the L,R state after each of the 16 rounds for one block."""
    block = bytes.fromhex("0123456789ABCDEF")
    key = bytes.fromhex("133457799BBCDFF1")
    b = int.from_bytes(block, "big")
    k = int.from_bytes(key, "big")
    state = _permute(b, IP, 64)
    left = (state >> 32) & 0xFFFFFFFF
    right = state & 0xFFFFFFFF
    subkeys = _key_schedule(k)
    print("Round | L (hex)        | R (hex)")
    print(f"  0   | {left:08x}     | {right:08x}")
    for i, sk in enumerate(subkeys, 1):
        new_right = left ^ _round_function(right, sk)
        left, right = right, new_right
        print(f"  {i:<3} | {left:08x}     | {right:08x}")


def main() -> None:
    print("=== NIST DES Known Answer Test ===")
    print(f"  PASS" if nist_kat() else "  FAIL")

    print("\n=== Round trace (FIPS 46-3 example) ===")
    demo_round_trace()

    print("\n=== Triple-DES (2-key EDE) round-trip ===")
    k1 = bytes.fromhex("0123456789ABCDEF")
    k2 = bytes.fromhex("23456789ABCDEF01")
    pt = b"NetworkSe!"   # 10 bytes -> pad to 16 with PKCS#7-style
    pt = pt + b"\x06\x06\x06\x06\x06\x06"
    ct = triple_des_encrypt(pt, k1, k2)
    rt = triple_des_decrypt(ct, k1, k2)
    print(f"  plaintext:  {pt!r}")
    print(f"  ciphertext: {ct.hex()}")
    print(f"  decrypt OK: {rt == pt}")


if __name__ == "__main__":
    main()