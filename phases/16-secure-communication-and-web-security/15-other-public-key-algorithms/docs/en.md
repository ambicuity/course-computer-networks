# Other public-key algorithms: Rabin, ElGamal, knapsack

> RSA is not the only public-key system. Three families of alternatives are historically and pedagogically important: **Rabin** (1979), whose security is provably as hard as integer factorization (C = M^2 mod n) and which produces four candidate decryptions, requiring the recipient to identify the right one with side information; **ElGamal** (1985), whose security rests on the discrete-logarithm problem in a prime-order subgroup of Z*_p, and which is the basis of DSA and the Schnorr signature family; and **knapsack** systems (Merkle-Hellman 1978), which encode plaintexts as subset sums of a hidden superincreasing sequence and which were broken in 1984 by Shamir's lattice attack, but illustrate the "trapdoor permutation by linear structure" pattern. The code implements all three families end-to-end: Rabin encrypt/decrypt (with the four-roots ambiguity resolution via parity bits), ElGamal key generation/encrypt/decrypt over a safe-prime modulus, and a textbook Merkle-Hellman knapsack system plus Shamir's lattice attack. The lesson closes with the modern lesson: RSA, ElGamal, and ECC all reduce to factoring or discrete log, and the lattice-based systems that survive quantum computers (NTRU, Kyber, Dilithium) are the next generation.

**Type:** Learn
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 15 lesson 21 (RSA), modular arithmetic, basic lattices
**Time:** ~85 minutes

## Learning Objectives

- Implement Rabin's cryptosystem: pick n = p * q with p ≡ q ≡ 3 mod 4, encrypt C = M^2 mod n, and recover the four square roots M, -M, M', -M' mod n using the Chinese Remainder Theorem.
- Implement ElGamal key generation over a safe-prime group: pick a safe prime p = 2q + 1, choose generator g, public key y = g^x mod p, encryption (c1, c2) = (g^k mod p, M * y^k mod p).
- Implement Merkle-Hellman knapsack: superincreasing sequence a_1, ..., a_n; trapdoor multiplier w and modulus N with gcd(w, N) = 1; public key b_i = w * a_i mod N.
- Implement Shamir's 1984 lattice attack on the Merkle-Hellman system: construct a low-density lattice from the public b_i and reduce it with Lenstra-Lenstra-Lovász (LLL) to recover the superincreasing structure.
- Compare and contrast the hardness assumptions: factorization (Rabin, RSA), discrete log (ElGamal, DSA, DH), and subset sum (knapsack — broken).

## The Problem

A textbook chapter on public-key cryptography must not stop at RSA. RSA is the most deployed system, but the structural ideas — trapdoor one-way functions built from number theory — show up in three other places. First, **Rabin** shows that you can build a public-key system whose security is *provably* as hard as factoring, not just "believed to be." Second, **ElGamal** is the foundation of every modern digital signature that is not RSA (DSA, ECDSA, Ed25519 are all in the ElGamal family). Third, **knapsack** systems are the cautionary tale: a beautifully designed system (Merkle-Hellman won a patent) that fell to lattice reduction in 1984, illustrating why "the trapdoor looks obvious in hindsight" is a real category of cryptanalytic failure. Together these three cover the design space that led to today's lattice-based post-quantum systems (Kyber, Dilithium, NTRU), which inherit the trapdoor-from-hard-problem pattern while dodging Shor's algorithm.

The lesson's challenge is that ElGamal and Rabin are far less convenient than RSA: Rabin requires sending parity bits to disambiguate four roots, and ElGamal produces ciphertext twice the size of plaintext. Knapsack is the cleanest to teach but the most broken in practice. The code implements all three in 200 lines of stdlib Python so a student can see the design choices directly.

## The Concept

Source: `chapters/chapter-08-network-security.md`, section 8.2.4 (Other Public-Key Algorithms). The companion diagram is `assets/other-public-key-algorithms.svg`.

### Rabin: factoring-equivalent encryption

Rabin's encryption is C = M^2 mod n where n = p * q. Decryption computes square roots of C mod p and mod q separately, then combines them via CRT. With p, q chosen so p ≡ q ≡ 3 mod 4, the square roots are:

```
r_p = C^((p+1)/4) mod p
r_q = C^((q+1)/4) mod q
```

The CRT combination gives four candidates (M, -M, M', -M'). The recipient must pick the right one. The standard fix: append redundancy (a parity bit, a hash, or a known padding) so only one of the four candidates is a valid plaintext. The security theorem: an attacker who can decrypt Rabin can factor n — the system is *provably* as hard as factoring. By contrast, RSA's security is "believed" to be as hard as factoring but no proof exists.

