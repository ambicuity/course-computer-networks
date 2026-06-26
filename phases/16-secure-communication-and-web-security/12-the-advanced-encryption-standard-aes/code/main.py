"""AES-128 (Rijndael) — stdlib Python reference implementation.

Implements the full FIPS 197 algorithm in 10 rounds, with key schedule,
SubBytes, ShiftRows, MixColumns, and AddRoundKey. The FIPS 197 Appendix B
known-answer test vector is checked at the end of main().

Run: python3 code/main.py
"""

from __future__ import annotations

import os
from typing import List, Tuple


# AES polynomial x^8 + x^4 + x^3 + x + 1 in GF(2^8)
AES_POLY = 0x11B


def _gf_degree(a: int) -> int:
    if a == 0:
        return -1
    return a.bit_length() - 1


def _gf_mul_no_mod(a: int, b: int) -> int:
    """Multiply two GF(2^8) elements with carry but no modulo."""
    result = 0
    while b:
        if b & 1:
            result ^= a
        a <<= 1
        b >>= 1
    return result


def gf_mod(a: int, poly: int) -> int:
    """Reduce `a` modulo `poly` in GF(2)."""
    while _gf_degree(a) >= _gf_degree(poly):
        a ^= poly << (_gf_degree(a) - _gf_degree(poly))
    return a


def gf_mul(a: int, b: int, poly: int = AES_POLY) -> int:
    return gf_mod(_gf_mul_no_mod(a, b), poly)


def gf_inverse(a: int) -> int:
    """Multiplicative inverse in GF(2^8) using extended Euclidean algorithm."""
    if a == 0:
        return 0
    # Find inverse via Fermat's little theorem: a^(2^8 - 2) in GF(2^8) is a^-1.
    result = 1
    base = a
    exp = 254  # 2^8 - 2
    while exp:
        if exp & 1:
            result = gf_mul(result, base)
        base = gf_mul(base, base)
        exp >>= 1
    return result


# ---------------------------------------------------------------------------
# S-box derivation from GF(2^8) inverse + affine transform.
# ---------------------------------------------------------------------------

def _affine(b: int) -> int:
    """AES affine transform: b' = M*b XOR 0x63, where bits are indexed LSB first."""
    M = [
        [1, 0, 0, 0, 1, 1, 1, 1],
        [1, 1, 0, 0, 0, 1, 1, 1],
        [1, 1, 1, 0, 0, 0, 1, 1],
        [1, 1, 1, 1, 0, 0, 0, 1],
        [1, 1, 1, 1, 1, 0, 0, 0],
        [0, 1, 1, 1, 1, 1, 0, 0],
        [0, 0, 1, 1, 1, 1, 1, 0],
        [0, 0, 0, 1, 1, 1, 1, 1],
    ]
    out = 0
    for r in range(8):
        bit = 0
        for c in range(8):
            bit ^= (M[r][c] * ((b >> c) & 1))
        out |= (bit << r)
    return out ^ 0x63


def _build_sbox() -> Tuple[List[int], List[int]]:
    sbox = [_affine(gf_inverse(x)) for x in range(256)]
    inv = [0] * 256
    for i, v in enumerate(sbox):
        inv[v] = i
    return sbox, inv


SBOX, INV_SBOX = _build_sbox()


# ---------------------------------------------------------------------------
# State manipulation. State is a 4x4 matrix of bytes (rows, columns).
# ---------------------------------------------------------------------------

def _state_from_bytes(block: bytes) -> List[List[int]]:
    if len(block) != 16:
        raise ValueError("AES block must be 16 bytes")
    state = [[0] * 4 for _ in range(4)]
    for c in range(4):
        for r in range(4):
            state[r][c] = block[c * 4 + r]
    return state


def _state_to_bytes(state: List[List[int]]) -> bytes:
    out = bytearray(16)
    for c in range(4):
        for r in range(4):
            out[c * 4 + r] = state[r][c]
    return bytes(out)


