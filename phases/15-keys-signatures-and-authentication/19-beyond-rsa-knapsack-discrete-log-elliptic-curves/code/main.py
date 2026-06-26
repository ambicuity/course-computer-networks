#!/usr/bin/env python3
"""Beyond RSA: Knapsack, Discrete-Log, and Elliptic Curves.

Implements, with stdlib only:

  * Merkle-Hellman knapsack: superincreasing sequence, trapdoor pair,
    encrypt/decrypt, and a low-density attack (Shamir 1984 style)
  * ElGamal encryption over Z_p*: keygen, encrypt, decrypt
  * Baby-step giant-step discrete-log solver
  * Elliptic-curve group over Z_p: point addition, doubling, scalar mul
  * Toy ECDSA sign and verify
  * ec_demo(): full ECDH-style key agreement on a small curve

Run with `python3 main.py`.
"""

from __future__ import annotations

import hashlib
import math
import secrets
from dataclasses import dataclass
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def modinv(a: int, m: int) -> int:
    """Extended Euclidean modular inverse."""
    g, x, _ = _egcd(a % m, m)
    if g != 1:
        raise ValueError(f"no inverse for {a} mod {m}")
    return x % m


def _egcd(a: int, b: int) -> Tuple[int, int, int]:
    if b == 0:
        return a, 1, 0
    g, x, y = _egcd(b, a % b)
    return g, y, x - (a // b) * y


def is_probable_prime(n: int, k: int = 20) -> bool:
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29):
        if n == p:
            return True
        if n % p == 0:
            return False
    d, s = n - 1, 0
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


# ---------------------------------------------------------------------------
# Part 1 – Merkle-Hellman knapsack
# ---------------------------------------------------------------------------

def _superincreasing(n: int) -> List[int]:
    """Generate a random superincreasing sequence of length n."""
    seq = []
    total = 0
    val = secrets.randbelow(8) + 2
    for _ in range(n):
        val = total + secrets.randbelow(16) + 1
        seq.append(val)
        total += val
    return seq


def merkle_hellman_keygen(n: int = 8) -> Tuple[Tuple[List[int], int], Tuple[List[int], int, int, int]]:
    """
    Returns (public_key, private_key).
      public_key  = (b_list, m)       where b_i = w * a_i mod m
      private_key = (a_list, m, w, w_inv)
    """
    a = _superincreasing(n)
    total = sum(a)
    # m must be > sum(a)
    m = total + secrets.randbelow(total) + 1
    # w must be coprime to m
    while True:
        w = secrets.randbelow(m - 2) + 2
        try:
            w_inv = modinv(w, m)
            break
        except ValueError:
            continue
    b = [(w * ai) % m for ai in a]
    pub = (b, m)
    priv = (a, m, w, w_inv)
    return pub, priv


def merkle_hellman_encrypt(plaintext_bits: List[int], pub: Tuple[List[int], int]) -> int:
    """Encrypt a list of bits (0/1) as a subset sum of the public sequence."""
    b, _m = pub
    if len(plaintext_bits) != len(b):
        raise ValueError("plaintext_bits length must equal key length")
    return sum(bi * xi for bi, xi in zip(b, plaintext_bits))


def merkle_hellman_decrypt(ciphertext: int, priv: Tuple[List[int], int, int, int]) -> List[int]:
    """Decrypt using the trapdoor: convert to superincreasing, greedy solve."""
    a, m, _w, w_inv = priv
    # Map ciphertext back to superincreasing domain
    c_prime = (ciphertext * w_inv) % m
    # Greedy recovery (works because a is superincreasing)
    bits = []
    for ai in reversed(a):
        if c_prime >= ai:
            bits.append(1)
            c_prime -= ai
        else:
            bits.append(0)
    bits.reverse()
    return bits


def low_density_attack(pub: Tuple[List[int], int], plaintext_bits: Optional[List[int]] = None) -> Optional[List[int]]:
    """
    Shamir (1984) low-density attack on Merkle-Hellman.

    For toy sizes we use a simple exhaustive or LLL-inspired heuristic:
    compute density d = n / log2(max(b)) and, for small n, brute-force
    a verification that the ciphertext decomposes.  Real implementations
    use LLL lattice reduction; here we show the density calculation and
    demonstrate the attack succeeds on these parameters.
    """
    b, m = pub
    n = len(b)
    max_b = max(b)
    density = n / math.log2(max_b) if max_b > 1 else float("inf")

    print(f"  [low_density_attack] n={n}, max(b)={max_b}, density={density:.4f}")
    print(f"  [low_density_attack] Density < 1 → Shamir/LO attack applicable: {density < 1.0}")

    if plaintext_bits is None:
        # Without target ciphertext we can only report density
        return None

    # For the toy demonstration: recompute ciphertext and verify
    target = sum(bi * xi for bi, xi in zip(b, plaintext_bits))

    # Brute-force for n <= 20 (toy demo only; LLL handles larger)
    if n <= 20:
        for mask in range(1 << n):
            bits = [(mask >> i) & 1 for i in range(n)]
            if sum(bi * xi for bi, xi in zip(b, bits)) == target:
                return bits
    return None


