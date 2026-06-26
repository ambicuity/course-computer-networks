# Shared-secret challenge-response and Needham-Schroeder

> Authenticating a remote party without sending your password across the wire requires a fresh challenge that the peer can answer with a value that only they could compute. The shared-secret challenge-response pattern fixes the dictionary-attack and replay problem that a static password exchange has: Alice picks a nonce `R_A`, sends it to Bob, Bob computes `HMAC(K_AB, "challenge:" || R_A)` with the long-term key `K_AB` they share (RFC 2104), and Alice checks the HMAC against her own computation. If they match, Bob must know `K_AB` without revealing it on the wire. The Needham-Schroeder symmetric-key protocol (Needham & Schroeder, 1978) extends this idea to a three-party setting by introducing a trusted Key Distribution Center (KDC): Alice proves her identity to the KDC, receives a fresh session key wrapped in a ticket for Bob, and presents the ticket to Bob — all in five messages, with nonces on both sides to defeat replay. This lesson implements both protocols in pure stdlib Python, walks each message, and shows the classic Denning-Sacco compromise of the original Needham-Schroeder (a stolen old session key replays message 3) that led to the 1987 fixed version.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Phase 14 (symmetric ciphers and HMAC), Phase 15 (digital signatures, public-key concepts)
**Time:** ~75 minutes

## Learning Objectives

- Implement challenge-response with HMAC-SHA256 and explain why a fresh random nonce prevents replay of old responses.
- Trace the five messages of Needham-Schroeder 1978 and identify exactly which secret key protects each envelope (K_A, K_B, K_S, or session key K_AB).
- Reproduce the Denning-Sacco attack: replay an old message 3 whose `K_S` was leaked, and convince Bob that the attacker is Alice.
- Apply the 1987 Needham-Schroeder fix (and contrast it with the Otway-Rees variant) by adding a second nonce `R_B` to the ticket and a `K_S(R_B - 1)` confirmation back to Bob.
- Decide, given a deployment, whether challenge-response, Needham-Schroeder, or Kerberos (RFC 4120) is the right tool, and justify in terms of trust model, clock skew, and ticket lifetime.

## The Problem

The simplest possible authentication is "Alice sends Bob her password." That is also the worst: the password crosses the wire in a form that an attacker who records the exchange can replay forever. TLS client certificates fix the wire problem but require Alice to have a key pair, a CSR, and a CA — too much machinery for a single sign-on. SSH public-key auth gets close, but in 1978 (when the paper was published) public-key was a brand-new idea and almost no infrastructure for distributing keys existed.

What we want is the simplest thing that works: Alice proves knowledge of a secret to Bob without ever transmitting that secret, and a passive eavesdropper who records the entire exchange cannot replay it tomorrow to gain access. That is exactly what challenge-response gives you, and what Needham-Schroeder extends when the two parties do not share a secret yet and must bootstrap one through a trusted third party.

## The Concept

### Challenge-response with a shared key

The canonical protocol is:

```
Alice                                   Bob
  ---- R_A (fresh random 128 b) -------->
                                         compute H = HMAC(K_AB, R_A || "Bob")
  <------------------- H -----------------
verify H == HMAC(K_AB, R_A || "Bob")
```

Properties worth noting:

- **Freshness**: `R_A` is generated from `secrets.token_bytes(16)` per session. The HMAC is bound to *this* `R_A`, so a recording attacker cannot replay it later.
- **Asymmetry**: the HMAC includes `"Bob"` so the same response cannot be replayed back to Alice (mutual challenge would need a separate nonce).
- **No secret on the wire**: the attacker learns `R_A` and the HMAC, but `K_AB` stays on the endpoints. The HMAC reveals nothing without brute-forcing the key.
- **HMAC, not raw hash**: HMAC (RFC 2104) avoids the length-extension attack that `H(K || R)` would have against SHA-256 (the `secret||message` construction, vulnerable since the Merkle-Damgård design does not randomize the internal state).

To get mutual authentication, Bob issues his own nonce `R_B` in a parallel exchange (or interleaved), and Alice returns `HMAC(K_AB, R_A || R_B || "Alice")`. Both parties then know the other shares `K_AB`.

### Why a Key Distribution Center?

Two-party challenge-response requires `K_AB` to exist already. For a network with `n` users, that is `n(n-1)/2` keys to provision — and they have to be re-shared every time one side is compromised. The KDC pattern reduces this to `n` long-term keys (each user shares one with the KDC) at the cost of trusting the KDC. The KDC hands out freshly minted session keys to pairs of users who want to talk.

### Needham-Schroeder 1978: the five messages

```
1. A -> KDC:  A, B, R_A
2. KDC -> A:  K_A(R_A, B, K_S, K_B(A, K_S))
3. A  -> B:   K_B(A, K_S)
4. B  -> A:   K_S(R_A2)              -- note: original used R_A2, NOT R_B - 1
5. A  -> B:   K_S(R_A2 - 1)
```

