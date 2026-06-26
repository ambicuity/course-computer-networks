# The Advanced Encryption Standard (AES / Rijndael)

> AES is the FIPS 197 (2001) successor to DES, selected by NIST in October 2000 after a three-year open competition. The winning algorithm, **Rijndael**, was designed by two Belgian cryptographers, Joan Daemen and Vincent Rijmen, and operates on 128-bit blocks with 128-, 192-, or 256-bit keys. AES-128 runs 10 rounds; AES-192 runs 12; AES-256 runs 14. The state is a 4×4 byte matrix arranged in column-major order. Each round is four operations: **SubBytes** (a single 256-entry S-box derived from a multiplicative inverse in **GF(2^8)** with an affine transform), **ShiftRows** (rotate row *i* by *i* bytes left), **MixColumns** (multiply each column by a fixed 4×4 matrix over GF(2^8) — diffusion), and **AddRoundKey** (XOR the state with a round key derived from the cipher key by a key schedule). The first round has an extra AddRoundKey before SubBytes, and the last round skips MixColumns. The key schedule expands the 16-byte key into 11 round keys by rotating the last column, applying the S-box, XORing with a round-dependent Rcon, and chaining. The S-box has no fixed points and no fixed-point opposites, eliminating trivial symmetries. AES is the only public, unbroken, widely-deployed block cipher; the most successful published attacks (Biclique by Bogdanov, Knudsen, Leander, Müller, Raghunathan, and others, 2011) only reach 4-round AES-128 with time complexity 2^126.1, well above the 2^128 of brute force. AES runs at ~10 GB/s with AES-NI hardware on a modern x86 core.

**Type:** Learn
**Languages:** Python (stdlib AES-128 round-by-round simulator), diagrams
**Prerequisites:** Block ciphers and modes, modular arithmetic, finite field GF(2^8)
**Time:** ~90 minutes

## Learning Objectives

- Run a complete AES-128 encryption step by step: key expansion → 10 rounds of SubBytes/ShiftRows/MixColumns/AddRoundKey → ciphertext.
- Compute the AES S-box from the GF(2^8) multiplicative inverse plus the affine transform `b' = Mb XOR 0x63`, and show it has no fixed points.
- Show that the round key for round *i* is generated from the previous round key by `RotWord + SubWord + XOR Rcon[i]`, then `SubWord + XOR` for each subsequent word.
- Multiply a 4-byte column by the MixColumns matrix over GF(2^8) and verify diffusion: changing one byte of input changes all four output bytes.
- Compare AES-128, AES-192, and AES-256 with respect to rounds (10/12/14), key schedule length, and effective security margin against brute force.

## The Problem

In 1997 NIST announced a public competition to replace DES, whose 56-bit key was already considered too short. The competition was deliberately open — 15 submissions, 5 finalists, three years of public cryptanalysis — to avoid the suspicion of a back door that had dogged DES (the alleged NSA key-shortening from 128 to 56 bits). Three properties had to hold: the algorithm must be a symmetric block cipher, the full design must be public, and key lengths of 128, 192, and 256 bits must be supported. Rijndael won over finalists including **Serpent** (Anderson, Biham, Knudsen), **Twofish** (Schneier et al.), **MARS** (IBM), and **RC6** (Rivest, Robshaw, Sidney, Yin) on the basis of security margin, performance on diverse platforms, and simplicity. Becoming **FIPS 197** in November 2001, AES now secures nearly every TLS connection, every WiFi WPA2/WPA3 frame, every IPsec ESP packet, every BitLocker drive, and every SSH session.

## The Concept

