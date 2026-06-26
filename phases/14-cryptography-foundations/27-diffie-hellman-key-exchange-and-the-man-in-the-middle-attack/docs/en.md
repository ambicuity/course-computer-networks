# Diffie-Hellman key exchange and the man-in-the-middle attack

> Diffie-Hellman (DH) key exchange lets two parties who have never met derive a shared secret over an insecure channel by exploiting the difficulty of the discrete logarithm problem in a multiplicative group. Alice picks a prime p and a generator g, transmits (p, g, g^a mod p); Bob transmits (g^b mod p); both compute g^(ab) mod p. The cost of breaking DH is the cost of computing a from g^a mod p, which for a 2048-bit prime is approximately 2^112 operations on the best known algorithms (Number Field Sieve). The classic vulnerability is the man-in-the-middle (MITM) attack: Trudy sits between Alice and Bob, establishes two DH exchanges (one with Alice, one with Bob), and reads both conversations in cleartext. The defense is to authenticate the DH exchange — by signing g^a and g^b with RSA, or by running inside an authenticated tunnel. This lesson ships a stdlib-only Python simulator (code/main.py) that runs a working DH exchange using the small IETF "second Oakley group" (1536-bit, RFC 3526) reduced for demonstration, demonstrates the MITM attack, and shows how RSA-signed DH parameters defeat it.

**Type:** Learn
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 14 lessons 01-09 (modular arithmetic, RSA), Chapter 8.3.2
**Time:** ~80 minutes

## Learning Objectives

- Trace the three-message DH key exchange: parameter announcement, public-value exchange, and shared-secret derivation, and explain why both parties arrive at the same key.
- Implement modular exponentiation in Python stdlib using pow(base, exp, mod) and verify that (g^a)^b mod p equals (g^b)^a mod p.
- Construct a man-in-the-middle attack where Trudy replaces Alice's g^a with g^t and Bob's g^b with g^t, and show that Trudy derives two separate keys.
- Apply three defenses (signed DH parameters via RSA, authenticated tunnels, and identity-bound exchanges) and verify that each blocks the MITM.
- Compare DH group sizes: 1024-bit DH (deprecated), 2048-bit DH (~112-bit security), 3072-bit DH (~128-bit security), and x25519 (128-bit security with 256-bit keys).

## The Problem

Two hosts, Alice and Bob, have never met. They want to encrypt their conversation with AES-256 but they have no shared secret to use as a key. Asking a courier to hand-deliver a key is expensive and slow. Asking each other over an unencrypted channel gives Trudy the same key. Asking a Key Distribution Center works but introduces a single point of trust and a round-trip to the KDC. Diffie-Hellman solves this elegantly: both parties broadcast a *public value* derived from a *private secret* they keep, and the math guarantees that both parties arrive at the same shared key even though no key was ever transmitted. The cost is that the math (the discrete log problem) is hard for Trudy to invert.

The MITM attack breaks DH because the protocol has no authentication: Trudy can sit on the wire, replace Alice's g^a with g^t_a, replace Bob's g^b with g^t_b, and run two separate DH exchanges. Alice and Bob each believe they share a key with the other, but actually each shares a key with Trudy. The fix is to authenticate the public values, which is what every real protocol does (TLS, SSH, IPsec IKE).

## The Concept

Source: chapters/chapter-08-network-security.md, section 8.3.2 (Diffie-Hellman). The companion diagram is assets/diffie-hellman-key-exchange-and-the-man-in-the-middle-attack.svg.

### The discrete logarithm problem

DH security rests on the difficulty of computing a from (g, p, g^a mod p). For a 2048-bit prime p, the best known algorithm (Number Field Sieve, GNFS) takes approximately 2^112 operations, which is the same work factor as breaking RSA-2048. For 3072-bit p, the cost is approximately 2^128 operations. The takeaway is that DH group size maps to security level directly: |p|/2 ≈ symmetric-key security bits.

### The protocol in three steps

