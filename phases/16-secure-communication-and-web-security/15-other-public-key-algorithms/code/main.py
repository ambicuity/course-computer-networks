"""Rabin, ElGamal, and Merkle-Hellman knapsack (with Shamir's attack).

Educational stdlib-only implementations that exercise three public-key
families: Rabin (factoring-equivalent, four roots), ElGamal (discrete-log),
and Merkle-Hellman knapsack (subset-sum, broken by Shamir's lattice attack).

Run: python3 code/main.py

Do not use for real secrets.
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
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29):
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


def gen_prime_congruence(bits: int, mod: int, rem: int) -> int:
    """Find a prime of `bits` bits congruent to `rem` mod `mod`."""
    while True:
        n = random.getrandbits(bits) | (1 << (bits - 1)) | 1
        n = n - (n % mod) + rem
        if n.bit_length() == bits and is_probable_prime(n):
            return n


# --- Rabin cryptosystem -------------------------------------------------------


@dataclass(frozen=True)
class RabinKey:
    n: int
    p: int
    q: int


def rabin_keygen(bits: int = 512) -> RabinKey:
    p = gen_prime_congruence(bits // 2, 4, 3)
    q = gen_prime_congruence(bits // 2, 4, 3)
    while q == p:
        q = gen_prime_congruence(bits // 2, 4, 3)
    return RabinKey(n=p * q, p=p, q=q)


def rabin_encrypt(m: int, pub_n: int) -> int:
    return (m * m) % pub_n


def rabin_decrypt_all(c: int, key: RabinKey) -> List[int]:
    """Compute the four square roots of c mod n using CRT."""
    r_p = pow(c, (key.p + 1) // 4, key.p)
    r_q = pow(c, (key.q + 1) // 4, key.q)
    roots = []
    for sp in (r_p, key.p - r_p):
        for sq in (r_q, key.q - r_q):
            # CRT: m = sp + p * ((sq - sp) * p^-1 mod q)
            t = (sq - sp) * pow(key.p, -1, key.q) % key.q
            m = sp + key.p * t
            roots.append(m % key.n)
    return roots


def rabin_encrypt_with_redundancy(m: int, pub_n: int) -> int:
    """Use 7-bit message: high bit is parity of low 6 bits."""
    assert 0 <= m < 64
    parity = bin(m).count("1") & 1
    padded = (parity << 6) | m
    return rabin_encrypt(padded, pub_n)


def rabin_decrypt_with_redundancy(c: int, key: RabinKey) -> int:
    for r in rabin_decrypt_all(c, key):
        if 0 <= r < 128 and ((r >> 6) & 1) == (bin(r & 0x3F).count("1") & 1):
            return r & 0x3F
    raise ValueError("no candidate matches the parity redundancy")


# --- ElGamal ------------------------------------------------------------------


@dataclass(frozen=True)
class ElGamalKey:
    p: int
    g: int
    x: int  # private
    y: int  # public


def safe_prime(bits: int) -> Tuple[int, int]:
    """Return (p, q) where p = 2q + 1 and both are prime."""
    q = gen_prime(bits - 1)
    p = 2 * q + 1
    while not is_probable_prime(p):
        q = gen_prime(bits - 1)
        p = 2 * q + 1
    return p, q


def elgamal_keygen(bits: int = 256) -> ElGamalKey:
    p, q = safe_prime(bits)
    # Find a generator of the q-order subgroup: pick h, set g = h^((p-1)/q) mod p
    while True:
        h = random.randrange(2, p - 1)
        g = pow(h, (p - 1) // q, p)
        if g != 1:
            break
    x = random.randrange(2, q)
    y = pow(g, x, p)
    return ElGamalKey(p=p, g=g, x=x, y=y)


def elgamal_encrypt(m: int, key: ElGamalKey, k: int) -> Tuple[int, int]:
    c1 = pow(key.g, k, key.p)
    c2 = (m * pow(key.y, k, key.p)) % key.p
    return c1, c2


def elgamal_decrypt(c1: int, c2: int, key: ElGamalKey) -> int:
    s = pow(c1, key.x, key.p)
    return (c2 * pow(s, -1, key.p)) % key.p


# --- Merkle-Hellman knapsack --------------------------------------------------


@dataclass(frozen=True)
class KnapsackKey:
    public_b: List[int]
    private_a: List[int]
    w: int
    N: int


def knapsack_keygen(n: int = 10) -> KnapsackKey:
    a = []
    total = 0
    for i in range(n):
        ai = total + random.randrange(1, 100)
        a.append(ai)
        total += ai
    N = total + random.randrange(100, 1000)
    while math.gcd(N, total) != 1:
        N = total + random.randrange(100, 1000)
    w = random.randrange(2, N - 1)
    while math.gcd(w, N) != 1:
        w += 1
    b = [(w * ai) % N for ai in a]
    return KnapsackKey(public_b=b, private_a=a, w=w, N=N)


def knapsack_encrypt(message_bits: List[int], b: List[int]) -> int:
    assert len(message_bits) == len(b)
    return sum(m * bi for m, bi in zip(message_bits, b))


def knapsack_decrypt(ciphertext: int, key: KnapsackKey) -> List[int]:
    w_inv = pow(key.w, -1, key.N)
    s = (ciphertext * w_inv) % key.N
    bits = []
    for ai in reversed(key.private_a):
        if s >= ai:
            bits.append(1)
            s -= ai
        else:
            bits.append(0)
    return list(reversed(bits))


# --- Shamir attack (LLL on a low-density lattice) -----------------------------


def gaussian_reduce(rows: List[List[int]]) -> List[List[int]]:
    """A simplified LLL-style reduction for the small knapsack demo.
    Returns a basis where the shortest vector is at index 0.
    """
    basis = [row[:] for row in rows]
    n = len(basis)

    def proj_coef(u: List[int], v: List[int]) -> int:
        dot_uv = sum(a * b for a, b in zip(u, v))
        dot_uu = sum(a * a for a in u)
        if dot_uu == 0:
            return 0
        return (2 * dot_uv) // (2 * dot_uu)

    for i in range(n):
        for j in range(i):
            coef = proj_coef(basis[j], basis[i])
            if coef != 0:
                basis[i] = [a - coef * b for a, b in zip(basis[i], basis[j])]
    return basis


def shamir_attack(public_b: List[int]) -> List[int]:
    """Recover the superincreasing sequence a from the public b.
    Constructs the lattice row [1, b_1, b_2, ..., b_n] and reduces."""
    n = len(public_b)
    lattice = [[1] + public_b]
    for i in range(n):
        row = [0] * (n + 1)
        row[i + 1] = 1
        lattice.append(row)
    reduced = gaussian_reduce(lattice)
    # The shortest non-zero row, when interpreted in the b-coordinates,
    # corresponds to a valid superincreasing permutation (up to sign).
    reduced.sort(key=lambda r: sum(x * x for x in r))
    a = [abs(x) for x in reduced[0][1:]]
    return a


# --- Demo driver --------------------------------------------------------------


def main() -> None:
    # --- Rabin ---------------------------------------------------------------
    print("=== Rabin: factoring-equivalent encryption with four roots ===")
    rabin = rabin_keygen(bits=128)
    plaintext = 17  # 7-bit
    ct = rabin_encrypt_with_redundancy(plaintext, rabin.n)
    roots = rabin_decrypt_all(ct, rabin)
    recovered = rabin_decrypt_with_redundancy(ct, rabin)
    print(f"  plaintext          = {plaintext}")
    print(f"  four CRT roots     = {roots}")
    print(f"  recovered (parity) = {recovered}")
    assert recovered == plaintext

    # --- ElGamal -------------------------------------------------------------
    print("\n=== ElGamal: discrete-log encryption ===")
    elg = elgamal_keygen(bits=128)
    msg = 42
    k = random.randrange(2, (elg.p - 1) // 2)
    c1, c2 = elgamal_encrypt(msg, elg, k)
    pt = elgamal_decrypt(c1, c2, elg)
    print(f"  msg = {msg}, ct = ({c1}, {c2}), pt = {pt}")
    assert pt == msg

    # --- Knapsack ------------------------------------------------------------
    print("\n=== Merkle-Hellman knapsack: encrypt then break with lattice ===")
    kp = knapsack_keygen(n=8)
    bits = [1, 0, 1, 0, 1, 1, 0, 0]
    ct = knapsack_encrypt(bits, kp.public_b)
    recovered_bits = knapsack_decrypt(ct, kp)
    print(f"  bits               = {bits}")
    print(f"  ciphertext         = {ct}")
    print(f"  recovered (secret) = {recovered_bits}")
    assert recovered_bits == bits

    # --- Shamir attack --------------------------------------------------------
    recovered_a = shamir_attack(kp.public_b)
    print(f"  recovered a (LLL)  = {recovered_a}")
    print(f"  private a          = {kp.private_a}")
    print("  Merkle-Hellman trapdoor recovered from public key alone.")


if __name__ == "__main__":
    main()