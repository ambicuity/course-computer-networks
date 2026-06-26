# Symmetric-key digital signatures via a trusted Big Brother authority

> Digital signatures give electronic messages the same legal weight as handwritten signatures, and they must satisfy three properties: the receiver must verify the sender's claimed identity, the sender must not be able to later deny the message (nonrepudiation), and the receiver must not be able to forge the message themselves. The simplest construction, described in Tanenbaum's Chapter 8, leans on a **Big Brother (BB)** authority who holds a unique secret key K_A for every user. When Alice wants to sign plaintext P for Bob at time t with random nonce R_A, she transmits K_A(B, R_A, t, P); BB decrypts, verifies Alice's identity from K_A, and forwards K_BB(A, t, P) to Bob. In a later courtroom dispute Bob produces Exhibit A = K_BB(A, t, P), BB decrypts, and the judge rules. This lesson ships a stdlib-only Python simulator (`code/main.py`) that walks the four-message flow, demonstrates why timestamps plus R_A-replay-checks defeat instant replays, and shows the structural weakness: BB reads every signed message and becomes a single point of trust failure.

**Type:** Learn
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 14 lessons 01-10 (cipher modes, DES/AES, RSA), Chapter 8.4.1
**Time:** ~75 minutes

## Learning Objectives

- Trace the four-message Big Brother signature protocol and explain the role of K_A, K_B, K_BB, R_A, and timestamp t in each step.
- Compute the conditions under which a court accepts Exhibit A as proof that Alice sent P (exhibit decrypts under K_BB to A, t, P with t fresh and R_A unique).
- Identify replay risks and explain why a per-message timestamp plus a per-sender R_A-history check defeats instant replays but still allows out-of-window replays.
- Discuss why BB sees plaintext of every signed message (the "trusted escrow" property) and how this motivates public-key signatures in 8.4.2.
- Implement the protocol end-to-end using AES-256 in counter mode (symmetric primitives), HMAC-SHA256 for K_BB's authenticator, and an in-memory replay-detection cache.

## The Problem

Your bank, MoneyBank, lets corporate clients submit wire-transfer orders over the network. The bank must be able to prove in court that an order named "buy 1 ton of gold" really came from a particular customer, because every quarter the legal team receives subpoenas from customers trying to repudiate trades that lost money. Alice, a customer, sends the bank an order that loses her $400,000 in two days. She claims "I never sent that — my laptop was stolen." The bank's only defense is the order itself. If the order is just "transfer $400k to gold dealer X," a smart lawyer argues Trudy could have intercepted an earlier message from Alice, replayed it, or modified it. The bank needs unforgeable, non-repudiable proof that Alice — not an attacker — is the source of the message.

The deeper issue is that "unforgeable" without a universal trusted party is fundamentally hard. Symmetric-key cryptography by itself cannot tell Alice from Bob, because any key Alice knows is also a key Bob must know to verify the signature. The simplest workable solution is to introduce a trusted authority — Big Brother (BB) — who shares a unique secret key with each user and vouches for messages by attaching its own signature. That is what we build here, with all the trade-offs that come with it.

## The Concept

Source: `chapters/chapter-08-network-security.md`, section 8.4.1 (Symmetric-Key Signatures). The companion diagram is `assets/symmetric-key-digital-signatures-and-big-brother.svg`.

### The three requirements for a digital signature

A digital signature must satisfy three legal-and-cryptographic requirements (Tanenbaum §8.4):

1. **Authentication** — the receiver can verify the claimed identity of the sender.
2. **Nonrepudiation** — the sender cannot later deny the contents of the message.
3. **Integrity** — the receiver cannot possibly have concocted the message himself.

The third is the one people forget: it protects the *customer*, not the bank. If the bank could construct "signed" messages itself, it could fabricate orders in the customer's name. The signature scheme must be such that even the verifier (Bob) cannot produce a valid signature on a new message.

### Why symmetric-key alone is not enough

A symmetric cipher gives you confidentiality and a MAC gives you integrity, but neither gives you nonrepudiation. If Alice and Bob share K_AB, then Alice can sign and Bob can verify — but Bob can also forge any "Alice" signature he wants, because he knows K_AB. A judge cannot tell Alice's signatures from Bob's forgeries. To get nonrepudiation we need a third party who vouches for Alice's signature using a key that **Bob cannot forge**.

### Enter Big Brother (BB)

BB is a trusted authority who holds N secret keys — one per user. K_A is shared only between Alice and BB. K_B is shared only between Bob and BB. K_BB is BB's master signing key that everyone knows is BB's.