| Step | From | To | Wire | What |
|------|------|----|------|------|
| 0 | Public | -- | (p, g) | System parameters; p is a safe prime (p = 2q+1), g is a generator of Z*_p |
| 1 | Alice | Bob | g^a mod p | Alice's public value |
| 2 | Bob | Alice | g^b mod p | Bob's public value |
| 3 | Both | -- | K = g^(ab) mod p | Alice computes (g^b)^a, Bob computes (g^a)^b; both arrive at K |

The order of the wires is two messages, but the conceptual exchange has three steps including the shared parameter announcement. In practice (p, g) are fixed for a long time (RFC 3526 defines six groups of 1536, 2048, 3072, 4096, 6144, and 8192 bits).

### The MITM attack in detail

Trudy sits between Alice and Bob. She intercepts both public values and substitutes her own:

| Original | Wire | MITM becomes |
|----------|------|--------------|
| Alice -> Bob: g^a | Trudy modifies to g^t_a | Bob <- Trudy: g^t_a |
| Bob -> Alice: g^b | Trudy modifies to g^t_b | Alice <- Trudy: g^t_b |

Alice and Bob each compute a key with Trudy:
- Alice computes K_A = (g^t_b)^a mod p. Trudy knows K_A too: K_A = (g^a)^t_b mod p.
- Bob computes K_B = (g^t_a)^b mod p. Trudy knows K_B too: K_B = (g^b)^t_a mod p.

Trudy reads both conversations. The protocol "succeeded" from Alice and Bob's perspective, but the security property is gone.

### Defense 1: signed DH parameters (RSA or ECDSA)

The standard fix: Alice signs (g^a mod p) with her RSA private key and Bob signs (g^b mod p) with his. Trudy cannot forge Alice's signature because she does not know Alice's private key. This is exactly what TLS 1.2 does in the DHE-RSA and ECDHE-RSA cipher suites (RFC 5246, RFC 4346).

### Defense 2: authenticated tunnel

Run DH inside an already-authenticated channel (e.g., SSH after host-key verification, or a pre-shared key). The tunnel prevents Trudy from injecting her own values. SSH uses this: the DH exchange is authenticated by the host key the client already trusts.

### Defense 3: identity-bound exchange

Use identity-based cryptography (IBE) or pass the DH public value through a key-derivation function that mixes in both parties' identities. Real protocols like IKEv2 use a transcript hash that includes all previous handshake bytes (RFC 7296 Section 2).

### Where DH is used in real protocols

- TLS 1.2 DHE-RSA, DHE-DSS, ECDHE-RSA, ECDHE-ECDSA cipher suites.
- SSH Transport Layer Protocol, RFC 4253.
- IPsec IKEv1 and IKEv2, RFCs 2409 and 7296.
- Off-the-Record (OTR) messaging protocol.
- Modern x25519 (Curve25519) is the de facto choice for forward-secret key agreement.

## Build It

code/main.py implements Diffie-Hellman with MITM demo. Work through it in this order:

1. Run python3 main.py and read the import block. The protocol uses pow(base, exp, mod) for modular exponentiation and secrets for randomness. There are no third-party dependencies.
2. Read the small-prime group constants at the top: a 256-bit safe prime p and a generator g of order q. Using a small prime here keeps the demo fast; in production use RFC 3526 groups.
3. Read DHParticipant.__init__: each party has a private int a and computes the public g^a mod p. Both Alice and Bob use the same code.
4. Read derive_shared: K = pow(their_public, my_private, p). Verify that Alice's K equals Bob's K using assert.
5. Read scenario_mitm: Trudy creates two private keys t_a and t_b, intercepts both public values, and substitutes her own. Both Alice and Bob "succeed" but end up with different keys.
6. Read scenario_signed_dh: each party signs its public value with a long-term RSA-style key (simulated via HMAC over an authenticated channel). Trudy cannot forge without the long-term key.
7. Run the main() scenarios: honest DH, MITM, signed DH (MITM blocked).

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| Derive a shared key | pow(g^a, b, p) == pow(g^b, a, p) | Both Alice and Bob print the same K hex string |
| Detect MITM | Alice's K_A differs from Bob's K_B | Demo prints different K values for the two honest parties |
| Block MITM with signatures | signature of (g^a mod p) verified under Alice's long-term public key | Trudy cannot substitute her own value without invalidating the signature |
| Choose group size | RFC 3526 Group 14 (2048-bit) for 112-bit security; Group 15 (3072-bit) for 128-bit; x25519 for 128-bit with smaller keys | Documented in code/main.py constants |