def sub_bytes(state: List[List[int]], inv: bool = False) -> None:
    table = INV_SBOX if inv else SBOX
    for r in range(4):
        for c in range(4):
            state[r][c] = table[state[r][c]]


def shift_rows(state: List[List[int]], inv: bool = False) -> None:
    for r in range(4):
        # Row r is rotated left by r (or right by r for inverse).
        shift = (-r) if inv else r
        state[r] = state[r][shift:] + state[r][:shift]


def mix_columns(state: List[List[int]], inv: bool = False) -> None:
    # MixColumns matrix: 0x02 0x03 0x01 0x01; inverse: 0x0e 0x0b 0x0d 0x09.
    mat = ([0x0E, 0x0B, 0x0D, 0x09], [0x09, 0x0E, 0x0B, 0x0D],
           [0x0D, 0x09, 0x0E, 0x0B], [0x0B, 0x0D, 0x09, 0x0E]) if inv else (
        [0x02, 0x03, 0x01, 0x01], [0x01, 0x02, 0x03, 0x01],
        [0x01, 0x01, 0x02, 0x03], [0x03, 0x01, 0x01, 0x02])
    for c in range(4):
        col = [state[r][c] for r in range(4)]
        for r in range(4):
            state[r][c] = gf_mul(mat[r][0], col[0]) ^ gf_mul(mat[r][1], col[1]) ^ \
                          gf_mul(mat[r][2], col[2]) ^ gf_mul(mat[r][3], col[3])


def add_round_key(state: List[List[int]], rk: List[int]) -> None:
    for c in range(4):
        for r in range(4):
            state[r][c] ^= rk[c * 4 + r]


# ---------------------------------------------------------------------------
# Key schedule: 11 round keys (44 32-bit words) for AES-128.
# ---------------------------------------------------------------------------

