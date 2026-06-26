# Two Fundamental Cryptographic Principles

> Two principles underlie every cryptographic protocol. Principle 1 — Redundancy: every encrypted message must contain information not needed to understand the message, so the receiver can tell valid plaintext from attacker garbage after decryption. Without redundancy, an active intruder who knows customer names but not keys can inject random ciphertext; since almost every 3-byte message is a valid order, the system ships 837 swings to a real customer. Adding 9 leading zero bytes (12-byte messages where 9 must be zeros) stops the attack — random junk almost never passes the check. But redundancy helps cryptanalysts: a valid/invalid oracle distinguishes correct key guesses from wrong ones, so the redundancy must not be a predictable run of zeros. A CRC polynomial is better; a cryptographic hash is best. Principle 2 — Freshness: every received message must be verifiable as recent, to foil replay attacks. A fired employee taps the line and replays old valid orders. Timestamps valid for 10 seconds, nonces, and sequence numbers all serve. Violating either principle breaks real systems: without redundancy, active intruders cause chaos without reading ciphertext; without freshness, replay attacks bypass encryption entirely.

**Type:** Build
**Languages:** Python, crypto diagrams
**Prerequisites:** Lessons 01-03 of Phase 14
**Time:** ~70 minutes

## Learning Objectives

- State Principle 1 (redundancy) and explain why encrypted messages need information beyond the payload.
- Demonstrate the active-intruder attack on a no-redundancy order system and show how a 9-zero-byte prefix defeats it.
- Explain why redundancy helps cryptanalysts and why the redundancy should be a CRC or cryptographic hash, not a run of zeros.
- State Principle 2 (freshness) and implement timestamp and nonce checks that reject stale or replayed messages.
- Identify redundancy and freshness mechanisms in real protocols (TLS record MAC, Kerberos timestamps, IPsec sequence numbers).

## The Problem

The Couch Potato (TCP), a mail-order company with 60,000 products, encrypts the last 3 bytes of each order (1 byte quantity, 2 bytes product number) with a per-customer key. A fired employee steals the customer list and sends hundreds of fake orders with random 3-byte ciphertext. Because almost every 3-byte message is a valid order, TCP's computer prints shipping instructions for 837 sets of children's swings to real customers. The encryption is unbroken — the attacker never reads plaintext — but the active intruder causes massive damage by exploiting the absence of redundancy. Separately, the same employee can tap the line and replay old valid encrypted orders. Two principles must be applied.

## The Concept

### Principle 1: Messages must contain redundancy

Upon decrypting a message, the receiver must be able to tell whether it is valid by inspecting the message and perhaps performing a simple computation. Without redundancy, an active intruder can send garbage and trick the receiver into acting on the "plaintext."

| Message format | Redundancy | Active-intruder attack |
|----------------|-----------|----------------------|
| 16-byte name + 3-byte encrypted order | None | Random 3-byte ciphertext -> almost all valid -> ships garbage |
| 16-byte name + 9 zero bytes + 3-byte order | 9 zero bytes | Random ciphertext -> 1 in 2^72 passes -> attack fails |
| 16-byte name + 4-byte CRC + 3-byte order | CRC | Receiver verifies CRC; random junk fails CRC check |
| 16-byte name + 32-byte HMAC + 3-byte order | Cryptographic hash | Random junk fails HMAC; best redundancy |

The 9-zero-byte fix works because the probability of random ciphertext decrypting to 9 zero bytes is 2^-72 — negligible. But a run of zeros is the worst form of redundancy because it makes the cryptanalyst's job easier: encrypting known zero blocks through some algorithms gives predictable results. A CRC polynomial is better because it is harder to predict. A cryptographic hash (or HMAC) is best because it is designed to resist chosen-plaintext analysis.

### The tension between redundancy and cryptanalysis

Redundancy protects against active intruders but helps passive ones. In the original 3-byte scheme, cryptanalysis was nearly impossible: after guessing a key, the analyst had no way to tell if the guess was right because almost every message was technically legal. With the 12-byte scheme (9 zeros + 3 payload), the analyst has a validity oracle: a correct key produces 9 zero bytes; a wrong key produces random-looking output. This tension is fundamental. The resolution: use redundancy that is verifiable but not predictable — a CRC or, better, a keyed MAC that the cryptanalyst cannot compute without the key.

### Principle 2: Messages must be fresh

Measures must ensure that each message received can be verified as being sent recently, to prevent active intruders from replaying old messages.

| Freshness mechanism | How it works | Example protocol |
|---------------------|-------------|-----------------|
| Timestamp | Receiver accepts messages within a window (e.g., 10 seconds); rejects older | Kerberos tickets |
| Nonce | Sender includes a random number; receiver rejects duplicates | TLS handshake |
| Sequence number | Each message has a monotonically increasing counter; receiver rejects lower or duplicate | IPsec AH/ESP |

