# PGP-pretty Good Privacy to S/MIME

> PGP (Pretty Good Privacy), released in 1991 by Phil Zimmermann, is a complete email security package providing privacy, authentication, digital signatures, and compression. It encrypts data with IDEA (128-bit keys), manages keys with RSA, and provides integrity with MD5. A PGP message flows through five steps: MD5 hash of plaintext, RSA-encrypt the hash with Alice's private key D_A (signature), concatenate with plaintext, ZIP compress, prompt for random input to generate a 128-bit IDEA message key K_M, encrypt P1.Z with IDEA in cipher feedback mode, encrypt K_M with Bob's public key E_B, base64-encode the result. RSA is used only on 256 bits total (128-bit hash + 128-bit key), so the slow public-key algorithm is not a bottleneck. PGP supports four RSA key lengths: Casual (384 bits, breakable), Commercial (512, breakable by three-letter agencies), Military (1024), Alien (2048). S/MIME (RFCs 2632-2643) is IETF's email security standard: it provides authentication, integrity, secrecy, and nonrepudiation; uses multiple trust anchors instead of a rigid hierarchy; and integrates with MIME via new headers for digital signatures. PGP's key management is decentralized (each user keeps a private key ring and a public key ring with trust indicators), setting it apart from centralized PKI schemes.

**Type:** Learn
**Languages:** openssl, browser tools, Wireshark
**Prerequisites:** Phase 14 cryptography; Phase 15 keys, signatures, authentication
**Time:** ~75 minutes

## Learning Objectives

- Trace the five-step PGP encryption flow: MD5 hash, RSA signature with private key, ZIP compression, IDEA encryption with a random message key, RSA encryption of the message key with the recipient's public key, base64 encoding.
- Explain why RSA is used only on 256 bits (128-bit MD5 hash + 128-bit IDEA key) and why this keeps the slow public-key algorithm off the critical path.
- List the four PGP RSA key lengths (384, 512, 1024, 2048 bits) and their practical security levels.
- Describe PGP key management: private key ring (encrypted by a password), public key ring (with trust indicators), and the decentralized trust model versus centralized PKI.
- Contrast PGP with S/MIME: standardization body, certificate hierarchy, MIME integration, and algorithm flexibility.
- Identify the PGP message format: key part (IDEA key + key ID), signature part (timestamp, sender key ID, algorithm types, encrypted hash), message part (header, filename, timestamp, message).

## The Problem

When an email message is sent between two distant sites, it transits dozens of machines on the way. Any of these can read and record the message. In practice, privacy is nonexistent despite what many people think. A user wants to send email that can be read only by the intended recipient — not their boss, not their government. This desire drove Phil Zimmermann to create PGP in 1991, and IETF to standardize S/MIME later. The engineering challenge is combining encryption, signatures, compression, and key management into a form that ordinary users can operate.

## The Concept

### PGP — Pretty Good Privacy

PGP is the brainchild of one person, Phil Zimmermann. His motto: "If privacy is outlawed, only outlaws will have privacy." Released in 1991, PGP is a complete email security package providing privacy, authentication, digital signatures, and compression, all in an easy-to-use form. The complete package, including all source code, was distributed free via the Internet. Due to its quality, price (zero), and availability on UNIX, Linux, Windows, and Mac OS, it is widely used.

PGP intentionally uses existing cryptographic algorithms rather than inventing new ones. It is based on algorithms that have withstood extensive peer review and were not designed or influenced by any government agency. For people who distrust government, this property is a big plus.

| Component | Algorithm | Key size |
|-----------|-----------|----------|
| Data encryption | IDEA (International Data Encryption Algorithm) | 128 bits |
| Key management | RSA | 384-2048 bits |
| Data integrity | MD5 | 128-bit hash |
| Compression | ZIP (Ziv-Lempel algorithm) | — |

### The five-step PGP flow

When Alice wants to send a signed plaintext message P to Bob securely:

| Step | Operation | Key used | Output |
|------|-----------|----------|--------|
| 1 | MD5 hash of P | — | 128-bit hash |
| 2 | RSA-encrypt hash with Alice's private key D_A | D_A (private) | Signed hash (signature) |
| 3 | Concatenate P + signed hash, ZIP compress | — | P1.Z |
| 4 | Generate random 128-bit IDEA message key K_M; encrypt P1.Z with IDEA in CFB mode | K_M (symmetric) | Encrypted P1.Z |
| 5 | RSA-encrypt K_M with Bob's public key E_B; concatenate, base64-encode | E_B (public) | Final message |

