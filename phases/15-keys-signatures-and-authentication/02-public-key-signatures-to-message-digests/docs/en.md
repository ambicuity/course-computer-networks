# Public-key Signatures to Message Digests

> Public-key signatures remove the trusted Big Brother from signing: Alice signs by encrypting the message under her *private* key D_A, and Bob verifies by applying Alice's *public* key E_A. The construction E_A(D_A(P)) = P works because RSA has the property that D(E(P)) = P *and* E(D(P)) = P, so decryption with the private key inverts into a signature. The scheme gives nonrepudiation without a central authority reading the mail — but it has two environmental weaknesses: if Alice discloses D_A (claims a "burglary") the signature argument collapses, and if Alice rotates keys a judge applying the *current* E_A to an *old* D_A(P) gets garbage. Message digests solve the performance half of the problem: instead of signing the entire plaintext P (slow — RSA on megabytes is impractical), Alice computes MD(P) — a fixed-length 160-bit (SHA-1) or 256-bit (SHA-256) hash — signs only the digest as D_A(MD(P)), and sends both P and D_A(MD(P)) to Bob. Bob recomputes MD(P) and applies E_A to the signed digest; if they match, the message is authentic and unmodified. MD5 (128-bit, Rivest) is broken — collisions have been demonstrated (Sotirov et al. 2008) — and must not be used in new designs. SHA-1 (160-bit, NSA/NIST FIPS 180-1) processes 512-bit blocks through 80 rounds of five 32-bit state words; SHA-2 (224/256/384/512-bit) supersedes it. A valid digest function has four properties: easy to compute, hard to invert, hard to find a second preimage, and avalanche (1-bit input change → drastically different output).

**Type:** Build
**Languages:** Python (stdlib hashlib, hmac, rsa toy)
**Prerequisites:** Lesson 01 (symmetric-key signatures), Phase 14 RSA
**Time:** ~55 minutes

## Learning Objectives

- Explain why E_A(D_A(P)) = P serves as a digital signature and why D_A(P) alone is the signed evidence in court.
- Describe the two environmental weaknesses of raw public-key signatures (key disclosure, key rotation) and why they are not algorithm flaws.
- Define the four properties a message digest must satisfy and identify which property MD5 fails.
- Trace the SHA-1 compression function: 512-bit block → 80 words W_0..W_79 → five 32-bit state words H_0..H_4 → 160-bit hash.
- Demonstrate the digest-sign-verify pipeline in `code/main.py` using SHA-256 and a toy RSA.

## The Problem

Big Brother (lesson 01) reads every signed message and is a single point of trust. Alice wants to sign a purchase order directly to Bob with no intermediary. She also wants to sign a 10 MB contract — and RSA-signing 10 MB is hundreds of times slower than signing a 256-bit hash. She needs a scheme that is nonrepudiable without BB and fast enough for real documents.

## The Concept

### Public-key signature mechanics

Alice sends E_B(D_A(P)) to Bob — encrypted *and* signed. Bob applies D_B to get D_A(P), stores it as evidence, then applies E_A to recover P. The signature property: only Alice knows D_A, so only Alice could have produced D_A(P). In court, Bob produces P and D_A(P); the judge applies E_A and checks.

| Property | How it holds |
|----------|-------------|
| Receiver can verify sender | Bob applies E_A to D_A(P) → gets P back |
| Sender cannot repudiate | Only Alice has D_A; Bob could not have forged D_A(P) |
| Receiver cannot concoct | Bob does not know D_A, so he cannot synthesize a valid D_A(P) for a different P |

### The two environmental weaknesses

These are not flaws in RSA — they are flaws in *using* RSA for signatures in the real world.

**Weakness 1 — Key disclosure excuse.** Alice tells Bob to buy stock; price crashes; Alice reports a "burglary" and claims D_A was stolen. Depending on jurisdiction she may escape liability. The argument "only Alice could have signed" breaks because *anyone* with D_A could have.

**Weakness 2 — Key rotation.** Alice routinely changes keys (good practice). Months later in court, the judge applies the *current* E_A to the old D_A(P). It does not produce P. Bob looks foolish. The fix is timestamped key archives, but that requires infrastructure (lesson 04 certificates, lesson 05 PKI).

### DSS and the El Gamal detour

NIST proposed DSS in 1991, based on El Gamal (discrete-logarithm security, not factoring). It was criticized for: too secret (NSA-designed), too slow (10–40× slower than RSA for verification), too new, and originally fixed at 512-bit keys. Keys up to 1024 bits were later allowed. RSA remains the de facto industry standard.

### Message digests: the performance fix

A message digest MD is a one-way hash with four mandatory properties:

| # | Property | Why it matters |
|---|----------|---------------|
| 1 | Given P, easy to compute MD(P) | Signatures must be fast |
| 2 | Given MD(P), hard to find P | Prevents inversion attacks |
| 3 | Given P, hard to find P' ≠ P with MD(P') = MD(P) | Second-preimage resistance — prevents substitution |
| 4 | 1-bit change → drastically different output | Avalanche; detects tampering |

Property 3 requires digest length ≥ 128 bits, preferably more. Property 4 is why SHA-1 mangles bits through 80 rounds.

### The digest-sign-verify pipeline

```
Alice:                                  Bob:
  P ──SHA-256──> MD(P)                    receives P, D_A(MD(P))
  D_A(MD(P)) ──sign──> signed digest      SHA-256(P) ──recompute──> MD(P)'
  send P + D_A(MD(P)) ───────────────>    E_A(D_A(MD(P))) ──verify──> MD(P)
                                          MD(P)' == MD(P)? → accept
```

