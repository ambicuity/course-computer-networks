# SHA-1, SHA-2, and MD5 Digest Internals

> A hash function is a one-way compression engine: every input bit influences every output bit, and no algorithm can unwind the computation in useful time.

**Type:** Build
**Languages:** Python
**Prerequisites:** Lessons 11–13, bitwise operations, modular arithmetic
**Time:** ~75 minutes

## Learning Objectives

- Describe the Merkle–Damgård construction and explain why length-extension is a structural consequence, not a bug.
- Implement SHA-256 padding: fill to 448 bits mod 512, then append the 64-bit big-endian message length.
- Trace a single SHA-256 compression round: Ch, Maj, SIGMA0, SIGMA1, the message schedule, and how they update eight 32-bit working registers.
- Compare MD5's 128-bit state and four-group round structure (F/G/H/I nonlinear functions) with SHA-1's 160-bit state and eighty-round schedule.
- State precisely why MD5 and SHA-1 are broken for collision resistance: cite Wang et al. (2004/2005) and the SHAttered (2017) practical collision.
- Verify a from-scratch SHA-256 implementation against `hashlib` for identical inputs and explain the speed gap.

## The Problem

You are auditing a TLS 1.1 deployment at a payments company. The server's certificate chain uses SHA-1 signatures. Your assessment tool flags this as a critical finding. The engineering team asks for a precise technical explanation of the risk — not vague warnings about "weak algorithms," but a concrete account of what Wang et al. actually found and why it breaks certificate binding.

Answering that question requires knowing the round structure of SHA-1. You need to explain what a differential path is, why SHA-1's single-bit-rotate message schedule permits one to be constructed, and why SHA-256's wider rotation constants close that path. You also need to answer the follow-up: "If SHA-1 collisions cost $110,000 in 2017, how long before they cost $1,000?"

This lesson provides that foundation by building SHA-256 from first principles — padding, compression rounds, message schedule — and verifying it against the standard library. Reading the collision literature with this background, you can explain the attack at the bit level rather than by analogy.

## The Concept

### What a hash function must provide

A cryptographic hash function `H` maps an arbitrary-length byte string to a fixed-length digest:

```
H : {0,1}* → {0,1}^n
```

For SHA-256, `n = 256` (32 bytes, 64 hex characters). For MD5, `n = 128`. For SHA-1, `n = 160`. Three computational properties are required:

| Property | Meaning | "Broken" means |
|----------|---------|----------------|
| Preimage resistance | Given `d`, cannot find `M` with `H(M) = d` | Attacker reverses hashes |
| Second-preimage resistance | Given `M`, cannot find `M' ≠ M` with `H(M') = H(M)` | Attacker swaps a specific document |
| Collision resistance | Cannot find any `M ≠ M'` with `H(M) = H(M')` | Two different messages share a digest |

Collision resistance is the hardest to achieve and the first to fall. MD5 and SHA-1 have lost it entirely. That is sufficient to break TLS certificate chaining, code signing, and any protocol that uses hash equality as an integrity guarantee.

### The Merkle–Damgård construction

MD5, SHA-1, and SHA-256 all share the same outer skeleton, known as the Merkle–Damgård construction:

```
message M (arbitrary length)
       |
       v
  [Padding + Length field]      <- fills to a block-size multiple
       |
       +--------+
       |        | IV (fixed initial value)
       v        v
      block_0  [C] --> state_1
      block_1  [C] --> state_2
          ...
      block_n  [C] --> final state  <- output as digest
```

`C` is the **compression function** — it maps `(state, block)` to a new state of the same width as the state. The three algorithms differ only in `C`. The outer loop — pad, split into 512-bit blocks, iterate `C` with chaining — is identical.

Ralph Merkle and Ivan Damgård independently proved that if `C` is collision resistant, then the full hash is collision resistant. Their proof also exposed the construction's main structural weakness:

**Length-extension attack:** The final state is indistinguishable from an intermediate state. An adversary who knows `H(M)` can compute `H(M || padding || extension)` for any extension without knowing `M`. This is because they can feed `H(M)` as the initial state for a new chain starting at block `n+1`. HMAC was designed specifically to prevent this by double-hashing with a key.

### Message padding and length encoding

Before block iteration, the message is padded to a multiple of 512 bits (64 bytes). The rules for SHA-256 (and SHA-1, which is identical):

1. Append a single `0x80` byte (a 1-bit followed by seven zeros).
2. Append `0x00` bytes until the total length is 56 bytes mod 64 (leaving 8 bytes for the length).
3. Append the original message length **in bits** as a 64-bit **big-endian** integer.

