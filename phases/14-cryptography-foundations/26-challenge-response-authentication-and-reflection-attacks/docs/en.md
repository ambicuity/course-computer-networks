# Challenge-response authentication and reflection attacks

> A challenge-response protocol proves a peer holds a shared secret K_AB without ever sending K_AB on the wire. The verifier issues a fresh nonce R (challenge), the prover returns f(K_AB, R) for some keyed function f, and the verifier checks the response against its own computation of f(K_AB, R). If the two match, the prover knows K_AB. The design choice is which f to use: a cipher like AES-128 in ECB mode is the textbook answer because it is one-way to anyone without the key. The vulnerability that breaks naive constructions is the reflection attack: Trudy opens a second connection to the verifier, replays the verifier's own challenge R back as if she had solved it, and the verifier — symmetrically holding K_AB — validates her own response. Defenses include binding each challenge to a specific sender id, using different keys for each direction, and choosing R from a domain the prover will not be tricked into forwarding. This lesson ships a stdlib-only Python simulator (code/main.py) that demonstrates a working HMAC-SHA256 challenge-response, simulates a reflection attack, and shows how a per-direction key separation (K_AB_in, K_AB_out) defeats it.

**Type:** Learn
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 14 lessons 01-09 (symmetric ciphers, AES), Chapter 8.3.1
**Time:** ~70 minutes

## Learning Objectives

- Trace a two-message challenge-response protocol and explain why it proves knowledge of K_AB without transmitting it.
- Implement a verifier that issues a 16-byte nonce R and accepts responses only when HMAC-SHA256(K_AB, R) matches the expected value.
- Construct a reflection attack where Trudy re-uses the verifier's own R as her response, and identify why the naive verifier is fooled.
- Apply three defenses (per-direction keys, sender-id binding, distinct challenge domains) and verify that each blocks the reflection.
- Distinguish challenge-response from one-way authentication protocols and explain why CR needs no prior context other than K_AB.

## The Problem

Two hosts, Alice and Bob, share a symmetric key K_AB. Alice wants to log into Bob's server over an insecure network. A password-based scheme has problems: passwords travel (encrypted or not), they are replayable, and they are brute-forceable. What Alice really wants is a protocol that lets Bob confirm "you are Alice" using K_AB without ever sending K_AB and without sending a value an eavesdropper can replay. The textbook answer is challenge-response: Bob picks a fresh nonce R, sends it to Alice, Alice returns E(K_AB, R), and Bob verifies. The protocol is one round-trip and provably secure under standard assumptions on the underlying cipher. The complication is that the textbook protocol has a subtle hole: because Alice and Bob hold the same key, an attacker can open a second connection and use Bob as an oracle to compute responses for Bob's own challenges. This is the reflection attack, and the lesson's deliverable is a working simulator that shows the hole, fixes it, and verifies the fix.

## The Concept

Source: chapters/chapter-08-network-security.md, section 8.3.1 (Authentication Protocols). The companion diagram is assets/challenge-response-authentication-and-reflection-attacks.svg.

### The shape of a challenge-response protocol

A challenge-response (CR) protocol has exactly two messages in its simplest form:

| Step | From | To | Wire | Meaning |
|------|------|----|------|---------|
| 1 | Verifier (Bob) | Prover (Alice) | R | Prove you hold K_AB by computing f(K_AB, R) |
| 2 | Alice | Bob | f(K_AB, R) | Here is the keyed function output; verify it |

