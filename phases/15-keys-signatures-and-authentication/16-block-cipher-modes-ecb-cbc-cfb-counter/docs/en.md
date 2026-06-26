# Block Cipher Modes: ECB, CBC, CFB, and Counter Mode

> Any block cipher — DES, 3DES, AES — is just a keyed permutation on a fixed-size block. Without a *mode of operation*, encrypting each block independently yields **ECB mode**, which is famously broken: the chapter's bonus-fiasco shows Leslie copying Kim's encrypted bonus block onto her own record and pocketing the difference. CBC, CFB, OFB, and CTR modes chain blocks together so that the same plaintext block produces different ciphertext depending on its position, and tampering with one block destroys all subsequent blocks. This lesson implements all five modes on top of the AES-128 block from lesson 15, encrypts the canonical 16-block "Tux" image in each mode, and demonstrates the attacks: ECB leaks structure, CBC bit-flipping lets an attacker rewrite chosen plaintext bits, and CTR nonce reuse collapses the keystream. You will see exactly why TLS, IPsec, and disk encryption all forbid ECB and require random IVs for CBC/GCM.

**Type:** Lab
**Languages:** Python, packet traces
**Prerequisites:** Lessons 14 (DES), 15 (AES), bitwise XOR
**Time:** ~90 minutes

## Learning Objectives

- Implement ECB, CBC, CFB-8, OFB, and CTR modes around any block cipher.
- Demonstrate ECB's structure leakage: encrypt the 16-block Tux image in ECB and see the penguin silhouette survive.
- Implement CBC bit-flipping: show how an attacker who can XOR a chosen delta into ciphertext block `i` flips the corresponding plaintext bits in block `i+1`.
- Implement CTR mode with explicit nonce handling, and show that nonce reuse leaks the XOR of two plaintexts.
- Choose the correct mode for random-access (disk) vs streaming (TLS record) vs authenticated (GCM) workloads.
- Recognize the IV requirements for CBC (uniformly random, transmitted in plaintext) and CTR (unique per message under the same key).

## The Problem

You have just shipped a product that encrypts customer records with AES-128 in ECB mode because it was the simplest thing to implement. A security review surfaces a problem: an attacker who steals the encrypted file can rearrange, copy, and delete blocks at will, because each block decrypts independently. They swap their own salary field with the CEO's salary field, and the system accepts the modified ciphertext.

The chapter (§8.2.3) gives Leslie's bonus-block swap as the canonical example. The fix is a chaining mode: CBC adds an XOR with the previous ciphertext block before encryption, so any modification propagates and corrupts subsequent blocks in a detectable way.

But CBC brings its own footguns: a 1-bit flip in ciphertext block `i` corrupts block `i` entirely *and* flips the corresponding plaintext bit in block `i+1` — a "CBC bit-flipping" attack. CTR mode avoids the propagation but introduces a strict nonce-uniqueness requirement. The lesson builds all five modes and the attacks against each, so the trade-offs are visible.

## The Concept

### ECB — Electronic Code Book

```
C_i = E_K(P_i)
P_i = D_K(C_i)
```

Each block encrypted independently with the same key. **Identical plaintext blocks produce identical ciphertext blocks**, so structure leaks. The chapter's bonus file is a one-line example; the famous Tux image shows the entire silhouette. ECB is *never* used for anything beyond single random keys.

### CBC — Cipher Block Chaining

```
C_0 = E_K(P_0 XOR IV)
C_i = E_K(P_i XOR C_{i-1})   for i >= 1
```

The IV (Initialization Vector) is a uniformly random block, sent in plaintext with the ciphertext. Each ciphertext block depends on every previous plaintext block, so rearranging ciphertext blocks destroys everything from the moved block onward. CBC requires the block cipher only in the forward direction during encryption, but during decryption it runs the cipher in both directions (the recipient computes `D_K(C_i)`, then XORs `C_{i-1}` to recover `P_i`).

The IV must be unpredictable to the attacker. If the attacker can predict the IV, they can craft a chosen-ciphertext attack; if the attacker can control the IV, they can prepend a chosen plaintext block. NIST SP 800-38A §6.2 mandates a random IV.

### CBC bit-flipping

If the attacker can XOR `Δ` into ciphertext block `C_{i-1}`, then `P_i = D_K(C_i) XOR C_{i-1}` becomes `D_K(C_i) XOR (C_{i-1} XOR Δ) = P_i XOR Δ`. They flipped the corresponding bits in `P_i` without knowing the key. The fix is a MAC over the entire ciphertext (HMAC-SHA256, or use an authenticated mode like GCM).

