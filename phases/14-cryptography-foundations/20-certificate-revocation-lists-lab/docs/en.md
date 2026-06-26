# Certificate Revocation Lists Lab

> A certificate is supposed to be valid until its `not_after`, but real life intrudes: private keys get stolen, CAs get compromised (DigiNotar 2011, Symantec 2017), certificates are mis-issued, or the subject ceases to exist. CRLs (RFC 5280 §5) are signed, time-stamped lists of revoked certificate serial numbers published by each CA. A CRL has its own ASN.1 structure (TBSCertList, signatureAlgorithm, signatureValue) and is fetched over HTTP from a CRL Distribution Point URL embedded in every certificate. We build a CRL parser/generator, attach revocation to our chain validator from Lesson 19, and walk through OCSP (RFC 6960) as the modern alternative.

**Type:** lab
**Languages:** Python 3 (stdlib only)
**Prerequisites:** Lessons 17-19 (certificates, ASN.1, chain validation)
**Time:** ~75 minutes

## Learning Objectives

- Define a CRL as a CA-signed, periodically-issued list of revoked certificate serial numbers with a `nextUpdate` deadline.
- Generate and parse a minimal CRL using ASN.1 DER (TBSCertList + signatureAlgorithm + signatureValue).
- Wire CRL checking into the chain validator: a certificate is rejected if its serial appears in any unrevoked-or-not-yet-expired CRL signed by its issuer.
- Distinguish CRL from OCSP, and OCSP stapling (RFC 6066 §11.3 / RFC 6961) from online lookups.
- Walk through the lifecycle: a serial is added to a CRL, the CRL is refreshed, an old CRL expires via `nextUpdate`, and a validator that holds the old CRL mistakenly accepts a revoked cert until refresh.

## The Problem

Certificate validity is a function of three properties: signature correctness, name chaining, and *current* non-revocation. Most students learn only the first two. In practice, revocation is what bites you: a CA that has issued a mis-issued cert must revoke it, and every consumer must learn about the revocation within a window bounded by `nextUpdate`. CRL size, network reliability, and cache freshness all create subtle availability and security trade-offs that we explore in this lesson.

The pedagogical goal: write a CRL generator, parse it back, and prove that the chain validator from Lesson 19 properly rejects a revoked leaf.

## The Concept

### CRL Anatomy (RFC 5280 §5.1)

```
CertificateList ::= SEQUENCE {
    tbsCertList         TBSCertList,
    signatureAlgorithm  AlgorithmIdentifier,
    signatureValue      BIT STRING
}
TBSCertList ::= SEQUENCE {
    version                 INTEGER OPTIONAL,
    signature               AlgorithmIdentifier,
    issuer                  Name,
    thisUpdate              Time,
    nextUpdate              Time OPTIONAL,
    revokedCertificates     SEQUENCE OF SEQUENCE {
        userCertificate     INTEGER,
        revocationDate      Time,
        crlEntryExtensions  Extensions OPTIONAL
    } OPTIONAL,
    crlExtensions           [0] EXPLICIT Extensions OPTIONAL
}
```

| Field | Purpose |
|-------|---------|
| version | v1 (default) or v2 (adds crlExtensions + entry extensions). |
| issuer | DN of the issuing CA. |
| thisUpdate | When this CRL was issued. |
| nextUpdate | When the next CRL will be available. |
| revokedCertificates | Sequence of (serial, revocationDate, extensions). |
| signatureAlgorithm | Identifies the signing algorithm. |
| signatureValue | Bit-string signature over TBSCertList. |

### CRL Distribution Points

A certificate carries a CRL Distribution Points extension (OID 2.5.29.31) with one or more URIs. The validator fetches the CRL over HTTP from one of those URIs.

```
crlDistributionPoints:
  fullName:
    uniformResourceIdentifier: "http://ca.example.com/crl/intermediate.crl"
```

### Revocation Reason Codes (RFC 5280 §5.3.1)

| Code | Reason | Typical use |
|------|--------|-------------|
| 0 | unspecified | default |
| 1 | keyCompromise | private key leaked |
| 2 | cACompromise | CA's own key leaked |
| 3 | affiliationChanged | subject changed organisation |
| 4 | superseded | replaced by a newer cert |
| 5 | cessationOfOperation | subject retired service |
| 6 | certificateHold | temporary hold (reversible) |
| 8 | removeFromCRL | take cert off hold |
| 9 | privilegeWithdrawn |
| 10 | aACompromise | attribute authority compromise |

### CRL vs. OCSP vs. OCSP Stapling

| Mechanism | Latency | Bandwidth | Privacy | Failure mode |
|-----------|---------|-----------|---------|--------------|
| CRL | up to `nextUpdate` (hours/days) | full list per fetch | reveals browsing to CA | stale CRL |
| OCSP | real-time | one query per cert | reveals browsing to CA | OCSP responder down |
| OCSP stapling | real-time, server-driven | one response per TLS handshake | hides user | server must support it |

