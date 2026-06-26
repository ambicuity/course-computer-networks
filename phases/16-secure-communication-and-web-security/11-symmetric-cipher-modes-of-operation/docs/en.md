# Symmetric Block Cipher Modes of Operation

> A block cipher like AES or 3DES encrypts one fixed-size block at a time: 16 bytes for AES-128, 8 bytes for DES. But network traffic is not a single block — it is a multi-megabyte file, a streaming video session, a database row. The **mode of operation** is the rule that tells the encryptor how to chain (or not chain) those fixed-size blocks across an arbitrarily long message. The chapter introduces four classic modes defined in **NIST SP 800-38A (2001)**: **ECB (Electronic Code Book)**, **CBC (Cipher Block Chaining)**, **CFB (Cipher Feedback)**, and **OFB/CTR (Output Feedback / Counter)**. ECB is a flat monoalphabetic substitution and is the only mode in which identical plaintext blocks always produce identical ciphertext blocks — a fatal weakness that lets an attacker cut-and-paste ciphertext blocks to alter meaning (the "Leslie/Kim bonus" example). CBC XORs each plaintext block with the previous ciphertext block before encryption, defeating the cut-and-paste attack at the cost of needing a random Initialization Vector (IV). CFB turns the block cipher into a self-synchronizing stream cipher with 8-bit (or larger) granularity, useful when a byte at a time must be released. CTR turns it into a true stream cipher by encrypting a counter and XORing the result with plaintext; CTR is the basis of AES-GCM, the dominant authenticated-encryption mode on the modern web. Misuse of any of these modes (ECB for non-random plaintext, CTR/OFB with a reused nonce, CBC with a predictable IV, CBC without a MAC) has produced some of the most famous protocol failures in security history, from **TLS 1.0 CBC padding oracles** (Vaudenay 2002) to **CRIME/BREACH** to **HTTPoxy**.

**Type:** Learn
**Languages:** Python (stdlib ECB/CBC/CFB/CTR demo + cut-and-paste attack), diagrams
**Prerequisites:** AES or DES as a block cipher primitive, XOR, byte-string operations in Python
**Time:** ~90 minutes

## Learning Objectives

- Implement and compare ECB, CBC, CFB, and CTR modes on top of a toy 16-byte block cipher, and produce correctly framed ciphertext for multi-block plaintexts.
- Explain why ECB is a "big monoalphabetic substitution cipher": identical plaintext blocks yield identical ciphertext blocks, enabling cut-and-paste forgery.
- Show that CBC defeats cut-and-paste because block *i* depends on all earlier plaintext, but it still leaks the equality of prefixes when IVs collide.
- Describe CFB and CTR as stream ciphers built from a block cipher: both XOR a keystream with plaintext, and both catastrophically fail on (key, IV/nonce) reuse.
- Implement the **Leslie/Kim** block-cutting attack on ECB, including detection (a "block equality histogram" works on the famous ECB penguin bitmap).

## The Problem

A payroll team encrypts an end-of-quarter bonus file with AES-128 before mailing it to the bank. The team uses **ECB** because the developer copy-pasted a sample from a 2009 blog post. The encrypted file is 16 blocks of 16 bytes; nobody notices when, after the file leaves the payroll system but before it reaches the bank, block 12 is replaced with a copy of block 8. The bank decrypts everything, sees a valid payroll, and pays out a $100,000 bonus to an employee who was scheduled to receive a $5 bonus. The "encryption" did its job — the file is still gibberish without the key — but integrity is completely absent. ECB preserved *block identity* across the file, and an attacker who can rewrite the file blindly can rewrite meaning.

This is the same class of bug that bit **ECB-mode bitmap encryption** (the famous Linux Tux penguin whose encrypted form still shows the penguin), and the same logic that defeated WEP WiFi (keystream reuse in RC4-as-a-stream-cipher). The mode of operation is not a cosmetic choice: it is the difference between "the attacker can read this" and "the attacker can rewrite this without ever needing the key."

## The Concept

