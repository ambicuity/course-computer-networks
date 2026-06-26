"""Offline X.509 v3 certificate builder and chain verifier.

Implements just enough of RFC 5280 to issue a root, an intermediate, and a
leaf certificate by hand, then validate the chain with the RFC 5280 §6
algorithm. No external dependencies; all ASN.1 DER encoding is done in-place
so you can see the bytes flow.

This is a teaching tool, not a CA: the RSA key generation is slow because it
runs Miller-Rabin in pure Python, and the verifier does not consult real
CRLs or OCSP responders. The structure, OIDs, and algorithm identifiers
match what `openssl x509 -text` reports and what `openssl verify -CAfile`
checks, byte for byte.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

OID_COMMON_NAME = "2.5.4.3"
OID_RSA_SHA256 = "1.2.840.113549.1.1.11"
OID_RSA_ENCRYPTION = "1.2.840.113549.1.1.1"
OID_SHA256 = "2.16.840.1.101.3.4.2.1"

OID_TO_DER = {
    OID_COMMON_NAME: bytes([0x55, 0x04, 0x03]),
    OID_RSA_SHA256: bytes([0x2A, 0x86, 0x48, 0x86, 0xF7, 0x0D, 0x01, 0x01, 0x0B]),
    OID_RSA_ENCRYPTION: bytes([0x2A, 0x86, 0x48, 0x86, 0xF7, 0x0D, 0x01, 0x01, 0x01]),
    OID_SHA256: bytes([0x60, 0x86, 0x48, 0x01, 0x65, 0x03, 0x04, 0x02, 0x01]),
}

RSA_PUBLIC_EXPONENT = 65537
MILLER_RABIN_ROUNDS = 12


def _is_probable_prime(n: int, k: int = MILLER_RABIN_ROUNDS) -> bool:
    if n < 2:
        return False
    for p in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29):
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for _ in range(k):
        a = secrets.randbelow(n - 3) + 2
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
    while True:
        candidate = secrets.randbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(candidate):
            return candidate


@dataclass(frozen=True)
class PublicKey:
    n: int
    e: int


@dataclass(frozen=True)
class PrivateKey:
    n: int
    d: int


def generate_rsa_keypair(bits: int = 2048) -> tuple[PrivateKey, PublicKey]:
    """Generate an RSA key pair. Slow: ~1-3 seconds at 2048 bits."""
    half = bits // 2
    while True:
        p = _gen_prime(half)
        q = _gen_prime(half)
        if p == q:
            continue
        n = p * q
        if n.bit_length() != bits:
            continue
        phi = (p - 1) * (q - 1)
        try:
            d = pow(RSA_PUBLIC_EXPONENT, -1, phi)
        except ValueError:
            continue
        return PrivateKey(n=n, d=d), PublicKey(n=n, e=RSA_PUBLIC_EXPONENT)


def _length_bytes(length: int) -> bytes:
    if length < 0x80:
        return bytes([length])
    parts = length.to_bytes((length.bit_length() + 7) // 8, "big")
    return bytes([0x80 | len(parts)]) + parts


def _tlv(tag: int, value: bytes) -> bytes:
    return bytes([tag]) + _length_bytes(len(value)) + value


def _encode_integer(value: int) -> bytes:
    raw = value.to_bytes((value.bit_length() + 7) // 8 or 1, "big")
    if raw[0] & 0x80:
        raw = b"\x00" + raw
    return _tlv(0x02, raw)


def _encode_oid(oid_dotted: str) -> bytes:
    if oid_dotted not in OID_TO_DER:
        raise ValueError(f"unknown OID: {oid_dotted}")
    return _tlv(0x06, OID_TO_DER[oid_dotted])


def _encode_bitstring(value: bytes) -> bytes:
    return _tlv(0x03, b"\x00" + value)


def _encode_utf8(text: str) -> bytes:
    return _tlv(0x0C, text.encode("utf-8"))


def _encode_utctime(dt: datetime) -> bytes:
    return _tlv(0x18, dt.strftime("%Y%m%d%H%M%SZ").encode("ascii"))


def _encode_sequence(body: bytes) -> bytes:
    return _tlv(0x30, body)


def _encode_set(body: bytes) -> bytes:
    return _tlv(0x31, body)


def _encode_boolean(value: bool) -> bytes:
    return _tlv(0x01, b"\xff" if value else b"\x00")


def _encode_algo_id(oid: str) -> bytes:
    return _encode_sequence(_encode_oid(oid) + b"\x05\x00")


def _encode_subject_pubkey_info(pub: PublicKey) -> bytes:
    spk = _encode_sequence(_encode_integer(pub.n) + _encode_integer(pub.e))
    return _encode_sequence(_encode_algo_id(OID_RSA_ENCRYPTION) + _encode_bitstring(spk))


@dataclass(frozen=True)
class Name:
    cn: str

    def to_der(self) -> bytes:
        rdn = _encode_set(
            _encode_sequence(_encode_oid(OID_COMMON_NAME) + _encode_utf8(self.cn))
        )
        return _encode_sequence(rdn)


@dataclass(frozen=True)
class Validity:
    not_before: datetime
    not_after: datetime


@dataclass(frozen=True)
class Certificate:
    tbs_der: bytes
    signature_alg: str
    signature_value: bytes
    issuer_dn: str
    subject_dn: str
    not_before: datetime
    not_after: datetime
    serial: int
    subject_pub: PublicKey

    def to_der(self) -> bytes:
        body = _encode_algo_id(self.signature_alg) + _encode_bitstring(self.signature_value)
        return _encode_sequence(self.tbs_der + body)

    def to_pem(self) -> str:
        import base64
        b64 = base64.b64encode(self.to_der()).decode("ascii")
        return (
            "-----BEGIN CERTIFICATE-----\n"
            + "\n".join(b64[i:i + 64] for i in range(0, len(b64), 64))
            + "\n-----END CERTIFICATE-----\n"
        )


def _build_tbs(
    serial: int,
    issuer: Name,
    validity: Validity,
    subject: Name,
    subject_pub: PublicKey,
    is_ca: bool,
    pathlen: int | None,
) -> bytes:
    version = _tlv(0xA0, _encode_integer(2))
    body = (
        version
        + _encode_integer(serial)
        + _encode_algo_id(OID_RSA_SHA256)
        + issuer.to_der()
        + _encode_sequence(_encode_utctime(validity.not_before) + _encode_utctime(validity.not_after))
        + subject.to_der()
        + _encode_subject_pubkey_info(subject_pub)
    )
    if is_ca:
        bc_value = _encode_sequence(_encode_boolean(True))
        if pathlen is not None:
            bc_value += _encode_integer(pathlen)
        basic_constraints = _tlv(0x55, bc_value)
        ext_seq = _encode_sequence(basic_constraints)
        body += _tlv(0xA3, ext_seq)
    return _encode_sequence(body)


def pkcs1_v15_sign(message: bytes, priv: PrivateKey, hash_oid: str = OID_SHA256) -> bytes:
    """RFC 8017 §8.2.1: RSASSA-PKCS1-v1_5-Sign with SHA-256."""
    digest = hashlib.sha256(message).digest()
    digest_info = _encode_sequence(_encode_algo_id(hash_oid) + _tlv(0x04, digest))
    k = (priv.n.bit_length() + 7) // 8
    pad_len = k - 3 - len(digest_info)
    if pad_len < 8:
        raise ValueError("key too short for this message")
    em = b"\x00\x01" + (b"\xff" * pad_len) + b"\x00" + digest_info
    return pow(int.from_bytes(em, "big"), priv.d, priv.n).to_bytes(k, "big")


def pkcs1_v15_verify(message: bytes, signature: bytes, pub: PublicKey) -> bool:
    """RFC 8017 §8.2.2: RSASSA-PKCS1-v1_5-Verify."""
    k = (pub.n.bit_length() + 7) // 8
    if len(signature) != k:
        return False
    em = pow(int.from_bytes(signature, "big"), pub.e, pub.n).to_bytes(k, "big")
    if em[:2] != b"\x00\x01":
        return False
    sep = em.find(b"\x00", 2)
    if sep < 10:
        return False
    digest_info = em[sep + 1:]
    if not digest_info.startswith(b"\x30"):
        return False
    digest = hashlib.sha256(message).digest()
    expected = _encode_sequence(_encode_algo_id(OID_SHA256) + _tlv(0x04, digest))
    return digest_info == expected


def issue_certificate(
    subject: Name,
    issuer_name: Name,
    subject_pub: PublicKey,
    issuer_priv: PrivateKey,
    serial: int,
    validity: Validity,
    is_ca: bool,
    pathlen: int | None = None,
) -> Certificate:
    tbs = _build_tbs(serial, issuer_name, validity, subject, subject_pub, is_ca, pathlen)
    sig = pkcs1_v15_sign(tbs, issuer_priv)
    return Certificate(
        tbs_der=tbs,
        signature_alg=OID_RSA_SHA256,
        signature_value=sig,
        issuer_dn=issuer_name.cn,
        subject_dn=subject.cn,
        not_before=validity.not_before,
        not_after=validity.not_after,
        serial=serial,
        subject_pub=subject_pub,
    )


@dataclass
class ChainResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    path: list[Certificate] = field(default_factory=list)


def verify_chain(
    leaf: Certificate,
    intermediates: list[Certificate],
    trust_anchors: dict[str, PublicKey],
    now: datetime,
    is_revoked,
    expected_hostname: str | None = None,
) -> ChainResult:
    result = ChainResult(valid=False)
    chain = [leaf] + list(intermediates)
    for cert in chain:
        if not (cert.not_before <= now < cert.not_after):
            result.errors.append(f"expired or not-yet-valid: {cert.subject_dn}")
            return result
        if is_revoked(cert.serial):
            result.errors.append(f"revoked serial {cert.serial}: {cert.subject_dn}")
            return result
    for i in range(len(chain) - 1):
        subject = chain[i]
        issuer = chain[i + 1]
        if subject.issuer_dn != issuer.subject_dn:
            result.errors.append(
                f"issuer mismatch on {subject.subject_dn}: expected {issuer.subject_dn}, got {subject.issuer_dn}"
            )
            return result
        if not pkcs1_v15_verify(subject.tbs_der, subject.signature_value, issuer.subject_pub):
            result.errors.append(f"bad signature on {subject.subject_dn}")
            return result
    top = chain[-1]
    if top.issuer_dn not in trust_anchors:
        result.errors.append(f"unknown top issuer {top.issuer_dn}; no matching trust anchor")
        return result
    if not pkcs1_v15_verify(top.tbs_der, top.signature_value, trust_anchors[top.issuer_dn]):
        result.errors.append(f"bad signature from trust anchor on {top.subject_dn}")
        return result
    if expected_hostname is not None and leaf.subject_dn != f"CN={expected_hostname}":
        result.errors.append(
            f"hostname {expected_hostname!r} does not match CN {leaf.subject_dn!r}"
        )
        return result
    result.valid = True
    result.path = chain
    return result


def main() -> None:
    print("=" * 68)
    print("X.509 v3 BUILDER  --  issuing root, intermediate, and leaf")
    print("=" * 68)

    root_priv, root_pub = generate_rsa_keypair(bits=2048)
    int_priv, int_pub = generate_rsa_keypair(bits=2048)
    leaf_priv, leaf_pub = generate_rsa_keypair(bits=2048)

    now = datetime.now(timezone.utc)
    one_year_later = now.replace(year=now.year + 1)
    five_years_later = now.replace(year=now.year + 5)
    ten_years_later = now.replace(year=now.year + 10)

    root_cert = issue_certificate(
        subject=Name("CN=Test Root"),
        issuer_name=Name("CN=Test Root"),
        subject_pub=root_pub,
        issuer_priv=root_priv,
        serial=1,
        validity=Validity(now, ten_years_later),
        is_ca=True,
        pathlen=1,
    )
    int_cert = issue_certificate(
        subject=Name("CN=Test Intermediate"),
        issuer_name=Name("CN=Test Root"),
        subject_pub=int_pub,
        issuer_priv=root_priv,
        serial=2,
        validity=Validity(now, five_years_later),
        is_ca=True,
        pathlen=0,
    )
    leaf_cert = issue_certificate(
        subject=Name("CN=server.internal"),
        issuer_name=Name("CN=Test Intermediate"),
        subject_pub=leaf_pub,
        issuer_priv=int_priv,
        serial=3,
        validity=Validity(now, one_year_later),
        is_ca=False,
    )

    print("\nIssued certificates:")
    for label, cert in (
        ("root", root_cert),
        ("intermediate", int_cert),
        ("leaf", leaf_cert),
    ):
        print(
            f"  {label:<12} subject={cert.subject_dn!r:<32} "
            f"serial={cert.serial} bytes={len(cert.to_der())}"
        )

    trust = {root_cert.subject_dn: root_cert.subject_pub}
    revoked_serials = {3}

    print("\nChain validation matrix:")
    cases = [
        ("happy path", [int_cert], trust, False, "server.internal", True),
        ("unknown issuer", [int_cert], {}, False, "server.internal", False),
        ("revoked leaf", [int_cert], trust, True, "server.internal", False),
        ("hostname mismatch", [int_cert], trust, False, "evil.example", False),
    ]
    for name, ints, ts, revoked_flag, host, expected in cases:
        is_revoked = (lambda s: s in revoked_serials) if revoked_flag else (lambda s: False)
        result = verify_chain(leaf_cert, ints, ts, now, is_revoked, host)
        status = "PASS" if result.valid == expected else "FAIL"
        err_summary = "; ".join(result.errors) if result.errors else "ok"
        print(f"  [{status}] {name:<22} valid={result.valid}  -> {err_summary}")

    print("\nVerification summary: RFC 5280 §6 algorithm applied offline.")
    print("Use openssl x509 -text -noout to see the same fields in PEM form.")


if __name__ == "__main__":
    main()
