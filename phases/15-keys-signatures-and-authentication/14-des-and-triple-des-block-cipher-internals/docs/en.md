# DES and Triple-DES Block Cipher Internals

> DES (Data Encryption Standard, FIPS 46-3) was the workhorse symmetric cipher of the late 20th century: a 64-bit block, a 56-bit key, 16 Feistel rounds, eight S-boxes, and an Initial/Final permutation pair. It is no longer secure in its single-key form — the EFF's Deep Crack (1998) and modern GPUs exhaust the 2^56 key space in days — but its design ideas (Feistel networks, S-boxes, whitening, EDE) live on in 3DES, Blowfish, and even modern block ciphers. Triple-DES (3DES, FIPS 46-3 §3, ANSI X9.52) chains three DES operations as `Encrypt(K1) → Decrypt(K2) → Encrypt(K3)` with two or three independent keys for an effective 112- or 168-bit security, while staying backwards-compatible with single DES when K1 = K2. This lesson builds a complete DES implementation in pure Python (initial/final permutation, expansion, eight S-boxes, P-box, 16 round keys) so you can watch a 64-bit block get scrambled round by round, and then wraps it in a 3DES `Encrypt-Decrypt-Encrypt` driver. The implementation is intentionally pedagogical — slow, but round-trip correct on the NIST DES test vectors.

**Type:** Learn
**Languages:** Python, diagrams
**Prerequisites:** Lessons 11–13, bitwise operations
**Time:** ~90 minutes

## Learning Objectives

- Implement the full DES round function: expansion `E`, XOR with the round key, eight 6→4 S-boxes, the P-box permutation.
- Generate the 16 round keys from the 56-bit key schedule (parity drop, two 28-bit halves, left rotations, compression `PC2`).
- Apply the initial permutation `IP` and final permutation `FP = IP^-1` correctly so the implementation passes the NIST DES "loopback" test vector.
- Show why DES is a monoalphabetic substitution cipher on 64-bit characters and what that means for ECB mode.
- Implement Triple-DES EDE with two keys (112-bit security) and verify it round-trips on multi-block plaintext.
- Quantify why the 56-bit key is the limit: EFF Deep Crack's 1998 brute force at $250K, today's GPU clusters at dollars and hours.

## The Problem

You are auditing a legacy banking system that still uses single DES to encrypt account numbers on its 1990s mainframe. The auditor asks: "is this still safe?" The answer is no — but the auditor wants evidence: where is the key, what is the round function, why does the small key matter, and what would it take to migrate to 3DES or AES?

You need to be able to point at every byte of the DES computation and show the auditor exactly where the security comes from. That means building a working DES implementation, not just citing it.

This lesson builds it: a from-scratch DES that round-trips on the official test vector, plus a 3DES layer that demonstrates the EDE construction.

## The Concept

### Block cipher basics

A **block cipher** takes an `n`-bit plaintext block and a key, and produces an `n`-bit ciphertext block. DES uses `n = 64` (block size) and a 64-bit key (56 bits of which are real key, the rest are parity bits). The same algorithm with the same key decrypts the block. AES does the same with 128-bit blocks and 128/192/256-bit keys.

The chapter frames block ciphers as **product ciphers**: many rounds of simple substitution (S-boxes) and permutation (P-boxes) composed together so the output is an "exceedingly complicated function of the input" (chapter §8.2).

### The DES outline (Fig. 8-7)

```
                    +----------------------------+
                    v                            |
64-bit plaintext -> [IP] -> L0,R0 -> round 1 -> L1,R1 -> ... -> round 16 -> L16,R16
                                                                            |
                                                                       swap L/R
                                                                            |
                                                                       [FP^-1]
                                                                            v
                                                                      ciphertext
```

Each round `i` (for `i = 1..16`) does:

```
L_i = R_{i-1}
R_i = L_{i-1} XOR f(R_{i-1}, K_i)
```

`f` is the round function:

1. **Expand** `R_{i-1}` from 32 bits to 48 bits via expansion table `E` (duplicating 16 of the 32 bits).
2. **XOR** with the 48-bit round key `K_i`.
3. **Substitute** via eight 6→4 S-boxes `S1..S8`, producing 32 bits.
4. **Permute** the 32 bits through P-box `P`.

