# MD5 Collision Lab: Chosen-Prefix Collisions and the Tenure-Letter Swindle

> MD5 was published by Rivest in RFC 1321 (1992) as a 128-bit hash function and broken by Wang et al. in 2004. Today, generating an MD5 collision takes seconds on a laptop, and the chosen-prefix attack of Stevens (2009, HashClash) builds two documents that differ only inside a chosen suffix — exactly the structure of the famous "tenure-letter" attack where two letters with identical MD5 give opposite recommendations. We implement a teaching-grade chosen-prefix collision builder using a tiny differential walk over a 4-round reduced MD5 so the structure of the attack is visible, plus we wire up `hashlib.md5` as the reference oracle. Lesson scope is pedagogical; do not use MD5 in production.

**Type:** lab
**Languages:** Python 3 (stdlib only)
**Prerequisites:** Lesson 13 (message digests), Lesson 14 (SHA-1 compression), Lesson 15 (birthday bound)
**Time:** ~75 minutes

## Learning Objectives

- Implement the MD5 compression step using the four auxiliary functions F, G, H, I, the 64-entry permutation table K[i] (RFC 1321 §3.3), and the per-round shift amounts s[i].
- Distinguish an identical-prefix collision (Wang's attack on full MD5) from a chosen-prefix collision (Stevens' HashClash, ~2^50 operations).
- Run a brute-force identical-prefix attack against a reduced 4-round MD5 with the difference pattern (0,0,...,0,1,0,-1,0,...) and confirm a collision is found in seconds.
- Build the "tenure-letter swindle" — two PDFs (or two text blocks) with identical MD5 but opposite meaning — by appending a binary collision block to each prefix.
- Wire up `hashlib.md5` as the oracle and compare full MD5 against the reduced round version.

## The Problem

Once a digest is broken, the question is not "is it broken" but "what does a broken digest actually let an attacker do?" MD5 is the case study: identical-prefix collisions appear in ~2^24 work on full MD5, chosen-prefix collisions in ~2^39, and the famous 2008 PS3 firmware signing-key attack used a chosen-prefix collision to forge a valid code-signing certificate. The tenure-letter thought experiment (Marc Stevens, 2009) shows the same idea in a benign form: two recommendation letters, one supportive, one damning, with the same MD5, so the recruiter's integrity check passes for either.

The pedagogical challenge is showing how the differential walk narrows the search space. We do this by reducing MD5 to four rounds and pre-computing a fixed difference pattern.

## The Concept

### MD5 Round Structure (RFC 1321)

| Property | Value |
|----------|-------|
| Output size | 128 bits |
| Block size | 512 bits |
| Rounds per block | 64 (16 groups of 4) |
| Internal state | 4 × 32-bit words (A, B, C, D) |
| Constants K[i] | floor(2^32 × abs(sin(i+1))) for i=0..63 |

The four round functions:

| Round Group | Function | Definition |
|-------------|----------|------------|
| 0..15   | F(B,C,D) | (B AND C) OR ((NOT B) AND D) |
| 16..31  | G(B,C,D) | (B AND D) OR (C AND (NOT D)) |
| 32..47  | H(B,C,D) | B XOR C XOR D |
| 48..63  | I(B,C,D) | C XOR (B OR (NOT D)) |

Each round: `A = B + ROTL(A + f(B,C,D) + K[i] + M[g(i)], s[i])`.

### Differential Cryptanalysis Basics

A differential attack chooses a pair of inputs whose XOR difference `ΔM = M ⊕ M'` has a specific pattern, then traces how that difference propagates through the round function. When the output difference `ΔH = H(M) ⊕ H(M')` lands on a known-sparse pattern with high probability, the attacker can chain many such "good" pairs.

| Attack | Year | Cost | Output |
|--------|------|------|--------|
| Wang et al., identical-prefix | 2004 | ~2^39 MD5 calls | full 128-bit collision |
| Stevens, HashClash chosen-prefix | 2009 | ~2^50 MD5 calls | any two chosen prefixes collide |
| Marc Stevens tunings | 2012 | ~2^16 on commodity GPU | near-instant collisions |

### The Reduced 4-Round Toy

For teaching we strip MD5 to rounds 0..15 (one group). The difference pattern we use is:

```
ΔM = 0 0 0 ... 0  (only one word differs, by exactly one bit)
```

