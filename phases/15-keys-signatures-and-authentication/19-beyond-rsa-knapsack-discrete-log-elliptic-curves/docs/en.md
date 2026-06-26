# Beyond RSA: Knapsack, Discrete-Log, and Elliptic Curves

> RSA is the dominant public-key algorithm, but the chapter (§8.3.2) lists three other families: **knapsack** schemes (broken — the chapter tells the famous story of Merkle offering $100, $1000, then declining $10000 bounties that Rivest, Shamir, and Adleman successively collected); **discrete-logarithm** schemes (ElGamal, Schnorr, DSA — still secure); and **elliptic-curve** schemes (Menezes-Vanstone 1993 — the modern default). All three are worth understanding because they trade different mathematical problems against RSA's factoring problem. ECC in particular offers equivalent security to RSA at much smaller key sizes: a 256-bit EC key matches RSA-2048, and a 384-bit EC key matches RSA-7680. This lesson implements toy Merkle-Hellman knapsack (and shows the low-density attack breaking it), ElGamal encryption over a multiplicative group, and a small elliptic-curve group with point addition, doubling, and scalar multiplication. You will see exactly why ECC is preferred for new protocols and why knapsack is now in the cryptographic museum.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Lesson 18 (RSA), modular arithmetic
**Time:** ~75 minutes

## Learning Objectives

- Implement the Merkle-Hellman knapsack cryptosystem: superincreasing sequence, trapdoor pair, encryption by subset sum, decryption by modular inverse.
- Demonstrate the **low-density attack** (Shamir, 1984) breaking Merkle-Hellman knapsack, justifying the chapter's history lesson.
- Implement ElGamal encryption: choose a prime `p`, generator `g`, private key `x`, public key `y = g^x mod p`; encrypt `M` as `(g^k mod p, M * y^k mod p)`; decrypt by multiplying by `p^x mod p`'s inverse.
- Solve a small discrete-log problem via baby-step giant-step to show why `p` must be large.
- Implement an elliptic-curve group `E: y^2 = x^3 + ax + b mod p` with point addition, doubling, and scalar multiplication.
- Compare key sizes: ECC-256 ≈ RSA-2048 in security strength; explain the asymptotic advantage.

## The Problem

You are choosing a public-key algorithm for a new IoT device that has 32 KB of flash. RSA-2048 needs ~256 bytes for the public key, ~1 KB for the private key in PKCS#8 form, and RSA signature operations are slow. ECC-256 (Ed25519 or NIST P-256) needs 32 bytes for the public key, 32 bytes for the private key, and signatures are 64 bytes, computed in microseconds.

You also want to understand the alternatives — why knapsack failed, what makes ElGamal secure, and why ECC's security reduces to the elliptic-curve discrete-log problem (ECDLP). The lesson builds all three.

## The Concept

### Knapsack and the chapter's history lesson

The chapter (§8.3.2) tells the famous story. The Merkle-Hellman knapsack:

- **Public key**: a sequence of `n` integers `b_1, ..., b_n` and a modulus `m`.
- **Private key**: a superincreasing sequence `a_1, ..., a_n` (each `a_i > sum of all smaller a_j`), a multiplier `w`, and a modulus `m` such that `b_i = w * a_i mod m`. The private key lets you solve the subset-sum problem efficiently.
- **Encrypt**: choose a subset `S` of indices; ciphertext is `sum_{i in S} b_i`.
- **Decrypt**: divide by `w` mod `m` to convert to the superincreasing form; greedy algorithm recovers the subset.

The chapter: "Ralph Merkle was quite sure that this algorithm could not be broken, so he offered a $100 reward to anyone who could break it. Adi Shamir (the 'S' in RSA) promptly broke it and collected the reward." Then $1000 to Ronald Rivest. Then Merkle declined the $10000 escalation.

The attack: Shamir's **low-density attack** (1984) on knapsack instances where `n / log2(max(b))` is small. Most knapsack proposals have density < 1, so the attack works. Modern knapsack variants (Chor-Rivest) survived longer but were broken by 1995.

### Discrete-logarithm schemes

The chapter: "Other public-key schemes are based on the difficulty of computing discrete logarithms. Algorithms that use this principle have been invented by El Gamal (1985) and Schnorr (1991)."

The **discrete-log problem** in `Z_p*`: given `y = g^x mod p`, find `x`. The best general algorithm is **index calculus** with sub-exponential complexity `L_p[1/2, c]` for `L_p[a, c] = exp(c * (log p)^a * (log log p)^(1-a))`. For ECC, the best known is **Pollard's rho** with complexity `O(sqrt(n))` for an `n`-bit curve, which is exponential. That gap is why ECC needs smaller keys.

**ElGamal encryption** over `Z_p*`:

- Public parameters: prime `p`, generator `g` of `Z_p*`.
- Alice's keypair: private `x`, public `y = g^x mod p`.
- Bob encrypts message `M`: choose random `k`, send `(c1, c2) = (g^k mod p, M * y^k mod p)`.
- Alice decrypts: `M = c2 * (c1^x)^-1 mod p` because `c1^x = g^(kx)` and `(g^(kx))^-1 * y^k = (g^(kx))^-1 * g^(xk) = 1`.

