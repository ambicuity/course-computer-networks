# Public Key Infrastructure and Chains of Trust

> A Public Key Infrastructure (PKI) is the policy, procedural, and software machinery that issues, distributes, verifies, and revokes certificates. The WebPKI alone is operated by ~150 root CAs whose chains collectively sign more than a billion active leaf certificates (Let's Encrypt alone issues >4 million/day at peak). Beyond TLS, enterprise PKIs run inside organisations via Active Directory Certificate Services, EJBCA, or Dogtag, supporting S/MIME, code signing, smart-card logon, and document signing. We build a chain validator that walks a leaf → intermediate → root path, checks name chaining, validity windows, key usage, and basic constraints, and explains why each link matters.

**Type:** implementation
**Languages:** Python 3 (stdlib only)
**Prerequisites:** Lessons 17-18 (certificates, ASN.1), digital signatures
**Time:** ~60 minutes

## Learning Objectives

- Define PKI as the union of policies (CP/CPS), technical components (CA software, HSMs, OCSP responders), and trust roots (browsers, OSes).
- Implement a chain validator that enforces name chaining (issuer == subject of parent), signature chaining, validity windows, basic constraints, and key usage.
- Distinguish cross-certified PKIs (mesh) from hierarchical PKIs (tree) and from bridge CAs (e.g., US Federal Bridge).
- Walk an arbitrary chain and explain the failure mode for each kind of breakage: expired, untrusted root, name mismatch, broken signature, basic-constraints violation.
- Produce a model of an enterprise PKI in ~50 lines of code that you can extend into a small CA for tests.

## The Problem

Students often treat certificates as standalone files and chains as sequences of bytes. The actual machinery is layered: each link has a name, a public key, an algorithm, a validity window, and a set of constraints. A validator must respect all of them. Without a working chain model, it is impossible to reason about why a TLS handshake fails (was the leaf expired, was the intermediate missing, was the root rotated?).

The pedagogical challenge: produce a chain validator whose output is a list of validation steps, each annotated with pass/fail, so a learner can see exactly where the chain breaks.

## The Concept

### PKI Components

| Component | Purpose |
|-----------|---------|
| Certificate Policy (CP) | Long-form human-readable document governing issuance. |
| Certification Practice Statement (CPS) | Operational procedures (audits, key ceremony). |
| Root CA | Self-signed top of the chain. |
| Subordinate / Intermediate CA | Signed by a parent; signs leaves or further subordinates. |
| Registration Authority (RA) | Verifies subject identity before issuance. |
| Online Certificate Status Protocol (OCSP) | Real-time revocation check (RFC 6960). |
| Certificate Revocation List (CRL) | Periodically published list of revoked serials. |
| Validation Authority (VA) | Service that aggregates OCSP/CRL responses. |

### Trust Models

| Model | Topology | Example |
|-------|----------|---------|
| Hierarchical (strict tree) | Single root, fan-out subordinates | WebPKI, DoD PKI |
| Mesh (cross-certified) | Multiple roots cross-sign each other | Some government PKIs |
| Bridge | One bridge CA signs each root's public key | US Federal Bridge, EU eIDAS |
| Web of trust | Decentralised, user-asserted | PGP |

The WebPKI is technically a forest: each browser/OS has its own trust store, with overlapping but distinct roots. Browsers can distrust a root unilaterally even if it remains in another trust store (e.g., the 2018 Symantec distrust by Chrome).

### The WebPKI in Numbers (2026)

| Metric | Value |
|--------|-------|
| Active root CAs (Mozilla root store) | 162 |
| Active intermediates observed in scans | 2,500+ |
| Leaf certificates on the public web | 1.5B+ (per crt.sh) |
| Let's Encrypt daily issuance peak | 4-6M/day |
| Average leaf validity (WebPKI) | 90 days (down from 825 in 2018) |

### Chain Validation Algorithm (RFC 5280 §6.1)

```
function validate(cert, path, trust_roots, time):
    if cert in trust_roots:
        return OK
    if cert.issuer != path.parent.subject:
        return FAIL_NAME_CHAINING
    if not verify_sig(path.parent.public_key, cert.tbs, cert.signature):
        return FAIL_SIGNATURE
    if not (cert.not_before <= time <= cert.not_after):
        return FAIL_VALIDITY
    if cert.basic_constraints.cA is True and path.depth >= max_path_length:
        return FAIL_BASIC_CONSTRAINTS
    return OK, recurse to path.parent
```

### Key Usage and Extended Key Usage

| Extension | OID | Purpose |
|-----------|-----|---------|
| keyUsage | 2.5.29.15 | digitalSignature, keyEncipherment, keyCertSign, cRLSign |
| extKeyUsage | 2.5.29.37 | serverAuth, clientAuth, codeSigning, emailProtection |
| basicConstraints | 2.5.29.19 | cA boolean + pathLenConstraint |
| subjectAltName | 2.5.29.17 | DNS names / IPs for TLS |

A certificate with `keyCertSign` not set in keyUsage must not be allowed to sign other certificates. Modern browsers reject such chains.

### Failure Modes the Validator Must Catch

| Failure | Symptom | RFC 5280 step |
|---------|---------|---------------|
| Expired leaf | TLS handshake fails with `certificate has expired` | step (a) |
| Untrusted root | TLS fails with `unable to get local issuer certificate` | step (b) |
| Name mismatch | TLS fails with `hostname mismatch` | step (i) SAN comparison |
| Wrong key usage | TLS fails with `key usage not permitted` | step (l) |
| Broken signature | TLS fails with `signature verification failed` | step (g) |
| Path length exceeded | TLS fails with `path length constraint exceeded` | step (n) |

## Build It

`main.py` ships:

- `ChainValidator` class with `add_trust_root(cert)`, `validate(cert_chain, time)`.
- Returns a `ValidationReport` listing each step and pass/fail.
- A `KeyUsage` enum covering `digitalSignature`, `keyCertSign`, `cRLSign`, etc.
- A demo that builds root → intermediate → leaf and validates the chain end-to-end.

```python
from main import ChainValidator, mint_root, mint_intermediate, mint_leaf

root_kp = KeyPair.generate()
root = mint_root("Acme Root", root_kp)
inter_kp = KeyPair.generate()
intermediate = mint_intermediate("Acme Inter", root_kp)
leaf_kp = KeyPair.generate()
leaf = mint_leaf("example.com", inter_kp)

v = ChainValidator()
v.add_trust_root(root)
report = v.validate([leaf, intermediate])
for step in report.steps:
    print(step)
print(report.ok)
```

## Use It

| Routine | Purpose |
|---------|---------|
| `ChainValidator.add_trust_root(cert)` | register a root |
| `ChainValidator.validate(chain, time=None)` | walk the chain, return report |
| `ValidationReport.steps` | list of (check_name, ok, detail) |
| `ValidationReport.ok` | boolean final result |
| `mint_root/mint_intermediate/mint_leaf` | build a 3-level chain |

## Ship It

Use OpenSSL or the `cryptography` library's `x509.verification` module for production validation. This lesson's validator is a model, not a replacement. Real validation also checks CRLs/OCSP, name constraints, policy constraints, and EKU. The Mozilla PKI section of the Mozilla source tree is a good reference for a complete WebPKI policy.

## Exercises

1. Build a 4-level chain (root → intermediate1 → intermediate2 → leaf). Verify it. Now drop intermediate2 and confirm the chain breaks with "issuer name mismatch".
2. Add `keyUsage = keyCertSign` only to intermediates, not to leaves. Confirm the validator rejects any attempt to use a leaf as a signer.
3. Simulate expiry by setting `not_after` of the intermediate to a date in the past. Verify the chain breaks.
4. Add a `pathLenConstraint=0` to the intermediate; verify that adding a sub-intermediate between it and the leaf is rejected.
5. Build a mesh topology: two roots cross-sign each other. Verify that a leaf issued under either root validates against the other.
6. Implement revocation by serial: add `revoke(serial)` to the validator and confirm the chain breaks if any link is revoked.

## Key Terms

| Term | Definition |
|------|------------|
| PKI | The full set of policies, software, hardware, and procedures for issuing and verifying certificates. |
| Trust root | A certificate pre-installed in the consumer's trust store. |
| Chain validation | Walking from a leaf up through intermediates to a trust root, checking each link. |
| Name chaining | Property that issuer == parent.subject. |
| Basic constraints | X.509 extension marking a cert as a CA and bounding its sub-tree depth. |
| Path length | Number of intermediates allowed beneath a CA. |
| OCSP | Online Certificate Status Protocol (RFC 6960). |
| CRL | Certificate Revocation List, periodically published. |
| Bridge CA | A meta-CA that cross-certifies roots across PKIs. |

## Further Reading

- RFC 5280, Internet X.509 PKI Certificate and CRL Profile (especially §6, validation).
- RFC 6960, X.509 Internet Public Key Infrastructure Online Certificate Status Protocol.
- CA/Browser Forum Baseline Requirements (current version).
- NIST SP 800-32, Introduction to Public Key Technology and the Federal PKI.
- NIST SP 800-57 Part 1 Rev. 5, Recommendation for Key Management.
- Let's Encrypt "How It Works" documentation — operational PKI design.
- Mozilla Root Store Policy and included CA list.