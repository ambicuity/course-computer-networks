# Certificates to X.509

> A certificate binds a public key to a principal's identity, signed by a Certification Authority (CA) so that strangers can verify the key without the CA being online. Bob takes his public key plus his driver's license to a CA; the CA issues a certificate (Fig. 8-24) and signs its SHA-256 hash with the CA's private key. Bob posts the certificate + signature block on his website. When Alice fetches it, Trudy cannot substitute her own key because the signature block — which Alice verifies with the CA's well-known public key — would not match a modified certificate. The fundamental job: bind a public key to a name. Certificates are not secret; Bob can publish his. They can also bind a key to an attribute ("this key belongs to someone over 18") for privacy-preserving proof. X.509 (ITU, since 1988; V3 is current) is the standard certificate format, adopted by IETF in RFC 5280 despite its OSI origins (ASN.1 encoding, X.500 Distinguished Names like /C=US/O=MoneyBank/OU=Loan/CN=Bob/). The core fields: Version, Serial number, Signature algorithm, Issuer, Validity period, Subject name, Public key, Issuer/Subject IDs, Extensions, and the CA's Signature. V3 permits DNS names instead of X.500 names, fixing the "is this the right Bob?" problem. Certificates defeat the fake-home-page attack where Trudy replaces Bob's public key with her own: Alice recomputes the SHA-256 hash of the certificate and compares it to the CA-signed hash recovered with E_CA; a mismatch exposes Trudy instantly.

**Type:** Build
**Languages:** Python (stdlib hashlib, dataclasses)
**Prerequisites:** Lesson 02 (public-key signatures, message digests), Lesson 03 (birthday attack)
**Time:** ~50 minutes

## Learning Objectives

- Explain how a certificate binds a public key to a principal and why the CA does not need to be online for verification.
- Trace the fake-home-page attack (Fig. 8-23) and show how a signed certificate defeats it.
- List the X.509 V3 certificate fields (Version, Serial, Signature algorithm, Issuer, Validity, Subject, Public key, Extensions, Signature) and what each protects against.
- Distinguish identity-binding certificates from attribute-binding certificates and give a use case for each.
- Build and verify a toy X.509-style certificate in `code/main.py` using SHA-256 and a toy RSA CA.

## The Problem

Alice wants Bob's public key. She types his URL. Trudy intercepts the GET request and replies with a fake home page containing *her* public key E_T instead of Bob's E_B. Alice encrypts her message with E_T; Trudy decrypts, reads, re-encrypts with E_B, and forwards to Bob. Neither Alice nor Bob detects the man-in-the-middle. The fix: Bob needs a verifiable binding between his identity and his public key — a certificate signed by a CA everyone trusts.

## The Concept

### The fake-home-page attack (what certificates solve)

