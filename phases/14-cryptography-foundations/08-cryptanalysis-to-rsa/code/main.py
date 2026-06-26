#!/usr/bin/env python3
"""Cryptanalysis and RSA from scratch (textbook Sec 8.3).

Stdlib only. Demonstrates:

1. RSA key generation, encryption, decryption with small primes.
2. Modular exponentiation (square-and-multiply).
3. Cryptanalysis attacks: small e attack, common modulus attack,
   Fermat factoring for close primes.

Run:  python3 main.py
"""
from __future__ import annotations

import math
import random


def is_prime(n: int, k: int = 10) -> bool:
    if n < 2:
        return False
    if n == 2 or n == 3:
        return True
    if n % 2 == 0:
        return False
    r, d = 0, n - 1
    while d % 2 == 0:
        r += 1
        d //= 2
    rng = random.Random(42)
    for _ in range(k):
        a = rng.randrange(2, n - 1)
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


def generate_prime(bits: int, seed: int) -> int:
    rng = random.Random(seed)
    while True:
        candidate = rng.getrandbits(bits) | (1 << (bits - 1)) | 1
        if is_prime(candidate):
            return candidate


def mod_exp(base: int, exp: int, mod: int) -> int:
    return pow(base, exp, mod)


def extended_gcd(a: int, b: int) -> tuple[int, int, int]:
    if a == 0:
        return b, 0, 1
    g, x, y = extended_gcd(b % a, a)
    return g, y - (b // a) * x, x


def mod_inverse(e: int, phi: int) -> int:
    g, x, _ = extended_gcd(e % phi, phi)
    if g != 1:
        raise ValueError("No modular inverse")
    return x % phi


class RSAPublicKey:
    def __init__(self, n: int, e: int):
        self.n = n
        self.e = e


class RSAPrivateKey:
    def __init__(self, n: int, e: int, d: int, p: int, q: int):
        self.n = n
        self.e = e
        self.d = d
        self.p = p
        self.q = q


def rsa_generate(bits: int = 64, seed: int = 42) -> tuple[RSAPublicKey, RSAPrivateKey]:
    p = generate_prime(bits // 2, seed)
    q = generate_prime(bits // 2, seed + 1)
    while q == p:
        q = generate_prime(bits // 2, seed + 2)
    n = p * q
    phi = (p - 1) * (q - 1)
    e = 65537
    if math.gcd(e, phi) != 1:
        e = 3
        while math.gcd(e, phi) != 1:
            e += 2
    d = mod_inverse(e, phi)
    return RSAPublicKey(n, e), RSAPrivateKey(n, e, d, p, q)


def rsa_encrypt(pub: RSAPublicKey, m: int) -> int:
    if m >= pub.n:
        raise ValueError("Message too large for key")
    return mod_exp(m, pub.e, pub.n)


def rsa_decrypt(priv: RSAPrivateKey, c: int) -> int:
    return mod_exp(c, priv.d, priv.n)


def rsa_sign(priv: RSAPrivateKey, m: int) -> int:
    return mod_exp(m, priv.d, priv.n)


def rsa_verify(pub: RSAPublicKey, m: int, sig: int) -> bool:
    return mod_exp(sig, pub.e, pub.n) == m


def fermat_factor(n: int, max_iter: int = 100000) -> tuple[int, int]:
    a = math.isqrt(n)
    if a * a == n:
        return a, a
    a += 1
    for _ in range(max_iter):
        b2 = a * a - n
        b = math.isqrt(b2)
        if b * b == b2:
            return a + b, a - b
        a += 1
    raise ValueError("Fermat factoring failed")


def small_e_attack(pub: RSAPublicKey, ciphertext: int, max_k: int = 1000000) -> int | None:
    if pub.e != 3:
        return None
    for k in range(max_k):
        m_cubed = ciphertext + k * pub.n
        m = round(m_cubed ** (1/3))
        if m ** 3 == m_cubed:
            return m
    return None


def common_modulus_attack(c1: int, c2: int, e1: int, e2: int, n: int) -> int:
    g, s, t = extended_gcd(e1, e2)
    if g != 1:
        raise ValueError("e1 and e2 must be coprime")
    if s < 0:
        c1 = mod_inverse(c1, n)
        s = -s
    if t < 0:
        c2 = mod_inverse(c2, n)
        t = -t
    m = (mod_exp(c1, s, n) * mod_exp(c2, t, n)) % n
    return m


def main() -> None:
    print("=" * 65)
    print("RSA Key Generation, Encryption, Decryption")
    print("=" * 65)

    pub, priv = rsa_generate(bits=64, seed=42)
    print(f"  p = {priv.p}")
    print(f"  q = {priv.q}")
    print(f"  n = p*q = {priv.n}")
    print(f"  phi = (p-1)(q-1) = {(priv.p-1)*(priv.q-1)}")
    print(f"  e = {pub.e}")
    print(f"  d = e^-1 mod phi = {priv.d}")
    print(f"  Public key:  (n={pub.n}, e={pub.e})")
    print(f"  Private key: (n={priv.n}, d={priv.d})")

    message = 12345
    ct = rsa_encrypt(pub, message)
    pt = rsa_decrypt(priv, ct)
    print(f"\n  Message:  {message}")
    print(f"  Encrypt:  {message}^{pub.e} mod {pub.n} = {ct}")
    print(f"  Decrypt:  {ct}^{priv.d} mod {priv.n} = {pt}")
    print(f"  Roundtrip: {'OK' if pt == message else 'FAIL'}")

    sig = rsa_sign(priv, message)
    valid = rsa_verify(pub, message, sig)
    print(f"\n  Sign:     {message}^d mod n = {sig}")
    print(f"  Verify:   {sig}^e mod n = {mod_exp(sig, pub.e, pub.n)} == {message}? {valid}")

    print()
    print("=" * 65)
    print("Cryptanalysis: Small e Attack (e=3, no padding)")
    print("=" * 65)
    pub_small = RSAPublicKey(n=pub.n, e=3)
    phi = (priv.p - 1) * (priv.q - 1)
    e_small = 3
    while math.gcd(e_small, phi) != 1:
        e_small += 2
    priv_small = RSAPrivateKey(n=pub.n, e=e_small, d=mod_inverse(e_small, phi), p=priv.p, q=priv.q)
    pub_small = RSAPublicKey(n=pub.n, e=e_small)
    small_msg = 42
    small_ct = rsa_encrypt(pub_small, small_msg)
    recovered = small_e_attack(pub_small, small_ct, max_k=100000)
    print(f"  Message:  {small_msg}")
    print(f"  Ciphertext: {small_ct}")
    print(f"  Cube root attack recovered: {recovered}")
    print(f"  Attack success: {'YES' if recovered == small_msg else 'NO'}")
    print(f"  Lesson: Without OAEP padding, small e + small m = m^e < n, so just take the e-th root.")

    print()
    print("=" * 65)
    print("Cryptanalysis: Common Modulus Attack")
    print("=" * 65)
    e1, e2 = 5, 7
    phi = (priv.p - 1) * (priv.q - 1)
    d1 = mod_inverse(e1, phi)
    d2 = mod_inverse(e2, phi)
    cm_msg = 999
    cm_n = priv.n
    cm_c1 = mod_exp(cm_msg, e1, cm_n)
    cm_c2 = mod_exp(cm_msg, e2, cm_n)
    cm_recovered = common_modulus_attack(cm_c1, cm_c2, e1, e2, cm_n)
    print(f"  Same n, two different public keys (e1={e1}, e2={e2})")
    print(f"  Message:  {cm_msg}")
    print(f"  c1 = m^e1 mod n = {cm_c1}")
    print(f"  c2 = m^e2 mod n = {cm_c2}")
    print(f"  Recovered without private key: {cm_recovered}")
    print(f"  Attack success: {'YES' if cm_recovered == cm_msg else 'NO'}")
    print(f"  Lesson: Never share n across users. Using extended GCD on e1,e2 recovers m from c1,c2.")

    print()
    print("=" * 65)
    print("Cryptanalysis: Fermat Factoring (close primes)")
    print("=" * 65)
    p_close = generate_prime(32, seed=100)
    q_close = p_close + 2
    while not is_prime(q_close):
        q_close += 2
    n_close = p_close * q_close
    print(f"  p = {p_close}")
    print(f"  q = {q_close} (close to p)")
    print(f"  n = {n_close}")
    fp, fq = fermat_factor(n_close)
    print(f"  Fermat factored: {fp} x {fq}")
    print(f"  Attack success: {'YES' if fp * fq == n_close else 'NO'}")
    print(f"  Lesson: Primes must be far apart. Fermat's method factors n quickly when |p-q| is small.")

    print()
    print("=" * 65)
    print("Modular Exponentiation (Square-and-Multiply)")
    print("=" * 65)
    base, exp, mod = 7, 13, 100
    result = mod_exp(base, exp, mod)
    print(f"  {base}^{exp} mod {mod} = {result}")
    print(f"  Binary of exp {exp} = {bin(exp)}")
    print(f"  Steps: square-and-multiply traverses bits of exponent")


if __name__ == "__main__":
    main()
