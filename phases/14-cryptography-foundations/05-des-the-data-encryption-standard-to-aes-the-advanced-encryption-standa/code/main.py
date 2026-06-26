#!/usr/bin/env python3
"""DES to AES - simplified Feistel cipher and AES-like SPN round.

Implements a toy 4-round Feistel cipher (8-bit blocks, 4-bit halves) to
illustrate the DES round structure, and a simplified AES-like
Substitution-Permutation Network round (2x2 byte state) to illustrate
SubBytes, ShiftRows, and AddRoundKey. Not real DES or AES; educational
only. No external dependencies; runs under plain python3.
"""

from __future__ import annotations

import os

# Toy S-box for the Feistel f-function (4-bit -> 4-bit, arbitrary nonlinearity).
FEISTEL_SBOX: list[int] = [0xE, 0x4, 0xD, 0x1, 0x2, 0xF, 0xB, 0x8,
                           0x3, 0xA, 0x6, 0xC, 0x5, 0x9, 0x0, 0x7]

# Toy S-box for the AES-like SPN (8-bit -> 8-bit, small for demo).
SPN_SBOX: list[int] = [
    0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5, 0x30, 0x01, 0x67, 0x2B,
    0xFE, 0xD7, 0xAB, 0x76, 0xCA, 0x82, 0xC9, 0x7D, 0xFA, 0x59, 0x47, 0xF0,
    0xAD, 0xD4, 0xA2, 0xAF, 0x9C, 0xA4, 0x72, 0xC0,
]


def feistel_f(r: int, subkey: int) -> int:
    """Toy f function: expand, XOR subkey, S-box substitute, permute."""
    # Expand 4-bit r to 6 bits by duplicating middle bits (toy expansion).
    expanded: int = ((r & 0b1000) << 2) | ((r & 0b0110) << 1) | (r & 0b0111)
    xored: int = expanded ^ (subkey & 0x3F)
    s_in: int = (xored >> 2) & 0xF  # take 4 bits for toy S-box
    return FEISTEL_SBOX[s_in] ^ ((xored & 0x3) << 2)


def feistel_encrypt(block: int, key: int, rounds: int = 4) -> int:
    """Encrypt an 8-bit block with a toy 4-round Feistel cipher."""
    left: int = (block >> 4) & 0xF
    right: int = block & 0xF
    for i in range(rounds):
        subkey: int = (key >> (i * 2)) & 0xF
        new_left: int = right
        new_right: int = left ^ feistel_f(right, subkey)
        left, right = new_left, new_right
    return (left << 4) | right


def feistel_decrypt(block: int, key: int, rounds: int = 4) -> int:
    """Decrypt by running rounds in reverse (Feistel property)."""
    left: int = (block >> 4) & 0xF
    right: int = block & 0xF
    for i in range(rounds - 1, -1, -1):
        subkey: int = (key >> (i * 2)) & 0xF
        new_right: int = left
        new_left: int = right ^ feistel_f(left, subkey)
        left, right = new_left, new_right
    return (left << 4) | right


def spn_sub_bytes(state: list[list[int]]) -> list[list[int]]:
    """AES-like SubBytes: apply S-box to each byte of the 2x2 state."""
    return [[SPN_SBOX[state[r][c] % len(SPN_SBOX)] for c in range(len(state[0]))]
            for r in range(len(state))]


def spn_shift_rows(state: list[list[int]]) -> list[list[int]]:
    """AES-like ShiftRows: rotate row i left by i bytes (2x2 state)."""
    return [state[0], [state[1][1], state[1][0]]]


def spn_add_round_key(state: list[list[int]], round_key: list[list[int]]) -> list[list[int]]:
    """AES-like AddRoundKey: XOR each byte with the round key."""
    return [[state[r][c] ^ round_key[r][c] for c in range(len(state[0]))]
            for r in range(len(state))]


def state_to_hex(state: list[list[int]]) -> str:
    """Render a 2x2 state as a hex string."""
    return "".join(f"{state[r][c]:02x}" for r in range(len(state)) for c in range(len(state[0])))


def demo_feistel() -> None:
    print("=== Toy Feistel Cipher (DES-like, 8-bit blocks, 4 rounds) ===")
    key: int = 0xB7  # toy key
    for pt in (0x12, 0x34, 0xAB, 0xCD):
        ct: int = feistel_encrypt(pt, key)
        pt_back: int = feistel_decrypt(ct, key)
        print(f"  PT={pt:02x} -> CT={ct:02x} -> DT={pt_back:02x}  "
              f"{'OK' if pt_back == pt else 'FAIL'}")
    print("  L_i = R_{i-1}; R_i = L_{i-1} XOR f(R_{i-1}, K_i)")
    print("  Decryption = same algorithm, rounds reversed (Feistel property).\n")


def demo_spn() -> None:
    print("=== Toy AES-like SPN Round (2x2 state, SubBytes+ShiftRows+AddRoundKey) ===")
    state: list[list[int]] = [[0x01, 0x02], [0x03, 0x04]]
    round_key: list[list[int]] = [[0xA0, 0xB0], [0xC0, 0xD0]]
    print(f"  Initial state:  {state_to_hex(state)}")
    s1: list[list[int]] = spn_sub_bytes(state)
    print(f"  After SubBytes: {state_to_hex(s1)}")
    s2: list[list[int]] = spn_shift_rows(s1)
    print(f"  After ShiftRows: {state_to_hex(s2)}")
    s3: list[list[int]] = spn_add_round_key(s2, round_key)
    print(f"  After AddRoundKey: {state_to_hex(s3)}")
    print("  (Real AES also has MixColumns: GF(2^8) matrix multiply per column)\n")


def demo_key_space() -> None:
    print("=== Key Space Comparison ===")
    ciphers: list[tuple[str, int]] = [
        ("DES (56-bit)", 56), ("3DES (112-bit)", 112),
        ("AES-128", 128), ("AES-256", 256),
    ]
    rate: int = 10**9  # keys per second
    for name, bits in ciphers:
        space: int = 2 ** bits
        seconds: float = space / rate
        years: float = seconds / (365.25 * 86400)
        if years < 1:
            time_str: str = f"{seconds:.1f} s"
        elif years < 10**6:
            time_str = f"{years:.1f} years"
        else:
            time_str = f"{years:.2e} years"
        print(f"  {name:<18} 2^{bits} = {space:.3e}  brute-force @ 1ns: {time_str}")


def main() -> None:
    print("Lesson: DES to AES\n")
    demo_feistel()
    demo_spn()
    demo_key_space()
    print("\nDES: 64-bit block, 56-bit key, 16 Feistel rounds, 8 S-boxes -> broken.")
    print("AES: 128-bit block, 128/192/256-bit key, 10/12/14 SPN rounds, 1 S-box -> standard.")


if __name__ == "__main__":
    main()