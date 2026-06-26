# DES — The Data Encryption Standard to AES — The Advanced Encryption Standard

> DES (adopted January 1977 as FIPS) encrypts 64-bit plaintext blocks with a 56-bit key over 19 stages: an initial transposition, 16 functionally identical rounds parameterized by different 48-bit subkeys derived from the key, a 32-bit swap, and the inverse transposition. Each round takes two 32-bit halves: the left output copies the right input; the right output is the XOR of the left input with f(R, K) — a function that expands 32 bits to 48, XORs with the subkey, feeds eight 6-bit groups into eight S-boxes (each mapping 6→4 bits), and passes the 32-bit result through a P-box. DES is broken: a $10,000 machine brute-forces 2^56 in under a day (Kumar et al., 2006). Triple DES (EDE with two keys, 112-bit effective security) extends life but is slow and aging. AES (Rijndael, selected October 2000, FIPS 197 November 2001) uses 128-bit blocks with 128/192/256-bit keys over 10/12/14 rounds. Each round: SubBytes (single S-box, byte substitution), ShiftRows (rotate row i by i bytes), MixColumns (Galois field GF(2^8) matrix multiply), AddRoundKey (XOR round key). AES is the world's dominant cipher; AES-NI instructions ship in Intel CPUs. A 128-bit key space (~3×10^38) defeats brute force at astronomical timescales.

**Type:** Build
**Languages:** Python, crypto diagrams
**Prerequisites:** Lessons 01-04 of Phase 14
**Time:** ~100 minutes

## Learning Objectives

- Describe the DES block size (64 bits), key size (56 bits effective), round count (16), and the Feistel structure (left/right halves).
- Trace one DES round: expand 32→48, XOR subkey, eight S-boxes (6→4), P-box, XOR with left half.
- Explain why 56-bit DES is obsolete and how triple DES (EDE, two keys) extends security to 112 bits.
- Describe the AES block size (128 bits), key sizes (128/192/256), round counts (10/12/14), and the four round operations.
- Compute why a 128-bit key space (~3.4×10^38) resists brute force even at 10^9 keys/sec × 10^9 parallel processors.

## The Problem

Your bank encrypts transaction records. In 1977, DES was the standard. Today, a $10,000 FPGA cluster brute-forces the 56-bit key in hours. You must migrate to AES-128, but you need to understand why DES's structure was sound but its key was too short, and why AES's design (public competition, open review, byte-oriented operations) makes it the trustworthy default.

## The Concept

### DES structure: the Feistel cipher

DES is a 16-round Feistel cipher operating on 64-bit blocks with a 56-bit key. The 19 stages:

1. Initial transposition (key-independent, 64-bit permutation).
2. 16 rounds, each parameterized by a 48-bit subkey K_i derived from the master key.
3. A 32-bit swap (left and right halves exchange).
4. Inverse of the initial transposition.

Decryption uses the same key with the rounds run in reverse — a Feistel property that makes hardware symmetric. The `code/main.py` demo implements a simplified Feistel cipher (not real DES) to illustrate the structure.

### One DES round in detail

Each round takes two 32-bit inputs (L_{i-1}, R_{i-1}) and produces two 32-bit outputs (L_i, R_i):

```
L_i = R_{i-1}
R_i = L_{i-1} XOR f(R_{i-1}, K_i)
```

The function f has four steps:

| Step | Operation | Size |
|------|-----------|------|
| 1 | Expand R_{i-1} from 32 to 48 bits (fixed transposition + duplication) | 32→48 |
| 2 | XOR E with 48-bit subkey K_i | 48 |
| 3 | Partition into eight 6-bit groups; each enters an S-box (6→4 mapping) | 8×6→8×4=32 |
| 4 | Pass 32-bit S-box output through a P-box (permutation) | 32 |

The eight S-boxes are the heart of DES's nonlinearity. Each maps 64 possible 6-bit inputs to one of 16 4-bit outputs via a lookup table. The S-box designs were classified by IBM/NSA, fueling suspicion of a back door — though no back door was ever found.

### Why DES is obsolete: the 56-bit key

The key is 64 bits, but 8 are parity bits — effective key length is 56 bits. 2^56 ≈ 7.2×10^16. At 1 ns per key, a single processor takes ~2.3 years; a million parallel chips take under a second. In 1977, Diffie and Hellman estimated a $20 million machine could break DES in a day. Today, the machine exists and costs under $10,000 (Kumar et al., 2006). DES is too weak for any modern use.

| Cipher | Key length | Key space | Brute-force time (1 ns/key, single CPU) |
|--------|-----------|-----------|----------------------------------------|
| DES | 56 bits | 7.2×10^16 | ~2.3 years |
| Triple DES | 112 bits (2 keys) | 5.2×10^33 | ~10^17 years |
| AES-128 | 128 bits | 3.4×10^38 | ~10^22 years |
| AES-256 | 256 bits | 1.1×10^77 | ~10^60 years |

### Triple DES (3DES)

IBM realized in 1979 that DES's key was too short. Triple DES (Tuchman, 1979; ISO 8732) uses two keys and three stages: Encrypt(K1) → Decrypt(K2) → Encrypt(K1). The EDE (Encrypt-Decrypt-Encrypt) pattern is backward-compatible with single DES when K1=K2. Two keys (112 bits effective) are considered adequate for routine commercial use. 3DES is still found in legacy payment systems (PIN encryption, EMV) but is being retired due to its 64-bit block size (Sweet32 birthday attacks) and slowness.

### The AES competition: a cryptographic bake-off

