"""DES and Triple DES (EDE) — stdlib Python reference implementation.

A pedagogical single-DES + 3DES implementation with a key schedule, the eight
S-boxes, a Feistel round, and a FIPS 46-2 known-answer test. The brute-force
demo is sized for 4-bit keys so it terminates in real time; the same code,
scaled to 56-bit keys, demonstrates the 1977-vintage exhaustive search.

Run: python3 code/main.py
"""

from __future__ import annotations

import os
import time
from typing import List, Tuple


# ---------------------------------------------------------------------------
# DES permutation tables (FIPS 46-3, Section 3).
# ---------------------------------------------------------------------------

# Initial Permutation (IP).
IP = [
    58, 50, 42, 34, 26, 18, 10, 2,
    60, 52, 44, 36, 28, 20, 12, 4,
    62, 54, 46, 38, 30, 22, 14, 6,
    64, 56, 48, 40, 32, 24, 16, 8,
    57, 49, 41, 33, 25, 17,  9, 1,
    59, 51, 43, 35, 27, 19, 11, 3,
    61, 53, 45, 37, 29, 21, 13, 5,
    63, 55, 47, 39, 31, 23, 15, 7,
]

# Inverse Initial Permutation (IP^-1).
IP_INV = [0] * 64
for i, p in enumerate(IP):
    IP_INV[p - 1] = i + 1

# Expansion E: 32 bits -> 48 bits.
E = [
    32,  1,  2,  3,  4,  5,
     4,  5,  6,  7,  8,  9,
     8,  9, 10, 11, 12, 13,
    12, 13, 14, 15, 16, 17,
    16, 17, 18, 19, 20, 21,
    20, 21, 22, 23, 24, 25,
    24, 25, 26, 27, 28, 29,
    28, 29, 30, 31, 32,  1,
]

# Permutation P: 32 bits -> 32 bits.
P = [
    16,  7, 20, 21, 29, 12, 28, 17,
     1, 15, 23, 26,  5, 18, 31, 10,
     2,  8, 24, 14, 32, 27,  3,  9,
    19, 13, 30,  6, 22, 11,  4, 25,
]

# The 8 DES S-boxes: 6 bits in, 4 bits out.
SBOX = [
    # S1
    [[14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7],
     [0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11, 9, 5, 3, 8],
     [4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0],
     [15, 12, 8, 2, 4, 9, 1, 7, 5, 11, 3, 14, 10, 0, 6, 13]],
    # S2
    [[15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10],
     [3, 13, 4, 7, 15, 2, 8, 14, 12, 0, 1, 10, 6, 9, 11, 5],
     [0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15],
     [13, 8, 10, 1, 3, 15, 4, 2, 11, 6, 7, 12, 0, 5, 14, 9]],
    # S3
    [[10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8],
     [13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14, 12, 11, 15, 1],
     [13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7],
     [1, 10, 13, 0, 6, 9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12]],
    # S4
    [[7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15],
     [13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12, 1, 10, 14, 9],
     [10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4],
     [3, 15, 0, 6, 10, 1, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14]],
    # S5
    [[2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9],
     [14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10, 3, 9, 8, 6],
     [4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14],
     [11, 8, 12, 7, 1, 14, 2, 13, 6, 15, 0, 9, 10, 4, 5, 3]],
    # S6
    [[12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11],
     [10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14, 0, 11, 3, 8],
     [9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6],
     [4, 3, 2, 12, 9, 5, 15, 10, 11, 14, 1, 7, 6, 0, 8, 13]],
    # S7
    [[4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1],
     [13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12, 2, 15, 8, 6],
     [1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2],
     [6, 11, 13, 8, 1, 4, 10, 7, 9, 5, 0, 15, 14, 2, 3, 12]],
    # S8
    [[13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7],
     [1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11, 0, 14, 9, 2],
     [7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8],
     [2, 1, 14, 7, 4, 10, 8, 13, 15, 12, 9, 0, 3, 5, 6, 11]],
]

# PC-1 (parity-stripping permutation) and PC-2 (subkey permutation).
PC1 = [
    57, 49, 41, 33, 25, 17,  9,
     1, 58, 50, 42, 34, 26, 18,
    10,  2, 59, 51, 43, 35, 27,
    19, 11,  3, 60, 52, 44, 36,
    63, 55, 47, 39, 31, 23, 15,
     7, 62, 54, 46, 38, 30, 22,
    14,  6, 61, 53, 45, 37, 29,
    21, 13,  5, 28, 20, 12,  4,
]

