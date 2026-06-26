# Digital signatures and HMACs

> A digital signature is the public-key analog of a MAC: it ties a message to a specific signer in a way that anyone with the signer's public key can verify, but only the signer can produce. RSA signatures (RSASSA-PKCS1-v1_5, RSASSA-PSS) compute S = H(m)^d mod n with the private key and recover H(m) = S^e mod n with the public key. The hash-then-sign construction requires a collision-resistant hash; without it, an attacker who can find two messages with the same digest can substitute one for the other. ECDSA (used in TLS 1.3) and EdDSA (Ed25519) work in elliptic-curve groups and produce 64-byte signatures at the 128-bit security level. **HMAC** (RFC 2104) is the symmetric-key counterpart: H((K ⊕ opad) || H((K ⊕ ipad) || m)), a two-key nested construction that defeats the length-extension attack on Merkle-Damgård hashes. The lesson implements textbook RSA signatures, ECDSA over a small curve, and HMAC-SHA256, then verifies a sample message under each. The lesson closes with the policy implications: signature keys need long-term protection (hardware tokens, HSMs); MAC keys can be session-scoped because they only protect a single connection.

**Type:** Learn
**Languages:** Python (stdlib hashlib + hmac, textbook RSA, ECDSA over secp256r1)
**Prerequisites:** Phase 15 lesson 21 (RSA), message digests (lesson 16)
**Time:** ~80 minutes

## Learning Objectives

- Implement textbook RSA signatures (S = H(m)^d mod n, verify by S^e mod n = H(m)) and explain the role of the hash.
- Implement HMAC-SHA256 (RFC 2104) from scratch and demonstrate that it defeats the Merkle-Damgård length-extension attack.
- Implement ECDSA over a small curve (secp256r1 or a reduced-modulus toy curve) and demonstrate sign + verify with deterministic k (RFC 6979).
- Compare signature sizes: RSA-2048 = 256-byte signatures, ECDSA P-256 = 64-byte signatures, Ed25519 = 64-byte signatures.
- Discuss key-management differences: signature keys are long-term identity; HMAC keys are session-scoped.

## The Problem

A software vendor ships an update every Tuesday. Each update needs to convince 50 million customers that it came from the vendor and not from an attacker. Two cryptographic primitives fit the bill: digital signatures (public-key, anyone can verify) and MACs (symmetric, only the holder of a shared secret can verify). Digital signatures scale: the vendor holds one private key, customers hold one public key, no per-customer state. MACs do not scale: the vendor would need a separate MAC key for each customer, and revoking one is hard. Signatures are the right primitive for public software distribution.

But signatures are slow (RSA-2048 signatures take milliseconds, ECDSA microseconds, MACs nanoseconds) and the public-key infrastructure that distributes the public keys (certificates, lesson 18) is its own complexity. MACs are the right primitive for live connections: the TLS record layer uses HMAC-SHA256 in TLS 1.2 and AES-GCM (which is internally HMAC-like) in TLS 1.3, because both peers already share a key from the handshake. The lesson builds both primitives so a student can choose the right tool for the threat model.

The lesson's structural lesson: a "signature" is not "encryption with the private key." That formulation only works for textbook RSA on a single-block message. Real signatures hash the message first, pad the digest with a scheme like PSS, and then sign. The lesson walks through the structural pieces so a student is not surprised by the gaps between "encryption" and "signature" when they read a real protocol spec.

## The Concept

Source: `chapters/chapter-08-network-security.md`, sections 8.4.2 (Public-Key Signatures) and 8.3.2 (HMAC). The companion diagram is `assets/digital-signatures-and-hmacs.svg`.

### RSA signatures (RSASSA)

A textbook RSA signature is S = H(m)^d mod n, where d is the private exponent and H is a hash function. Verification recovers H(m) = S^e mod n and checks it equals the recomputed hash of m. The construction works but is brittle: an attacker who can find two messages m, m' with H(m) = H(m') can substitute m' for m in any signed message and the signature still verifies. This is why real schemes wrap the hash with a padding scheme:

- **PKCS#1 v1.5** (RSASSA-PKCS1-v1_5): pads the digest with a fixed prefix and random padding before signing. Has historical attacks (Bleichenbacher's e=3 forgery against improperly implemented verification).
- **PSS** (RSASSA-PSS, RFC 8017): probabilistic padding that adds a random salt; provably secure in the random-oracle model.

### ECDSA

