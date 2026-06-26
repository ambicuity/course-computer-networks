# The Birthday Attack

> You might think an m-bit message digest requires 2^m operations to break. The birthday attack (Yuval, 1979, "How to Swindle Rabin") cuts that to roughly 2^(m/2) operations by exploiting the birthday paradox: with 23 people in a room the probability of a shared birthday exceeds 1/2, not the ~180 most students guess. The math: n inputs over k outputs form n(n−1)/2 pairs; when n(n−1)/2 > k a collision is likely, so n > √k suffices. A 64-bit digest breaks at ~2^32 messages, not 2^64. The classic swindle: Ellen, a secretary romantically involved with Dick, writes two letters — one praising Tom for tenure, one damning him — each with 32 bracketed word-choice options ([letter|message], [honest|frank], ...). 2^32 ≈ 4 billion variants per letter. Overnight she hashes both sets; chances are one "good" letter and one "bad" letter share the same 64-bit digest. She sends the good letter to Marilyn for signing; Marilyn signs the digest; Ellen swaps in the bad letter for delivery. The Dean verifies the digest matches — it does — and fires Tom. Defense: use a digest long enough that 2^(m/2) is infeasible. SHA-1 (160-bit) needs 2^80 — at 1 trillion digests/sec that is 32,000 years, or 2 weeks on a million-chip cluster. SHA-256 needs 2^128, far beyond any feasible brute force.

**Type:** Build
**Languages:** Python (stdlib hashlib, math)
**Prerequisites:** Lesson 02 (message digests, SHA-1/SHA-256)
**Time:** ~45 minutes

## Learning Objectives

- State the birthday paradox result (23 people → P>1/2 of shared birthday) and derive n > √k as the collision threshold.
- Explain why a 64-bit digest breaks at 2^32 operations, not 2^64, and why this halves the effective security in bits.
- Walk through Yuval's tenure-letter swindle: good/bad letter pairs, bracketed options, overnight digest matching, signature reuse.
- Compute the work factor for SHA-1 (2^80) and SHA-256 (2^128) and explain why SHA-256 is considered safe against birthday attacks.
- Demonstrate a real birthday collision in `code/main.py` using a truncated 16-bit digest space.

## The Problem

