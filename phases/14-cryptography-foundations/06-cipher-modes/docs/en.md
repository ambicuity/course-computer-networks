# Cipher Modes

> A block cipher alone is a monoalphabetic substitution on big characters (128-bit for AES). Encrypt the same plaintext block 100 times with the same key and you get the same ciphertext 100 times — an attacker can copy-paste ciphertext blocks (Leslie swaps Kim's bonus block without knowing the key). Cipher modes solve this. **ECB** (Electronic Code Book): each block encrypted independently; identical plaintext blocks produce identical ciphertext blocks; no chaining; patterns leak; block-reorder attacks work. **CBC** (Cipher Block Chaining): each plaintext block XORed with the previous ciphertext block before encryption; first block XORed with a random IV; a swapped block garbles itself and the next block; cryptanalysis is harder; requires a full block before decryption. **CTR** (Counter Mode): encrypt IV, IV+1, IV+2... to produce a keystream, XOR with plaintext; enables random access to any block without decrypting predecessors; never reuse (key, IV) pairs or the keystream-reuse attack applies. **Stream cipher mode** (OFB): encrypt IV, then encrypt the output repeatedly to generate a keystream independent of data; 1-bit ciphertext error = 1-bit plaintext error. **GCM** (Galois/Counter Mode): CTR encryption plus an authentication tag over the ciphertext and associated data; provides confidentiality AND integrity in one pass; the TLS 1.3 and IPsec default. The rule: never use ECB for multi-block data; always use an authenticated mode (GCM or CBC+HMAC).

**Type:** Build
**Languages:** Python, crypto diagrams
**Prerequisites:** Lesson 05 DES to AES
**Time:** ~90 minutes

## Learning Objectives

- Encrypt multi-block data with ECB and demonstrate the identical-block leak and the block-reorder attack.
- Encrypt with CBC using a random IV and show that a swapped block garbles two blocks.
- Encrypt with CTR and demonstrate random-access decryption of a single block.
- Explain why reusing (key, IV) in CTR or stream-cipher mode enables the keystream-reuse attack.
- Describe GCM as CTR + authentication tag and why authenticated encryption is the modern default.

## The Problem

Your company encrypts an employee bonus file as 16 eight-byte DES blocks. Each 32-byte record has 16 bytes name, 8 bytes position, 8 bytes bonus. Leslie can access the encrypted file before it reaches the bank. In ECB mode, Leslie copies block 12 (Kim's bonus) over block 4 (Leslie's bonus) — without knowing the key — and gets a bigger Christmas bonus. The fix is a cipher mode that chains blocks so reordering produces garbage.

## The Concept

### ECB (Electronic Code Book Mode)

The straightforward mode: break plaintext into consecutive blocks and encrypt each independently with the same key. The last block is padded to full size.

| Property | ECB |
|----------|-----|
| Identical plaintext blocks | Produce identical ciphertext blocks |
| Block reorder attack | Works: swap ciphertext blocks, swap plaintext blocks |
| Random access | Yes: decrypt any block independently |
| Parallelization | Yes: encrypt blocks in parallel |
| Pattern leakage | Yes: structure of plaintext (e.g., BMP header) is visible |

ECB is acceptable only for a single block or when plaintext has no repeated blocks. For any multi-block message with structure, ECB leaks patterns. The famous ECB penguin: encrypting the Linux Tux logo in ECB mode still shows the penguin outline in ciphertext.

### CBC (Cipher Block Chaining Mode)

Each plaintext block is XORed with the previous ciphertext block before encryption. The first block is XORed with a random IV (Initialization Vector), transmitted in plaintext alongside the ciphertext.

```
C_0 = E(P_0 XOR IV)
C_1 = E(P_1 XOR C_0)
C_2 = E(P_2 XOR C_1)
...
P_0 = IV XOR D(C_0)
P_1 = C_0 XOR D(C_1)
```

| Property | CBC |
|----------|-----|
| Identical plaintext blocks | Produce different ciphertext blocks (chaining) |
| Block reorder attack | Garbles the swapped block and the next one |
| Random access | No: must decrypt all preceding blocks first |
| Error propagation | 1-bit error in C_i garbles P_i and P_{i+1} |
| IV | Must be random and unpredictable; transmitted in plaintext |

CBC is the mainstay of non-authenticated encryption. The IV need not be secret but must be unpredictable (an attacker who predicts the IV can mount a chosen-plaintext attack). The `code/main.py` demo implements CBC with a toy block cipher.

### CTR (Counter Mode)

CTR mode turns a block cipher into a stream cipher. Instead of encrypting plaintext directly, encrypt a counter (IV, IV+1, IV+2, ...) to produce a keystream, then XOR the keystream with the plaintext.

```
C_0 = P_0 XOR E(IV)
C_1 = P_1 XOR E(IV + 1)
C_2 = P_2 XOR E(IV + 2)
```

| Property | CTR |
|----------|-----|
| Random access | Yes: decrypt block i by computing E(IV + i) |
| Parallelization | Yes: all keystream blocks independent |
| Error propagation | 1-bit error = 1-bit plaintext error |
| IV/nonce | Must NEVER repeat for the same key (keystream reuse) |
| No padding | Plaintext can be any length (XOR with keystream) |

CTR is the basis for modern authenticated modes (GCM). The critical rule: never reuse the same (key, IV) pair. If P_0 is encrypted with keystream K and later Q_0 is encrypted with the same K, the attacker XORs the two ciphertexts to get P_0 XOR Q_0 — the key is eliminated.

### Stream cipher mode (OFB)

Similar to CTR but the keystream is generated by repeatedly encrypting the previous output: K_0 = E(IV), K_1 = E(K_0), K_2 = E(K_1). The keystream is independent of the data, so it can be precomputed. A 1-bit ciphertext error causes only a 1-bit plaintext error (unlike CBC's 2-block garble).

### GCM (Galois/Counter Mode)

GCM = CTR encryption + GHASH authentication tag. CTR provides confidentiality; GHASH computes a polynomial hash over the ciphertext and associated data (AAD) under a hashing subkey derived from the key. The tag is appended to the ciphertext and verified before decryption is accepted.

| Property | GCM |
|----------|-----|
| Confidentiality | CTR mode (random access, parallel) |
| Integrity | GHASH tag (16 bytes, truncated to 12+ in TLS) |
| AAD | Supports authenticated associated data (headers, sequence numbers) |
| One-pass | Encrypt and authenticate simultaneously |
| Nonce | Must NEVER repeat (catastrophic tag forgery) |
| Standard | NIST SP 800-38D; TLS 1.3 and IPsec default |

GCM is the recommended mode for all new systems. If GCM is unavailable, use CBC + HMAC (encrypt-then-MAC). Never use unauthenticated CBC for network protocols — padding oracle attacks (POODLE, Lucky13) break it.

### Mode comparison summary

| Mode | Confidentiality | Integrity | Random Access | Parallel | IV/Nonce reuse risk |
|------|-----------------|-----------|---------------|----------|---------------------|
| ECB | Yes (weak) | No | Yes | Yes | N/A (no IV) |
| CBC | Yes | No | No | Encrypt only | IV predictable |
| CTR | Yes | No | Yes | Yes | Catastrophic (keystream reuse) |
| OFB | Yes | No | No | No | Catastrophic (keystream reuse) |
| GCM | Yes | Yes (tag) | Yes | Yes | Catastrophic (tag forgery) |

## Build It

1. Run `python3 code/main.py`. It implements ECB, CBC, and CTR with a toy block cipher, demonstrates the identical-block leak in ECB, shows CBC garbling on block swap, and demonstrates CTR random-access decryption.
2. Encrypt a message with repeated blocks in ECB and observe that ciphertext blocks repeat. Repeat in CBC and observe no repetition.
3. Swap two ciphertext blocks in CBC and observe the garbled plaintext.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|---------------------|
| ECB pattern leak | Identical plaintext blocks → identical ciphertext blocks | Ciphertext shows the same 16-byte pattern repeatedly |
| CBC chaining | Swapped block garbles two blocks | Attacker cannot extract a clean bonus block |
| CTR random access | Decrypt block 5 without touching blocks 0-4 | E(IV + 5) XOR C_5 = P_5, no chain needed |
| GCM authenticated | Tag mismatch on tampered ciphertext | Decryption rejects; no plaintext released |

## Ship It

This lesson produces `outputs/cipher-mode-selection-guide.md`: a decision table mapping use cases (disk encryption, network protocol, streaming, random-access file) to the correct mode, with IV/nonce generation rules and failure modes for each.

## Exercises

1. Encrypt the 32-byte bonus file from the chapter with ECB. Which ciphertext blocks are identical for Kim and Leslie? Perform the block-swap attack.
2. Re-encrypt with CBC using IV = 0x1234... Repeat the block swap. How many plaintext blocks are garbled? Why exactly two?
3. In CTR mode, you reuse IV=42 with the same key for two different messages. Capture both ciphertexts. Describe the exact attack that recovers both plaintexts.
4. GCM produces a 16-byte tag. What happens if the tag is truncated to 4 bytes? What is the forgery probability per attempt?
5. Why does TLS 1.3 mandate AEAD (GCM or ChaCha20-Poly1305) and forbid bare CBC? Name the padding oracle attack that killed CBC in TLS.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| ECB | "just encrypt each block" | Identical blocks leak; block-reorder attacks; never use for multi-block |
| IV | "random start" | Initialization vector; CBC needs unpredictable, CTR needs unique |
| CBC | "chain the blocks" | XOR each plaintext with previous ciphertext; garbles on swap |
| CTR | "counter keystream" | Encrypt counter to make keystream; random access; no padding |
| Keystream reuse | "same pad twice" | Catastrophic: XOR of two ciphertexts = XOR of two plaintexts |
| GCM | "authenticated encryption" | CTR + GHASH tag; confidentiality + integrity in one pass |
| AAD | "extra data to authenticate" | Associated data authenticated but not encrypted (headers) |
| Padding oracle | "tell me if padding is right" | Attacker learns plaintext bit by bit from padding error (POODLE) |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), Section 8.2.3
- NIST SP 800-38A — Block cipher modes (ECB, CBC, CFB, OFB, CTR)
- NIST SP 800-38D — GCM mode
- RFC 5116 — An Interface and Algorithms for Authenticated Encryption
- Bodo Möller, "Padding Oracle Attacks" — POODLE and Lucky13 analysis