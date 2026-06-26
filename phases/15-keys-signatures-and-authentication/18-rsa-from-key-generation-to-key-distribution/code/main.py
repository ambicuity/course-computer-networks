#!/usr/bin/env python3
"""Pure-Python textbook RSA and session-key distribution.

Implements, with stdlib only:

  * Miller-Rabin primality testing
  * Random prime generation
  * Extended Euclidean algorithm and modular inverse
  * RSA key generation (default 2048-bit)
  * Textbook RSA encrypt / decrypt (chapter's SUZANNE example verified)
  * RSA-OAEP-style padding for IND-CPA security
  * RSA session-key distribution (TLS 1.2 RSA key transport model)

Run with `python3 main.py`.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from typing import Tuple


def egcd(a: int, b: int) -> Tuple[int, int, int]:
    if b == 0:
        return a, 1, 0
    g, x, y = egcd(b, a % b)
    return g, y, x - (a // b) * y


def modinv(a: int, m: int) -> int:
    g, x, _ = egcd(a % m, m)
    if g != 1:
        raise ValueError("no modular inverse")
    return x % m


def is_probable_prime(n: int, k: int = 40) -> bool:
    if n < 2:
        return False
    small_primes = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    for p in small_primes:
        if n == p:
            return True
        if n % p == 0:
            return False
    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1
    for _ in range(k):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def generate_prime(bits: int) -> int:
    if bits < 8:
        raise ValueError("bits must be >= 8")
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if is_probable_prime(candidate):
            return candidate


def rsa_keygen(bits: int = 2048, e: int = 65537) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    half = bits // 2
    while True:
        p = generate_prime(half)
        q = generate_prime(bits - half)
        if p == q:
            continue
        n = p * q
        phi = (p - 1) * (q - 1)
        if phi % e == 0:
            continue
        d = modinv(e, phi)
        return (e, n), (d, n)


def rsa_encrypt(p: int, pub: Tuple[int, int]) -> int:
    e, n = pub
    if not 0 <= p < n:
        raise ValueError("plaintext out of range")
    return pow(p, e, n)


def rsa_decrypt(c: int, priv: Tuple[int, int]) -> int:
    d, n = priv
    return pow(c, d, n)


def _mgf1(seed: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hashlib.sha256(seed + counter.to_bytes(4, "big")).digest())
        counter += 1
    return bytes(out[:length])


def rsa_encrypt_oaep(message: bytes, pub: Tuple[int, int], label: bytes = b"") -> int:
    e, n = pub
    k = (n.bit_length() + 7) // 8
    if len(message) > k - 2 * 32 - 2:
        raise ValueError("message too long")
    label_hash = hashlib.sha256(label).digest()
    ps = b"\x00" * (k - len(message) - 2 * 32 - 2)
    db = label_hash + ps + b"\x01" + message
    seed = os.urandom(32)
    db_mask = _mgf1(seed, k - 32 - 1)
    masked_db = bytes(a ^ b for a, b in zip(db, db_mask))
    seed_mask = _mgf1(masked_db, 32)
    masked_seed = bytes(a ^ b for a, b in zip(seed, seed_mask))
    em = b"\x00" + masked_seed + masked_db
    return pow(int.from_bytes(em, "big"), e, n)


def rsa_decrypt_oaep(ciphertext: int, priv: Tuple[int, int], label: bytes = b"") -> bytes:
    d, n = priv
    k = (n.bit_length() + 7) // 8
    em = pow(ciphertext, d, n).to_bytes(k, "big")
    if em[0] != 0:
        raise ValueError("decryption failed")
    masked_seed = em[1:33]
    masked_db = em[33:]
    seed_mask = _mgf1(masked_db, 32)
    seed = bytes(a ^ b for a, b in zip(masked_seed, seed_mask))
    db_mask = _mgf1(seed, k - 33)
    db = bytes(a ^ b for a, b in zip(masked_db, db_mask))
    label_hash = hashlib.sha256(label).digest()
    if db[:32] != label_hash:
        raise ValueError("label mismatch")
    sep = db.find(b"\x01", 32)
    if sep < 0:
        raise ValueError("OAEP separator missing")
    return db[sep + 1:]


def suzanne_demo() -> None:
    print("=== Chapter SUZANNE example ===")
    p, q = 3, 11
    n = p * q
    z = (p - 1) * (q - 1)
    d = 7
    e = modinv(d, z)
    pub = (e, n)
    priv = (d, n)
    print(f"  p={p}, q={q}, n={n}, z={z}, d={d}, e={e}")
    for letter in "SUZANNE":
        P = ord(letter) - ord("A") + 1
        C = rsa_encrypt(P, pub)
        P2 = rsa_decrypt(C, priv)
        assert P == P2, f"round-trip failed for {letter}"
        print(f"  {letter}: P={P:>2}, P^3={P**3:>10}, P^3 mod 33={C:>2}, "
              f"recovered={P2}")


def session_key_distribution() -> Tuple[bytes, int, bytes]:
    pub, priv = rsa_keygen(bits=2048)
    aes_key = secrets.token_bytes(32)
    ciphertext = rsa_encrypt_oaep(aes_key, pub)
    recovered = rsa_decrypt_oaep(ciphertext, priv)
    return aes_key, ciphertext, recovered


def demo() -> None:
    suzanne_demo()

    print("\n=== 2048-bit RSA keygen (this takes a few seconds) ===")
    pub, priv = rsa_keygen(bits=2048)
    print(f"  n bits: {pub[1].bit_length()}")
    print(f"  e:      {pub[0]}")

    print("\n=== RSA-OAEP round-trip on a 32-byte AES session key ===")
    aes_key, ciphertext, recovered = session_key_distribution()
    print(f"  AES key length: {len(aes_key)} bytes")
    print(f"  ciphertext length: {(pub[1].bit_length() + 7) // 8} bytes")
    print(f"  recovered key matches: {recovered == aes_key}")


def main() -> None:
    demo()


if __name__ == "__main__":
    main()