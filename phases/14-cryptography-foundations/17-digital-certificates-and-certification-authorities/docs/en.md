# Digital Certificates and Certification Authorities

> A digital certificate binds an identity (subject, common name, organisation) to a public key, signed by an issuer's private key. The dominant format is X.509 v3 (RFC 5280), built on ASN.1 DER encoding, with the issuer being either a root Certification Authority (CA) or an intermediate. Browsers, OS trust stores, and TLS libraries trust a CA when its root certificate is preinstalled — currently the Mozilla, Apple, and Microsoft root programs together list roughly 150-180 root CAs covering the modern web. We build a minimal certificate (subject, issuer, public key, validity window, signature) from primitives, then sign and verify it with Ed25519 keys.

**Type:** implementation
**Languages:** Python 3 (stdlib only)
**Prerequisites:** Lesson 11 (symmetric-key signatures — Big Brother), Lesson 12 (public-key signatures), public-key cryptography
**Time:** ~60 minutes

## Learning Objectives

- Define a certificate as a binding of (subject, public key, validity, extensions) signed by an issuer's private key.
- Construct a minimal X.509-like structure using ASN.1 SEQUENCE/SET/INTEGER/OCTET STRING primitives.
- Distinguish root CAs (self-signed), intermediate CAs (signed by a parent), and end-entity certificates (leaf).
- Sign a certificate with Ed25519 (`cryptography.hazmat` style) and verify the signature against the issuer's public key.
- Walk the chain from leaf → intermediate → root and verify each link in turn.

## The Problem

Most TLS handshakes happen invisibly: the browser receives a certificate chain, walks it up to a trusted root, and either accepts or rejects the connection. When something goes wrong — an expired certificate, an untrusted root, a name mismatch — the user sees a warning but has no model for what just happened. Without a working certificate builder, students cannot introspect a chain, debug a CA problem, or understand why a self-signed certificate is not automatically trustworthy.

The problem we solve here: produce a self-contained Python module that mints a leaf certificate, an intermediate CA, and a root CA, then chains them so verification has a clear success path.

## The Concept

### Certificate Anatomy (RFC 5280 §4.1)

```
Certificate ::= SEQUENCE {
    tbsCertificate       TBSCertificate,
    signatureAlgorithm   AlgorithmIdentifier,
    signatureValue       BIT STRING
}
TBSCertificate ::= SEQUENCE {
    version         [0] EXPLICIT Version DEFAULT v1,
    serialNumber         CertificateSerialNumber,
    signature            AlgorithmIdentifier,
    issuer               Name,
    validity             Validity,
    subject              Name,
    subjectPublicKeyInfo SubjectPublicKeyInfo,
    extensions      [3] EXPLICIT Extensions OPTIONAL
}
```

| Field | Purpose |
|-------|---------|
| version | v1, v2, or v3 (v3 adds extensions). |
| serialNumber | CA-issued unique identifier (e.g., random 64-bit integer). |
| signature | identifier of the algorithm used by the issuer. |
| issuer | distinguished name (DN) of the signer. |
| validity | notBefore and notAfter timestamps. |
| subject | DN of the entity the certificate is for. |
| subjectPublicKeyInfo | algorithm + public key bits. |

### The CA Hierarchy

```
                Root CA (self-signed)
                 |         |
       Intermediate A   Intermediate B
          |                       |
       Leaf cert 1           Leaf cert 2
```

| Tier | Trust source | Stored in |
|------|--------------|-----------|
| Root CA | Out-of-band: shipped with the OS / browser | Trust store |
| Intermediate CA | Signed by a root or another intermediate | Server delivers during TLS |
| Leaf | Signed by an intermediate | Server delivers during TLS |

### Signing and Verifying

A certificate is just data signed by an issuer's private key over the DER encoding of the `TBSCertificate`. The verifier:

1. Decodes the DER.
2. Extracts the issuer's public key (either by trusting it directly, or by walking up the chain).
3. Verifies the signature using the issuer's algorithm.
4. Checks the validity window, the chain of issuer-name → subject-name, and any name constraints.

### Trust Roots in 2026

| Program | Approximate root count |
|---------|------------------------|
| Mozilla (Firefox, NSS) | 160+ |
| Apple (macOS/iOS) | 160+ |
| Microsoft (Windows) | 100+ |
| Chrome (uses OS store) | inherits |

