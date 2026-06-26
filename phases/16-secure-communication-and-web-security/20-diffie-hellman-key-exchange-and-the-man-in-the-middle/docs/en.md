# Diffie-Hellman key exchange and the man-in-the-middle problem

> Two parties who share no prior secret can establish one across an open channel by exchanging exponentials modulo a large prime — provided they trust that the values they receive are not from an imposter. Whitfield Diffie and Martin Hellman (1976) showed that given a public prime `p` (a "safe prime" where `(p-1)/2` is also prime) and a generator `g` of the multiplicative group mod `p`, Alice and Bob can each pick a private exponent (`x` or `y`), send `g^x mod p` and `g^y mod p` to each other, and both compute the same `g^(xy) mod p` without anyone observing the wire learning `xy`. RFC 3526 specifies the standard 1536-, 2048-, 3072-, and 4096-bit MODP groups; RFC 7919 specifies the named groups used in TLS 1.3 (ffdhe2048, ffdhe3072, ffdhe4096, ffdhe6144, ffdhe8192). The trouble starts when the channel is *not* authenticated: a man-in-the-middle (a.k.a. bucket-brigade) attacker can run two simultaneous DH exchanges, one with Alice and one with Bob, and decrypt or rewrite every byte they thought was private. This lesson implements both the genuine DH (RFC 2631 / RFC 3526 §3) and the active attack, then shows how authenticated variants (signed DH, SIGMA, TLS 1.3) close the hole.

**Type:** Build
**Languages:** Python
**Prerequisites:** Phase 14 (modular arithmetic), Phase 15 (digital signatures), Phase 18 (certificates for the authenticated variant)
**Time:** ~75 minutes

## Learning Objectives

- Implement modular exponentiation `pow(g, x, p)` for `p` up to 1024 bits without using any external big-integer library, and verify it produces the same shared secret at both ends.
- Use RFC 3526's 1536-bit Group 5 and explain why `(p-1)/2` also being prime (a "safe prime") defeats the Pohlig-Hellman discrete-log attack that splits `p-1` into small factors.
- Reproduce the textbook DH exchange with `g`, `p`, `g^x mod p`, `g^y mod p` and prove both sides land on the same 1536-bit shared secret.
- Mount a man-in-the-middle attack: split the exchange into two DH runs (Alice↔Trudy, Trudy↔Bob), each with Trudy's own exponent, and read every byte Alice and Bob thought was encrypted.
- Describe how signed DH (station-to-station, SIGMA, TLS 1.3) prevents MITM by binding the public exponentials to long-term signing keys (RSA or ECDSA).
- Compare the discrete-log problem (DH, ElGamal, DSA) with the integer-factorization problem (RSA) and explain why ECDH (RFC 6090) achieves equivalent security at ~256 bits vs. RSA's 3072+.

## The Problem

If two parties have never met, they have no shared secret to bootstrap symmetric encryption with. They could try to exchange keys over the wire, but anyone tapping the wire learns the key. PKI solves this for public-key encryption, but it does not directly give Alice and Bob a *symmetric* key — and symmetric crypto is what TLS, SSH, IPsec, and WireGuard actually use on the data path. We need a way to derive a fresh symmetric secret from a public conversation.