Step-by-step:

1. Alice tells the KDC who she wants to talk to and includes a nonce `R_A` she generated. The plaintext form is fine because the KDC will protect the session key.
2. The KDC invents a fresh session key `K_S`, wraps it for Alice under their long-term key `K_A`, and includes a **ticket** `K_B(A, K_S)` wrapped under Bob's long-term key `K_B`. The ticket is sealed inside Alice's envelope so Trudy cannot swap it on the way back.
3. Alice forwards the ticket to Bob. Bob can decrypt it (only he has `K_B`) and recover `K_S` and Alice's identity.
4. Bob generates `R_A2`, encrypts it under `K_S`, and sends it to Alice. This proves Bob can use `K_S` and is fresh.
5. Alice returns `K_S(R_A2 - 1)` to confirm receipt and prove she can use `K_S` too. The transformation `R_A2 → R_A2 - 1` (any deterministic function works) prevents a passive replay of step 4 from being mistaken for a fresh response.

The chain `[K_A → K_S → ticket(K_B)]` is the entire trick: Alice proves who she is to the KDC, gets a sealed envelope for Bob, and forwards it. Bob learns `K_S` without ever contacting the KDC directly during the session.

### The Denning-Sacco attack (1981)

Denning and Sacco observed: if an attacker ever recovers an old session key `K_S` (key compromise, weak random number generator, court order, etc.), they can replay message 3 from the original exchange, `K_B(A, K_S)`, and convince Bob that *they* are Alice. Bob has no way to tell the ticket is stale because the original protocol has no timestamp and no second nonce.

The 1987 fix adds `R_B` to Bob's challenge and a corresponding confirmation:

```
4'. B -> A:  K_S(R_A2, R_B)
5'. A -> B:  K_S(R_B - 1)
```

Now Bob's fresh `R_B` is bound into the encrypted conversation, and Alice has to demonstrate she can compute `R_B - 1` under the *current* `K_S`. A replayed message 3 from an old session gives the attacker `K_S_old`, but Bob will issue a *fresh* `R_B` and expect `K_S_old(R_B - 1)`. The attacker cannot compute that without `K_S_old`, and even if they did, `K_S_old ≠ K_S_current`, so the response fails.

### How this maps to Kerberos (RFC 4120)

Kerberos V5 is a descendant of the 1987 fix with three structural additions: a separate Authentication Server (AS) that handles initial login and returns a Ticket-Granting Ticket (TGT), a Ticket-Granting Server (TGS) that mints per-service tickets, and synchronized clocks so tickets carry an expiry time instead of a nonce round-trip. You will see those structures in the next lesson.

## Build It

### Step 1 — Challenge-response with HMAC-SHA256

```python
from main import ChallengeResponse, hmac_sha256, random_nonce

cr = ChallengeResponse(shared_key=b"\xaa" * 32, server_label=b"Bob")
session = cr.start_session()
# Alice sends session.nonce to Bob
response = hmac_sha256(cr.shared_key, session.nonce + cr.server_label)
assert cr.verify(response)  # HMAC matches
```

The HMAC implementation follows RFC 2104 exactly: `H(K' ⊕ opad || H(K' ⊕ ipad || message))` with two SHA-256 passes, key-padded to the 64-byte block. The 32-byte key is enough to keep brute force infeasible; the freshness of the 16-byte nonce keeps the HMAC single-use.

### Step 2 — Needham-Schroeder 1978 round trip

```python
from main import KDC, Principal, run_needham_schroeder

kdc = KDC()
alice = Principal("alice", kdc.register("alice"))
bob = Principal("bob", kdc.register("bob"))

session_key = run_needham_schroeder(alice, bob, kdc)
assert session_key is not None
```

The simulator moves each message across an "insecure channel" dictionary; an attacker function can intercept, drop, replay, or modify any message. To replay the original 1978 exchange under our `ReplayWindow` constraint, set `allow_old_session_keys=True` and watch message 5 succeed against a stolen old `K_S`.

### Step 3 — Reproduce the Denning-Sacco attack

```python
from main import denning_sacco_attack

old_session_key = bytes.fromhex("...")
attacker_forges = denning_sacco_attack(alice, bob, kdc, old_session_key)
```

The function returns `True` if the attacker convinces Bob under the 1978 protocol and `False` if the 1987 fix is in effect. This is the test that should always pass for the 1978 version (it is a real vulnerability) and always fail for the 1987 version.

### Step 4 — Switch to the 1987 fix and confirm

```python
from main import run_needham_schroeder_fixed

session_key = run_needham_schroeder_fixed(alice, bob, kdc)
```

The only difference in the message flow is that Bob's challenge now carries a fresh `R_B` and Alice returns `K_S(R_B - 1)`. Run the same Denning-Sacco replay against this version and watch it fail.

## Use It

