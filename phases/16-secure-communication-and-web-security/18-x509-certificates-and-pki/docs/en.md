# X.509 certificates, chains, and PKI trust models

> X.509 (RFC 5280) is the certificate format that lets Alice be sure Bob's public key really belongs to Bob, instead of to whoever just rewrote Bob's web page. A certificate is a small, signed wrapper around three fields — subject name (Distinguished Name), subject public key (e.g., RSA-2048 or EC P-256), and validity period (notBefore/notAfter) — plus the issuer's Distinguished Name, a serial number, the signature algorithm OID (e.g., `sha256WithRSAEncryption`), and a signature value computed over the DER-encoded `TBSCertificate`. The issuer signs with a long-lived private key whose matching public key is either shipped in your browser as a trust anchor or fetched from a parent in a certification chain. Chain validation walks subject → issuer → issuer → root, verifying signatures and policy constraints at each hop, and consulting CRLs (RFC 5280 §5) or OCSP responders (RFC 6960) to make sure no serial number has been revoked since issuance. This lesson builds an offline X.509 mini-PKI in pure Python: you generate RSA keys, build the ASN.1 structures by hand, sign with PKCS#1 v1.5 (RFC 8017), and walk a two-level chain end to end.

**Type:** Lab
**Languages:** Python, shell, OpenSSL
**Prerequisites:** Phase 14 (public-key cryptography), Phase 15 (digital signatures and HMACs), familiarity with DER/ASN.1 length-byte encoding
**Time:** ~75 minutes

## Learning Objectives

- Enumerate the fields of an X.509 v3 certificate (RFC 5280 §4.1) and explain why each is needed for binding a public key to an identity.
- Build a minimal ASN.1 encoder for `SEQUENCE`, `INTEGER`, `OBJECT IDENTIFIER`, `BIT STRING`, `UTF8String`, `GeneralizedTime`, and `BOOLEAN`, then assemble a valid `Certificate` structure.
- Sign a TBSCertificate using PKCS#1 v1.5 RSA (RFC 8017 §8.2.1, RSASSA-PKCS1-v1_5 with `sha256WithRSAEncryption`) and verify the signature with the issuer's public key.
- Walk a two-level chain root → intermediate → leaf and detect failures caused by an unknown issuer, an expired notAfter, a wrong subject DN, or a revoked serial number.
- Compare the offline validator against `openssl x509 -text -noout` and `openssl verify -CAfile`, mapping the verifier outputs to the RFC 5280 §6 algorithm.

## The Problem

You are told "deploy mTLS between two services." The wire protocol is the easy part — every TLS 1.2 handshake (RFC 5246) and TLS 1.3 handshake (RFC 8446) carries a certificate chain, and Python's `ssl` module or Go's `crypto/tls` will validate it for you if you point it at a CA bundle. The hard part is trust: when service A presents a leaf certificate, what stops an attacker from re-signing it with their own key? When the leaf says `CN=service-a.internal`, who vouched that this public key really belongs to that hostname? When a service is decommissioned, how does the rest of the fleet learn not to trust it?

The reason most operators struggle is that they have never seen the bytes. They configure `/etc/ssl/certs/ca-certificates.crt` and trust the OS, or they pin a thumbprint and hope nobody rotates. After this lab you will have hand-built a `Certificate` structure, signed it, and verified a chain — so the next time you read `X509_verify_cert: certificate revoked` from `strace openssl s_client`, you will know exactly which byte the verifier choked on.

## The Concept

### The fields of an X.509 v3 certificate

RFC 5280 §4.1 defines the `Certificate` structure. A v3 certificate is a `SEQUENCE OF` three things: the `TBSCertificate` (everything the issuer is attesting to), the `signatureAlgorithm` (repeated for symmetry so a parser can find the signature algorithm without parsing the TBSCertificate first), and the `signatureValue` (a `BIT STRING` containing the signature bytes). Inside `TBSCertificate`:

| Field | Type | Purpose |
|---|---|---|
| `version` | `[0] EXPLICIT Version DEFAULT v1` | v3 adds extension support; we always emit v3 |
| `serialNumber` | `CertificateSerialNumber ::= INTEGER` | Unique per CA; used as CRL/OCSP key |
| `signature` | `AlgorithmIdentifier` | Same OID as the outer `signatureAlgorithm` |
| `issuer` | `Name` | Distinguished Name (RDN sequence) of the signer |
| `validity` | `SEQUENCE { notBefore, notAfter }` | Both `GeneralizedTime` (YYYYMMDDHHMMSSZ) |
| `subject` | `Name` | DN of the public-key holder |
| `subjectPublicKeyInfo` | `SubjectPublicKeyInfo` | Algorithm OID + BIT STRING of the public key |
| `extensions` | `[3] EXPLICIT Extensions OPTIONAL` | v3-only; SAN, key usage, basic constraints |

A real-world leaf cert also carries `Key Usage` (digitalSignature, keyEncipherment), `Extended Key Usage` (serverAuth, clientAuth), and `Subject Alternative Name` (DNS entries). A CA cert additionally carries `Basic Constraints CA:TRUE` and a `pathLenConstraint` that bounds how many intermediates can sit beneath it.

### The signature: PKCS#1 v1.5 with SHA-256

RFC 8017 §8.2.1 specifies RSASSA-PKCS1-v1_5. To sign a TBSCertificate:

1. Encode the TBSCertificate DER.
2. Compute `DigestInfo ::= SEQUENCE { digestAlgorithm AlgorithmIdentifier, digest OCTET STRING }` containing SHA-256 of (1).
3. Build `EM = 0x00 || 0x01 || PS || 0x00 || T` where `PS` is `0xFF` repeated until `EM` equals the modulus length, and `T` is the DER of `DigestInfo`.
4. Compute the signature `S = EM^d mod n` (raw RSA private operation).
5. Wrap `S` as a BIT STRING (prepend `0x00` for "0 unused bits").

Verification reverses the steps: RSA public operation `EM = S^e mod n`, strip `0x00 0x01 PS 0x00`, parse `DigestInfo`, recompute SHA-256 over the TBSCertificate, and compare. RSASSA-PSS (RFC 8017 §8.1) is the modern alternative, but PKCS#1 v1.5 is what `sha256WithRSAEncryption` (OID `1.2.840.113549.1.1.11`) means in nearly every certificate you have ever inspected.

### Chain building and validation (RFC 5280 §6)

A path of length `n` is an ordered sequence of `n+1` certificates where the `subject` of certificate `i` matches the `issuer` of certificate `i-1`, for `i = 1..n`. Validation has five passes:

1. **Signatures**: for each cert except the trust anchor, verify `signature` against the issuer's `subjectPublicKeyInfo`.
2. **Validity**: every cert's `notBefore ≤ now < notAfter`. RFC 5280 tolerates a small skew but rejects beyond it.
3. **Issuer/Subject chaining**: as above, recursively.
4. **Name constraints**: if an intermediate carries a name constraint extension, every descendant's SAN/DN must be inside the permitted subtree.
5. **Revocation**: consult CRLs or OCSP. RFC 6960 (OCSP) is faster than full CRLs because the responder returns only the queried serial's status; clients should use `OCSP Stapling` (TLS 1.3 cert entry) to avoid leaking browsing patterns.

In practice, most failures come from passes 1–3 (expired cert, mismatched issuer DN, wrong hostname in SAN). Revocation check failures are rarer because browsers fall back to "soft-fail" when the OCSP responder is unreachable.

### Mini-PKI topology we will build

```
RootCA  (CN=Test Root, RSA-2048, 10y validity)
  └─ IntermediateCA  (CN=Test Intermediate, RSA-2048, 5y, CA:TRUE pathlen:0)
       ├─ leaf-server  (CN=server.internal, SAN=DNS:server.internal, RSA-2048, 1y)
       └─ leaf-client  (CN=alice@internal, SAN=email:alice@internal, RSA-2048, 90d)
```

