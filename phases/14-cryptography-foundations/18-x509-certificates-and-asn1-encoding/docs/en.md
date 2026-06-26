# X.509 v3 Certificates and ASN.1 DER Encoding

> ASN.1 (Abstract Syntax Notation One, ITU-T X.680) and its DER (Distinguished Encoding Rules, X.690) are the binary lingua franca of PKIX, SNMP, LDAP, and many telecom protocols. Every byte of an X.509 certificate is a TLV triple — tag, length, value — where the tag class (UNIVERSAL=00, APPLICATION=01, CONTEXT-SPECIFIC=10, PRIVATE=11) and the constructed bit (0=primitive, 1=constructed) determine what comes next. We implement a small ASN.1 DER encoder and decoder from scratch in Python, then use it to assemble a parseable X.509 v3 certificate skeleton with version, serial, signature algorithm, issuer, validity, subject, and subjectPublicKeyInfo fields, exercising every primitive tag we touch.

**Type:** implementation
**Languages:** Python 3 (stdlib only)
**Prerequisites:** Lesson 17 (certificates and CAs), hexadecimal numeracy
**Time:** ~60 minutes

## Learning Objectives

- Decode and encode the ASN.1 universal tags BOOLEAN (0x01), INTEGER (0x02), BIT STRING (0x03), OCTET STRING (0x04), NULL (0x05), OID (0x06), UTF8String (0x0C), PrintableString (0x13), UTCTime (0x17), GeneralizedTime (0x18), SEQUENCE (0x30), SET (0x31).
- Distinguish primitive encoding (length-encoded leaf value) from constructed encoding (concatenation of TLV children), and recognise that SEQUENCE/SET are constructed (tag bit 0x20 set).
- Encode and decode an OID using the base-128 variable-length scheme (first two arcs share the first byte: `40*a + b`).
- Walk a real DER byte stream produced by `openssl x509 -in cert.pem -outform DER | xxd` and identify each TLV by hand.
- Assemble a parseable X.509 v3 certificate skeleton whose DER bytes re-parse identically.

## The Problem

Most developers treat certificates as opaque blobs. When something goes wrong — wrong tag, bad length, corrupt OID — there is no model for what just happened. The DER format is small, regular, and self-describing; once you have written the encoder/decoder, every certificate becomes legible. This lesson is the "X-ray vision" lesson for PKI.

The pedagogical challenge is keeping the encoder compact while still handling every tag we use in X.509. We focus on the tags that appear in real certificates and skip obscure ones (e.g., BMPString, Real).

## The Concept

### Tag Anatomy

| Class | Tag byte pattern | Examples |
|-------|------------------|----------|
| Universal | 0b000xxxxx | BOOLEAN, INTEGER, OCTET STRING, NULL, OID, UTCTime, ... |
| Application | 0b01xxxxxx | rarely used in PKIX |
| Context-specific | 0b10xxxxxx | `[0]`, `[1]`, `[2]`, `[3]` (constructed) wrappers in RFC 5280 |
| Private | 0b11xxxxxx | rarely used in PKIX |

Constructed bit (0x20) is set for SEQUENCE (0x30) and SET (0x31); primitive for INTEGER (0x02), OCTET STRING (0x04), OID (0x06).

### DER Length Rules

| Length | Encoding |
|--------|----------|
| 0..127 | single byte `0x00..0x7F` |
| ≥ 128 | first byte is `0x80 \| nbytes`, followed by `nbytes` big-endian length |

DER demands the SHORTEST possible form — a length of 5 must encode as `0x05`, not `0x81 0x05`. DER demands the shortest INTEGER encoding (no leading 0x00 unless needed to keep the sign bit clear).

### OID Encoding

Object Identifiers are dotted decimal sequences like `1.2.840.113549.1.1.11`. The first two arcs share a byte: `byte0 = 40 * a + b`. Subsequent arcs are base-128 with the high bit set on every byte except the last.

| Arc | Base-128 bytes |
|-----|----------------|
| 1   | 0x2A        (40*1 + 2)   |
| 2   | 0x86 0x48    (840 = 6*128 + 72) |
| 840 | 0x86 0xF7 0x0D (113549) |

Common OIDs we will see:

| OID | Algorithm |
|-----|-----------|
| 1.2.840.113549.1.1.11 | sha256WithRSAEncryption |
| 1.2.840.10045.4.3.2 | ecdsa-with-SHA256 |
| 1.3.101.112 | Ed25519 |
| 2.5.4.3 | commonName (id-at-commonName) |

### X.509 v3 Field Layout (RFC 5280 §4.1)

```
Certificate ::= SEQUENCE {
    tbsCertificate       TBSCertificate,
    signatureAlgorithm   AlgorithmIdentifier,
    signatureValue       BIT STRING
}
```

| Field | Tag | Notes |
|-------|-----|-------|
| version | [0] EXPLICIT Version | context-specific, constructed, tag 0xA0 |
| serialNumber | INTEGER | 0x02 |
| signature | AlgorithmIdentifier | SEQUENCE { OID, NULL } |
| issuer | Name | SEQUENCE OF SET OF SEQUENCE |
| validity | Validity | SEQUENCE of two Time choices |
| subject | Name | same as issuer |
| subjectPublicKeyInfo | SubjectPublicKeyInfo | SEQUENCE { AlgorithmIdentifier, BIT STRING } |

