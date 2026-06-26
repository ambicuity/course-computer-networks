# Cryptanalysis: Differential, Linear, Power, and Timing Attacks

> The chapter names four cryptanalytic developments that changed what "secure" means for a block cipher. **Differential cryptanalysis** (Biham and Shamir, 1990) tracks how specific bit-differences propagate through the rounds of a cipher, narrowing the key search from 2^56 to 2^47 for DES. **Linear cryptanalysis** (Matsui, 1993) finds linear approximations to the nonlinear S-boxes and breaks DES with 2^43 known plaintexts. **Power analysis** observes the electrical current a smart card draws while encrypting and reads the key off the supply pin. **Timing analysis** observes how long each round takes and infers which branches the code took. None of these attacks requires breaking the math; they exploit the *implementation*. This lesson implements toy differential and linear distinguishers against a 4-round mini-DES, builds a Hamming-weight power model for an AES S-box lookup, and demonstrates a constant-time comparison to defeat timing leaks. The point is not to break AES — that is impossible — but to understand why constant-time code, masking, and other side-channel countermeasures are non-negotiable in real products.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Lessons 14 (DES), 15 (AES), basic probability
**Time:** ~75 minutes

## Learning Objectives

- Implement a *difference distribution table* for the DES S-boxes and use it to mount a 4-round differential attack.
- Implement Matsui's linear cryptanalysis: build linear approximations from S-box bias, peel rounds off the cipher, recover a few key bits.
- Build a Hamming-weight power model and show how the model recovers the AES S-box index byte from a simulated power trace.
- Quantify timing leakage in a non-constant-time comparison and demonstrate how `hmac.compare_digest` defeats it.
- Articulate the constant-time programming rules: no table lookups indexed by secret data, no early returns, no variable-time arithmetic.
- Recognize that side-channel resistance is a property of the *implementation*, not the *algorithm*, and review NIST FIPS 140-3 requirements.

## The Problem

You have implemented AES-128 correctly per FIPS 197 and the test vectors pass. Your auditor says: "fine, but what about side channels?" You do not know what that means.

You start measuring how long your AES implementation takes to encrypt each block. Some blocks take 10% longer than others. You plot power consumption during encryption and see distinct spikes keyed to the S-box lookups. The math says AES is unbreakable; the silicon leaks the key anyway.

This lesson makes the threat concrete: build a toy cipher and a power/timing model, watch the key leak out of side channels, then apply the standard countermeasures and verify the leakage disappears.

## The Concept

### Differential cryptanalysis

The chapter (§8.2.5): "Differential cryptanalysis ... works by beginning with a pair of plaintext blocks differing in only a small number of bits and watching carefully what happens on each internal iteration as the encryption proceeds. In many cases, some bit patterns are more common than others, which can lead to probabilistic attacks."

Mechanically, an attacker:

1. Picks a difference `ΔP` between two plaintexts (e.g. one bit flipped at a known position).
2. Encrypts both `P` and `P ⊕ ΔP` under the unknown key `K`, getting `C` and `C'`.
3. Computes the output difference `ΔC = C ⊕ C'`.
4. Looks up `ΔC` in a *difference distribution table* (DDT) for the cipher's S-boxes.
5. For each candidate subkey that could have produced `ΔC`, increments a counter. The subkey with the highest counter is the right one.

The DDT for DES's S1 has 64 rows (input differences 0..63) and 64 columns, with entries being the number of input pairs that produce the corresponding output difference. Many entries are zero — the attacker eliminates those key candidates immediately.

Toy attack on a 4-round mini-DES with two S-boxes runs in < 1 second on a laptop. Full DES with 16 rounds and eight S-boxes is harder but was published by Biham and Shamir in 1990; their attack recovers a DES key with 2^47 chosen plaintexts.

### Linear cryptanalysis

Matsui (1993) found that XORing certain bits of plaintext and ciphertext gives a biased result for DES: about half the time the XOR is 0, but it deviates from 1/2 by 2^-21. Stacking this bias across rounds of approximation gives `Pr[P_x ⊕ C_y = K_z] = 1/2 + 2^-21`. With 2^42 known plaintexts (the reciprocal of the squared bias), the attacker recovers one bit of the last-round key. Repeat for the other bits; the full key falls out.