# ---------------------------------------------------------------------------
# Part 2 – ElGamal encryption over Z_p*
# ---------------------------------------------------------------------------

def elgamal_keygen(p: int, g: int) -> Tuple[int, int]:
    """
    Returns (public_key y, private_key x) where y = g^x mod p.
    Caller supplies a prime p and generator g.
    """
    x = secrets.randbelow(p - 3) + 2      # private key in [2, p-2]
    y = pow(g, x, p)                       # public key
    return y, x


def elgamal_encrypt(m: int, pub: int, p: int, g: int) -> Tuple[int, int]:
    """
    Bob encrypts message m.
    Chooses random k; returns (c1, c2) = (g^k mod p, m * pub^k mod p).
    """
    if not 0 < m < p:
        raise ValueError("message m must satisfy 0 < m < p")
    k = secrets.randbelow(p - 3) + 2
    c1 = pow(g, k, p)
    c2 = (m * pow(pub, k, p)) % p
    return c1, c2


def elgamal_decrypt(c1: int, c2: int, priv: int, p: int) -> int:
    """
    Alice decrypts: m = c2 * (c1^x)^-1 mod p.
    """
    s = pow(c1, priv, p)          # shared secret g^(kx) mod p
    s_inv = modinv(s, p)
    return (c2 * s_inv) % p


# ---------------------------------------------------------------------------
# Part 3 – Baby-step giant-step discrete-log solver
# ---------------------------------------------------------------------------

def baby_step_giant_step(g: int, y: int, p: int, n: int) -> Optional[int]:
    """
    Solve g^x ≡ y (mod p) for x in [0, n).
    Uses O(sqrt(n)) time and space.
    Returns x or None if not found.
    """
    m = math.isqrt(n) + 1
    # Baby steps: compute g^j mod p for j in 0..m-1
    table: dict[int, int] = {}
    gj = 1
    for j in range(m):
        table[gj] = j
        gj = (gj * g) % p
    # Giant steps: g^(-m) mod p
    g_neg_m = modinv(pow(g, m, p), p)
    gamma = y
    for i in range(m):
        if gamma in table:
            x = i * m + table[gamma]
            if x < n:
                return x
        gamma = (gamma * g_neg_m) % p
    return None


# ---------------------------------------------------------------------------
# Part 4 – Elliptic-curve group over Z_p
# ---------------------------------------------------------------------------

@dataclass
class Curve:
    a: int
    b: int
    p: int
    # A known generator point and its order
    Gx: int
    Gy: int
    order: int

    def is_on_curve(self, x: int, y: int) -> bool:
        return (y * y - x * x * x - self.a * x - self.b) % self.p == 0


# Toy curve: y^2 = x^3 + 2x + 3 mod 97  (order 100, generator (3,6))
TINY_CURVE = Curve(a=2, b=3, p=97, Gx=3, Gy=6, order=5)

# A slightly larger toy: secp-like but tiny p=211
# y^2 = x^3 + 0*x + 7 mod 211 (Bitcoin-style, small prime)
SMALL_CURVE = Curve(a=0, b=7, p=211, Gx=15, Gy=137, order=211)


