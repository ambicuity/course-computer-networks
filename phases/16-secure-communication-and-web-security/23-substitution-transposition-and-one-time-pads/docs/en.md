# Classical ciphers: substitution, transposition, one-time pads

> Before DES, AES, and the rest of modern symmetric cryptography, the entire discipline of secret writing boiled down to two operations on alphabetic text — substitute one symbol for another (Caesar, Vigenere, monoalphabetic), and permute the order of symbols without changing them (columnar transposition, rail fence). Classical ciphers are broken by statistics: English has letter-frequency distribution `e ≈ 12.7%, t ≈ 9.1%, a ≈ 8.2%`; digram `th ≈ 3.5%`; trigram `the ≈ 3.0%`. A monoalphabetic substitution preserves these frequencies exactly, so even with 26! ≈ 4×10²⁶ possible keys, the cipher is broken with a few hundred characters of ciphertext using frequency analysis and probable-word search. The one-time pad (OTP) is the only classical construction that is *provably* unbreakable: the key is a uniformly random bit string at least as long as the message, the ciphertext is the XOR of the two, and there is no statistical structure left to attack. The OTP is impractical (key distribution, key reuse sensitivity) but it is the theoretical ceiling against which every modern cipher is compared. This lesson implements each family, breaks the breakable ones, and proves the OTP unbreakable by information-theoretic argument.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Phase 14 (basic cryptography), Phase 15 (statistical reasoning about randomness)
**Time:** ~75 minutes

## Learning Objectives

- Implement Caesar, monoalphabetic, Vigenere, and columnar transposition ciphers and produce round-trip `decrypt(encrypt(m, k), k) == m`.
- Run frequency analysis on monoalphabetic ciphertext: count letter occurrences, sort by frequency, map `e, t, a, o, i, n` to the most common ciphertext letters, and recover plaintext.
- Run Kasiski examination and the Friedman test on Vigenere ciphertext to recover the key length without knowing the key.
- Prove the one-time pad is unbreakable: given ciphertext `c`, every plaintext `m` of the same length is equally probable (because the key is uniformly random), so the ciphertext leaks zero Shannon information about the message.
- Demonstrate why OTP key reuse is catastrophic: `c1 XOR c2 = m1 XOR m2`, and with a known `m1` (or a likely space character) you recover `m2` directly.
- Connect classical attacks to modern design: why AES uses a substitution-permutation network, why CTR mode with a reused keystream is broken the same way OTP key reuse is broken, and why a deterministic generator that ever repeats an output is exploitable.

## The Problem

Every modern symmetric cipher is a descendant of substitution and permutation. AES-128 has 16 bytes of state and 10 rounds; each round is SubBytes (substitution), ShiftRows (permutation), MixColumns (linear transform), AddRoundKey (XOR with key material). DES has 16 rounds of similar shape. Understanding the classical ancestors — and the classical attacks that broke them — is the only way to understand *why* modern ciphers are constructed the way they are, and *why* a cryptographer reading an AES proposal would look at the S-box design first.

There is also a recurring pattern in real-world failure modes: a modern system that reuses keystream (WEP's RC4 IV collision; ECB mode in TLS before 1.2; Telegram's MTProto when used naively) is exactly the classical "OTP key reuse" mistake in different clothes. If you understand why OTP reuse is catastrophic, you understand why CTR mode requires a unique nonce per message, why WEP fails at scale, and why AES-GCM has a 96-bit nonce that must never repeat under the same key.

## The Concept

### Caesar cipher: `E_k(c) = (c - 'a' + k) mod 26`

A single-letter shift. `attack` with k=3 becomes `dwwdfn`. Brute force is 26 attempts. Frequency analysis is overkill. Historically attributed to Julius Caesar (k=3), but Suetonius records that he also used k=4 and k=7 for variety.

### Monoalphabetic substitution: a fixed permutation of the alphabet

The key is a 26-letter string defining the substitution table. Plaintext `attack` becomes `qzzqea` under the key `Q W E R T Y U I O P A S D F G H J K L Z X C V B N M`. Keyspace is `26! ≈ 4×10²⁶`, which sounds huge but is broken by frequency analysis: ciphertext letter frequencies match plaintext letter frequencies exactly (modulo a permutation), and English letter, digram, and trigram tables reduce the search to a small handful of guesses.

### Polyalphabetic: Vigenere

The key is a short word; each plaintext letter is shifted by the corresponding key letter (`a=0, b=1, ..., z=25`). `attack` with key `lemon` becomes `lxfopv`. Frequency analysis on the raw ciphertext fails because letter frequencies are flattened — but a two-step attack recovers the key:

1. **Kasiski examination**: repeated ciphertext digrams likely come from repeated plaintext digrams aligned with the key. The distances between occurrences share a common factor that is the key length.
2. **Friedman test (Index of Coincidence)**: for English text the IC is ~0.066; for random text it is ~0.038. Split the ciphertext into `L` columns (one per candidate key length), compute IC of each column, and pick the `L` that makes every column's IC closest to 0.066.