RCON = [0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


def key_expansion(key: bytes) -> List[List[int]]:
    if len(key) != 16:
        raise ValueError("AES-128 key must be 16 bytes")
    w = [0] * 44
    for i in range(4):
        w[i] = (key[4 * i] << 24) | (key[4 * i + 1] << 16) | \
               (key[4 * i + 2] << 8) | key[4 * i + 3]
    for i in range(4, 44):
        temp = w[i - 1]
        if i % 4 == 0:
            # RotWord + SubWord + Rcon
            temp = ((temp << 8) | (temp >> 24)) & 0xFFFFFFFF
            temp = (SBOX[(temp >> 24) & 0xFF] << 24) | \
                   (SBOX[(temp >> 16) & 0xFF] << 16) | \
                   (SBOX[(temp >> 8) & 0xFF] << 8) | \
                   (SBOX[temp & 0xFF])
            temp ^= (RCON[i // 4] << 24)
        w[i] = w[i - 4] ^ temp
    # Pack into 11 round keys of 16 bytes each.
    round_keys = []
    for rk_idx in range(11):
        words = w[rk_idx * 4:(rk_idx + 1) * 4]
        rk = bytearray(16)
        for j, word in enumerate(words):
            rk[4 * j] = (word >> 24) & 0xFF
            rk[4 * j + 1] = (word >> 16) & 0xFF
            rk[4 * j + 2] = (word >> 8) & 0xFF
            rk[4 * j + 3] = word & 0xFF
        round_keys.append(list(rk))
    return round_keys


# ---------------------------------------------------------------------------
# AES-128 block cipher.
# ---------------------------------------------------------------------------

def aes_encrypt_block(plaintext: bytes, key: bytes) -> bytes:
    round_keys = key_expansion(key)
    state = _state_from_bytes(plaintext)
    add_round_key(state, round_keys[0])
    for r in range(1, 10):
        sub_bytes(state)
        shift_rows(state)
        mix_columns(state)
        add_round_key(state, round_keys[r])
    sub_bytes(state)
    shift_rows(state)
    add_round_key(state, round_keys[10])
    return _state_to_bytes(state)


def aes_decrypt_block(ciphertext: bytes, key: bytes) -> bytes:
    round_keys = key_expansion(key)
    state = _state_from_bytes(ciphertext)
    add_round_key(state, round_keys[10])
    for r in range(9, 0, -1):
        shift_rows(state, inv=True)
        sub_bytes(state, inv=True)
        add_round_key(state, round_keys[r])
        mix_columns(state, inv=True)
    shift_rows(state, inv=True)
    sub_bytes(state, inv=True)
    add_round_key(state, round_keys[0])
    return _state_to_bytes(state)


# ---------------------------------------------------------------------------
# FIPS 197 test vectors.
# ---------------------------------------------------------------------------

FIPS_PT = bytes.fromhex("3243f6a8885a308d313198a2e0370734")
FIPS_KEY = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
FIPS_CT = bytes.fromhex("3925841d02dc09fbdc118597196a0b32")


def main() -> None:
    os.makedirs("outputs", exist_ok=True)

    # Sanity: the S-box must be 0x63 at index 0 and 0x7c at index 1.
    assert SBOX[0] == 0x63, "AES S-box[0] must be 0x63"
    assert SBOX[1] == 0x7C, "AES S-box[1] must be 0x7c"

    # Encrypt the FIPS 197 test vector.
    ct = aes_encrypt_block(FIPS_PT, FIPS_KEY)
    print(f"Plaintext:  {FIPS_PT.hex()}")
    print(f"Key:        {FIPS_KEY.hex()}")
    print(f"Expected:   {FIPS_CT.hex()}")
    print(f"Got:        {ct.hex()}")
    assert ct == FIPS_CT, f"AES-128 FIPS 197 mismatch (got {ct.hex()})"

    # Decrypt the FIPS 197 test vector.
    pt = aes_decrypt_block(FIPS_CT, FIPS_KEY)
    assert pt == FIPS_PT, f"AES-128 decrypt mismatch (got {pt.hex()})"

    # Strict avalanche test: flip one bit of a random plaintext and report
    # the average bit-difference in the ciphertext.
    import random
    random.seed(0x1234_5678)
    diffs = []
    for _ in range(64):
        pt = bytes(random.randint(0, 255) for _ in range(16))
        key = bytes(random.randint(0, 255) for _ in range(16))
        c1 = aes_encrypt_block(pt, key)
        c2 = aes_encrypt_block(bytes(b ^ 1 for b in pt), key)
        # Flip the LSB of byte 0.
        bit_diff = sum(bin(a ^ b).count("1") for a, b in zip(c1, c2))
        diffs.append(bit_diff)
    avg = sum(diffs) / len(diffs)
    print(f"\nStrict avalanche: avg {avg:.1f} bit differences "
          f"(expected ~64, max 128) over {len(diffs)} trials")

    with open("outputs/aes_known_answer.txt", "w") as f:
        f.write(f"Plaintext: {FIPS_PT.hex()}\n")
        f.write(f"Key:       {FIPS_KEY.hex()}\n")
        f.write(f"Expected:  {FIPS_CT.hex()}\n")
        f.write(f"Got:       {ct.hex()}\n")
        f.write(f"Match:     {ct == FIPS_CT}\n")
    with open("outputs/aes_state_trace.txt", "w") as f:
        # Recompute a round trace for the FIPS vector.
        round_keys = key_expansion(FIPS_KEY)
        state = _state_from_bytes(FIPS_PT)
        f.write(f"After AddRoundKey rk[0]: {_state_to_bytes(state).hex()}\n")
        for r in range(1, 11):
            sub_bytes(state)
            shift_rows(state)
            if r < 10:
                mix_columns(state)
            add_round_key(state, round_keys[r])
            f.write(f"After round {r:2d}:       {_state_to_bytes(state).hex()}\n")
    print("Wrote outputs/aes_known_answer.txt, outputs/aes_state_trace.txt")


if __name__ == "__main__":
    main()
