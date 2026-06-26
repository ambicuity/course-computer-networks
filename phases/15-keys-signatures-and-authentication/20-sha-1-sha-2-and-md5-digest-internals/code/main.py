#!/usr/bin/env python3
"""Pure-Python SHA-256 implementation using only the stdlib.

Implements:
  * FIPS 180-4 SHA-256 padding (append 0x80, zero-fill to 56 mod 64, 64-bit big-endian length)
  * Message schedule expansion (16 input words -> 64 via sigma0/sigma1)
  * 64-round compression with Ch, Maj, SIGMA0, SIGMA1, feed-forward add
  * Full digest: sha256(msg) -> 64-char hex string
  * Comparison against hashlib.sha256 to prove correctness
  * Padded-block layout and W[0..19] trace for b"abc"

Run with `python3 main.py`.
"""

from __future__ import annotations

import hashlib
import struct
from typing import List

K: List[int] = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
    0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
    0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
    0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
    0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7,
    0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
    0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
    0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
    0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3,
    0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
    0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5,
    0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
    0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
    0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
]

H0: List[int] = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
]


def rotr(x: int, n: int) -> int:
    return ((x >> n) | (x << (32 - n))) & 0xFFFFFFFF


def sha256_pad(msg: bytes) -> bytes:
    length_bits = len(msg) * 8
    msg = msg + b'\x80'
    while len(msg) % 64 != 56:
        msg += b'\x00'
    return msg + length_bits.to_bytes(8, 'big')


def sha256_compress(state: List[int], block: bytes) -> List[int]:
    W = list(struct.unpack('>16I', block))
    for i in range(16, 64):
        s0 = rotr(W[i - 15], 7) ^ rotr(W[i - 15], 18) ^ (W[i - 15] >> 3)
        s1 = rotr(W[i - 2], 17) ^ rotr(W[i - 2], 19) ^ (W[i - 2] >> 10)
        W.append((W[i - 16] + s0 + W[i - 7] + s1) & 0xFFFFFFFF)
    a, b, c, d, e, f, g, h = state
    for i in range(64):
        S1 = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)
        ch = (e & f) ^ (~e & g)
        T1 = (h + S1 + ch + K[i] + W[i]) & 0xFFFFFFFF
        S0 = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)
        maj = (a & b) ^ (a & c) ^ (b & c)
        T2 = (S0 + maj) & 0xFFFFFFFF
        h, g, f = g, f, e
        e = (d + T1) & 0xFFFFFFFF
        d, c, b = c, b, a
        a = (T1 + T2) & 0xFFFFFFFF
    return [(x + y) & 0xFFFFFFFF for x, y in zip(state, [a, b, c, d, e, f, g, h])]


def sha256(msg: bytes) -> str:
    padded = sha256_pad(msg)
    state = H0[:]
    for i in range(0, len(padded), 64):
        state = sha256_compress(state, padded[i:i + 64])
    return ''.join(f'{x:08x}' for x in state)


def main() -> None:
    print("=== SHA-256 from scratch vs hashlib ===")
    test_inputs = [
        b"abc",
        b"",
        b"The quick brown fox jumps over the lazy dog",
    ]
    all_ok = True
    for msg in test_inputs:
        ours = sha256(msg)
        ref = hashlib.sha256(msg).hexdigest()
        ok = ours == ref
        all_ok = all_ok and ok
        status = "OK  " if ok else "FAIL"
        label = repr(msg[:40])
        print(f"  {status}  {label:<45}  {ours}")
    print(f"\n  All match hashlib: {all_ok}")

    print("\n=== Padded block layout for b'abc' (64 bytes = 1 block) ===")
    padded = sha256_pad(b"abc")
    print(f"  Total padded length: {len(padded)} bytes")
    print(f"  Bytes  0-31:  {padded[:32].hex(' ')}")
    print(f"  Bytes 32-63:  {padded[32:64].hex(' ')}")
    print(f"  Length field (last 8): {padded[-8:].hex()} = {int.from_bytes(padded[-8:], 'big')} bits")

    print("\n=== Message schedule W[0..19] for b'abc' ===")
    W = list(struct.unpack('>16I', padded[:64]))
    for i in range(16, 20):
        s0 = rotr(W[i - 15], 7) ^ rotr(W[i - 15], 18) ^ (W[i - 15] >> 3)
        s1 = rotr(W[i - 2], 17) ^ rotr(W[i - 2], 19) ^ (W[i - 2] >> 10)
        W.append((W[i - 16] + s0 + W[i - 7] + s1) & 0xFFFFFFFF)
    print(f"  {'i':>3}  {'W[i]':>10}  source")
    for i in range(20):
        src = "from block" if i < 16 else "derived   "
        print(f"  {i:>3}  {W[i]:08x}   {src}")

    print("\n=== Round-trip verification vs hashlib for multiple inputs ===")
    extra = [b"a" * 55, b"a" * 64, b"a" * 128]
    for msg in extra:
        ours = sha256(msg)
        ref = hashlib.sha256(msg).hexdigest()
        ok = ours == ref
        label = f"b'a' * {len(msg)}"
        print(f"  {'OK  ' if ok else 'FAIL'}  {label:<20}  {ours}")
    print(f"\n  All verification tests passed: {all_ok}")


if __name__ == "__main__":
    main()