NIST took an unprecedented open approach: a public competition announced January 1997. Rules: (1) symmetric block cipher, (2) full design public, (3) key lengths 128/192/256, (4) hardware and software implementable, (5) public or nondiscriminatory licensing. Fifteen proposals. Five finalists (August 1998). Winner announced October 2000: Rijndael by Joan Daemen and Vincent Rijmen. Published as FIPS 197 in November 2001. The openness defeated suspicion of NSA back doors — two young Belgian cryptographers had no incentive to please NSA.

### AES (Rijndael) internals

AES operates on a 4×4 byte state array (128 bits). Key lengths 128/192/256 → 10/12/14 rounds. Each round has four steps:

| Step | Operation | Detail |
|------|-----------|--------|
| SubBytes | Single S-box (256-entry lookup) | Byte-for-byte monoalphabetic substitution |
| ShiftRows | Row i rotated left by i bytes | Diffusion across columns |
| MixColumns | GF(2^8) matrix multiply per column | Diffusion within columns; skipped in last round |
| AddRoundKey | XOR round key into state | Round keys derived from key expansion |

Unlike DES (8 S-boxes), AES has one S-box. MixColumns uses Galois field arithmetic: each new column byte is a linear combination of old column bytes over GF(2^8), computable with two table lookups and three XORs per byte. The `code/main.py` demo implements a simplified AES-like round (not real AES) to illustrate SubBytes, ShiftRows, and AddRoundKey.

### AES security and performance

A 128-bit key gives 2^128 ≈ 3.4×10^38 keys. Even at 10^9 keys/sec with 10^9 parallel processors, exhaustive search takes ~10^13 years — longer than the sun will burn. A 2 GHz software implementation achieves ~700 Mbps; hardware with AES-NI instructions hits gigabits per second. AES encrypts 100+ MPEG-2 videos in real time on a single core.

### The DES-to-AES migration

| Property | DES | AES |
|----------|-----|-----|
| Block size | 64 bits | 128 bits |
| Key length | 56 bits | 128/192/256 bits |
| Rounds | 16 | 10/12/14 |
| Structure | Feistel (two halves) | Substitution-permutation network |
| S-boxes | 8 (6→4) | 1 (8→8) |
| Status | Broken (brute-forceable) | World standard |

The SVG (`assets/des-the-data-encryption-standard-to-aes-the-advanced-encryption-standa.svg`) diagrams both structures side by side.

## Build It

1. Run `python3 code/main.py`. It implements a simplified Feistel cipher (4 rounds, 8-bit blocks) to show the left/right split and round function, then implements a simplified AES-like SPN round (SubBytes, ShiftRows, AddRoundKey on a 2×2 state) to show the substitution-permutation network.
2. Verify the Feistel round-trip: encrypt then decrypt recovers the plaintext.
3. Compare the round function complexity: the Feistel f() expands, XORs, S-boxes, and P-boxes; the SPN substitutes, shifts, and XORs.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|---------------------|
| Trace a DES round | Expand 32→48, XOR subkey, 8 S-boxes, P-box | L_i = R_{i-1}; R_i = L_{i-1} XOR f(R_{i-1}, K_i) |
| Explain DES death | 56-bit key brute-forced in hours by $10K hardware | 2^56 is too small; 2^128 is not |
| Describe AES round | SubBytes → ShiftRows → MixColumns → AddRoundKey | Four steps; MixColumns skipped in final round |
| Justify AES trust | Open competition, public review, no NSA incentive | FIPS 197; two independent Belgian authors |

## Ship It

This lesson produces `outputs/des-to-aes-migration-notes.md`: a migration document covering block size (64→128), key size (56→128+), round structure (Feistel→SPN), performance impact, and legacy 3DES retirement timing.

## Exercises

1. Compute the time to brute-force a 56-bit DES key at 10^9 keys/sec on a single CPU. How many parallel CPUs are needed to finish in 1 second?
2. Triple DES uses EDE with two keys. Why two and not three? Why EDE and not EEE? What property allows backward compatibility with single DES?
3. AES-128 has 10 rounds. How many rounds does AES-256 have? Why does the round count increase with key length?
4. MixColumns uses GF(2^8) arithmetic. Why is the last round missing MixColumns? What would break if it were included?
5. A payment system still uses 3DES with a 64-bit block. Look up the Sweet32 attack. Why does the 64-bit block size create a birthday-bound vulnerability that AES-128 does not have?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| Feistel cipher | "split in half" | Round: L_i=R_{i-1}, R_i=L_{i-1} XOR f(R_{i-1},K_i); decrypt = encrypt reversed |
| S-box | "substitution box" | Nonlinear lookup table; DES has 8 (6→4), AES has 1 (8→8) |
| P-box | "permutation box" | Bit permutation wiring; provides diffusion |
| Product cipher | "cascaded boxes" | Alternating S-boxes and P-boxes over many rounds |
| Whitening | "XOR extra keys" | XOR random keys before/after DES to increase effective key length |
| AES-NI | "Intel instructions" | Hardware AES instructions in modern x86 CPUs |
| FIPS 197 | "the AES standard" | NIST publication defining AES (November 2001) |
| Rijndael | "the AES winner" | Daemen + Rijmen; pronounced "Rhine-doll" |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), Sections 8.2.1 and 8.2.2
- FIPS 46-3 — DES standard (now withdrawn)
- FIPS 197 — AES standard (November 2001)
- Daemen and Rijmen, *The Design of Rijndael* (2002)
- NIST AES competition archive — all 15 proposals and finalist analysis
- Kumar et al., "A High-Density FPGA Implementation of DES" (2006) — $10K brute-force machine