Bob reverses the process: base64-decode, RSA-decrypt K_M with his private key, IDEA-decrypt to get P1.Z, decompress, separate plaintext from encrypted hash, RSA-decrypt the hash with Alice's public key, and verify the MD5 hash matches.

### Why RSA is not the bottleneck

RSA is used only in two places: encrypting the 128-bit MD5 hash (signature) and encrypting the 128-bit IDEA key K_M. That is 256 bits total of exceedingly random data. The heavy-duty encryption of the actual message is done by IDEA, which is orders of magnitude faster than RSA. Thus PGP provides security, compression, and a digital signature efficiently.

### PGP RSA key lengths

| Level | Bits | Security |
|-------|------|----------|
| Casual | 384 | Breakable easily today |
| Commercial | 512 | Breakable by three-letter organizations |
| Military | 1024 | Not breakable by anyone on Earth |
| Alien | 2048 | Not breakable by anyone on other planets, either |

Since RSA is only used for two small computations, everyone should use alien-strength keys all the time.

### PGP message format

A classic PGP message has three parts:

| Part | Contents |
|------|----------|
| Key part | IDEA key K_M encrypted with E_B, key identifier (which public key was used) |
| Signature part | Header, timestamp, sender's public key identifier, algorithm type info, encrypted MD5 hash |
| Message part | Header, default filename, message creation timestamp, message itself |

### PGP key management

Each user maintains two local data structures:

- **Private key ring**: one or more personal private/public key pairs. Multiple pairs let users change keys periodically or after compromise without invalidating messages in transit. Each pair has an identifier (low-order 64 bits of the public key). Private keys on disk are encrypted with a password.

- **Public key ring**: public keys of the user's correspondents, each with a 64-bit identifier and a trust indicator. The trust indicator records how much the user trusts the key — from "Bob personally handed me a CD-ROM" (highest) to "fetched from a bulletin board" (needs verification).

This decentralized, user-controlled approach sets PGP apart from centralized PKI schemes. After X.509 was standardized, PGP supported X.509 certificates as well as the traditional public key ring mechanism.

### The key-substitution attack

If public keys are maintained on bulletin boards, Trudy can attack the board and replace Bob's public key with one of her choice. When Alice fetches the key allegedly belonging to Bob, Trudy mounts a bucket-brigade (man-in-the-middle) attack. To prevent this, Alice's public key ring records how much to trust each key. If she knows Bob personally handed her a CD-ROM with the key, she sets the trust value to the highest level.

### S/MIME — Secure/MIME

IETF's venture into email security, S/MIME, is described in RFCs 2632 through 2643. It provides authentication, data integrity, secrecy, and nonrepudiation. It is flexible, supporting a variety of cryptographic algorithms. Given the name, S/MIME integrates well with MIME, allowing all kinds of messages to be protected via new MIME headers (e.g., for digital signatures).

S/MIME does not have a rigid certificate hierarchy beginning at a single root — a political problem that doomed an earlier system called PEM (Privacy Enhanced Mail). Instead, users can have multiple trust anchors. As long as a certificate can be traced back to some trust anchor the user believes in, it is considered valid.

### PGP vs S/MIME

| Aspect | PGP | S/MIME |
|--------|-----|--------|
| Origin | Phil Zimmermann (1991) | IETF (RFCs 2632-2643) |
| Key management | Decentralized (private/public key rings, trust indicators) | X.509 certificates with multiple trust anchors |
| Data encryption | IDEA (128-bit) | Flexible (various algorithms) |
| Signatures | RSA + MD5 | Flexible (various algorithms) |
| MIME integration | Preprocessor producing base64 | Native MIME headers for signatures |
| Certificate hierarchy | None (decentralized) | Multiple trust anchors (not rigid root) |

### Failure modes