MD5 uses the same structure but appends the length in **little-endian** byte order — an architectural choice that contributes to its implementation complexity.

Example: padding the 3-byte message `abc` (24 bits):

```
Byte offset:   0   1   2   3   4  ...  55  56  57  58  59  60  61  62  63
Value (hex):  61  62  63  80  00  ...  00  00  00  00  00  00  00  00  18
              ^^^^^^^^^  ^           zeros^            length = 24 bits^^^
              "abc"      |
                       0x80 marker
```

Result: exactly one 64-byte block. The 64-bit length field binds the digest to a specific message length, preventing the simplest padding oracle attacks.

### The SHA-256 compression function

SHA-256 (FIPS 180-4) operates on 512-bit blocks with a 256-bit (eight 32-bit words) internal state `(a, b, c, d, e, f, g, h)`. There are 64 rounds.

**State layout:**

```
  a      b      c      d      e      f      g      h
[32]   [32]   [32]   [32]   [32]   [32]   [32]   [32]   = 256-bit state
```

**Per-round update** (round `i = 0..63`):

```
T1 = h + SIGMA1(e) + Ch(e, f, g) + K[i] + W[i]
T2 = SIGMA0(a) + Maj(a, b, c)

new values: a = T1 + T2
            b = a,  c = b,  d = c
            e = d + T1
            f = e,  g = f,  h = g
```

The nonlinear and rotation primitives:

```
Ch(e,f,g)  = (e AND f) XOR (NOT e AND g)                  "Choice"
Maj(a,b,c) = (a AND b) XOR (a AND c) XOR (b AND c)        "Majority"
SIGMA0(a)  = ROTR(a, 2)  XOR ROTR(a, 13) XOR ROTR(a, 22)
SIGMA1(e)  = ROTR(e, 6)  XOR ROTR(e, 11) XOR ROTR(e, 25)
```

`Ch` selects bits from `f` or `g` based on `e`; `Maj` outputs the majority vote of three bits. Together they create avalanche: a 1-bit change in any register propagates across all bits within a few rounds.

**Message schedule** expands the 16-word (512-bit) block into 64 words so each round uses distinct derived material:

```
W[i] = message word i,                              for i = 0..15
W[i] = sigma1(W[i-2]) + W[i-7]
       + sigma0(W[i-15]) + W[i-16]  (mod 2^32),    for i = 16..63

sigma0(x) = ROTR(x, 7)  XOR ROTR(x, 18) XOR SHR(x, 3)
sigma1(x) = ROTR(x, 17) XOR ROTR(x, 19) XOR SHR(x, 10)
```

The **round constants** `K[0..63]` are the first 32 bits of the fractional parts of the cube roots of the first 64 primes. They break register-level symmetry so two identical blocks do not cancel.

After 64 rounds, each working register is added modulo 2^32 to the incoming state for that block (the Merkle–Damgård **feed-forward**), and the result becomes the initial state for the next block.

### The MD5 compression function

MD5 (RFC 1321) uses a 128-bit state — four 32-bit words `(a, b, c, d)` — and 64 rounds in four groups of 16. Each group applies a different nonlinear function:

```
Rounds  1–16:  F(b,c,d) = (b AND c) OR (NOT b AND d)     "Choice on d"
Rounds 17–32:  G(b,c,d) = (b AND d) OR (c AND NOT d)     "Choice on b"
Rounds 33–48:  H(b,c,d) = b XOR c XOR d                  "XOR chain"
Rounds 49–64:  I(b,c,d) = c XOR (b OR NOT d)             "Not-or"
```

Per-round update (where `<<<` is a left rotation by `s` bits):

```
a = b + ((a + F/G/H/I(b,c,d) + X[k] + T[i]) <<< s)
```

`X[k]` is a word from the current block (with a group-specific access permutation), and `T[i] = floor(2^32 × |sin(i+1)|)` is a per-round constant. The left-rotation amount `s` varies per round within each group (e.g., group 1 uses 7, 12, 17, 22 repeatedly). MD5 is little-endian throughout.

### The SHA-1 compression function

SHA-1 (FIPS 180-4 §6.1) uses a 160-bit state — five 32-bit words `(a, b, c, d, e)` — and 80 rounds in four groups of 20. Its message schedule:

```
W[i] = message word i,                        for i = 0..15
W[i] = ROTL(W[i-3] XOR W[i-8] XOR W[i-14] XOR W[i-16], 1),  for i = 16..79
```

The single 1-bit left-rotation is the critical weakness: Wang et al. showed this rotation is too narrow to destroy the differential relationship between two carefully chosen message blocks.