After 16 rounds, the left and right halves are swapped, and the final permutation `FP = IP^-1` is applied.

### The initial permutation `IP` and its inverse

`IP` is a fixed permutation of the 64 input bits. It is *not* cryptographic — its purpose is to make hardware implementations easier by spreading the input across multiple bytes. `FP` is its inverse. Because `FP` undoes `IP`, applying `IP` before encrypting and `FP` after encrypting the last round is the same as encrypting without any permutation. We include them anyway because the DES standard specifies them.

### The S-boxes

Each S-box `S_i` takes a 6-bit input `(b1 b2 b3 b4 b5 b6)` and returns a 4-bit value. The first and last bits select the row (`0..3`), the middle four bits select the column (`0..15`). There are eight S-boxes, each a 4×16 table of values from 0 to 15. They are the *only* nonlinear component of DES — every other operation is linear (XOR, permutation, expansion). The strength of DES against differential and linear cryptanalysis rests on the careful choice of these eight tables.

### The key schedule

The 64-bit key is reduced to 56 bits by dropping the parity bits (every 8th bit). The 56 bits are split into two halves `C0` and `D0` (28 bits each). For round `i`:

1. Left-rotate `C` and `D` by 1 or 2 bits (rotation schedule: 1,1,2,2,2,2,2,2,1,2,2,2,2,2,2,1).
2. Concatenate to form 56 bits.
3. Apply compression permutation `PC2` to extract 48 round-key bits.

### Whitening (optional)

DES can be hardened by XORing two 64-bit whitening keys with each block — one before, one after the 16 rounds. This adds 128 bits of effective key length and made early DES brute-force attacks much harder. The chapter notes the same whitening key is used for every block.

### Triple DES (3DES / TDES)

The chapter's 3DES construction (Fig. 8-8):

```
ciphertext = E_K3(D_K2(E_K1(plaintext)))
```

Three DES operations: encrypt with K1, decrypt with K2, encrypt with K3. Two reasons for this odd EDE pattern:

1. **Two keys are enough.** With K1 = K3, you get 112-bit security; with three independent keys, 168-bit. The chapter argues 112 bits is "adequate for routine commercial applications for the time being".
2. **Backwards compatibility.** When K1 = K2, the middle `D_K2` and outer `E_K1` cancel, reducing 3DES to single DES. This let IBM phase 3DES in gradually: legacy single-DES boxes could still talk to new 3DES boxes by setting K1 = K2.

3DES is specified in FIPS 46-3 (withdrawn in 2024 but still widely deployed), ANSI X9.52, and ISO/IEC 18033-3. NIST now requires 3DES be retired in favour of AES.

### Why DES is broken in single-key form

The 56-bit key space is 2^56 ≈ 7.2 × 10^16. EFF's "Deep Crack" (1998) brute-forced a DES key in 56 hours at $250,000 hardware cost. A modern rig of 8× RTX 4090 GPUs tests ~2 × 10^11 keys/second against DES, exhausting the space in ~4 days on a single machine, or hours on a cloud cluster. NIST officially withdrew DES in 2005 and 3DES in 2024.

The lesson's main.py runs DES at ~10,000 blocks/second in pure Python — slow enough that you can watch the rounds, fast enough to verify correctness on test vectors.

## Build It

The implementation lives in `code/main.py` (≈230 lines). It exposes:

- `IP`, `FP`, `E`, `P`, `PC1`, `PC2`, `SBOXES` — full DES tables from FIPS 46-3.
- `des_block(block64, key64, decrypt=False)` — single 64-bit block encrypt/decrypt.
- `des_encrypt(plaintext_bytes, key_bytes)` — ECB mode on a multiple-of-8 byte string.
- `triple_des_encrypt(plaintext_bytes, key1, key2)` — 2-key 3DES EDE.
- `nist_kat()` — runs the official NIST Known Answer Test vectors.
- `demo_round_trace()` — shows the round-by-round L,R state for one block.

Run the NIST KAT to verify correctness:

```python
from main import nist_kat
nist_kat()
```

Encrypt a single block and inspect the round trace:

```python
from main import des_block, demo_round_trace
key  = bytes.fromhex("133457799BBCDFF1")   # weak key from FIPS 46-3
pt   = bytes.fromhex("0123456789ABCDEF")
ct   = des_block(pt, key)
print(ct.hex())      # expected: 85e813540f0ab405
```

Run 3DES:

```python
from main import triple_des_encrypt, triple_des_decrypt
k1 = bytes.fromhex("0123456789ABCDEF")
k2 = bytes.fromhex("23456789ABCDEF01")
ct = triple_des_encrypt(b"hello123hello123", k1, k2)
print(ct.hex())
assert triple_des_decrypt(ct, k1, k2) == b"hello123hello123"
```

## Use It

| Function | Real-world counterpart | Notes |
|----------|------------------------|-------|
| `des_block` | OpenSSL `EVP_des_ecb`, Java `Cipher.getInstance("DES")` | Hardware acceleration on legacy CPUs. |
| `triple_des_encrypt` | OpenSSL `EVP_des_ede3_ecb`, Java `DESede` | 168-bit key (with K3 independent) or 112-bit (K1 = K3). |
| S-box tables | FIPS 46-3 §3.3 | The exact tables; never modify them. |
| `nist_kat` | NIST CAVP test vectors | Same vectors every DES implementation must pass. |
| Round trace | VLSI verification trace | Useful for proving hardware implementations are correct. |

This lesson's DES is intentionally slow (no tables, no bit-slice). Real libraries use lookup tables for the expansion+S-box+P combined, and bit-slicing for SIMD parallelism.

## Ship It

A reusable artifact for cryptography courses lives at `outputs/prompt-des-and-3des.md`. It includes the DES test vector, three round-by-round trace examples, and a migration checklist for moving from DES/3DES to AES-256. Reuse it when onboarding engineers to legacy banking systems.

## Exercises

1. Verify the DES weak keys (`0101010101010101`, `FEFEFEFEFEFEFEFE`, `E0E0E0E0F1F1F1F1`, `1F1F1F1F0E0E0E0E`) produce the same output for `E` and `D`.
2. Verify the DES semi-weak key pairs: encrypting with one decrypts with the other.
3. Implement DES-CBC mode using `des_block` as the primitive; show why an active attacker can flip plaintext bits by XORing the previous ciphertext block.
4. Modify `triple_des_encrypt` to use three independent keys and compare the security statement (112 vs 168 bits).
5. Time `des_block` on your machine; estimate how long a brute-force attack would take at the measured rate and contrast with EFF Deep Crack's 1998 result.
6. Show that AES-128 in CTR mode is roughly 100× faster than this Python DES on equivalent hardware — and argue why 3DES is no longer worth maintaining.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Block cipher | "Encrypts one block at a time" | A keyed permutation on fixed-size bit strings. |
| DES | "Data Encryption Standard" | 64-bit block, 56-bit key, 16 Feistel rounds, FIPS 46-3. |
| Triple DES | "3DES / TDES" | EDE chain `E_K1, D_K2, E_K3`, 112- or 168-bit effective key. |
| Feistel network | "Half the block at a time" | Structure where one half is XORed with a function of the other half and the key. |
| S-box | "Substitution box" | The only nonlinear component of DES; 6→4 bits. |
| P-box | "Permutation box" | Bit permutation; linear. |
| Round key | "Per-round subkey" | 48-bit key derived from the 56-bit master key for each of 16 rounds. |
| Initial permutation | "IP" | Fixed bit permutation at the start of DES; not cryptographic. |
| Whitening | "XOR before and after" | Extra XOR with separate keys to extend effective key length. |
| EDE | "Encrypt-Decrypt-Encrypt" | 3DES construction; backward compatible with single DES. |

## Further Reading

- Tanenbaum, *Computer Networks*, Chapter 8 (this chapter).
- FIPS 46-3 — *Data Encryption Standard (DES)* (withdrawn 2005).
- ANSI X9.52 — *Triple Data Encryption Algorithm Modes of Operation*.
- NIST SP 800-131A — *Transitioning the Use of Cryptographic Algorithms and Key Lengths* (3DES deprecated 2024).
- Electronic Frontier Foundation, *Cracking DES* (1998) — Deep Crack project notes.
- Schneier, B., *Applied Cryptography* — full DES and 3DES reference.