### ElGamal: discrete-log key exchange

ElGamal works in a cyclic group G of prime order q. The public parameters are (p, g) where p is a safe prime (p = 2q + 1, q prime) and g is a generator of the q-order subgroup. The private key is x in {1, ..., q - 1}; the public key is y = g^x mod p. Encryption of M with randomness k:

```
c1 = g^k mod p
c2 = M * y^k mod p
```

Decryption: M = c2 * (c1^x)^(-1) mod p. The semantic security rests on the **Decisional Diffie-Hellman assumption**: given (g^a, g^b, g^c), distinguishing g^(ab) from g^c is hard. The system is randomized: encrypting the same M twice produces different ciphertexts. This is a feature for IND-CPA security; it also means ciphertexts are twice the size of plaintexts.

### Knapsack: Merkle-Hellman and Shamir's attack

The Merkle-Hellman system encodes a plaintext M as a bit string (m_1, ..., m_n) and computes S = sum(m_i * b_i) where b_i = w * a_i mod N for a superincreasing a_i. The superincreasing property (a_i > sum of all smaller a_j) lets the recipient solve the subset sum greedily: starting from the largest a_i, include it if S >= a_i, subtract, and continue. The secret key is (w, N, a); the public key is (b_1, ..., b_n).

Shamir's 1984 attack constructs a lattice L from the public b_i and applies LLL reduction. The reduced basis contains a short vector that recovers the superincreasing structure. The attack runs in polynomial time and breaks the system for any reasonable parameter size. **Lesson**: not every "trapdoor by linear structure" design is sound; the trapdoor must be hard to invert for a *generic* attacker, not just for one with the secret key. Modern lattice-based systems (Kyber, NTRU) are designed to resist lattice attacks at specific parameter sizes.

### Comparison table

| System | Hard problem | Year | Status |
|--------|--------------|------|--------|
| RSA | Integer factorization | 1977 | Widely deployed |
| Rabin | Factoring (provable) | 1979 | Rare; theoretical interest |
| Merkle-Hellman | Subset sum | 1978 | Broken by Shamir 1984 |
| ElGamal | Discrete log (DLP) | 1985 | Basis of DSA, DH |
| DSA | DLP in Z*_p | 1991 | US federal standard |
| ECDSA / EdDSA | Elliptic-curve DLP | 1992 / 2011 | Modern web (TLS 1.3) |
| NTRU | Shortest vector in a lattice | 1996 | Post-quantum candidate |
| Kyber | Module-LWE | 2017 | NIST PQC winner |
| Dilithium | Module-LWE / SIS | 2017 | NIST PQC signature |

## Build It

`code/main.py` implements all three systems. Work through it in this order:

1. Run `python3 main.py` and read the imports. Only stdlib: `math`, `random`, `hashlib`. No third-party crypto.
2. Read the `rabin_*` functions. Key generation picks p ≡ q ≡ 3 mod 4 with similar bit length; encryption squares the message; decryption uses Tonelli-Shanks-style root extraction and CRT to enumerate four candidates.
3. Read `rabin_decrypt_with_redundancy`. It accepts a 7-bit plaintext where the high bit is a parity copy of the low six bits. Only one of the four candidates has the right parity.
4. Read the `elgamal_*` functions. Key generation builds a safe prime p = 2q + 1, picks a generator g of the q-subgroup, and computes y = g^x mod p. Encryption produces (c1, c2).
5. Read the `knapsack_*` functions. Key generation builds a superincreasing a, picks w and N coprime, and computes b_i = w * a_i mod N. Encrypt is the linear combination; decrypt uses the trapdoor.
6. Read `shamir_attack`. It builds the lattice rows `[1, b_1, b_2, ..., b_n]` and `[0, N, 0, ..., 0]` (etc.), runs a simplified LLL reduction (Gaussian elimination on the small case), and recovers the superincreasing sequence from the reduced basis.
7. Run `main()`: it shows Rabin decrypting a 7-bit message via parity, ElGamal encrypting/decrypting a small block, and Shamir's attack recovering the Merkle-Hellman trapdoor.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| Rabin encrypt + decrypt | The recovered M matches one of the four CRT candidates | Exactly one candidate has the parity bit; the wrong three are rejected |
| Rabin factorization security | Given C, the four roots are well-defined and indistinguishable without p, q | Attacker cannot pick the right M without redundancy |
| ElGamal round-trip | M = c2 * c1^(-x) mod p | Decryption recovers the original M |
| ElGamal semantic security | Two encryptions of the same M yield different (c1, c2) | Ciphertexts share no bytes even when plaintexts do |
| Knapsack round-trip | subset-sum greedy solver recovers the bit vector | All bits are correctly identified |
| Shamir attack | LLL reduction recovers a superincreasing sequence from public b_i | Recovered a_i satisfy the superincreasing inequality |