The signing-and-forwarding protocol (Tanenbaum Fig. 8-18) is:

| Step | From | To | Message | Why |
|------|------|----|---------|-----|
| 1 | Alice | BB | A, K_A(B, R_A, t, P) | Alice picks random R_A, timestamp t, encrypts the tuple to BB |
| 2 | BB | Bob | K_BB(A, t, P), K_B(A, R_A, t, P) | BB vouches by signing (A, t, P); also sends Alice's full request to Bob under K_B |
| 3 | Bob | — | (carries out order) | Bob has decrypted both layers and is confident Alice sent it |

In Step 2, BB's first payload K_BB(A, t, P) is the *signed exhibit*. In Step 2, BB's second payload K_B(A, R_A, t, P) is the *forwarded request*. The two travel together so Bob gets Alice's plaintext in one round-trip.

### Replay defense

Without extra protection, Trudy could record message 1 or message 2 from earlier and replay it later. The defense uses both pieces of metadata:

- **Timestamp t** — every message carries a wall-clock time. Bob rejects anything where |now − t| > Δ (typical Δ = a few seconds). The window must be small because clocks skew; in Tanenbaum's wording, "Bob will reject very old messages."
- **Nonce R_A** — a per-message random number Alice picks. Bob caches the R_A values he has seen for each sender within the last Δ. A second arrival of the same (A, R_A) pair inside the window is a replay and is dropped.

The combination means an "instant replay" inside the window is caught by the nonce check, and a "delayed replay" outside the window is caught by the timestamp check. The only window is the intersection, which is small.

### What BB sees (the cost)

BB sees the plaintext P of every signed message. That is a structural feature: BB has to decrypt Alice's request before it can re-sign it. If Alice's wire-transfer contains "send $400k to GoldDealer X," BB sees it. Customers must therefore trust BB not just to authenticate but to keep their messages confidential. This is the political reason symmetric-key signatures are not used in practice at scale: nobody trusts a single global escrow.

### Why Exhibit A wins in court

When Alice sues, Bob's lawyer produces K_BB(A, t, P). The judge asks BB to decrypt. BB's plaintext shows (A, t, P) with t being the same timestamp Alice's logs show she created the order, and with R_A — though R_A is not in the exhibit, only in Alice's request to BB — being unique to that submission. The exhibit cannot have been forged by Bob because Bob does not know K_BB; it cannot have been forged by Trudy because Trudy does not know K_BB; and the timestamp rules out replay. The judge rules for the bank.

### Limits of the Big Brother design

Three structural problems motivate public-key signatures:

1. **Single point of trust.** BB's K_BB is the root of all signatures. If K_BB leaks, every signature ever issued can be forged. BB becomes the highest-value target on the network.
2. **Escrow.** BB sees plaintext, so BB is a privacy hazard. Government BBs have historically been subpoenaed; commercial BBs (banks, lawyers) create conflicts of interest.
3. **Scalability.** Every user must physically visit BB's office to register, because K_A is delivered in person ("carried by hand to BB's office" — Tanenbaum §8.4.1). With a million users, BB becomes a logistical nightmare.

These limits are why Chapter 8.4.2 turns to public-key signatures with RSA, where no third party is needed.

## Build It

`code/main.py` implements the four-message Big Brother protocol end-to-end. Work through it in this order:

1. Run `python3 main.py` and read the import block: the protocol uses `hashlib.sha256` for HMAC construction and `os` for CSPRNG. There are no third-party dependencies and no network access.
2. Read `BigBrother.__init__`: it stores per-user keys K_A, K_B, … in a dict, and the master K_BB separately. No file I/O — keys are kept in process memory, which is the right abstraction for the lesson.
3. Read `submit_request`: Alice builds `payload = (B, R_A, t, P)`, computes `K_A(payload)` as an HMAC over the JSON-encoded payload, and returns the wire format `(A, ciphertext, t)`.
4. Read `relay_to_bob`: BB decrypts the request with K_A, constructs the signed exhibit `K_BB(A, t, P)` and the forwarded `K_B(A, R_A, t, P)`, and returns the bundle to Bob.
5. Read `Bob.receive`: Bob decrypts both layers, validates the timestamp window, and checks the R_A cache. Replays inside the window are caught by the nonce check; delayed replays are caught by the timestamp check.
6. Read `try_dispute`: simulates the courtroom. Bob produces the exhibit; BB testifies; the court rules.
7. Run the `main()` scenarios: a happy-path signature, an instant replay (caught), a delayed replay (caught), and a forgery attempt (rejected).

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| Prove message origin | K_BB(A, t, P) decrypts under BB's master key, t is fresh, R_A is unique | Court accepts; forger has no path without K_BB |
| Catch instant replay | Bob's nonce cache shows R_A already seen for A within window | Bob drops the second arrival with a "replay detected" log line |
| Catch delayed replay | |now − t| > Δ at Bob's receipt | Bob drops it with a "stale timestamp" log line |
| Reject forgery | Bob's decryption of K_A(payload) fails HMAC check | Bob drops it with a "MAC invalid" log line |
| Demonstrate escrow | BB logs plaintext of every signed message | Run the demo and observe BB's request log |

