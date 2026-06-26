"""Certificates to X.509: toy CA, certificate issuance and verification.

Demonstrates (Python stdlib only):
  1. A Certification Authority (CA) with an RSA keypair.
  2. Certificate issuance: bind a public key to a subject's X.500-style DN.
  3. X.509 V3 field model: Version, Serial, SigAlg, Issuer, Validity,
     Subject, PublicKey, Extensions, Signature.
  4. Verification: SHA-256(body) == E_CA(signature) and time in validity.
  5. Tamper detection: modify the public key after signing -> reject.
  6. The fake-home-page attack: Trudy presents her own cert -> caught.

Run: python3 main.py
"""

from __future__ import annotations

import hashlib
import random
import time
from dataclasses import dataclass, field, asdict
from typing import Any

# ---------------------------------------------------------------------------
# Toy RSA (educational; same as lesson 02)
# ---------------------------------------------------------------------------

def _is_prime(n: int, k: int = 20) -> bool:
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13):
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
    d: int
    e: int


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
    return pow(digest, key.d, key.n)


def rsa_verify_sig(key: RSAKey, digest: int, signature: int) -> bool:
    return pow(signature, key.e, key.n) == digest


# ---------------------------------------------------------------------------
# X.509 V3 certificate model
# ---------------------------------------------------------------------------

def _encode(body: dict[str, Any]) -> bytes:
    """Length-prefixed encoding (teaching substitute for ASN.1/DER)."""
    out = bytearray()
    for k in sorted(body):
        v = body[k]
        b = str(v).encode()
        out += k.encode().ljust(16, b"\x00")
        out += len(b).to_bytes(4, "big") + b
    return bytes(out)


@dataclass
class Certificate:
    version: int = 3
    serial: int = 0
    sig_algorithm: str = "sha256WithRSAEncryption"
    issuer: str = ""
    not_before: float = 0.0
    not_after: float = 0.0
    subject: str = ""
    public_key: int = 0
    extensions: dict[str, str] = field(default_factory=dict)
    signature: int = 0  # CA's signature over the TBS (to-be-signed) body

    def tbs_bytes(self) -> bytes:
        """The to-be-signed body (all fields except the signature)."""
        body = {
            "version": self.version,
            "serial": self.serial,
            "sig_algorithm": self.sig_algorithm,
            "issuer": self.issuer,
            "not_before": self.not_before,
            "not_after": self.not_after,
            "subject": self.subject,
            "public_key": self.public_key,
            "extensions": ",".join(f"{k}={v}" for k, v in self.extensions.items()),
        }
        return _encode(body)


@dataclass
class CA:
    name: str
    key: RSAKey = field(default_factory=lambda: rsa_keygen(64))
    next_serial: int = 1

    def issue(self, subject: str, subject_pubkey: int,
              validity_days: int = 365) -> Certificate:
        now = time.time()
        cert = Certificate(
            serial=self.next_serial,
            issuer=self.name,
            not_before=now,
            not_after=now + validity_days * 86400,
            subject=subject,
            public_key=subject_pubkey,
            extensions={"keyUsage": "digitalSignature,keyEncipherment",
                        "subjectAltName": "bob.moneybank.com"},
        )
        self.next_serial += 1
        body_hash = int.from_bytes(hashlib.sha256(cert.tbs_bytes()).digest(), "big")
        cert.signature = rsa_sign(self.key, body_hash % self.key.n)
        return cert


def verify_certificate(cert: Certificate, ca_key: RSAKey) -> tuple[bool, str]:
    body_hash = int.from_bytes(hashlib.sha256(cert.tbs_bytes()).digest(), "big") % ca_key.n
    if not rsa_verify_sig(ca_key, body_hash, cert.signature):
        return False, "signature mismatch (tampered or wrong CA)"
    now = time.time()
    if now < cert.not_before:
        return False, "not yet valid"
    if now > cert.not_after:
        return False, "expired"
    return True, "valid"


# ---------------------------------------------------------------------------
# Scenes
# ---------------------------------------------------------------------------

