# AES (Rijndael) Round Structure

> AES (FIPS 197) replaced DES as the U.S. government standard block cipher in 2001 after NIST's open 1997–2000 competition. The winner was Rijndael, by two Belgian cryptographers (Joan Daemen and Vincent Rijmen). AES works on 128-bit blocks with 128-, 192-, or 256-bit keys, and its 10-round structure is small enough to reason about end-to-end. Each round applies four operations — SubBytes (a single 256-entry S-box), ShiftRows (rotate each of four rows left by 0,1,2,3 bytes), MixColumns (a GF(2^8) matrix multiply per column), and AddRoundKey (XOR with the round key). A round-key schedule derives 11 round keys from the initial 16-byte key. This lesson implements the full AES-128 round structure in pure Python: the S-box, ShiftRows, MixColumns, the key schedule, and the encrypt/decrypt functions, validated against the FIPS 197 Known Answer Test vectors.

**Type:** Build
**Languages:** Python
**Prerequisites:** Lesson 14 (DES), bitwise XOR, modular arithmetic
**Time:** ~90 minutes

## Learning Objectives

- Implement the AES S-box (`SubBytes`) as a single 256-entry table and apply it to a 16-byte state.
- Implement `ShiftRows` so row `i` is rotated left by `i` bytes for `i = 0..3`.
- Implement `MixColumns` using the GF(2^8) matrix `[[2,3,1,1],[1,2,3,1],[1,1,2,3],[3,1,1,2]]` and irreducible polynomial `x^8 + x^4 + x^3 + x + 1` (0x11B).
- Implement the AES-128 key schedule producing 11 round keys from a 16-byte key.
- Verify the implementation passes the FIPS 197 Known Answer Tests for AES-128.
- Recognize why AES's design is provably stronger than DES: larger block, larger key, no parity bits, fewer rounds with more diffusion per round.

## The Problem

You need a symmetric block cipher that will resist brute force for the next 30 years. DES is broken in its single-key form and 3DES is deprecated. AES-128 has a 128-bit key (3.4 × 10^38 possible keys), a 128-bit block, and a clean algebraic structure that has been beaten on by every academic cryptanalyst since 1998 without a practical break.

You also need to understand what is happening inside it — auditors and security engineers routinely read cipher implementations to look for timing side channels, weak key schedules, or accidental use of ECB mode. This lesson builds the cipher from tables so you can see exactly what it does.

## The Concept

### The state, the block, and the key

AES operates on a 4×4 byte matrix called the **state**:

```
s_00 s_04 s_08 s_12     <- column 0 (bytes 0..3 of the block)
s_01 s_05 s_09 s_13     <- column 1 (bytes 4..7)
s_02 s_06 s_10 s_14     <- column 2 (bytes 8..11)
s_03 s_07 s_11 s_15     <- column 3 (bytes 12..15)
```

The block is loaded column-major: `state[r][c] = block[4*c + r]`. After all rounds, the state is read back into the block in the same column-major order.

### The four round operations

For each of the 10 rounds (numbered 1..10, with an extra pre-round `AddRoundKey`):

1. **SubBytes** — replace each byte with `SBOX[b]`. The S-box is a single 256-entry table derived from the affine transform `y = A · x^{-1} + 0x63` over GF(2^8). It is the only nonlinear component of AES.
2. **ShiftRows** — rotate row `r` left by `r` bytes. Row 0 stays, row 1 shifts by 1, row 2 by 2, row 3 by 3. This provides inter-column diffusion.
3. **MixColumns** — multiply each column by the fixed 4×4 matrix over GF(2^8). Provides intra-column diffusion. *Skipped on the last round.*
4. **AddRoundKey** — XOR the state with the round key. The simplest step, but it is what binds the cipher to the key.

```
Round i:  SubBytes -> ShiftRows -> MixColumns (if i < 10) -> AddRoundKey
Pre:                                  XOR state with rk[0]
```

### The key schedule (AES-128)

Eleven round keys, each 16 bytes (128 bits), derived from the 16-byte master key. The first round key is the master key itself. To produce the next round key:

```
for i in 1..10:
    prev = rk[i-1]
    # take last 4 bytes, rotate left by 1
    rot = prev[1], prev[2], prev[3], prev[0]
    # apply S-box
    sub = SBOX[rot[0]], SBOX[rot[1]], SBOX[rot[2]], SBOX[rot[3]]
    # XOR with round constant
    rcon = RCON[i]
    first_word = sub[0] XOR rcon, sub[1], sub[2], sub[3]
    # XOR with the first word of prev
    rk[i] = (first_word XOR prev[0..3]) ++
            (rk[i][0..3] XOR rk[i-1][4..7]) ++
            (rk[i][4..7] XOR rk[i-1][8..11]) ++
            (rk[i][8..11] XOR rk[i-1][12..15])
```

`RCON[i] = (2^(i-1) in GF(2^8), 0, 0, 0)`. The doubling in GF(2^8) is the same operation used in `MixColumns`.

### Why AES is fast

DES does bit-level work: 32-bit halves, S-boxes on 6-bit chunks, bit permutations. AES works on whole bytes: 256-entry table lookups, byte rotations, GF(2^8) multiplications. On modern CPUs:

- A software AES implementation hits ~700 Mbps on a 2-GHz core (chapter §8.2.2).
- AES-NI hardware instructions on Intel/AMD chips run at >5 Gbps per core.
- AES is in the instruction set of many ARM chips too.