### CFB — Cipher Feedback (8-bit mode)

```
shift_register = IV
for each plaintext byte P_i:
    O_i = E_K(shift_register)
    C_i = P_i XOR leftmost_byte(O_i)
    shift_register = shift_register << 8 | C_i
```

A self-synchronizing stream cipher built from a block cipher. Each ciphertext byte depends on the previous `n` ciphertext bytes (where `n` is the cipher's block size). A 1-bit transmission error corrupts `n` bytes of plaintext (the bytes while the bad bit is in the shift register), then self-corrects.

### OFB — Output Feedback

```
O_0 = E_K(IV)
O_i = E_K(O_{i-1})
C_i = P_i XOR O_i
```

A synchronous stream cipher. The keystream is independent of plaintext and ciphertext, so a transmission error corrupts only the corresponding plaintext byte. Both endpoints must run the block cipher only in the forward direction.

### CTR — Counter Mode

```
C_i = P_i XOR E_K(IV + i)
```

The block cipher encrypts `IV+0`, `IV+1`, `IV+2`, … and the outputs form the keystream. CTR has every property you want for random access: decrypt block `n` without touching blocks `0..n-1`. It is the basis for disk encryption (AES-CTR with ESSIV) and for AEAD constructions (AES-GCM = AES-CTR + GHASH).

CTR's fatal weakness is nonce reuse: if two messages share `(K, IV)`, they share the keystream, and `C_1 XOR C_2 = P_1 XOR P_2`. The 2013 Dual EC DRBG scandal showed that some real systems had backdoored nonces that forced reuse. The lesson ships a `ctr_encrypt(plaintext, key, nonce)` that fails loudly on nonce reuse.

### Why GCM wins

Every modern protocol (TLS 1.3, IPsec ESP, QUIC, SSH chacha20-poly1305) uses an *authenticated* mode: AES-GCM or ChaCha20-Poly1305. These combine CTR-style encryption with a polynomial MAC (GHASH or Poly1305) over the ciphertext, giving confidentiality *and* integrity in one pass. The chapter covers AES-CTR explicitly; GCM is the natural extension.

### Mode selection cheat sheet

| Use case | Recommended mode | Why |
|----------|-------------------|-----|
| Disk encryption (random access) | AES-XTS or AES-CTR with ESSIV | Random read/write per block. |
| Network record (TLS, SSH) | AES-GCM, ChaCha20-Poly1305 | Authenticated encryption; covers bit-flipping. |
| Streaming with self-sync | AES-CFB-8 | Tolerates bit errors; rarely used now. |
| Single-block random key | AES-ECB | Safe only for keys, never for messages. |
| Hardware without AES-NI | AES-CTR + separate HMAC | Avoids CBC's bit-flipping surface. |

## Build It

The lab lives in `code/main.py` (≈230 lines). It exposes:

- `BlockCipher` protocol — any object with `encrypt(block, key)` / `decrypt(block, key)`.
- `aes_ecb(cipher, pt, key)`, `aes_cbc(...)`, `aes_cfb8(...)`, `aes_ofb(...)`, `aes_ctr(...)`.
- `cbc_bit_flip(ct, key, iv, target_block, delta)` — the chosen-ciphertext attack.
- `ctr_nonce_reuse_demo()` — encrypt two plaintexts with the same nonce and recover `P_1 XOR P_2`.
- `ecb_penguin_demo()` — encrypts the canonical 16-block "Tux" image in ECB and CBC, shows the silhouette leak.

Run all five modes on a multi-block message:

```python
from main import aes_ecb, aes_cbc, aes_cfb8, aes_ofb, aes_ctr, AES_BLOCK
key = bytes(range(16))
iv  = bytes(range(16, 32))
pt  = b"Hello, AES modes! " * 4
ct_ecb = aes_ecb(pt, key)
ct_cbc = aes_cbc(pt, key, iv)
ct_cfb = aes_cfb8(pt, key, iv)
ct_ofb = aes_ofb(pt, key, iv)
ct_ctr = aes_ctr(pt, key, iv[:12], counter_start=1)
```

Demonstrate CBC bit-flipping:

```python
from main import aes_cbc, aes_cbc_decrypt, cbc_bit_flip
# encrypt a known plaintext
pt = b"amount=0000;user=alice" + b"\x00" * 48  # pad to 64 bytes
key = b"\x42" * 16
iv = b"\x01" * 16
ct = aes_cbc(pt, key, iv)
# attacker XORs delta into block 0 -> block 1 plaintext flips predictably
modified = cbc_bit_flip(ct, key, iv, target_block=1, delta=0x10)
print(aes_cbc_decrypt(modified, key, iv))
```

Demonstrate CTR nonce reuse:

```python
from main import ctr_nonce_reuse_demo
ctr_nonce_reuse_demo()
```

ECB penguin demo:

```python
from main import ecb_penguin_demo
ecb_penguin_demo()
```

## Use It

| Function | Real-world counterpart | Notes |
|----------|------------------------|-------|
| `aes_ecb` | OpenSSL `EVP_aes_128_ecb` | Use only for single-block keys. |
| `aes_cbc` | OpenSSL `EVP_aes_128_cbc` | Requires random IV per message. |
| `aes_cfb8` | OpenSSL `EVP_aes_128_cfb8` | Self-synchronizing stream. |
| `aes_ofb` | OpenSSL `EVP_aes_128_ofb` | Synchronous stream. |
| `aes_ctr` | OpenSSL `EVP_aes_128_ctr` | Fast, parallelizable, random-access. |
| `cbc_bit_flip` | POODLE, BEAST (CBC-mode attacks) | Mitigated by authenticated encryption. |
| `ctr_nonce_reuse_demo` | 2013 Dual EC DRBG incident | Why deterministic IVs are dangerous. |
| `ecb_penguin_demo` | The classic Wikipedia ECB image | Visual proof of structure leakage. |

This lab uses AES-128 as the underlying block cipher; the same modes work identically with DES, 3DES, or ChaCha20.

## Ship It

A reusable artifact for cryptography training lives at `outputs/prompt-block-cipher-modes.md`. It includes the five mode diagrams from the chapter, the bonus-file attack walkthrough, and a mode-selection checklist for new product design. Reuse it when reviewing a TLS or IPsec configuration.

## Exercises

1. Modify `aes_cbc` to support ciphertext stealing (CTS-CBC) so the plaintext does not need to be block-aligned. Verify it round-trips.
2. Implement `aes_gcm_siv(key, nonce, plaintext, ad)` and verify it produces a different ciphertext for the same `(key, plaintext, nonce)` due to the IV-derived nonce.
3. Implement the POODLE attack: given a CBC ciphertext and partial control over plaintext padding, recover arbitrary plaintext bytes one at a time.
4. Implement `aes_cmac` (CBC-MAC) and use it to authenticate a CBC ciphertext; show that bit-flipping now fails because the MAC does not match.
5. Show that AES-CTR with the same nonce across two messages yields `C_1 XOR C_2 = P_1 XOR P_2`, and demonstrate a crib-drag attack to recover both plaintexts.
6. Modify `aes_cfb8` to CFB-128 and show the change in error-propagation behavior.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| ECB | "Electronic Code Book" | Independent per-block encryption; structure leaks. |
| CBC | "Cipher Block Chaining" | Each block XORed with previous ciphertext; needs random IV. |
| CFB | "Cipher Feedback" | Self-synchronizing stream cipher built from a block cipher. |
| OFB | "Output Feedback" | Synchronous stream cipher; keystream independent of data. |
| CTR | "Counter mode" | Encrypt `IV+i` to form keystream; random access; no padding. |
| IV | "Initialization Vector" | Per-message random block; sent in plaintext. |
| Nonce | "Number used once" | Per-message counter; must be unique under a given key. |
| Bit-flipping | "Modify chosen ciphertext bits" | In CBC, this flips plaintext in the next block. |
| Keystream reuse | "Same IV twice" | In CTR, leaks `P_1 XOR P_2`. |
| AEAD | "Authenticated encryption with associated data" | GCM, ChaCha20-Poly1305; encrypt + MAC in one pass. |

## Further Reading

- Tanenbaum, *Computer Networks*, Chapter 8 (this chapter).
- NIST SP 800-38A — *Recommendation for Block Cipher Modes of Operation*.
- NIST SP 800-38D — *Recommendation for Block Cipher Modes: Galois/Counter Mode (GCM)*.
- RFC 5246 — *The TLS Protocol*, §6.2.3.3 CBC modes and MAC.
- RFC 7539 — *ChaCha20 and Poly1305 for IETF Protocols*.
- Ferguson, N., Schneier, B., *Practical Cryptography* (2003) — the chapter that popularized "don't use ECB, don't roll your own MAC".