Trust is asymmetric: a CA can sign for any subject it likes within the constraints of its CP/CPS, which is what makes CA compromise catastrophic. Notable incidents: DigiNotar (2011), Symantec/Google distrust (2018), various subordinate CAs mis-issued for internal names.

## Build It

`main.py` ships:

- `Certificate` dataclass with subject, issuer, public_key, not_before, not_after, serial, signature.
- `mint_root_ca(name, key_pair)` — self-signs.
- `mint_intermediate(name, parent_cert, parent_key)` — signs under a parent.
- `mint_leaf(subject, parent_cert, parent_key, public_key)` — signs a leaf.
- `verify_chain(chain, trust_roots)` — walks leaf → root.
- `serialize_cert(cert)` / `parse_cert(data)` — minimal DER-style encoding.

```python
from main import mint_root_ca, mint_intermediate, mint_leaf, verify_chain, KeyPair

root = mint_root_ca("CN=Acme Root", KeyPair.generate())
inter = mint_intermediate("CN=Acme Intermediate CA", root.cert, root.key)
leaf = mint_leaf("CN=example.com", inter.cert, inter.key, KeyPair.generate().public)

ok = verify_chain([leaf.cert, inter.cert], [root.cert])
print(ok)  # -> True
```

## Use It

| Routine | Purpose | Returns |
|---------|---------|---------|
| `mint_root_ca(name, kp)` | create a self-signed root | Certificate |
| `mint_intermediate(name, parent_cert, parent_key)` | create a CA signed by parent | Certificate |
| `mint_leaf(name, parent_cert, parent_key, pubkey)` | create a leaf signed by parent | Certificate |
| `verify_chain(chain, trust_roots)` | walk chain to a trusted root | bool |
| `serialize_cert(cert)` | DER-style byte encoding | bytes |
| `KeyPair.generate()` | generate an Ed25519-style keypair | KeyPair |

## Ship It

In production, never roll your own certificate format. Use `cryptography.x509` (PyCA) or Go's `crypto/x509`. This lesson's purpose is to make the structure visible, not to ship a CA. If you do operate a private CA, follow the CA/Browser Forum Baseline Requirements (BR) for certificate issuance, key ceremony procedures (FIPS 140-3 / WebTrust), and audit trail retention.

## Exercises

1. Mint a 3-level chain (root → intermediate → leaf) and verify it programmatically. Tamper with the leaf's serial number and confirm verification fails.
2. Add an `extensions` field carrying a Subject Alternative Name (SAN) of `example.com`. Demonstrate that the verifier rejects a leaf claiming a different SAN.
3. Reduce the chain to root + leaf (skip the intermediate). Verify it still works — what changes about the trust delegation?
4. Simulate CA compromise by signing a malicious leaf with a root's private key and show that `verify_chain` accepts it (the trust root is, by definition, trusted).
5. Walk a real-world chain with `cryptography.x509` and dump the issuer/subject/serial/validity fields. Compare the JSON-equivalent output to your in-memory model.
6. Add `not_before > not_after` rejection in the verifier and prove it catches a back-dated leaf.

## Key Terms

| Term | Definition |
|------|------------|
| Certificate | Signed binding of identity to a public key. |
| CA (Certification Authority) | Issuer of certificates; trusted by some trust programme. |
| Root CA | Self-signed top of a trust chain; preinstalled in OS trust stores. |
| Intermediate CA | Signed by a parent CA; signs leaf certificates. |
| Leaf certificate | End-entity certificate, identifying a server or client. |
| Distinguished Name (DN) | Hierarchical identifier (CN, O, C, etc.) for a certificate subject or issuer. |
| Chain of trust | Path from leaf → intermediate → root, each link signed by the next. |
| Baseline Requirements | CA/Browser Forum document governing public WebPKI issuance. |

## Further Reading

- RFC 5280, Internet X.509 Public Key Infrastructure Certificate and CRL Profile.
- RFC 7468, Textual Encodings of PKIX, PKCS, and CMS Structures (PEM).
- CA/Browser Forum Baseline Requirements, current version.
- Mozilla Root Store Policy.
- Peter Gutmann's "X.509 Style Guide" — practical DER encoding pitfalls.
- NIST SP 800-32, Introduction to Public Key Technology and the Federal PKI.