The combination of byte-level parallelism and dedicated hardware makes AES the cheapest strong cipher to deploy at scale.

### Why 10 rounds is enough

Each round of AES diffuses and confuses. Two full rounds provide full diffusion: every output bit depends on every input bit. Ten rounds add a safety margin against future cryptanalytic breakthroughs and against partial-round attacks on reduced AES (e.g. SQUARE / integral attacks on 6-round AES-128, which do not extend to the full 10).

### Decryption

Decryption is the inverse of encryption in reverse order:

```
Inverse AddRoundKey -> Inverse MixColumns -> Inverse ShiftRows -> Inverse SubBytes
```

Equivalently, you can encrypt with modified round keys and modified MixColumns/SubBytes tables. The lesson exposes both for clarity.

## Build It

The implementation lives in `code/main.py` (≈250 lines). It exposes:

- `SBOX`, `INV_SBOX`, `RCON` — full FIPS 197 tables (256 entries each for S-boxes).
- `sub_bytes(state)`, `inv_sub_bytes(state)`, `shift_rows(state)`, `inv_shift_rows(state)`.
- `mix_columns(state)`, `inv_mix_columns(state)`.
- `key_schedule_128(key16)` — produces 11 round keys.
- `aes_encrypt_block(block16, key16)` — full AES-128 encryption.
- `aes_decrypt_block(block16, key16)` — full AES-128 decryption.
- `fips_kat()` — runs the FIPS 197 Appendix C.1 test vectors.
- `demo_round_trace()` — shows the state after each round for one block.

Verify the implementation against the FIPS 197 KAT:

```python
from main import fips_kat
print("PASS" if fips_kat() else "FAIL")
```

Encrypt and decrypt a block:

```python
from main import aes_encrypt_block, aes_decrypt_block
key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
pt  = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")
ct  = aes_encrypt_block(pt, key)
print(ct.hex())
assert aes_decrypt_block(ct, key) == pt
```

Watch the round trace:

```python
from main import demo_round_trace
demo_round_trace()
```

## Use It

| Function | Real-world counterpart | Notes |
|----------|------------------------|-------|
| `aes_encrypt_block` | OpenSSL `EVP_aes_128_ecb`, Intel AES-NI `aesenc` | Real libraries use hardware acceleration. |
| `SBOX` / `INV_SBOX` | FIPS 197 §5.1.1 (inverse S-box §5.3.2) | The exact tables; never modify them. |
| `key_schedule_128` | FIPS 197 §5.2 (Key Expansion) | Real implementations precompute all 11 round keys once. |
| `mix_columns` | FIPS 197 §5.1.3 (MixColumns) | Real implementations use lookup tables for `xtime` to avoid per-byte computation. |
| `fips_kat` | NIST CAVP test vectors | Every conformant AES implementation must pass these. |

The lesson's implementation runs at ~5,000 blocks/second in pure Python. AES-NI runs at millions per second per core.

## Ship It

A reusable artifact for cryptography courses lives at `outputs/prompt-aes-round-structure.md`. It includes the FIPS 197 test vector, three round-trace examples, and a comparison table of AES-128 / AES-192 / AES-256 round counts. Reuse it when introducing AES to engineers migrating off DES or 3DES.

## Exercises

1. Verify that AES encryption followed by AES decryption with the same key recovers the plaintext on a 10-block message in ECB mode.
2. Implement `aes_encrypt_block` and `aes_decrypt_block` for AES-256 (14 rounds, 15 round keys, modified key schedule) and verify it round-trips.
3. Implement `xtime(b)` for GF(2^8) doubling and rewrite `mix_columns` using only `xtime` and XOR.
4. Show that the AES S-box is a permutation (bijection) on {0..255} by computing `INV_SBOX[SBOX[b]] == b` for all `b`.
5. Implement CTR mode on top of `aes_encrypt_block` and compare its throughput to ECB mode on a 1 MB payload.
6. Time `aes_encrypt_block` on your machine and estimate how long a brute-force attack would take at the measured rate; contrast with the EFF DES brute-force (1998).

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| AES | "Advanced Encryption Standard" | Rijndael; FIPS 197; 128-bit block, 128/192/256-bit key. |
| State | "Working buffer" | The 4×4 byte matrix AES operates on. |
| S-box | "SubBytes table" | Single 256-entry nonlinear permutation. |
| ShiftRows | "Rotate the rows" | Row `r` rotated left by `r` bytes. |
| MixColumns | "Mix each column" | GF(2^8) matrix multiply per column. |
| AddRoundKey | "XOR with the key" | State XOR round key. |
| Round key | "Per-round subkey" | 16 bytes; 11 round keys for AES-128. |
| GF(2^8) | "Finite field of 8 bits" | Bytes with XOR as addition; multiplication mod x^8+x^4+x^3+x+1. |
| xtime | "Double in GF(2^8)" | Multiply by 2 with reduction by 0x11B if overflow. |
| AES-NI | "Hardware AES" | Intel/AMD instructions for AES; billions of ops per second per core. |

## Further Reading

- Tanenbaum, *Computer Networks*, Chapter 8 (this chapter).
- FIPS 197 — *Advanced Encryption Standard (AES)*, November 2001.
- Daemen, J., and Rijmen, V., *The Design of Rijndael* (2002).
- NIST SP 800-38A — *Recommendation for Block Cipher Modes of Operation*.
- RFC 5246 — *The TLS Protocol*, §6.3 cipher suite definitions.
- Ferguson, N., Schneier, B., and Kohno, T., *Cryptography Engineering* (2010).