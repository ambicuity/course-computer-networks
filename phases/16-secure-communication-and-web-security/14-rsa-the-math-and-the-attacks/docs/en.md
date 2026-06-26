# RSA: the math and the attacks

> RSA (Rivest, Shamir, Adleman, 1977) is the workhorse public-key cryptosystem on the modern Internet. Its security rests on the supposed hardness of factoring the product of two large primes: if n = p * q with p, q each ~1024 bits, then no known algorithm can recover p and q in fewer than ~2^112 operations on classical hardware. The lesson covers the four-step RSA recipe (key generation, public encryption, private decryption, signing) and the three classical mathematical attacks that recover the private key d from (n, e) when the implementation gets the parameter choice wrong: **Wiener's continued-fraction attack** (1990), which exploits a small d (d < n^0.25 / 3); **Fermat's factorization**, which recovers p and q in milliseconds when p and q are close; and **Pollard's rho** for moderate-size factors. The code is a self-contained RSA implementation (textbook, 1024-bit) plus the three attack demos. The lesson closes with the practical mitigations: enforce d >= n^0.5 (or randomize it via CRT), ensure |p - q| > n^0.5, pad plaintexts with OAEP, and use a 2048+ bit modulus.

**Type:** Learn
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 15 lesson 21 (RSA basics), modular arithmetic
**Time:** ~80 minutes

## Learning Objectives

- Implement textbook RSA end-to-end: Miller-Rabin prime generation, key pair derivation (n = p*q, e = 65537, d = e^-1 mod phi(n)), encryption C = M^e mod n, and decryption M = C^d mod n.
- Compute the four correctness invariants: d * e ≡ 1 mod phi(n), gcd(e, phi(n)) = 1, decryption inverts encryption, and signatures verify.
- Implement Wiener's continued-fraction attack and demonstrate that it recovers d from (n, e) in milliseconds when d < n^0.25 / 3.
- Implement Fermat's factorization and demonstrate it runs in milliseconds on primes p and q with |p - q| < n^0.25.
- Implement Pollard's rho cycle-finding factorization and demonstrate it factors a 40-digit semiprime with realistic runtime.

## The Problem

A startup builds an SSH-like service that lets employees log in from home. The system uses RSA-2048 because that is what the consultant said was "safe." But the consultant, under deadline pressure, generated the RSA keys by repeatedly calling `OpenSSL` with a random seed, and the seed turned out to be only 32 bits of entropy. Two of the deployed keys (one for the CEO, one for the CFO) share a prime factor with each other — a birth-day-style collision in the random seed — and any attacker who notices the GCD is one gets the other for free. That is a *real* RSA failure mode that has shown up in production (the 2012 "Debian OpenSSL weak key" incident, and the 2017 "ROCA" ROCA vulnerability in Infineon TPMs).

The deeper point: RSA's security rests on three structural assumptions, all of which can be broken if the implementation is sloppy. (1) n is the product of two independently random primes; if the primes are close (Fermat) or share structure (shared factor, ROCA), factoring becomes easy. (2) e and d are not too small relative to n; if d is short, Wiener's continued-fraction attack recovers d in milliseconds from (n, e). (3) The implementation does not leak side-channel information; Kocher's 1996 timing attack and its variants recover d from observation of decryption latency. The lesson builds the first two attacks; side channels are in lesson 15.

## The Concept

Source: `chapters/chapter-08-network-security.md`, section 8.2.3 (RSA). The companion diagram is `assets/rsa-math-and-attacks.svg`.

### The RSA recipe

Key generation is a four-step process:

| Step | Operation | Why |
|------|-----------|-----|
| 1 | Pick random primes p, q with p != q | n = p*q must be hard to factor |
| 2 | Compute n = p * q and phi(n) = (p-1)(q-1) | phi(n) is the order of Z*_n |
| 3 | Pick e coprime to phi(n); default e = 65537 | Encrypt without inverting |
| 4 | Compute d = e^-1 mod phi(n) | Decrypt without factoring |

Encryption of a message M (interpreted as an integer 0 <= M < n) is C = M^e mod n. Decryption is M = C^d mod n. The correctness argument: M^(d*e) ≡ M mod n because d*e ≡ 1 mod phi(n), and by Euler's theorem a^phi(n) ≡ 1 mod n for gcd(a, n) = 1. Signatures flip the roles: S = M^d mod n with the private key; verification recovers M = S^e mod n with the public key.