ECDSA works in an elliptic-curve group. Key pair: private d, public Q = d * G where G is the base point of a prime-order subgroup. Signing message m with randomness k:

```
r = (k * G).x mod n
s = k^-1 * (H(m) + d * r) mod n
```

Signature is (r, s), 32 bytes each at the 128-bit security level. Verification: u1 = H(m) * s^-1 mod n, u2 = r * s^-1 mod n, check (u1*G + u2*Q).x == r mod n.

The security argument reduces to the Elliptic Curve Discrete Logarithm Problem (ECDLP). The randomness k must be secret and unique per signature; reusing k across two signatures leaks d (the Sony PS3 incident of 2010). RFC 6979 specifies a deterministic derivation of k from (d, m) that eliminates the catastrophic failure mode.

### EdDSA (Ed25519)

Ed25519 is a specific instantiation of EdDSA on the Edwards curve Curve25519. It uses SHA-512, has a 32-byte private key, a 32-byte public key, and a 64-byte signature. Determinism is built in (no random k generation). Performance is on the order of 100,000 signatures per second on commodity hardware. Ed25519 is the default signature algorithm in OpenSSH, Signal, and many cryptocurrency protocols.

### HMAC

HMAC is a keyed hash defined in RFC 2104:

```
HMAC(K, m) = H((K ⊕ opad) || H((K ⊕ ipad) || m))
```

where ipad and opad are 0x36 and 0x5C repeated to the hash block size, and K is the key padded to the block size with zeros. The nested construction defeats the Merkle-Damgård length-extension attack because the attacker does not know K (and therefore cannot compute the inner hash state). HMAC-SHA256 is the canonical MAC for TLS 1.2; AES-GCM (an authenticated-encryption mode) replaces HMAC in TLS 1.3 because it provides both confidentiality and integrity in one primitive.

### Key management

The lesson's structural lesson on keys:

- **Signature keys** are long-term identity. The signing key is held by the signer for years; the verifying key is held by every verifier. Compromise of the signing key is catastrophic: every signature ever issued can be repudiated or forged. Mitigation: hardware tokens (YubiKey, TPM), HSMs, air-gapped signing.
- **MAC keys** are session-scoped. A new key per session limits the blast radius of compromise. TLS forward secrecy adds a DH exchange so a stolen long-term key does not decrypt past sessions.

### Comparison table

| Primitive | Key type | Output size | Use case |
|-----------|----------|-------------|----------|
| RSA-2048 | Public 2048-bit | 256-byte sig | Legacy compatibility |
| ECDSA P-256 | Public 256-bit | 64-byte sig | TLS 1.2 / 1.3 |
| Ed25519 | Public 256-bit | 64-byte sig | SSH, modern apps |
| HMAC-SHA256 | 256-bit symmetric | 32-byte tag | TLS record layer |
| AES-GCM | 128/256-bit symmetric | 16-byte tag | TLS 1.3, IPsec |

## Build It

`code/main.py` is a stdlib-only signatures-and-MAC simulator. Work through it in this order:

1. Run `python3 main.py` and read the imports. Only stdlib: `hashlib`, `hmac`, `math`, `random`, plus the lesson 14 textbook RSA module.
2. Read `rsa_sign`. It hashes the message with SHA-256, applies PKCS#1 v1.5 padding (a fixed 0x00 0x01 prefix, fill bytes, separator, then the digest), and signs with the private key.
3. Read `rsa_verify`. It reverses the padding, recovers the digest, and checks against the recomputed hash.
4. Read `hmac_sha256_manual`. It implements HMAC from scratch using stdlib SHA-256, demonstrating the ipad/opad structure.
5. Read `ecdsa_sign` and `ecdsa_verify`. The implementation uses a small toy curve to keep the demo fast; the structure is identical to P-256.
6. Read `length_extension_resistance`. It compares `SHA-256(key || m)` (broken) with `HMAC-SHA256(key, m)` (resistant) on a sample message.
7. Run `main()`: it signs and verifies a sample message under each scheme, prints the signature sizes, and shows the length-extension comparison.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| RSA sign + verify | `verify(sign(m), m) == True` | Output equals the recomputed hash; padding is correctly stripped |
| ECDSA sign + verify | Recovery point's x-coordinate matches r | The (r, s) signature verifies deterministically |
| HMAC matches stdlib | Manual `hmac_sha256_manual(key, m)` equals `hmac.new(key, m, sha256).digest()` | Bytes are equal |
| Length-extension defense | HMAC of (key \|\| m \|\| pad \|\| X) is not computable from HMAC(key, m) | Demo shows HMAC tag changes when suffix is appended |

