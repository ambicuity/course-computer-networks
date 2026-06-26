# Symmetric-key Signatures

> Digital signatures prove authorship, integrity, and nonrepudiation without public-key cryptography by routing every signed message through a central trusted authority called Big Brother (BB). Each user chooses a secret key and delivers it to BB in person; BB is the only party who can decrypt a user's signed message and re-sign it for the recipient. Alice's signed payload is K_A(B, R_A, t, P) — Bob's identity, a random nonce, a timestamp, and the plaintext — encrypted under her key K_A. BB decrypts it, then sends Bob K_B(A, R_A, t, P, K_BB(A, t, P)). The inner K_BB(A, t, P) is BB's own signature: only BB could have produced it, and only BB can verify it in court. Freshness comes from the timestamp t and the nonce R_A; Bob rejects any message whose R_A he has seen in the past hour, defeating instant replay. The weakness is structural: BB reads every signed message, everyone must trust BB, and BB is a single point of failure. This is why public-key signatures replaced it for most general-purpose signing — but the symmetric-key model survives inside KDC and Kerberos designs covered later in this phase.

**Type:** Build
**Languages:** Python (stdlib hmac/hashlib)
**Prerequisites:** Phase 14 cryptography foundations (symmetric-key algorithms, cipher modes)
**Time:** ~50 minutes

## Learning Objectives

- Trace the five-field message K_A(B, R_A, t, P) through BB to Bob and explain why each field is present.
- Explain how K_BB(A, t, P) serves as nonrepudiable evidence in a dispute.
- Identify the replay attack against the symmetric-key signature protocol and the nonce-plus-timestamp defense.
- Name the three structural weaknesses (BB reads all mail, single point of trust, single point of failure) that motivated public-key signatures.
- Demonstrate the protocol end-to-end with `code/main.py` using HMAC-SHA256 as the symmetric primitive.

## The Problem

A bank receives an electronic order: "Buy one ton of gold for account 12345." The customer later denies sending it. With paper, a handwritten signature settles the dispute. With bits, the original and a copy are indistinguishable, so the bank needs a cryptographic equivalent: something the customer alone could have produced, something the bank cannot forge, and something a judge can verify. Symmetric-key signatures solve this by introducing a trusted third party — Big Brother — who co-signs every transaction.

## The Concept

### The Big Brother protocol

The protocol from section 8.4.1 has three principals: Alice (sender), Bob (recipient/banker), and BB (trusted authority). Each user registers a secret key with BB in person.

| Step | Direction | Message | Purpose |
|------|-----------|---------|---------|
| 1 | Alice → BB | A, K_A(B, R_A, t, P) | Alice signs her request under K_A |
| 2 | BB → Bob | K_B(A, R_A, t, P, K_BB(A, t, P)) | BB re-wraps for Bob + attaches BB's signature |

BB decrypts step 1 with K_A, reads B and P, then encrypts the result for Bob under K_B. Crucially, BB adds K_BB(A, t, P) — a signature only BB can create. Bob cannot forge it; Alice cannot forge it; Trudy cannot forge it.

### Why each field exists

