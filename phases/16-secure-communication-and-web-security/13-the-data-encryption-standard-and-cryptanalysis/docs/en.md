# DES, Triple DES, and the Cryptanalysis That Broke Them

> DES (Data Encryption Standard) was adopted as **FIPS 46** in January 1977 after IBM's "Lucifer" cipher was reduced from 128 to 56 bits in classified discussions with the NSA. DES is a 16-round **Feistel** cipher operating on 64-bit blocks with a 56-bit key plus 8 parity bits. Each round applies an expansion `E` (32→48 bits), XOR with a 48-bit round key, eight fixed 6→4-bit **S-boxes**, and a 32-bit **P-box** permutation. The round keys are derived from a 56-bit register that is rotated and permuted per round. The structure is small enough to implement on a chip (the first hardware DES ran at 1 Mbit/s) but, with only 2^56 ≈ 7.2 × 10^16 keys, became vulnerable to **exhaustive key search**: Diffie and Hellman estimated in 1977 that a custom machine could break DES in one day for $20 million; the EFF **Deep Crack** built in 1998 found a DES key in 56 hours for under $250,000; COPACOBANA (2006) brought the cost below $10,000. **Triple DES (3DES, TDEA)** applies DES three times with two or three keys, written **EDE** (Encrypt-Decrypt-Encrypt) for backward compatibility: `C = E_K3(D_K2(E_K1(P)))`. The effective key length is 112 bits (two-key 3DES) or 168 bits (three-key 3DES), but the meet-in-the-middle attack on 2-key 3DES reduces effective security to about 80 bits of work. NIST finally **deprecated 3DES** in 2023 (FIPS 197 supersedes; SP 800-131A rev. 2). The 56-bit key plus the 8-bit parity design is the foundational case study in why the cryptographic community learned to demand public designs and to size keys against Moore's Law.

**Type:** Learn
**Languages:** Python (stdlib DES, 3DES, brute-force demonstrator), diagrams
**Prerequisites:** Block ciphers, Feistel structure, AES chapter as the modern contrast
**Time:** ~90 minutes

## Learning Objectives

- Implement a single DES round: 32-bit expansion, 48-bit subkey XOR, 8 S-box lookups, P-box permutation, and Feistel half-swap.
- Generate the DES subkeys for all 16 rounds from a 64-bit key (56 bits used, 8 parity bits discarded).
- Encrypt and decrypt 64-bit blocks under single DES, then chain three DES operations into EDE triple DES.
- Show the **avalanche effect**: a one-bit change in the key or plaintext flips approximately half the ciphertext bits.
- Quantify the **exhaustive key search**: simulate a 10,000-key/second brute-force on a 4-bit key as a proxy for 2^56.

## The Problem