A block cipher `E_K(P)` maps one block to one block. A mode of operation specifies three things: (1) how to handle a plaintext longer than one block, (2) how to randomize the encryption (typically via a public IV), and (3) what unit of plaintext can be released to the consumer before the rest of the message arrives. The mode dictates the security properties you get — confidentiality only, or confidentiality plus (limited) integrity, or true stream-cipher behavior — and the failure modes you inherit.

### Why ECB is dangerous

ECB does the most obvious thing: split the plaintext into blocks and encrypt each independently with the same key `K`. Formally, `C_i = E_K(P_i)`. Because `E_K` is a deterministic bijection, the same `P_i` always produces the same `C_i`. This makes ECB a **monoalphabetic substitution cipher** at block granularity, and it inherits every weakness of monoalphabetic substitution: pattern-preservation (the Tux penguin), block-cutting (the Leslie/Kim attack), and statistical attacks when the same message is re-encrypted many times under the same key. ECB is also the only mode in which **block reordering** is invisible to decryption: shuffling `C_i` deterministically shuffles `P_i`. The SVG in this lesson shows two Tux bitmaps; the second is the first, ECB-encrypted block by block, and the penguin is still plainly visible.

### CBC: chaining for confidentiality

CBC (Cipher Block Chaining) is the textbook fix: `C_i = E_K(P_i XOR C_{i-1})`, with `C_{-1} = IV` (a random, non-secret value sent in the clear). The XOR with the previous ciphertext block makes every block's encryption a function of **all** earlier plaintext, so identical plaintext blocks no longer map to identical ciphertext blocks (assuming a non-repeating IV), and the cut-and-paste attack on the bonus file produces garbage at the insertion point. The IV must be unpredictable to the attacker: a predictable IV lets an attacker pre-compute "what the first block of any message beginning with P will encrypt to" and thus fingerprint the start of every encrypted message. **TLS 1.0–1.1** used predictable (last ciphertext block) IVs in CBC mode, which enabled the BEAST attack (2011). CBC has two operational costs: it cannot release block *i* to the application until block *i + 1* has been decrypted (parallel decryption is fine, parallel *encryption* is not), and it requires **padding** to a multiple of the block size (typically PKCS#7, RFC 5652), which in turn creates the famous **padding-oracle attack** when a server reveals "padding invalid" vs "MAC invalid."

### CFB and OFB: turning a block cipher into a stream cipher

CFB (Cipher Feedback) and OFB (Output Feedback) build a keystream `K_0, K_1, K_2, ...` from the block cipher and XOR it with the plaintext. The two differ in how the keystream is updated:

- **CFB**: `K_i = E_K(C_{i-1})` (or `E_K(IV)` for `i=0`); ciphertext feeds back. A 1-bit error in ciphertext corrupts one byte of plaintext (in 8-bit CFB) plus propagates through one full block of keystream.
- **OFB**: `K_i = E_K(K_{i-1})`; the keystream is independent of the plaintext and ciphertext. A 1-bit error corrupts exactly 1 bit of plaintext and does not propagate.
- **CTR** (technically separate from SP 800-38A's OFB, but in the same family): `K_i = E_K(IV + i)` — encrypt a counter. CTR is a stream cipher with no feedback, fully parallelizable in both directions, and forms the encryption core of **AES-GCM** (NIST SP 800-38D).

All three are stream ciphers, and **all three share the same catastrophic failure mode: never reuse a (key, IV/nonce) pair.** Reuse means the same keystream XORs two different plaintexts, and the XOR of the two ciphertexts equals the XOR of the two plaintexts — `P1 XOR P2 = C1 XOR C2`, the key is gone, and the two messages are immediately vulnerable to a "two-time pad" attack. **WEP** reused the 24-bit IV with the same key until the keystream cycled, which is why WEP falls in minutes; **AES-GCM** with a reused nonce catastrophically reveals the authentication key (the **forbidden attack**, polynomial-XOR cancellation).

### Padding and the padding-oracle problem

Block modes that need aligned blocks (ECB, CBC) require padding. **PKCS#7** (RFC 5652) appends *N* bytes, each with value *N*, so a 5-byte message becomes 11 bytes (5 + six `0x06` bytes) and a block-aligned message gets a full extra block of 16 `0x10` bytes (so a 16-byte message becomes 32 bytes). Decryption strips padding; if the stripped bytes are not all equal to the length stripped, the padding is invalid. Servers that leak the difference between "bad padding" and "bad MAC" enable a **Vaudenay-style padding oracle** (2002), which recovers plaintext one byte at a time in 256 × *b* queries for a *b*-byte message. TLS mitigations (encrypt-then-MAC, AEAD ciphers) were driven by this attack.

### Authenticated encryption: AEAD

Modern practice is to drop naked block modes entirely and use **AEAD (Authenticated Encryption with Associated Data)**: AES-GCM, AES-CCM, ChaCha20-Poly1305. AEAD modes bind a MAC to the ciphertext so any modification fails decryption, and they all sit on top of CTR (or a CTR-equivalent) — there is no "GCM-with-ECB" option, because GCM's authentication tag would have to authenticate something, and that something would be the ECB ciphertext, which is just as malleable as the plaintext. The chapter's CBC and CFB sections remain important because they explain the design space; what you actually configure on a TLS 1.3 connection is an AEAD suite (TLS_AES_128_GCM_SHA256, TLS_AES_256_GCM_SHA384, TLS_CHACHA20_POLY1305_SHA256).

## Build It

The build is a stdlib Python module `code/main.py` that provides:

1. A toy 16-byte Feistel block cipher `toy_cipher(block, key)` (two-round Feistel with a fixed round function) — *not* cryptographically secure, but it has the right input/output shape to drop into a real mode-of-operation implementation.
2. `ecb_encrypt`, `cbc_encrypt`, `cfb_encrypt`, `ctr_encrypt` and their `*_decrypt` counterparts, all working on byte strings and IVs.
3. A `pkcs7_pad` / `pkcs7_unpad` helper.
4. A `cut_and_paste_attack(ciphertext, src, dst)` function that swaps block *src* into block *dst* of an ECB-encrypted bonus file.
5. A `keystream_reuse_demo(plaintexts)` function that XORs two plaintexts with the same CTR keystream and shows how the XOR of the ciphertexts equals the XOR of the plaintexts.
6. A `__main__` block that prints a small bonus file encrypted under each mode, the cut-and-paste swap, and the two-time-pad demo.

Run with `python3 code/main.py`. There are no external dependencies.

## Use It

| Mode | Operation | Failure on (key,IV) reuse | Used in |
|---|---|---|---|
| ECB | `C_i = E_K(P_i)` | Deterministic; equal P → equal C always | Legacy; **never** for non-random plaintext |
| CBC | `C_i = E_K(P_i XOR C_{i-1})` | Predictable IVs enable BEAST-style fingerprinting | TLS 1.0–1.1, IPsec ESP, PEM (legacy) |
| CFB | `K_i = E_K(C_{i-1})`; `C_i = P_i XOR K_i` | Two-time pad → recover P1 XOR P2 | TLS 1.0 fallback, satellite links |
| OFB | `K_i = E_K(K_{i-1})`; `C_i = P_i XOR K_i` | Two-time pad → recover P1 XOR P2 | Rare; superseded by CTR |
| CTR | `K_i = E_K(nonce||i)`; `C_i = P_i XOR K_i` | Two-time pad; **AES-GCM** nonce reuse reveals auth key | AES-GCM, AES-CCM, ChaCha20, IPsec ESP |
| GCM | CTR + GHASH MAC | Same as CTR + forgery if nonce reuses | TLS 1.2/1.3, IPsec, QUIC, 802.1AE MACsec |
| XTS | Tweakable ECB for disks | Tweak collision; per-sector | Disk encryption (IEEE 1619) |

The chapter stops at CBC and CFB; CTR and AEAD are covered in the TLS lesson.

## Ship It

The outputs/ directory holds a small reference trace:

- `outputs/bonus_ecb.txt` — the bonus file encrypted block by block under ECB, with the cut-and-paste replacement applied.
- `outputs/bonus_cbc.txt` — the same file under CBC with a random IV; the swapped block produces garbage.
- `outputs/keystream_reuse.txt` — two plaintexts XORed with the same CTR keystream, plus the recovered `P1 XOR P2`.

`code/main.py` is runnable as `python3 code/main.py` and writes all three files when executed.

## Exercises

1. **Block-cutting an ECB bitmap.** Encrypt a 16x16 black-and-white image (256 bytes) under ECB. Show that the encrypted image still looks like the original if you plot the bytes. Implement the "swap block N for block M" attack and show that the result is a valid image with one row replaced.
2. **BEAST-style IV fingerprinting.** Build a CBC encryptor that reuses the IV across messages. Show that two messages with the same first plaintext block produce the same first ciphertext block, and explain why this lets an attacker recover a session cookie one block at a time.
3. **Padding-oracle detector.** Implement CBC decryption with PKCS#7 unpadding. Add a flag that distinguishes "padding invalid" from "padding valid but MAC invalid" and time the two cases. The difference is what enables the Vaudenay attack.
4. **CTR nonce reuse.** Encrypt two distinct messages with the same (key, nonce) under CTR. Show that the XOR of the two ciphertexts equals the XOR of the two plaintexts, and demonstrate a crib-drag attack on the two-time pad.
5. **Mode swap.** Take a real CBC implementation (e.g., the `cryptography` package's `Cipher(algorithms.AES, modes.CBC(iv))`) and use it to encrypt, then "convert" the ciphertext to look like ECB output by isolating a single block. What does this tell you about how a defender should check the mode in use?
6. **Why is no real protocol a "mode" itself?** TLS, IPsec, and SSH all sit on top of a mode. Explain in two paragraphs why "TLS-CBC" is actually "TLS-handshake-keying + CBC-record-encryption + HMAC-SHA1-outer-MAC" and why this stacking is what made padding oracles possible.

## Key Terms

| Term | Definition |
|---|---|
| Block cipher | A keyed permutation on a fixed-size block (16 B for AES, 8 B for DES). |
| Mode of operation | Rule for using a block cipher to encrypt arbitrarily long messages (NIST SP 800-38A). |
| ECB | Electronic Code Book: independent encryption of each block. |
| CBC | Cipher Block Chaining: each block XORed with the previous ciphertext before encryption. |
| CFB | Cipher Feedback: block cipher used to generate a self-synchronizing keystream. |
| OFB | Output Feedback: block cipher used to generate a keystream independent of the plaintext. |
| CTR | Counter mode: encrypt a counter, XOR with plaintext. |
| AEAD | Authenticated Encryption with Associated Data (AES-GCM, ChaCha20-Poly1305). |
| IV | Initialization Vector: a public random nonce that randomizes the encryption. |
| Nonce | Number used once; public, never reused under the same key. |
| Padding | Extra bytes appended to a message to align it to a block boundary (PKCS#7). |
| Padding oracle | Side channel that distinguishes bad padding from bad MAC; recovers plaintext. |
| Two-time pad | Keystream reuse attack: `C1 XOR C2 = P1 XOR P2`, key canceled out. |
| Cut-and-paste | Attack that swaps ciphertext blocks in ECB mode to alter plaintext meaning. |
| BEAST | Browser Exploit Against SSL/TLS: predictable IV attack on TLS 1.0 CBC (2011). |

## Further Reading

- NIST SP 800-38A, *Recommendation for Block Cipher Modes of Operation — Methods and Techniques* (2001).
- NIST SP 800-38D, *Recommendation for Block Cipher Modes of Operation: Galois/Counter Mode (GCM) and GMAC* (2007).
- S. Vaudenay, *Security Flaws Induced by CBC Padding — Applications to SSL, IPSEC, WTLS...*, EUROCRYPT 2002.
- RFC 5246, *The Transport Layer Security (TLS) Protocol Version 1.2* — CBC-mode record layer.
- RFC 8446, *The Transport Layer Security (TLS) Protocol Version 1.3* — mandates AEAD.
- A. Joux, *Authentication Failures in NIST Version of GCM* (NIST nonce-misuse comment, 2006).
- M. Bellare and C. Namprempre, *Authenticated Encryption: Relations among Notions and Analysis of the Generic Composition Paradigm*, ASIACRYPT 2000.
- D. Wagner and B. Schneier, *Analysis of the SSL 3.0 Protocol* (1996) — first CBC padding discussion.
