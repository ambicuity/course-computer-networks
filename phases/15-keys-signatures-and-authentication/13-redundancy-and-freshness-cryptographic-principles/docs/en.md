# Redundancy and Freshness: Two Cryptographic Principles

> The chapter states two cryptographic principles that govern every secure message ever designed: (1) messages must contain *redundancy* so the receiver can tell a valid message from random garbage, and (2) every message must be *fresh* so an attacker cannot replay an old valid message. Both principles exist because encryption alone does not stop an active intruder — it only stops a passive eavesdropper. This lesson implements them in pure Python. You will see why TCP's "16-byte customer name + 3-byte order" scheme falls apart when a fired employee generates random ciphertexts that decrypt to legal orders, and how adding redundancy (a fixed 9-zero prefix, a CRC, or a cryptographic hash) eliminates the attack. You will also see why timestamps inside a 10-second window and per-message nonces stop replay attacks. The lesson ships an `order_frame` builder/validator and a `replay_filter` that tracks recent nonces; together they show what every real protocol (TLS, IPsec, Kerberos, OAuth JWT) embeds in its handshake.

**Type:** Build
**Languages:** Python
**Prerequisites:** Lessons 11–12, familiarity with hex encoding
**Time:** ~60 minutes

## Learning Objectives

- Articulate the two cryptographic principles (redundancy, freshness) and explain why each is independent of encryption strength.
- Construct an `order_frame` with redundant prefix, payload, and integrity hash, then verify it on the receive side.
- Show quantitatively how a fixed 9-byte zero prefix reduces the random-forgery success rate from ~100% to 2^-72.
- Implement a sliding-window replay filter that drops any message whose timestamp is older than `ΔT` or whose nonce has been seen.
- Recognize where these patterns appear in real protocols: TLS record sequence numbers, IPsec AH/ESP anti-replay, Kerberos authenticators, OAuth JWT `exp` claims.
- Add a simple HMAC-SHA256 integrity check to the frame and explain why HMAC is preferred over plain hash.

## The Problem

The Couch Potato mail-order company designs its order wire as: `16-byte customer name || 3-byte encrypted order`. A fired employee with the customer list but not the keys sends 500 messages with random 3-byte encrypted tails. Almost every one decrypts to a valid order (some quantity × some product). The warehouse ships out 837 swings and 540 sandboxes to nobody. The encryption is unbreakable; the system is still worthless.

The chapter calls this the *active-intruder problem* and prescribes redundancy: extend the encrypted portion to 12 bytes, the first 9 of which must be zero. Now random guesses hit a 9-byte prefix check with probability 2^-72. But redundancy alone creates a new problem: an attacker who records yesterday's valid message can replay it today. Freshness — a timestamp valid for 10 seconds, plus a per-message nonce the receiver tracks — closes that hole.

The lesson builds both halves so the student can watch the attack succeed, then fail, after each mitigation.

## The Concept

### Cryptographic principle 1: redundancy

> "All messages must contain some redundancy, that is, information not needed to understand the message." (Chapter 8, section 8.1.5.)

Why? Without redundancy, every bit string the receiver decrypts is a candidate valid message. An active intruder who cannot decrypt can still *generate* ciphertexts (e.g., random bytes, or pre-recorded valid ones). Redundancy gives the receiver a cheap test: "does this decrypted message look like something a legitimate sender would produce?" If yes, accept; if no, drop.

But redundancy has a cost: it makes the cryptanalyst's job easier. If a guessed key consistently produces plaintext with the expected redundancy, the analyst knows they have the right key. The chapter calls this a tension and recommends:

- **CRC** — fast, exposes obvious tampering.
- **Cryptographic hash (SHA-256)** — better, but slower.
- **Avoid leading or trailing zeros** — predictable patterns bias certain ciphers (notably stream ciphers with reused nonces).

The Couch Potato fix: extend the order to 12 bytes, first 9 must be zeros. The redundancy is 72 bits. A random forgery hits the prefix with probability 2^-72 ≈ 1 in 4.7×10^21 — effectively zero. But the principle is independent of the cipher: it is purely a protocol-level constraint.

### Cryptographic principle 2: freshness

> "Some method is needed to foil replay attacks." (Chapter 8, section 8.1.5.)