Once you have the key length, each column is a Caesar cipher and is solved independently.

### Columnar transposition

Plaintext is written into rows under a keyword that defines the column order, and read out by columns in that order. The key is the keyword (or its numeric order, e.g., `MEGABUCK = [4, 2, 1, 3, 0, 6, 5]` if we read letters alphabetically). Frequency analysis does not directly help because letter frequencies are unchanged; instead the attacker hunts for probable words (`milliondollars` in Tanenbaum's example) and uses the digrams that result from the wrap-around to infer the column count and ordering.

### One-time pad: `c = m XOR k` with uniformly random `k` of length |m|

The Shannon (1949) argument: `H(M|C) = H(M)` — observing the ciphertext gives the attacker zero information about the message because every message of the given length is consistent with some key. Practically:

- The key must be at least as long as the message.
- The key must be uniformly random — generated from a hardware source, not from `random.randint`.
- The key must never be reused under the same message space; if you XOR two OTP ciphertexts made with the same key, you get the XOR of the two plaintexts, and many real-world plaintexts (HTTP headers, English text with known structure) yield to known-plaintext attacks.
- The key distribution problem is unsolved in general: out-of-band key delivery is required.

The famous "I love you." / "Elvis lives" example (Tanenbaum Fig. 8-4) shows that for a fixed 11-character ciphertext, there exists a key that decrypts to any 11-character plaintext the attacker wants. The OTP provides confidentiality, not authenticity — Mallory cannot read the message, but he can replace it with any other message of the same length.

### Modern ciphers as iterated classical operations

DES: 16 rounds, each with an expansion, XOR with a subkey, S-box substitution, P-box permutation. AES: 10–14 rounds, each with SubBytes (substitution via an S-box), ShiftRows (permutation), MixColumns (linear diffusion), AddRoundKey (XOR). The classical ideas are not obsolete — they are the *building blocks* of every modern cipher, applied enough times and with carefully chosen S-boxes so that no classical attack survives the iteration count.

## Build It

### Step 1 — Caesar round-trip

```python
from main import caesar_encrypt, caesar_decrypt

assert caesar_decrypt(caesar_encrypt("attackatdawn", k=3), k=3) == "attackatdawn"
```

### Step 2 — Monoalphabetic break via frequency analysis

```python
from main import monoalphabetic_encrypt, frequency_break

key = "QWERTYUIOPASDFGHJKLZXCVBNM"
ciphertext = monoalphabetic_encrypt("the quick brown fox jumps over the lazy dog and then runs away into the dark forest", key)
recovered = frequency_break(ciphertext)
assert "the" in recovered.lower()
```

The breaker counts letter occurrences in `ciphertext`, maps them to the top English frequencies `etaoinshrdlcumwfgypbvkjxqz`, and reconstructs the key from the mapping.

### Step 3 — Vigenere key-length recovery via Friedman test

```python
from main import vigenere_encrypt, friedman_key_length, kasiski_key_length

ciphertext = vigenere_encrypt("tobeornottobethatisthequestion", key="hamlet")
print(kasiski_key_length(ciphertext))   # prints 6
print(friedman_key_length(ciphertext))  # prints 6
```

Both attacks return the same key length without needing the key. After that, each column is a Caesar cipher and is solved by frequency analysis on that column.

### Step 4 — One-time pad

```python
from main import otp_encrypt, otp_decrypt, xor_bytes

key = secrets.token_bytes(len(message))
ciphertext = xor_bytes(message, key)
# ANY plaintext of the same length could have produced this ciphertext given a different key
recovered = xor_bytes(ciphertext, key)
assert recovered == message
```

The library functions use `secrets.token_bytes` so the key is genuinely random. A test that reuses a key across two messages and XORs the two ciphertexts will see the XOR of the plaintexts leak through immediately.

### Step 5 — Key-reuse attack

```python
recovered = xor_bytes(c1, c2)   # m1 XOR m2 leaks
# With one known plaintext (or a likely space character 0x20), recover the other
```

If `m1` is known (e.g., a HTTP request begins with `GET /`), then `m2 = (c1 XOR c2) XOR m1`. This is the WEP attack pattern (RC4 keystream reused across packets) and the TLS 1.0 CBC-IV attack pattern (where the IV can be made predictable).

## Use It

| Modern system | Classical analog | Same weakness if misused |
|---|---|---|
| AES-128 ECB | Monoalphabetic substitution (same plaintext block → same ciphertext block) | Reused keystream reveals patterns; same key+plaintext always yields same ciphertext |
| AES-128 CTR with reused nonce | OTP key reuse | `c1 XOR c2 = m1 XOR m2`; HTTP, TLS, SSH all leak via known plaintext |
| AES-128 CBC with predictable IV | One-time pad with reused/known key | BEAST attack (TLS 1.0) recovered plaintext cookies via IV manipulation |
| RSA without padding (textbook RSA) | Monoalphabetic substitution (small key space) | Fermat factorization, chosen-ciphertext attack; never use textbook RSA |
| RC4 in WEP | One-time pad with reused per-packet keystream | 24-bit IV → keystream collision after ~5000 packets → key recovery in minutes |
| Substitution-permutation network | Iterated classical S+P | If round count is too small: differential / linear cryptanalysis (DES reduced to 8 rounds was broken in 1998) |

The classical attacks did not die; they were absorbed into the design requirements of modern ciphers. Every AES S-box entry is the result of decades of research into what substitutions resist differential and linear cryptanalysis.

## Ship It

The reusable artifact in `outputs/prompt-classical-ciphers.md` is `classical_cipher_lab.py` with:

- `caesar_encrypt(text, k)`, `caesar_decrypt(text, k)`, `caesar_brute(text)` returning the 26 candidates sorted by English-likelihood score.
- `monoalphabetic_encrypt(text, key_perm)`, `frequency_break(ciphertext)`.
- `vigenere_encrypt(text, key)`, `vigenere_decrypt`, `kasiski_key_length`, `friedman_key_length`, `vigenere_break`.
- `columnar_transposition_encrypt(text, key)`, `columnar_transposition_decrypt`, `columnar_break(text, max_keylen)`.
- `otp_encrypt`, `otp_decrypt`, plus a `key_reuse_attack(c1, c2, known_plaintext)` that demonstrates the catastrophic plaintext recovery.

A `cli.py` accepts a ciphertext and a `--cipher {caesar, mono, vigenere, transposition}` flag and prints the recovered plaintext.

## Exercises

1. Caesar-decrypt `fvhduvklyh` with brute force and rank candidates by English bigram frequency. Which key is the correct one, and how many false-positive candidates appear in the top 5?
2. Monoalphabetic-substitute your full name and run `frequency_break` on the result. Does it succeed? What is the smallest ciphertext length for which the attack reliably recovers the key?
3. Vigenere with key `LEMON` on a paragraph of public-domain text. Run Kasiski and Friedman; do they agree on the key length? Reconstruct the key by frequency-analyzing each column.
4. Columnar transposition with key length 7. Hand-draw the 7-column matrix for a 30-character plaintext, mark the read-out order, and verify `decrypt(encrypt(m, key), key) == m`.
5. Generate a 1 MB OTP-encrypted file. Compare its size to the original and to the same data encrypted with AES-GCM (if your environment provides it). What overhead does AES-GCM add, and what overhead does the OTP add?
6. Reuse one OTP key to encrypt two HTTP requests: `GET / HTTP/1.1\r\nHost: example.com\r\n\r\n` and `GET / HTTP/1.1\r\nHost: evil.com\r\n\r\n`. XOR the two ciphertexts. Recover the second `Host:` header without breaking the OTP — by leveraging the known structure of the first.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Substitution | "swap letters" | Monoalphabetic: one fixed permutation; polyalphabetic: position-dependent permutation |
| Transposition | "rearrange letters" | Permute the order of plaintext symbols without changing identity |
| Caesar cipher | "shift by 3" | ROT-k; `c = (p + k) mod 26` |
| Vigenere | "polyalphabetic cipher" | A keyword-driven set of Caesar shifts; broken by Kasiski + IC |
| Frequency analysis | "count letters" | English letter, digram, trigram frequencies identify the substitution table |
| Kasiski examination | "find repeated patterns" | Distances between repeated digrams share the key length as a factor |
| Index of Coincidence | "IC" | Probability that two random letters from a text are equal; ~0.066 for English, ~0.038 for random |
| One-time pad | "OTP" | XOR with uniformly random key as long as the message; Shannon-secure if implemented correctly |
| Shannon secrecy | "perfect secrecy" | `H(M|C) = H(M)`; ciphertext reveals no Shannon information about plaintext |
| Information-theoretic | "provably unbreakable" | Based on entropy, not on computational hardness assumptions |

## Further Reading

- Kahn, D. — *The Codebreakers* (the historical reference for classical ciphers)
- Singh, S. — *The Code Book* (accessible introduction to substitution, transposition, and the OTP)
- Shannon, C. E. (1949). *Communication Theory of Secrecy Systems.* Bell System Technical Journal.
- Tanenbaum, A. S., & Wetherall, D. J. — *Computer Networks*, 5th ed., Ch. 8.1 (substitution, transposition, OTP)
- Stallings, W. — *Cryptography and Network Security*, Ch. 3 (classical encryption techniques)
- Friedman, W. F. — *The Index of Coincidence and Its Applications in Cryptanalysis*
- Kasiski, F. W. (1863). *Die Geheimschriften und die Dechiffrir-Kunst*
- Bellare, M., & Rogaway, P. — *Introduction to Modern Cryptography*, Ch. 2 (the OTP and Shannon security)
