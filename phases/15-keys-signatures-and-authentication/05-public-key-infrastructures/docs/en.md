# Public Key Infrastructures

> A PKI is the trust plumbing that makes public-key crypto work at scale: a hierarchy of CAs issues certificates that bind names to keys, and every relying party verifies the chain back to a trusted root anchor. Without it, a public key is just a number — anyone can claim it belongs to anyone.

**Type:** Build
**Languages:** Python (stdlib)
**Prerequisites:** Phase 14 (RSA, public-key crypto), Phase 15 lessons 01-04 (signatures, certificates, X.509)
**Time:** ~90 minutes

## Learning Objectives

- Trace a certificate chain from an end-entity certificate through intermediate CAs to a root trust anchor, naming each signature that must be verified.
- Explain the difference between hierarchical trust, web of trust (PGP), and bridge CA models.
- Simulate the certificate issuance process: CA validates identity, generates certificate, signs with CA private key.
- Detect expired, revoked (CRL), and spoofed certificates using chain validation logic.
- Implement an OCSP-style revocation check and explain why CRLs and OCSP have different operational tradeoffs.

## The Problem

Alice sends Bob her public key. Bob asks: "How do I know this is really Alice's key and not Mallory's?" In a small group, Alice can hand Bob the key in person. On the Internet with billions of users, that does not scale. A PKI solves this by introducing Certificate Authorities (CAs) — trusted third parties that vouch for the binding between an identity and a public key. The CA signs a certificate containing the identity and the public key; Bob verifies the CA's signature using the CA's public key. But how does Bob know the CA's key? Through a higher-level CA, and so on up to a root CA that Bob trusts a priori (pre-installed in his browser/OS). This chain of trust is the backbone of TLS, code signing, and email security.

## The Concept

### Certificate Chain

```
Root CA (self-signed, pre-trusted)
  |
  +-- Intermediate CA (signed by Root CA)
        |
        +-- End-Entity certificate (signed by Intermediate CA)
              |
              +-- Public Key = Alice's key
```

### Trust Models

| Model | Description | Example |
|-------|-------------|---------|
| Hierarchical | Tree of CAs, root at top | X.509 / Web PKI |
| Web of Trust | Peer-to-peer trust signatures | PGP / GPG |
| Bridge CA | Cross-certifies multiple hierarchies | Federal PKI |

### Revocation

- **CRL (Certificate Revocation List):** CA publishes a signed list of revoked certificate serial numbers. Bob downloads and checks it. Simple but can be large and stale.
- **OCSP (Online Certificate Status Protocol):** Bob queries the CA in real-time for the status of a specific certificate. Fresh but adds latency and a privacy concern (CA learns which sites Bob visits).

## Build It

1. Define the CA hierarchy: root CA, intermediate CA, end-entity.
2. Simulate certificate issuance: CA signs (subject, public_key, validity) with CA private key.
3. Implement chain validation: verify each certificate's signature up to the root.
4. Add revocation: maintain a CRL and implement OCSP query simulation.
5. Test with valid chain, expired cert, revoked cert, and broken chain.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Validate a chain | Certificate signatures at each level | All signatures verify up to root, root is in trust store |
| Detect revocation | CRL or OCSP response | Revoked cert rejected with reason "revoked" |
| Detect expiry | Validity dates in certificate | Expired cert rejected with reason "expired" |

## Ship It

Create one artifact under `outputs/`:

- A PKI validation runbook that lists the steps to verify any certificate chain
- A study prompt that teaches PKI from evidence

## Exercises

1. Trace the full chain for a real website's TLS certificate using your browser.
2. Create a PKI with two intermediate CAs and demonstrate cross-certification.
3. Simulate a CA compromise: revoke all certificates issued by the compromised CA.
4. Compare CRL vs OCSP freshness: what happens if the CRL is 24 hours old?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| PKI | "Certificate stuff" | The infrastructure of CAs, certificates, and revocation that makes public-key trust scale |
| Certificate chain | "The cert path" | The sequence of certificates from end-entity through intermediates to a trusted root |
| Trust anchor | "The root cert" | A self-signed CA certificate that a relying party trusts a priori (pre-installed) |
| CRL | "Revocation list" | A signed, timestamped list of revoked certificate serial numbers published by a CA |
| OCSP | "Real-time revocation check" | A protocol to query a CA for the current status of a specific certificate |

## Further Reading

- RFC 5280: Internet X.509 Public Key Infrastructure Certificate and CRL Profile
- RFC 6960: Online Certificate Status Protocol (OCSP)
- The textbook chapter on network security (Sec 8.5)