Marilyn, a department chair, signs a recommendation letter by computing its 64-bit message digest and signing that digest with her private key. Her secretary Ellen wants Tom fired (to benefit Ellen's partner Dick). Ellen controls the letter text. If she can produce two letters — one that Marilyn will approve, one that damns Tom — with the *same* digest, Marilyn signs the good one and Ellen delivers the bad one. The Dean verifies the signature against the digest; it matches. Tom is fired. No cryptographic primitive was "broken" — the digest function itself is sound — but its output space was too small to resist the birthday attack.

## The Concept

### The birthday paradox

The question: how many students in a class before P(shared birthday) > 1/2? Intuition says ~180 (half of 365). The real answer is 23. With 23 people there are 23×22/2 = 253 pairs, each with P=1/365 of matching. 253 trials at 1/365 each gives a cumulative probability over 1/2.

### The general collision math

For a mapping with n inputs (people, messages) and k possible outputs (birthdays, digests):

| Condition | Result |
|-----------|--------|
| n(n−1)/2 > k | a collision is likely |
| n > √k | approximate threshold for a match |

For a 64-bit digest, k = 2^64, so √k = 2^32 ≈ 4.3 billion. Generating 2^32 messages and looking for two with the same digest is feasible overnight on modern hardware. This is why 64-bit digests are unsafe for signatures.

### Effective security halving

The birthday attack means an m-bit digest provides only m/2 bits of collision resistance. This is the single most important number to remember:

| Digest | Brute-force (naive) | Birthday attack (real) |
|--------|---------------------|------------------------|
| MD5 (128-bit) | 2^128 | 2^64 — feasible |
| 64-bit digest | 2^64 | 2^32 — trivial overnight |
| SHA-1 (160-bit) | 2^160 | 2^80 — hard but targeted |
| SHA-256 (256-bit) | 2^256 | 2^128 — infeasible |

### Yuval's tenure-letter swindle (the worked example)

Ellen writes letter A (praising Tom) and letter B (damning Tom), each with 32 bracketed word-choice options:

```
This [letter|message] is to give my [honest|frank] opinion of Prof. Tom
Wilson, who is [a candidate|up] for tenure [now|this year]. ...
```

Each bracketed option doubles the variant count. 32 options → 2^32 variants per letter. Ellen programs her computer to:

1. Generate all 2^32 variants of letter A; hash each; store (digest → variant).
2. Generate all 2^32 variants of letter B; hash each; check if any digest is already in the table.
3. With ~2^32 × 2^32 = 2^64 pairs across the two sets, and k = 2^64 possible digests, a collision is expected (n(n−1)/2 ≈ k).

She finds matching digests d. Letter A_variant and B_variant both hash to d. She sends A_variant to Marilyn for approval. Marilyn signs d = MD(A_variant). Ellen delivers B_variant to the Dean with Marilyn's signature on d. The Dean computes MD(B_variant) = d, verifies the signature, and fires Tom.

### Why SHA-1 is (barely) safe, SHA-256 is safe

SHA-1 produces 160-bit digests. Birthday attack needs 2^80 operations. At 1 trillion digests/sec, that is 2^80 / 2^40 ≈ 2^40 seconds ≈ 32,000 years. A million-chip cluster cuts that to ~2 weeks — which is why SHA-1 is being deprecated. SHA-256 needs 2^128 operations: at 2^40 digests/sec that is 2^88 seconds ≈ 10^19 years. Safe.

### The defense: digest length

| Defense | Mechanism |
|---------|----------|
| Use SHA-256 (256-bit) | Birthday attack needs 2^128 — infeasible |
| Avoid MD5 (128-bit) | Collisions already demonstrated practically |
| Avoid 64-bit digests | 2^32 overnight — trivial |
| Sign digests, not raw messages | Limits attacker to digest-space search |

`code/main.py` demonstrates a real birthday collision on a *truncated* 16-bit digest space (k = 2^16 = 65536, threshold √k = 256 messages) so you can see the attack complete in milliseconds rather than waiting 32,000 years.

## Build It

1. Run `code/main.py` — it simulates Yuval's attack on a 16-bit digest space and prints the collision count vs the theoretical √k threshold.
2. Observe how few messages are needed to find a collision (typically 200–400 for k=65536).
3. The SVG in `assets/the-birthday-attack.svg` shows the paradox curve and the tenure-letter swindle flow.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Estimate collision threshold | Compute √k for a given digest size | n > √k matches observed collision point |
| Run birthday attack on 16-bit space | Generate random messages, hash, find first collision | Collision found in ~300 messages (not 65536) |
| Compare digest security | MD5 vs SHA-1 vs SHA-256 effective bits | 64 / 80 / 128 bits of collision resistance |
| Identify vulnerable system | Any system signing 64-bit digests | Flag for immediate upgrade to SHA-256 |

## Ship It

Create one artifact under `outputs/`:

- A birthday-paradox probability table for digest sizes 64/128/160/256
- A collision-finder script (extracted from main.py) parameterized by digest bit-length
- A one-page risk brief: "Why our legacy 64-bit MAC system must move to HMAC-SHA-256"

Start with [`outputs/prompt-the-birthday-attack.md`](../outputs/prompt-the-birthday-attack.md).

## Exercises

1. How many messages must you generate to find a collision in a 128-bit digest (MD5)? Why is MD5 considered broken even though 2^64 is "large"?
2. Ellen's tenure letter has 32 bracketed options → 2^32 variants. If the digest is 64-bit, what is the probability of a collision between the good and bad sets? Relate n(n−1)/2 to k.
3. Your system uses HMAC-SHA-1 (160-bit). What is the birthday-attack work factor? Is it safe for a 10-year horizon? For a 50-year horizon?
4. Modify `code/main.py` to use a 24-bit truncated digest. How many messages does the collision take? Does it match √(2^24)?
5. A colleague says "MD5 is fine for integrity checking, just not for signatures." Explain why the birthday attack makes this false — Trudy can precompute two colliding documents and swap them.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| Birthday paradox | "23 people share a birthday" | P(collision) > 1/2 at n > √k, not n > k/2 |
| Birthday attack | "the √ trick" | Finding any collision in ~2^(m/2) work for an m-bit digest |
| Collision | "two messages same hash" | MD(P) = MD(P') with P ≠ P'; breaks signatures |
| Yuval's swindle | "the tenure letter trick" | Good/bad letter pairs with bracketed options; sign good, deliver bad |
| Effective security | "real bits of security" | m-bit digest gives m/2 bits of collision resistance |
| 2^(m/2) | "birthday bound" | Work factor to find a collision in an m-bit hash |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), Chapter 8, Section 8.4.4
- Yuval (1979), "How to Swindle Rabin" — the original birthday-attack paper
- RFC 3174 — SHA-1 (and its deprecation rationale)
- NIST SP 800-107 — Recommendation for Applications Using Approved Hash Algorithms
- Stevens et al. (2017), "The first collision for full SHA-1" — practical SHA-1 collision