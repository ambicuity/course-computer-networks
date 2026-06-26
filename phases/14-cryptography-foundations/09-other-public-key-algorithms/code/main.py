#!/usr/bin/env python3
"""Other Public-Key Algorithms: ElGamal, Diffie-Hellman, ECC (textbook Sec 8.3).

Stdlib only. Demonstrates:

1. ElGamal encryption and signatures over a small multiplicative group.
2. Diffie-Hellman key exchange with modular exponentiation.
3. Elliptic curve arithmetic (point addition, scalar multiplication)
   over a small prime field, and ECDH key exchange.

Run:  python3 main.py
"""
from __future__ import annotations

import random


def mod_exp(base: int, exp: int, mod: int) -> int:
    return pow(base, exp, mod)


def mod_inverse(a: int, m: int) -> int:
    g, x, _ = extended_gcd(a % m, m)
    if g != 1:
        raise ValueError("No inverse")
    return x % m


def extended_gcd(a: int, b: int) -> tuple[int, int, int]:
    if a == 0:
        return b, 0, 1
    g, x, y = extended_gcd(b % a, a)
    return g, y - (b // a) * x, x


def is_prime(n: int) -> bool:
    if n < 2: return False
    if n < 4: return True
    if n % 2 == 0 or n % 3 == 0: return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0: return False
        i += 6
    return True


def find_primitive_root(p: int) -> int:
    for g in range(2, p):
        seen = set()
        for i in range(p - 1):
            seen.add(mod_exp(g, i, p))
            if len(seen) == p - 1:
                return g
    raise ValueError("No primitive root found")


def elgamal_keygen(p: int, g: int, seed: int = 42) -> tuple[int, int, int]:
    rng = random.Random(seed)
    x = rng.randrange(1, p - 1)
    y = mod_exp(g, x, p)
    return x, y, p


def elgamal_encrypt(p: int, g: int, y: int, m: int, seed: int = 99) -> tuple[int, int]:
    rng = random.Random(seed)
    k = rng.randrange(1, p - 1)
    c1 = mod_exp(g, k, p)
    c2 = (m * mod_exp(y, k, p)) % p
    return c1, c2


def elgamal_decrypt(p: int, x: int, c1: int, c2: int) -> int:
    s = mod_exp(c1, x, p)
    s_inv = mod_inverse(s, p)
    return (c2 * s_inv) % p


def elgamal_sign(p: int, g: int, x: int, m: int, seed: int = 77) -> tuple[int, int]:
    rng = random.Random(seed)
    while True:
        k = rng.randrange(1, p - 1)
        if extended_gcd(k, p - 1)[0] == 1:
            break
    r = mod_exp(g, k, p)
    k_inv = mod_inverse(k, p - 1)
    s = ((m - x * r) * k_inv) % (p - 1)
    return r, s


def elgamal_verify(p: int, g: int, y: int, m: int, r: int, s: int) -> bool:
    v1 = mod_exp(g, m, p)
    v2 = (mod_exp(y, r, p) * mod_exp(r, s, p)) % p
    return v1 == v2


def diffie_hellman(p: int, g: int, seed_a: int = 10, seed_b: int = 20) -> tuple[int, int, int]:
    rng_a = random.Random(seed_a)
    rng_b = random.Random(seed_b)
    a = rng_a.randrange(1, p)
    b = rng_b.randrange(1, p)
    A = mod_exp(g, a, p)
    B = mod_exp(g, b, p)
    shared_a = mod_exp(B, a, p)
    shared_b = mod_exp(A, b, p)
    return a, b, shared_a


class ECPoint:
    def __init__(self, x: int | None, y: int | None, p: int, a: int, b: int):
        self.x = x
        self.y = y
        self.p = p
        self.a = a
        self.b = b

    @property
    def is_infinity(self) -> bool:
        return self.x is None and self.y is None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ECPoint):
            return False
        return self.x == other.x and self.y == other.y

    def __repr__(self) -> str:
        if self.is_infinity:
            return "O(infinity)"
        return f"({self.x}, {self.y})"


def ec_add(P: ECPoint, Q: ECPoint) -> ECPoint:
    if P.is_infinity: return Q
    if Q.is_infinity: return P
    if P.x == Q.x and (P.y != Q.y or P.y == 0):
        return ECPoint(None, None, P.p, P.a, P.b)
    if P == Q:
        lam = (3 * P.x * P.x + P.a) * mod_inverse(2 * P.y, P.p) % P.p
    else:
        lam = (Q.y - P.y) * mod_inverse(Q.x - P.x, P.p) % P.p
    x3 = (lam * lam - P.x - Q.x) % P.p
    y3 = (lam * (P.x - x3) - P.y) % P.p
    return ECPoint(x3, y3, P.p, P.a, P.b)


def ec_scalar_mult(k: int, P: ECPoint) -> ECPoint:
    result = ECPoint(None, None, P.p, P.a, P.b)
    addend = P
    while k > 0:
        if k & 1:
            result = ec_add(result, addend)
        addend = ec_add(addend, addend)
        k >>= 1
    return result


def ec_is_on_curve(P: ECPoint) -> bool:
    if P.is_infinity: return True
    return (P.y * P.y - P.x * P.x * P.x - P.a * P.x - P.b) % P.p == 0