The Diffie-Hellman construction solves exactly that — but only if you can trust the channel. The first time you read about DH you probably thought "wait, why can't Trudy just substitute her own exponentials?" She can. The protocol is correct in the *passive* adversary model and broken in the *active* adversary model. The fix is to authenticate the exponentials — usually with a signature — which is why every real protocol that uses DH (TLS 1.2/1.3, IKEv2, SSH, Signal's X3DH) combines DH with a digital signature or a pre-shared key.

## The Concept

### The DH exchange in one paragraph

Alice and Bob agree on `(p, g)` from a published Group (RFC 3526 §3). Alice picks a random `x ∈ [2, p-2]`, computes `A = g^x mod p`, and sends `A` to Bob. Bob picks `y`, computes `B = g^y mod p`, sends `B` to Alice. Alice computes `S = B^x mod p = g^(xy) mod p`. Bob computes `S = A^y mod p = g^(xy) mod p`. Both sides land on the same `S`. An eavesdropper sees `(p, g, A, B)` but cannot compute `S` without solving the discrete logarithm problem: find `x` from `g^x mod p`. For a 1536-bit safe prime, the best known algorithm (Number Field Sieve, NFS) is harder than brute-forcing a 90-bit symmetric key, which is why RFC 3526's 1536-bit Group 5 maps to roughly 90 bits of symmetric strength.

### Why safe primes and why a generator

A *safe prime* is a prime `p` where `(p-1)/2` is also prime. The corresponding *generator* `g` of order `p-1` (or the smaller subgroup of order `(p-1)/2`) has the property that `g^k mod p` cycles through all non-zero residues mod `p`. Without `p` being safe, an attacker can use Pohlig-Hellman to factor `p-1` into small primes and solve the discrete log in each factor separately, then combine via CRT — turning a 1024-bit problem into many tiny ones. RFC 3526 publishes only safe primes specifically to prevent this.

### Worked numeric example

Following Tanenbaum's textbook example (Section 8.7.2): pick `p = 47`, `g = 3`. Alice picks `x = 8`; `A = 3^8 mod 47 = 6561 mod 47 = 28`. Bob picks `y = 10`; `B = 3^10 mod 47 = 59049 mod 47 = 17`. Alice computes `S = 17^8 mod 47 = 6975757441 mod 47 = 4`. Bob computes `S = 28^10 mod 47 = 296196766695424 mod 47 = 4`. Both reach `S = 4`. Trudy, who only saw `(47, 3, 28, 17)`, would need to solve `3^x ≡ 28 (mod 47)`, which is trivial for `p = 47` but infeasible for `p` with hundreds of bits.

### The man-in-the-middle attack

```
Alice                  Trudy                  Bob
  A = g^x mod p
  ---- A ------------>  intercepts, picks z
                        B' = g^z mod p         computes B = g^y mod p
  <-- B' (from Trudy)
  S_A = (B')^x = g^(xz) mod p                  sends A
                        A' = g^z mod p  ----->  
                                          S_B = (A')^y = g^(zy) mod p
```

Trudy ends up holding `S_A = g^(xz)` (Alice thinks it's `S_AB`) and `S_B = g^(zy)` (Bob thinks it's `S_AB`). Anything Alice encrypts under `S_A`, Trudy decrypts, optionally re-encrypts under `S_B`, and forwards. Bob sees plaintext he thinks only he and Alice could see. This is the bucket-brigade attack: Trudy relays every bucket (packet) from the fire truck (Alice) to the fire (Bob) and back, peeking into each one as it passes.

### Authentication fixes the MITM

Three patterns work:

1. **Signed DH (Station-to-Station, SIGMA, TLS 1.3)**: after computing `S`, each side signs `g^x || g^y` with their long-term private key (RSA, ECDSA, Ed25519). The signatures prove that the exponentials came from the holder of the trusted key, not an attacker. TLS 1.3 (RFC 8446) combines ECDHE with the signature in the `CertificateVerify` handshake message.
2. **PAKE (Password-Authenticated Key Exchange)**: both sides know a low-entropy password; the protocol resists offline dictionary attacks even if the eavesdropper records the exchange. Used in Wi-Fi WPA3 (Dragonfly, RFC 7664) and Thread.
3. **Pre-shared keys**: out-of-band distribution of a key (QR code, NFC tap, courier) and use it to authenticate the DH exchange via a MAC. This is what WireGuard does with its "pre-shared key" mode.

### ECDH vs. classical DH

ECDH (RFC 6090) uses the same idea but on an elliptic curve: scalar multiplication of a base point `G` by private integer `x` gives a public point `x·G`. The shared secret is the x-coordinate of `x·y·G`. ECDH P-256 reaches ~128 bits of symmetric strength with only a 256-bit group — much smaller keys, signatures, and handshakes than RSA or classical DH at equivalent security. ECDHE (the "E" for ephemeral) is what TLS 1.3 calls the algorithm in its `key_share` extension.

## Build It

### Step 1 — Implement modular exponentiation by square-and-multiply

```python
from main import modexp

assert modexp(3, 8, 47) == 28
assert modexp(28, 10, 47) == 4
```

`modexp(base, exp, mod)` uses the binary method: walk `exp` from the most significant bit, square-and-multiply. No `pow` shortcut — though Python's built-in `pow(b, e, m)` is constant-time and used in production code, the by-hand version lets you watch the squares.

### Step 2 — Load RFC 3526 Group 5 (1536-bit)

```python
from main import RFC3526_GROUP5
p, g = RFC3526_GROUP5
```

The 1536-bit prime is hard-coded as a hex literal. Check it matches the IETF registry: `FFFF...FFFF2A^7B` etc.

### Step 3 — Run a clean DH exchange

```python
from main import DiffieHellman, run_dh_exchange

alice = DiffieHellman(p, g)
bob = DiffieHellman(p, g)
alice_public = alice.publish()
bob_public = bob.publish()
shared_alice = alice.shared_secret(bob_public)
shared_bob = bob.shared_secret(alice_public)
assert shared_alice == shared_bob
```

### Step 4 — Mount a man-in-the-middle attack

```python
from main import MITMTrudy, run_mitm

trudy = MITMTrudy(p, g)
alice_sees, bob_sees, alice_actual, bob_actual = run_mitm(alice, bob, trudy)
assert alice_sees != alice_actual  # Alice believes a different secret than reality
```

Trudy runs two parallel DH exchanges: one with Alice pretending to be Bob, one with Bob pretending to be Alice. The function returns the secrets each party computes and the secrets Trudy actually has.

### Step 5 — Authenticate with a signature (signed DH)

```python
from main import SignedDH, sign_shared_secret, verify_signed_dh

signer_alice, signer_bob = some_signature_setup()
A = sign_shared_secret(alice_pub, bob_pub, shared, signer_alice)
assert verify_signed_dh(alice_pub, bob_pub, shared, A, verifier_alice_pub)
```

The signature binds `g^x || g^y || shared_secret` to Alice's long-term key; Trudy's substitution of exponentials invalidates the signature because she does not have Alice's private signing key.

## Use It

| Real system | DH variant | Group / curve | Authentication |
|---|---|---|---|
| TLS 1.3 (RFC 8446) | ECDHE | X25519, P-256, P-384, ffdhe2048 | Signature in `CertificateVerify` |
| TLS 1.2 (RFC 5246) | DHE / ECDHE | Configurable cipher suite | Signature in `ServerKeyExchange` |
| IKEv2 (RFC 7296) | DH or ECDH | Groups 1–21, 25–26 | Signature or pre-shared key |
| SSH (RFC 4253) | DH | Group 1, 14, 16; X25519 in RFC 8308 | Host key signature |
| Signal X3DH | X3DH (3-DH) | X25519 | Identity keys + pre-keys |
| WireGuard | Noise IK | X25519 | Static public key in handshake |
| WPA3 (RFC 7664) | Dragonfly (PAKE) | P-256, P-384 | Password |
| IPsec (RFC 4303) | DH or ECDH | Configurable | IKEv2 signatures |

Notice the pattern: DH is the key-derivation primitive, signatures or PSKs are the authentication primitive, and the two are glued together in every real protocol.

## Ship It

The reusable artifact in `outputs/prompt-diffie-hellman.md` is `dh_lab.py` exposing:

- `RFC3526_GROUP5` and `RFC3526_GROUP14` (2048-bit) constants.
- `modexp(b, e, m)`, `DiffieHellman(p, g)`, `shared_secret(...)`.
- `MITMTrudy` that logs each forged message and recovers both shared secrets.
- `signed_dh.py` that wraps a `DiffieHellman` instance with a signature over `(g^x, g^y, S)` using PKCS#1 v1.5 RSA.

Plus a `cli.py` that runs the clean exchange, prints the shared secret fingerprints, runs the MITM attack, and prints the four secrets side-by-side.

## Exercises

1. Hand-compute `modexp(5, 13, 23)`. Walk through the binary expansion of `13 = 1101b` and confirm the intermediate squares are 5, 25=2, 4, 16, 8, 64=18, 18*5=20, then `modexp(5, 13, 23) = 21`. Why does the binary method take at most `2 log2(exp)` multiplications?
2. Re-run the DH exchange with `p = 23` (not safe prime; `(p-1)/2 = 11` is prime but `p-1 = 22 = 2·11` has small factors). What is the order of `g = 5`? Does the order matter for the security argument?
3. Implement the Pohlig-Hellman attack on `p = 23`, `g = 5`, `A = g^x mod p` for `x ∈ [2, 20]`. Confirm you can recover `x` in `O(sqrt(11))` work — orders of magnitude faster than brute force.
4. In the MITM attack, what stops Trudy from doing the same thing twice — once in each direction — and reading the *cleartext* Alice sends Bob? (Answer: DH only establishes the key; the data path still uses symmetric crypto with that key. Once Trudy holds the keys, the symmetric encryption is transparent.)
5. Compare `modexp(2, p-1, p) == 1` for an RFC 3526 prime. Fermat's little theorem guarantees this for any `p` coprime to 2. Verify it for the first 200 hex digits and explain why it is a sanity check, not a security proof.
6. Replace signed DH with HMAC-based binding: Alice computes `HMAC(PSK, g^x || g^y)` and sends it alongside the exponentials. Why does this work for a PSK but not for an unknown peer? (Hint: HMAC requires both sides to know the key; a brand-new SSH host has no shared secret yet.)

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Diffie-Hellman | "key exchange" | Public exponentials `g^x`, `g^y` over a safe prime group; both sides compute `g^(xy)` |
| Safe prime | "the modulus" | Prime `p` where `(p-1)/2` is also prime; prevents Pohlig-Hellman |
| Generator | "g" | Element of multiplicative group mod p with order `p-1`; cycles through all non-zero residues |
| Discrete log | "hard problem" | Given `g^x mod p`, find `x`; basis of DH, ElGamal, DSA, Schnorr security |
| Shared secret | "the session key" | `g^(xy) mod p`; seed for HKDF (RFC 5869) to derive symmetric keys |
| ECDH | "elliptic curve DH" | Same idea on elliptic curve groups; smaller keys (RFC 6090) |
| DHE / ECDHE | "ephemeral DH" | Fresh `x, y` per session; provides forward secrecy |
| MITM | "man in the middle" | Active attacker who relays and substitutes messages between two honest parties |
| Bucket brigade | "passing buckets" | Tanenbaum's name for MITM because of the relay metaphor |
| Forward secrecy | "FS" | Compromising long-term key does not recover past session keys; requires ephemeral DH |

## Further Reading

- Diffie, W., & Hellman, M. E. (1976). *New Directions in Cryptography.* IEEE Transactions on Information Theory.
- RFC 2631 — Diffie-Hellman Key Agreement Method (the ECP / DH primitives)
- RFC 3526 — More MODP Diffie-Hellman groups for IKE (Group 5 = 1536-bit, Group 14 = 2048-bit)
- RFC 7919 — Negotiated Finite Field Diffie-Hellman Ephemeral Parameters for TLS (ffdhe2048 etc.)
- RFC 6090 — Fundamental Elliptic Curve Cryptography Algorithms (ECDH)
- RFC 8446 — The Transport Layer Security Protocol Version 1.3 (uses ECDHE)
- RFC 5869 — HMAC-based Extract-and-Expand Key Derivation Function (HKDF; turns the DH shared secret into symmetric keys)
- Rescorla, E. — *Diffie-Hellman, revisited*, ;login: 2018 (the historical context of "Logjam")
- Tanenbaum, A. S., & Wetherall, D. J. — *Computer Networks*, 5th ed., Ch. 8.7.2
