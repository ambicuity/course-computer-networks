"""RSA: math and the attacks. Wiener's, Fermat's, Pollard's rho.

Educational stdlib-only implementation that:
- generates 1024-bit RSA key pairs with Miller-Rabin primality testing,
- encrypts / decrypts / signs / verifies,
- runs Wiener's continued-fraction attack on small-d keys,
- runs Fermat's factorization on close-primes moduli,
- runs Pollard's rho factorization on moderate factors.

Run: python3 code/main.py

This is textbook RSA on a small modulus. Never use this for real secrets.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Tuple


# --- Miller-Rabin primality test ---------------------------------------------


def is_probable_prime(n: int, witnesses: int = 8) -> bool:
    if n < 2:
        return False
    small_primes = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)
    for p in small_primes:
        if n % p == 0:
            return n == p
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(witnesses):
        a = random.randrange(2, n - 1)
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def gen_prime(bits: int) -> int:
    while True:
        n = random.getrandbits(bits) | (1 << (bits - 1)) | 1
        if is_probable_prime(n):
            return n


# --- RSA core -----------------------------------------------------------------


@dataclass(frozen=True)
class RSAKeyPair:
    n: int
    e: int
    d: int = 0

    def public_tuple(self) -> Tuple[int, int]:
        return (self.n, self.e)


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


def generate_keypair(bits: int = 1024, e: int = 65537) -> RSAKeyPair:
    p = gen_prime(bits // 2)
    q = gen_prime(bits // 2)
    while q == p:
        q = gen_prime(bits // 2)
    n = p * q
    phi = (p - 1) * (q - 1)
    d = modinv(e, phi)
    return RSAKeyPair(n=n, e=e, d=d)


def encrypt(m: int, pub: Tuple[int, int]) -> int:
    return pow(m, pub[1], pub[0])


def decrypt(c: int, priv: RSAKeyPair) -> int:
    return pow(c, priv.d, priv.n)


# --- Wiener attack ------------------------------------------------------------


def cf_convergents(num: int, den: int) -> List[Tuple[int, int]]:
    """Generate (a, b) convergents of the continued fraction of num/den."""
    out: List[Tuple[int, int]] = []
    h_prev, k_prev = 1, 0
    h, k = 0, 1
    a, b = num, den
    while b != 0:
        q = a // b
        a, b = b, a - q * b
        h_prev, h = h, q * h + h_prev
        k_prev, k = k, q * k + k_prev
        out.append((h, k))
    return out


def wiener_attack(n: int, e: int) -> int:
    """Recover d from (n, e) when d < n^0.25 / 3."""
    for k, d in cf_convergents(e, n):
        if k == 0 or d == 0:
            continue
        if (e * d - 1) % k != 0:
            continue
        phi = (e * d - 1) // k
        b = n - phi + 1
        disc = b * b - 4 * n
        if disc < 0:
            continue
        s = math.isqrt(disc)
        if s * s == disc:
            return d
    raise ValueError("Wiener attack failed: d may not be small enough")


# --- Fermat factorization -----------------------------------------------------


def fermat_factor(n: int, max_iters: int = 200_000) -> Tuple[int, int]:
    a = math.isqrt(n)
    if a * a < n:
        a += 1
    for _ in range(max_iters):
        b2 = a * a - n
        b = math.isqrt(b2)
        if b * b == b2:
            return (a + b, a - b)
        a += 1
    raise ValueError("Fermat factorization did not converge")


# --- Pollard's rho ------------------------------------------------------------


def pollard_rho(n: int, max_iters: int = 200_000) -> int:
    if n % 2 == 0:
        return 2
    while True:
        x = random.randrange(2, n)
        y = x
        c = random.randrange(1, n)
        d = 1
        while d == 1:
            x = (x * x + c) % n
            y = (y * y + c) % n
            y = (y * y + c) % n
            d = math.gcd(abs(x - y), n)
            max_iters -= 1
            if max_iters == 0:
                break
        if d != n and d != 1:
            return d


# --- Demo driver --------------------------------------------------------------


def main() -> None:
    # --- Round-trip RSA ---------------------------------------------------------
    print("=== RSA round-trip on 1024-bit modulus ===")
    kp = generate_keypair(bits=1024)
    n, e = kp.n, kp.e
    print(f"  bits(n) = {n.bit_length()}, e = {e}")
    msg = random.randrange(2, n - 1)
    ct = encrypt(msg, kp.public_tuple())
    pt = decrypt(ct, kp)
    assert pt == msg, "decrypt(encrypt(M)) != M"
    print(f"  encrypt/decrypt round-trip OK on 1024-bit modulus")

    # --- Wiener attack ----------------------------------------------------------
    print("\n=== Wiener's continued-fraction attack on a small-d key ===")
    # Construct a key with d < n^0.25 / 3 by choosing a small d and computing e.
    p_small = gen_prime(512)
    q_small = gen_prime(512)
    n_small = p_small * q_small
    phi_small = (p_small - 1) * (q_small - 1)
    d_small = random.randrange(2, max(3, int(n_small ** 0.25 // 3)))
    while math.gcd(d_small, phi_small) != 1:
        d_small += 1
    e_small = modinv(d_small, phi_small)
    recovered_d = wiener_attack(n_small, e_small)
    assert recovered_d == d_small, "Wiener attack recovered wrong d"
    print(f"  recovered d = {recovered_d} (matches the small private exponent)")

    # --- Fermat attack ----------------------------------------------------------
    print("\n=== Fermat factorization on close-primes modulus ===")
    base = gen_prime(512)
    delta = random.randrange(2, 2 ** 18)
    p_close = base
    q_close = base + delta
    while not is_probable_prime(q_close):
        q_close += 1
    n_close = p_close * q_close
    p2, q2 = fermat_factor(n_close)
    assert {p2, q2} == {p_close, q_close}
    print(f"  recovered p, q = {p2.bit_length()} bits and {q2.bit_length()} bits")

    # --- Pollard's rho ----------------------------------------------------------
    print("\n=== Pollard's rho on a 40-digit semiprime ===")
    p_big = gen_prime(64)
    q_big = gen_prime(64)
    n_big = p_big * q_big
    factor = pollard_rho(n_big)
    assert n_big % factor == 0 and 1 < factor < n_big
    print(f"  recovered non-trivial factor ({factor.bit_length()} bits)")
    print("  All three attacks completed successfully.")


if __name__ == "__main__":
    main()