The fired employee who taps the line and replays old valid orders is defeated by any of these. The receiver keeps recent messages for the window duration and compares new arrivals; duplicates are discarded. Messages older than the window are rejected as stale.

### Redundancy in quantum key distribution

Even quantum cryptography needs redundancy. Trudy's interception of photons introduces errors in Bob's one-time pad. Bob needs redundancy in incoming messages to detect errors. A crude form: repeat the message twice and compare. A Hamming or Reed-Solomon code is more efficient. The point: redundancy distinguishes valid from invalid messages even against an active adversary who can introduce noise.

### Real-protocol examples

| Protocol | Redundancy mechanism | Freshness mechanism |
|----------|---------------------|---------------------|
| TLS 1.3 record | AEAD tag (16 bytes) | Sequence number in nonce |
| Kerberos | Ticket encrypted with KDC key | Timestamp in ticket (5-min skew) |
| IPsec ESP | ICV (integrity check value) | Sequence number + anti-replay window |
| SSH | HMAC over payload + sequence | Sequence number per packet |

Every real secure protocol implements both principles. The `code/main.py` demo simulates the Couch Potato attack with and without redundancy, and a replay attack with and without a timestamp freshness check.

### Why these principles are non-negotiable

Violating Principle 1 means an active intruder who cannot read ciphertext can still cause the system to act on attacker-controlled plaintext. Violating Principle 2 means an intruder who captures one valid message can replay it indefinitely. Encryption without these two principles is like a locked door with no frame — the lock holds, but the wall does not.

## Build It

1. Run `python3 code/main.py`. It simulates the Couch Potato attack: without redundancy, random 3-byte orders are almost all valid; with 9 leading zero bytes, the attack rate drops to ~0%. Then it simulates a replay attack with and without a 10-second timestamp window.
2. Observe the attack-success-rate difference between the two message formats.
3. Modify the timestamp window to 1 second and replay a message 11 seconds old; verify rejection.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|---------------------|
| Apply Principle 1 | No-redundancy orders succeed at ~100%; with 9-zero prefix, ~0% | Attack rate drops from ~100% to 2^-72 |
| Apply Principle 2 | Replay of stale message rejected by timestamp check | Messages older than window are dropped |
| Choose good redundancy | CRC or HMAC, not a run of zeros | Cryptanalyst gains no predictable-plaintext oracle |
| Identify in real protocols | Name the redundancy and freshness in TLS, Kerberos, IPsec | Each protocol has both; neither is optional |

## Ship It

This lesson produces `outputs/redundancy-and-freshness-checklist.md`: a protocol review checklist that verifies a secure protocol implements Principle 1 (verifiable redundancy, not predictable zeros) and Principle 2 (timestamp/nonce/sequence freshness with replay window).

## Exercises

1. The Couch Potato system uses 3-byte encrypted orders with no redundancy. Calculate the probability that a random 3-byte ciphertext decrypts to a valid order. How does this change with 9 leading zero bytes?
2. Why is a run of zero bytes the worst form of redundancy? What attack does it enable that a CRC avoids?
3. A protocol uses timestamps valid for 10 seconds. The attacker captures a valid message at t=0 and replays it at t=15. What happens? What if the receiver's clock is 8 seconds ahead?
4. IPsec uses a 64-element anti-replay window with sequence numbers. Describe how a replayed packet with sequence number 5 is handled when the window starts at 100.
5. TLS 1.3 uses AEAD with a 16-byte tag and a sequence number in the nonce. Which principle does each satisfy? What happens if the sequence number wraps at 2^64?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| Redundancy (Principle 1) | "extra bytes" | Verifiable info that lets the receiver distinguish valid from garbage after decryption |
| Freshness (Principle 2) | "not old" | Verifiable recency that prevents replay of captured valid messages |
| Active intruder | "the dangerous one" | Can inject, replay, or modify messages without necessarily reading them |
| Replay attack | "play it again" | Re-sending a captured valid message to trick the receiver |
| Validity oracle | "is it valid?" | A way for the cryptanalyst to test key guesses; redundancy creates one |
| Nonce | "number once" | A random value used once to ensure freshness |
| Anti-replay window | "sliding window" | Receiver tracks recent sequence numbers and rejects duplicates |
| MAC / HMAC | "tag" | Keyed redundancy that resists cryptanalytic prediction |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), Section 8.1.5
- RFC 4303 — IPsec ESP anti-replay window mechanism
- RFC 5246 / 8446 — TLS record layer MAC and sequence numbers
- Kaufman, Perlman, Speciner, *Network Security* — redundancy and freshness in protocol design