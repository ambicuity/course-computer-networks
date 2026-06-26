#!/usr/bin/env python3
"""Public-key digital signatures via textbook RSA (small-prime demonstration).

Implements Tanenbaum & Wetherall Chapter 8, Sec. 8.4.2:
* Generate (e, d, n) using two small primes.
* Sign m -> s = m^d mod n; verify (m, s) -> s^e mod n == m.
* Demonstrate the signature property E(D(P)) = P.
* Demonstrate forgery resistance without d, and how key rotation breaks old exhibits.

No third-party dependencies, no network access. Run: ``python3 main.py``.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Primality and key generation
# ---------------------------------------------------------------------------
def is_probable_prime(n: int, rounds: int = 20) -> bool:
    """Miller-Rabin primality test."""
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29):
        if n == p:
            return True
        if n % p == 0:
            return False
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def random_prime(bits: int) -> int:
    """Return an odd probable prime of the requested bit length."""
    while True:
        n = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if is_probable_prime(n):
            return n


@dataclass(frozen=True)
class PublicKey:
    e: int
    n: int


@dataclass(frozen=True)
class PrivateKey:
    d: int
    n: int


@dataclass(frozen=True)
class KeyPair:
    public: PublicKey
    private: PrivateKey


def generate_keypair(bits: int = 64) -> KeyPair:
    """Generate a textbook RSA key pair. ``bits`` is the size of each prime."""
    p = random_prime(bits)
    q = random_prime(bits)
    while q == p:
        q = random_prime(bits)
    n = p * q
    phi = (p - 1) * (q - 1)
    e = 65537
    if phi % e == 0:
        e = 3
    d = pow(e, -1, phi)
    return KeyPair(PublicKey(e, n), PrivateKey(d, n))


# ---------------------------------------------------------------------------
# Sign / verify (textbook, no padding - demonstration only)
# ---------------------------------------------------------------------------
def sign(message: int, key: PrivateKey) -> int:
    return pow(message, key.d, key.n)


def verify(message: int, signature: int, key: PublicKey) -> bool:
    return pow(signature, key.e, key.n) == message


# ---------------------------------------------------------------------------
# Demo scenarios
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 72)
    print("Public-key signatures via textbook RSA - demo")
    print("=" * 72)

    alice = generate_keypair(bits=64)
    print("\n[1] Alice's keypair")
    print(f"    n bits = {alice.public.n.bit_length()}, e = {alice.public.e}")

    plaintext = 0x12345
    print("\n[2] Sign and verify")
    sig = sign(plaintext, alice.private)
    ok = verify(plaintext, sig, alice.public)
    print(f"    plaintext = {plaintext:#x}, signature = {sig:#x}, verify = {ok}")

    # Canonical signature property: E(D(P)) = P
    print("\n[3] Canonical property E(D(P)) = P")
    encrypted_then_decrypted = sign(plaintext, alice.private)
    recovered = pow(encrypted_then_decrypted, alice.public.e, alice.public.n)
    print(f"    P = {plaintext:#x}, E(D(P)) = {recovered:#x}, equal = {plaintext == recovered}")

    # Forgery resistance: pick random sig, verify fails
    print("\n[4] Forgery resistance - random signature rejected")
    forgery = secrets.randbelow(alice.public.n)
    print(f"    random sig verify = {verify(plaintext, forgery, alice.public)}")

    # Bob cannot sign without d (random guessing cannot recover plaintext)
    print("\n[5] Bob attempts forgery by random guessing")
    bob_tries = 0
    t0 = time.perf_counter()
    for _ in range(1000):
        guess = secrets.randbelow(alice.public.n)
        bob_tries += 1
        if pow(guess, alice.public.e, alice.public.n) == plaintext:
            break
    elapsed = time.perf_counter() - t0
    print(f"    Bob tried {bob_tries} random guesses in {elapsed*1000:.2f} ms - none succeeded")

    # Key rotation breaks old exhibits
    print("\n[6] Key rotation - old exhibit fails under new public key")
    rotated = generate_keypair(bits=64)
    print(f"    rotated n bits = {rotated.public.n.bit_length()}")
    print(f"    old exhibit verify under old key = {verify(plaintext, sig, alice.public)}")
    print(f"    old exhibit verify under new key = {verify(plaintext, sig, rotated.public)}")

    # Compare signature sizes
    print("\n[7] Signature size - RSA matches modulus size")
    for bits, label in [(1024, "RSA-1024"), (2048, "RSA-2048"), (3072, "RSA-3072")]:
        k = generate_keypair(bits=bits // 2)
        s = sign(plaintext, k.private)
        print(f"    {label}: signature {s.bit_length()} bits, modulus {k.public.n.bit_length()} bits")

    print("\n[8] Sign vs verify benchmark (1024-bit n)")
    k = generate_keypair(bits=512)
    n_iter = 5
    t0 = time.perf_counter()
    for _ in range(n_iter):
        _ = sign(plaintext, k.private)
    sign_ms = (time.perf_counter() - t0) * 1000 / n_iter
    t0 = time.perf_counter()
    for _ in range(n_iter):
        _ = verify(plaintext, sig, k.public)
    verify_ms = (time.perf_counter() - t0) * 1000 / n_iter
    print(f"    sign (private exp) avg = {sign_ms:.2f} ms")
    print(f"    verify (public exp e=65537) avg = {verify_ms:.2f} ms")


if __name__ == "__main__":
    main()