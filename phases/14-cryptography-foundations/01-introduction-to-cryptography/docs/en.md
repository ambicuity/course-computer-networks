# Introduction to Cryptography

> Cryptography is the study of secret writing — transforming plaintext P into ciphertext C using an encryption function E parameterized by a key K, so that C = E_K(P), and recovering P with D_K(C) such that D_K(E_K(P)) = P. The model has three roles: Alice (sender), Bob (receiver), and an intruder who may be passive (only listens) or active (alters, replays, or injects messages). Kerckhoffs's principle (1883) is the foundation: the algorithm is public, the key is the only secret. Key length sets the work factor: 64 bits stops your kid brother, 128 bits covers commercial use, 256 bits holds off major governments. Cryptanalysis comes in three flavors: ciphertext-only, known-plaintext, and chosen-plaintext. A cipher secure only under ciphertext-only is naive — the cryptanalyst almost always has "login:" or similar known plaintext. Classical ciphers split into substitution (replace symbols) and transposition (reorder symbols); modern block ciphers cascade both. The field that designs ciphers (cryptography) and the field that breaks them (cryptanalysis) together form cryptology.

**Type:** Build
**Languages:** Python, crypto diagrams
**Prerequisites:** Phase 13 streaming and content delivery lessons
**Time:** ~90 minutes

## Learning Objectives

- State Kerckhoffs's principle and explain why security-by-obscurity fails in practice.
- Distinguish ciphertext-only, known-plaintext, and chosen-plaintext attack models and name a realistic example of each.
- Compute the work factor for an exhaustive key search given key length in bits.
- Separate substitution ciphers from transposition ciphers by what they preserve (symbol identity vs. symbol order).
- Map the C = E_K(P) / P = D_K(C) notation to a concrete encryption and decryption round-trip.

## The Problem

Your company transmits purchase orders over a link an adversary can tap. The plaintext orders contain customer names, product IDs, and quantities. If a recently-fired employee captures the wire and injects fabricated orders, the receiving system ships goods to real customers at attacker-chosen quantities. Encryption alone is not enough — the receiver must be able to distinguish a valid message from attacker garbage, and must reject stale replays. This lesson establishes the vocabulary (plaintext, ciphertext, key, intruder types, attack models) that every later crypto lesson builds on.

## The Concept

### The encryption model and notation

The canonical model has five parts: plaintext P, an encryption method E parameterized by key K producing ciphertext C = E_K(P), a decryption method D with D_K(E_K(P)) = P, a transmission channel, and an intruder. The intruder is **passive** when she only listens, and **active** when she can record and replay, inject new messages, or modify messages in flight. The notation treats E and D as mathematical functions of two parameters, with the key written as a subscript to distinguish it from the message argument.

| Symbol | Meaning |
|--------|---------|
| P | Plaintext (the readable message) |
| C | Ciphertext (the encrypted output) |
| K | Key (the short secret that selects the transformation) |
| E_K(P) | Encryption of P under key K |
| D_K(C) | Decryption of C under key K |
| D_K(E_K(P)) = P | Round-trip identity: decrypting encrypted plaintext recovers the original |

### Kerckhoffs's principle

Auguste Kerckhoffs, a Flemish military cryptographer, stated in 1883 that the algorithm must be public and only the key is secret. The reasoning is operational: inventing, testing, and deploying a new algorithm every time the old one is suspected compromised is impractical, especially when thousands of low-level code clerks must be retrained. A public algorithm also gets free review from academic cryptographers eager to publish breaks. Hiding the algorithm — "security by obscurity" — never works and does more harm than good because it breeds false confidence. The `code/main.py` demo implements a toy substitution cipher and shows that even with the algorithm fully public, the key space is what sets the work factor.

### Key length and work factor

The key is a short string that selects one of many possible encryptions. A combination-lock analogy: two digits give 100 possibilities, three give 1,000, six give 1,000,000. The work factor for exhaustive search is exponential in key length. The table below maps common key lengths to their key spaces and practical guidance.

| Key length | Key space | Practical guidance |
|------------|-----------|-------------------|
| 64 bits | ~1.8 x 10^19 | Stops casual attackers; brute-forceable with hardware |
| 128 bits | ~3.4 x 10^38 | Routine commercial minimum |
| 256 bits | ~1.1 x 10^77 | Resists major-government brute force |

A single-chip exhaustive search of a 56-bit DES key space at 1 ns per key takes approximately 2.3 years; a 128-bit AES key space at the same rate would outlast the sun. The SVG (`assets/introduction-to-cryptography.svg`) diagrams the key-length-to-work-factor curve.

### Three cryptanalysis attack models

The cryptanalyst's problem has three principal variants. Which one applies changes the difficulty dramatically.

| Attack model | What the cryptanalyst has | Realistic example |
|-------------|--------------------------|-------------------|
| Ciphertext-only | Ciphertext, no plaintext | Newspaper cryptograms |
| Known-plaintext | Matched ciphertext + plaintext | The "login:" prompt that precedes every session |
| Chosen-plaintext | Can encrypt arbitrary plaintext | A public-key system where anyone can encrypt |

