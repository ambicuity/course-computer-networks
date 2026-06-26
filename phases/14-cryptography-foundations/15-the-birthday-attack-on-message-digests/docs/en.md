# The Birthday Attack on Message Digests

> The birthday paradox says that among only 23 people there is a better-than-even chance two share a birthday. Applied to an n-bit hash, the same logic means an attacker who can evaluate roughly 2^(n/2) digests will find two inputs with the same digest with probability around 0.5. That shrinks SHA-1's 160-bit security claim to about 2^80 work for a collision (broken since Wang et al., 2005) and explains why NIST moved SHA-2 to 256/512 bits and selected Keccak/SHA-3 with a 256-bit default. This lesson ships a probability calculator plus a tiny brute-force toy that finds a 16-bit digest collision in seconds, letting you feel the square-root before you read any more theory.

**Type:** analysis-tool
**Languages:** Python 3 (stdlib only)
**Prerequisites:** Lesson 13 (message digests), Lesson 14 (SHA-1 compression)
**Time:** ~45 minutes

## Learning Objectives

- Compute the approximate birthday-bound collision probability for any n-bit hash using the closed-form `1 - exp(-k(k-1)/(2·2^n))`.
- Distinguish first-preimage resistance (2^n) from collision resistance (2^(n/2)).
- Reproduce the canonical constant: 1.177·2^(n/2) draws give a 50% collision chance.
- Run a tiny brute-force collision finder against a 16-bit digest and watch the actual work approach the predicted bound.
- Map the bound onto SHA-1 (160 bits), SHA-256, and SHA-512 with concrete numerical cost.

## The Problem

When we say SHA-256 is "128-bit secure against collisions" we are citing the birthday bound, not the algorithm's design strength. Newcomers frequently mistake that statement for "you need 2^256 tries to break it". Worse, instructors sometimes skip the proof and present the bound as a fact rather than a derived quantity. Without a calculator and a working toy, students cannot evaluate vendor claims, choose an appropriate digest for their threat model, or judge when MD5/SHA-1 should be retired.

The mathematical core is small. We want `P(collision after k draws from a uniform N-bucket space) ≈ 1 - exp(-k²/2N)`. The educational value comes from turning that formula into a script and then proving it empirically with a 16-bit toy.

## The Concept

### The Birthday Probability

Choose k items from N possible buckets uniformly at random. The probability all k items land in distinct buckets is:

```
P(no collision) = prod_{i=0}^{k-1} (1 - i/N)
                = N! / (N^k · (N-k)!)   for k <= N
                ≈ exp(-k(k-1) / (2N))    for k << N
```

So `P(collision) = 1 - exp(-k(k-1)/(2N))`. Setting this equal to 0.5 and solving for k gives k ≈ 1.177·√N.

| Hash   | Output bits n | Collision bound (50%) | First-preimage (50%) |
|--------|---------------|----------------------|----------------------|
| MD5    | 128           | 2^64.0 ≈ 1.9e19      | 2^128                |
| SHA-1  | 160           | 2^80 ≈ 1.2e24        | 2^160                |
| SHA-256| 256           | 2^128 ≈ 3.4e38       | 2^256                |
| SHA-512| 512           | 2^256                | 2^512                |
| SHA-3-256 | 256        | 2^128                | 2^256                |

### Approximate Bound vs. Exact Bound

The exact `k = ⌈√(2N · ln(1/(1-p)))⌉` formula lets you solve for the k that hits any target probability p. With p=0.5 the constant is 1.1774; with p=0.25 it is 0.8326; with p=0.9 it is 1.5174.

### Attacker Cost Model

| Step | Operation | Work factor |
|------|-----------|-------------|
| 1 | Choose 2^(n/2) random messages | 2^(n/2) evaluations |
| 2 | Insert all digests into a hash table | 2^(n/2) storage |
| 3 | Look for a repeated digest | O(2^(n/2)) expected |

The cost is dominated by step 1. The space requirement is also 2^(n/2) digests — which is why MD5 collisions are easy to store (~32 GB at 2^64) but SHA-256 collisions would need ~10^37 bytes, far beyond current storage.

### Why MD5 and SHA-1 Are Dead

| Algorithm | Status (2026) | Reference |
|-----------|---------------|-----------|
| MD5 | Collisions trivial (~seconds on a laptop); no longer collision-resistant. | Wang et al., 2004; Stevens, 2009. |
| SHA-1 | SHAttered (2017) produced two PDF files with identical SHA-1; chosen-prefix collision feasible for ~$110k (Leurent-Peyrin 2020 "SHA-1 is a Shambles"). | NIST SP 800-131A Rev. 2. |
| SHA-256 | Currently safe; collision bound 2^128. | NIST FIPS 180-4. |
| SHA-3-256 | Safe; different construction (sponge) gives a margin if SHA-2 is ever broken. | NIST FIPS 202. |