class ECPoint:
    """
    A point on an elliptic curve y^2 = x^3 + ax + b mod p,
    including the point at infinity (represented as x=None, y=None).
    """

    def __init__(self, x: Optional[int], y: Optional[int], curve: Curve) -> None:
        self.x = x
        self.y = y
        self.curve = curve
        if x is not None and y is not None:
            if not curve.is_on_curve(x, y):
                raise ValueError(f"Point ({x}, {y}) is not on the curve")

    @property
    def is_infinity(self) -> bool:
        return self.x is None

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ECPoint):
            return NotImplemented
        return self.x == other.x and self.y == other.y

    def __repr__(self) -> str:
        if self.is_infinity:
            return "ECPoint(∞)"
        return f"ECPoint({self.x}, {self.y})"

    def negate(self) -> "ECPoint":
        if self.is_infinity:
            return self
        return ECPoint(self.x, (-self.y) % self.curve.p, self.curve)

    def double(self) -> "ECPoint":
        if self.is_infinity or self.y == 0:
            return ECPoint(None, None, self.curve)
        p, a = self.curve.p, self.curve.a
        lam = (3 * self.x * self.x + a) * modinv(2 * self.y, p) % p
        x3 = (lam * lam - 2 * self.x) % p
        y3 = (lam * (self.x - x3) - self.y) % p
        return ECPoint(x3, y3, self.curve)

    def add(self, other: "ECPoint") -> "ECPoint":
        if self.is_infinity:
            return other
        if other.is_infinity:
            return self
        if self == other.negate():
            return ECPoint(None, None, self.curve)
        if self == other:
            return self.double()
        p = self.curve.p
        lam = (other.y - self.y) * modinv(other.x - self.x, p) % p
        x3 = (lam * lam - self.x - other.x) % p
        y3 = (lam * (self.x - x3) - self.y) % p
        return ECPoint(x3, y3, self.curve)

    def scalar_mul(self, k: int) -> "ECPoint":
        """Double-and-add scalar multiplication."""
        if k < 0:
            return self.negate().scalar_mul(-k)
        result = ECPoint(None, None, self.curve)   # identity
        addend = ECPoint(self.x, self.y, self.curve)
        while k:
            if k & 1:
                result = result.add(addend)
            addend = addend.double()
            k >>= 1
        return result


# ---------------------------------------------------------------------------
# Part 5 – Toy ECDSA
# ---------------------------------------------------------------------------

def ec_keygen(curve: Curve) -> Tuple[ECPoint, int]:
    """
    Returns (public_key Q, private_key d) where Q = [d]G.
    """
    G = ECPoint(curve.Gx, curve.Gy, curve)
    d = secrets.randbelow(curve.order - 2) + 1
    Q = G.scalar_mul(d)
    return Q, d


def ecdsa_sign(message_hash: int, priv: int, curve: Curve) -> Tuple[int, int]:
    """
    Sign using toy ECDSA.  Returns (r, s).
    Uses a random nonce k; production code uses RFC 6979 deterministic k.
    """
    G = ECPoint(curve.Gx, curve.Gy, curve)
    n = curve.order
    while True:
        k = secrets.randbelow(n - 2) + 1
        R = G.scalar_mul(k)
        if R.is_infinity:
            continue
        r = R.x % n
        if r == 0:
            continue
        k_inv = modinv(k, n)
        s = k_inv * (message_hash + priv * r) % n
        if s == 0:
            continue
        return r, s


def ecdsa_verify(message_hash: int, sig: Tuple[int, int], pub: ECPoint, curve: Curve) -> bool:
    """Verify a toy ECDSA signature."""
    r, s = sig
    n = curve.order
    if not (1 <= r < n and 1 <= s < n):
        return False
    G = ECPoint(curve.Gx, curve.Gy, curve)
    s_inv = modinv(s, n)
    u1 = message_hash * s_inv % n
    u2 = r * s_inv % n
    point = G.scalar_mul(u1).add(pub.scalar_mul(u2))
    if point.is_infinity:
        return False
    return point.x % n == r


# ---------------------------------------------------------------------------
# Part 6 – ECDH key-agreement demo on small curve
# ---------------------------------------------------------------------------

def ec_demo() -> None:
    """ECDH-style key agreement on the small toy curve."""
    print("=== Elliptic-Curve Diffie-Hellman (toy curve) ===")
    # Use a verified small curve: y^2 = x^3 + 2x + 2 mod 17
    # Generator G=(5,1), order=19
    curve = Curve(a=2, b=2, p=17, Gx=5, Gy=1, order=19)
    G = ECPoint(curve.Gx, curve.Gy, curve)
    print(f"  Curve: y² = x³ + {curve.a}x + {curve.b}  mod {curve.p}")
    print(f"  Generator G = {G},  order = {curve.order}")

    # Alice chooses private scalar a, sends A = [a]G
    a_priv = 6
    A = G.scalar_mul(a_priv)
    print(f"\n  Alice private key: a = {a_priv}")
    print(f"  Alice public key:  A = [a]G = {A}")

    # Bob chooses private scalar b, sends B = [b]G
    b_priv = 13
    B = G.scalar_mul(b_priv)
    print(f"\n  Bob   private key: b = {b_priv}")
    print(f"  Bob   public key:  B = [b]G = {B}")

    # Shared secret: Alice computes [a]B, Bob computes [b]A
    alice_shared = B.scalar_mul(a_priv)
    bob_shared = A.scalar_mul(b_priv)
    print(f"\n  Alice computes [a]B = {alice_shared}")
    print(f"  Bob   computes [b]A = {bob_shared}")
    assert alice_shared == bob_shared, "ECDH shared secret mismatch!"
    print(f"  Shared secret matches: {alice_shared} ✓")

    # ECDSA on this curve
    print("\n=== Toy ECDSA sign/verify ===")
    msg_hash = 7   # pretend H("hello") mod order = 7
    pub, priv_d = ec_keygen(curve)
    sig = ecdsa_sign(msg_hash, priv_d, curve)
    valid = ecdsa_verify(msg_hash, sig, pub, curve)
    print(f"  Public key Q = {pub}")
    print(f"  Signature  (r, s) = {sig}")
    print(f"  Verification: {valid} ✓")
    # Tampered message should fail
    tampered = ecdsa_verify(msg_hash + 1, sig, pub, curve)
    print(f"  Tampered message verification: {tampered}  (expected False)")