Trudy can replace P with P' but cannot forge D_A(MD(P')) because she lacks D_A. Bob detects the swap when MD(P') ≠ MD(P). This is the integrity guarantee.

### SHA-1 internals (the 80-round compression)

SHA-1 (FIPS 180-1, RFC 3174) pads the message with a 1-bit, zero bits, and a 64-bit length to a multiple of 512 bits. It maintains five 32-bit state words H_0..H_4 (initialized to constants). For each 512-bit block it expands 16 words into 80 words via W_i = S_1(W_{i-3} XOR W_{i-8} XOR W_{i-14} XOR W_{i-16}), then runs 80 rounds of:

```
temp = S_5(A) + f_i(B,C,D) + E + W_i + K_i
E=D; D=C; C=S_30(B); B=A; A=temp
```

The mixing functions f_i change every 20 rounds (Ch, Parity, Maj, Parity). After all blocks, H_0..H_4 concatenate to the 160-bit hash. See `code/main.py` for a from-scratch SHA-1 compression function (educational, not for production).

### MD5 and why it died

MD5 (Rivest) pads to 448 mod 512, appends a 64-bit length, mixes 512-bit blocks through a 128-bit buffer using a sine-derived table. After a decade of use, researchers found collisions (Sotirov et al. 2008) — different messages with the same hash. Property 3 is violated. MD5 is considered broken; do not use it in new systems. You will still see it in legacy contexts.

### SHA-2 family

SHA-2 produces 224, 256, 384, or 512-bit hashes with a revised compression function to counter SHA-1 weaknesses. SHA-256 is the modern default. `code/main.py` uses Python's `hashlib.sha256` for real verification and a hand-rolled SHA-1 for teaching the compression logic.

## Build It

1. Run `code/main.py` — it signs a message with a toy RSA private key over its SHA-256 digest, then verifies. It also demonstrates a tampered message being rejected.
2. Inspect the hand-rolled SHA-1 compression function (lines ~60–130) to see the 80-round loop and the four mixing functions.
3. Modify one byte of the plaintext after signing and observe the digest mismatch.
4. The SVG in `assets/public-key-signatures-to-message-digests.svg` shows the digest-sign-verify pipeline.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Sign a message | D_A(MD(P)) produced; SHA-256 digest is 32 bytes | Tag is 256 bits; verification with E_A recovers the same digest |
| Verify a signature | E_A(D_A(MD(P))) == SHA-256(P) | Bit-exact match; no exceptions |
| Detect tampering | Change 1 byte of P after signing; recompute MD(P') | MD(P') ≠ MD(P); verification fails |
| Identify MD5 weakness | Find two messages with same MD5 (conceptual) | Property 3 (second-preimage resistance) is violated |
| Compare SHA-1 vs SHA-256 | Hash the same input with both | SHA-1 → 20 bytes; SHA-256 → 32 bytes |

## Ship It

Create one artifact under `outputs/`:

- A digest-sign-verify reference implementation (extract the toy RSA + SHA-256 from main.py)
- A diagram of the 80-round SHA-1 compression function annotated with the four mixing functions
- A study prompt contrasting Big Brother (lesson 01) with direct public-key signing

Start with [`outputs/prompt-public-key-signatures-to-message-digests.md`](../outputs/prompt-public-key-signatures-to-message-digests.md).

## Exercises

1. Alice signs P with D_A, then claims her key was stolen. Why is this an *environmental* weakness, not an RSA algorithm flaw? What infrastructure (lesson 04/05) mitigates it?
2. Bob rotates keys every 90 days. Six months later he tries to verify an old D_A(P) with the *current* E_A. What happens? What does he need to do instead?
3. Compute SHA-256("hello") and SHA-256("Hello"). How many of the 256 output bits differ? Does this match property 4 (avalanche)?
4. Why is signing MD(P) with D_A faster than signing P directly with D_A? Quantify for a 10 MB document and a 2048-bit RSA key.
5. MD5 is broken (collisions found). Why does this make it unsafe for signatures even if you "only" use it for integrity checking? Relate to the birthday attack in lesson 03.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| Public-key signature | "sign with private key" | D_A(P) — encryption under the private key; verified by E_A |
| Nonrepudiation | "can't deny it" | Only Alice has D_A, so only she could have produced D_A(P) |
| Message digest | "a hash" | One-way fixed-length fingerprint MD(P) with the four properties |
| Second-preimage resistance | "no collision" | Given P, hard to find P' ≠ P with MD(P') = MD(P) |
| SHA-1 | "the 160-bit one" | NSA/NIST FIPS 180-1; 512-bit blocks, 80 rounds, 160-bit output |
| SHA-256 | "the 256-bit one" | SHA-2 family; modern default for new systems |
| MD5 | "the old one" | 128-bit; BROKEN — collisions found; do not use |
| DSS | "NIST's standard" | Digital Signature Standard based on El Gamal (discrete log) |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), Chapter 8, Sections 8.4.2–8.4.3
- FIPS 180-1 — Secure Hash Standard (SHA-1)
- FIPS 180-4 — Secure Hash Standard (SHA-2 family)
- RFC 3174 — US Secure Hash Algorithm 1 (SHA-1) C source code
- Rivest, "The MD5 Message-Digest Algorithm" (RFC 1321) — and why it is now broken
- Sotirov, Stevens, et al. (2008) — MD5 collision demonstration