The intermediate is signed by the root; the leaves are signed by the intermediate. Trust anchors in real PKIs are shipped as self-signed roots, but the validation algorithm does not care about self-signing — it only cares that some key in your trust store matches the issuer of the topmost cert you present.

## Build It

### Step 1 — Generate three RSA key pairs

```python
from main import generate_rsa_keypair

root_priv, root_pub = generate_rsa_keypair(bits=2048)
int_priv,  int_pub  = generate_rsa_keypair(bits=2048)
leaf_priv, leaf_pub = generate_rsa_keypair(bits=2048)
```

Each call produces an `(n, e)` public tuple and an `(n, d)` private tuple. The implementation uses Python's built-in `pow(base, exp, mod)` for modular exponentiation and a deterministic Miller-Rabin primality test so the same seed reproduces the same key in tests.

### Step 2 — Build the X.509 structures

```python
from main import Name, Validity, build_tbs_certificate, sign_certificate, encode_der

root = build_certificate(
    subject=Name(("CN", "Test Root")),
    issuer=Name(("CN", "Test Root")),     # self-signed
    subject_pub=int_pub,
    issuer_priv=int_priv,                 # not used; root signs with its own priv
    validity=Validity(not_before, not_after),
    serial=1,
    is_ca=True,
    pathlen=1,
    private_key=root_priv,
)
```

The `build_certificate` helper encodes the TBSCertificate DER, hashes it with SHA-256, applies PKCS#1 v1.5 padding, and produces a full `Certificate SEQUENCE` ready to write to disk as `.der`.

### Step 3 — Verify the chain

```python
from main import verify_chain, load_der_certificate

parsed_root = load_der_certificate(root_der)
parsed_int  = load_der_certificate(int_der)
parsed_leaf = load_der_certificate(leaf_der)
trust_store = {parsed_root.subject: parsed_root.subject_pub}

result = verify_chain(
    leaf=[parsed_leaf],
    intermediates=[parsed_int],
    trust_store=trust_store,
    now=datetime.now(timezone.utc),
    check_revocation=lambda serial: False,
    hostname="server.internal",
)
assert result.valid
```

`verify_chain` runs the five RFC 5280 passes and returns a `ChainResult` with `valid`, `errors: list[str]`, and a `path: list[Certificate]` for diagnostics.

### Step 4 — Trigger each failure mode

Run the demo block at the bottom of `code/main.py` to print a table where each row disables one check: expired cert, wrong issuer, hostname mismatch, revoked serial, broken signature.

## Use It

| Task | Real tool | Our `code/main.py` | Result |
|---|---|---|---|
| Inspect certificate text | `openssl x509 -text -noout -in cert.pem` | `pretty_print(cert)` | Same fields, same OIDs |
| Validate a chain | `openssl verify -CAfile root.pem -untrusted int.pem leaf.pem` | `verify_chain(...)` | Returns `OK` vs. `valid=True` |
| Check expiry | `openssl x509 -checkend 0` | `validity.remaining(now)` | Seconds remaining |
| Test signature | `openssl x509 -in cert.pem -pubkey -noout \| openssl dgst -sha256 -verify` | `verify_signature(cert, issuer_pub)` | match/mismatch |
| Read OCSP | `openssl ocsp -issuer int.pem -cert leaf.pem -url http://ocsp/` | `check_revocation(serial)` callable | revoked / not-revoked |

The offline `code/main.py` cannot make network calls or use OpenSSL's hardware-accelerated RSA; it is a teaching tool, not a CA. But the structure of the verifier and the field layout are exactly the bytes RFC 5280 prescribes — the OpenSSL output and ours agree on every field name and OID.

## Ship It

The reusable artifact is a self-contained CA library that produces valid `.der` and `.pem` (base64-wrapped DER with `-----BEGIN CERTIFICATE-----`) certs. See `outputs/prompt-x509-pki.md` for a starter checklist that includes:

- A `make_root.py` script that emits a 10-year root and prints the SHA-256 fingerprint for trust-store distribution.
- An `issue_leaf.py` that takes a CSR (RFC 2986 / PKCS#10) and returns a signed DER and PEM.
- A `verify_chain.py` CLI that accepts a bundle and prints the chain in human-readable form.
- A failure-mode regression suite with the four classic mistakes (expired, wrong hostname, revoked serial, broken signature).

## Exercises

1. Hand-trace the DER bytes of a leaf certificate with `subject = (CN=server.internal)`, `serialNumber = 256`, `signatureAlgorithm = sha256WithRSAEncryption`. What is the length byte after the outer `SEQUENCE` tag `0x30`? After `INTEGER` for the serial? Why does ASN.1 use a length byte at all instead of fixed-width fields?
2. The root signs itself — `issuer == subject`. What stops an attacker from minting their own self-signed root and putting it in your trust store? (Hint: trust is not transitive in the cryptographic sense; it is a policy decision made by whoever ships the trust store.)
3. Replace PKCS#1 v1.5 padding with a constant `0x00 0x02 PS 0x00 M` and try to verify a signature. Why does the verifier fail on real-world signatures? (Bleichenbacher's e=3 attack on PKCS#1 v1.5 took advantage of weak verifiers that did not check the full padding structure.)
4. Set `notAfter = notBefore - 1s` and run `verify_chain`. Which RFC 5280 §6 step catches this, and what error code does your code print?
5. Add `pathlen:0` to the intermediate and try to add a second intermediate below it. What does `verify_chain` report? Where in the chain-building algorithm is the constraint checked?
6. Simulate a key compromise: revoke the leaf by adding its serial to an in-memory CRL and pass a custom `check_revocation` to `verify_chain`. Compare the error to what happens when the OCSP responder is unreachable.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| X.509 | "the SSL cert format" | ITU-T X.509 / RFC 5280 ASN.1 structure with version, serial, issuer, validity, subject, SPKI, signature |
| PKI | "the certificate system" | The set of CAs, RAs, certificate formats, validation rules, and revocation infrastructure that make X.509 useful |
| CA | "the cert authority" | An entity that signs certificates; identified by its Distinguished Name and bound to its key by a chain or a trust anchor |
| TBSCertificate | "the part being signed" | `To Be Signed` Certificate — everything except the outer `signatureAlgorithm` and `signatureValue` |
| DN / RDN | "the subject name" | A `SEQUENCE OF RelativeDistinguishedName`; each RDN is `SET OF AttributeTypeAndValue` like `(CN=alice)` |
| SAN | "the hostname list" | Subject Alternative Name extension; DNS entries, IPs, URIs, email; overrides CN for hostname checks since RFC 2818 |
| CRL | "the revocation list" | A signed, time-stamped list of revoked serial numbers; clients must fetch and re-fetch |
| OCSP | "real-time revocation check" | RFC 6960; client sends `(serial, issuer)` to responder and gets `good | revoked | unknown` |
| Trust anchor | "a root cert" | A CA cert the verifier has decided to trust out-of-band (browser pre-install, OS package, pinned bundle) |
| Path validation | "chain checking" | RFC 5280 §6 algorithm; signatures, validity, chaining, name constraints, revocation |

## Further Reading

- RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile (the authoritative spec)
- RFC 6960 — X.509 Internet Public Key Infrastructure Online Certificate Status Protocol (OCSP)
- RFC 2986 — PKCS #10: Certification Request Syntax (CSR format)
- RFC 8017 — PKCS #1 v2.2: RSA Cryptography Specifications (RSASSA-PKCS1-v1_5 padding)
- RFC 6090 — Fundamental Elliptic Curve Cryptography Algorithms (for ECDSA signing keys)
- ITU-T X.509 (2019) — the original ASN.1 standard
- A. J. Menezes, P. C. van Oorschot, S. A. Vanstone — *Handbook of Applied Cryptography*, Ch. 13 (X.509)
- OpenSSL documentation: `x509(1)`, `verify(1)`, `ocsp(1)`
- Peter Gutmann — *X.509 Style Guide* (the de facto ASN.1 ergonomics reference)