Security reduces to discrete log in `Z_p*`. Requires `p ≥ 2048` bits for safety.

### DSA and Schnorr signatures

NIST's **DSA** (Digital Signature Algorithm, FIPS 186-4) is an ElGamal-style signature over a Schnorr group. Each signature is `(r, s)` where `r = (g^k mod p) mod q` for a random `k`, and `s = k^-1 * (H(m) + x*r) mod q`. Verification checks `r = (g^(H(m)*s^-1) * y^(r*s^-1) mod p) mod q`.

DSA keys are `(p, q, g, x, y)` — same ElGamal structure. DSA was controversial when NIST proposed it in 1991: too secret (NSA involvement), too slow, too new, too insecure (fixed 512-bit `q`). Modern DSA allows 1024- and 2048-bit `q`.

### Elliptic-curve cryptography

The chapter (§8.3.2) mentions: "A few other schemes exist, such as those based on elliptic curves (Menezes and Vanstone, 1993)."

An **elliptic curve** over a prime field `Z_p` is the set of points `(x, y)` with `y^2 ≡ x^3 + ax + b mod p`, plus the point at infinity. The group operation is **point addition**: draw a line through two points; its third intersection with the curve is the negation of the sum. Point doubling is the tangent-line case.

**Scalar multiplication** is repeated addition: `[k]P = P + P + ... + P` (k times). The **ECDLP**: given `[k]P` and `P`, find `k`. The best general attack is Pollard's rho at `O(sqrt(n))` group operations for an `n`-bit curve order. There is no known sub-exponential algorithm for general curves — that is why ECC is preferred.

Standardized curves:

| Curve | Field | Security | Used by |
|-------|-------|----------|---------|
| NIST P-256 | 256 bits | ~128 bits | TLS 1.3, FIDO2, US government |
| Curve25519 (X25519) | 256 bits | ~128 bits | TLS 1.3, SSH, Signal |
| Ed25519 | 255 bits | ~128 bits | Signatures: SSH, GPG, JWT (EdDSA) |
| NIST P-384 | 384 bits | ~192 bits | TLS 1.3, high-security |
| NIST P-521 | 521 bits | ~256 bits | Top-secret government |

NIST recommended curves P-256, P-384, P-521 in FIPS 186-4. Curve25519 and Ed25519 (Bernstein, 2006) are the modern community standard because of clean math and side-channel resistance by design.

### Why ECC is smaller for the same security

For `n`-bit security, RSA needs keys of size ~`O(n^3)` bits (sub-exponential algorithms); ECC needs keys of size ~`O(n^2)` bits (square-root attacks). Practical comparison from NIST SP 800-57:

| Security (bits) | RSA / DH (bits) | ECC (bits) |
|------------------|-----------------|------------|
| 80 | 1024 | 160 |
| 112 | 2048 | 224 |
| 128 | 3072 | 256 |
| 192 | 7680 | 384 |
| 256 | 15360 | 521 |

A 256-bit ECC key matches RSA-3072 at a fraction of the size and computation cost.

### Comparison of public-key families

| Family | Hard problem | Key size for 128-bit security | Used for |
|--------|--------------|------------------------------|----------|
| RSA | Integer factoring | 3072 bits | Signatures, legacy key transport |
| ElGamal/DSA | DLP in Z_p* | 3072 bits (DSA: 256-bit q) | Signatures, encryption |
| Diffie-Hellman | DLP in Z_p* | 3072 bits | Key agreement |
| ECC | ECDLP | 256 bits | Signatures, key agreement, encryption |
| Lattice (post-quantum) | LWE / SIS | ~1 KB public key | NIST PQC standardization |

## Build It

The lab lives in `code/main.py` (≈220 lines). It exposes:

- `merkle_hellman_keygen(n=8)` — public/private key pair from a superincreasing sequence.
- `merkle_hellman_encrypt(plaintext_bits, pub)` and `merkle_hellman_decrypt(ciphertext, priv)`.
- `low_density_attack(public_seq)` — recover the plaintext from low-density Merkle-Hellman.
- `elgamal_keygen(p, g)`, `elgamal_encrypt(m, pub, p, g)`, `elgamal_decrypt(c1, c2, priv, p)`.
- `baby_step_giant_step(g, y, p, n)` — discrete-log solver for toy examples.
- `ECPoint` class with `add`, `double`, `scalar_mul`, `__eq__`.
- `ec_keygen(curve)`, `ecdsa_sign(message_hash, priv, curve)`, `ecdsa_verify(message_hash, sig, pub, curve)`.
- `ec_demo()` — full ECDH-style key agreement on a tiny curve.

Reproduce the knapsack demo:

```python
from main import merkle_hellman_keygen, merkle_hellman_encrypt, merkle_hellman_decrypt, low_density_attack
pub, priv = merkle_hellman_keygen(n=10)
pt_bits = [1, 0, 1, 1, 0, 0, 1, 0, 1, 0]
c = merkle_hellman_encrypt(pt_bits, pub)
recovered = merkle_hellman_decrypt(c, priv)
broken = low_density_attack(pub)
print("legit decrypt:", recovered)
print("attack result: ", broken)
```

Run ElGamal:

```python
from main import elgamal_keygen, elgamal_encrypt, elgamal_decrypt
p = 0xFFFFFFFEFFFFFC2F  # a near-256-bit prime (small toy)
g = 5
pub, priv = elgamal_keygen(p, g)
c1, c2 = elgamal_encrypt(42, pub, p, g)
print("decrypted:", elgamal_decrypt(c1, c2, priv, p))
```

Run ECC over a small curve:

```python
from main import ec_demo
ec_demo()
```

## Use It

| Function | Real-world counterpart | Notes |
|----------|------------------------|-------|
| `merkle_hellman_*` | Historical / pedagogical | The chapter's "broken" example; do not use for production. |
| `elgamal_*` | OpenSSL `EVP_DH`, GnuPG ElGamal | Production ElGamal uses safe primes and large `p`. |
| `baby_step_giant_step` | Index calculus | Real DLP solvers use index calculus, much faster. |
| `ECPoint` class | OpenSSL `EC_POINT`, libsodium `crypto_scalarmult` | Real libraries use Montgomery ladder for constant-time scalar mul. |
| `ecdsa_sign` / `ecdsa_verify` | OpenSSL `ECDSA_do_sign`, Ed25519 | Real ECDSA uses RFC 6979 deterministic `k` to avoid `k` reuse bugs. |

The lesson's ECC group uses a tiny prime `p = 97` so the math is visible. Real curves use 256-bit primes.

## Ship It

A reusable artifact for cryptography courses lives at `outputs/prompt-beyond-rsa.md`. It includes the knapsack demo, ElGamal encryption example, and an ECC key agreement on a small curve. Reuse it when introducing public-key families.

## Exercises

1. Implement the Lagarias-Odlyzko attack on low-density knapsack and verify it recovers the plaintext in seconds for `n = 30`.
2. Implement a Schnorr signature over `Z_p*` and verify a signature against the public key.
3. Implement baby-step giant-step with O(sqrt(p)) time and memory; solve `5^x ≡ 31 (mod 97)`.
4. Add point compression to `ECPoint` (transmit only `x` and the sign bit of `y`) and decompress on receive.
5. Implement the **double-and-add** algorithm for scalar multiplication with constant-time semantics (no branches on secret bits).
6. Compare key sizes: list the equivalent security levels for RSA-2048, RSA-3072, RSA-15360, P-256, P-384, P-521. Cite NIST SP 800-57.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Knapsack | "Subset-sum problem" | Given weights and a total, find the subset. NP-hard in general; trapdoor via superincreasing sequences. |
| Discrete log | "Given y = g^x, find x" | Hard in cyclic groups; underpins ElGamal, DSA, DH. |
| ElGamal | "1985 El Gamal scheme" | Public-key encryption over Z_p*; randomized ciphertext (2x message size). |
| DSA | "Digital Signature Algorithm" | FIPS 186-4; ElGamal-style signatures over Schnorr groups. |
| ECC | "Elliptic-curve cryptography" | Group law on E: y^2 = x^3 + ax + b mod p; ECDLP is the hard problem. |
| ECDLP | "Elliptic-curve discrete log" | Given P and [k]P, find k. Pollard rho in O(sqrt(n)). |
| ECDSA | "ECC signatures" | DSA over an elliptic curve; signature is (r, s). |
| Ed25519 | "Bernstein curve" | Modern signature curve; 32-byte keys, 64-byte signatures. |
| NIST P-256 | "secp256r1" | The most-deployed ECC curve, used in TLS, FIDO2. |
| Baby-step giant-step | "Discrete-log solver" | O(sqrt(n)) time and memory; used to demonstrate DLP hardness. |

## Further Reading

- Tanenbaum, *Computer Networks*, Chapter 8 (this chapter).
- Merkle, R., and Hellman, M., *Hiding information and signatures in trapdoor knapsacks*, IEEE TIT 24(5), 1978.
- Shamir, A., *A Polynomial-Time Algorithm for Breaking the Basic Merkle-Hellman Cryptosystem*, IEEE TIT 30(5), 1984.
- El Gamal, T., *A Public Key Cryptosystem and a Signature Scheme Based on Discrete Logarithms*, IEEE TIT 31(5), 1985.
- NIST FIPS 186-4 — *Digital Signature Standard (DSS)*.
- NIST SP 800-186 — *Recommendations for Discrete Logarithm-Based Cryptography: Elliptic Curve Domain Parameters*.
- Bernstein, D. J., *Curve25519: new Diffie-Hellman speed records*, PKC 2006.
- Washington, L., *Elliptic Curves: Number Theory and Cryptography* (2008).