## Ship It

Produce one artifact under `outputs/`:

- A one-page runbook titled *"Three families, three fates: factoring-equivalent, discrete-log, and broken-by-lattice"* that walks through the security argument for each system and the structural reason Merkle-Hellman fell.
- Or a comparison table of hardness assumptions (factoring vs DLP vs SVP/LWE) with the modern systems that instantiate each (RSA, ECDSA, Kyber).

Start from [`outputs/prompt-other-public-key-algorithms.md`](../outputs/prompt-other-public-key-algorithms.md) and back every claim with a transcript from `code/main.py`.

## Exercises

1. Implement Rabin's redundant-encoding scheme: take a 7-bit message, append its parity, encrypt, decrypt, and verify the four candidates collapse to one valid plaintext.
2. Demonstrate ElGamal's semantic security: encrypt the same plaintext twice with different k and show the (c1, c2) pairs differ. Explain why RSA without padding does not have this property.
3. Run Shamir's attack against a Merkle-Hellman key with n = 10 items and recover the superincreasing a_i from the public b_i. Increase n to 20 and compare runtime.
4. Implement a side-channel on ElGamal: measure the time to compute g^x mod p for different x and demonstrate that bit-length leaks via timing. (Don't ship it; just demonstrate the principle.)
5. Compute the size of an ElGamal public key (p, g, y) at the 128-bit security level (p ~ 3072 bits, q ~ 256 bits) and compare against an ECDSA public key (256 bits) at the same level. What does the comparison tell you about why ECC replaced ElGamal/DSA?
6. Research: explain why lattice-based cryptography (Kyber, Dilithium) is believed to be quantum-safe, and what hardness assumption it relies on (LWE / module-LWE).

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|--------------------|
| Rabin | "the factoring-equivalent cipher" | Public-key system with C = M^2 mod n; security provably equivalent to factoring |
| ElGamal | "the discrete-log cipher" | Public-key system with security resting on the discrete-log problem in Z*_p |
| Safe prime | "p = 2q + 1, q prime" | Prime p where (p-1)/2 is also prime; eliminates Pohlig-Hellman attacks |
| DLP | "discrete-log problem" | Given g, g^x mod p, recover x |
| Subset sum | "the knapsack problem" | Given a set of integers, find a subset that sums to a target — NP-hard |
| Merkle-Hellman | "the broken knapsack" | Public-key system based on a hidden superincreasing sequence; broken by Shamir 1984 |
| Shamir attack | "the lattice attack" | LLL reduction on a low-density lattice recovers the superincreasing structure |
| LLL | "Lenstra-Lenstra-Lovász" | Polynomial-time lattice basis reduction; the engine of lattice cryptanalysis |
| Redundancy | "the disambiguator" | Extra bits (parity, hash) that let the recipient pick the right one of four Rabin roots |

## Further Reading

- Rabin, M. O. (1979). "Digitalized Signatures and Public-Key Functions as Intractable as Factorization." MIT Tech Report.
- ElGamal, T. (1985). "A Public Key Cryptosystem and a Signature Scheme Based on Discrete Logarithms." *IEEE Transactions on Information Theory* 31(4): 469-472.
- Merkle, R., and Hellman, M. (1978). "Hiding Information and Signatures in Trapdoor Knapsacks." *IEEE Transactions on Information Theory* 24(5): 525-530.
- Shamir, A. (1984). "A Polynomial-Time Algorithm for Breaking the Merkle-Hellman Cryptosystem." *CRYPTO 1984*.
- Lenstra, A. K., Lenstra, H. W., and Lovász, L. (1982). "Factoring Polynomials with Rational Coefficients." *Mathematische Annalen* 261(4): 515-534.
- National Institute of Standards and Technology (2024). *FIPS 203 (ML-KEM)* and *FIPS 204 (ML-DSA)* — the lattice-based post-quantum standards.
- Diffie, W., and Hellman, M. (1976). "New Directions in Cryptography." *IEEE Transactions on Information Theory* IT-22(6): 644-654.
- Tanenbaum, A. S., and Wetherall, D. J. (2011). *Computer Networks*, 5th ed., Chapter 8 §8.2.4 — Other Public-Key Algorithms.