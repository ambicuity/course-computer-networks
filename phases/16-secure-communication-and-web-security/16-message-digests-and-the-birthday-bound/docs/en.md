# Message digests and the birthday bound

> A cryptographic hash function maps an arbitrary-length message to a fixed-length digest with three security properties: preimage resistance (given a digest D, hard to find M with hash(M) = D), second-preimage resistance (given M, hard to find M' != M with hash(M) = hash(M')), and collision resistance (hard to find any M, M' with hash(M) = hash(M')). The first two give 2^n work for an n-bit digest (exhaustive search). Collision resistance gives only **2^(n/2)** work — the birthday bound — because of the birthday paradox: with 2^(n/2) random samples, the probability of any two colliding reaches ~50%. The lesson covers the MD/SHA family (MD5, SHA-1, SHA-256, SHA-3/Keccak), the structural design of Merkle-Damgård hashes, the SHA-3 sponge construction that abandons Merkle-Damgård, and a birthday-bound collision-finding experiment that finds SHA-256 collisions in ~2^128 operations on a 32-bit-truncated digest. The lesson closes with the practical implications: collision resistance requires ~2n-bit digests for n-bit security; SHA-1 is broken (Google's SHAttered, 2017); MD5 should not be used; SHA-256 is the current workhorse; SHA-3 (Keccak) is the sponge-based alternative standardized in FIPS 202.

**Type:** Learn
**Languages:** Python (stdlib hashlib + birthday-attack simulator)
**Prerequisites:** Probability, basic Python
**Time:** ~75 minutes

## Learning Objectives

- Compute SHA-256 and SHA-3 (Keccak) digests of arbitrary messages with stdlib `hashlib` and identify the output length and block size for each NIST standard.
- Demonstrate the birthday paradox: estimate the collision probability after sampling k items from an n-bit space and show it reaches ~50% at k ≈ 1.177 * sqrt(n).
- Run a birthday-bound collision-finder on a truncated digest (e.g., SHA-256 truncated to 32 bits) and measure the runtime scaling.
- Explain the Merkle-Damgård construction (length-padded iterative compression function) and the length-extension attack that makes SHA-256 unsuitable for naive MAC use.
- Explain the SHA-3 sponge construction (Keccak) and why it is structurally immune to length-extension attacks.

## The Problem

A software-vendor publishes an update file `update.bin` and its SHA-256 digest on the website so customers can verify they got the right bits. Mallory wants to distribute a malicious update that customers will accept as authentic. She needs a file `evil.bin` whose SHA-256 digest matches `update.bin`'s. The naive approach: try random files until one matches. SHA-256 produces 2^256 possible digests, so this requires ~2^256 attempts. At a billion hashes per second on a GPU farm, that is longer than the age of the universe.

But Mallory has a second path: she does not need to match a *specific* digest; she just needs any two files with the same digest. She can iterate: try a candidate, store (digest, file) in a table, and stop when she finds a candidate whose digest is already in the table. By the birthday paradox, the table only needs ~2^128 entries before a collision becomes likely. That is still infeasible for full SHA-256, but the same attack against MD5's 128-bit digest requires only 2^64 attempts (still too many in 2026, but feasible for state actors) and against SHA-1's 160-bit digest requires 2^80 attempts (Google's SHAttered used a structural attack in 2^63 to find the first SHA-1 collision in 2017). The lesson's exercise shows the attack on a 32-bit truncation of SHA-256, where 2^16 attempts is enough — fast enough to run in the demo.

The deeper point: collision resistance and preimage resistance are *different* security properties, and the second is much stronger than the first. Anyone who treats "hashing" as a single primitive is implicitly assuming 2n-bit security when they get only n-bit collision security. The lesson separates the three properties and shows how to compute the security level for each.

## The Concept

Source: `chapters/chapter-08-network-security.md`, section 8.3 (Message Digests). The companion diagram is `assets/message-digests-birthday-bound.svg`.

### The three security properties

A hash function H is judged against three increasingly demanding properties:

| Property | Adversary goal | Work for an n-bit digest |
|----------|----------------|--------------------------|
| Preimage | Given D, find M with H(M) = D | ~2^n |
| Second preimage | Given M, find M' != M with H(M') = H(M) | ~2^n |
| Collision | Find any M, M' with H(M) = H(M') | ~2^(n/2) (birthday bound) |