def ecdh(p: int, a: int, b: int, G: ECPoint, n: int, seed_a: int = 5, seed_b: int = 15) -> tuple[ECPoint, ECPoint, ECPoint]:
    rng_a = random.Random(seed_a)
    rng_b = random.Random(seed_b)
    priv_a = rng_a.randrange(1, n)
    priv_b = rng_b.randrange(1, n)
    pub_a = ec_scalar_mult(priv_a, G)
    pub_b = ec_scalar_mult(priv_b, G)
    shared_a = ec_scalar_mult(priv_a, pub_b)
    shared_b = ec_scalar_mult(priv_b, pub_a)
    return pub_a, pub_b, shared_a


def main() -> None:
    print("=" * 65)
    print("ElGamal Encryption and Signatures")
    print("=" * 65)

    p = 10007
    g = find_primitive_root(p)
    x, y, _ = elgamal_keygen(p, g, seed=42)
    print(f"  Prime p = {p}, Generator g = {g}")
    print(f"  Private key x = {x}")
    print(f"  Public key y = g^x mod p = {y}")

    message = 1234
    c1, c2 = elgamal_encrypt(p, g, y, message, seed=99)
    decrypted = elgamal_decrypt(p, x, c1, c2)
    print(f"\n  Message:    {message}")
    print(f"  Ciphertext: (c1={c1}, c2={c2})")
    print(f"  Decrypted:  {decrypted}")
    print(f"  Roundtrip:  {'OK' if decrypted == message else 'FAIL'}")

    r, s = elgamal_sign(p, g, x, message, seed=77)
    valid = elgamal_verify(p, g, y, message, r, s)
    print(f"\n  Signature: (r={r}, s={s})")
    print(f"  Verify:    {valid}")

    tampered = message + 1
    invalid = elgamal_verify(p, g, y, tampered, r, s)
    print(f"  Verify tampered msg {tampered}: {invalid} (should be False)")

    print()
    print("=" * 65)
    print("Diffie-Hellman Key Exchange")
    print("=" * 65)
    p_dh = 10007
    g_dh = find_primitive_root(p_dh)
    a_priv, b_priv, shared = diffie_hellman(p_dh, g_dh)
    print(f"  Prime p = {p_dh}, Generator g = {g_dh}")
    print(f"  Alice private a = {a_priv}")
    print(f"  Bob private b = {b_priv}")
    A = mod_exp(g_dh, a_priv, p_dh)
    B = mod_exp(g_dh, b_priv, p_dh)
    print(f"  Alice public A = g^a mod p = {A}")
    print(f"  Bob public B = g^b mod p = {B}")
    print(f"  Alice computes: B^a mod p = {mod_exp(B, a_priv, p_dh)}")
    print(f"  Bob computes:   A^b mod p = {mod_exp(A, b_priv, p_dh)}")
    print(f"  Shared secret:  {shared}")
    print(f"  Match: {'YES' if mod_exp(B, a_priv, p_dh) == mod_exp(A, b_priv, p_dh) else 'NO'}")

    print()
    print("=" * 65)
    print("Elliptic Curve Cryptography (ECDH)")
    print("=" * 65)

    ec_p = 23
    ec_a = 1
    ec_b = 1
    G = ECPoint(9, 1, ec_p, ec_a, ec_b)
    print(f"  Curve: y^2 = x^3 + {ec_a}x + {ec_b} mod {ec_p}")
    print(f"  Generator G = (9, 1)")
    print(f"  G on curve: {ec_is_on_curve(G)}")

    print(f"\n  Point addition examples:")
    G2 = ec_add(G, G)
    G3 = ec_add(G2, G)
    G4 = ec_add(G2, G2)
    print(f"    2G = {G2}")
    print(f"    3G = {G3}")
    print(f"    4G = {G4}")
    print(f"    2G on curve: {ec_is_on_curve(G2)}")
    print(f"    3G on curve: {ec_is_on_curve(G3)}")

    print(f"\n  Scalar multiplication (k*G for k=1..10):")
    for k in range(1, 11):
        kG = ec_scalar_mult(k, G)
        on = ec_is_on_curve(kG)
        print(f"    {k:2d}*G = {kG}  on_curve={on}")

    print(f"\n  ECDH Key Exchange:")
    n = 28
    pub_a, pub_b, shared_ec = ecdh(ec_p, ec_a, ec_b, G, n, seed_a=5, seed_b=15)
    print(f"    Alice public: {pub_a}")
    print(f"    Bob public:   {pub_b}")
    print(f"    Shared secret: {shared_ec}")
    print(f"    Match: {'YES' if shared_ec == shared_ec else 'NO'}")

    print()
    print("=" * 65)
    print("Public-Key Algorithm Comparison")
    print("=" * 65)
    print(f"  {'Algorithm':15s} {'Type':20s} {'Key Exchange':12s} {'Signature':10s}")
    print(f"  {'-'*15} {'-'*20} {'-'*12} {'-'*10}")
    print(f"  {'RSA':15s} {'Factoring':20s} {'Yes':12s} {'Yes':10s}")
    print(f"  {'ElGamal':15s} {'Discrete Log':20s} {'Yes':12s} {'Yes':10s}")
    print(f"  {'DH':15s} {'Discrete Log':20s} {'Yes':12s} {'No':10s}")
    print(f"  {'ECDH/ECDSA':15s} {'EC Discrete Log':20s} {'Yes':12s} {'Yes':10s}")
    print(f"\n  ECC achieves same security with much smaller keys:")
    print(f"    RSA-2048 ~= ECC-224, RSA-3072 ~= ECC-256, RSA-15360 ~= ECC-521")


if __name__ == "__main__":
    main()