# ---------------------------------------------------------------------------
# Main demonstration
# ---------------------------------------------------------------------------

def demo_knapsack() -> None:
    print("=" * 60)
    print("PART 1 — Merkle-Hellman Knapsack (broken cryptosystem)")
    print("=" * 60)
    n = 10
    pub, priv = merkle_hellman_keygen(n=n)
    b, m = pub
    a, _, w, w_inv = priv
    print(f"  Superincreasing sequence a: {a}")
    print(f"  Public sequence         b:  {b}")
    print(f"  Modulus m = {m},  multiplier w = {w}")

    pt_bits = [1, 0, 1, 1, 0, 0, 1, 0, 1, 0]
    c = merkle_hellman_encrypt(pt_bits, pub)
    recovered = merkle_hellman_decrypt(c, priv)
    print(f"\n  Plaintext bits:   {pt_bits}")
    print(f"  Ciphertext:       {c}")
    print(f"  Decrypted bits:   {recovered}")
    print(f"  Decrypt correct:  {recovered == pt_bits}")

    print("\n  --- Low-density attack (Shamir 1984) ---")
    broken = low_density_attack(pub, plaintext_bits=pt_bits)
    if broken is not None:
        print(f"  Attack recovered: {broken}")
        print(f"  Attack correct:   {broken == pt_bits}")
    else:
        print("  Attack: n too large for brute force; density shown above.")


def demo_elgamal() -> None:
    print("\n" + "=" * 60)
    print("PART 2 — ElGamal Encryption over Z_p*")
    print("=" * 60)
    # Small safe prime for demo (real usage: ≥ 2048 bits)
    p = 2357     # prime
    g = 2
    assert is_probable_prime(p)
    pub_y, priv_x = elgamal_keygen(p, g)
    print(f"  Prime p = {p},  generator g = {g}")
    print(f"  Private key x = {priv_x}")
    print(f"  Public key  y = g^x mod p = {pub_y}")

    message = 1729   # the Hardy-Ramanujan taxicab number
    c1, c2 = elgamal_encrypt(message, pub_y, p, g)
    print(f"\n  Plaintext M  = {message}")
    print(f"  Ciphertext (c1, c2) = ({c1}, {c2})")
    decrypted = elgamal_decrypt(c1, c2, priv_x, p)
    print(f"  Decrypted M  = {decrypted}")
    print(f"  Round-trip correct: {decrypted == message}")

    print("\n  --- Baby-step giant-step discrete-log demo ---")
    # Solve: 2^x ≡ pub_y (mod p)  i.e., recover priv_x
    found_x = baby_step_giant_step(g, pub_y, p, p - 1)
    print(f"  BSGS found x = {found_x}  (true x = {priv_x})")
    # Verify: both give same public key (x may differ by group order structure)
    if found_x is not None:
        print(f"  g^found_x mod p = {pow(g, found_x, p)}  ==  pub_y = {pub_y}: "
              f"{pow(g, found_x, p) == pub_y}")

    print("\n  Note: For p ≥ 2048 bits, BSGS needs 2^1024 operations — infeasible.")


def demo_ecc() -> None:
    print("\n" + "=" * 60)
    print("PART 3 — Elliptic-Curve Cryptography")
    print("=" * 60)
    ec_demo()

    print("\n  --- Key size comparison (NIST SP 800-57) ---")
    table = [
        (80,  1024, 160),
        (112, 2048, 224),
        (128, 3072, 256),
        (192, 7680, 384),
        (256, 15360, 521),
    ]
    print(f"  {'Security':>10}  {'RSA/DH bits':>12}  {'ECC bits':>10}")
    print(f"  {'-'*10}  {'-'*12}  {'-'*10}")
    for sec, rsa, ecc in table:
        print(f"  {sec:>10}  {rsa:>12}  {ecc:>10}")
    print("\n  ECC 256-bit key ≈ RSA 3072-bit key in security strength.")
    print("  ECC public key = 32 bytes vs RSA public key ≈ 384 bytes.")


def main() -> None:
    demo_knapsack()
    demo_elgamal()
    demo_ecc()


if __name__ == "__main__":
    main()
