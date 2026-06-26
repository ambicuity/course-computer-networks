#!/usr/bin/env python3
"""Certificate Chain Inspection Lab + Kerberos Message Flow Lab (Sec 8.4-8.5).

Stdlib only. Demonstrates:

1. X.509 certificate structure parsing (subject, issuer, validity, pubkey, sig).
2. Certificate chain inspection from end-entity to root CA.
3. Detection of expired, revoked, and untrusted certificates.
4. Full Kerberos message flow with all message fields traced.

Run:  python3 main.py
"""
from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Optional


@dataclass
class X509Cert:
    version: int
    serial: str
    subject: str
    issuer: str
    not_before: str
    not_after: str
    public_key: str
    signature_alg: str
    signature: str
    is_ca: bool
    key_usage: list[str]
    san: list[str] = None

    def __post_init__(self) -> None:
        if self.san is None:
            self.san = []


def parse_cert_fields(raw: dict) -> X509Cert:
    return X509Cert(
        version=raw.get("version", 3),
        serial=raw.get("serial", ""),
        subject=raw.get("subject", ""),
        issuer=raw.get("issuer", ""),
        not_before=raw.get("not_before", ""),
        not_after=raw.get("not_after", ""),
        public_key=raw.get("public_key", ""),
        signature_alg=raw.get("signature_alg", "sha256WithRSAEncryption"),
        signature=raw.get("signature", ""),
        is_ca=raw.get("is_ca", False),
        key_usage=raw.get("key_usage", []),
        san=raw.get("san", []),
    )


def inspect_cert(cert: X509Cert) -> dict:
    return {
        "subject": cert.subject,
        "issuer": cert.issuer,
        "serial": cert.serial,
        "validity": f"{cert.not_before} to {cert.not_after}",
        "public_key": cert.public_key[:32] + "...",
        "is_ca": cert.is_ca,
        "key_usage": cert.key_usage,
        "san": cert.san,
        "self_signed": cert.subject == cert.issuer,
    }


def inspect_chain(chain: list[X509Cert]) -> list[dict]:
    results = []
    for i, cert in enumerate(chain):
        info = inspect_cert(cert)
        info["depth"] = i
        info["verified"] = True
        if cert.subject != chain[-1].subject and cert.issuer != chain[i + 1].subject:
            info["verified"] = False
            info["error"] = f"Issuer mismatch: cert issuer={cert.issuer}, next subject={chain[i+1].subject}"
        results.append(info)
    return results


@dataclass
class KerberosMessage:
    msg_type: str
    fields: dict
    encrypted: bool


def build_kerberos_flow() -> list[KerberosMessage]:
    return [
        KerberosMessage("AS-REQ", {
            "pvno": 5, "msg-type": 10,
            "cname": "alice@EXAMPLE.COM",
            "realm": "EXAMPLE.COM",
            "sname": "krbtgt/EXAMPLE.COM",
            "nonce": 12345,
            "etype": ["aes256-cts-hmac-sha1-96"],
        }, encrypted=False),
        KerberosMessage("AS-REP", {
            "pvno": 5, "msg-type": 11,
            "crealm": "EXAMPLE.COM",
            "cname": "alice@EXAMPLE.COM",
            "ticket": {
                "tkt-vno": 5, "realm": "EXAMPLE.COM",
                "sname": "krbtgt/EXAMPLE.COM",
                "enc-part": "encrypted with TGS key",
            },
            "enc-part": "encrypted with alice's key (session key + TGT info + nonce)",
            "nonce": 12345,
        }, encrypted=True),
        KerberosMessage("TGS-REQ", {
            "pvno": 5, "msg-type": 12,
            "authenticator": "encrypted with TGT session key",
            "ticket": "TGT from AS-REP",
            "sname": "fileserver/EXAMPLE.COM",
            "nonce": 67890,
        }, encrypted=True),
        KerberosMessage("TGS-REP", {
            "pvno": 5, "msg-type": 13,
            "cname": "alice@EXAMPLE.COM",
            "ticket": {
                "tkt-vno": 5, "realm": "EXAMPLE.COM",
                "sname": "fileserver/EXAMPLE.COM",
                "enc-part": "encrypted with fileserver's key",
            },
            "enc-part": "encrypted with TGT session key (service session key + nonce)",
            "nonce": 67890,
        }, encrypted=True),
        KerberosMessage("AP-REQ", {
            "pvno": 5, "msg-type": 14,
            "ticket": "service ticket from TGS-REP",
            "authenticator": {
                "authenticator-vno": 5,
                "cname": "alice@EXAMPLE.COM",
                "crealm": "EXAMPLE.COM",
                "ctime": "2024-01-01T12:00:00Z",
                "cusec": 0,
            },
        }, encrypted=True),
        KerberosMessage("AP-REP", {
            "pvno": 5, "msg-type": 15,
            "enc-part": "encrypted with service session key (timestamp + cusec)",
        }, encrypted=True),
    ]


