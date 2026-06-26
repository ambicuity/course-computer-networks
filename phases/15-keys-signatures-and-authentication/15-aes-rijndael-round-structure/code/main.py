#!/usr/bin/env python3
"""Pure-Python AES-128 (Rijndael) implementation per FIPS 197.

Implements, with stdlib only:

  * SubBytes / InvSubBytes via the FIPS 197 S-box
  * ShiftRows / InvShiftRows
  * MixColumns / InvMixColumns over GF(2^8) with polynomial 0x11B
  * AES-128 key schedule producing 11 round keys
  * Single-block encrypt / decrypt (ECB)
  * FIPS 197 Known Answer Test (Appendix C.1)

Run with `python3 main.py`.
"""

from __future__ import annotations

from typing import List

_SBOX_BASE = [
    0x63, 0x7C, 0x77, 0x7B, 0xF2, 0x6B, 0x6F, 0xC5, 0x30, 0x01, 0x67, 0x2B, 0xFE, 0xD7, 0xAB, 0x76,
    0xCA, 0x82, 0xC9, 0x7D, 0xFA, 0x59, 0x47, 0xF0, 0xAD, 0xD4, 0xA2, 0xAF, 0x9C, 0xA4, 0x72, 0xC0,
    0xB7, 0xFD, 0x93, 0x26, 0x36, 0x3F, 0xF7, 0xCC, 0x34, 0xA5, 0xE5, 0xF1, 0x71, 0xD8, 0x31, 0x15,
    0x04, 0xC7, 0x23, 0xC3, 0x18, 0x96, 0x05, 0x9A, 0x07, 0x12, 0x80, 0xE2, 0xEB, 0x27, 0xB2, 0x75,
    0x09, 0x83, 0x2C, 0x1A, 0x1B, 0x6E, 0x5A, 0xA0, 0x52, 0x3B, 0xD6, 0xB3, 0x29, 0xE3, 0x2F, 0x84,
    0x53, 0xD1, 0x00, 0xED, 0x20, 0xFC, 0xB1, 0x5B, 0x6A, 0xCB, 0xBE, 0x39, 0x4A, 0x4C, 0x58, 0xCF,
    0xD0, 0xEF, 0xAA, 0xFB, 0x43, 0x4D, 0x33, 0x85, 0x45, 0xF9, 0x02, 0x7F, 0x50, 0x3C, 0x9F, 0xA8,
    0x51, 0xA3, 0x40, 0x8F, 0x92, 0x9D, 0x38, 0xF5, 0xBC, 0xB6, 0xDA, 0x21, 0x10, 0xFF, 0xF3, 0xD2,
    0xCD, 0x0C, 0x13, 0xEC, 0x5F, 0x97, 0x44, 0x17, 0xC4, 0xA7, 0x7E, 0x3D, 0x64, 0x5D, 0x19, 0x73,
    0x60, 0x81, 0x4F, 0xDC, 0x22, 0x2A, 0x90, 0x88, 0x46, 0xEE, 0xB8, 0x14, 0xDE, 0x5E, 0x0B, 0xDB,
    0xE0, 0x32, 0x3A, 0x0A, 0x49, 0x06, 0x24, 0x5C, 0xC2, 0xD3, 0xAC, 0x62, 0x91, 0x95, 0xE4, 0x79,
    0xE7, 0xC8, 0x37, 0x6D, 0x8D, 0xD5, 0x4E, 0xA9, 0x6C, 0x56, 0xF4, 0xEA, 0x65, 0x7A, 0xAE, 0x08,
    0xBA, 0x78, 0x25, 0x2E, 0x1C, 0xA6, 0xB4, 0xC6, 0xE8, 0xDD, 0x74, 0x1F, 0x4B, 0xBD, 0x8B, 0x8A,
    0x70, 0x3E, 0xB5, 0x66, 0x48, 0x03, 0xF6, 0x0E, 0x61, 0x35, 0x57, 0xB9, 0x86, 0xC1, 0x1D, 0x9E,
    0xE1, 0xF8, 0x98, 0x11, 0x69, 0xD9, 0x8E, 0x94, 0x9B, 0x1E, 0x87, 0xE9, 0xCE, 0x55, 0x28, 0xDF,
    0x8C, 0xA1, 0x89, 0x0D, 0xBF, 0xE6, 0x42, 0x68, 0x41, 0x99, 0x2D, 0x0F, 0xB0, 0x54, 0xBB, 0x16,
]

SBOX: List[int] = list(_SBOX_BASE)
INV_SBOX: List[int] = [0] * 256
for i, v in enumerate(_SBOX_BASE):
    INV_SBOX[v] = i

RCON = [0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1B, 0x36]


def _state_from_block(block: bytes) -> List[List[int]]:
    state = [[0] * 4 for _ in range(4)]
    for c in range(4):
        for r in range(4):
            state[r][c] = block[4 * c + r]
    return state


def _state_to_block(state: List[List[int]]) -> bytes:
    out = bytearray(16)
    for c in range(4):
        for r in range(4):
            out[4 * c + r] = state[r][c]
    return bytes(out)


def _xor_state(state: List[List[int]], key_bytes: bytes) -> None:
    for r in range(4):
        for c in range(4):
            state[r][c] ^= key_bytes[4 * c + r]


def sub_bytes(state: List[List[int]]) -> None:
    for r in range(4):
        for c in range(4):
            state[r][c] = SBOX[state[r][c]]


def inv_sub_bytes(state: List[List[int]]) -> None:
    for r in range(4):
        for c in range(4):
            state[r][c] = INV_SBOX[state[r][c]]


def shift_rows(state: List[List[int]]) -> None:
    state[1] = state[1][1:] + state[1][:1]
    state[2] = state[2][2:] + state[2][:2]
    state[3] = state[3][3:] + state[3][:3]