## Ship It

Produce one artifact under outputs/:

- A one-page runbook titled "How DH avoids sending the key" that diagrams the three-step exchange and explains why the discrete log problem keeps the private values safe.
- Or a threat-model document listing who can break DH under each defense: passive eavesdropper (no, discrete log), MITM without auth (yes), MITM with signed params (no, cannot forge signature).

Start from outputs/prompt-diffie-hellman-key-exchange-and-the-man-in-the-middle-attack.md and back every claim with a transcript from code/main.py.

## Exercises

1. Trace the DH exchange for "p = 23, g = 5, a = 6, b = 15." Compute A = g^a mod p, B = g^b mod p, and verify that A^b mod p == B^a mod p. Identify each integer's role in the protocol.
2. Describe the MITM attack step by step. At which message does Trudy first substitute her own public value? What key does Alice end up using, and what key does Bob end up using?
3. Modify code/main.py to use a 1024-bit safe prime from RFC 2409 Oakley Group 2. Measure how long the pow() calls take. How does the time change with a 2048-bit prime?
4. Implement the RSA-signed DH defense: each party hashes (g^a mod p) with SHA-256, signs with RSA-2048 (or HMAC under a long-term key), and verifies before deriving K. Show that Trudy's MITM attempt now fails because her substituted value produces an invalid signature.
5. Compare the security levels of 1024-bit DH, 2048-bit DH, and x25519. For each, give the symmetric-equivalent security bits and identify which is appropriate for new deployments in 2026.
6. Tanenbaum notes that the discrete log problem is "as hard as factoring." Use the literature to argue why this claim is approximately true but not exactly true, and identify the polynomial-time algorithm that connects the two (Miller's reduction for prime-field DH).

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Diffie-Hellman | "key agreement" | Two-party protocol that derives a shared secret from public values without sending the secret |
| Discrete logarithm | the hard problem | Given (g, p, g^a mod p), find a; cost is sub-exponential but super-polynomial |
| Safe prime | p = 2q + 1 | Prime whose (p-1)/2 is also prime; prevents small-subgroup attacks |
| Generator g | a primitive root | Element of Z*_p whose powers generate the whole group |
| RFC 3526 | the standard groups | Six MODP groups (1536 to 8192 bits) used in IKE, TLS, SSH |
| x25519 | modern DH | Curve25519 ECDH; 128-bit security with 256-bit keys; the 2026 default |
| MITM | the active attack | Trudy substitutes her own public values for both parties' |
| Signed DH | the defense | Sign (g^a mod p) with a long-term RSA or ECDSA key to bind the value to an identity |
| Forward secrecy | past is safe | Compromise of long-term key does not retroactively decrypt past sessions (DHE/ECDHE gives this; RSA key transport does not) |

## Further Reading

- Diffie, W., and Hellman, M. E. (1976). "New Directions in Cryptography." IEEE Transactions on Information Theory IT-22(6): 644-654 — the original paper.
- RFC 3526 — More Modular Exponential (MODP) Diffie-Hellman groups for IKE.
- RFC 4253 — SSH Transport Layer Protocol (DH exchange with host-key authentication).
- RFC 5246 — TLS 1.2 (DHE-RSA cipher suite).
- RFC 7296 — IKEv2 (signed DH in the AUTH exchange).
- RFC 7748 — Elliptic Curves for Security (defines x25519 and x448).
- Menezes, A., van Oorschot, P., and Vanstone, S. (1996). Handbook of Applied Cryptography, Chapter 12 — Diffie-Hellman key agreement.
- Tanenbaum & Wetherall, Computer Networks, Chapter 8 Section 8.3.2.