### Wiener attack: continued fractions crack small d

When d is small (specifically d < n^0.25 / 3), Boneh's 1999 theorem shows that the convergents of the continued-fraction expansion of e/n include k/d, where k is some integer. The attacker:

1. Computes the continued-fraction expansion of e/n.
2. For each convergent a/b, tests whether b is a valid d (i.e., (e * b - 1) is divisible by some phi(n) candidate, or equivalently, n + 1 - e * b is a small multiple of phi(n)).
3. The correct convergent has denominator equal to d, and verification succeeds.

The attack runs in O(log n) operations — milliseconds for 1024-bit n. The fix is to enforce d >= n^0.5, or randomize it via the Chinese Remainder Theorem (CRT) so that the *effective* exponent is large even if d is moderate.

### Fermat's factorization: close primes die fast

If |p - q| is small relative to sqrt(n), then n = p*q = ((p+q)/2)^2 - ((p-q)/2)^2 is close to a perfect square. Fermat's method starts with a = ceil(sqrt(n)) and iterates b^2 = a^2 - n, testing whether a^2 - n is a perfect square. If it is, p = a + b and q = a - b. For primes within 2^20 of each other on a 1024-bit modulus, the method recovers p and q in milliseconds. The fix is to ensure |p - q| > 2^64 (any bound well above the size of any future factoring improvement).

### Pollard's rho: cycle finding beats trial division

Pollard's rho algorithm finds a factor p of n in O(p^0.5) operations by random walk: pick x_0, set x_{i+1} = (x_i^2 + 1) mod n, and use Floyd's cycle-finding algorithm to detect a collision. When x_i ≡ x_j mod p (but x_i != x_j mod n), gcd(x_i - x_j, n) reveals p. The expected runtime is sqrt(p) which is ~2^20 for a 20-digit factor — fast. Modern factoring (quadratic sieve, number field sieve) is asymptotically faster (sub-exponential) but Pollard's rho remains a useful primitive for small factors and for the shared-factor attack on the startup scenario above.

### What the attacks do not break

A well-parameterized RSA-2048 with random p, q (no shared factors, |p - q| > 2^64), e = 65537, and OAEP-padded plaintext is still considered secure on classical hardware as of 2026. The lesson's attacks all assume a structural flaw — small d, close primes, or shared factors. Cryptanalytic progress (lattice attacks on weak keys, ROCA-style implementation flaws) keeps finding structural flaws; the lesson is therefore not a one-time exercise but a recurring audit: any new RSA key generation pipeline should be checked against all three attacks.

## Build It

`code/main.py` is a self-contained RSA + attacks simulator. Work through it in this order:

1. Run `python3 main.py` and read the imports. Only stdlib: `math`, `random`, `hashlib`. No third-party crypto.
2. Read `MillerRabin.is_probably_prime`. The implementation accepts a witness count parameter; 8 witnesses is enough for cryptographic strength up to ~2048-bit numbers (per Damgård, Landrock, Pomerance 1993).
3. Read `generate_keypair`. It picks two primes with `bits//2` bits each, computes phi(n), and uses the extended Euclidean algorithm for d = e^-1 mod phi(n).
4. Read `encrypt` and `decrypt`. Both use Python's built-in `pow(c, e, n)` for fast modular exponentiation (which is constant-time enough for educational use).
5. Read `wiener_attack(n, e)`. It builds the continued-fraction expansion of e/n, walks the convergents, and verifies each candidate d by checking `pow(2, e*d, n) == 2`.
6. Read `fermat_factor(n)`. It starts at `ceil(sqrt(n))` and increments until it finds a perfect square.
7. Read `pollard_rho(n)`. It runs Floyd's cycle-finding algorithm with `f(x) = x^2 + 1` and `gcd` at every step.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| Verify key generation | gcd(e, phi(n)) = 1 and (e * d) mod phi(n) = 1 | Both invariants hold; `pow(2, e*d, n) == 2` |
| Encrypt + decrypt round-trip | `decrypt(encrypt(M)) == M` for random M | Equality holds for all tested M |
| Wiener attack succeeds | Given n, e with d < n^0.25 / 3, recovered d matches | Attack runs in < 1 ms on a 1024-bit modulus |
| Fermat attack succeeds | Given n with |p - q| < 2^20, recovered p, q are correct | Attack runs in < 1 ms |
| Pollard rho attack succeeds | Given n = p * q with p ~ 2^40, recovered p is correct | Attack runs in seconds |