| Step | Without certificate | With certificate |
|------|---------------------|------------------|
| 1. Alice GETs Bob's page | Trudy replies with fake page + E_T | Trudy must present Bob's certificate or fail |
| 2. Alice gets public key | E_T (Trudy's) | E_B, verified via CA signature |
| 3. Alice encrypts message | E_T(message) — Trudy reads it | E_B(message) — only Bob can read |
| 4. Trudy's detection | None — invisible MITM | SHA-256(cert) ≠ CA-signed hash → caught |

### Certificate structure (Fig. 8-24)

```
I hereby certify that the public key
  19836A8B03030CF83737E3837837FC3...
belongs to
  Robert John Smith
  12345 University Avenue
  Berkeley, CA 94702
  Birthday: July 4, 1958
  Email: bob@superdupernet.com
SHA-256 hash of the above certificate signed with the CA's private key
```

The certificate body is public. The CA's signature on the body's hash is the tamper-evident seal. Alice verifies by: (1) recomputing SHA-256(body), (2) applying E_CA to the signature block to recover the CA's hash, (3) comparing. If they match, the certificate is genuine and unmodified.

### Why the CA need not be online

Verification uses only the CA's *public* key (built into browsers) and the CA's signature on the certificate. No network call to the CA is needed. This eliminates the bottleneck and single-point-of-failure of a 24/7 key-distribution server. The CA only needs to be online to *issue* certificates; revocation (lesson 05) reintroduces some online dependency.

### X.509 V3 fields (Fig. 8-25)

| Field | Purpose | Attack prevented |
|-------|---------|-----------------|
| Version | V1/V2/V3 — V3 adds extensions | Downgrade |
| Serial number | Unique per CA; identifies cert for revocation | Reuse ambiguity |
| Signature algorithm | Algorithm used by CA to sign (e.g. sha256WithRSAEncryption) | Algorithm substitution |
| Issuer | X.500 name of the CA | Fake-CA impersonation |
| Validity period | notBefore / notAfter timestamps | Expired-cert reuse |
| Subject name | X.500 DN of the entity whose key is certified | Identity spoofing |
| Public key | Subject's public key + algorithm ID | Key substitution |
| Issuer/Subject IDs | Optional unique identifiers | Name collision |
| Extensions | V3: key usage, subject alt name (DNS), constraints | Over-broad key use |
| Signature | CA's signature over the TBS (to-be-signed) fields | Tampering with any field |

### X.500 Distinguished Names

X.509 inherited OSI X.500 naming: `/C=US/O=MoneyBank/OU=Loan/CN=Bob/` where C=country, O=organization, OU=organizational unit, CN=common name. The problem: Alice emailing `bob@moneybank.com` receives a certificate with an X.500 DN and cannot easily confirm it is "her" Bob. V3 fixes this with the Subject Alternative Name (SAN) extension, permitting DNS names (`bob.moneybank.com`) and email addresses in the certificate.

### ASN.1 encoding

X.509 certificates are encoded in OSI ASN.1 (Abstract Syntax Notation 1) — verbose, binary, DER-encoded. This is the OSI legacy IETF accepted despite usually rejecting OSI conventions. `code/main.py` uses a simple length-prefixed encoding as a teaching substitute; real tooling (`openssl x509`) handles ASN.1/DER.

### Attribute certificates

A certificate can bind a key to an *attribute* instead of an identity: "This public key belongs to someone over 18." The holder proves possession of the corresponding private key by decrypting a random challenge. Useful where privacy matters (age verification without revealing identity) and in distributed object systems (a bitmap of allowed methods bound to a key).

### The verification algorithm

```
1. Parse cert → (body, signature)
2. h_mine = SHA-256(body)
3. h_ca   = E_CA(signature)   # recover CA's hash from signature
4. if h_mine == h_ca and now() in [notBefore, notAfter]:
       trust public_key in body
   else:
       reject
```

`code/main.py` implements this end-to-end with a toy RSA CA, including a tampered-certificate detection scene.

## Build It

1. Run `code/main.py` — it issues a certificate for Bob, signs it with the CA, then verifies. A second scene tampers with the public key and shows verification failing.
2. Inspect the `Certificate` dataclass to see the X.509 V3 field mapping.
3. The SVG in `assets/certificates-to-x-509.svg` shows the fake-home-page attack and the certificate verification flow.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Verify a certificate | SHA-256(body) == E_CA(signature) and time in validity window | Bit-exact match; timestamp within notBefore/notAfter |
| Detect tampering | Modify public key field; recompute hash | h_mine ≠ h_ca → reject |
| Detect expiry | Check `now()` against notAfter | Expired cert rejected even if signature valid |
| Identify MITM | Trudy presents her own cert for Bob's URL | Subject name ≠ "Bob" OR signature invalid |

## Ship It

Create one artifact under `outputs/`:

- A certificate-verification reference implementation (extract from main.py)
- A field-by-field X.509 V3 reference card
- A study prompt: "Why does the CA not need to be online for verification?"

Start with [`outputs/prompt-certificates-to-x-509.md`](../outputs/prompt-certificates-to-x-509.md).

## Exercises

1. Trudy replaces Bob's public key in his certificate with her own but does not re-sign. What does Alice detect when she verifies? Which two hashes does she compare?
2. A certificate's `notAfter` is 2024-01-01. It is now 2026-06-21. The signature is still valid. What does the verifier do? Which field governs this?
3. Why did IETF accept X.509 despite its OSI origins? What problem does the SAN (Subject Alternative Name) extension solve that X.500 Distinguished Names did not?
4. Build an attribute certificate in `code/main.py` that binds a key to "over 18". How does the holder prove the attribute without revealing identity?
5. The CA's private key is compromised. What happens to all certificates it issued? How does revocation (lesson 05) address this?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| Certificate | "signed key" | CA-signed binding of a public key to a principal or attribute |
| CA | "the signer" | Certification Authority; issues and signs certificates; need not be online for verification |
| X.509 | "cert format" | ITU standard for certificates (V3 current); IETF profile in RFC 5280 |
| Distinguished Name | "X.500 name" | Hierarchical name: /C=US/O=MoneyBank/OU=Loan/CN=Bob/ |
| SAN | "alt name" | Subject Alternative Name (V3) — allows DNS/email names in certs |
| TBS (to-be-signed) | "the body" | Certificate fields covered by the CA signature |
| ASN.1 | "the encoding" | Abstract Syntax Notation 1 — verbose OSI binary encoding for X.509 |
| Signature block | "the CA's hash" | CA's signed hash of the certificate body; verified with E_CA |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), Chapter 8, Sections 8.5.1–8.5.2
- RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile
- Ford & Baum (2000), *Secure Electronic Commerce* — X.509 in depth
- ITU-T X.509 — the original standard (1988, V3 1996/2008)
- `openssl x509 -in cert.pem -text -noout` — inspect a real certificate's fields