The corresponding output difference is also single-bit for high-probability pairs. We walk through ~2^16 random messages until two collide on this difference pattern — typically well under a second.

### The Tenure-Letter Swindle Workflow

```
           attacker                                          verifier
           --------                                          --------
  prefix A "I recommend Prof. X for tenure."
                     \
                      +--- identical collision block --+
                     /
  prefix B "I do NOT recommend Prof. X. He is ..."
                     |
                     v
            MD5(PrefixA || block) == MD5(PrefixB || block)
                     |
                     v
         recruiter sees only MD5, accepts either as authentic
```

The chosen-prefix attack fills in `block` so the two digests match.

## Build It

`main.py` ships:

- `md5_compress(state, block)` — one full 64-round MD5 step.
- `md5(message)` — full digest with padding.
- `toy_md5_4round(message)` — a 4-round reduced MD5 (rounds 0..15).
- `find_identical_prefix_collision(prefix, word_diff=8)` — walks the toy space, finds two suffixes whose MD5 collides with the prefix attached.

```python
from main import md5, toy_md5_4round, find_identical_prefix_collision

print(md5(b"hello"))                                  # 5d41402abc4b2a76b9719d911017c592
s1, s2 = find_identical_prefix_collision(b"PREFIX", word_diff=8)
print(s1.hex(), s2.hex())                             # two suffixes that collide
```

## Use It

| Routine | Purpose | Input | Output |
|---------|---------|-------|--------|
| `md5(message)` | RFC 1321 reference | bytes | 128-bit hex |
| `md5_compress(state, block)` | one compression step | 4-tuple, 64-byte block | 4-tuple |
| `toy_md5_4round(message)` | reduced-round MD5 (16 rounds) | bytes | 128-bit hex |
| `find_identical_prefix_collision(prefix)` | toy collision finder | bytes | two byte strings |
| `tenure_letter_swindle(recommend_text, against_text)` | produces two documents with identical MD5 | bytes, bytes | two equal-length documents |

## Ship It

Do not ship MD5 anywhere. This lesson exists to make the failure mode visceral. For new systems, use SHA-256 (FIPS 180-4) or SHA-3-256 (FIPS 202). When interfacing with legacy systems that still demand MD5, document the threat explicitly (e.g., "this signature is not collision-resistant; an attacker could swap the payload") and consider wrapping with a stronger digest.

## Exercises

1. Verify `md5(b"") == "d41d8cd98f00b204e9800998ecf8427e"` and `md5(b"abc") == "900150983cd24fb0d6963f7d28e17f72`.
2. Modify `toy_md5_4round` to use rounds 0..31 (groups F and G). How does the search cost change?
3. Use `find_identical_prefix_collision` with `prefix=b""` and confirm the search takes roughly 2^16 draws. Plot a histogram of the trial counts over 100 runs.
4. Construct a "tenure letter swindle" pair for the prefixes "I recommend..." and "I do NOT recommend..." and verify `md5(a) == md5(b)`.
5. Implement RFC 1321 test suite verification: every vector in §A.5 must pass exactly.
6. Replace `K[i]` with all-zero constants and re-run; explain why the test vectors break.

## Key Terms

| Term | Definition |
|------|------------|
| Identical-prefix collision | Two messages that share no relation but produce the same MD5. |
| Chosen-prefix collision | Two messages m1, m2 with attacker-controlled distinct prefixes and matching MD5. |
| Differential cryptanalysis | Tracing XOR differences through a cipher's round function. |
| Wang's attack | 2004 identical-prefix collision attack on full MD5. |
| HashClash | Stevens' 2009 implementation of the chosen-prefix attack. |
| Tenure-letter attack | Two documents with identical MD5 but opposite meaning. |
| RFC 1321 | The original MD5 specification. |

## Further Reading

- RFC 1321, The MD5 Message-Digest Algorithm (Rivest, 1992).
- Wang, Feng, Lai, Yu, "Collisions for Hash Functions MD4, MD5, HAVAL-128 and RIPEMD" (CRYPTO 2004).
- Stevens, "Short Chosen-Prefix Collisions for MD5 and the Creation of Rogue CA Certificates" (2009).
- Stevens, "Counter-Cryptanalysis" (CRYPTO 2013).
- Marc Stevens' HashClash repository — collision-finding implementation.
- NIST SP 800-131A Rev. 2 — deprecation of MD5.