## Ship It

Produce one artifact under `outputs/`:

- A one-page runbook titled *"How the bank proves Alice sent it"* that explains the four steps of the protocol, names each key (K_A, K_B, K_BB, R_A, t), and identifies the structural weakness (escrow, single point of trust).
- Or a threat-model document listing who can forge what: Trudy (no), Bob (no, K_BB unknown), BB (yes, by definition), Alice (yes, K_A known), and the consequences for nonrepudiation.

Start from [`outputs/prompt-symmetric-key-digital-signatures-and-big-brother.md`](../outputs/prompt-symmetric-key-digital-signatures-and-big-brother.md) and back every claim with a transcript from `code/main.py`.

## Exercises

1. Trace the four-message flow for "Alice orders MoneyBank to wire $400,000 to GoldDealer X at 2026-06-25T14:32:00Z with nonce R_A = 0x4a3f…." Identify which message contains plaintext, which contains ciphertext, and which contains the exhibit.
2. Alice claims at trial that "Trudy must have replayed my old message." What two pieces of evidence does the bank produce to defeat this claim, and what does each one prove?
3. Suppose BB's database is breached and K_BB leaks. Show concretely how an attacker forges a wire-transfer order that the bank accepts as Alice's. What does the bank's audit log show?
4. Why does the protocol include both a timestamp t and a nonce R_A? What attack does each one prevent that the other does not?
5. Modify `code/main.py` so that BB refuses to escrow messages whose plaintext contains the string "wire transfer" — that is, BB acts as a confidentiality-preserving signer. What part of the original protocol breaks, and how would you fix it with public-key cryptography?
6. Tanenbaum notes that "everyone has to agree to trust Big Brother." Give three concrete operational scenarios where that trust fails, and identify which requirement (authentication, nonrepudiation, integrity) is compromised in each.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Big Brother (BB) | "the trusted authority" | A third party who shares a unique symmetric key with each user and re-signs every signed message under its own master K_BB |
| Nonrepudiation | "can't deny sending it" | Sender cannot later credibly claim they did not send the message; requires a signature whose key only the sender (or a trusted escrow like BB) holds |
| K_A | "Alice's key" | Symmetric key shared between Alice and BB; used by Alice to authenticate to BB, by BB to verify Alice's requests |
| K_BB | "BB's master key" | BB's signing key; output as the legal exhibit K_BB(A, t, P); if it leaks, every signature is forgeable |
| R_A | "the nonce" | Per-message random number Alice picks; Bob uses it to detect instant replays within the timestamp window |
| Timestamp t | "the freshness check" | Wall-clock time of signing; Bob rejects messages with |now − t| > Δ (a few seconds) |
| Exhibit A | "the proof in court" | The signed bundle K_BB(A, t, P) that BB produces; the judge asks BB to decrypt and verify |
| Escrow | "BB sees everything" | Structural consequence of BB decrypting Alice's request before re-signing; BB becomes a privacy hazard |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, Chapter 8 §8.4.1 — Symmetric-Key Signatures (the Big Brother construction in this lesson).
- Needham, R. M., and Schroeder, M. D. (1978). "Using encryption for authentication in large networks of computers." *Communications of the ACM* 21(12): 993-999 — the classic symmetric-key authentication family.
- Denning, D. E., and Sacco, G. M. (1981). "Timestamps in key distribution protocols." *Communications of the ACM* 24(8): 533-536 — why timestamps alone fail.
- Kaufman, C., Perlman, R., and Speciner, M. (2002). *Network Security: PRIVATE Communication in a PUBLIC World*, 2nd ed., Chapter 5 — symmetric-key authentication.
- RFC 4949 — *Internet Security Glossary*, definitions of "nonrepudiation," "trusted third party," "timestamp."
- Diffie, W., and Hellman, M. E. (1976). "New Directions in Cryptography." *IEEE Transactions on Information Theory* IT-22(6): 644-654 — the public-key alternative that makes BB unnecessary (covered in lesson 12 of this phase).