## Ship It

Produce one artifact under `outputs/`:

- A one-page runbook titled *"How to check that your RSA keys are not Wiener-able, Fermat-able, or Pollard-able"* that runs all three attacks against a candidate key and reports pass/fail.
- Or a vulnerability report: take a 1024-bit key with d = 257, show Wiener's attack recovers d, and propose the fix (enforce d >= n^0.5 via CRT randomization).

Start from [`outputs/prompt-rsa-the-math-and-the-attacks.md`](../outputs/prompt-rsa-the-math-and-the-attacks.md) and back every claim with a transcript from `code/main.py`.

## Exercises

1. Run Wiener's attack against a key generated with d forced to be small (e.g., regenerate d until d < 2^200 for a 1024-bit n). Show that the attack succeeds in milliseconds.
2. Generate two primes p and q with |p - q| < 2^20 on a 1024-bit modulus. Run Fermat's factorization and report the iteration count.
3. Take a 40-digit semiprime and run Pollard's rho. Compare the runtime against trial division up to sqrt(n) and explain why Pollard is faster (heuristically).
4. Generate two RSA keys with a shared prime factor (draw p1 once, generate q1 and q2 independently, build n1 = p1*q1 and n2 = p1*q2). Show that gcd(n1, n2) reveals p1 instantly.
5. Use the **Miller-Rabin** primality test to estimate the probability of a 1024-bit composite passing the test with k = 8 witnesses. Why is k = 8 enough for RSA key generation but not for cryptographic protocols?
6. Compare the runtime of Wiener's attack, Fermat's factorization, and Pollard's rho on a 2048-bit modulus with parameters chosen to defeat each attack. What does the comparison tell you about the size of the constants in each algorithm?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|--------------------|
| RSA | "the public-key cipher" | First practical public-key cryptosystem; security rests on hardness of factoring n = p * q |
| Modulus n | "the public composite" | The product of two large primes p and q |
| Public exponent e | "the encryption exponent" | Typically 65537; chosen to be coprime to phi(n) |
| Private exponent d | "the decryption exponent" | d = e^-1 mod phi(n); d * e ≡ 1 mod phi(n) |
| Wiener attack | "the small-d attack" | Continued-fraction attack that recovers d when d < n^0.25 / 3 |
| Fermat factorization | "the close-primes attack" | Recovers p, q when |p - q| is small by searching for a near-square |
| Pollard's rho | "the cycle-finding attack" | Factors n in O(p^0.5) operations using Floyd's cycle detection |
| Continued fraction | "the convergent expansion" | Sequence of rational approximations; Wiener's attack walks convergents of e/n |
| CRT | "Chinese Remainder Theorem" | Decryption shortcut using d mod (p-1) and d mod (q-1); also a defense against small-d attacks |

## Further Reading

- Rivest, R. L., Shamir, A., and Adleman, L. (1978). "A Method for Obtaining Digital Signatures and Public-Key Cryptosystems." *Communications of the ACM* 21(2): 120-126.
- Wiener, M. J. (1990). "Cryptanalysis of Short RSA Secret Exponents." *IEEE Transactions on Information Theory* 36(3): 553-558.
- Boneh, D. (1999). "Twenty Years of Attacks on the RSA Cryptosystem." *Notices of the AMS* 46(2): 203-213.
- Pollard, J. M. (1975). "A Monte Carlo Method for Factorization." *BIT Numerical Mathematics* 15(3): 331-334.
- Fermat, P. de (1643). *Oeuvres* — letter to Mersenne describing the factorization method.
- Heninger, N., and Shacham, H. (2009). "Reconstructing RSA Private Keys from Random Key Bits." *CRYPTO 2009*.
- Nemec, M., et al. (2017). "The Return of Coppersmith's Attack: Practical Factorization of Widely Used RSA Moduli." *ACM CCS 2017* (the ROCA paper).
- Tanenbaum, A. S., and Wetherall, D. J. (2011). *Computer Networks*, 5th ed., Chapter 8 §8.2.3 — RSA.