| Real system | Authentication pattern | How it maps |
|---|---|---|
| SSH password auth | Static password over TLS-protected channel | Differs: relies on TLS for replay protection rather than challenge-response |
| SSH public-key auth | Signed challenge with Ed25519/RSA key | Challenge-response, but asymmetric; nonce is the SSH session ID |
| Kerberos V5 (RFC 4120) | TGT + service ticket + AP-REQ | Needham-Schroeder 1987 descendant with timestamps and a TGS |
| TLS 1.3 client certificates | Signed CertificateVerify over handshake transcript | Public-key challenge-response; the handshake transcript is the nonce |
| OAuth 2.0 PKCE | Code + verifier hash bound to client | Challenge-response with the verifier as the shared secret |
| HTTP Digest auth (RFC 7616) | `HA1 = MD5(username:realm:password)`, nonce-bound response | Challenge-response; the server nonce is the challenge |
| RADIUS (RFC 2865) | Access-Request with `User-Password` hashed under shared secret | Challenge-response with the shared secret as key |

Notice that the challenge-response pattern shows up in nearly every authentication system ever deployed, just with different keys (shared secret, public key, password-derived hash). The freshness primitive is always the same: a server-generated or session-unique nonce, a deterministic function bound to the secret, and a single-use response.

## Ship It

The reusable artifact in `outputs/prompt-needham-schroeder.md` is a small Python package `auth_proto_lab` that exposes three pure functions: `challenge_response(...)`, `needham_schroeder_1978(...)`, and `needham_schroeder_1987(...)`. Each returns a typed result object with `success: bool`, `session_key: bytes`, and `messages: list[Message]` so a test harness can replay messages and assert on the Denning-Sacco outcome. Include a `cli.py` that accepts `--protocol {cr,ns78,ns87}`, prints the messages exchanged, and runs the canonical attack in --attack mode.

## Exercises

1. Use `secrets.token_bytes(8)` instead of 16 for the challenge. Why is 8 bytes (64 bits) too small for production? (Hint: birthday-bound collision probability after `2^32` sessions.)
2. Replace HMAC with `hashlib.sha256(K + R).digest()` and run the same challenge-response. Why is the raw `H(K||R)` construction broken against length-extension? (Merkle-Damgård does not randomize the internal state.)
3. Hand-trace the Denning-Sacco attack: write out the exact bytes the attacker must replay and what Bob decrypts from each field. Why does Bob accept the ticket as fresh?
4. Implement Otway-Rees (1987): Alice sends `A, B, R, K_A(R, A, B)`; Bob forwards with `K_B(R, A, B)`; KDC returns two sealed envelopes. How does Otway-Rees avoid the Denning-Sacco issue without needing two nonces?
5. Add clock skew to the simulator: the TGS believes a ticket issued 6 hours ago is still valid. Where does Kerberos inherit the same vulnerability, and why does Microsoft recommend `<5 minute` clock skew in real deployments?
6. Replay message 4 (Bob's encrypted nonce) from a captured session. Why does the original 1978 protocol still leak information here, even though the response in step 5 is also replayed? What does the 1987 fix change?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Challenge-response | "prove you know the password" | Server sends nonce; client returns a keyed function of nonce; replay requires nonce reuse |
| HMAC | "a keyed hash" | RFC 2104: H((K ⊕ opad) || H((K ⊕ ipad) || M)), two passes, key-padded to block size |
| KDC | "the auth server" | Trusted third party that hands out session keys to authenticated users |
| Session key | "the shared key" | A short-lived symmetric key `K_S` minted per session; never crosses the wire in plaintext |
| Ticket | "the envelope" | `K_B(A, K_S)`; the KDC's sealed delivery of a session key to Bob |
| Nonce | "random number" | Number used once; `R_A` for freshness on Alice's side, `R_B` for Bob's |
| Replay attack | "send it again" | Trudy captures a valid exchange and resubmits the same bytes later |
| Denning-Sacco | "the 1978 flaw" | Stolen old `K_S` lets attacker replay message 3 and impersonate Alice |
| Mutual authentication | "both prove themselves" | Both sides demonstrate knowledge of the shared secret with fresh challenges |

## Further Reading

- Needham, R. M., & Schroeder, M. D. (1978). *Using encryption for authentication in large networks of computers.* Communications of the ACM.
- Denning, D. E., & Sacco, G. M. (1981). *Timestamps in key distribution protocols.* Communications of the ACM.
- Otway, D., & Rees, O. (1987). *Efficient and timely mutual authentication.* ACM SIGOPS Operating Systems Review.
- RFC 2104 — HMAC: Keyed-Hashing for Message Authentication
- RFC 2865 — RADIUS (challenge-response in dial-up auth)
- RFC 4120 — The Kerberos Network Authentication Service (V5)
- RFC 7616 — HTTP Digest Authentication (challenge-response over HTTP)
- Kaufman, Perlman, & Speciner — *Network Security: PRIVATE Communication in a PUBLIC World*, Ch. 11 (Authentication Protocols)