- **Weak key length**: using Casual (384-bit) or Commercial (512-bit) RSA keys that are breakable today.
- **MD5 weakness**: MD5 has known collision vulnerabilities; modern PGP uses SHA-1 or SHA-256.
- **Key-substitution attack**: fetching a public key from an untrusted source without verifying it.
- **Lost private key password**: the private key ring is encrypted by a password; losing it means losing access to all stored private keys.
- **Trust indicator neglect**: failing to set trust levels on the public key ring, allowing forged keys to be treated as valid.
- **S/MIME rigid hierarchy (avoided)**: PEM was doomed by its rigid root hierarchy; S/MIME avoids this with multiple trust anchors.

`code/main.py` simulates the PGP five-step flow (hash, sign, compress, encrypt message key, encrypt with public key); `assets/pgp-pretty-good-privacy-to-s-mime.svg` diagrams the flow and message format.

## Build It

1. Run `python3 code/main.py` to see the PGP five-step flow simulated for a sample message.
2. Examine the RSA key-length table and the 256-bit total RSA workload.
3. Trigger the key-substitution attack simulation: Trudy replaces Bob's public key on the key ring.
4. Compare PGP and S/MIME output in the comparison table.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify PGP signature | gpg --verify output showing "Good signature from Alice" | Hash matches; Alice's public key is on the key ring with high trust |
| Confirm encryption | gpg --list-packets showing IDEA-encrypted session key + encrypted payload | Message key K_M is RSA-encrypted with Bob's public key |
| Audit key lengths | gpg --list-keys showing RSA key sizes | All keys are 2048-bit (Alien) or at minimum 1024-bit (Military) |
| Check S/MIME cert | openssl smime -verify with X.509 chain | Certificate traces to a trusted anchor; no single-root dependency |

## Ship It

Create one artifact under `outputs/`:

- A PGP key-management policy document (key lengths, rotation schedule, trust-level assignment).
- An S/MIME certificate chain verification runbook.
- A one-page comparison of PGP and S/MIME for a corporate email deployment.

Start with [`outputs/prompt-pgp-pretty-good-privacy-to-s-mime.md`](../outputs/prompt-pgp-pretty-good-privacy-to-s-mime.md).

## Exercises

1. Trace the five-step PGP flow for a 10KB plaintext message. At which step is RSA used, and on how many bits total? Why is this not a performance problem?
2. Alice uses a 384-bit Casual RSA key. Why is this insecure today? What key length should she use, and what is the performance impact given RSA is only used on 256 bits?
3. Trudy replaces Bob's public key on Alice's public key ring. How does PGP's trust indicator system help Alice detect this? What trust level should "fetched from a bulletin board" have?
4. Compare PGP and S/MIME: which uses a decentralized trust model, which uses X.509 certificates, and which was designed to avoid the rigid root hierarchy that doomed PEM?
5. A PGP message has three parts: key part, signature part, message part. What does each contain, and which field tells the recipient which public key to use for decryption?
6. MD5 has known collision vulnerabilities. How does this affect PGP, and what modern alternative should be used for the hash step?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| PGP | "the email crypto one" | Pretty Good Privacy — Zimmermann's 1991 package: IDEA + RSA + MD5 + ZIP, decentralized key rings |
| IDEA | "the block cipher in PGP" | International Data Encryption Algorithm, 128-bit keys, used for bulk message encryption in PGP |
| Message key K_M | "session key" | One-time 128-bit IDEA key generated per message from random input; RSA-encrypted with recipient's public key |
| Private key ring | "my keys" | Local store of personal private/public pairs, encrypted by a password, with 64-bit identifiers |
| Public key ring | "address book" | Local store of correspondents' public keys with trust indicators (highest = personal handoff) |
| Alien-strength | "2048-bit" | PGP's highest RSA key tier — "not breakable by anyone on other planets, either" |
| S/MIME | "the IETF one" | Secure/MIME (RFCs 2632-2643) — IETF email security with X.509 certificates and multiple trust anchors |
| Trust anchor | "trusted root" | A certificate a user believes in without further verification; S/MIME allows multiple anchors, avoiding PEM's single-root failure |

## Further Reading

- RFC 2440 — OpenPGP Message Format
- RFCs 2632 through 2643 — S/MIME
- Zimmermann, P. (1995) — The Official PGP User's Guide
- Levy, S. (1993) — "Crypto Rebels" (Wired, on the PGP export controversy)
- Tanenbaum and Wetherall, Computer Networks, 5th ed., Chapter 8 sections 8.8.1 and 8.8.2