The preimage goal is hard because the attacker must match a specific target; second-preimage is the same with a chosen input. Collision-finding is easier by a square-root factor because of the birthday paradox: any two of the attacker's samples might collide, and the attacker chooses both.

### The birthday paradox explained

Throw k balls uniformly into N bins. The probability that at least one bin holds two or more balls reaches ~50% at k ≈ 1.177 * sqrt(N). For a 256-bit hash, N = 2^256, and sqrt(N) = 2^128. So an attacker who can compute 2^128 hashes against a 256-bit digest and store them in a table will find a collision with probability ~50%. SHA-256's collision resistance is therefore 128-bit, not 256-bit — half of the apparent digest length.

### Merkle-Damgård construction

SHA-1, SHA-256, and the SHA-2 family use Merkle-Damgård: pad the message to a multiple of the block size, split into blocks M_1, M_2, ..., M_t, and iterate H_i = f(H_{i-1}, M_i) starting from a fixed IV. The final H_t is the digest. The construction has a critical weakness: if you know hash(M) and len(M), you can compute hash(M || padding || X) without knowing M — a *length-extension attack*. The classic exploit: a server that uses SHA-256(secret || message) as a MAC is vulnerable, because the attacker can extend the message and recompute the digest from the known state. HMAC (lesson 17) wraps the hash in a two-key structure that defeats length extension.

### SHA-3 sponge (Keccak)

SHA-3, standardized in FIPS 202, uses an entirely different structure: a sponge. The state is b + c bits, where b is the "rate" (data absorbed per round) and c is the "capacity" (security parameter). The function alternates absorbing r-bit blocks into the rate portion and applying the Keccak-f permutation to the full state. Squeezing produces n output bits. SHA3-256 uses b = 1088 bits, c = 512 bits, output 256 bits. The sponge is structurally immune to length extension because the capacity bits are never exposed to the input.

### The MD5 / SHA-1 / SHA-256 status

| Algorithm | Digest size | Block size | Status (2026) |
|-----------|-------------|------------|---------------|
| MD5 | 128 bits | 512 bits | Broken (collision in seconds; do not use) |
| SHA-1 | 160 bits | 512 bits | Broken (SHAttered, 2017); collision in 2^63 |
| SHA-256 | 256 bits | 512 bits | Secure; quantum-reduced to 128-bit preimage |
| SHA-384 | 384 bits | 1024 bits | Secure |
| SHA-512 | 512 bits | 1024 bits | Secure |
| SHA3-256 | 256 bits | 1088 bits (rate 576) | Secure; structural length-extension immunity |
| BLAKE3 | 256 bits | 64-byte chunks | Modern; very fast; tree structure |

## Build It

`code/main.py` is a stdlib-only digest + birthday-attack simulator. Work through it in this order:

1. Run `python3 main.py` and read the imports. Only stdlib: `hashlib`, `os`, `random`. No third-party crypto.
2. Read `digest_bytes`. It picks `hashlib.new(algo)` and returns the digest of a message. The `available_algorithms()` test confirms SHA-256 and SHA3-256 are both present.
3. Read `merkle_damgard_length_extension_demo`. It shows that given hash(secret || M) and len(M), an attacker can compute hash(secret || M || padding || suffix) without knowing the secret. This is the classic length-extension attack; HMAC (next lesson) wraps the hash to defeat it.
4. Read `truncated_digest_attack`. It builds a dictionary {digest: original_file} over random file content, truncated to n bits, and stops when a collision appears. The expected work scales as 2^(n/2).
5. Read `birthday_probability`. It computes the analytic probability of collision after k samples into an n-bit space using the approximation 1 - exp(-k*(k-1)/(2*N)) where N = 2^n.
6. Run `main()`: it shows the digest demo, the length-extension demo, and a 16-bit truncated birthday attack (~65536 attempts → collision expected in ~256 attempts).

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|--------------------|
| Digest comparison | hash(M) == hash(M') iff M == M' (probabilistically) | SHA-256 output is 32 bytes; SHA3-256 output is also 32 bytes (different structure) |
| Length-extension | Given H(secret \|\| M) and len(M), can compute H(secret \|\| M \|\| pad \|\| X) | The demo produces the attacker-controlled extended digest |
| Birthday bound | Collision probability after k samples into N = 2^n | At k ≈ 1.177 * sqrt(N), probability crosses 50% |
| Truncated attack runtime | Truncating SHA-256 to 16 bits, expected work ≈ 2^8 = 256 | Demo finds a collision in < 1 second |
| Security level | 256-bit digest gives ~128-bit collision security | The lesson names the security level for each NIST standard |

## Ship It

Produce one artifact under `outputs/`:

- A one-page runbook titled *"Why your SHA-256 collision security is 128-bit, not 256-bit"* that walks through the birthday bound, computes the expected work to find a collision for a given digest size, and lists the NIST status of MD5, SHA-1, SHA-256, SHA-512, and SHA-3.
- Or a vulnerability report: a hypothetical update-signing scheme using SHA-256(secret || update) instead of HMAC-SHA-256, and a length-extension attack that produces a forged valid signature.

Start from [`outputs/prompt-message-digests-and-the-birthday-bound.md`](../outputs/prompt-message-digests-and-the-birthday-bound.md) and back every claim with a transcript from `code/main.py`.

## Exercises

1. Implement a birthday-bound attack on a 24-bit truncated SHA-256. Report the expected number of attempts and the wall-clock runtime.
2. Compute the collision probability after k = 2^16, 2^20, 2^24, 2^32 samples into a 32-bit space. At what k does the probability cross 1%, 50%, 99%?
3. Demonstrate the length-extension attack on SHA-256 against a fake server that signs `SHA-256(secret || message)` as its MAC. Show how an attacker produces a forged message and signature without knowing the secret.
4. Hash the same message with SHA-256 and SHA3-256 and show the digests differ. Hash 1 MB of zeroes with both and report the wall-clock runtime on your machine. Which is faster, and why?
5. Take the SHAttered PDF (the 2017 SHA-1 collision) and verify that the two files have the same SHA-1 digest. Why is this collision "free" (in the sense of being a chosen-prefix attack) rather than an identical-prefix attack?
6. Compare the security levels of MD5, SHA-1, SHA-256, and SHA-3 against (a) brute-force preimage, (b) birthday-bound collision, and (c) Grover's quantum search. Show that quantum search halves the preimage security but does not halve the collision security.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|--------------------|
| Hash function | "the fingerprint" | Maps arbitrary-length input to a fixed-length digest |
| Preimage | "given D, find M with hash(M) = D" | First preimage property; 2^n work for an n-bit digest |
| Second preimage | "given M, find M' with hash(M') = hash(M)" | Harder to compute than collision |
| Collision | "any two M, M' with the same digest" | 2^(n/2) work (birthday bound) |
| Birthday paradox | "sqrt(N) before collision" | Probability of any two of k samples colliding reaches 50% at k ≈ 1.177 * sqrt(N) |
| Merkle-Damgård | "the iterative compression" | Length-padded block-by-block hash construction; vulnerable to length extension |
| Length extension | "extend a known hash" | Given H(secret \|\| M) and len(M), compute H(secret \|\| M \|\| pad \|\| X) |
| SHA-3 sponge | "the Keccak construction" | Rate-capacity structure; structurally immune to length extension |
| SHA-256 | "the workhorse" | 256-bit Merkle-Damgård digest; 128-bit collision security |

## Further Reading

- NIST (2015). *Secure Hash Standard (SHS)*. FIPS PUB 180-4.
- NIST (2015). *SHA-3 Standard: Permutation-Based Hash and Extendable-Output Functions*. FIPS PUB 202.
- Stevens, M., et al. (2017). "SHAttered: The first collision for full SHA-1." Google Research / CWI Amsterdam.
- Wang, X., Yin, Y. L., and Yu, H. (2005). "Finding Collisions in the Full SHA-1." *CRYPTO 2005*.
- Bertoni, G., Daemen, J., Peeters, M., and Van Assche, G. (2008). "Keccak sponge function family." NIST submission.
- Damgård, I. (1989). "A Design Principle for Hash Functions." *CRYPTO 1989*.
- Merkle, R. (1989). "One Way Hash Functions and DES." *CRYPTO 1989*.
- Aumasson, J.-P. (2017). *Serious Cryptography*. No Starch Press. Chapter 5.
- Tanenbaum, A. S., and Wetherall, D. J. (2011). *Computer Networks*, 5th ed., Chapter 8 §8.3 — Message Digests.