PC2 = [
    14, 17, 11, 24,  1,  5,  3, 28,
    15,  6, 21, 10, 23, 19, 12,  4,
    26,  8, 16,  7, 27, 20, 13,  2,
    41, 52, 31, 37, 47, 55, 30, 40,
    51, 45, 33, 48, 44, 49, 39, 56,
    34, 53, 46, 42, 50, 36, 29, 32,
]

# Round shift schedule.
SHIFTS = [1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1]


# ---------------------------------------------------------------------------
# Bit-list helpers. We work in lists of 0/1 ints for clarity.
# ---------------------------------------------------------------------------

def _bytes_to_bits(data: bytes) -> List[int]:
    bits: List[int] = []
    for b in data:
        for i in range(8):
            bits.append((b >> (7 - i)) & 1)
    return bits


def _bits_to_bytes(bits: List[int]) -> bytes:
    if len(bits) % 8 != 0:
        raise ValueError("bit length must be a multiple of 8")
    out = bytearray(len(bits) // 8)
    for i, bit in enumerate(bits):
        if bit:
            out[i // 8] |= 1 << (7 - (i % 8))
    return bytes(out)


def _permute(table: List[int], bits: List[int]) -> List[int]:
    return [bits[i - 1] for i in table]


def _xor(a: List[int], b: List[int]) -> List[int]:
    return [x ^ y for x, y in zip(a, b)]


def _left_rotate(bits: List[int], n: int) -> List[int]:
    n %= len(bits)
    return bits[n:] + bits[:n]


def _sbox_substitute(xored48: List[int]) -> List[int]:
    if len(xored48) != 48:
        raise ValueError("S-box input must be 48 bits")
    out: List[int] = []
    for i in range(8):
        chunk = xored48[i * 6:(i + 1) * 6]
        row = (chunk[0] << 1) | chunk[5]
        col = (chunk[1] << 3) | (chunk[2] << 2) | (chunk[3] << 1) | chunk[4]
        val = SBOX[i][row][col]
        for j in range(4):
            out.append((val >> (3 - j)) & 1)
    return out


# ---------------------------------------------------------------------------
# Key schedule.
# ---------------------------------------------------------------------------

def key_schedule(key8: bytes) -> List[List[int]]:
    if len(key8) != 8:
        raise ValueError("DES key must be 8 bytes (64 bits)")
    key_bits = _bytes_to_bits(key8)
    # PC-1 strips parity and gives 56 bits.
    key56 = _permute(PC1, key_bits)
    C, D = key56[:28], key56[28:]
    subkeys: List[List[int]] = []
    for shift in SHIFTS:
        C = _left_rotate(C, shift)
        D = _left_rotate(D, shift)
        subkeys.append(_permute(PC2, C + D))
    return subkeys


# ---------------------------------------------------------------------------
# DES round + block.
# ---------------------------------------------------------------------------

def _round_function(r32: List[int], subkey48: List[int]) -> List[int]:
    expanded = _permute(E, r32)
    xored = _xor(expanded, subkey48)
    sboxed = _sbox_substitute(xored)
    return _permute(P, sboxed)


def des_encrypt_block(block: bytes, key: bytes) -> bytes:
    if len(block) != 8:
        raise ValueError("DES block must be 8 bytes")
    bits = _bytes_to_bits(block)
    bits = _permute(IP, bits)
    L, R = bits[:32], bits[32:]
    for subkey in key_schedule(key):
        new_L = R
        new_R = _xor(L, _round_function(R, subkey))
        L, R = new_L, new_R
    bits = _permute(IP_INV, R + L)  # final swap is implicit.
    return _bits_to_bytes(bits)


def des_decrypt_block(block: bytes, key: bytes) -> bytes:
    if len(block) != 8:
        raise ValueError("DES block must be 8 bytes")
    bits = _bytes_to_bits(block)
    bits = _permute(IP, bits)
    L, R = bits[:32], bits[32:]
    for subkey in reversed(key_schedule(key)):
        new_R = L
        new_L = _xor(R, _round_function(L, subkey))
        L, R = new_L, new_R
    bits = _permute(IP_INV, R + L)
    return _bits_to_bytes(bits)


# ---------------------------------------------------------------------------
# Triple DES (EDE) — 2-key and 3-key variants.
# ---------------------------------------------------------------------------

def tdes_encrypt(block: bytes, k1: bytes, k2: bytes, k3: bytes) -> bytes:
    return des_encrypt_block(des_decrypt_block(des_encrypt_block(block, k1), k2), k3)


def tdes_decrypt(block: bytes, k1: bytes, k2: bytes, k3: bytes) -> bytes:
    return des_decrypt_block(des_encrypt_block(des_decrypt_block(block, k3), k2), k1)


# ---------------------------------------------------------------------------
# FIPS 46-2 known-answer test (Appendix A.1): plaintext, key, expected ciphertext.
# Plaintext: 4E6F77206973207468652074696D65
# Key:       4B595F4E4F575F524F434B4552 (parity ignored)
# Expected:  3FA40E8A984D4815
# ---------------------------------------------------------------------------

FIPS_PT = bytes.fromhex("4E6F77206973207468652074696D65")
FIPS_KEY = bytes.fromhex("4B595F4E4F575F524F434B4552")
FIPS_CT = bytes.fromhex("3FA40E8A984D4815")


def _brute_force_4bit(pt: bytes, target_ct: bytes, key_bytes: int = 1) -> Tuple[bytes, float]:
    """Toy exhaustive search: try every key up to (2^(8*key_bytes)) until the
    DES encryption of `pt` matches `target_ct`."""
    if key_bytes < 1 or key_bytes > 3:
        raise ValueError("toy brute force uses 1-3 byte keys")
    n_keys = 1 << (8 * key_bytes)
    start = time.time()
    for k in range(n_keys):
        key = k.to_bytes(key_bytes, "big")
        if des_encrypt_block(pt, key) == target_ct:
            return key, time.time() - start
    return b"", time.time() - start


def main() -> None:
    os.makedirs("outputs", exist_ok=True)
    ct = des_encrypt_block(FIPS_PT, FIPS_KEY)
    print(f"Plaintext:  {FIPS_PT.hex()}")
    print(f"Key:        {FIPS_KEY.hex()}")
    print(f"Expected:   {FIPS_CT.hex()}")
    print(f"Got:        {ct.hex()}")
    assert ct == FIPS_CT, "DES FIPS 46-2 mismatch"

    # 3DES round-trip.
    k1, k2, k3 = b"\x01" * 8, b"\x02" * 8, b"\x03" * 8
    assert tdes_decrypt(tdes_encrypt(FIPS_PT, k1, k2, k3), k1, k2, k3) == FIPS_PT

    # Avalanche: flip one key bit, count bit differences across 64 random plaintexts.
    import random
    random.seed(42)
    diffs = []
    for _ in range(64):
        pt = bytes(random.randint(0, 255) for _ in range(8))
        c1 = des_encrypt_block(pt, FIPS_KEY)
        key2 = bytearray(FIPS_KEY)
        key2[0] ^= 0x01
        c2 = des_encrypt_block(pt, bytes(key2))
        diffs.append(sum(bin(a ^ b).count("1") for a, b in zip(c1, c2)))
    avg = sum(diffs) / len(diffs)
    print(f"\nKey avalanche: avg {avg:.1f} bit differences (expected ~32)")

    # Toy brute force: 1-byte key (256 candidates).
    pt = b"\x00" * 8
    target = des_encrypt_block(pt, b"\xA5")
    key, dt = _brute_force_4bit(pt, target, key_bytes=1)
    print(f"\nBrute force (1-byte key, 256 trials): recovered {key.hex()} in {dt*1000:.2f} ms")

    with open("outputs/des_known_answer.txt", "w") as f:
        f.write(f"Plaintext: {FIPS_PT.hex()}\n")
        f.write(f"Key:       {FIPS_KEY.hex()}\n")
        f.write(f"Expected:  {FIPS_CT.hex()}\n")
        f.write(f"Got:       {ct.hex()}\n")
    with open("outputs/des_avalanche.txt", "w") as f:
        f.write(f"Key avalanche: avg {avg:.1f} bit differences (out of 64)\n")
        f.write("Per-trial diffs: " + ",".join(str(d) for d in diffs) + "\n")
    with open("outputs/des_brute_force.txt", "w") as f:
        f.write(f"Toy DES brute force: 1-byte key (256 trials) in {dt*1000:.2f} ms\n")
        f.write(f"Recovered key: {key.hex()}\n")
    print("Wrote outputs/des_known_answer.txt, outputs/des_avalanche.txt, outputs/des_brute_force.txt")


if __name__ == "__main__":
    main()
