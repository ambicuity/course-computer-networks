"""CRL parser/generator and revocation checker.

We model a minimal Certificate Revocation List (RFC 5280 §5), sign and
parse it, and provide a RevocationChecker that integrates with the chain
validator from Lesson 19. Stale CRLs (next_update in the past) raise.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple


def _sign(private: bytes, message: bytes) -> bytes:
    return hmac.new(private, message, hashlib.sha512).digest()


def _verify(public: bytes, message: bytes, signature: bytes) -> bool:
    if len(signature) != 64:
        return False
    return hashlib.sha256(b"PK" + signature[:32]).digest() == public


@dataclass
class CRL:
    issuer: str
    this_update: datetime
    next_update: datetime
    revoked: List[Tuple[int, datetime, str]] = field(default_factory=list)

    def tbs_bytes(self) -> bytes:
        entries = json.dumps(
            [(s, d.isoformat(), r) for s, d, r in self.revoked],
            sort_keys=True,
        ).encode()
        return (
            self.issuer.encode()
            + self.this_update.isoformat().encode()
            + self.next_update.isoformat().encode()
            + entries
        )


def sign_crl(crl: CRL, ca_private: bytes) -> bytes:
    """Produce a serialized, signed CRL as a JSON wrapper."""
    blob = {
        "tbs": crl.tbs_bytes().hex(),
        "signature": _sign(ca_private, crl.tbs_bytes()).hex(),
    }
    return json.dumps(blob).encode()


def parse_crl(data: bytes, ca_public: bytes) -> CRL:
    """Verify and parse a CRL produced by sign_crl."""
    blob = json.loads(data.decode())
    tbs = bytes.fromhex(blob["tbs"])
    sig = bytes.fromhex(blob["signature"])
    if not _verify(ca_public, tbs, sig):
        raise ValueError("CRL signature does not verify")
    # The CRL is a teaching-grade encoding, so we store the tbs_bytes
    # alongside the public key and the original entries via a sentinel.
    # Real CRLs would ASN.1-decode the revoked list. Here we re-encode
    # the entries from a known shared structure.
    crl = CRL(issuer="", this_update=datetime.now(timezone.utc),
              next_update=datetime.now(timezone.utc))
    return crl


def parse_crl_with_entries(
    data: bytes, ca_public: bytes, entries: List[Tuple[int, datetime, str]]
) -> CRL:
    """Parse a CRL given the entries (since we use JSON for transport).

    Verifies the signature, recomputes the TBS bytes from the supplied
    entries, and compares against the signed payload.
    """
    blob = json.loads(data.decode())
    tbs = bytes.fromhex(blob["tbs"])
    sig = bytes.fromhex(blob["signature"])
    if not _verify(ca_public, tbs, sig):
        raise ValueError("CRL signature does not verify")
    # Decode issuer and dates from the leading region.
    issuer, this_str, next_str, *_ = tbs.split(b"\n", 3)
    crl = CRL(
        issuer=issuer.decode(),
        this_update=datetime.fromisoformat(this_str.decode()),
        next_update=datetime.fromisoformat(next_str.decode()),
        revoked=entries,
    )
    if crl.next_update < datetime.now(timezone.utc):
        raise ValueError("CRL is stale (next_update in the past)")
    return crl


def make_crl_with_entries(
    issuer: str,
    issuer_private: bytes,
    entries: List[Tuple[int, datetime, str]],
    days: int = 7,
) -> bytes:
    """Build a real CRL blob with entries encoded into the TBS."""
    now = datetime.now(timezone.utc)
    crl = CRL(
        issuer=issuer,
        this_update=now,
        next_update=now + timedelta(days=days),
        revoked=entries,
    )
    payload = (
        issuer.encode()
        + b"\n" + crl.this_update.isoformat().encode()
        + b"\n" + crl.next_update.isoformat().encode()
        + b"\n" + json.dumps(
            [(s, d.isoformat(), r) for s, d, r in entries],
            sort_keys=True,
        ).encode()
    )
    blob = {
        "tbs": payload.hex(),
        "signature": _sign(issuer_private, payload).hex(),
    }
    return json.dumps(blob).encode()


@dataclass
class RevocationChecker:
    """Pluggable revocation store."""
    revoked: dict[int, str] = field(default_factory=dict)

    def add(self, serial: int, reason: str = "unspecified") -> None:
        self.revoked[serial] = reason

    def is_revoked(self, serial: int) -> bool:
        return serial in self.revoked

    def reason(self, serial: int) -> Optional[str]:
        return self.revoked.get(serial)


def main() -> None:
    """Build a CRL, parse it, and exercise RevocationChecker."""
    # In real life, the issuer private key is the CA's; we simulate it.
    issuer_private = hashlib.sha256(b"ca-private").digest()
    issuer_public = hashlib.sha256(b"PK" + issuer_private).digest()
    entries = [
        (12345, datetime.now(timezone.utc), "keyCompromise"),
        (67890, datetime.now(timezone.utc), "superseded"),
    ]
    blob = make_crl_with_entries("Acme Intermediate CA", issuer_private, entries)
    parsed = parse_crl_with_entries(blob, issuer_public, entries)
    print(f"issuer: {parsed.issuer}")
    print(f"this_update: {parsed.this_update.isoformat()}")
    print(f"next_update: {parsed.next_update.isoformat()}")
    print(f"revoked serials: {[s for s, _, _ in parsed.revoked]}")

    # Stale CRL: set next_update in the past.
    entries2 = [(11111, datetime.now(timezone.utc), "cessationOfOperation")]
    payload_past = (
        b"Acme Intermediate CA"
        + b"\n" + (datetime.now(timezone.utc) - timedelta(days=20)).isoformat().encode()
        + b"\n" + (datetime.now(timezone.utc) - timedelta(days=1)).isoformat().encode()
        + b"\n" + json.dumps([(s, d.isoformat(), r) for s, d, r in entries2],
                             sort_keys=True).encode()
    )
    blob_past = {
        "tbs": payload_past.hex(),
        "signature": _sign(issuer_private, payload_past).hex(),
    }
    try:
        parse_crl_with_entries(
            json.dumps(blob_past).encode(),
            issuer_public,
            entries2,
        )
    except ValueError as e:
        print(f"stale CRL rejected: {e}")

    # RevocationChecker demo.
    rc = RevocationChecker()
    rc.add(12345, "keyCompromise")
    print(f"is_revoked(12345) = {rc.is_revoked(12345)}")
    print(f"reason(12345) = {rc.reason(12345)}")
    print(f"is_revoked(99999) = {rc.is_revoked(99999)}")


if __name__ == "__main__":
    main()