Toy attack: pick a 4-round mini-DES where the S-box has a known linear approximation table (LAT) with non-zero entries. Build a `linear_approximation` table mapping input-bit-masks to output-bit-mask biases. Sample enough plaintext-ciphertext pairs; the bias emerges from the noise.

### Power analysis

The chapter notes: "Computers typically use around 3 volts to represent a 1 bit and 0 volts to represent a 0 bit. Thus, processing a 1 takes more electrical energy than processing a 0."

The **Hamming weight model** says `power ∝ HW(byte)`. If the cipher performs a table lookup `SBOX[x]` where `x` is a secret-derived byte, the power trace's spike at that lookup reveals `HW(x)`. Across many traces, the attacker correlates each possible key-byte guess with the observed power and picks the best.

The lesson simulates this: a noise-free power trace is `HW(SBOX[key_byte ⊕ plaintext_byte])` for each of AES's 16 S-box lookups in round 1. With one trace, the attacker can guess each key byte from 256 candidates by checking which produces the observed spike pattern.

### Timing analysis

C code that does `if (key[i] & 1) { ... }` takes a different number of cycles on each branch. Over many trials, an attacker with a high-resolution clock can read off which bits of the key were 0 or 1.

Real-world example: the 2018 **Spectre** and **Meltdown** CPU vulnerabilities generalized this: even *speculative* execution left timing artifacts that revealed protected memory contents.

The defense is **constant-time code**: every code path takes the same number of cycles regardless of secret data. Rules:

- No `if secret: ...`.
- No table lookups indexed by secret data.
- No `memcmp(a, b, n)` for MAC verification; use `CRYPTO_memcmp` or `hmac.compare_digest` (constant-time comparison).
- No early returns inside loops over secret indices.

### Countermeasures

For differential/linear cryptanalysis:

- **More rounds.** AES-128 has 10 rounds; reduced-round attacks exist on 6-round AES but do not extend to the full 10.
- **Better S-boxes.** AES's S-box has maximal differential probability 4/256 and linear bias 16/128. ChaCha20's quarter-round has provably low differential bias.

For power/timing:

- **Masking.** XOR the secret with random `r`, do the computation, XOR `r` back at the end. Power no longer correlates with the secret.
- **Hiding.** Add dummy operations or shuffle the order so the signal-to-noise ratio falls below detection.
- **Constant-time code.** No data-dependent control flow.
- **Formal verification.** Tools like `dudect`, `ctgrind`, `valgrind --tool=memcheck` for AES timing, and `tvla` for power traces.

FIPS 140-3 §7.5 requires non-invasive attack testing (timing, power, fault injection) for level 3+ security modules. Common Criteria AVA_VAN.5 mandates high-resistance side-channel analysis.

## Build It

The lab lives in `code/main.py` (≈230 lines). It exposes:

- `mini_des_block(block32, key32, rounds=4)` — a stripped-down Feistel with two S-boxes for cryptanalysis demos.
- `ddt_sbox(sbox)` — difference distribution table for a 4-bit S-box.
- `lat_sbox(sbox)` — linear approximation table.
- `differential_attack(cipher, sbox, n_pairs)` — recover the last-round subkey.
- `linear_attack(cipher, lat, plaintexts, ciphertexts)` — recover a few key bits via Matsui-style piling-up.
- `power_trace(key_byte, plaintexts)` — simulate Hamming-weight power for AES SubBytes step.
- `correlate_power(trace, model)` — recover the secret byte from a single power trace.
- `timing_demo()` — show variable-time vs constant-time string comparison.

Differential cryptanalysis on the mini-DES:

```python
from main import mini_des_block, ddt_sbox, differential_attack
DDT = ddt_sbox([0xE, 0x4, 0xD, 0x1, 0x2, 0xF, 0xB, 0x8,
                0x3, 0xA, 0x6, 0xC, 0x5, 0x9, 0x0, 0x7])
key = 0xDEADBEEF
recovered = differential_attack(mini_des_block, DDT, n_pairs=200)
```

