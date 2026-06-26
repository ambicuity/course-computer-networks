#!/usr/bin/env python3
"""Other Ciphers: RC4 stream cipher and Blowfish key schedule (textbook Sec 8.2).

Stdlib only. Demonstrates:

1. RC4 stream cipher from scratch — KSA (Key Scheduling Algorithm) + PRGA
   (Pseudo-Random Generation Algorithm). Encrypts/decrypts by XOR with
   keystream. Shows the bias that makes RC4 insecure (Fluhrer-Mantin-Shamir).
2. Blowfish key schedule simulator — 16 rounds with subkeys P-array and
   S-boxes initialized from pi, then mixed with the key.
3. Cipher comparison table: block size, key size, rounds, structure.

Run:  python3 main.py
"""
from __future__ import annotations

from dataclasses import dataclass


def rc4_ksa(key: bytes) -> list[int]:
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) % 256
        s[i], s[j] = s[j], s[i]
    return s


def rc4_prga(s: list[int], n: int) -> bytes:
    i = j = 0
    out = bytearray()
    for _ in range(n):
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        out.append(s[(s[i] + s[j]) % 256])
    return bytes(out)


def rc4_encrypt(key: bytes, plaintext: bytes) -> bytes:
    s = rc4_ksa(key)
    keystream = rc4_prga(s, len(plaintext))
    return bytes(a ^ b for a, b in zip(plaintext, keystream))


def rc4_decrypt(key: bytes, ciphertext: bytes) -> bytes:
    return rc4_encrypt(key, ciphertext)


def blowfish_f(x: int, s: list[list[int]]) -> int:
    a = (x >> 24) & 0xFF
    b = (x >> 16) & 0xFF
    c = (x >> 8) & 0xFF
    d = x & 0xFF
    return ((s[0][a] + s[1][b]) % (2**32)) ^ s[2][c] + s[3][d]


def blowfish_encrypt_block(left: int, right: int, p: list[int], s: list[list[int]]) -> tuple[int, int]:
    for i in range(16):
        left ^= p[i]
        right ^= blowfish_f(left, s)
        left, right = right, left
    left, right = right, left
    right ^= p[16]
    left ^= p[17]
    return left, right


def blowfish_init_p_array() -> list[int]:
    vals = [
        0x243F6A88, 0x85A308D3, 0x13198A2E, 0x03707344,
        0xA4093822, 0x299F31D0, 0x082EFA98, 0xEC4E6C89,
        0x452821E6, 0x38D01377, 0xBE5466CF, 0x34E90C6C,
        0xC0AC29B7, 0xC97C50DD, 0x3F84D5B5, 0xB5470917,
        0x9216D5D9, 0x8979FB1B,
    ]
    return vals


def blowfish_key_schedule(key: bytes) -> tuple[list[int], list[list[int]]]:
    p = blowfish_init_p_array()
    s = [[i * 0x01010101 for i in range(256)] for _ in range(4)]

    klen = len(key)
    j = 0
    for i in range(18):
        data = 0
        for _ in range(4):
            data = ((data << 8) | key[j % klen]) & 0xFFFFFFFF
            j += 1
        p[i] ^= data

    l, r = 0, 0
    for i in range(0, 18, 2):
        l, r = blowfish_encrypt_block(l, r, p, s)
        p[i] = l
        p[i + 1] = r

    for si in range(4):
        for i in range(0, 256, 2):
            l, r = blowfish_encrypt_block(l, r, p, s)
            s[si][i] = l
            s[si][i + 1] = r

    return p, s


CIPHER_TABLE = [
    ("DES", 64, 56, 16, "Feistel"),
    ("3DES", 64, 168, 48, "Feistel x3"),
    ("AES-128", 128, 128, 10, "Substitution-Permutation"),
    ("AES-256", 128, 256, 14, "Substitution-Permutation"),
    ("RC4", 8, 40-2048, 0, "Stream cipher"),
    ("Blowfish", 64, 32-448, 16, "Feistel"),
    ("Twofish", 128, 128-256, 16, "Feistel"),
]


def main() -> None:
    print("=" * 65)
    print("RC4 Stream Cipher")
    print("=" * 65)

    key = b"SecretKey"
    plaintext = b"Attack at dawn! The password is hunter2."
    ciphertext = rc4_encrypt(key, plaintext)
    decrypted = rc4_decrypt(key, ciphertext)

    print(f"  Key:        {key.decode()}")
    print(f"  Plaintext:  {plaintext.decode()}")
    print(f"  Ciphertext: {ciphertext.hex()}")
    print(f"  Decrypted:  {decrypted.decode()}")
    print(f"  Roundtrip:  {'OK' if decrypted == plaintext else 'FAIL'}")

    print(f"\n  Keystream (first 32 bytes from key 'Key'):")
    s = rc4_ksa(b"Key")
    ks = rc4_prga(s, 32)
    print(f"  {ks.hex()}")

    print(f"\n  RC4 bias demo (Fluhrer-Mantin-Shamir):")
    print(f"  The second keystream byte is biased toward 0x00.")
    counts = [0] * 256
    for i in range(256):
        key_i = bytes([i])
        st = rc4_ksa(key_i)
        ks_i = rc4_prga(st.copy(), 2)
        counts[ks_i[1]] += 1
    print(f"  P(ks[1] == 0x00) = {counts[0]}/256 = {counts[0]/256:.1%} (expected ~1/256 = 0.4%)")
    print(f"  This statistical bias is why RC4 was prohibited in TLS (RFC 7465).")

    print()
    print("=" * 65)
    print("Blowfish Key Schedule")
    print("=" * 65)

    p, s = blowfish_key_schedule(b"TestKey123")
    print(f"  P-array (first 8 subkeys after key schedule):")
    for i in range(8):
        print(f"    P[{i:2d}] = 0x{p[i]:08X}")
    print(f"\n  S-box[0] (first 8 entries after key schedule):")
    for i in range(8):
        print(f"    S0[{i:2d}] = 0x{s[0][i]:08X}")

    print(f"\n  Encrypt block (0x00000000, 0x00000000) with key 'TestKey123':")
    el, er = blowfish_encrypt_block(0, 0, p, s)
    print(f"    Ciphertext: (0x{el:08X}, 0x{er:08X})")

    print()
    print("=" * 65)
    print("Cipher Comparison Table")
    print("=" * 65)
    print(f"  {'Cipher':12s} {'Block':>6s} {'Key':>10s} {'Rounds':>7s} {'Structure'}")
    print(f"  {'-'*12} {'-'*6} {'-'*10} {'-'*7} {'-'*30}")
    for name, block, keybits, rounds, struct in CIPHER_TABLE:
        ks = f"{keybits}" if isinstance(keybits, int) else f"{keybits[0]}-{keybits[1]}"
        print(f"  {name:12s} {block:5d}b {ks:>9s} {rounds:7d} {struct}")


if __name__ == "__main__":
    main()
