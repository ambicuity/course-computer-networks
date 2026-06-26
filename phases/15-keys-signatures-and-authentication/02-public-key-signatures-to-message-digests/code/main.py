"""Public-key signatures and message digests: digest-sign-verify demo.

Demonstrates (Python stdlib only):
  1. A from-scratch SHA-1 compression function (80 rounds, 5 state words).
  2. SHA-256 via hashlib for real verification.
  3. A toy RSA (small primes) signing the SHA-256 digest of a message.
  4. Verification: E_A(D_A(MD(P))) == SHA-256(P).
  5. Tamper detection: change one byte, digest mismatch.

Run: python3 main.py
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Toy RSA (small primes, educational only — NOT secure)
# ---------------------------------------------------------------------------

def _is_prime(n: int, k: int = 20) -> bool:
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31):
        if n % p == 0:
            return n == p
    d, s = n - 1, 0
    while d % 2 == 0:
        d //= 2; s += 1
    for _ in range(k):
        a = random.randrange(2, n - 1)
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def _gen_prime(bits: int) -> int:
    while True:
        cand = random.getrandbits(bits) | (1 << (bits - 1)) | 1
        if _is_prime(cand):
            return cand


@dataclass
class RSAKey:
    n: int
    d: int  # private exponent
    e: int  # public exponent


def rsa_keygen(bits: int = 64) -> RSAKey:
    p, q = _gen_prime(bits), _gen_prime(bits)
    while p == q:
        q = _gen_prime(bits)
    n = p * q
    phi = (p - 1) * (q - 1)
    e = 65537
    d = pow(e, -1, phi)
    return RSAKey(n=n, d=d, e=e)


def rsa_sign(key: RSAKey, digest: int) -> int:
    """D_A(MD(P)) — sign the digest with the private key."""
    return pow(digest, key.d, key.n)


def rsa_verify(key: RSAKey, digest: int, signature: int) -> bool:
    """E_A(D_A(MD(P))) == digest?"""
    return pow(signature, key.e, key.n) == digest


# ---------------------------------------------------------------------------
# From-scratch SHA-1 (educational — mirrors RFC 3174 structure)
# ---------------------------------------------------------------------------

def _rotl(word: int, bits: int) -> int:
    word &= 0xFFFFFFFF
    return ((word << bits) | (word >> (32 - bits))) & 0xFFFFFFFF


def sha1_compress(block: bytes, h0: int, h1: int, h2: int,
                   h3: int, h4: int) -> tuple[int, int, int, int, int]:
    """Process one 512-bit block; return updated H0..H4."""
    w = [0] * 80
    for i in range(16):
        w[i] = int.from_bytes(block[i*4:i*4+4], "big")
    for i in range(16, 80):
        w[i] = _rotl(w[i-3] ^ w[i-8] ^ w[i-14] ^ w[i-16], 1)

    a, b, c, d, e = h0, h1, h2, h3, h4
    for i in range(80):
        if i < 20:
            f = (b & c) | (~b & d) & 0xFFFFFFFF
            k = 0x5A827999
        elif i < 40:
            f = b ^ c ^ d
            k = 0x6ED9EBA1
        elif i < 60:
            f = (b & c) | (b & d) | (c & d)
            k = 0x8F1BBCDC
        else:
            f = b ^ c ^ d
            k = 0xCA62C1D6
        temp = (_rotl(a, 5) + f + e + k + w[i]) & 0xFFFFFFFF
        e, d, c, b, a = d, c, _rotl(b, 30), a, temp
    return (h0 + a) & 0xFFFFFFFF, (h1 + b) & 0xFFFFFFFF, (h2 + c) & 0xFFFFFFFF, \
           (h3 + d) & 0xFFFFFFFF, (h4 + e) & 0xFFFFFFFF


def sha1(msg: bytes) -> str:
    """Full SHA-1: pad, process blocks, output 160-bit hex."""
    ml = len(msg) * 8
    msg += b"\x80"
    while len(msg) % 64 != 56:
        msg += b"\x00"
    msg += ml.to_bytes(8, "big")
    h0, h1, h2, h3, h4 = (
        0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0,
    )
    for i in range(0, len(msg), 64):
        h0, h1, h2, h3, h4 = sha1_compress(msg[i:i+64], h0, h1, h2, h3, h4)
    return f"{h0:08x}{h1:08x}{h2:08x}{h3:08x}{h4:08x}"


# ---------------------------------------------------------------------------
# Digest-sign-verify pipeline
# ---------------------------------------------------------------------------

def run_pipeline() -> None:
    print("=" * 64)
    print("SCENE 1 - Digest-Sign-Verify pipeline (SHA-256 + toy RSA)")
    print("=" * 64)
    random.seed(42)
    alice = rsa_keygen(bits=64)
    msg = b"Transfer $1000 to account 67890"
    digest = int.from_bytes(hashlib.sha256(msg).digest(), "big") % alice.n
    sig = rsa_sign(alice, digest)
    ok = rsa_verify(alice, digest, sig)
    print(f"Message:     {msg.decode()}")
    print(f"SHA-256:     {hashlib.sha256(msg).hexdigest()}")
    print(f"Signature:   {hex(sig)[:24]}...")
    print(f"Verified:     {ok}\n")


def run_tamper_detection() -> None:
    print("=" * 64)
    print("SCENE 2 - Tamper detection (1 byte changed after signing)")
    print("=" * 64)
    random.seed(42)
    alice = rsa_keygen(bits=64)
    msg = b"Transfer $1000 to account 67890"
    digest = int.from_bytes(hashlib.sha256(msg).digest(), "big") % alice.n
    sig = rsa_sign(alice, digest)

    tampered = b"Transfer $1000 to account 67891"  # last digit changed
    tampered_digest = int.from_bytes(hashlib.sha256(tampered).digest(), "big") % alice.n
    ok_original = rsa_verify(alice, digest, sig)
    ok_tampered = rsa_verify(alice, tampered_digest, sig)
    print(f"Original msg verified: {ok_original}")
    print(f"Tampered  msg verified: {ok_tampered}")
    print(f"SHA-256(orig): {hashlib.sha256(msg).hexdigest()[:32]}...")
    print(f"SHA-256(tamp): {hashlib.sha256(tampered).hexdigest()[:32]}...\n")


def run_sha1_demo() -> None:
    print("=" * 64)
    print("SCENE 3 - From-scratch SHA-1 vs hashlib (avalanche demo)")
    print("=" * 64)
    a = b"hello"
    b = b"Hello"
    mine_a = sha1(a)
    mine_b = sha1(b)
    lib_a = hashlib.sha1(a).hexdigest()
    lib_b = hashlib.sha1(b).hexdigest()
    print(f"sha1('hello')  mine={mine_a[:32]}...  lib={lib_a[:32]}...  match={mine_a==lib_a}")
    print(f"sha1('Hello')  mine={mine_b[:32]}...  lib={lib_b[:32]}...  match={mine_b==lib_b}")
    diff = sum(bin(x ^ y).count("1") for x, y in zip(
        int(mine_a, 16).to_bytes(20, "big"), int(mine_b, 16).to_bytes(20, "big")))
    print(f"Bit differences between sha1('hello') and sha1('Hello'): {diff}/160\n")


def main() -> None:
    run_pipeline()
    run_tamper_detection()
    run_sha1_demo()
    print("All three scenes completed successfully.")


if __name__ == "__main__":
    main()