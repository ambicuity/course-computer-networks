#!/usr/bin/env python3
"""Public Key Infrastructure (PKI) Simulator (textbook Sec 8.5).

Stdlib only. Demonstrates:

1. CA hierarchy: root CA (self-signed), intermediate CA, end-entity certificates.
2. Certificate issuance: CA validates identity, signs certificate with CA key.
3. Chain validation: verify signatures from end-entity up to root trust anchor.
4. Revocation: CRL (Certificate Revocation List) and OCSP query simulation.
5. Trust models: hierarchical, web of trust, bridge CA.

Run:  python3 main.py
"""
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass, field
from enum import Enum


class CertStatus(Enum):
    VALID = "valid"
    EXPIRED = "expired"
    REVOKED = "revoked"
    UNTRUSTED = "untrusted"
    BROKEN_CHAIN = "broken_chain"


@dataclass
class Certificate:
    subject: str
    issuer: str
    public_key: str
    serial: int
    not_before: float
    not_after: float
    signature: str = ""
    is_ca: bool = False
    self_signed: bool = False

    def is_expired(self, now: float) -> bool:
        return now < self.not_before or now > self.not_after


@dataclass
class CA:
    name: str
    private_key: str
    public_key: str
    certificate: Certificate
    crl: set[int] = field(default_factory=set)
    ocsp_cache: dict[int, CertStatus] = field(default_factory=dict)

    def sign_cert(self, subject: str, subject_pubkey: str, valid_days: float,
                  is_ca: bool = False, now: float = 0.0) -> Certificate:
        cert = Certificate(
            subject=subject,
            issuer=self.name,
            public_key=subject_pubkey,
            serial=hashlib.sha256(f"{subject}{time.time()}".encode()).hexdigest()[:8],
            not_before=now,
            not_after=now + valid_days * 86400,
            is_ca=is_ca,
        )
        msg = f"{cert.subject}|{cert.issuer}|{cert.public_key}|{cert.serial}|{cert.not_before}|{cert.not_after}"
        cert.signature = hmac.new(self.private_key.encode(), msg.encode(), hashlib.sha256).hexdigest()
        return cert

    def revoke(self, serial: int) -> None:
        self.crl.add(serial)

    def check_crl(self, cert: Certificate) -> bool:
        return int(cert.serial, 16) in {int(s, 16) if isinstance(s, str) else s for s in self.crl}

    def ocsp_respond(self, cert: Certificate) -> CertStatus:
        serial_int = int(cert.serial, 16)
        if serial_int in {int(s) for s in self.crl}:
            return CertStatus.REVOKED
        if cert.is_expired(time.time()):
            return CertStatus.EXPIRED
        return CertStatus.VALID


@dataclass
class TrustStore:
    roots: dict[str, Certificate] = field(default_factory=dict)

    def add_root(self, cert: Certificate) -> None:
        if cert.self_signed and cert.is_ca:
            self.roots[cert.subject] = cert

    def is_trusted(self, cert: Certificate) -> bool:
        return cert.subject in self.roots


