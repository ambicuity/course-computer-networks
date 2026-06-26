# Building the SHA-1 Compression Function

> SHA-1 processes 512-bit message blocks through an 80-round compression function that mixes five 32-bit state variables (h0..h4) using non-linear functions f(t), constants K(t), and a 32-word message schedule W[t] derived from the original 16 words via left-rotation expansion. The function is described in FIPS 180-4 (now superseded by SHA-2/SHA-3) and produces a 160-bit digest. We implement the compression function in pure Python, exercising every stage on a known test vector so we can prove the round constants, the 80-step schedule, and the final additive feedback into the state vector all line up with the standard.

**Type:** algorithm-implementation
**Languages:** Python 3 (stdlib only)
**Prerequisites:** message digests (Lesson 13), big-endian bit packing, modular addition
**Time:** ~50 minutes

## Learning Objectives

- Implement the SHA-1 initial hash values H and the four 32-bit round constants K[t] from FIPS 180-4 §4.1.1 / §4.2.1.
- Expand a 16-word block into the 80-word message schedule W[t] using the rotation-based recurrence.
- Code the four non-linear functions f[0..19], f[20..39], f[40..59], f[60..79] with their parity/majority/rotation semantics.
- Drive 80 compression rounds that update (a, b, c, d, e) and produce the next chaining value H_i+1.
- Verify the implementation against the FIPS 180-4 ""abc"" vector and a multi-block message.

## The Problem

Knowing that SHA-1 produces a 160-bit digest does not tell us what happens inside a single compression step. To audit a digest, to compare SHA-1 against SHA-256, or to detect downstream confusion between the message schedule W[t] and the working state (a..e), we need to look inside the round function. A reusable, testable, line-by-line Python implementation lets us swap the round constants in-place and immediately observe how a single bit flip propagates through the 80-round dependency chain.

The challenge is pedagogical completeness: many open-source implementations hide the message-schedule expansion inside `for t in range(16, 80)`. We want each piece to be visible — the rotation by 1 bit in the expansion, the constants 0x5A827999..0xCA62C1D6, and the final additive combination `H_i+1 = H_i + (a,b,c,d,e)`.

## The Concept

### FIPS 180-4 Initial Hash Values

The initial hash value H(0) for SHA-1 is five 32-bit words hard-coded in the standard:

| Word | Hex Value | Decimal |
|------|-----------|---------|
| H0   | 0x67452301 | 1732584193 |
| H1   | 0xEFCDAB89 | 4023233417 |
| H2   | 0x98BADCFE | 2562383102 |
| H3   | 0x10325476 | 271733878 |
| H4   | 0xC3D2E1F0 | 3285377520 |

These are the first five 32-bit words of the fractional parts of the square roots of 2, 3, 5, 7, and 11. We pass them in as a tuple rather than recomputing them, since the standard defines them literally.

### Round Constants K[t]

Four constant groups, one per 20-round phase. The numeric pattern is visible in the hex pattern: each is a 32-bit value constructed from the fractional bits of the cube roots of small primes (2, 3, 5, 10).

| Round | Hex Constant |
|-------|--------------|
|  0..19 | 0x5A827999 |
| 20..39 | 0x6ED9EBA1 |
| 40..59 | 0x8F1BBCDC |
| 60..79 | 0xCA62C1D6 |

### The 80-Word Message Schedule W[t]

Given a 512-bit (16-word) block M[0..15], extend to W[0..79]:

```
W[t] = M[t]                              for 0 <= t < 16
W[t] = ROTL_1(W[t-3] xor W[t-8] xor
              W[t-14] xor W[t-16])       for 16 <= t < 80
```

ROTL_1(x) is a 32-bit left rotation by one bit. Each W[t] for t ≥ 16 mixes words 3, 8, 14, and 16 positions earlier with a one-bit rotation, which is the seed of SHA-1's avalanche property.

### The Non-Linear Round Functions

| Phase | Round t | Function f(B, C, D) | Operation |
|-------|---------|---------------------|-----------|
| 0 |  0..19 | (B AND C) OR ((NOT B) AND D) | Ch — choose |
| 1 | 20..39 | B XOR C XOR D | Parity |
| 2 | 40..59 | (B AND C) OR (B AND D) OR (C AND D) | Majority |
| 3 | 60..79 | B XOR C XOR D | Parity (same shape as phase 1) |

### One Round in Pseudocode

```
T = ROTL_5(A) + f(B, C, D) + E + K[t] + W[t]
E = D
D = C
C = ROTL_30(B)
B = A
A = T
```

The chained shift along (a, b, c, d, e) is what makes the function iterative rather than purely parallel.

### Final Additive Feedback

