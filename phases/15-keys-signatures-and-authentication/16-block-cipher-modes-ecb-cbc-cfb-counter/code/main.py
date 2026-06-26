#!/usr/bin/env python3
"""Block cipher modes of operation lab.

Implements, with stdlib only (and AES-128 from lesson 15):

  * ECB, CBC, CFB-8, OFB, CTR modes for an arbitrary block cipher
  * CBC bit-flipping attack
  * CTR nonce-reuse attack demo
  * ECB "penguin" demo (canonical Tux silhouette leak)

Run with `python3 main.py`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Callable, List

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "15-aes-rijndael-round-structure" / "code"))
from main import aes_encrypt_block, aes_decrypt_block  # noqa: E402

AES_BLOCK = 16


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def aes_ecb(plaintext: bytes, key: bytes) -> bytes:
    if len(plaintext) % AES_BLOCK != 0:
        raise ValueError("plaintext must be a multiple of 16 bytes")
    out = bytearray()
    for i in range(0, len(plaintext), AES_BLOCK):
        out.extend(aes_encrypt_block(plaintext[i:i + AES_BLOCK], key))
    return bytes(out)


def aes_ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    out = bytearray()
    for i in range(0, len(ciphertext), AES_BLOCK):
        out.extend(aes_decrypt_block(ciphertext[i:i + AES_BLOCK], key))
    return bytes(out)


def aes_cbc(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    if len(plaintext) % AES_BLOCK != 0:
        raise ValueError("plaintext must be a multiple of 16 bytes")
    prev = iv
    out = bytearray()
    for i in range(0, len(plaintext), AES_BLOCK):
        block = plaintext[i:i + AES_BLOCK]
        mixed = _xor(block, prev)
        enc = aes_encrypt_block(mixed, key)
        out.extend(enc)
        prev = enc
    return bytes(out)


def aes_cbc_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    prev = iv
    out = bytearray()
    for i in range(0, len(ciphertext), AES_BLOCK):
        block = ciphertext[i:i + AES_BLOCK]
        dec = aes_decrypt_block(block, key)
        out.extend(_xor(dec, prev))
        prev = block
    return bytes(out)


def aes_cfb8(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    shift = bytearray(iv)
    out = bytearray()
    for byte in plaintext:
        o = aes_encrypt_block(bytes(shift), key)
        c = byte ^ o[0]
        out.append(c)
        shift = shift[1:] + bytearray([c])
    return bytes(out)


def aes_cfb8_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    shift = bytearray(iv)
    out = bytearray()
    for byte in ciphertext:
        o = aes_encrypt_block(bytes(shift), key)
        p = byte ^ o[0]
        out.append(p)
        shift = shift[1:] + bytearray([byte])
    return bytes(out)


def aes_ofb(plaintext: bytes, key: bytes, iv: bytes) -> bytes:
    out = bytearray()
    counter = bytearray(iv)
    for i in range(0, len(plaintext), AES_BLOCK):
        counter = bytearray(aes_encrypt_block(bytes(counter), key))
        chunk = plaintext[i:i + AES_BLOCK]
        out.extend(_xor(chunk, bytes(counter[:len(chunk)])))
    return bytes(out)


def aes_ofb_decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
    return aes_ofb(ciphertext, key, iv)


def aes_ctr(plaintext: bytes, key: bytes, nonce: bytes, counter_start: int = 1) -> bytes:
    if len(nonce) != 12:
        raise ValueError("nonce must be 12 bytes (RFC 5116)")
    out = bytearray()
    counter = counter_start
    for i in range(0, len(plaintext), AES_BLOCK):
        block = counter_block(nonce, counter)
        ks = aes_encrypt_block(block, key)
        chunk = plaintext[i:i + AES_BLOCK]
        out.extend(_xor(chunk, ks[:len(chunk)]))
        counter += 1
    return bytes(out)


def aes_ctr_decrypt(ciphertext: bytes, key: bytes, nonce: bytes, counter_start: int = 1) -> bytes:
    return aes_ctr(ciphertext, key, nonce, counter_start)


def counter_block(nonce: bytes, counter: int) -> bytes:
    return nonce + counter.to_bytes(4, "big")


def cbc_bit_flip(ct: bytes, key: bytes, iv: bytes, target_block: int, delta: int) -> bytes:
    """XOR `delta` into ciphertext block (target_block - 1) so plaintext
    block `target_block` has its first byte flipped by `delta`.
    """
    if target_block <= 0:
        raise ValueError("target_block must be >= 1")
    out = bytearray(ct)
    idx = (target_block - 1) * AES_BLOCK
    out[idx] ^= delta
    return bytes(out)


def ctr_nonce_reuse_demo() -> None:
    key = b"\x42" * 16
    nonce = b"\x00" * 12
    p1 = b"transfer $100 to Alice    "
    p2 = b"transfer $999 to Mallory  "
    c1 = aes_ctr(p1, key, nonce)
    c2 = aes_ctr(p2, key, nonce)
    xor_plain = bytes(a ^ b for a, b in zip(p1, p2))
    xor_cipher = bytes(a ^ b for a, b in zip(c1, c2))
    print("  p1 XOR p2 == c1 XOR c2 ?", xor_plain == xor_cipher)


def ecb_penguin_demo() -> None:
    """Encrypt a 16-block 'image' in ECB and CBC; show ECB keeps structure.

    The image is a 16x16 grid where rows of 'A's form a shape. ECB
    encryption leaves the shape visible in the ciphertext because identical
    plaintext rows map to identical ciphertext rows.
    """
    shape = (
        "................"
        "................"
        "..AA........AA.."
        "...A........A..."
        "...A..AAAA..A..."
        "...A..A..A..A..."
        "...A..AAAA..A..."
        "...A........A..."
        "..AA........AA.."
        "................"
        "..BBBBBBBBBBBB.."
        "..B..........B.."
        "..B..........B.."
        "..B..........B.."
        "..BBBBBBBBBBBB.."
        "................"
    )
    plain = ("".join(shape) * 4).encode()  # repeat to 16-block bytes
    key = b"\x37" * 16
    ct = aes_ecb(plain, key)
    print("  Plain row 2:  ", plain[32:48].hex())
    print("  ECB  row 2:   ", ct[32:48].hex())
    print("  ECB  row 10:  ", ct[160:176].hex())
    print("  -> Identical plaintext rows => identical ciphertext rows in ECB")


def demo() -> None:
    key = b"\x13" * 16
    iv = b"\x57" * 16
    nonce = b"\xab" * 12
    pt = b"The quick brown fox jumps over the lazy dog!!!"
    pt = pt + b" " * ((AES_BLOCK - len(pt) % AES_BLOCK) % AES_BLOCK)

    print("=== Round-trip each mode on a multi-block message ===")
    for name, enc, dec in (
        ("ECB", aes_ecb, aes_ecb_decrypt),
        ("CBC", aes_cbc, aes_cbc_decrypt),
        ("CFB-8", aes_cfb8, aes_cfb8_decrypt),
        ("OFB", aes_ofb, aes_ofb_decrypt),
        ("CTR", lambda p, k, iv: aes_ctr(p, k, nonce), lambda c, k, iv: aes_ctr_decrypt(c, k, nonce)),
    ):
        if name == "ECB":
            ct = enc(pt, key)
        else:
            ct = enc(pt, key, iv)
        if name == "ECB":
            rt = dec(ct, key)
        else:
            rt = dec(ct, key, iv)
        print(f"  {name:6s} round-trip: {rt == pt}")

    print("\n=== CBC bit-flipping ===")
    pt2 = b"amount=0000;user=alic"
    pt2 = pt2 + b"e" * ((16 - len(pt2) % 16) % 16)
    key2 = b"\x99" * 16
    iv2 = b"\x42" * 16
    ct = aes_cbc(pt2, key2, iv2)
    modified = cbc_bit_flip(ct, key2, iv2, target_block=1, delta=ord("a") ^ ord("9"))
    rt = aes_cbc_decrypt(modified, key2, iv2)
    print(f"  original: {pt2!r}")
    print(f"  modified plaintext block 1: {rt[16:32]!r}")

    print("\n=== CTR nonce reuse ===")
    ctr_nonce_reuse_demo()

    print("\n=== ECB penguin demo ===")
    ecb_penguin_demo()


def main() -> None:
    demo()


if __name__ == "__main__":
    main()