In the 1970s the U.S. government needed a single unclassified cipher for the Federal Reserve, banking clearinghouses, military logistics, and diplomatic cables. IBM had a candidate called **Lucifer** (128-bit key, 128-bit block), but the NSA, in closed negotiations, asked IBM to reduce the key to 56 bits and to keep the S-box design criteria secret. Critics (notably Diffie and Hellman) argued the smaller key let NSA read DES traffic; defenders (notably NIST's later FIPS process) argued the design was still strong enough. Three decades of public cryptanalysis have shown:

- The S-boxes, while designed in secret, do not appear to contain a back door (Coppersmith, 1994, revealed the design criteria and showed the S-boxes were chosen for **differential cryptanalysis resistance** — a 1990 attack that IBM and NSA knew about in 1974, two decades before the open community).
- The 56-bit key is far too short for the 1990s, let alone the 2020s. AES with a 128-bit key is 2^72 times harder to brute-force than DES.

DES's lesson is not that it was a bad cipher — within its design parameters it is robust — but that **a public key length is a forward commitment**: every additional doubling of compute halves the key's useful life. Modern designs (AES with 128/192/256-bit keys) bake in 30+ years of headroom; DES's 56-bit key was already marginal in 1977 and broken by 1998.

## The Concept

DES is the canonical Feistel cipher. A Feistel cipher splits the block into two halves and applies a round function to one half, then XORs it with the other. The structure is invertible regardless of the round function's invertibility, which is the elegant trick that lets DES use non-invertible S-boxes.

### The 16-round Feistel structure

A 64-bit plaintext is permuted by an **Initial Permutation (IP)**, then split into `L_0` (left 32 bits) and `R_0` (right 32 bits). For rounds 1 to 16:

```
L_i = R_{i-1}
R_i = L_{i-1} XOR f(R_{i-1}, K_i)
```

After 16 rounds, the two halves are swapped (the final swap), and the **Inverse Initial Permutation (IP^-1)** produces the 64-bit ciphertext. Decryption uses the same structure with the round keys in reverse order: `K_16, K_15, ..., K_1`.

### The DES round function f(R, K)

The function takes a 32-bit `R` and a 48-bit round key `K_i`:

1. **Expansion E** — 32 bits → 48 bits by duplicating 16 of the 32 bits according to a fixed table.
2. **XOR with K_i** — bitwise XOR.
3. **S-box substitution** — 48 bits split into 8 groups of 6 bits; each group is fed to a fixed 4×16 S-box that returns 4 bits. The 6-bit input selects a row (top and bottom bits) and a column (middle 4 bits), giving a 4-bit output. The S-boxes are the only non-linear part of DES and the only place where the cipher can be attacked algebraically.
4. **Permutation P** — 32 bits permuted across 32 positions to spread S-box output.

The non-linearity of the S-boxes is what makes DES hard to invert without the key.

### The key schedule

The 64-bit key has 8 parity bits (one per byte, ignored). The 56 remaining bits are split into `C_0` and `D_0` (28 bits each). For round *i*, both halves are rotated left by the round's shift amount (1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1 bits), and the round key `K_i` is a 48-bit **Permuted Choice 2 (PC-2)** of the rotated register. The rotation amounts are designed so that each key bit is used in approximately 14 of the 16 rounds.

### Triple DES (EDE) and the meet-in-the-middle attack

Triple DES, codified in **ANSI X9.52** and FIPS 46-3, applies three DES operations: `C = E_K3(D_K2(E_K1(P)))`. The middle **decrypt** is there for backward compatibility — if `K_1 = K_2 = K_3`, you get single DES. With three independent keys, the search space is 2^168; with two keys (where `K_1 = K_3`), it is 2^112. **Meet-in-the-middle** reduces the effective security of two-key 3DES:

- An attacker pre-computes `E_K1(P)` for all 2^112 values of K1 and stores them in a hash table.
- The attacker computes `D_K2(C)` for all 2^112 values of K2.
- A match between any pair reveals the key. Time: ~2^112, space: ~2^112 block-storage.

This brings 2-key 3DES to about 80 bits of work, well below AES-128. NIST deprecated 3DES in 2023; the only remaining legitimate uses are in legacy financial protocols and in TLS 1.0/1.1 ciphersuites that are themselves deprecated.

### The cryptanalysis that broke DES

Three classes of attack on DES are historically important:

1. **Exhaustive key search.** 2^56 work. EFF's Deep Crack (1998) ran 1,856 custom chips at 60 MHz and found a key in 56 hours. COPACOBANA (2006, Universities of Bochum and Kiel) used 120 FPGAs and brought the cost below $10,000. By 2025, a determined attacker with a GPU cluster can break DES in minutes.
2. **Differential cryptanalysis (Biham and Shamir, 1990).** A chosen-plaintext attack that recovers a DES key with 2^47 chosen plaintexts and 2^47 work. The S-boxes are tuned so that this is the best known attack but it remains infeasible in practice. IBM knew about the attack in 1974 and designed the S-boxes to be resistant; the design was declassified by Coppersmith in 1994.
3. **Linear cryptanalysis (Matsui, 1993).** A known-plaintext attack that recovers a DES key with 2^43 known plaintexts and 2^43 work. The first cryptanalytic attack on DES that was practical in a research setting, though still infeasible against a real adversary who controls only ciphertext.

These two cryptanalytic techniques reshaped modern cipher design: every modern cipher (AES, ChaCha20, Twofish) is deliberately designed to resist both differential and linear cryptanalysis. The "wide trail strategy" of AES specifically proves a lower bound on the number of active S-boxes in any differential or linear characteristic.

## Build It

`code/main.py` provides a stdlib DES implementation plus a 3DES wrapper:

1. `_permutation(table, bits)` — apply a fixed permutation table to a bit list.
2. `sbox_lookup(bits6)` — apply the 8 DES S-boxes.
3. `des_round(left, right, subkey)` — one Feistel round.
4. `key_schedule(key64)` — 16 × 48-bit subkeys from a 64-bit key.
5. `des_encrypt_block(block, key)` and `des_decrypt_block(block, key)`.
6. `tdes_encrypt(block, k1, k2, k3)` and `tdes_decrypt(block, k1, k2, k3)` — EDE.
7. `__main__` that verifies a **FIPS 46-2** known-answer test vector, then runs a 4-bit-key brute-force demo (1,000 key trials per second, 2^4 = 16 keys; scales to 2^56 by Moore's Law in the documentation).

Run with `python3 code/main.py`. No external dependencies.

## Use It

| DES variant | Block | Key | Effective security | Status |
|---|---|---|---|---|
| DES | 64 b | 56 b | ~56 b (brute) | **Withdrawn** NIST 2005 |
| 3DES (2-key EDE) | 64 b | 112 b (K1=K3) | ~80 b (meet-in-the-middle) | **Deprecated** NIST 2023 |
| 3DES (3-key EDE) | 64 b | 168 b | ~112 b | **Deprecated** NIST 2023 |
| AES-128 | 128 b | 128 b | ~126 b | **Recommended** |
| AES-256 | 128 b | 256 b | ~254 b | **Recommended** for long-term |

DES is still found in:
- Legacy **TLS 1.0/1.1** cipher suites (`SSL_DES_*`), all disabled in TLS 1.3.
- **Kerberos v5** still offers `des-cbc-md5` and `des3-cbc-sha1-kd` encryption types, both deprecated by RFC 6649.
- **WiFi WEP** uses RC4 over a 24-bit IV; the same generation as DES and just as broken.
- **Bitcoin** uses double-SHA-256 and secp256k1, not DES, but the original "Bitcoin mining" SHA-256 ASICs are conceptually a follow-on to the EFF's DES-breaking hardware.

## Ship It

The outputs/ directory contains:

- `outputs/des_known_answer.txt` — FIPS 46-2 test vector comparison.
- `outputs/des_avalanche.txt` — avalanche bit-difference statistics for 1-bit key and plaintext flips.
- `outputs/des_brute_force.txt` — small-scale brute-force trace (2^4 keys at 1000 keys/sec).

Run with `python3 code/main.py`; all three are produced on each run.

## Exercises

1. **FIPS 46-2 known-answer test.** Encrypt `4E6F77206973207468652074696D65` (ASCII "Now is the time") with key `4B595F4E4F575F524F434B4552` ("KYF_NOW_ROCKER" without parity) and confirm ciphertext is `3FA40E8A984D4815`.
2. **Avalanche test.** Encrypt 64 random 64-bit plaintexts under a fixed key, then flip the LSB of the key and re-encrypt. Count the bit differences — they should cluster near 32 with a standard deviation of about 4.
3. **3DES EDE round-trip.** Encrypt a plaintext under 3DES with three independent keys, then decrypt with the same keys. Verify the result is the plaintext.
4. **Brute-force scale-out.** Run the demo with 1, 2, 3, 4, and 5-bit keys. Plot time-to-break as a function of `2^n`. Extrapolate to 2^56 using a model `t(n) = c * 2^n`; the constant `c` is the time per key on your machine. Compare to the EFF Deep Crack's actual rate.
5. **S-box linearity check.** For each of the 8 DES S-boxes, count the number of input bits that linearly correlate with each output bit. The maximum correlation should be small (≤ 8/64, 12.5%) — if any S-box shows stronger linearity, that is a known weakness.
6. **DES-X.** Implement DES-X: `C = K3 XOR DES_K2(P XOR K1)`. Show why this construction resists **meet-in-the-middle** at the cost of two additional 64-bit XOR keys (it is not a substitute for AES but it shows the design space).

## Key Terms

| Term | Definition |
|---|---|
| DES | Data Encryption Standard (FIPS 46, 1977). 64-bit blocks, 56-bit key, 16 Feistel rounds. |
| Feistel network | Structure that splits a block into two halves and runs an arbitrary round function on one half per round. |
| S-box | Substitution table; the only non-linear part of DES (and many other ciphers). |
| FIPS 46 | Federal Information Processing Standard 46, the original DES (withdrawn 2005). |
| Lucifer | IBM's 128-bit-key precursor cipher; reduced to 56 bits for DES. |
| Deep Crack | EFF's 1998 custom hardware that broke DES in 56 hours. |
| COPACOBANA | 2006 academic DES-cracker; <$10,000 in FPGAs. |
| Triple DES / 3DES | EDE application of DES with 2 or 3 independent keys. |
| Meet-in-the-middle | Attack that halves the effective key length of multi-encryption. |
| Differential cryptanalysis | Chosen-plaintext attack (Biham-Shamir 1990) requiring 2^47 work on DES. |
| Linear cryptanalysis | Known-plaintext attack (Matsui 1993) requiring 2^43 work on DES. |
| Wide trail strategy | AES design principle that bounds the propagation of differential/linear trails. |
| DES-X | K1 XOR / DES / K2 XOR construction (Rivest 1984). |
| Initial Permutation | DES IP, a fixed bit-reordering of the plaintext; has no cryptographic value. |
| Subkey / round key | A 48-bit key derived for each of the 16 DES rounds. |

## Further Reading

- FIPS 46-3, *Data Encryption Standard (DES)*, NIST (1999) — withdraw notice 2005.
- NIST SP 800-131A Rev. 2, *Transitioning the Use of Cryptographic Algorithms and Key Lengths* (2023) — 3DES deprecation.
- E. Biham and A. Shamir, *Differential Cryptanalysis of DES-like Cryptosystems*, CRYPTO 1990.
- M. Matsui, *Linear Cryptanalysis Method for DES Cipher*, EUROCRYPT 1993.
- D. Coppersmith, *The Data Encryption Standard (DES) and Its Strength Against Attacks*, IBM J. Res. Dev. 1994.
- EFF, *Cracking DES: Secrets of Encryption Research, Wiretap Politics, and Chip Design* (1998).
- S. Kumar, C. Paar, J. Pelzl, G. Pfeiffer, A. Rupp, M. Schimmler, *How to Break DES for EUR 8,980*, 2006 (COPACOBANA).
- A. Biryukov and C. Namprempre, *Advanced Meet-in-the-Middle Attacks on Block Ciphers*, 2007.