Redundancy tells the receiver "this is a valid format", but not "I have not seen this before". An attacker who records a valid message can replay it indefinitely. Freshness mechanisms:

- **Timestamps.** Sender embeds the current time inside the encrypted payload. Receiver keeps messages for `ΔT` (e.g. 10 seconds) and discards anything older. Limitation: requires synchronized clocks.
- **Sequence numbers / nonces.** Receiver tracks a per-sender counter. Each new message must have a counter strictly greater than the last accepted. Sender stores the last counter it used per receiver; resends request it.
- **Challenge-response.** Receiver sends a random nonce; sender must include it (inside the encryption) in the next message. This is the strongest mechanism because it does not require clock sync or persistent counters — but it costs an extra round trip.

The chapter's examples: BB84 uses the *sifting* step (Alice tells Bob which bases were right, in plaintext, after the quantum exchange) and the QBER check to confirm freshness of the key exchange. The Kerberos authenticator (later in the chapter) embeds a timestamp + nonce inside an encrypted blob.

### Replay attacks in the wild

Real protocols combine mechanisms:

| Protocol | Freshness mechanism |
|----------|---------------------|
| TLS 1.3 | 64-bit record sequence number, explicit `nonce` in AEAD |
| IPsec AH/ESP | 32-bit sequence number per Security Association, anti-replay window |
| Kerberos v5 | Authenticator timestamp + 5-minute clock skew window |
| OAuth JWT | `exp` (expiration) + `iat` (issued-at) + `jti` (JWT ID, single use) |
| 802.11i (WPA2) | 48-bit packet number (PN), replay-protected by AP |

Every one of these is the chapter's principle 2 in a different costume.

### Redundancy vs. integrity vs. authentication

It is worth distinguishing three concepts the chapter layers on top of each other:

- **Redundancy** — fixed structure in the plaintext (e.g. zero prefix, fixed field lengths) that catches random junk.
- **Integrity** — a checksum, CRC, or hash inside the message that detects any modification.
- **Authentication** — a MAC keyed with a shared secret (or a digital signature) that detects modification *and* proves the sender.

A CRC over a message is redundancy. An HMAC over a message is integrity + authentication. The chapter keeps them as separate principles because they address different threats: a passive eavesdropper cannot forge a CRC-protected message but can replay one; an active intruder can forge a CRC but not an HMAC.

### How much redundancy is enough?

Rule of thumb from RFC 4949 and the chapter: enough that a random forgery has success probability < 2^-32, but not so much that the cryptanalyst gets a free oracle. Common patterns:

- **Sequence numbers** — 48 bits (catches replays for centuries at GHz rates).
- **Timestamps** — 32 bits of Unix time, second resolution (catches replays for ~136 years).
- **MAC tag** — 64 to 128 bits (collision-resistant against birthday attacks up to 2^32 or 2^64 messages).
- **CRC** — 16 or 32 bits (catches accidental corruption, not adversarial tampering).

The Couch Potato's 72 bits of zero prefix is on the high end, but it is also doing double duty: a valid order always has the form `000000000XXX`, so the legitimate order format is fixed and any deviation is detectable.

## Build It

The builder lives in `code/main.py` (≈200 lines). It exposes:

- `OrderFrame` dataclass with `customer_id`, `quantity`, `product_id`, `nonce`, `timestamp`, `hmac`.
- `make_frame(customer_id, quantity, product_id, key, redundancy=9)` — pack fields, prepend zero prefix, HMAC-SHA256.
- `verify_frame(frame, key, max_age_seconds=10, seen_nonces=None)` — verify redundancy, freshness, nonce uniqueness, HMAC.
- `random_forge(rate=1000, key=b"unknown")` — simulate the fired employee's attack on a no-redundancy scheme.
- `ReplayFilter(max_age_seconds=10)` — tracks nonces and timestamps to drop replays.
- `demo_attack_and_defense()` — runs the full Couch Potato scenario.

Run the lesson end-to-end:

```python
from main import demo_attack_and_defense
demo_attack_and_defense()
```

You should see four phases:

1. **No redundancy** — 1000 random ciphertexts, ~all decrypt successfully.
2. **9-byte zero prefix** — same 1000 ciphertexts, ~0 succeed.
3. **Add a timestamp + nonce** — replaying yesterday's valid message fails.
4. **Add HMAC** — random modifications to a valid message fail with probability 1 - 2^-256.

