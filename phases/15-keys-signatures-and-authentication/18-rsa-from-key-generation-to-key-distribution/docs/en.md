# RSA: From Key Generation to Session-Key Distribution

> RSA (Rivest, Shamir, Adleman, 1978; RFC 8017 PKCS#1) is the most widely deployed public-key algorithm. Its security rests on the difficulty of factoring the product of two large primes: given `n = p × q`, finding `p` and `q` is believed to be computationally infeasible for `n ≥ 2048` bits. RSA gives us two operations: encrypt with the public key `(e, n)` to compute `C = P^e mod n`, and decrypt with the private key `(d, n)` to compute `P = C^d mod n`. The same pair of operations, swapped, gives digital signatures. This lesson implements textbook RSA from scratch in pure Python: key generation (Miller-Rabin primality testing, modular inverse via extended Euclidean), the encrypt/decrypt primitives, and the canonical `SUZANNE` example from the chapter (p=3, q=11, e=3, d=7). It then builds a session-key distribution protocol on top: Alice generates a fresh AES-256 session key, RSA-encrypts it under Bob's public key, and Bob decrypts to recover the session key — exactly how TLS, S/MIME, and SSH key exchange work.

**Type:** Learn
**Languages:** Python, big-integers
**Prerequisites:** Modular arithmetic, lessons 11–17
**Time:** ~90 minutes

## Learning Objectives

- Generate RSA keys from scratch: pick primes `p`, `q` via Miller-Rabin, compute `n = p × q`, choose `e`, compute `d = e^-1 mod phi(n)` via extended Euclidean.
- Encrypt and decrypt a message under RSA and verify the chapter's SUZANNE example reproduces `C = P^3 mod 33`.
- Explain why the security rests on the difficulty of factoring `n`, and quantify the threat (RSA-250 factored in 2020, RSA-2048 estimated at 10^24 operations).
- Implement a textbook RSA-OAEP-like padding check (or warn that textbook RSA is deterministic and malleable).
- Build a session-key distribution protocol: Alice generates a 256-bit AES key, RSA-encrypts it for Bob, Bob recovers it and uses it for symmetric encryption.
- Recognize the role of RSA in TLS (key exchange), SSH (host key signing), S/MIME (email), and X.509 certificates.

## The Problem

You are designing a wire between two services that must share a fresh AES session key for every connection. Diffie-Hellman would work but you want a simpler protocol: the server publishes its RSA public key once, and every client can encrypt a fresh session key to it without an interactive handshake. This is the "RSA key transport" mode of TLS 1.2 (now superseded by (EC)DH in TLS 1.3, but still everywhere in legacy systems).

The lesson walks through the entire stack: how RSA keys are generated, why the math works, what the chapter's SUZANNE example shows, and how to layer session-key distribution on top.

## The Concept

### The Diffie-Hellman revolution

Before RSA (chapter §8.3), every cryptosystem used the same secret key for encryption and decryption. Distributing those keys securely was the weakest link. Diffie and Hellman (1976) proposed: what if the encryption key and decryption key are *different*, the encryption key is public, and deducing the private key from the public key is infeasible? RSA, published by Rivest, Shamir, and Adleman in 1978, gave the first practical construction. They received the 2002 ACM Turing Award for it.

### Key generation (chapter §8.3.1)

The four-step procedure:

1. Pick two large primes `p` and `q`. In practice each is at least 1024 bits, giving `n ≥ 2048` bits.
2. Compute `n = p × q` and `z = (p - 1) × (q - 1)`.
3. Choose `e` relatively prime to `z`. The textbook choice is `e = 65537` (`0x10001`); `e = 3` works for pedagogy.
4. Find `d` such that `e × d ≡ 1 (mod z)`. The extended Euclidean algorithm gives this.

Public key: `(e, n)`. Private key: `(d, n)`. The primes `p`, `q`, and `z` are discarded — knowing any one of them lets you compute `d` from `e`, so they must be securely zeroed after key generation.

### Encrypt and decrypt

For a plaintext `P` (an integer in `[0, n)`):

```
encrypt:  C = P^e mod n
decrypt:  P = C^d mod n
```

The math: by Fermat's little theorem, for `P` coprime to `p` and `q`, `P^(k*phi(n)+1) ≡ P (mod n)`. With `e × d = 1 + k × phi(n)`, we have `C^d = (P^e)^d = P^(e×d) ≡ P (mod n)`. RSA is therefore a *trapdoor permutation*: easy to compute forward, hard to invert without `d`.

### The chapter's SUZANNE example

The chapter's pedagogical example uses tiny primes:

| | Value |
|---|---|
| p | 3 |
| q | 11 |
| n | 33 |
| z = (p-1)(q-1) | 20 |
| d | 7 |
| e | 3 (since 3 × 7 = 21 ≡ 1 mod 20) |

Encrypting each letter `S U Z A N N E` as a number `P` between 1 and 26:

| Letter | P | P^3 | P^3 mod 33 |
|--------|---|-----|------------|
| S | 19 | 6859 | 28 |
| U | 21 | 9261 | 21 |
| Z | 26 | 17576 | 20 |
| A | 1 | 1 | 1 |
| N | 14 | 2744 | 5 |
| N | 14 | 2744 | 5 |
| E | 5 | 125 | 26 |

Decryption with `C^7 mod 33` recovers each letter. The lesson reproduces these exact numbers.

### Why RSA works at all: Euler's theorem

Euler's totient `phi(n)` counts integers in `[1, n]` coprime to `n`. For `n = p × q` with `p, q` prime, `phi(n) = (p-1)(q-1)`. Euler's theorem says `a^phi(n) ≡ 1 (mod n)` for `a` coprime to `n`. Setting `e × d ≡ 1 (mod phi(n))` gives `e × d = 1 + k × phi(n)` for some integer `k`, so `(P^e)^d = P^(1 + k × phi(n)) = P × (P^phi(n))^k ≡ P × 1^k ≡ P (mod n)`.

### Why RSA is slow

Modular exponentiation with a 2048-bit modulus takes millions of multiplications of 2048-bit numbers. AES-128 can do billions of blocks per second on AES-NI; RSA-2048 decryption takes ~1 ms per operation on the same hardware. So RSA is only used to encrypt small things — typically 32-byte session keys.

### Why textbook RSA is dangerous

`C = P^e mod n` is deterministic: encrypting the same `P` twice gives the same `C`. This breaks IND-CPA security. Worse, RSA is *malleable*: an attacker who sees `C = P^e` can compute `(C × 2^e) mod n = (2P)^e mod n`, the encryption of `2P`. The lesson's session-key distribution therefore pads the session key with OAEP-style randomness before encryption. Production code uses RSAES-OAEP from RFC 8017 §7.1.

### Miller-Rabin primality testing

Generating RSA keys requires primes. A random 1024-bit number is prime with probability ~1 / 1024 ln 2 ≈ 1/710. The Miller-Rabin test determines primality with probability 1 - 4^(-k) after `k` rounds. For `k = 40`, the false-positive rate is `4^-40 < 10^-24` — small enough to ignore.

The test: write `n - 1 = 2^s × d` with `d` odd. For a random witness `a`:

- Compute `x = a^d mod n`. If `x == 1` or `x == n - 1`, `n` is probably prime.
- Otherwise, repeatedly square `x` up to `s - 1` times. If `x == n - 1` at any point, `n` is probably prime.
- Otherwise, `n` is composite.

### Extended Euclidean algorithm

To compute `d = e^-1 mod phi(n)`, use the extended Euclidean algorithm. The standard Euclidean algorithm computes `gcd(e, phi(n))`; the extended version tracks coefficients so that `gcd(e, phi(n)) = s × e + t × phi(n)`. When `gcd = 1`, `s ≡ e^-1 (mod phi(n))`.

### RSA in the wild

| Use | Where |
|-----|-------|
| TLS 1.2 key transport | Legacy HTTPS servers |
| TLS 1.3 signatures | RSA-PSS signatures over (EC)DH keys |
| X.509 certificates | RSA-PSS or RSA-PKCS1v1.5 signatures |
| S/MIME email | RSA encrypts content-encryption keys |
| SSH host keys | RSA-2048/4096, slowly being replaced by Ed25519 |
| PGP | RSA encrypts session keys |
| JWT (RS256/PS256) | RSA signatures for OAuth tokens |

NIST recommends 2048-bit RSA minimum through 2030 and 3072-bit for new deployments. RSA-4096 is common in long-lived root certificates.

## Build It

The implementation lives in `code/main.py` (≈230 lines). It exposes:

- `is_probable_prime(n, k=40)` — Miller-Rabin test.
- `generate_prime(bits, rng=secrets)` — random prime of given bit length.
- `egcd(a, b)`, `modinv(a, m)` — extended Euclidean and modular inverse.
- `rsa_keygen(bits=2048, e=65537)` — generate a key pair.
- `rsa_encrypt(P, pub)` / `rsa_decrypt(C, priv)` — textbook RSA.
- `rsa_encrypt_oaep(P, pub)` / `rsa_decrypt_oaep(C, priv)` — RSAES-OAEP-style padding.
- `suzanne_demo()` — reproduces the chapter's `SUZANNE` example exactly.
- `session_key_distribution()` — Alice encrypts an AES key, Bob decrypts it.

Reproduce the chapter's SUZANNE example:

```python
from main import suzanne_demo
suzanne_demo()
```

Generate a real 2048-bit RSA key:

```python
from main import rsa_keygen
pub, priv = rsa_keygen(bits=2048)
print("n bits:", pub[1].bit_length())
```

End-to-end session-key distribution:

```python
from main import rsa_keygen, session_key_distribution
pub, priv = rsa_keygen(bits=2048)
aes_key, ciphertext, recovered = session_key_distribution(pub, priv)
print("AES key recovered:", recovered == aes_key)
```

## Use It

| Function | Real-world counterpart | Notes |
|----------|------------------------|-------|
| `is_probable_prime` | OpenSSL `BN_prime_test`, GMP `mpz_probab_prime_p` | Real libraries use faster BPSW and deterministic witnesses for small `n`. |
| `rsa_keygen` | OpenSSL `RSA_generate_key_ex` | Real keygen uses safe primes (`p = 2q + 1`) and adds `e = 65537`. |
| `rsa_encrypt_oaep` | RFC 8017 §7.1 RSAES-OAEP | The real OAEP uses MGF1-SHA256 and an empty label. |
| `session_key_distribution` | TLS 1.2 RSA key transport | TLS 1.3 removed this in favor of (EC)DH; many legacy systems still use it. |
| `suzanne_demo` | Pedagogical example | The chapter's exact `P^3 mod 33` table. |

## Ship It

A reusable artifact for cryptography courses lives at `outputs/prompt-rsa-from-primes-to-session-keys.md`. It includes the SUZANNE walkthrough, a 2048-bit keygen demo, and a checklist for choosing RSA vs ECC vs (EC)DH in new protocols. Reuse it when introducing public-key cryptography.

## Exercises

1. Modify `rsa_keygen` to generate safe primes `p = 2q + 1` where `q` is also prime. Verify the property with a primality test.
2. Implement RSA-CRT (Chinese Remainder Theorem) decryption: compute `d_p = d mod (p-1)` and `d_q = d mod (q-1)`, then use Garner's formula. Measure the speedup.
3. Implement RSA-OAEP per RFC 8017 §7.1 with MGF1-SHA256.
4. Implement RSA-PSS signatures per RFC 8017 §8.1 and verify a message-signature pair.
5. Reproduce the chapter's claim: factoring RSA-250 (829 bits) is at the edge of feasibility in 2020. How does the 2048-bit RSA modulus compare?
6. Implement a Bleichenbacher-style attack against textbook RSA: recover plaintext from `C = P^e mod n` by choosing a related ciphertext `C' = C × r^e mod n` and asking an oracle whether `P'` is correctly formatted.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Public key | "(e, n)" | Encryption exponent and modulus; published freely. |
| Private key | "(d, n)" | Decryption exponent and modulus; secret. |
| Modulus | "n = p × q" | Product of two large primes; ~2048 bits. |
| phi(n) | "(p-1)(q-1)" | Euler's totient of the RSA modulus. |
| RSAES-OAEP | "Padded RSA" | RFC 8017 §7.1; defeats malleability and deterministic leaks. |
| RSA-PSS | "Probabilistic signature scheme" | RFC 8017 §8.1; modern RSA signature padding. |
| CRT | "Chinese Remainder Theorem" | Speeds up RSA decryption by 4× by splitting mod p and mod q. |
| Common modulus attack | "Same n, different e" | If two users share `n`, an attacker recovers both private keys via `egcd`. |
| Fermat's little theorem | "a^(p-1) = 1 mod p" | The number-theory fact that makes RSA work. |
| Miller-Rabin | "Probabilistic primality test" | Random-witness test with 1 - 4^(-k) confidence. |

## Further Reading

- Tanenbaum, *Computer Networks*, Chapter 8 (this chapter).
- Rivest, R., Shamir, A., Adleman, L., *A Method for Obtaining Digital Signatures and Public-Key Cryptosystems*, CACM 21(2), 1978.
- RFC 8017 — *PKCS #1: RSA Cryptography Specifications v2.2*.
- Boneh, D., *Twenty Years of Attacks on the RSA Cryptosystem*, Notices of the AMS 46(2), 1999.
- NIST SP 800-56B — *Recommendation for Pair-Wise Key-Establishment Using Integer Factorization Cryptography*.
- RSA-250 factorization announcement (2020): https://lists.gforge.inria.fr/pipermail/cado-nfs-discuss/.