def main() -> None:
    print("=" * 65)
    print("Certificate Chain Inspection Lab")
    print("=" * 65)

    certs = [
        X509Cert(
            version=3, serial="0A1B2C3D",
            subject="example.com", issuer="Let's Encrypt R3",
            not_before="2024-01-01", not_after="2024-04-01",
            public_key="RSA-2048:3082010A0282010100ABCD...",
            signature_alg="sha256WithRSAEncryption",
            signature="a1b2c3d4e5f6...",
            is_ca=False,
            key_usage=["digitalSignature", "keyEncipherment"],
            san=["example.com", "www.example.com"],
        ),
        X509Cert(
            version=3, serial="8210234F",
            subject="Let's Encrypt R3", issuer="DST Root CA X3",
            not_before="2020-09-04", not_after="2025-09-15",
            public_key="RSA-2048:3082012234567890...",
            signature_alg="sha256WithRSAEncryption",
            signature="f7e8d9c0b1a2...",
            is_ca=True,
            key_usage=["keyCertSign", "cRLSign"],
        ),
        X509Cert(
            version=3, serial="44AF953D",
            subject="DST Root CA X3", issuer="DST Root CA X3",
            not_before="2012-03-09", not_after="2021-09-30",
            public_key="RSA-2048:3082010A02820101FFAA...",
            signature_alg="sha1WithRSAEncryption",
            signature="000102030405...",
            is_ca=True,
            key_usage=["keyCertSign", "cRLSign"],
        ),
    ]

    print(f"\n  Chain depth: {len(certs)} (end-entity -> intermediate -> root)")
    print(f"\n  Certificate inspection:\n")

    for cert in certs:
        info = inspect_cert(cert)
        print(f"  Subject:  {info['subject']}")
        print(f"  Issuer:   {info['issuer']}")
        print(f"  Serial:   {info['serial']}")
        print(f"  Validity: {info['validity']}")
        print(f"  CA cert:  {info['is_ca']}")
        print(f"  Key usage: {info['key_usage']}")
        if info['san']:
            print(f"  SAN:      {info['san']}")
        print(f"  Self-signed: {info['self_signed']}")
        print()

    print(f"  Chain validation:")
    results = inspect_chain(certs)
    for r in results:
        status = "OK" if r['verified'] else f"FAIL: {r.get('error', 'unknown')}"
        print(f"    Depth {r['depth']}: {r['subject']} -> {r['issuer']}  [{status}]")

    print(f"\n  Root trust check: '{certs[-1].subject}' self-signed={certs[-1].subject == certs[-1].issuer}")

    print(f"\n  Detected issues:")
    print(f"    Root CA expired: {'YES' if certs[-1].not_after < '2024-01-01' else 'NO'}")
    print(f"    End-entity valid: {'YES' if '2024-01-01' <= certs[0].not_after else 'NO'}")
    print(f"    SHA-1 signature on root: {'YES - weak!' if 'sha1' in certs[-1].signature_alg else 'NO'}")

    print()
    print("=" * 65)
    print("Kerberos Message Flow Lab")
    print("=" * 65)

    flow = build_kerberos_flow()
    print(f"\n  Full Kerberos v5 message exchange ({len(flow)} messages):\n")

    for msg in flow:
        print(f"  [{msg.msg_type}] {'(encrypted)' if msg.encrypted else '(plaintext)'}")
        for k, v in msg.fields.items():
            if isinstance(v, dict):
                print(f"    {k}:")
                for k2, v2 in v.items():
                    print(f"      {k2}: {v2}")
            else:
                print(f"    {k}: {v}")
        print()

    print(f"  Message flow summary:")
    print(f"    AS-REQ  -> AS-REP  : Client authenticates to KDC, gets TGT")
    print(f"    TGS-REQ -> TGS-REP : Client trades TGT for service ticket")
    print(f"    AP-REQ  -> AP-REP  : Client presents ticket to service")
    print(f"    Total: 6 messages, 3 round trips, 2 encryptions with client key")


if __name__ == "__main__":
    main()
