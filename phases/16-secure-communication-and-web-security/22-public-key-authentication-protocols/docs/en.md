# Public-key authentication and mutual challenge-response

> When both parties hold long-term public keys (issued by a PKI they both trust, fetched via a directory, or pinned out-of-band), mutual authentication collapses to two nonces and two signatures — no KDC, no pre-shared key, no clock synchronization. Alice and Bob exchange nonces (`R_A` from Alice, `R_B` from Bob), then each signs the pair `(R_A, R_B, identity_A, identity_B)` with their long-term private key. The receiver verifies with the sender's public key from a directory (X.509, RFC 5280), from a TOFU pin (SSH `known_hosts`), or from a pre-shared fingerprint. Trudy cannot substitute her own nonces because she does not have Alice's signing key, and cannot replay an old transcript because the nonces are fresh per session. This lesson builds a complete mutual challenge-response protocol on top of the RSA verifier from lesson 18, shows the seven-message TLS 1.3 handshake (RFC 8446 §4) as the canonical real-world deployment, and contrasts SSH `publickey` auth (RFC 4252 §7), which uses a hash of the session identifier instead of two nonces.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Phase 18 (X.509 certificates and PKCS#1 v1.5 signing), Phase 20 (Diffie-Hellman), Phase 15 (digital signatures)
**Time:** ~75 minutes

## Learning Objectives

- Trace a mutual challenge-response with two nonces `R_A` and `R_B`, identifying which party signs what and which key verifies each signature.
- Implement the protocol on top of the RSA signer/verifier from lesson 18 and produce a typed `MutualAuthResult` with the session keying material.
- Explain why the two nonces must be cryptographically independent and generated from `secrets.token_bytes(32)` (not from `random`).
- Map the abstract protocol to SSH `publickey` auth (RFC 4252 §7, hash over session ID + identity + key + nonce) and to TLS 1.3 mutual auth (RFC 8446 §4.4, signature over handshake transcript).
- Reproduce a downgrade attack: an attacker who can rewrite the wire negotiates a weaker algorithm; defend by binding the algorithm choice into the signed transcript.
- Compare password, shared-secret, public-key, and certificate-based authentication on three axes: deployability, trust model, and forward secrecy.

## The Problem

Shared-secret auth (lesson 19) requires Alice and Bob to share a secret before they ever meet — that is a chicken-and-egg problem at internet scale. Certificates (lesson 18) solve the binding of identity to public key, but a certificate alone does not prove that Alice (the entity in possession of the private key) is on the other end of the wire right now. Public-key mutual challenge-response is the protocol that combines those two pieces: prove you have the private key matching a public key that the other side trusts, and do it without sending the private key or anything replayable.

The reason this protocol dominates modern auth — TLS client certificates, SSH public-key auth, WebAuthn, smart-card login, and Signal's identity-key system — is that it has exactly the properties you want and none of the ones you do not:

- **No shared secret to provision.** The CA signs the binding; you do not hand out keys.
- **No clock sync required.** Freshness comes from nonces, not timestamps.
- **Replay-resistant by construction.** A transcript is bound to two nonces that exist only for this session.
- **Mutual by default.** Either side can require the other to prove the same thing.
- **Forward-secret with one addition.** Combine with Diffie-Hellman (lesson 20) to get ephemeral session keys even if the long-term key is later compromised.

## The Concept

### The protocol in one paragraph

```
Alice                                                    Bob
  ----- R_A (32 random bytes) ---------------------------> 
                                                          generate R_B
  <-------------------- R_B ------------------------------ 
  sign: SA = SIG_Alice(R_A || R_B || "alice" || "bob")   
  ---- SA, optional: cert chain for Alice's pub key ---->
                                                          verify SA with Alice's pub key
                                                          sign: SB = SIG_Bob(R_A || R_B || "alice" || "bob")
  <------------------ SB, optional: cert chain -----------
  verify SB with Bob's pub key
```

Both sides end up with `R_A || R_B`, proof that each holds the other's expected long-term key, and a transcript they can hash into a session key (`HKDF-Extract(R_A || R_B, salt = "mutual-auth")`, RFC 5869).

### Why two nonces?

A single nonce proves liveness to one party but leaves the other side open to a reflection attack: Trudy opens a connection to Alice, gets Alice's challenge response, then opens a connection to Alice pretending to be Bob and replays Alice's own challenge — Alice would happily "authenticate herself" to herself. Two independent nonces defeat reflection: Bob's `R_B` is bound into Alice's signature and only Bob (the holder of `R_B`) can verify it.

### Canonical deployments

**SSH publickey auth (RFC 4252 §7)**: the client signs `session_id || user || "ssh-connection" || public_key_blob || R_B` where `session_id` is the SSH binary packet negotiated at transport setup. The server has previously accepted the client's public key (either by TOFU on first connect with a fingerprint prompt, or pre-distributed via `authorized_keys`). The nonces are implicit: `session_id` is shared from the transport handshake and `R_B` is the server's anti-replay token from the `SSH_MSG_USERAUTH_REQUEST`.

**TLS 1.3 mutual auth (RFC 8446 §4.4)**: the client signs a `CertificateVerify` struct containing the hash of the entire handshake transcript (`transcript_hash`) concatenated with a context-specific byte string. The server does the same in `CertificateVerify` on its side. Both signatures cover every byte of the handshake — every ClientHello extension, every ServerHello, every Finished — so an attacker who rewrites any byte invalidates both signatures.

**WebAuthn / FIDO2**: the authenticator signs `authenticatorData || clientDataHash` where `clientDataHash = SHA-256(origin || challenge || type || crossOrigin)`. The challenge is the server's nonce, the origin binds the signature to a specific site, and the counter field inside `authenticatorData` defeats replay even within the same session.

### Why bind the algorithm choice

A downgrade attack works like this: Alice supports two signature algorithms (`rsa-pkcs1-sha256` and `rsa-pkcs1-sha1`), and Bob does too. Trudy rewrites the wire so both sides negotiate `sha1`. Both sides sign and verify successfully under the weaker algorithm, but neither knows the other is capable of `sha256`. The fix (used in TLS 1.3 `signature_algorithms` extension, RFC 8446 §4.2.3) is to put the algorithm identifier *inside* the signed bytes, so a downgrade invalidates the signature.

### The transcript hash

Every modern mutual auth protocol signs not just the nonces but a hash of every preceding message. The reason is the same as the algorithm-binding fix: if the transcript covers the negotiated algorithm, the cipher suite, the certificate chain, the nonces, and any extensions, then no byte of the handshake can be silently rewritten. TLS 1.3 calls this the `transcript_hash`; SSH calls it `session_id`; Signal calls it the "chain key" derived from the ratchet.

## Build It

### Step 1 — Generate nonces

```python
from main import generate_nonce

ra = generate_nonce()
rb = generate_nonce()
assert ra != rb
```

Each nonce is 32 bytes from `secrets.token_bytes(32)`. Never derive one nonce from another — that re-creates a single-nonce protocol.

### Step 2 — Sign and verify a mutual transcript

```python
from main import (
    rsa_keypair, pkcs1_v15_sign, pkcs1_v15_verify,
    mutual_challenge_response,
)

alice_priv, alice_pub = rsa_keypair()
bob_priv, bob_pub = rsa_keypair()

result = mutual_challenge_response(alice_priv, alice_pub, bob_priv, bob_pub)
assert result.success
assert result.session_key_material == derive_session_key(result.ra, result.rb)
```

The function drives the full protocol, returning a `MutualAuthResult` with `ra`, `rb`, `alice_signature`, `bob_signature`, and the SHA-256 of `(ra || rb)` as session keying material.

### Step 3 — Inject a downgrade attack

```python
def downgrade_attack(ra, rb, sig_alice, sig_bob, advertised_algo="rsa-pkcs1-sha1"):
    return (ra, rb, sig_alice, sig_bob, advertised_algo)

def mutual_challenge_response_with_algo_check(...):
    # Re-verify with the algorithm actually used
```

Your verification code must reject any signature that was computed under a different algorithm than the one currently in use.

### Step 4 — Compare with SSH publickey

```python
from main import ssh_publickey_sign, ssh_publickey_verify

sig = ssh_publickey_sign(alice_priv, session_id=b"...", user="alice", service="ssh-connection", key_blob=alice_pub_blob)
ok = ssh_publickey_verify(sig, alice_pub, session_id=b"...", user="alice", service="ssh-connection", key_blob=alice_pub_blob)
```

The SSH-specific transcript `session_id || user || service || key_blob || nonce` matches RFC 4252 §7.

## Use It

| Real system | Two nonces? | Long-term key | What is signed |
|---|---|---|---|
| SSH publickey (RFC 4252) | session_id + server nonce | RSA / ECDSA / Ed25519 | `session_id || user || svc || pubkey_blob || nonce` |
| TLS 1.3 mutual (RFC 8446) | handshake transcript hash | RSA / ECDSA / EdDSA | `0x00 * 64 || context || transcript_hash` (CertificateVerify) |
| WebAuthn (W3C) | server challenge | ECDSA / EdDSA (per credential) | `authenticatorData || SHA-256(clientDataJSON)` |
| S/MIME (RFC 8551) | none; signed message body | X.509 RSA / ECDSA | PKCS#7 `SignedData` over MIME body |
| PGP (RFC 9580) | none; signed message | OpenPGP key | hashed subpacket + signature packet over body |
| Signal X3DH | per-message DH ratchet | Identity + pre-keys | XEdDSA over the DH chain |
| FIDO2 / passkeys | server challenge | ECDSA P-256 | `authData || clientDataHash` |

Notice that every modern system uses exactly one nonce (server-generated) plus a transcript hash that binds everything else. The two-nonce protocol in this lesson is the simplest form that is correct; in production, transcript binding subsumes the second nonce.

## Ship It

The reusable artifact in `outputs/prompt-public-key-auth.md` is `mutual_auth.py` with:

- `rsa_keypair(bits=2048)` (re-uses lesson 18).
- `mutual_challenge_response(...)` returning `MutualAuthResult`.
- `ssh_publickey_sign(...)` and `tls13_certificate_verify(...)` that implement the protocol-specific transcript format.
- `cli.py` that runs the protocol with a randomly generated keypair on each side, prints the nonces, signatures, and session key fingerprint, and reports the MITM failure mode when one party's key is replaced.

## Exercises

1. Use `random.randint` instead of `secrets.token_bytes(32)` for the nonces. Why is `random` broken here? (Hint: Mersenne Twister state recovery — after observing ~624 32-bit outputs you can predict every subsequent value.)
2. Drop one of the nonces and run the protocol. The reflection attack now succeeds: send Alice's own challenge back to her. Trace the bytes.
3. Add the algorithm OID to the signed bytes. Replay the downgrade attack from Step 3 — does your verifier catch it? Why is the algorithm OID sufficient to defeat negotiation downgrades?
4. Compare the size of the signed structure: two-nonce mutual challenge-response vs. TLS 1.3 `CertificateVerify` over the full transcript. Which is faster to verify? Which is more robust to negotiation attacks?
5. What happens if Alice and Bob do not share a directory, but both pin each other's public key fingerprint out-of-band (SSH TOFU style)? Walk through the trust assumptions and where the man-in-the-middle can still sit.
6. Combine this lesson with lesson 20: after the mutual challenge-response completes, run an ECDH key exchange (or reuse the RSA-OAEP encrypt-a-DH-secret pattern) and derive a forward-secret session key. What does the new protocol guarantee that the standalone mutual challenge-response does not?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Mutual auth | "both prove identity" | Each side signs a transcript including the other's nonce; replay requires forging a signature |
| Challenge-response | "prove you know the secret" | Server sends nonce; client returns signature/HMAC; bound to one session |
| Nonce | "random number" | Per-session random value with cryptographic unpredictability (`secrets.token_bytes`) |
| Reflection attack | "send it back" | Trudy replays Alice's challenge back to Alice; defeated by two independent nonces |
| Transcript hash | "covers everything" | Hash of every preceding protocol message; signed to bind algorithm and cipher suite choices |
| TOFU | "trust on first use" | SSH pattern: accept the host key on first connect, pin the fingerprint forever |
| Downgrade attack | "negotiate weaker" | Trudy rewrites algorithm negotiation; defeated by binding algorithm into signed transcript |
| CertificateVerify | "the TLS 1.3 signature" | RFC 8446 §4.4.3: signature over `context || transcript_hash` using the long-term key |
| PKI | "the trust anchor" | The directory or chain of trust that maps identity to public key (lesson 18) |
| Forward secrecy | "FS / PFS" | Compromising long-term key does not recover past session keys; requires ephemeral DH on top |

## Further Reading

- Needham, R. M., & Schroeder, M. D. (1978). *Using encryption for authentication in large networks of computers.*
- RFC 4252 — SSH Authentication Protocol (publickey method in §7)
- RFC 4253 — SSH Transport Layer Protocol (session_id derivation in §6)
- RFC 5246 — The TLS Protocol Version 1.2 (CertificateVerify in §7.4.8)
- RFC 8446 — The Transport Layer Security Protocol Version 1.3 (mutual auth in §4.4)
- RFC 8017 — PKCS#1 v2.2: RSASSA-PKCS1-v1_5 and RSASSA-PSS signatures
- RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function (HKDF; turns `(R_A, R_B)` into symmetric keys)
- W3C Web Authentication (WebAuthn) Level 2, §5.1 (authenticatorData signing)
- OWASP Authentication Cheat Sheet (deployment tradeoffs across all four mechanisms)