Per-round nonlinear functions:

```
Rounds  0–19:  Ch(b,c,d)  = (b AND c) OR (NOT b AND d)
Rounds 20–39:  Parity(b,c,d) = b XOR c XOR d
Rounds 40–59:  Maj(b,c,d) = (b AND c) OR (b AND d) OR (c AND d)
Rounds 60–79:  Parity(b,c,d) = b XOR c XOR d
```

Round constants: K0 = 0x5A827999, K1 = 0x6ED9EBA1, K2 = 0x8F1BBCDC, K3 = 0xCA62C1D6.

Per-round update:

```
temp = ROTL(a, 5) + f(b,c,d) + e + W[i] + K_round
e = d,  d = c,  c = ROTL(b, 30),  b = a,  a = temp
```

### Why MD5 and SHA-1 are broken for collision resistance

**MD5 (Wang and Yu, 2004):** Published at CRYPTO 2004, the attack constructs two 1024-bit (two-block) messages `M` and `M'` that differ in specific bit positions in each block. By solving a system of differential conditions across MD5's four round groups, the differences cancel completely by round 64 of block 2, yielding identical `(a, b, c, d)` outputs. The collision generation now takes milliseconds on a laptop. MD5 is cryptographically dead for any use requiring collision resistance.

**SHA-1 (Wang, Yin, Yu 2005; SHAttered 2017):** Wang et al. estimated finding a SHA-1 collision in approximately 2^63 compression evaluations — well below the birthday bound of 2^80. The SHAttered project (Stevens, Bursztein, Karpman, Albertini, Markov — Google and CWI, 2017) produced the first concrete SHA-1 collision: two distinct PDF files with identical SHA-1 digests. The computation required 9.2 × 10^18 SHA-1 compressions, running on GPU clusters for months at an estimated cost of ~$110,000. SHA-1 was banned in publicly trusted TLS certificates by Chrome and Firefox in 2017. The chosen-prefix variant (which allows meaningful content in both colliding documents) was demonstrated in 2020 for ~$45,000, with costs falling as GPU prices drop.

SHA-256's wider rotation constants (SIGMA0: 2, 13, 22 bits; SIGMA1: 6, 11, 25 bits) compared to SHA-1's (5 and 30 bits) mean differential paths diffuse across all 32 bit positions in fewer rounds. The wider state (eight 32-bit words vs five) and 64-round schedule with the sigma-based message schedule make constructing a differential path through all 64 rounds computationally infeasible with current techniques.

### Algorithm comparison

| Algorithm | Digest | Block | State width | Rounds | Collision attack | Status |
|-----------|--------|-------|-------------|--------|-----------------|--------|
| MD5 | 128 bits | 512 bits | 128 bits | 64 (4×16) | Milliseconds | Broken |
| SHA-1 | 160 bits | 512 bits | 160 bits | 80 (4×20) | ~2^63, $110k | Broken |
| SHA-256 | 256 bits | 512 bits | 256 bits | 64 | None known | Safe |
| SHA-512 | 512 bits | 1024 bits | 512 bits | 80 | None known | Safe |
| SHA-3-256 | 256 bits | 1088-bit rate | 1600 bits | 24 (Keccak) | None known | Safe |

SHA-3 uses the sponge construction, not Merkle–Damgård, so it is inherently immune to length-extension attacks.

## Build It

The implementation in `code/main.py` builds a complete SHA-256 using only the Python standard library. It exposes:

- `rotr(x, n)` — 32-bit right-rotate of `x` by `n` positions.
- `sha256_pad(msg)` — pads a byte string to a multiple of 64 bytes per FIPS 180-4.
- `sha256_compress(state, block)` — applies one 64-round SHA-256 compression to an 8-word state list.
- `sha256(msg)` — full digest: pad, iterate blocks, serialize to hex.
- `main()` — verifies multiple inputs against `hashlib.sha256`, prints the padded block layout for `b"abc"`, and traces message schedule words W[0..19].

### Step 1: Round constants and initial hash values

The 64 round constants and 8 initial hash values are specified in FIPS 180-4. They must be taken from the table verbatim — computing them with floating-point `cbrt` or `sqrt` introduces rounding errors for several entries:

```python
K = [
    0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5,
    0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
    # ... 56 more (full list in code/main.py)
]

H0 = [
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
    0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19,
]
```

`H0` is a copy of the state at the start of each fresh hash. Each block compression starts from the state left by the previous block.

### Step 2: Right-rotate and padding

A 32-bit right-rotate shifts bits right by `n`, wrapping the discarded low bits to the top:

```python
def rotr(x: int, n: int) -> int:
    return ((x >> n) | (x << (32 - n))) & 0xFFFFFFFF
```

Padding appends `0x80`, fills with zeros, then writes the 64-bit big-endian bit-count:

```python
def sha256_pad(msg: bytes) -> bytes:
    length_bits = len(msg) * 8
    msg = msg + b'\x80'
    while len(msg) % 64 != 56:
        msg += b'\x00'
    return msg + length_bits.to_bytes(8, 'big')
```

For `b"abc"` (24 bits), this produces exactly one 64-byte block.

### Step 3: The compression function

The message schedule expands 16 input words into 64, then 64 rounds update eight working registers:

```python
def sha256_compress(state: list[int], block: bytes) -> list[int]:
    W = list(struct.unpack('>16I', block))
    for i in range(16, 64):
        s0 = rotr(W[i-15], 7) ^ rotr(W[i-15], 18) ^ (W[i-15] >> 3)
        s1 = rotr(W[i-2], 17) ^ rotr(W[i-2], 19) ^ (W[i-2] >> 10)
        W.append((W[i-16] + s0 + W[i-7] + s1) & 0xFFFFFFFF)
    a, b, c, d, e, f, g, h = state
    for i in range(64):
        S1  = rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)
        ch  = (e & f) ^ (~e & g)
        T1  = (h + S1 + ch + K[i] + W[i]) & 0xFFFFFFFF
        S0  = rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)
        maj = (a & b) ^ (a & c) ^ (b & c)
        T2  = (S0 + maj) & 0xFFFFFFFF
        h, g, f = g, f, e
        e = (d + T1) & 0xFFFFFFFF
        d, c, b = c, b, a
        a = (T1 + T2) & 0xFFFFFFFF
    return [(x + y) & 0xFFFFFFFF for x, y in zip(state, [a, b, c, d, e, f, g, h])]
```

Note that `~e & g` in Python gives the correct 32-bit result: Python's arbitrary-precision two's complement ensures the low 32 bits of `~e` match the bitwise NOT of the 32-bit value `e`, and `g` (a 32-bit value) masks away all higher bits.

### Step 4: Full digest

Chain compression over all padded blocks and serialize the eight final state words:

```python
def sha256(msg: bytes) -> str:
    padded = sha256_pad(msg)
    state = H0[:]
    for i in range(0, len(padded), 64):
        state = sha256_compress(state, padded[i:i+64])
    return ''.join(f'{x:08x}' for x in state)
```

### Step 5: Verify against hashlib

The FIPS 180-4 test vector for `b"abc"`:

```
SHA-256("abc") = ba7816bf8f01cfea414140de5dae2ec73b00361bbef0469bf5f8cf819c912347
```

Run `python3 code/main.py` to see the comparison for three inputs side-by-side, the 64-byte padded block layout for `b"abc"`, and W[0..19] of the message schedule — showing how the first 16 words come directly from the padded block and words 16–19 are derived.

## Use It

| Function | Real-world counterpart | Notes |
|----------|------------------------|-------|
| `sha256_pad` | `hashlib.sha256` padding | Same rule in FIPS 180-4 §5.1.1; identical for SHA-1 except SHA-1 block size is also 64 bytes. |
| `sha256_compress` | `SHA256_Transform` in OpenSSL, `sha256_block` in Linux `crypto/sha256.c` | Intel SHA-NI extensions reduce this to ~2-4 cycles per round in hardware. |
| `sha256` | `hashlib.sha256(msg).hexdigest()` | Standard library wraps OpenSSL; 100–500× faster than pure Python. |
| `hashlib.md5` | Checksum tools, non-security caches | Still in stdlib; never use for signatures, MACs, or certificate binding. |
| `hashlib.sha1` | Legacy Git object IDs, old TLS stacks | Deprecated in certificates since 2017; Git is migrating to SHA-256 (git SHA-256 mode). |
| `hmac.new(key, msg, hashlib.sha256)` | HMAC-SHA256 in TLS record MAC | Double-hashing with a key defeats length-extension; preferred over raw SHA-256 for MACs. |

The key performance gap: this pure-Python implementation runs SHA-256 at roughly 3–5 MB/s on a modern laptop. OpenSSL with SHA-NI runs at 3–5 GB/s — a 1000× speedup from hardware single-instruction compress and pipelined block processing. The algorithm is identical; only the substrate differs.

## Ship It

A reusable study and incident-response artifact lives at `outputs/prompt-sha-1-sha-2-and-md5-digest-internals.md`. It prompts an LLM (or study partner) to produce: a one-paragraph mechanism summary, the observable state and packet fields that prove hash use, a normal trace checklist, a failure mode with a minimal diagnostic, and a runbook or drill. Load it into any cryptography course study session or security-incident context to anchor analysis in observable network evidence rather than abstract theory.