Power analysis on a single AES SubBytes lookup:

```python
from main import power_trace, correlate_power, AES_SBOX
key_byte = 0x42
plaintexts = list(range(256))
trace = power_trace(key_byte, plaintexts, AES_SBOX)
recovered = correlate_power(trace, AES_SBOX)
assert recovered == key_byte
```

Timing leak demonstration:

```python
from main import timing_demo
timing_demo()
```

## Use It

| Function | Real-world counterpart | Notes |
|----------|------------------------|-------|
| `mini_des_block` | Reference DES implementation | Stripped for clarity, not security. |
| `ddt_sbox` | Biham-Shamir DDT tables | The core data structure for differential attacks. |
| `linear_attack` | Matsui's 1993 attack on DES | Recovers DES key with 2^43 known plaintexts. |
| `power_trace` | ChipWhisperer capture | Real ChipWhisperer traces include jitter, clock drift, EM noise. |
| `correlate_power` | CPA, DPA attacks | Cross-correlation or Pearson coefficient on real traces. |
| `timing_demo` | `hmac.compare_digest`, `crypto_verify_16` | OpenSSL constant-time functions. |

The lesson uses a toy cipher and a noise-free power model. Real attacks need thousands of traces and statistical denoising; the structure is identical.

## Ship It

A reusable artifact for security training lives at `outputs/prompt-cryptanalysis-zoo.md`. It includes the DDT for DES S1, a power-trace example, and a side-channel review checklist for new products. Reuse it when onboarding to a hardware-security team.

## Exercises

1. Compute the DDT for the AES S-box and show its maximal entry is 4 (out of 256).
2. Implement the **Biham-Shamir** 3-round differential attack on the toy mini-DES and recover the full 32-bit key.
3. Use Matsui's piling-up lemma: combine four linear approximations with biases `2^-3`, `2^-4`, `2^-3`, `2^-4` to estimate the combined bias.
4. Add timing jitter to `timing_demo` and show that the variable-time leak survives ±10% noise but disappears at ±50%.
5. Implement a constant-time AES key schedule and verify it produces the same round keys as a naive implementation but with constant-time array accesses.
6. Use `dudect`-style statistics on `hmac.compare_digest` vs `==` for MAC verification: which one shows no timing bias across millions of trials?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Differential cryptanalysis | "Track plaintext differences" | Choose pairs with a fixed input XOR, observe output XOR bias. |
| Linear cryptanalysis | "Linear approximations" | Find XOR of input/output bits that is biased toward 0 or 1. |
| Power analysis | "Read the supply current" | DPA / SPA use the power trace correlated with a key-guess model. |
| Timing analysis | "Measure execution time" | Data-dependent branches or memory accesses leak via timing. |
| DDT | "Difference Distribution Table" | `DDT[Δin][Δout]` = number of inputs that produce the given output difference. |
| LAT | "Linear Approximation Table" | `LAT[a][b]` = (# pairs with input mask `a` and output mask `b` both 1) − 8. |
| Constant-time code | "No data-dependent branches" | Every code path takes the same number of cycles regardless of secret. |
| Masking | "XOR with random" | Splits a secret into random shares to defeat DPA. |
| Hiding | "Add dummy operations" | Reduces the signal-to-noise ratio below detection. |
| DFA | "Differential Fault Analysis" | Inject faults during encryption and analyze the wrong outputs. |

## Further Reading

- Tanenbaum, *Computer Networks*, Chapter 8 (this chapter).
- Biham, E., and Shamir, A., *Differential Cryptanalysis of the Data Encryption Standard* (1993).
- Matsui, M., *Linear Cryptanalysis Method for DES Cipher*, EUROCRYPT 1993.
- Kocher, P., Jaffe, J., Jun, B., *Differential Power Analysis*, CRYPTO 1999.
- Mangard, S., Oswald, E., Popp, T., *Power Analysis Attacks* (2007).
- NIST FIPS 140-3 — *Security Requirements for Cryptographic Modules*, §7.5 side-channel testing.
- Common Criteria AVA_VAN.5 — *Advanced methodical vulnerability analysis*.