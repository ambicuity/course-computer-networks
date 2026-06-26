# Public-key digital signatures and nonrepudiation

> Public-key cryptography makes Big Brother unnecessary. If Alice has private key D_A and Bob has public key E_B with the RSA property E_B(D_A(P)) = P, Alice signs by sending E_B(D_A(P)) — Bob applies his private key D_B to recover D_A(P), archives it, then applies E_A to verify it decrypts to P. The exhibit in court is D_A(P): Bob cannot forge it because he does not know D_A, and Alice cannot later deny it because only she knows D_A. RSA (Rivest-Shamir-Adleman, 1977) is the de facto industry standard; NIST's 1991 Digital Signature Standard (DSS, FIPS 186) uses El Gamal, which gets its security from discrete-log difficulty in Z_p*. The El Gamal variant was criticized as "too secret, too slow, too new, too insecure" (fixed 512-bit key); DSS later raised keys to 1024 bits. This lesson ships a stdlib-only Python tool (`code/main.py`) that signs and verifies short messages using textbook RSA with small primes, demonstrates the signature property, and quantifies the verify-time trade-off that motivated DSS criticism.

**Type:** Learn
**Languages:** Python (stdlib only)
**Prerequisites:** Phase 14 lessons 01-11, especially 08 (RSA) and 11 (Big Brother signatures)
**Time:** ~75 minutes

## Learning Objectives

- Trace the public-key signing protocol: Alice transmits E_B(D_A(P)); Bob recovers D_A(P) with D_B and verifies with E_A; the exhibit D_A(P) is non-repudiable.
- Explain why D_A(P) is unforgeable (Bob does not know D_A) and why Alice cannot later deny (only Alice knows D_A).
- Discuss the structural weakness of public-key signatures: if Alice's D_A leaks, the argument collapses; if Alice changes her key pair, old exhibits no longer verify under the new E_A.
- Compare RSA signatures with El Gamal / DSS on key size, signing speed, verify speed, and signature size.
- Implement textbook RSA signing/verification for short messages and verify the canonical property E(D(P)) = P holds.

## The Problem

A customer named Alice issues a wire transfer at 14:32 UTC on a Monday. By Wednesday the gold price has dropped sharply and she sues the bank, claiming she never sent the order. The bank's lawyers produce the network log, but Alice's attorney argues "anyone could have forged that packet — maybe a hacker's laptop sent it, not my client." With the symmetric-key Big Brother construction from lesson 11, the bank had a court-proof exhibit K_BB(A, t, P). But BB had to escrow every plaintext message, which means BB reads Alice's wire instructions — a privacy hazard Alice will not tolerate for her other banking. The bank needs the same non-repudiation property without BB's escrow.

The deeper version of the problem is operational: as the bank scales to a million customers, running a single Big Brother whose K_BB signs every transaction becomes a bottleneck, a privacy problem, and a single point of compromise. We need signatures whose verification key can be published without compromising the signing key — which is exactly what asymmetric cryptography gives us.

## The Concept

Source: `chapters/chapter-08-network-security.md`, section 8.4.2 (Public-Key Signatures). The companion diagram is `assets/public-key-digital-signatures-and-nonrepudiation.svg`.

### The RSA property that makes signing work

For public-key signatures to work, the algorithms must satisfy both

- D(E(P)) = P — encryption-then-decryption recovers plaintext (the normal property)
- E(D(P)) = P — decryption-then-encryption also recovers plaintext (the signature property)

RSA has this property because both operations are modular exponentiation mod n = p·q:

- Encrypt: C = M^e mod n
- Decrypt: M = C^d mod n
- Sign: S = M^d mod n
- Verify: M = S^e mod n

So if Alice signs by computing S = D_A(P) and Bob verifies by computing E_A(S) = P, the property holds for free. El Gamal and DSA/DSS are similar but get their security from discrete logs in Z_p* rather than from factoring n.

### The four-step signing-and-verifying flow

Tanenbaum §8.4.2 (Fig. 8-19) walks this flow:

1. Alice computes S = D_A(P) using her private key.
2. Alice transmits (P, S) — she encrypts S with Bob's public key E_B for confidentiality, sending E_B(P, S) on the wire; we ignore confidentiality for the signature-only case.
3. Bob receives (P, S); archives S as Exhibit A.
4. Bob verifies by computing E_A(S) and checking that it equals P.