def verify_signature(cert: Certificate, ca: CA) -> bool:
    msg = f"{cert.subject}|{cert.issuer}|{cert.public_key}|{cert.serial}|{cert.not_before}|{cert.not_after}"
    expected = hmac.new(ca.private_key.encode(), msg.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(cert.signature, expected)


def validate_chain(
    chain: list[Certificate],
    cas: dict[str, CA],
    trust_store: TrustStore,
    now: float,
    use_ocsp: bool = False,
) -> tuple[bool, str]:
    if not chain:
        return False, "Empty chain"

    for i in range(len(chain) - 1):
        cert = chain[i]
        issuer_name = cert.issuer
        if issuer_name not in cas:
            return False, f"No CA found for issuer '{issuer_name}'"
        issuer_ca = cas[issuer_name]
        if not verify_signature(cert, issuer_ca):
            return False, f"Signature verification failed for {cert.subject}"
        if cert.is_expired(now):
            return False, f"Certificate expired: {cert.subject}"

        if use_ocsp:
            status = issuer_ca.ocsp_respond(cert)
            if status != CertStatus.VALID:
                return False, f"OCSP: {cert.subject} status={status.value}"
        else:
            serial_int = int(cert.serial, 16)
            if serial_int in {int(s) for s in issuer_ca.crl}:
                return False, f"Certificate revoked (CRL): {cert.subject}"

    root_cert = chain[-1]
    if not trust_store.is_trusted(root_cert):
        return False, f"Root CA '{root_cert.subject}' not in trust store"
    if not root_cert.self_signed:
        return False, f"Root certificate is not self-signed: {root_cert.subject}"
    if root_cert.is_expired(now):
        return False, f"Root CA certificate expired: {root_cert.subject}"

    return True, "Chain valid: all signatures verified, root trusted"


def main() -> None:
    print("=" * 65)
    print("PKI Simulator: CA Hierarchy and Certificate Issuance")
    print("=" * 65)

    root_ca = CA(
        name="Root CA",
        private_key="root_secret_key_12345",
        public_key="root_pubkey",
        certificate=Certificate(
            subject="Root CA", issuer="Root CA", public_key="root_pubkey",
            serial="000001", not_before=0, not_after=1e18, is_ca=True, self_signed=True,
        ),
    )

    intermediate_ca = CA(
        name="Intermediate CA",
        private_key="intermediate_secret_key",
        public_key="intermediate_pubkey",
        certificate=root_ca.sign_cert("Intermediate CA", "intermediate_pubkey", valid_days=3650, is_ca=True, now=0),
    )

    end_entity_cert = intermediate_ca.sign_cert("example.com", "ee_public_key_abc", valid_days=90, now=0)

    print(f"\n  Root CA:        {root_ca.name}")
    print(f"    Self-signed:  {root_ca.certificate.self_signed}")
    print(f"    Is CA:        {root_ca.certificate.is_ca}")
    print(f"    Serial:       {root_ca.certificate.serial}")

    print(f"\n  Intermediate:   {intermediate_ca.name}")
    print(f"    Issued by:    {intermediate_ca.certificate.issuer}")
    print(f"    Serial:       {intermediate_ca.certificate.serial}")
    print(f"    Is CA:        {intermediate_ca.certificate.is_ca}")

    print(f"\n  End-Entity:     {end_entity_cert.subject}")
    print(f"    Issued by:    {end_entity_cert.issuer}")
    print(f"    Public key:   {end_entity_cert.public_key}")
    print(f"    Serial:       {end_entity_cert.serial}")

    print()
    print("=" * 65)
    print("Chain Validation")
    print("=" * 65)

    trust_store = TrustStore()
    trust_store.add_root(root_ca.certificate)

    cas = {"Root CA": root_ca, "Intermediate CA": intermediate_ca}
    chain = [end_entity_cert, intermediate_ca.certificate, root_ca.certificate]

    print(f"\n  Chain: {' -> '.join(c.subject for c in chain)}")
    valid, reason = validate_chain(chain, cas, trust_store, now=time.time())
    print(f"  Result: {'VALID' if valid else 'INVALID'} - {reason}")

    print(f"\n  Test: Expired end-entity certificate:")
    expired_cert = intermediate_ca.sign_cert("expired.com", "ee_key", valid_days=1, now=-100000)
    expired_chain = [expired_cert, intermediate_ca.certificate, root_ca.certificate]
    valid, reason = validate_chain(expired_chain, cas, trust_store, now=time.time())
    print(f"  Result: {'VALID' if valid else 'INVALID'} - {reason}")

    print(f"\n  Test: Revoked certificate (via CRL):")
    revoked_cert = intermediate_ca.sign_cert("revoked.com", "ee_key_rev", valid_days=90, now=0)
    intermediate_ca.revoke(int(revoked_cert.serial, 16))
    revoked_chain = [revoked_cert, intermediate_ca.certificate, root_ca.certificate]
    valid, reason = validate_chain(revoked_chain, cas, trust_store, now=time.time())
    print(f"  Result: {'VALID' if valid else 'INVALID'} - {reason}")

    print(f"\n  Test: Revocation check via OCSP:")
    valid_cert = intermediate_ca.sign_cert("ocsp-test.com", "ee_key_ocsp", valid_days=90, now=0)
    ocsp_status = intermediate_ca.ocsp_respond(valid_cert)
    print(f"  OCSP status for {valid_cert.subject}: {ocsp_status.value}")
    intermediate_ca.revoke(int(valid_cert.serial, 16))
    ocsp_status_revoked = intermediate_ca.ocsp_respond(valid_cert)
    print(f"  OCSP status after revocation: {ocsp_status_revoked.value}")

    print(f"\n  Test: Untrusted root CA:")
    untrusted_root = CA("Fake Root", "fake_key", "fake_pub", Certificate(
        "Fake Root", "Fake Root", "fake_pub", "999", 0, 1e18, is_ca=True, self_signed=True))
    fake_inter = CA("Fake Inter", "fake_inter_key", "fake_inter_pub",
                    untrusted_root.sign_cert("Fake Inter", "fake_inter_pub", 365, is_ca=True, now=0))
    fake_ee = fake_inter.sign_cert("evil.com", "evil_key", 90, now=0)
    fake_chain = [fake_ee, fake_inter.certificate, untrusted_root.certificate]
    fake_cas = {"Fake Root": untrusted_root, "Fake Inter": fake_inter}
    valid, reason = validate_chain(fake_chain, fake_cas, trust_store, now=time.time())
    print(f"  Result: {'VALID' if valid else 'INVALID'} - {reason}")

    print()
    print("=" * 65)
    print("Trust Models Comparison")
    print("=" * 65)
    print(f"  {'Model':15s} {'Structure':20s} {'Trust Source':20s} {'Example'}")
    print(f"  {'-'*15} {'-'*20} {'-'*20} {'-'*15}")
    print(f"  {'Hierarchical':15s} {'Tree (root->leaf)':20s} {'Pre-installed root':20s} {'X.509/Web PKI'}")
    print(f"  {'Web of Trust':15s} {'Peer-to-peer graph':20s} {'Personal signatures':20s} {'PGP/GPG'}")
    print(f"  {'Bridge CA':15s} {'Cross-certified':20s} {'Multiple roots':20s} {'Federal PKI'}")

    print()
    print("=" * 65)
    print("CRL vs OCSP Tradeoffs")
    print("=" * 65)
    print(f"  {'Aspect':20s} {'CRL':25s} {'OCSP'}")
    print(f"  {'-'*20} {'-'*25} {'-'*25}")
    print(f"  {'Freshness':20s} {'Stale (hours/days)':25s} {'Real-time'}")
    print(f"  {'Latency':20s} {'Low (cached download)':25s} {'High (network query)'}")
    print(f"  {'Bandwidth':20s} {'High (full list)':25s} {'Low (single query)'}")
    print(f"  {'Privacy':20s} {'Private (no query)':25s} {'CA learns site visits'}")
    print(f"  {'Failure mode':20s} {'Stale revocation':25s} {'Soft-fail = accept'}")


if __name__ == "__main__":
    main()
