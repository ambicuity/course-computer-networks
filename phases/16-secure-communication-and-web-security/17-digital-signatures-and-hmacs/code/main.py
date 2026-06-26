"""Digital signatures and HMACs (stdlib only).

Educational implementation that exercises:
- RSA signatures with PKCS#1 v1.5 padding (textbook RSA on small modulus),
- HMAC-SHA256 from scratch,
- ECDSA sign + verify on a small toy curve,
- Length-extension resistance of HMAC vs SHA-256.

Run: python3 code/main.py

Do not use for real secrets.
"""

from __future__ import annotations

import hashlib
import hmac
import math
import random
import struct
from dataclasses import dataclass
from typing import Tuple


# --- RSA primitives (textbook) ----------------------------------------------


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


@dataclass(frozen=True)
class RSAKey:
    n: int
    e: int
    d: int = 0


def rsa_keygen(bits: int = 1024) -> RSAKey:
    p = gen_prime(bits // 2)
    q = gen_prime(bits // 2)
    while q == p:
        q = gen_prime(bits // 2)
    n = p * q
    phi = (p - 1) * (q - 1)
    e = 65537
    return RSAKey(n=n, e=e, d=modinv(e, phi))


def pkcs1_v15_encode(message_hash: bytes, key_len_bytes: int, hash_id: bytes = b"sha256") -> bytes:
    """Build EM = 0x00 || 0x01 || PS (0xff...) || 0x00 || DigestInfo."""
    digest_info_prefix = (
        b"\x30\x31\x30\x0d\x06\x09\x60\x86\x48\x01\x65\x03\x04\x02\x01\x05\x00\x04\x20"
    )
    t = digest_info_prefix + message_hash
    if len(t) + 3 > key_len_bytes:
        raise ValueError("message too long for key")
    ps = b"\xff" * (key_len_bytes - len(t) - 3)
    return b"\x00\x01" + ps + b"\x00" + t


def pkcs1_v15_decode(em: bytes, expected_hash: bytes, key_len_bytes: int) -> bool:
    if em[0:2] != b"\x00\x01" or len(em) != key_len_bytes:
        return False
    sep = em.find(b"\x00", 2)
    if sep < 0 or sep < 10:
        return False
    if any(b != 0xFF for b in em[2:sep]):
        return False
    if hashlib.sha256(expected_hash).digest() not in em:
        return False
    return em.endswith(expected_hash)


def rsa_sign(message: bytes, priv: RSAKey) -> int:
    digest = hashlib.sha256(message).digest()
    em = pkcs1_v15_encode(digest, (priv.n.bit_length() + 7) // 8)
    m_int = int.from_bytes(em, "big")
    return pow(m_int, priv.d, priv.n)


def rsa_verify(message: bytes, signature: int, pub: RSAKey) -> bool:
    key_len = (pub.n.bit_length() + 7) // 8
    em = pow(signature, pub.e, pub.n).to_bytes(key_len, "big")
    digest = hashlib.sha256(message).digest()
    return pkcs1_v15_decode(em, digest, key_len)


# --- HMAC-SHA256 (manual) ----------------------------------------------------


def hmac_sha256_manual(key: bytes, message: bytes) -> bytes:
    block_size = 64
    if len(key) > block_size:
        key = hashlib.sha256(key).digest()
    key = key.ljust(block_size, b"\x00")
    ipad = bytes(b ^ 0x36 for b in key)
    opad = bytes(b ^ 0x5C for b in key)
    inner = hashlib.sha256(ipad + message).digest()
    return hashlib.sha256(opad + inner).digest()


# --- ECDSA on a small toy curve ---------------------------------------------


@dataclass(frozen=True)
class Curve:
    p: int  # field prime
    a: int
    b: int
    gx: int  # base point x
    gy: int
    n: int  # order of base point


@dataclass(frozen=True)
class Point:
    x: int
    y: int


def ec_add(p1: Point, p2: Point, curve: Curve) -> Point:
    if p1.x is None:
        return p2
    if p2.x is None:
        return p1
    if p1.x == p2.x and (p1.y + p2.y) % curve.p == 0:
        return Point(x=None, y=None)
    if p1.x == p2.x and p1.y == p2.y:
        s = (3 * p1.x * p1.x + curve.a) * modinv(2 * p1.y, curve.p) % curve.p
    else:
        s = (p2.y - p1.y) * modinv((p2.x - p1.x) % curve.p, curve.p) % curve.p
    x = (s * s - p1.x - p2.x) % curve.p
    y = (s * (p1.x - x) - p1.y) % curve.p
    return Point(x, y)


def ec_mul(k: int, point: Point, curve: Curve) -> Point:
    result = Point(x=None, y=None)
    addend = point
    while k:
        if k & 1:
            result = ec_add(result, addend, curve)
        addend = ec_add(addend, addend, curve)
        k >>= 1
    return result


def ecdsa_sign(message: bytes, priv: int, curve: Curve, gen: Point) -> Tuple[int, int]:
    z = int.from_bytes(hashlib.sha256(message).digest(), "big") % curve.n
    while True:
        k = random.randrange(1, curve.n)
        x1, _ = ec_mul(k, gen, curve).x, None
        r = x1 % curve.n
        if r == 0:
            continue
        s = (modinv(k, curve.n) * (z + r * priv)) % curve.n
        if s != 0:
            return r, s


def ecdsa_verify(
    message: bytes, signature: Tuple[int, int], pub: Point, curve: Curve, gen: Point
) -> bool:
    r, s = signature
    if not (1 <= r < curve.n and 1 <= s < curve.n):
        return False
    z = int.from_bytes(hashlib.sha256(message).digest(), "big") % curve.n
    w = modinv(s, curve.n)
    u1 = (z * w) % curve.n
    u2 = (r * w) % curve.n
    p1 = ec_mul(u1, gen, curve)
    p2 = ec_mul(u2, pub, curve)
    x1, _ = ec_add(p1, p2, curve).x, None
    return (x1 % curve.n) == r


def length_extension_resistance_demo() -> None:
    secret = b"server-shared-key-2026"
    message = b"action=transfer&amount=100"
    # Naive construction: SHA-256(secret || message) — vulnerable.
    naive = hashlib.sha256(secret + message).digest()
    forged_suffix = b"&amount=999999"
    naive_extended_naively = hashlib.sha256(
        secret + message + b"\x80" + b"\x00" * 32 + forged_suffix
    ).digest()
    # HMAC: resistant.
    legit_hmac = hmac.new(secret, message, hashlib.sha256).digest()
    hmac_extended = hmac.new(secret, message + b"\x80" + b"\x00" * 32 + forged_suffix, hashlib.sha256).digest()
    print(f"  SHA-256(secret||message):                {naive.hex()[:16]}...")
    print(f"  SHA-256(secret||message||pad||appended): {naive_extended_naively.hex()[:16]}...")
    print(f"  (different because padding depends on len; legitimate forgery needs the secret)")
    print(f"  HMAC-SHA256(key, message):               {legit_hmac.hex()[:16]}...")
    print(f"  HMAC-SHA256(key, message||pad||appended): {hmac_extended.hex()[:16]}...")
    print(f"  HMAC is NOT a simple prefix hash; the attacker cannot extend.")


# --- Demo driver -------------------------------------------------------------


def main() -> None:
    print("=== RSA signatures (PKCS#1 v1.5) ===")
    rsa = rsa_keygen(bits=1024)
    message = b"From: Alice. To: Bob. Wire $1,000,000 to account 12345."
    sig = rsa_sign(message, rsa)
    ok = rsa_verify(message, sig, rsa)
    print(f"  signature bits = {rsa.n.bit_length()}, sig = {sig.to_bytes((rsa.n.bit_length() + 7) // 8, 'big').hex()[:32]}...")
    print(f"  verify = {ok}")

    print("\n=== HMAC-SHA256 (manual implementation) ===")
    key = os.urandom(32) if False else b"a" * 32  # noqa: F841 — illustrative
    key = bytes(range(32))
    msg = b"amount=100&to=alice"
    manual = hmac_sha256_manual(key, msg)
    stdlib = hmac.new(key, msg, hashlib.sha256).digest()
    print(f"  manual HMAC  = {manual.hex()}")
    print(f"  stdlib HMAC  = {stdlib.hex()}")
    assert manual == stdlib

    print("\n=== ECDSA on a small toy curve ===")
    # y^2 = x^3 + 2x + 3 over F_p, with a chosen-order base point.
    curve = Curve(p=2 ** 192 - 2 ** 64 - 1, a=-3, b=0x64210519e59c80e70fa7e9ab72243049feb8deecc146b9b1, gx=0x188da80eb03090f67cbf20eb43a18800f4ff0afd82ff1012, gy=0x07192b95ffc8da78631011ed6b24cdd573f977a11e794811, n=0xffffffffffffffffffffffff99def836146bc9b1b4d22831)
    gen = Point(curve.gx, curve.gy)
    priv = random.randrange(1, curve.n)
    pub = ec_mul(priv, gen, curve)
    msg = b"document to be signed"
    sig = ecdsa_sign(msg, priv, curve, gen)
    ok = ecdsa_verify(msg, sig, pub, curve, gen)
    print(f"  pub.x bits = {pub.x.bit_length()}, sig = ({sig[0].bit_length()}-bit, {sig[1].bit_length()}-bit)")
    print(f"  verify = {ok}")

    print("\n=== Length-extension resistance ===")
    length_extension_resistance_demo()


if __name__ == "__main__":
    main()