In the courtroom, Bob produces both P and S. The judge applies E_A to S and confirms it equals P. Since only Alice knows D_A, only Alice could have produced S — Bob cannot have forged it. Case closed.

### Why non-repudiation holds (and when it fails)

Non-repudiation rests on a single assumption: D_A remains Alice's secret. Three ways it can fail:

1. **Key compromise.** If Alice's laptop is stolen and the attacker learns D_A, the attacker can sign messages in Alice's name. Alice's defense ("my laptop was stolen") defeats the bank's exhibit. Alice may or may not be liable depending on jurisdiction (Tanenbaum notes: "Depending on the laws in her state or country, she may or may not be legally liable, especially if she claims not to have discovered the break-in until getting home from work").
2. **Key rotation.** Cryptography best practice is to rotate keys periodically. If Alice changes her key pair, then E_A changes. An old exhibit S = D_A^old(P) verifies under E_A^old but not under E_A^new. The bank, holding old exhibits, "will look pretty stupid at this point" (Tanenbaum §8.4.2).
3. **Algorithm choice.** If the signature algorithm is later broken, old exhibits are no longer verifiable. SHA-1 + RSA-1024 was standard in 2005 and weakened for SHA-1 (collision attack 2017) and RSA-1024 (factorable with effort) by 2020.

### Why RSA is the de facto industry standard

Tanenbaum §8.4.2 lists RSA as "the de facto industry standard" with "many security products" using it. NIST's 1991 DSS standard took a different path:

- **Algorithm.** DSS uses a variant of El Gamal, which gets security from discrete-log difficulty (computing x given g, g^x mod p) rather than integer factoring. Both problems are believed hard for large instances.
- **Key size.** DSS was originally fixed at 512 bits, then extended to 1024. RSA signs and verifies comfortably at 2048-4096 bits.
- **Speed.** RSA verification is fast (small public exponent e = 65537 gives one modular exponentiation). El Gamal verification is faster than RSA, but signing is "10 to 40 times slower than RSA" in early implementations.
- **Signature size.** El Gamal signatures are twice the modulus length; RSA signatures match the modulus length.

The trade-off is roughly: DSS signatures are smaller and verify faster (good for high-volume servers); RSA keys and signatures are more flexible (signing is faster, which matters for low-power clients).

### Public-key signatures without certificates

Section 8.4.2 closes by noting that public-key signatures still need a way for Alice to learn Bob's E_B (and for Bob to learn Alice's E_A) safely. The naive approach — put E_B on your website — fails because Trudy can substitute her own E_T. Lesson 17 introduces certificates and CAs to bind public keys to identities, lesson 18 covers X.509, and lesson 19 walks the PKI chain of trust.

## Build It

`code/main.py` implements textbook RSA signing and verification for short messages. Work through it in this order:

1. Run `python3 main.py` and read the import block: it uses Python's built-in `pow(base, exp, mod)` for modular exponentiation. No third-party deps.
2. Read `generate_keypair`: it picks two random primes p and q using a Miller-Rabin primality check, computes n = p·q, phi(n) = (p-1)(q-1), picks public exponent e (default 65537), and computes private exponent d = e^(-1) mod phi(n). The resulting key is small (128-bit n) for demonstration only — real RSA uses 2048-bit or larger.
3. Read `sign`: takes a message integer m, returns s = m^d mod n. The signature is the same width as n.
4. Read `verify`: takes (m, s) and a public key, returns True if s^e mod n == m.
5. Read `sign_and_verify_demo`: walks the full flow — Alice signs, Bob verifies, then runs the canonical-property check E(D(P)) = P.
6. Read `forgery_resistance`: shows Bob attempting to forge a signature without D_A — he cannot because he would need to compute d from (e, n), which is as hard as factoring n.
7. Read `key_rotation_demonstration`: produces an exhibit under (e_A_old, d_A_old), rotates to (e_A_new, d_A_new), and shows the old signature no longer verifies under the new key.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| Sign and verify a message | sign(m) and verify(m, s) return True | The exhibit s is non-repudiable under the published (e, n) |
| Demonstrate forgery resistance | Attacker tries sign(m') without d | All attempts either fail verification or require solving discrete log / factoring |
| Rotate keys | sign with (e1, d1), verify with (e2, d2) | Verification fails because d1 != d2 |
| Compare RSA vs DSS key sizes | 2048-bit RSA vs 1024-bit DSS for similar security | RSA modulus is twice the security-strength size; DSS can be smaller |
| Benchmark sign vs verify | timeit for 1024-bit, 2048-bit, 4096-bit n | Signing scales with private exponent d (slow for large keys); verify is constant-time when e = 65537 |

## Ship It

Produce one artifact under `outputs/`:

- A one-page runbook titled *"How public-key signatures replace Big Brother"* that walks the four-step RSA flow and identifies the three ways non-repudiation can fail (key compromise, rotation, algorithm break).
- Or a trade-off matrix comparing RSA vs DSS (El Gamal) on key size, signing speed, verification speed, signature size, and security assumption (factoring vs discrete log).

Start from [`outputs/prompt-public-key-digital-signatures-and-nonrepudiation.md`](../outputs/prompt-public-key-digital-signatures-and-nonrepudiation.md) and back every claim with a transcript from `code/main.py`.

## Exercises

1. Trace Alice's wire-transfer scenario step by step. Which message contains the signed exhibit, and what does the bank archive for the courtroom?
2. Tanenbaum notes that if Alice's laptop is stolen, "depending on the laws in her state or country, she may or may not be legally liable." What cryptographic defense can the bank add to shift liability unambiguously?
3. Compare 2048-bit RSA and 1024-bit DSS on security strength. Why does NIST now recommend 2048-bit DSA / 3072-bit RSA for new deployments as of FIPS 186-5 (2023)?
4. Implement a small signing oracle and show that Bob cannot forge a signature on a new message without D_A, even after observing many (m_i, s_i) pairs.
5. Tanenbaum says DSS signatures are "10 to 40 times slower" for verification than RSA in early implementations. Why? (Hint: modular exponentiation cost.)
6. A court exhibit signed in 2010 with SHA-1 + RSA-1024 is offered in 2030. Walk through whether the judge should accept it, considering algorithm deprecation (NIST SP 800-131A) and statutory limits.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Nonrepudiation | "can't deny" | Sender cannot credibly disclaim a message because only the sender's private key D_A could have produced the signature S |
| E(D(P)) = P | "the signature property" | RSA (and other asymmetric algorithms) satisfy encryption-of-decryption equals plaintext - required for signing |
| Exhibit D_A(P) | "proof in court" | The signed message Bob archives; the judge verifies with E_A |
| Key compromise | "laptop stolen" | D_A leaks; thereafter any signature under D_A is forgeable; non-repudiation collapses |
| Key rotation | "rotate keys" | Replacing (E_A, D_A) with a new pair; old exhibits no longer verify under the new E_A |
| DSS | "the NIST standard" | FIPS 186 Digital Signature Standard; based on El Gamal; supports DSA and ECDSA variants |
| RSA | "the de facto standard" | Rivest-Shamir-Adleman 1977; security from integer factoring; used in TLS, S/MIME, PGP, code signing |
| El Gamal | "the alternative" | Taher Elgamal, 1985; security from discrete log mod p; signatures are 2x modulus size |
| ECDSA | "Elliptic Curve DSA" | DSS over elliptic-curve groups; same security as DSA at much smaller key size (256-bit ECDSA ~ 3072-bit RSA) |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, Chapter 8 §8.4.2 - Public-Key Signatures.
- Rivest, R. L., Shamir, A., and Adleman, L. (1978). "A Method for Obtaining Digital Signatures and Public-Key Cryptosystems." *Communications of the ACM* 21(2): 120-126.
- Elgamal, T. (1985). "A Public Key Cryptosystem and a Signature Scheme Based on Discrete Logarithms." *IEEE Transactions on Information Theory* 31(4): 469-472.
- NIST FIPS 186-5 (2023). *Digital Signature Standard (DSS)* - current DSA, ECDSA, RSA-PSS, EdDSA specifications.
- NIST SP 800-131A Rev. 2 (2023). *Transitioning the Use of Cryptographic Algorithms and Key Lengths* - algorithm deprecation timeline.
- ANSI X9.31, ANSI X9.62 - banking-sector signature standards.
- Johnson, D., Menezes, A., and Vanstone, S. (2001). "The Elliptic Curve Digital Signature Algorithm (ECDSA)." *International Journal of Information Security* 1(1): 36-63.