def inv_shift_rows(state: List[List[int]]) -> None:
    state[1] = state[1][-1:] + state[1][:-1]
    state[2] = state[2][-2:] + state[2][:-2]
    state[3] = state[3][-3:] + state[3][:-3]


def _xtime(b: int) -> int:
    return ((b << 1) ^ 0x1B) & 0xFF if b & 0x80 else (b << 1) & 0xFF


def _gf_mul(a: int, b: int) -> int:
    r = 0
    for _ in range(8):
        if b & 1:
            r ^= a
        a = _xtime(a)
        b >>= 1
    return r


def mix_columns(state: List[List[int]]) -> None:
    for c in range(4):
        a0, a1, a2, a3 = state[0][c], state[1][c], state[2][c], state[3][c]
        state[0][c] = _gf_mul(2, a0) ^ _gf_mul(3, a1) ^ a2 ^ a3
        state[1][c] = a0 ^ _gf_mul(2, a1) ^ _gf_mul(3, a2) ^ a3
        state[2][c] = a0 ^ a1 ^ _gf_mul(2, a2) ^ _gf_mul(3, a3)
        state[3][c] = _gf_mul(3, a0) ^ a1 ^ a2 ^ _gf_mul(2, a3)


def inv_mix_columns(state: List[List[int]]) -> None:
    for c in range(4):
        a0, a1, a2, a3 = state[0][c], state[1][c], state[2][c], state[3][c]
        state[0][c] = _gf_mul(0x0E, a0) ^ _gf_mul(0x0B, a1) ^ _gf_mul(0x0D, a2) ^ _gf_mul(0x09, a3)
        state[1][c] = _gf_mul(0x09, a0) ^ _gf_mul(0x0E, a1) ^ _gf_mul(0x0B, a2) ^ _gf_mul(0x0D, a3)
        state[2][c] = _gf_mul(0x0D, a0) ^ _gf_mul(0x09, a1) ^ _gf_mul(0x0E, a2) ^ _gf_mul(0x0B, a3)
        state[3][c] = _gf_mul(0x0B, a0) ^ _gf_mul(0x0D, a1) ^ _gf_mul(0x09, a2) ^ _gf_mul(0x0E, a3)


def key_schedule_128(key: bytes) -> List[bytes]:
    if len(key) != 16:
        raise ValueError("AES-128 requires a 16-byte key")
    schedule = [key]
    for i in range(1, 11):
        prev = bytearray(schedule[-1])
        rot = bytes([prev[13], prev[14], prev[15], prev[12]])
        sub = bytes([SBOX[b] for b in rot])
        first = bytes([
            sub[0] ^ RCON[i],
            sub[1],
            sub[2],
            sub[3],
        ])
        new = bytearray(16)
        for j in range(4):
            new[j] = prev[j] ^ first[j]
        for j in range(4, 16):
            new[j] = prev[j] ^ new[j - 4]
        schedule.append(bytes(new))
    return schedule


def aes_encrypt_block(block: bytes, key: bytes) -> bytes:
    if len(block) != 16:
        raise ValueError("block must be 16 bytes")
    schedule = key_schedule_128(key)
    state = _state_from_block(block)
    _xor_state(state, schedule[0])
    for r in range(1, 11):
        sub_bytes(state)
        shift_rows(state)
        if r < 10:
            mix_columns(state)
        _xor_state(state, schedule[r])
    return _state_to_block(state)


def aes_decrypt_block(block: bytes, key: bytes) -> bytes:
    if len(block) != 16:
        raise ValueError("block must be 16 bytes")
    schedule = key_schedule_128(key)[::-1]
    state = _state_from_block(block)
    _xor_state(state, schedule[0])
    for r in range(1, 11):
        inv_shift_rows(state)
        inv_sub_bytes(state)
        _xor_state(state, schedule[r])
        if r < 10:
            inv_mix_columns(state)
    return _state_to_block(state)


def fips_kat() -> bool:
    """FIPS 197 Appendix C.1 AES-128 KAT.

    Plaintext 0x00112233445566778899aabbccddeeff,
    Key       0x000102030405060708090a0b0c0d0e0f,
    Expected  0x69c4e0d86a7b0430d8cdb78070b4c55a.
    """
    pt = bytes.fromhex("00112233445566778899aabbccddeeff")
    key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    expected = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
    actual = aes_encrypt_block(pt, key)
    return actual == expected and aes_decrypt_block(actual, key) == pt


def demo_round_trace() -> None:
    pt = bytes.fromhex("00112233445566778899aabbccddeeff")
    key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
    schedule = key_schedule_128(key)
    state = _state_from_block(pt)
    _xor_state(state, schedule[0])
    print("Pre-round state:")
    _print_state(state)
    for r in range(1, 11):
        sub_bytes(state)
        shift_rows(state)
        if r < 10:
            mix_columns(state)
        _xor_state(state, schedule[r])
        print(f"After round {r}:")
        _print_state(state)


def _print_state(state: List[List[int]]) -> None:
    for r in range(4):
        print("  " + " ".join(f"{state[r][c]:02x}" for c in range(4)))


def main() -> None:
    print("=== FIPS 197 AES-128 Known Answer Test ===")
    print("  PASS" if fips_kat() else "  FAIL")
    print("\n=== Round trace ===")
    demo_round_trace()
    print("\n=== Round-trip a 32-byte block ===")
    key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
    pt = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")
    ct = aes_encrypt_block(pt, key)
    print(f"  ct = {ct.hex()}")
    print(f"  rt = {aes_decrypt_block(ct, key).hex()}")
    print(f"  match: {aes_decrypt_block(ct, key) == pt}")


if __name__ == "__main__":
    main()