| Field | Role | Failure without it |
|-------|------|--------------------|
| B (Bob's identity) | Prevents BB from delivering the signed message to the wrong recipient | Trudy could substitute herself as recipient |
| R_A (Alice's nonce) | Detects instant replay; Bob keeps recent nonces | Trudy replays step 1 verbatim |
| t (timestamp) | Bounds freshness window; old messages rejected | 5-year-old replayed order still "valid" |
| P (plaintext) | The actual payload being signed | Nothing to dispute about |
| K_BB(A, t, P) | Nonrepudiable evidence for court | Bob could forge his own "signature" |

### The dispute resolution scene

When Alice denies the order, Bob produces Exhibit A: K_BB(A, t, P). The judge asks BB to decrypt it. BB confirms the timestamp and payload match. Since only BB can produce K_BB(...), and BB only does so when Alice's original K_A(B, R_A, t, P) decrypted correctly, Alice is trapped. This is nonrepudiation: Alice cannot later deny having signed.

### Replay defense in depth

The source notes two layers of replay protection. First, the timestamp t lets Bob reject very old messages outright. Second, Bob checks R_A against all messages received from Alice in the past hour — if R_A was already seen, the message is discarded as a replay. The nonce R_A must be drawn from a large space (e.g., 128-bit random numbers) so Trudy cannot guess an unused one. See `code/main.py` for a working nonce-cache replay detector.

### The reflection attack does not apply here

Unlike the shared-secret challenge-response protocols in lesson 06, the Big Brother model has BB as an intermediary who decrypts and re-encrypts. Trudy cannot reflect a challenge back because there is no challenge-response loop between Alice and Bob — BB breaks the symmetry. This is a design advantage, though it comes at the cost of BB reading every message.

### Structural weaknesses

| Weakness | Consequence | Mitigation in later lessons |
|----------|-------------|-----------------------------|
| BB reads all signed messages | No end-to-end confidentiality from BB | Public-key signatures (lesson 02) |
| Everyone must trust one authority | Government/bank/lawyer as BB inspires varied confidence | PKI with multiple roots (lesson 05) |
| BB is a single point of failure | If BB goes down, all signing stops | KDC federation, Kerberos realms (lessons 07–08) |

### Relationship to HMAC

Modern systems implement K_BB(A, t, P) as an HMAC: HMAC-SHA256(K_BB, A || t || P). The hmac module in Python's stdlib does exactly this. `code/main.py` uses HMAC-SHA256 to simulate the entire protocol, including replay detection via a bounded nonce cache.

## Build It

1. Run `code/main.py` — it simulates Alice signing a message, BB re-signing, Bob verifying, and a replay attempt being caught.
2. Inspect the nonce cache: Bob prints which R_A values he has seen.
3. Modify the timestamp window (line ~140) to 0 seconds and observe that replay detection now relies solely on the nonce cache.
4. The SVG in `assets/symmetric-key-signatures.svg` shows the three-principal message flow.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Verify a signature | K_BB(A, t, P) decrypts under BB's key and matches (A, t, P) | HMAC recomputation matches the stored tag |
| Detect replay | R_A appears in Bob's nonce cache | Second message with same R_A is rejected with "replay detected" |
| Prove nonrepudiation | Judge decrypts K_BB(A, t, P) via BB | Plaintext P matches the disputed order |
| Identify BB as bottleneck | BB processes every signed message | Removing BB breaks the protocol entirely |

## Ship It

Create one artifact under `outputs/`:

- A one-page protocol-flow diagram annotating which field prevents which attack
- A replay-detection nonce-cache implementation (extracted from main.py)
- A study prompt that walks through the court dispute scene field by field

Start with [`outputs/prompt-symmetric-key-signatures.md`](../outputs/prompt-symmetric-key-signatures.md).

## Exercises

1. Alice sends K_A(B, R_A, t, P) but forgets to include R_A. Describe exactly how Trudy replays the message to Bob 10 minutes later.
2. Bob's nonce cache is lost in a crash. What replay attacks become possible, and how does the timestamp t limit the damage?
3. BB decides to log every (A, t, P) tuple. What privacy concern does this raise, and how do public-key signatures (lesson 02) avoid it?
4. Modify `code/main.py` so that BB's key K_BB is compromised. Show that Bob can no longer trust K_BB(A, t, P).
5. Compare the five-field message K_A(B, R_A, t, P) with the HMAC-based authentication in lesson 06. Which fields correspond, and which are missing?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| Big Brother | "the central server" | Trusted authority that co-signs every message; reads all plaintext |
| K_BB(A, t, P) | "BB's signature" | Symmetric encryption of (A, t, P) under BB's key — nonrepudiable in court |
| R_A (nonce) | "random number" | One-time-use value Alice generates to prevent instant replay |
| Nonrepudiation | "can't deny it" | Property that the sender cannot later disown the message, proven by K_BB |
| Replay attack | "resend old message" | Trudy resends a valid old message; defeated by nonce cache + timestamp |
| Symmetric-key signature | "signing with one key" | Signature scheme where sender and verifier share a secret key via BB |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), Chapter 8, Section 8.4.1 — Symmetric-Key Signatures
- RFC 2104 — HMAC: Keyed-Hashing for Message Authentication
- RFC 4120 — The Kerberos Network Authentication Service (V5), Section 3 for KDC-based signature analogues
- Kaufman, Perlman & Speciner, *Network Security: Private Communication in a Public World* — trusted third-party protocols