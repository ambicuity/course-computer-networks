"""Minimal PGP message construction and key-ring simulator (stdlib only).

Implements the five-operation PGP "Encrypt and Sign" chain described in
Tanenbaum section 8.6: SHA-256 hash of plaintext, RSA signature over the
hash, per-message session key K_S, a stream-mode symmetric encryption of the
plaintext (here: a CTR-style keystream generated from K_S via SHA-256 in
counter mode), and RSA wrap of K_S under the recipient's public key. Also
implements public/private key rings and the web-of-trust ownertrust model.

This is educational code: the RSA is textbook on a 1024-bit modulus and the
symmetric layer is a SHA-256-CTR stream. Do not use for real secrets.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
from dataclasses import dataclass, field
from typing import Dict, List, Tuple


# --- Minimal textbook RSA -----------------------------------------------------


def _egcd(a: int, b: int) -> Tuple[int, int, int]:
    if b == 0:
        return a, 1, 0
    g, x, y = _egcd(b, a % b)
    return g, y, x - (a // b) * y


def _modinv(a: int, m: int) -> int:
    g, x, _ = _egcd(a % m, m)
    if g != 1:
        raise ValueError("no modular inverse")
    return x % m


def _is_prime(n: int, witnesses: int = 8) -> bool:
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
    import random

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


def _gen_prime(bits: int) -> int:
    import random

    while True:
        n = random.getrandbits(bits) | (1 << (bits - 1)) | 1
        if _is_prime(n):
            return n


@dataclass(frozen=True)
class RSAKeyPair:
    n: int
    e: int
    d: int = 0

    def public_tuple(self) -> Tuple[int, int]:
        return (self.n, self.e)


def generate_rsa(bits: int = 1024) -> RSAKeyPair:
    p = _gen_prime(bits // 2)
    q = _gen_prime(bits // 2)
    while q == p:
        q = _gen_prime(bits // 2)
    n = p * q
    phi = (p - 1) * (q - 1)
    e = 65537
    d = _modinv(e, phi)
    return RSAKeyPair(n=n, e=e, d=d)


def rsa_encrypt(m: int, pub: Tuple[int, int]) -> int:
    n, e = pub
    return pow(m, e, n)


def rsa_decrypt(c: int, priv: RSAKeyPair) -> int:
    return pow(c, priv.d, priv.n)


# --- SHA-256-CTR stream (educational stand-in for AES-CTR) -------------------


def sha256_ctr_stream(key: bytes, iv: bytes, length: int) -> bytes:
    """Generate `length` bytes of keystream as SHA256(key || iv || counter)."""
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hashlib.sha256(key + iv + counter.to_bytes(8, "big")).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def stream_encrypt(key: bytes, plaintext: bytes) -> Tuple[bytes, bytes]:
    iv = os.urandom(16)
    ks = sha256_ctr_stream(key, iv, len(plaintext))
    ciphertext = bytes(a ^ b for a, b in zip(plaintext, ks))
    return ciphertext, iv


def stream_decrypt(key: bytes, ciphertext: bytes, iv: bytes) -> bytes:
    ks = sha256_ctr_stream(key, iv, len(ciphertext))
    return bytes(a ^ b for a, b in zip(ciphertext, ks))


# --- Key rings ----------------------------------------------------------------


@dataclass
class PublicRingEntry:
    user_id: str
    pub: Tuple[int, int]
    ownertrust: str = "unknown"  # unknown|never|marginal|full|ultimate
    signatures: List[str] = field(default_factory=list)


@dataclass
class PrivateRingEntry:
    user_id: str
    priv: RSAKeyPair
    passphrase_protected: bool = True


class KeyRing:
    def __init__(self) -> None:
        self.public_ring: Dict[str, PublicRingEntry] = {}
        self.private_ring: Dict[str, PrivateRingEntry] = {}

    def add_user(self, user_id: str, keypair: RSAKeyPair) -> None:
        self.public_ring[user_id] = PublicRingEntry(user_id, keypair.public_tuple())
        self.private_ring[user_id] = PrivateRingEntry(user_id, keypair)


# --- PGP message construction -------------------------------------------------


def pgp_encrypt_and_sign(
    sender_priv: RSAKeyPair,
    recipient_pub: Tuple[int, int],
    plaintext: bytes,
) -> Dict[str, bytes]:
    digest = hashlib.sha256(plaintext).digest()
    digest_int = int.from_bytes(digest, "big")
    if digest_int >= recipient_pub[0]:
        raise ValueError("plaintext digest exceeds RSA modulus")
    signature_int = pow(digest_int, sender_priv.d, sender_priv.n)
    sig_len = (sender_priv.n.bit_length() + 7) // 8
    signature = signature_int.to_bytes(sig_len, "big")
    session_key = os.urandom(16)
    ciphertext, iv = stream_encrypt(session_key, plaintext)
    key_int = int.from_bytes(session_key, "big")
    wrapped_int = pow(key_int, recipient_pub[1], recipient_pub[0])
    wrap_len = (recipient_pub[0].bit_length() + 7) // 8
    wrapped = wrapped_int.to_bytes(wrap_len, "big")
    return {
        "signature": signature,
        "wrapped_key": wrapped,
        "iv": iv,
        "ciphertext": ciphertext,
    }


def pgp_verify_and_decrypt(
    sender_pub: Tuple[int, int],
    recipient_priv: RSAKeyPair,
    packet: Dict[str, bytes],
) -> bytes:
    sig_int = int.from_bytes(packet["signature"], "big")
    digest_int = pow(sig_int, sender_pub[1], sender_pub[0])
    recovered_digest = digest_int.to_bytes(32, "big")
    wrapped_int = int.from_bytes(packet["wrapped_key"], "big")
    key_int = pow(wrapped_int, recipient_priv.d, recipient_priv.n)
    session_key = key_int.to_bytes(16, "big")
    plaintext = stream_decrypt(session_key, packet["ciphertext"], packet["iv"])
    actual = hashlib.sha256(plaintext).digest()
    if not hmac.compare_digest(recovered_digest, actual):
        raise ValueError("PGP signature verification failed")
    return plaintext


# --- Web of trust -------------------------------------------------------------


def compute_validity(
    target_user: str,
    ring: KeyRing,
    threshold_marginal: int = 2,
) -> str:
    weights = {"unknown": 0, "never": 0, "marginal": 1, "full": 2, "ultimate": 3}
    score = 0
    for introducer in ring.public_ring[target_user].signatures:
        if introducer in ring.public_ring:
            score += weights[ring.public_ring[introducer].ownertrust]
    if score >= 2 * threshold_marginal:
        return "full"
    if score >= threshold_marginal:
        return "marginal"
    return "unknown"


# --- ASCII armor --------------------------------------------------------------


def armor(packet: Dict[str, bytes]) -> str:
    raw = b"".join(
        [
            struct.pack(">I", len(packet["signature"]))[1:] + packet["signature"],
            struct.pack(">I", len(packet["wrapped_key"]))[1:] + packet["wrapped_key"],
            struct.pack(">I", len(packet["iv"]))[1:] + packet["iv"],
            packet["ciphertext"],
        ]
    )
    body = base64.b64encode(raw).decode("ascii")
    return (
        "-----BEGIN PGP MESSAGE-----\n\n"
        + "\n".join(body[i : i + 64] for i in range(0, len(body), 64))
        + "\n-----END PGP MESSAGE-----\n"
    )


def main() -> None:
    ring = KeyRing()
    ring.add_user("alice@example.com", generate_rsa(1024))
    ring.add_user("bob@example.com", generate_rsa(1024))

    plaintext = (
        b"From: Alice. To: Bob. The gold shipment leaves tonight from pier 7. "
        b"Please run the headline for the morning edition."
    )
    packet = pgp_encrypt_and_sign(
        ring.private_ring["alice@example.com"].priv,
        ring.public_ring["bob@example.com"].pub,
        plaintext,
    )
    print("PGP packet components:")
    for k, v in packet.items():
        print(f"  {k:11s} = {len(v)} bytes")

    recovered = pgp_verify_and_decrypt(
        ring.public_ring["alice@example.com"].pub,
        ring.private_ring["bob@example.com"].priv,
        packet,
    )
    assert recovered == plaintext
    print("PGP round-trip OK: SHA-256 verified, stream recovered, RSA unwrap OK")

    ring.public_ring["bob@example.com"].ownertrust = "full"
    ring.public_ring["bob@example.com"].signatures.append("alice@example.com")
    print(
        "Validity of bob's key under web of trust: "
        + compute_validity("bob@example.com", ring)
    )

    print("\nASCII-armored PGP message:")
    print(armor(packet))


if __name__ == "__main__":
    main()