Must-staple (RFC 7633) certificates require a stapled OCSP response and refuse to fall back to live lookups.

### The CRL Lifecycle

```
Day 0:   CA issues CRL #1 with 0 revocations
Day 1:   CA revokes serial 12345; issues CRL #2 with 1 revocation
Day 7:   CA issues CRL #3 with 1 revocation (refresh)
Day 30:  CRL #3 expires (nextUpdate passes); validator must fetch CRL #4
         or treat the cert as "unknown" (soft-fail) or "invalid" (hard-fail)
```

Browsers historically soft-fail: if the OCSP responder is unreachable, accept the cert. This was exploited in practice (e.g., 2014-2016 OCSP-stapling bypass research). Modern browsers lean toward hard-fail for EV certs and short-lived certs.

### CRL Size and Partitioning

A large CA may issue millions of certificates. A monolithic CRL would be too large to download frequently. Solutions:

- Partition CRLs by serial range.
- Use delta CRLs (RFC 5280 §5.2.4): a base CRL + incremental updates.
- Move to OCSP for real-time queries.

## Build It

`main.py` ships:

- `CRL` dataclass with issuer, this_update, next_update, revoked (list of (serial, date, reason)).
- `sign_crl(crl, ca_key) -> bytes` and `parse_crl(data, ca_public_key) -> CRL`.
- `CRLStore` with `add(serial)`, `get(url)`, `refresh(crl)`.
- Hook into the chain validator from Lesson 19 via a `RevocationChecker`.

```python
from main import CRL, sign_crl, parse_crl, RevocationChecker

crl = CRL(issuer="Acme Intermediate CA",
          this_update=datetime.now(timezone.utc),
          next_update=datetime.now(timezone.utc) + timedelta(days=7),
          revoked=[(12345, datetime.now(timezone.utc), "keyCompromise")])
blob = sign_crl(crl, intermediate_key.private, intermediate.public)
parsed = parse_crl(blob, intermediate.public)
print(parsed.revoked)
```

## Use It

| Routine | Purpose |
|---------|---------|
| `CRL(issuer, this_update, next_update, revoked)` | CRL record |
| `sign_crl(crl, ca_private)` | produce DER bytes |
| `parse_crl(data, ca_public)` | verify signature, return CRL |
| `RevocationChecker.check(serial)` | is this serial revoked? |
| `crl_distribution_point(cert)` | extract the CRLDP URI from a cert |
| `next_update_window(crl)` | seconds until nextUpdate |

## Ship It

Production uses OCSP stapling (RFC 6961) wherever possible; CRLs remain as a backstop. CAs that issue high-volume certificates (Let's Encrypt) must run a globally distributed OCSP infrastructure; small CAs may rely entirely on CRLs with daily refresh.

## Exercises

1. Build a CRL containing two revoked serials, sign it, parse it back, and verify the round trip preserves every field.
2. Attach `RevocationChecker` to the chain validator from Lesson 19; revoke the leaf's serial and confirm the chain breaks with `revocation_check = FAIL`.
3. Set `next_update` in the past and confirm `parse_crl` raises "stale CRL".
4. Decode the hex of a real CRL (downloaded from a public CA) with `parse_all` and identify every TLV.
5. Implement delta CRL support: a base CRL plus a delta that adds (serial 99, today) and removes nothing.
6. Simulate an OCSP responder returning `good`, `revoked`, and `unknown` and route each through `RevocationChecker`.

## Key Terms

| Term | Definition |
|------|------------|
| CRL | Certificate Revocation List, a CA-signed list of revoked serials. |
| CRL Distribution Point | URI from which a CRL can be fetched. |
| CRL reason code | Integer 0..10 explaining why a cert was revoked. |
| OCSP | Online Certificate Status Protocol (RFC 6960). |
| OCSP stapling | TLS extension (RFC 6961) that delivers the OCSP response in the handshake. |
| Delta CRL | Incremental update atop a base CRL. |
| Hard-fail vs soft-fail | Whether unreachable OCSP/CRL endpoints reject or accept. |
| Must-staple | TLS extension (RFC 7633) requiring a stapled response. |

## Further Reading

- RFC 5280, Internet X.509 PKI Certificate and CRL Profile (§5).
- RFC 6960, X.509 Internet PKI Online Certificate Status Protocol - OCSP.
- RFC 6961, Multiple Certificate Status Request Extension (OCSP stapling).
- RFC 7633, X.509v3 Transport Layer Security (TLS) Feature Extension (must-staple).
- NIST SP 800-73-4, Interfaces for Personal Identity Verification (CRL handling).
- Let's Encrypt "How It Works" — OCSP infrastructure design.
- Peter Gutmann, "PKI: It's Not Dead, Just Resting", IEEE Computer, 2002.