## Ship It

Produce one artifact under `outputs/`:

- A one-page runbook titled *"Choosing the right primitive: signature, MAC, or AEAD"* that walks through the threat model and key-management trade-offs and recommends one for a software-update channel, a TLS record layer, and a JSON Web Token.
- Or a comparison table of RSA-2048, ECDSA P-256, Ed25519, and HMAC-SHA256 showing key size, signature size, performance, and use cases.

Start from [`outputs/prompt-digital-signatures-and-hmacs.md`](../outputs/prompt-digital-signatures-and-hmacs.md) and back every claim with a transcript from `code/main.py`.

## Exercises

1. Demonstrate the Bleichenbacher RSA-PSS forgery against a server that uses `e = 3` and skips PKCS#1 v1.5 padding verification. Show how the attacker produces a signature that verifies against a chosen digest.
2. Show why reusing ECDSA randomness k across two signatures leaks the private key d. Compute d from two signatures (r, s1, s2) on messages m1, m2.
3. Implement RFC 6979 deterministic k derivation for ECDSA and show that signing the same message twice produces the same (r, s) signature.
4. Demonstrate HMAC's length-extension defense: compute HMAC-SHA256(key, m), then attempt to extend it for the longer message (key || m || pad || X) and show that the resulting tag differs.
5. Compare signature times: sign a 1 KB message with RSA-2048, ECDSA P-256 (via a library if available), and HMAC-SHA256. Report the wall-clock time per operation on your machine.
6. Explain why the SSH protocol uses Ed25519 (or ECDSA) and not RSA for host keys. What is the bandwidth / compute / key-storage advantage at the same security level?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|--------------------|
| Digital signature | "the signed receipt" | Public-key primitive; only the signer can produce; anyone with the public key can verify |
| HMAC | "the keyed hash" | H((K ⊕ opad) \|\| H((K ⊕ ipad) \|\| m)); defeats length extension |
| PKCS#1 v1.5 | "the legacy RSA padding" | Fixed-prefix padding for RSA signatures; has historical attacks |
| PSS | "the probabilistic padding" | RSA signature padding with random salt; provably secure in ROM |
| ECDSA | "the elliptic-curve signature" | Signature scheme in elliptic-curve groups; 64 bytes at 128-bit security |
| Ed25519 | "the modern signature" | Edwards-curve DSA with SHA-512; deterministic; 64-byte signatures |
| Length extension | "the Merkle-Damgård attack" | Given H(K \|\| M) and len, compute H(K \|\| M \|\| pad \|\| X) |
| ipad / opad | "the inner / outer pad" | 0x36 / 0x5C bytes repeated to hash block size in HMAC |
| RFC 6979 | "deterministic k" | ECDSA nonce derivation from (d, m); eliminates k-reuse catastrophe |

## Further Reading

- Rivest, R. L., Shamir, A., and Adleman, L. (1978). "A Method for Obtaining Digital Signatures and Public-Key Cryptosystems." *Communications of the ACM* 21(2): 120-126.
- Krawczyk, H., Bellare, M., and Canetti, R. (1997). *HMAC: Keyed-Hashing for Message Authentication*. RFC 2104.
- NIST (2013). *Digital Signature Standard (DSS)*. FIPS PUB 186-4.
- NIST (2023). *Digital Signature Standard (DSS)*. FIPS PUB 186-5 (Ed25519, Ed448, RSA-PSS).
- Johnson, D., Menezes, A., and Vanstone, S. (2001). "The Elliptic Curve Digital Signature Algorithm (ECDSA)." *International Journal of Information Security* 1(1): 36-63.
- Pornin, T. (2013). *Deterministic Usage of the Digital Signature Algorithm (DSA and ECDSA)*. RFC 6979.
- Bernstein, D. J., et al. (2012). "Ed25519: High-speed High-security Signatures." *Journal of Cryptographic Engineering* 2(2): 89-105.
- Bleichenbacher, D. (2006). "Forging RSA Signatures with e = 3." (Implementation-flaw attack on PKCS#1 v1.5.)
- Aumasson, J.-P. (2017). *Serious Cryptography*. No Starch Press. Chapter 6.
- Tanenbaum, A. S., and Wetherall, D. J. (2011). *Computer Networks*, 5th ed., Chapter 8 §8.4 — Digital Signatures.