### Real Certificate Byte Walk

```
30 82 03 C9           SEQUENCE (length 969 bytes)
  30 82 02 B1         tbsCertificate SEQUENCE (length 689)
    A0 03             [0] EXPLICIT version
      02 01 02        INTEGER 2 (v3)
    02 10             INTEGER (length 16) — serial number
      ...
```

You can reproduce this with `openssl x509 -in cert.pem -outform DER | xxd | head`.

## Build It

`main.py` ships:

- `encode_length(n)` / `decode_length(data, offset)`.
- `encode_integer(n)` / `decode_integer(data, offset)`.
- `encode_oid(dotted)` / `decode_oid(bytes)`.
- `encode_bit_string(bits)` / `decode_bit_string(data, offset)`.
- `encode_octet_string(b)` / `decode_octet_string(data, offset)`.
- `encode_utctime(dt)` / `decode_utctime(data, offset)`.
- `encode_sequence(children)` / `decode_sequence(data, offset)`.
- `build_x509_v3_skeleton(subject, issuer, public_key_oid, public_key_bits) -> bytes`.

```python
from main import encode_sequence, encode_integer, encode_oid, decode_oid

oid = encode_oid("1.2.840.113549.1.1.11")
print(oid.hex())               # -> 06 09 2a 86 48 86 f7 0d 01 01 0b
print(decode_oid(oid))          # -> "1.2.840.113549.1.1.11"

skel = build_x509_v3_skeleton(
    subject="CN=example.com",
    issuer="CN=Acme Intermediate CA",
    public_key_oid="1.2.840.10045.2.1",  # id-ecPublicKey
    public_key_bits=b"\x00" * 65,          # uncompressed P-256 placeholder
)
print(skel.hex()[:80])
```

## Use It

| Routine | Purpose |
|---------|---------|
| `encode_length(n)` | DER length encoding |
| `decode_length(buf, off)` | returns (length_value, next_offset) |
| `encode_integer(n)` | shortest-form INTEGER |
| `encode_oid(dotted)` | variable-length base-128 OID |
| `encode_bit_string(bits)` | BIT STRING with explicit padding bit |
| `encode_sequence(children)` | SEQUENCE wrapper |
| `build_x509_v3_skeleton(...)` | end-to-end skeleton builder |
| `parse_all(data)` | returns a nested Python list of `(tag, value)` tuples |

## Ship It

This is a teaching encoder. In production, use `pyasn1`, `pyasn1-modules`, or the `cryptography` library — they handle edge cases like indefinite-length encoding (BER, not DER), constructed OCTET STRING, and the long form of every tag. But keep this lesson's encoder on hand: it is invaluable when debugging bad certs and when teaching new engineers the format.

## Exercises

1. Decode the bytes `30 82 01 0A 02 01 03 02 01 02` by hand and identify each TLV. Then run `parse_all` and confirm.
2. Encode `OID("1.2.840.10045.4.3.2")` (ecdsa-with-SHA256) and verify the byte sequence against `openssl asn1parse -strparse`.
3. Extend `build_x509_v3_skeleton` to add a Subject Alternative Name extension (OID 2.5.29.17) carrying `DNS:example.com`.
4. Implement `decode_bit_string` with explicit handling of the unused-bits byte (first byte after tag+length).
5. Catch a malformed length (e.g., `30 81 04 01 02`) where the length byte says 4 but only 2 bytes follow. Raise `ASN1DecodeError` with a precise offset.
6. Compare your skeleton's hex output against `openssl req -new -x509 -key key.pem -outform DER | xxd` for a real Ed25519 self-signed cert.

## Key Terms

| Term | Definition |
|------|------------|
| ASN.1 | Abstract Syntax Notation One (ITU-T X.680), the type system. |
| DER | Distinguished Encoding Rules (ITU-T X.690), the binary encoding. |
| TLV | Tag-Length-Value triple, the universal DER structure. |
| OID | Object Identifier, dotted decimal such as 1.2.840.113549.1.1.11. |
| SEQUENCE | Ordered ASN.1 container, tag 0x30. |
| SET | Unordered ASN.1 container, tag 0x31. |
| Context-specific tag | [n] wrappers used in X.509 for optional/version fields. |
| Constructed | A TLV whose value is a concatenation of inner TLVs. |
| BER | Basic Encoding Rules (looser than DER; allows non-shortest forms). |

## Further Reading

- ITU-T X.680, Abstract Syntax Notation One.
- ITU-T X.690, ASN.1 Encoding Rules (BER, CER, DER).
- RFC 5280, Internet X.509 Public Key Infrastructure Certificate and CRL Profile.
- RFC 3279, Algorithms and Identifiers for X.509.
- Peter Gutmann, "X.509 Style Guide" — practical pitfalls in DER.
- `openssl asn1parse` — interactive DER dissection tool.