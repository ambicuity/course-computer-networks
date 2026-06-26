# Transposition Ciphers to One-Time Pads

> Transposition ciphers reorder letters without disguising them — the frequency distribution of the plaintext survives intact, which is the tell that distinguishes them from substitution. The columnar transposition cipher writes plaintext row by row into a grid keyed by a word with no repeated letters (MEGABUCK), numbers the columns by alphabetical key order, and reads ciphertext out by columns in that order. Breaking it requires guessing the key length from digram patterns (MO, IL, LL, LA, IR, OS for "milliondollars" at key length 8), then ordering columns by best digram-frequency match. The one-time pad (OTP) is the only provably unbreakable cipher: choose a random bit string as the key, XOR it with the plaintext bit by bit, and every possible plaintext of that length is equally likely — information theory gives the cryptanalyst nothing. The OTP is immune to all present and future attacks regardless of compute power. Its fatal practical drawbacks: the key must be as long as the message, cannot be memorized, must never be reused, and lost synchronization garbles everything downstream.

**Type:** Build
**Languages:** Python, crypto diagrams
**Prerequisites:** Lessons 01 and 02 of Phase 14
**Time:** ~85 minutes

## Learning Objectives

- Encrypt and decrypt with a columnar transposition cipher keyed by a no-repeat-letter word.
- Detect a transposition cipher by checking that letter frequencies match the plaintext language.
- Recover the key length by testing digram patterns of a probable word at different key lengths.
- Encrypt and decrypt with a one-time pad using XOR on 7-bit ASCII.
- Explain why OTP reuse is catastrophic: XOR of two ciphertexts eliminates the key and yields the XOR of two plaintexts.

## The Problem

You intercept ciphertext that has the normal English frequency distribution of e, t, a, o, i, n — so it is not a substitution cipher. It is a transposition cipher: the letters are English but scrambled. You suspect the plaintext contains "milliondollars." How do you find the key length and reorder the columns? Separately, your spy agency wants a cipher that is provably unbreakable. The one-time pad delivers that, but only if the pad is truly random, as long as the message, used exactly once, and perfectly synchronized. This lesson builds both.

## The Concept

### Columnar transposition: the grid model

The cipher is keyed by a word or phrase with no repeated letters. MEGABUCK is the chapter's example. The key orders the columns: the column under the letter closest to A is column 1, and so on.

```
Key:      M E G A B U C K
Order:    7 4 5 1 2 8 3 6

Plaintext (row by row):
          p l e a s e t r
          a n s f e r o n
          e m i l l i o n
          d o l l a r s t
          o m y s w i s s
          b a n k a c c o
          u n t s i x t w
          o t w o a b c d

Ciphertext (read columns in order 1..8):
Afllsksoselawaiatoossctclnmomant  Esilyntwrnntsowdpaedobuoeriricxb
```

The `code/main.py` demo implements this grid, numbers columns by key order, reads out by column, and reverses the process for decryption.

### Detecting transposition by frequency

The first diagnostic: count letter frequencies in the ciphertext. If e, t, a, o, i, n match normal English percentages, the cipher is transposition, not substitution. The letters are themselves; only their order changed. This single test separates the two classical families.

### Recovering key length with digram patterns

A probable word like "milliondollars" wraps across rows. At key length k, the digrams produced by that word in the ciphertext have a specific pattern. At k=8, the digrams from "milliondollars" are MO, IL, LL, LA, IR, OS (letters k apart in the plaintext end up adjacent in the ciphertext column). At k=7, the digrams would be MD, IO, LL, LL, IA, OR, NS. By testing each candidate key length and checking which digram set matches the ciphertext, the analyst determines k. The `code/main.py` demo computes digram sets for a given word and key length.

### Ordering the columns

Once k is known, the analyst examines each of the k(k-1) column pairs and checks which pair has digram frequencies closest to English. That pair is placed first. Then each remaining column is tested as the successor by digram and trigram match. The process continues until the full order is found. If "milloin" appears (a transposition error), the correct order is obvious.

### Transposition as a block cipher

Some transposition ciphers accept a fixed-length block and produce a fixed-length block. The MEGABUCK cipher with 8 columns and 8 rows is a 64-character block cipher. Its output order is 4, 12, 20, 28, 36, 44, 52, 60, 5, 13, … — the 4th input character comes out first, then the 12th, and so on. This is a permutation cipher, and modern block ciphers generalize it with P-boxes.

### The one-time pad: provably unbreakable

Constructing an unbreakable cipher is easy and has been known for decades. The recipe:

1. Choose a random bit string as the key (the "pad").
2. Convert the plaintext to a bit string (e.g., 7-bit ASCII).
3. Compute C = P XOR K, bit by bit.