After 80 rounds, the five new working variables are added (mod 2^32) back into the chain:

```
H0' = H0 + A
H1' = H1 + B
H2' = H2 + C
H3' = H3 + D
H4' = H4 + E
```

This is the only operation that carries state across blocks, which is what makes SHA-1 a Merkle-Damgård construction.

### End-to-End Pipeline

| Stage | Input | Output |
|-------|-------|--------|
| Pad | message M | padded blocks M* |
| Split | M* | 512-bit blocks M_0, M_1, ... |
| For each block | M_i + H(i) | H(i+1) |
| Final | H(last) | 160-bit digest |

## Build It

The `main.py` in `code/` ships a `sha1_compress(H, block)` function that does exactly one compression step. You can wire any 512-bit block of bytes into it, then chain the result. Test it by passing the empty block through and checking the intermediate state, then run a full `sha1("")` to compare against the published constant `da39a3ee5e6b4b0d3255bfef95601890afd80709`.

```python
from main import sha1_compress, sha1

# One round, manually inspected:
H = (0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0)
block = b"abc" + b"\x80" + b"\x00" * (64 - 3 - 1 - 8) + (24).to_bytes(8, "big")
H1 = sha1_compress(H, block)
print(H1)
assert sha1(b"abc") == "a9993e364706816aba3e25717850c26c9cd0d89d"
```

## Use It

| Routine | Purpose | Input | Output |
|---------|---------|-------|--------|
| `sha1_compress(H, block)` | one 80-round compression step | 5-tuple H, 64-byte block | 5-tuple H' |
| `sha1(message)` | full digest of a byte string | bytes | hex string |
| `rotr(x, n)` / `rotl(x, n)` | 32-bit rotations used inside round function | int | int |
| `extend_schedule(M)` | expand 16-word block into 80 words | 16-tuple of int | list of 80 int |

## Ship It

When you build a digest in production, prefer `hashlib.sha1` (C-implemented, FIPS-validated). Use this lesson's compression function for teaching, for cross-checking test vectors, and for experimenting with constant substitutions (e.g., reduced-round SHA-1 for academic collision work — note that SHA-1 is broken for collision resistance and must not be used for digital signatures in new systems, per NIST SP 800-131A Rev. 2 §3.2).

## Exercises

1. Modify `sha1_compress` to run only 20 rounds. Confirm that the output of `sha1_20(b"abc")` no longer matches the FIPS test vector. What does this say about the avalanche property of SHA-1?
2. Swap the four K[t] constants for 0xDEADBEEF. Verify with a Python test that the function still terminates and that the digest differs from the standard. Why does the standard require specific K[t] values?
3. Implement `extend_schedule` independently and confirm it returns 80 words. Then flip one bit of W[0] and show how the effect spreads into W[16], W[32], W[48], W[64] — predict which bits in the final digest change.
4. Trace through one round by hand for `t=0` with the ""abc"" block. Compare your intermediate T value with `print(A, B, C, D, E)` inside the implementation.
5. Reuse the compression function to build SHA-0 (the predecessor without the one-bit rotation in expansion) and compare its digest of ""abc"" to SHA-1's.

## Key Terms

| Term | Definition |
|------|------------|
| Compression function | The 80-round core of SHA-1 that maps 160-bit state + 512-bit block to 160-bit state. |
| Message schedule W[t] | The 80-word expanded view of a 16-word block, generated via left-rotation and XOR. |
| Ch (choose) | Round function `f(B,C,D) = (B AND C) OR ((NOT B) AND D)` used for t in 0..19. |
| Parity | Round function `f(B,C,D) = B XOR C XOR D` used for t in 20..39 and 60..79. |
| Majority | Round function `f(B,C,D) = (B AND C) OR (B AND D) OR (C AND D)` used for t in 40..59. |
| Merkle-Damgård | Construction pattern where the output of one compression feeds into the next. |
| K[t] | The four 32-bit round constants, one 20-round phase each. |

## Further Reading

- FIPS 180-4, Secure Hash Standard (NIST, 2015) — the canonical SHA-1 specification, §4.1 and §4.2.
- RFC 3174, US Secure Hash Algorithm 1 (SHA-1) — historical test vectors and C reference.
- RFC 6234, US Secure Hash Algorithms (SHA and SHA-based HMAC and HKDF) — updated test vectors.
- NIST SP 800-131A Rev. 2, Transitioning the Use of Cryptographic Algorithms — deprecation timeline.
- Wang, Yin, Yu — Finding Collisions in the Full SHA-1 (CRYPTO 2005) — why this construction is broken.
- Handbook of Applied Cryptography, Chapter 9 — Menezes, van Oorschot, Vanstone.