The verifier generates R fresh for every authentication attempt. R must be unpredictable (a CSPRNG) and unique (never reused inside the key's lifetime), otherwise Trudy can pre-compute f(K_AB, R_old) for some old R_old and replay it. The standard sizes are 8 bytes for low-value authentication and 16 or 32 bytes for higher-value sessions. NIST SP 800-63B and SP 800-90A both require at least 64 bits of entropy for nonces used in authentication.

### Choosing the keyed function f

Three practical choices for f exist:

1. Block cipher in ECB mode: f(K, R) = AES_K(R). One block in, one block out. Requires |R| = block size (16 bytes for AES).
2. Block cipher in CTR/OFB mode: f(K, R) = AES-CTR_K(R, 0...01). Stream-cipher-like, accepts arbitrary R length.
3. HMAC: f(K, R) = HMAC-SHA256(K, R). Standard for modern protocols, supports arbitrary R.

The textbook version uses a block cipher because it is the simplest. The practical version uses HMAC because it composes cleanly with hash functions and avoids cipher-mode pitfalls. This lesson uses HMAC-SHA256 because it accepts an arbitrary-length nonce and is the modern default.

### The reflection attack in detail

The naive CR protocol above is symmetric: Alice proves knowledge of K_AB by computing f(K_AB, R), and Bob verifies by computing f(K_AB, R) himself. But because the same key is used for verification, Bob is also a prover for the same key. Trudy exploits this by opening a second connection:

| Connection 1 (Trudy -> Bob, I am Alice) | Connection 2 (Trudy -> Bob, I am Bob) |
|----|----|
| Bob -> Trudy: R1 (16 bytes) | Trudy -> Bob: R2 = R1 (Trudy forwards Bob's R1 as her challenge to Bob) |
| Trudy -> Bob: ??? (Trudy does not know K_AB) | Bob -> Trudy: f(K_AB, R2) = f(K_AB, R1) (Bob helps!) |
| | Trudy -> Bob (Conn 1): f(K_AB, R1) (Trudy forwards Bob's answer back to Connection 1) |

After Connection 2 completes, Trudy has the value f(K_AB, R1) and sends it on Connection 1. Bob accepts. Trudy has authenticated as Alice without knowing K_AB.

The flaw is that the challenge R1 is not bound to the connection: Trudy can feed R1 back to Bob from a different context and get the same answer.

### Defense 1: per-direction keys

Split K_AB into K_AB_in (Alice -> Bob direction) and K_AB_out (Bob -> Alice direction). The verifier expects f(K_AB_in, R) when Alice authenticates; Bob uses K_AB_out to issue challenges to Alice. Trudy's Connection 2 demands f(K_AB_out, R1), not f(K_AB_in, R1); even if Trudy can compute one, it is the wrong direction. This is the standard defense and is what SSH and IPsec AH actually do.

### Defense 2: bind R to the sender id

Make the challenge R = (sender_id, nonce) instead of just nonce. The verifier expects f(K_AB, "Alice" || nonce). Trudy's Connection 2 demands f(K_AB, "Bob" || R1) because the server-side verifier must specify its own id, and the values differ.

### Defense 3: distinct challenge domains

Use a different key for issuing vs. verifying. Or use a different cipher mode. Or require the prover to transform R in a way that only a prover does (e.g., R' = R XOR 1, then f(K_AB, R')). Trudy's reflection supplies R, but she cannot produce the transformed R'.

### Where CR is used in real protocols

- SSH user authentication uses CR with the server's host key and the user's public key. RFC 4252 specifies the format.
- TLS 1.2 uses CR implicitly: the client signs a hash of the handshake that the server challenges with Finished.
- IPsec IKEv2 uses CR for peer authentication with both PSK and certificate modes (RFC 7296 Section 3).
- CHAP (RFC 1994) uses a three-way CR variant for PPP authentication.

## Build It

code/main.py implements challenge-response with reflection attack and defense. Work through it in this order:

1. Run python3 main.py and read the import block. The protocol uses os.urandom and secrets for nonce generation and hashlib for HMAC construction. There are no third-party dependencies and no network access.
2. Read NaiveVerifier.__init__: it stores K_AB for both directions in a single key (the insecure configuration). The verifier issues a nonce; the prover responds.
3. Read verifier_issue and prover_respond: both compute HMAC-SHA256(K_AB, R); the prover returns it; the verifier compares. Note that the verifier can compute the prover's answer because both ends hold K_AB.
4. Read scenario_reflection_attack_naive: opens two connections, uses Connection 2 to make Bob compute f(K_AB, R1) for Trudy, then forwards that into Connection 1.
5. Read scenario_reflection_blocked: implements the per-direction key split. Trudy's reflection now fails because Connection 2 returns f(K_AB_out, R1) and Connection 1 expects f(K_AB_in, R1).
6. Run the main() scenarios: a happy-path authentication, a reflection attack against the naive protocol (succeeds), and a reflection attack against the per-direction-key protocol (fails).

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| Generate a fresh nonce | secrets.token_bytes(16) returns 16 bytes from the OS CSPRNG | R is 128 bits, unique across attempts, unpredictable to Trudy |
| Verify a response | Constant-time compare of f(K_AB, R) | Bob accepts iff response equals his own computation |
| Detect a reflection | Trudy's Connection 2 returns f(K_AB_out, R1) but Connection 1 expects f(K_AB_in, R1) | Verifier logs direction mismatch, rejected |
| Block a reflection | Per-direction keys make the two contexts non-equivalent | Trudy's forwarded response does not authenticate |
| Defend with id binding | R includes the verifier's own sender id | Trudy's replayed R carries the wrong id; verifier rejects |

## Ship It

Produce one artifact under outputs/:

- A one-page runbook titled "Why two-message CR is not enough" that diagrams the reflection attack, names the three defenses, and recommends per-direction keys for new protocols.
- Or a threat-model document listing who can authenticate as whom under each defense: Trudy against naive CR (yes), Trudy against per-direction keys (no, unless she can also flip the direction), Trudy against id-bound challenges (no).

Start from outputs/prompt-challenge-response-authentication-and-reflection-attacks.md and back every claim with a transcript from code/main.py.

## Exercises

1. Trace the two-message CR protocol for "Alice <- Bob: R = 0x8a3f..., Alice -> Bob: HMAC-SHA256(K_AB, R) = 0x5c91....". Identify which message proves knowledge of K_AB and why an eavesdropper cannot replay it.
2. Describe the reflection attack step by step. At which message does Trudy first send Bob's own challenge R back to Bob? Which message carries the response that defeats the naive verifier?
3. Modify code/main.py to use AES-CTR (via cryptography.hazmat or a stdlib fallback) instead of HMAC. Does the reflection attack still work? Explain why or why not, and identify which property of HMAC prevents the attack.
4. Implement the per-direction key defense: K_AB_in = SHA256(K_AB || "client->server"), K_AB_out = SHA256(K_AB || "server->client"). Show that the reflection attack now fails and explain what property of the key derivation defeats Trudy.
5. Design a challenge format R = (sender_id, timestamp, nonce) that is bound to both parties and a time window. Identify two attacks the new format defeats that the naive R did not.
6. Tanenbaum notes that two-way authentication (mutual CR) doubles the protocol but halves the risk. Sketch the four-message mutual CR protocol and show that it blocks the reflection attack by symmetry.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Challenge-response | prove you have the key | Two-message protocol where the verifier issues a nonce and the prover returns a keyed function of it |
| Nonce R | the random challenge | Fresh, unpredictable value the verifier issues; must be unique inside the key's lifetime |
| K_AB | the shared key | Symmetric key both verifier and prover hold; same key in both roles is the root of the reflection vulnerability |
| Reflection attack | send it back to the sender | Trudy tricks the verifier into computing its own challenge, then forwards the answer to a different connection |
| Per-direction keys | split the key | Derive K_AB_in and K_AB_out from K_AB so that the verifier's challenge and the prover's response use different keys |
| HMAC | the standard CR function | Keyed hash used as the modern CR primitive; supports arbitrary challenge lengths and is provably secure |
| ECB mode | the textbook choice | Encrypts each block independently; the simplest CR but reuses block-structured plaintext |
| CHAP | PPP challenge | RFC 1994 challenge-response handshake used in PPP links |

## Further Reading

- Tanenbaum & Wetherall, Computer Networks, Chapter 8 Section 8.3.1 — Authentication Protocols (challenge-response and the reflection attack).
- Needham, R. M., and Schroeder, M. D. (1978). "Using encryption for authentication in large networks of computers." Communications of the ACM 21(12): 993-999 — the original mutual authentication family.
- RFC 1994 — PPP Challenge Handshake Authentication Protocol (CHAP).
- RFC 4252 — SSH Authentication Protocol (Section 8 covers publickey method using CR).
- RFC 7296 — Internet Key Exchange Protocol Version 2 (IKEv2), Section 3 — peer authentication using PSK and certificates (both use CR).
- Bellare, M., and Rogaway, P. (1993). "Entity authentication and key distribution." CRYPTO 1993, LNCS 773 — formal treatment of mutual CR protocols.
- Menezes, A., van Oorschot, P., and Vanstone, S. (1996). Handbook of Applied Cryptography, Chapter 10 — entity authentication.