## Exercises

1. Verify the FIPS 180-4 SHA-256 test vectors: `b""`, `b"abc"`, and the 1,000,000-character string `b"a" * 1_000_000`. Confirm your digest matches `hashlib.sha256` for all three.
2. Instrument `sha256_compress` to print registers `a` and `e` after every 8th round for `b"abc"` then for `b"abd"` (one bit different). Count how many rounds it takes before every bit position differs between the two traces — this is the avalanche measurement.
3. Implement a length-extension attack: given `d = sha256(secret + known)` and `len(secret)` (but not `secret`), compute `sha256(secret + known + padding + extension)` by treating `d` as an initial state and calling `sha256_compress` directly on an additional block. Demonstrate that the extended digest matches what `sha256(secret + known + padding + extension)` would produce if you knew `secret`.
4. Using `hashlib.md5`, verify a published Wang–Yu MD5 collision pair (two 128-byte messages from their 2004 appendix, widely republished online). Confirm both produce the same MD5 digest, then XOR the two messages and count the differing bit positions.
5. Extend `sha256` to handle streaming input: rewrite it to accept an iterable of `bytes` chunks rather than a single `bytes` object, accumulating partial blocks across chunk boundaries without loading the full message into memory.
6. Time `sha256(b"a" * 10_000_000)` against `hashlib.sha256(b"a" * 10_000_000).hexdigest()`. Compute the MB/s throughput ratio, then explain in one paragraph why a C implementation with Intel SHA-NI achieves another 5–10× speedup beyond the raw C-vs-Python gap.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Hash function | "Turns data into a fingerprint" | A deterministic map from arbitrary-length input to a fixed-size digest, computationally irreversible. |
| Merkle–Damgård | "How hash functions work internally" | A construction iterating a fixed-length compression function with chaining state; proven collision-resistant if the compression function is. |
| Compression function | "The core of the hash" | A keyed permutation from `(state_width + block_width)` bits to `state_width` bits, applied once per 512-bit block. |
| Collision resistance | "Two messages can't hash the same" | A computational property — no efficient algorithm can find distinct `M`, `M'` with `H(M) = H(M')`. MD5 and SHA-1 have lost this. |
| Length extension | "Appending to a hash you don't own" | An attack where knowing `H(M)` lets you compute `H(M || padding || ext)` without knowing `M`; a structural consequence of Merkle–Damgård. |
| Differential path | "The attacker's roadmap through rounds" | A sequence of bit-level differences engineered to cancel completely by the final compression round, producing two inputs with the same output. |
| Message schedule | "W[i] expansion" | Extending a 16-word block into 64 or 80 words so each round processes fresh derived material — the wider the rotations, the harder to construct a differential path. |
| Ch (Choice) | "The selection function" | `(e AND f) XOR (NOT e AND g)`: selects bits from `f` when the corresponding bit of `e` is 1, from `g` when 0. |
| Maj (Majority) | "The voting function" | `(a AND b) XOR (a AND c) XOR (b AND c)`: outputs whichever bit value appears in at least two of the three inputs. |
| SHAttered | "The SHA-1 collision" | The 2017 Stevens et al. demonstration of the first practical full SHA-1 collision using two different PDF files at ~$110,000 GPU cost. |

## Further Reading

- FIPS 180-4 (NIST, 2015) — *Secure Hash Standard* — authoritative specification for SHA-1, SHA-224, SHA-256, SHA-384, SHA-512; §6 contains the compression-function pseudocode used in this lesson.
- RFC 1321 (Rivest, 1992) — *The MD5 Message-Digest Algorithm* — original MD5 specification with step-by-step worked examples and Appendix A test vectors.
- Wang, X., & Yu, H. (2005). *How to Break MD5 and Other Hash Functions* — EUROCRYPT 2005; the paper that produced the first MD5 collision pairs in hours; accessible with the background this lesson provides.
- Stevens, M., Bursztein, E., Karpman, P., Albertini, A., & Markov, Y. (2017). *The First Collision for Full SHA-1* — SHAttered paper; full text and collision PDF files at [shattered.io](https://shattered.io).
- Tanenbaum, *Computer Networks*, Chapter 8 — positions hash functions within the security architecture: certificates, MACs, and digital signatures.
- Schneier, B., *Applied Cryptography* (2nd ed.), Chapter 18 — detailed MD5 and SHA-1 internals and differential cryptanalysis intuition without the formalism of the original papers.