def run_normal_issuance() -> None:
    print("=" * 64)
    print("SCENE 1 - CA issues a certificate for Bob; Alice verifies")
    print("=" * 64)
    random.seed(42)
    ca = CA(name="MoneyBank Root CA")
    bob_key = rsa_keygen(64)
    cert = ca.issue(subject="/C=US/O=MoneyBank/OU=Loan/CN=Bob/",
                    subject_pubkey=bob_key.e * (10**40) + bob_key.n,
                    validity_days=365)
    print(f"Issued cert serial #{cert.serial} for {cert.subject}")
    print(f"  Issuer:   {cert.issuer}")
    print(f"  SigAlg:   {cert.sig_algorithm}")
    print(f"  Validity: {cert.not_before:.0f} -> {cert.not_after:.0f}")
    ok, reason = verify_certificate(cert, ca.key)
    print(f"  Verify:   {ok} ({reason})\n")


def run_tamper_detection() -> None:
    print("=" * 64)
    print("SCENE 2 - Tamper detection (public key modified after signing)")
    print("=" * 64)
    random.seed(42)
    ca = CA(name="MoneyBank Root CA")
    bob_key = rsa_keygen(64)
    cert = ca.issue(subject="/C=US/O=MoneyBank/OU=Loan/CN=Bob/",
                    subject_pubkey=bob_key.e * (10**40) + bob_key.n)
    ok1, r1 = verify_certificate(cert, ca.key)
    print(f"Original cert verify: {ok1} ({r1})")
    # Trudy tampers: replace public key
    cert.public_key = 999999
    ok2, r2 = verify_certificate(cert, ca.key)
    print(f"Tampered  cert verify: {ok2} ({r2})\n")


def run_fake_homepage_attack() -> None:
    print("=" * 64)
    print("SCENE 3 - Fake-home-page attack (Trudy presents her own cert)")
    print("=" * 64)
    random.seed(42)
    ca = CA(name="MoneyBank Root CA")
    bob_key = rsa_keygen(64)
    trudy_key = rsa_keygen(64)
    bob_cert = ca.issue(subject="/C=US/O=MoneyBank/OU=Loan/CN=Bob/",
                        subject_pubkey=bob_key.e * (10**40) + bob_key.n)
    # Trudy makes a cert claiming to be Bob but signed by... Trudy's own fake CA
    fake_ca = CA(name="Trudy's Fake CA")
    trudy_cert = fake_ca.issue(
        subject="/C=US/O=MoneyBank/OU=Loan/CN=Bob/",
        subject_pubkey=trudy_key.e * (10**40) + trudy_key.n)
    # Alice verifies Trudy's cert with the REAL CA's key
    ok, r = verify_certificate(trudy_cert, ca.key)
    print(f"Trudy's cert verified with real CA key: {ok} ({r})")
    print("Alice rejects Trudy's certificate.\n")


def run_expired_cert() -> None:
    print("=" * 64)
    print("SCENE 4 - Expired certificate (validity window check)")
    print("=" * 64)
    random.seed(42)
    ca = CA(name="MoneyBank Root CA")
    bob_key = rsa_keygen(64)
    cert = ca.issue(subject="/C=US/O=MoneyBank/OU=Loan/CN=Bob/",
                    subject_pubkey=bob_key.e * (10**40) + bob_key.n,
                    validity_days=1)
    # Force expiry: rewind not_before/not_after to the past
    cert.not_before = time.time() - 10_000_000
    cert.not_after = time.time() - 1_000_000
    # Re-sign because we changed the body
    body_hash = int.from_bytes(hashlib.sha256(cert.tbs_bytes()).digest(), "big") % ca.key.n
    cert.signature = rsa_sign(ca.key, body_hash)
    ok, r = verify_certificate(cert, ca.key)
    print(f"Expired cert verify: {ok} ({r})\n")


def main() -> None:
    run_normal_issuance()
    run_tamper_detection()
    run_fake_homepage_attack()
    run_expired_cert()
    print("All four scenes completed successfully.")


if __name__ == "__main__":
    main()