Inspect a frame manually:

```python
from main import make_frame, verify_frame
key = b"shared-secret-32-bytes-long-enough"
frame = make_frame(b"alice", 1, 0x1234, key)
print(frame.hex())
assert verify_frame(frame, key)
```

Replay test:

```python
from main import make_frame, verify_frame, ReplayFilter
key = b"shared-secret-32-bytes-long-enough"
frame = make_frame(b"alice", 1, 0x1234, key)
seen = ReplayFilter(max_age_seconds=10)
assert verify_frame(frame, key, seen_nonces=seen)
assert not verify_frame(frame, key, seen_nonces=seen)   # second time fails
```

## Use It

| Function | Real-world counterpart | Notes |
|----------|------------------------|-------|
| `make_frame` | TLS record, IPsec ESP packet | Same fields: payload + nonce + timestamp + MAC. |
| `verify_frame` | TLS 1.3 record decryption | Discards out-of-order, replays, tampered records. |
| `random_forge` | Fuzz test against any unauthenticated protocol | Real implementations get hammered by `boofuzz` / `AFL`. |
| `ReplayFilter` | IPsec anti-replay window, Kerberos `auth_time` cache | RFC 4303 §3.4.3 specifies a 32-packet window by default. |
| 9-byte zero prefix redundancy | Kerberos principal name padding, JWT fixed header | The principle is universal. |

This lesson's frame is deliberately minimal so the principles are visible. Production frame formats (TLS record, IPsec ESP, SSH binary packet) add version, length, padding, and key-id fields on top.

## Ship It

A reusable artifact for protocol-design walkthroughs lives at `outputs/prompt-redundancy-and-freshness.md`. It includes the Couch Potato scenario, three principles summarized, and a checklist for adding both to a new wire protocol. Reuse it when reviewing a new authentication handshake.

## Exercises

1. Modify `make_frame` to use a 16-byte zero prefix instead of 9. Recompute the random-forgery success rate.
2. Implement an HMAC-SHA256 truncated to 64 bits and verify it still catches modifications. Measure how often random 64-bit MACs collide (birthday bound: 2^32 trials).
3. Add `max_clock_skew` to `verify_frame` so a sender with a fast clock cannot generate messages the receiver has not yet reached.
4. Implement challenge-response: receiver issues a 128-bit nonce, sender's next message must include it inside the encrypted payload. Show that this stops replay even without a clock.
5. Show that a message protected only by CRC-32 is forgeable in seconds: given any valid message, find a second message with the same CRC by random search.
6. Compare the bytes-on-wire cost of: zero-prefix redundancy, CRC-32, HMAC-SHA256, and AES-GCM tag. Quantify the trade-off.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Redundancy | "Extra bytes in the message" | A fixed, predictable structure that lets the receiver reject random junk. |
| Freshness | "The message is new" | Timestamp, sequence number, or nonce that stops replay attacks. |
| Replay attack | "Send yesterday's message again" | Reusing a captured valid message in a new context. |
| Nonce | "Number used once" | A random or counter value guaranteed unique per message. |
| Sequence number | "Monotonic counter" | A per-sender counter that increments with each message. |
| Timestamp window | "ΔT" | Time interval during which the receiver accepts messages (e.g. 10 s). |
| HMAC | "Hashed MAC" | A keyed hash providing integrity and authentication. |
| CRC | "Cyclic redundancy check" | A non-keyed checksum; detects accidental corruption, not tampering. |
| Active intruder | "Modifies or injects messages" | Trudy who can alter traffic, not just listen. |
| Passive intruder | "Just listens" | Eve who records but does not modify. |

## Further Reading

- Tanenbaum, *Computer Networks*, Chapter 8 (this chapter).
- Needham, R., and Schroeder, M., *Using encryption for authentication in large networks of computers*, CACM 21(12), 1978 — origin of the nonce-and-timestamp handshake.
- RFC 4949 — *Internet Security Glossary*, canonical definitions.
- RFC 4303 — *IP Encapsulating Security Payload (ESP)*, §3.4.3 anti-replay window.
- RFC 5246 — *The TLS Protocol*, §6.1 record-layer sequence numbers.
- RFC 4120 — *Kerberos Network Authentication Service*, §5.5.1 timestamp skew window.