### Toy Brute-Force Setup

For a 16-bit digest (N=65536), the birthday bound says ≈ 303 random evaluations should collide at 50%. We can verify this in well under a second on a laptop.

## Build It

The `main.py` ships:

- `collision_probability(n_bits, k)` — exact `1 - prod(1 - i/N)`, returns a float.
- `birthday_bound(n_bits, p=0.5)` — solves for the smallest k with `P >= p`.
- `find_collision(digest_fn, bits=16, max_tries=100_000)` — toy brute-forcer that returns two colliding inputs.

```python
from main import collision_probability, birthday_bound, find_collision

print(collision_probability(160, 2**80))     # -> ~0.39
print(birthday_bound(256, 0.5))              # -> 18446744073709551616  (2**64)
f, s = find_collision(lambda x: hash(bytes([x & 0xff, (x >> 8) & 0xff])), bits=16)
print(f, s)
```

## Use It

| Routine | Purpose | Returns |
|---------|---------|---------|
| `collision_probability(n_bits, k)` | probability of any collision after k random digests | float in [0, 1] |
| `birthday_bound(n_bits, p)` | smallest k achieving probability ≥ p | int |
| `expected_collisions(n_bits, k)` | expected number of colliding pairs E[X] | float |
| `find_collision(digest_fn, bits, max_tries)` | empirical collision finder | tuple of two inputs |
| `toy_digest_16(message)` | toy 16-bit digest for testing | int |

## Ship It

Run the calculator as a CLI: `python3 main.py 160 2**80` prints the collision probability for a 160-bit digest and 2^80 evaluations. Use it to sanity-check security claims in vendor documentation and to size your requirements (e.g., "we need 128-bit collision resistance" → SHA-256 or SHA-3-256). The toy collision finder is a teaching aid only — never use a 16-bit digest for any real authentication or integrity check.

## Exercises

1. Compute `collision_probability(128, 2**32)`. What does this say about an attacker willing to spend 2^32 evaluations against MD5?
2. Use `birthday_bound(256, 0.5)` and confirm it equals 2^64 exactly. Derive why.
3. Run `find_collision` against `toy_digest_16` ten times and record the average number of draws. Does it match `birthday_bound(16, 0.5)` ≈ 303?
4. Extend `find_collision` to return the collision in the form of two byte strings, not just integers. Show the digests side by side.
5. Estimate the cost in dollars of a chosen-prefix SHA-1 collision using the Leurent-Peyrin 2020 result of ~$110k for 2^63.2 SHA-1 evaluations. How does that compare to the per-dollar cost on AWS p4d.24xlarge instances?
6. Implement `expected_collisions(n_bits, k) = k(k-1)/(2N)` and check it against the exact probability for small k. When do they diverge?

## Key Terms

| Term | Definition |
|------|------------|
| Birthday paradox | The observation that ~√N draws from an N-bucket space usually produce a collision. |
| Collision resistance | Property: an attacker cannot find two distinct inputs m, m' with H(m)=H(m') faster than ~2^(n/2). |
| First-preimage resistance | Property: given a target digest d, finding m with H(m)=d costs ~2^n. |
| Birthday bound | The work factor 2^(n/2) at which a generic collision attack succeeds. |
| Chosen-prefix collision | Attack where two distinct prefixes p1, p2 are extended with the same suffix to produce a collision. |
| SHAttered | 2017 collision demonstration against SHA-1 by Stevens et al. |
| Sponge construction | The basis for SHA-3 (Keccak), with different security/cost trade-offs than Merkle-Damgård. |

## Further Reading

- RFC 4270, Attacks on Cryptographic Hashes in Internet Protocols — survey of attack models.
- NIST SP 800-107 Rev. 1, Recommendation for Applications Using Approved Hash Algorithms.
- NIST SP 800-131A Rev. 2, Transitioning the Use of Cryptographic Algorithms.
- Stevens et al., "The First Collision for Full SHA-1" (2017) — SHAttered.
- Leurent, Peyrin, "SHA-1 is a Shambles" (USENIX 2020) — chosen-prefix collision cost.
- Joux, "Multicollisions in Iterated Hash Functions" (CRYPTO 2004).
- van Oorschot, Wiener, "Parallel Collision Search with Cryptanalytic Applications" (1999).