The ciphertext carries zero information: every possible plaintext of that length is equally likely because for any desired plaintext there exists a pad that produces it. The chapter's example: message "I love you." in 7-bit ASCII, XORed with pad 1, produces ciphertext. Pad 2 (different random bits) XORed with the same ciphertext produces "Elvis lives." The cryptanalyst cannot distinguish the correct pad from any other pad, so the correct plaintext is unrecoverable — this is an information-theoretic guarantee, not a computational one.

| Message char | ASCII bits | Pad bits | Ciphertext bits |
|--------------|-----------|----------|-----------------|
| I | 1001001 | 1010010 | 0011011 |
| (space) | 0100000 | 1001011 | 1101011 |
| l | 1101100 | 1110010 | 0011110 |
| o | 1101111 | 1010101 | 0111010 |

### OTP practical failures

The OTP is perfect in theory and painful in practice:

- **Key length**: the key is as long as the message. At gigabit network speeds, you need a new DVD of pad material every 30 seconds.
- **No memorization**: sender and receiver carry written copies; capture exposes the pad.
- **No reuse**: reusing a pad is catastrophic. If P1 XOR K and P2 XOR K are both captured, XORing them eliminates K and yields P1 XOR P2. Statistical properties of the two plaintexts (spaces XOR spaces, space XOR e) then recover both. This is the **keystream reuse attack** that also applies to stream ciphers and counter mode.
- **Synchronization**: one lost or inserted bit garbles everything from that point forward.

### Why the OTP is the gold standard and the floor

The OTP sets the theoretical ceiling: perfect secrecy is achievable. Every other cipher (AES, RSA, everything) is a computational compromise — they are hard to break but not provably unbreakable. The OTP also sets the floor for what "secure" must mean: the ciphertext alone must not leak information about the plaintext. Modern authenticated encryption (AES-GCM) approximates this computationally; the OTP achieves it information-theoretically.

## Build It

1. Run `python3 code/main.py`. It encrypts a message with columnar transposition (key MEGABUCK), decrypts it back, checks that letter frequencies survive, computes the digram pattern for "milliondollars" at key length 8, and demonstrates OTP encrypt/decrypt with XOR on 7-bit ASCII.
2. Modify the key word to "CRYPTO" (6 columns, no repeats) and re-encrypt. Check the frequency distribution is unchanged.
3. XOR two ciphertexts produced with the same pad and verify the result equals the XOR of the two plaintexts (the reuse attack).

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|---------------------|
| Detect transposition | Letter frequencies match English | e, t, a, o, i, n percentages are in normal range |
| Recover key length | Digram pattern of probable word matches ciphertext at k=8 | Only one key length produces the expected digrams |
| OTP encrypt/decrypt | XOR round-trip recovers plaintext | Every bit matches; no information leaked |
| OTP reuse attack | XOR of two ciphertexts = XOR of two plaintexts | The key vanishes; plaintexts are exposed |

## Ship It

This lesson produces `outputs/transposition-and-otp-lab.md`: a lab notebook page documenting the columnar transposition break (frequency check, key-length discovery, column ordering) and the OTP reuse attack with a worked XOR example.

## Exercises

1. Encrypt "pleasetransferonemilliondollarstomyswissbankaccountsixtwotwo" with key MEGABUCK. Read out the ciphertext by columns. Decrypt to verify.
2. You intercept ciphertext with normal English letter frequencies. Is it substitution or transposition? Justify with the frequency test.
3. The probable word is "milliondollars." Compute the digram set for key lengths 6, 7, 8, and 9. Which key length matches the ciphertext digrams?
4. Encrypt "I love you." with a random 77-bit pad. Show that a different pad can decrypt the same ciphertext to "Elvis lives." Why is this not a break?
5. Two messages are encrypted with the same OTP pad. You capture both ciphertexts. Describe the exact steps to recover both plaintexts. Why must real systems never reuse a pad?

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| Columnar transposition | "grid cipher" | Write rows, read columns in key order |
| Key order | "alphabetical order of the key" | Column 1 is under the key letter nearest A |
| Frequency tell | "letters look normal" | Letter frequencies match plaintext language → transposition, not substitution |
| Digram pattern | "letter pairs" | Pairs k apart in plaintext become adjacent in ciphertext; reveals key length |
| One-time pad | "XOR with random key" | Provably unbreakable; every plaintext equally likely |
| Keystream reuse | "same pad twice" | Catastrophic: XOR of two ciphertexts eliminates the key |
| Perfect secrecy | "information-theoretic" | Ciphertext leaks zero bits about plaintext (Shannon) |
| Synchronization | "alignment" | One lost bit garbles everything after it in OTP |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), Sections 8.1.3 and 8.1.4
- Shannon, "Communication Theory of Secrecy Systems" (1949) — the OTP proof of perfect secrecy
- Sinkov, *Elementary Cryptanalysis* — transposition cipher breaks in detail
- Kahn, *The Codebreakers* — Venona project OTP reuse failures