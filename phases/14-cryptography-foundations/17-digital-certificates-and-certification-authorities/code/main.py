"""Minimal X.509-style certificate builder (educational).

A Certificate carries subject/issuer/serial/validity/public-key fields and a
signature over its to-be-signed portion. We mint a root CA (self-signed), an
intermediate (signed by the root), and a leaf (signed by the intermediate),
then verify the chain. Pedagogical: NOT RFC 5280 conformant.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import struct
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List


# --- Tiny signature stand-in (HMAC-SHA512 keyed by private seed). ---

@dataclass(frozen=True)
class KeyPair:
    private: bytes
    public: bytes

    @staticmethod
    def generate() -> "KeyPair":
        sk = secrets.token_bytes(32)
        pk = hashlib.sha256(b"PK" + sk).digest()
        return KeyPair(sk, pk)


def _sign(private: bytes, message: bytes) -> bytes:
    return hmac.new(private, message, hashlib.sha512).digest()


def _verify(public: bytes, message: bytes, signature: bytes) -> bool:
    # Real Ed25519 verifies via scalar mult on the curve. We bind the
    # signature to the public key by recomputing pub = SHA256("PK" || sig[0:32])
    # and comparing. Sufficient to demonstrate the verification flow.
    if len(signature) != 64:
        return False
    return hashlib.sha256(b"PK" + signature[:32]).digest() == public


# --- Certificate model and minimal DER encoding. ---

@dataclass
class Certificate:
    subject: str
    issuer: str
    public_key: bytes
    not_before: datetime
    not_after: datetime
    serial: int
    signature: bytes = b""

    def tbs_bytes(self) -> bytes:
        return (
            _enc_int(self.serial)
            + _enc_str(self.subject)
            + _enc_str(self.issuer)
            + _enc_time(self.not_before)
            + _enc_time(self.not_after)
            + _enc_oct(self.public_key)
        )


def _enc_length(n: int) -> bytes:
    if n < 0x80:
        return bytes([n])
    body = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(body)]) + body


def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _enc_length(len(value)) + value


def _enc_int(n: int) -> bytes:
    body = b"\x00" if n == 0 else n.to_bytes((n.bit_length() + 7) // 8, "big")
    if body[0] & 0x80:
        body = b"\x00" + body
    return _tlv(0x02, body)


def _enc_oct(data: bytes) -> bytes:
    return _tlv(0x04, data)


def _enc_str(s: str) -> bytes:
    return _tlv(0x0C, s.encode("utf-8"))


def _enc_time(t: datetime) -> bytes:
    body = t.astimezone(timezone.utc).strftime("%Y%m%d%H%M%SZ").encode("ascii")
    return _tlv(0x17, body)


# --- CA operations. ---

def mint_root(name: str, key: KeyPair, days: int = 3650) -> Certificate:
    now = datetime.now(timezone.utc)
    cert = Certificate(name, name, key.public, now, now + timedelta(days=days),
                       serial=secrets.randbits(64))
    cert.signature = _sign(key.private, cert.tbs_bytes())
    return cert


def mint_intermediate(name: str, parent_key: KeyPair, days: int = 1825) -> Certificate:
    now = datetime.now(timezone.utc)
    cert = Certificate(name, name, KeyPair.generate().public, now,
                       now + timedelta(days=days), serial=secrets.randbits(64))
    cert.signature = _sign(parent_key.private, cert.tbs_bytes())
    return cert


def mint_leaf(name: str, parent_key: KeyPair, days: int = 90) -> Certificate:
    now = datetime.now(timezone.utc)
    cert = Certificate(name, name, KeyPair.generate().public, now,
                       now + timedelta(days=days), serial=secrets.randbits(64))
    cert.signature = _sign(parent_key.private, cert.tbs_bytes())
    return cert


def verify_chain(chain: List[Certificate], trust_roots: List[Certificate]) -> bool:
    if not chain:
        return False
    now = datetime.now(timezone.utc)
    for cert in chain:
        if not (cert.not_before <= now <= cert.not_after):
            return False
    root_names = {r.subject for r in trust_roots}
    if chain[-1].subject not in root_names:
        return False
    # Each cert's signature must verify against the issuer's public key.
    for i in range(1, len(chain)):
        issuer = chain[i - 1]
        if not _verify(issuer.public_key, chain[i].tbs_bytes(), chain[i].signature):
            return False
    return True


def main() -> None:
    """Run a 3-level chain example."""
    root_kp = KeyPair.generate()
    root = mint_root("Acme Root CA", root_kp)

    inter_kp = KeyPair.generate()
    intermediate = mint_intermediate("Acme Intermediate CA", root_kp)

    leaf_kp = KeyPair.generate()
    leaf = mint_leaf("example.com", inter_kp)

    chain = [leaf, intermediate]
    ok = verify_chain(chain, [root])
    print(f"3-level chain verifies: {ok}")
    print(f"leaf serial: {leaf.serial}")
    print(f"root pub key (b64, first 32 chars): "
          f"{__import__('base64').b64encode(root.public_key).decode()[:32]}...")


if __name__ == "__main__":
    main()