AES is a substitution-permutation network with a 128-bit state. Each round applies four invertible operations that together provide **confusion** (SubBytes, a non-linear byte substitution) and **diffusion** (ShiftRows and MixColumns, which spread one byte's influence across the entire state). The chapter walks the algorithm top-down: state, rounds, key schedule, S-box, and MixColumns.

### The state and the 4×4 byte matrix

A 128-bit block is held in a 4×4 array of bytes called the **state**. The bytes are filled **column-major**: the first four input bytes go into column 0, top to bottom, then the next four into column 1, and so on. Byte `s[r][c]` is at row `r`, column `c`. The plaintext is loaded once at the start and copied out as ciphertext at the end. The same matrix is used for the round key; the AddRoundKey step is a byte-wise XOR of `state` and `rk[round]`.

| Input byte index | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| State position | s[0][0] | s[1][0] | s[2][0] | s[3][0] | s[0][1] | s[1][1] | s[2][1] | s[3][1] | s[0][2] | s[1][2] | s[2][2] | s[3][2] | s[0][3] | s[1][3] | s[2][3] | s[3][3] |

### SubBytes: the AES S-box

SubBytes applies the same fixed 16×16 lookup table to every byte independently. The S-box is constructed as `b' = A · b^-1 + 0x63` in GF(2^8), where `b^-1` is the multiplicative inverse (with `0` mapped to `0`) and `A` is a fixed 8×8 binary matrix that decorrelates the output from the algebraic structure of the field. The construction guarantees:

- No fixed point (`S(x) ≠ x` for all `x`); no "anti-fixed point" (`S(x) ≠ x XOR 0xFF` for all `x`). The DES S-boxes (and Rijndael's earlier drafts) had fixed points that simplified differential cryptanalysis.
- Maximum algebraic degree 7 (over GF(2)) for the output bits as functions of the input bits, which defeats low-degree polynomial attacks.
- A balanced output distribution: each output value occurs exactly 16 times across the 256 inputs.

The inverse S-box (used in decryption) is computed by reversing the affine transform and applying the same multiplicative inverse.

### ShiftRows: permutation for inter-column diffusion

ShiftRows rotates row *i* of the state left by *i* bytes: row 0 is unchanged, row 1 is rotated left 1, row 2 by 2, row 3 by 3. This is the byte-level analog of the column permutation in classical ciphers; after ShiftRows, the four bytes of any one column are now in four different columns. MixColumns then re-mixes them, completing the diffusion. The combined effect is that **every output byte of round 1 depends on every input byte** — a property called *full diffusion* — which the chapter highlights with the "two-rounds-are-enough" result from the Daemen-Rijmen design paper.

### MixColumns: GF(2^8) matrix multiplication

MixColumns treats each column as a 4-element vector over GF(2^8) and multiplies it by a fixed circulant matrix:

```
[0x02 0x03 0x01 0x01]   [s[0,c]]   [s'[0,c]]
[0x01 0x02 0x03 0x01] · [s[1,c]] = [s'[1,c]]
[0x01 0x01 0x02 0x03]   [s[2,c]]   [s'[2,c]]
[0x03 0x01 0x01 0x02]   [s[3,c]]   [s'[3,c]]
```

The constants 0x02 and 0x03 are chosen because 0x02 is `x` in the AES polynomial `x^8 + x^4 + x^3 + x + 1` (0x11B), and 0x03 = 0x02 XOR 0x01 = `x + 1`. Both are invertible in GF(2^8). The matrix is constructed so that any linear combination of two columns is also a valid column under MixColumns; this guarantees that the operation is invertible (the inverse MixColumns uses the matrix with entries 0x0E, 0x0B, 0x0D, 0x09). The branch number of MixColumns is 5, the theoretical maximum for a 4×4 byte mixing layer.

### AddRoundKey: the only step that uses the key

AddRoundKey is a byte-wise XOR of the state with the round key. The first round has AddRoundKey as a pre-whitening step (XOR `rk[0]` before SubBytes); the last round skips MixColumns, so the round structure is:

```
state = plaintext
state ^= rk[0]
for r in 1..ROUNDS-1:
    SubBytes(state)
    ShiftRows(state)
    MixColumns(state)
    state ^= rk[r]
SubBytes(state)
ShiftRows(state)
state ^= rk[ROUNDS]
ciphertext = state
```

This "XOR-key-into-state-then-rotate" structure is what makes AES trivially invertible for decryption: decryption runs the rounds in reverse order, with the inverse S-box, inverse ShiftRows (rotate right), inverse MixColumns, and AddRoundKey unchanged (XOR is its own inverse).

### The key schedule

The key schedule expands a 16/24/32-byte key into 11/13/15 round keys of 16 bytes each. For AES-128, the schedule processes 4-byte words `w[i]`. The first 4 words are the key itself; for `i ≥ 4`:

- If `i mod 4 == 0`: `w[i] = w[i-4] XOR SubWord(RotWord(w[i-1])) XOR Rcon[i/4]`.
- Else: `w[i] = w[i-4] XOR w[i-1]`.

`RotWord` is a 1-byte left rotation of a 4-byte word, `SubWord` applies the S-box to each byte, and `Rcon[j] = [0x02^(j-1), 0, 0, 0]` in GF(2^8). The round constants ensure that round keys differ even when the cipher key is constant. AES-192 and AES-256 use longer Nk (key length in 32-bit words) and additional SubWord steps for security margin; AES-256 specifically uses 7-word "staggered" SubWord steps to defend against related-key attacks (no successful related-key attack on AES-256 has been published as of 2024).

### Why AES is still secure in 2025

The best published attack on AES-128 is a **biclique** (Bogdanov, Knudsen, Leander, Müller, Raghunathan, Vikkelsoe, 2011) that recovers an AES-128 key with time complexity **2^126.1** (a 2× improvement over brute force, not a practical break). For AES-192 the biclique attack reaches 2^189.9; for AES-256, 2^254.4. Side-channel attacks on AES implementations are a real and persistent problem (cache-timing, differential power analysis), and the entire AES-NI instruction set on x86 was designed to make those attacks much harder by running AES with constant-time, lookup-free instructions. Quantum brute-force via Grover's algorithm gives a square-root speedup, reducing AES-128's effective security to 2^64, which is why NIST initiated the **post-quantum cryptography** standardization in 2016 — the answer is **ML-KEM** (formerly Kyber) for key exchange and **ML-DSA** (formerly Dilithium) for signatures, not a replacement block cipher.

## Build It

`code/main.py` is a stdlib Python AES-128 implementation, round by round:

1. `gf_inverse(x)` — multiplicative inverse in GF(2^8) using extended Euclidean algorithm.
2. `sub_bytes(state)` and `inv_sub_bytes(state)` — S-box and inverse S-box, both built from `gf_inverse + affine`.
3. `shift_rows(state)` and `inv_shift_rows(state)`.
4. `mix_columns(state)` and `inv_mix_columns(state)` — 4×4 matrix multiplication over GF(2^8).
5. `key_expansion(key)` — produces 11 round keys (44 32-bit words) following the AES-128 schedule.
6. `aes_encrypt_block(plaintext, key)` and `aes_decrypt_block(ciphertext, key)`.
7. A `__main__` block that encrypts the FIPS 197 Appendix B test vector (`"3243f6a8885a308d313198a2e0370734"` under key `"2b7e151628aed2a6abf7158809cf4f3c"`, expected ciphertext `"3925841d02dc09fbdc118597196a0b32"`) and prints the result. The vector is the FIPS 197 spec's "test vector" — failure means the implementation is wrong.

## Use It

| AES variant | Block | Key | Rounds | Round keys | Effective security (classical) |
|---|---|---|---|---|---|
| AES-128 | 128 b | 128 b | 10 | 11 | 126.1 b (biclique), 64 b (Grover) |
| AES-192 | 128 b | 192 b | 12 | 13 | 189.9 b (biclique), 96 b (Grover) |
| AES-256 | 128 b | 256 b | 14 | 15 | 254.4 b (biclique), 128 b (Grover) |
| Rijndael (full) | 128-256 b | 128-256 b | 10/12/14 | Nk+1 | AES subset only |

AES is the encryption primitive behind TLS 1.2 (cipher suites `TLS_RSA_WITH_AES_128_CBC_SHA` and `TLS_RSA_WITH_AES_128_GCM_SHA256`), TLS 1.3 (`TLS_AES_128_GCM_SHA256`, `TLS_AES_256_GCM_SHA384`, `TLS_CHACHA20_POLY1305_SHA256`), SSH (`chacha20-poly1305@openssh.com` or `aes256-gcm@openssh.com`), IPsec ESP, WPA2/WPA3, BitLocker, FileVault, and S/MIME.

## Ship It

The `outputs/` directory will contain:

- `outputs/aes_known_answer.txt` — the FIPS 197 test vector with the program's result, formatted for visual comparison.
- `outputs/aes_state_trace.txt` — the state after each of the 10 rounds for the FIPS 197 vector.

Run with `python3 code/main.py`; no external dependencies.

## Exercises

1. **Verify the FIPS 197 test vector.** Encrypt `3243f6a8885a308d313198a2e0370734` with key `2b7e151628aed2a6abf7158809cf4f3c` and confirm the ciphertext is `3925841d02dc09fbdc118597196a0b32`. (Appendix B of FIPS 197.)
2. **Build the S-box from the multiplicative inverse.** Compute `gf_inverse(x)` for all 256 values of `x`, then apply the affine transform `b' = Mb XOR 0x63`, and check that `S(0x00) = 0x63` and `S(0x01) = 0x7c`.
3. **Diffusion test.** Encrypt a plaintext, then flip one bit of the input and re-encrypt. Show that the second ciphertext differs from the first in approximately half its bits, on average over many random inputs (the **Strict Avalanche Criterion**).
4. **Round count comparison.** Implement (or simulate) AES-128 with 1, 2, 3, and 10 rounds on a 100-block random plaintext set. Plot the bit-error distribution: 1 round is almost linear and easy to invert; 4+ rounds look like a random permutation.
5. **Key schedule walk.** For the FIPS 197 key, print the 11 round keys as 16-byte hex strings. Verify that `rk[10]` matches the value in FIPS 197 Appendix A.1.
6. **Inverse cipher.** Decrypt the FIPS 197 ciphertext with your decrypt routine. Confirm the result is the original plaintext byte-for-byte. (Most AES bugs first appear here.)

## Key Terms

| Term | Definition |
|---|---|
| Rijndael | AES cipher, designed by Daemen and Rijmen (1998). |
| FIPS 197 | Federal Information Processing Standard 197, AES (2001). |
| State | 4×4 byte matrix that holds the 128-bit block during processing. |
| S-box | 256-byte substitution table; built from GF(2^8) inverse plus affine transform. |
| GF(2^8) | Galois field with 256 elements; AES uses polynomial `x^8 + x^4 + x^3 + x + 1`. |
| SubBytes | Apply the S-box to each byte of the state. |
| ShiftRows | Rotate row *i* by *i* bytes left. |
| MixColumns | Multiply each column by a fixed 4×4 matrix over GF(2^8). |
| AddRoundKey | XOR the state with a round key. |
| Round key | A 16-byte subkey derived from the cipher key by the key schedule. |
| Key schedule | Algorithm that expands the cipher key into 11/13/15 round keys. |
| Rcon | Round constant; `Rcon[j] = [0x02^(j-1), 0, 0, 0]` in GF(2^8). |
| Biclique | 2011 attack reaching AES-128 with 2^126.1 work; not a practical break. |
| AES-NI | x86 instruction set extension (since 2010 Westmere) that runs AES in hardware. |
| Strict Avalanche Criterion | Each output bit flips with probability 1/2 when any single input bit is flipped. |

## Further Reading

- FIPS 197, *Advanced Encryption Standard (AES)*, NIST (2001). The full algorithm, including S-box derivation and test vectors.
- J. Daemen and V. Rijmen, *The Design of Rijndael: AES — The Advanced Encryption Standard*, Springer 2002.
- A. Bogdanov, D. Knudsen, G. Leander, C. Paar, A. Poschmann, M. Robshaw, Y. Seurin, C. Vikkelsoe, *Present and Future Cryptography, Part I: AES*, 2003.
- A. Bogdanov, L. R. Knudsen, G. Leander, C. Müller, S. Raghunathan, M. Robshaw, Y. Seurin, C. Vikkelsoe, *Biclique Cryptanalysis of the Full AES*, ASIACRYPT 2011.
- NIST SP 800-38A, *Recommendation for Block Cipher Modes of Operation* (2001) — the modes that sit on top of AES.
- Intel, *Intel Advanced Encryption Standard (AES) New Instructions Set*, 2010.
- NIST PQC standardization: FIPS 203 (ML-KEM, 2024), FIPS 204 (ML-DSA, 2024).