A cipher that survives only ciphertext-only is naive. In real protocols, the attacker almost always has known plaintext — protocol headers, version strings, predictable greetings. The conservative designer demands security even under chosen-plaintext attack, which is exactly the threat public-key systems face by definition.

### Substitution versus transposition

Historical encryption splits into two families. **Substitution ciphers** replace each letter or group of letters with another, preserving order but disguising identity. The Caesar cipher (shift by 3: a→D, b→E, …, z→C) is the simplest. **Transposition ciphers** reorder letters without disguising them — the frequency distribution of the plaintext survives intact. The columnar transposition cipher (keyed by a word like MEGABUCK) writes plaintext into a grid row by row and reads ciphertext out by columns in alphabetical key order. Modern block ciphers cascade both: product ciphers alternate substitution (S-boxes) and transposition (P-boxes) over many rounds.

### Ciphers versus codes

Professionals distinguish **ciphers** (character-for-character or bit-for-bit transformations, indifferent to linguistic structure) from **codes** (word-for-word replacements). Codes are obsolete but have a glorious history. The most successful code ever devised was used by U.S. armed forces in the Pacific during World War II: Navajo code talkers used specific Navajo words for military terms (chay-da-gahi-nail-tsaidi, "tortoise killer," for antitank weapon). The Navajo language is highly tonal, has no written form, and no one in Japan knew it. The Japanese never broke it.

### What "breaking" a cipher means

Breaking a cipher does not always mean recovering the key. It may mean recovering the plaintext, recovering a partial key, or finding a way to distinguish valid ciphertext from random bits. Cryptanalysis and cryptography together form **cryptology**. The next lessons walk through specific classical ciphers, the one-time pad, the two principles (redundancy and freshness), and the modern symmetric and public-key algorithms that the Internet relies on.

## Build It

1. Run `python3 code/main.py` — it implements a Caesar cipher with variable shift k, demonstrates encryption and decryption round-trips, and prints a work-factor table for key lengths 8 through 256.
2. Verify the round-trip identity D_K(E_K("attack")) == "attack" for several keys.
3. Modify the key length table to include a 512-bit row and note the exponent.
4. Inspect `assets/introduction-to-cryptography.svg` for the encryption model diagram.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|---------------------|
| State Kerckhoffs's principle | You can explain why algorithm secrecy fails | You reject "security by obscurity" on operational grounds, not aesthetics |
| Classify an attack | You name which of the three models a scenario fits | Known-plaintext is the default assumption, not ciphertext-only |
| Estimate brute-force cost | You compute 2^key_length trials and convert to time at 1 ns/key | 56-bit falls in hours; 128-bit outlasts the sun |
| Tell substitution from transposition | You check whether letter frequencies survive | Frequencies survive → transposition; frequencies shift → substitution |

## Ship It

This lesson produces `outputs/crypto-vocabulary-cheatsheet.md`: a one-page reference mapping each term (plaintext, ciphertext, key, E_K, D_K, intruder types, attack models, Kerckhoffs's principle) to a concrete example and a diagnostic question.

## Exercises

1. A vendor claims their algorithm is secret and therefore secure. Refute the claim using two operational arguments from Kerckhoffs's principle.
2. You intercept 1 MB of ciphertext with no plaintext. Which attack model is this? What single known-plaintext string would upgrade you to known-plaintext for an HTTP session?
3. Compute how long exhaustive search of a 40-bit key takes at 10^9 keys/sec. Repeat for 80 bits and 128 bits. Where does the curve cross one year?
4. Distinguish a cipher from a code. Name one historical code and explain why codes are obsolete.
5. Modify `code/main.py` to add a transposition round after the Caesar substitution and verify that letter frequencies no longer match English.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| Plaintext (P) | "the message" | The readable input before encryption |
| Ciphertext (C) | "the encrypted thing" | Output of E_K(P); what travels on the wire |
| Key (K) | "the password" | The short secret selecting the transformation; the only thing that must be secret |
| Kerckhoffs's principle | "don't hide the algorithm" | Algorithms are public; only keys are secret (1883) |
| Work factor | "how hard to break" | Trials needed for exhaustive search; exponential in key length |
| Passive intruder | "just listening" | Copies ciphertext only; cannot modify traffic |
| Active intruder | "the dangerous one" | Can replay, inject, or modify messages in flight |
| Cryptanalysis | "code breaking" | Recovering plaintext or key from ciphertext |
| Cryptology | "the whole field" | Cryptography (design) + cryptanalysis (break) |
| Security by obscurity | "hiding the algorithm" | A failed strategy; does more harm than good |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), Chapter 8 Section 8.1.1
- Kahn, *The Codebreakers* (1995) — the comprehensive history of cryptography
- Kaufman, Perlman, and Speciner, *Network Security* (2002)
- Stinson, *Cryptography: Theory and Practice* (2002) — mathematical treatment
- Auguste Kerckhoffs, "La Cryptographie Militaire" (1883) — the original principle