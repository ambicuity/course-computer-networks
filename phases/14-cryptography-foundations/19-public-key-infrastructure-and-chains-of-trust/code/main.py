"""PKI chain validator (educational).

We model minimal Certificate objects, build a 3-level chain (root ->
intermediate -> leaf), and validate it. The validator emits a per-step
report so failures are explicit. Pedagogical: NOT RFC 5280 conformant;
no ASN.1, no CRL/OCSP, no EKU/policy enforcement.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional


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
    if len(signature) != 64:
        return False
    return hashlib.sha256(b"PK" + signature[:32]).digest() == public


@dataclass
class Certificate:
    subject: str
    issuer: str
    public_key: bytes
    not_before: datetime
    not_after: datetime
    serial: int
    is_ca: bool = False
    path_length: int = 0
    key_usage: int = 0
    signature: bytes = b""
    revoked: bool = False

    def tbs_bytes(self) -> bytes:
        return (
            self.subject.encode()
            + self.issuer.encode()
            + self.public_key
            + str(self.not_before.timestamp()).encode()
            + str(self.not_after.timestamp()).encode()
        )


# Bit values for KeyUsage.
KU_DIGITAL_SIGNATURE = 1 << 0
KU_KEY_CERT_SIGN = 1 << 5
KU_CRL_SIGN = 1 << 6


def mint_root(name: str, key: KeyPair, days: int = 3650) -> Certificate:
    now = datetime.now(timezone.utc)
    cert = Certificate(
        subject=name,
        issuer=name,
        public_key=key.public,
        not_before=now,
        not_after=now + timedelta(days=days),
        serial=secrets.randbits(64),
        is_ca=True,
        path_length=2,
        key_usage=KU_KEY_CERT_SIGN | KU_CRL_SIGN,
    )
    cert.signature = _sign(key.private, cert.tbs_bytes())
    return cert


def mint_intermediate(name: str, parent_key: KeyPair, path_length: int = 1,
                       days: int = 1825) -> Certificate:
    now = datetime.now(timezone.utc)
    cert = Certificate(
        subject=name,
        issuer=name,
        public_key=KeyPair.generate().public,
        not_before=now,
        not_after=now + timedelta(days=days),
        serial=secrets.randbits(64),
        is_ca=True,
        path_length=path_length,
        key_usage=KU_KEY_CERT_SIGN | KU_CRL_SIGN,
    )
    cert.signature = _sign(parent_key.private, cert.tbs_bytes())
    return cert


def mint_leaf(name: str, parent_key: KeyPair, days: int = 90) -> Certificate:
    now = datetime.now(timezone.utc)
    cert = Certificate(
        subject=name,
        issuer=name,
        public_key=KeyPair.generate().public,
        not_before=now,
        not_after=now + timedelta(days=days),
        serial=secrets.randbits(64),
        is_ca=False,
        key_usage=KU_DIGITAL_SIGNATURE,
    )
    cert.signature = _sign(parent_key.private, cert.tbs_bytes())
    return cert


@dataclass
class Step:
    name: str
    ok: bool
    detail: str


@dataclass
class ValidationReport:
    steps: List[Step] = field(default_factory=list)
    ok: bool = True
    revoked_serials: set[int] = field(default_factory=set)

    def add(self, name: str, ok: bool, detail: str = "") -> None:
        self.steps.append(Step(name, ok, detail))
        if not ok:
            self.ok = False


class ChainValidator:
    def __init__(self) -> None:
        self.trust_roots: List[Certificate] = []
        self.revoked: set[int] = set()

    def add_trust_root(self, cert: Certificate) -> None:
        self.trust_roots.append(cert)

    def revoke(self, serial: int) -> None:
        self.revoked.add(serial)

    def validate(self, chain: List[Certificate],
                 now: Optional[datetime] = None) -> ValidationReport:
        report = ValidationReport()
        if not chain:
            report.add("chain-not-empty", False, "chain is empty")
            return report
        now = now or datetime.now(timezone.utc)
        # Walk down from the leaf, attaching the parent at each step.
        parents = chain[1:] + [None]
        depth = 0
        cert: Optional[Certificate] = chain[0]
        parent: Optional[Certificate] = parents[0]
        # Find a trust root matching the top of the chain.
        root_match = None
        if parent is None:
            for r in self.trust_roots:
                if r.subject == cert.issuer:
                    root_match = r
                    break
        # If we have intermediates, root_match may be the last intermediate.
        for r in self.trust_roots:
            if chain[-1].issuer == r.subject:
                root_match = r
        report.add(
            "trust-root-found",
            root_match is not None,
            f"trust root subject = {root_match.subject if root_match else 'none'}",
        )
        if root_match is None:
            return report
        # Iterate from leaf up to the topmost intermediate, with parent.
        for i, cert in enumerate(chain):
            signer = parents[i] if i < len(parents) else root_match
            if signer is None:
                continue
            report.add(
                f"name-chain[{cert.subject}]",
                cert.issuer == signer.subject,
                f"cert.issuer={cert.issuer} signer.subject={signer.subject}",
            )
            report.add(
                f"signature[{cert.subject}]",
                _verify(signer.public_key, cert.tbs_bytes(), cert.signature),
                f"serial={cert.serial}",
            )
            report.add(
                f"validity[{cert.subject}]",
                cert.not_before <= now <= cert.not_after,
                f"now={now.isoformat()}",
            )
            report.add(
                f"revocation[{cert.subject}]",
                cert.serial not in self.revoked,
                f"serial={cert.serial}",
            )
            if signer.is_ca and depth >= signer.path_length:
                report.add(
                    f"path-length[{cert.subject}]",
                    False,
                    f"depth={depth} > pathLen={signer.path_length}",
                )
            depth += 1
        return report


def main() -> None:
    """Build a 3-level chain, validate it, then introduce failures."""
    root_kp = KeyPair.generate()
    root = mint_root("Acme Root", root_kp)
    inter_kp = KeyPair.generate()
    intermediate = mint_intermediate("Acme Intermediate", root_kp, path_length=1)
    leaf_kp = KeyPair.generate()
    leaf = mint_leaf("example.com", inter_kp)

    v = ChainValidator()
    v.add_trust_root(root)
    report = v.validate([leaf, intermediate])
    print(f"happy-path valid: {report.ok}")
    for step in report.steps:
        print(f"  [{step.name}] ok={step.ok}  {step.detail}")

    # Break it: revoke the leaf.
    v.revoke(leaf.serial)
    report2 = v.validate([leaf, intermediate])
    print(f"after leaf revocation: ok={report2.ok}")


if __name__ == "__main__":
    main()