# Substitution Ciphers

> A substitution cipher replaces each plaintext letter with another letter, preserving order but disguising identity. The Caesar cipher shifts by a fixed k (a→D for k=3); its generalization allows any of 26 shifts. The monoalphabetic cipher uses an arbitrary 26-letter permutation as the key — 26! ≈ 4 × 10^26 keys, far too many for brute force even at 1 ns per key (10,000 years on a million chips). Yet the cipher falls to frequency analysis: English letter frequencies (e most common, then t, a, o, i, n, s, h, r), digram frequencies (th, in, er, re, an), and trigram frequencies (the, ing, and, ion) let a cryptanalyst build the key letter by letter. A probable-word attack accelerates the break: guess "financial," locate its repeated-letter pattern in the ciphertext, align, and deduce surrounding letters. The Caesar cipher is broken by a child in seconds; monoalphabetic substitution is broken by a determined analyst with a few hundred characters of ciphertext. Substitution alone is never enough.

**Type:** Build
**Languages:** Python, crypto diagrams
**Prerequisites:** Lesson 01 Introduction to Cryptography
**Time:** ~75 minutes

## Learning Objectives

- Encrypt and decrypt with a Caesar cipher of arbitrary shift k.
- Encrypt and decrypt with a monoalphabetic substitution cipher keyed by a 26-letter permutation.
- Perform frequency-analysis attack: rank ciphertext letters, map the most common to e, find digrams and trigrams, and build the key incrementally.
- Execute a probable-word attack: match a guessed word's letter pattern to ciphertext and recover the partial key.
- Explain why 26! keys is large but insufficient, and why polyalphabetic ciphers are the historical response.

## The Problem

An accounting firm encrypts payroll messages with a monoalphabetic cipher. You intercept ciphertext blocked in groups of five characters. You know the firm is an accounting firm, so the word "financial" is likely. The cipher has 26! ≈ 4 × 10^26 possible keys — brute force is infeasible, but frequency analysis and a probable-word attack crack it in minutes. This lesson builds both attacks from scratch.

## The Concept

### Caesar cipher: shift by k

Julius Caesar's cipher maps a→D, b→E, …, z→C (shift k=3). The generalization allows any k from 0 to 25, making k the key. There are only 26 keys; brute force takes seconds. The `code/main.py` demo encrypts and decrypts with arbitrary k.

| Plaintext | k=3 | k=7 | k=13 (ROT13) |
|-----------|-----|-----|---------------|
| attack | DWWDFN | haahaU | nggnpx |
| hello | KHOOR | olssv | uryyb |
| retreat | UHWUHDW | ylalyha | ertrerg |

### Monoalphabetic substitution: 26! keys

The improvement: map each of the 26 letters to an arbitrary other letter. The key is the 26-letter ciphertext alphabet. Example:

```
plaintext:   a b c d e f g h i j k l m n o p q r s t u v w x y z
ciphertext: Q W E R T Y U I O P A S D F G H J K L Z X C V B N M
```

With this key, `attack` becomes `QZZQEA`. The key space is 26! ≈ 4 × 10^26. Even at 1 ns per key on a million parallel chips, exhaustive search takes ~10,000 years. The SVG (`assets/substitution-ciphers.svg`) diagrams the key space and the brute-force wall.

### Frequency analysis: the real break

Despite the huge key space, the cipher falls easily. Natural languages have skewed statistics. English letter frequencies:

| Rank | Letter | Approx. freq | Rank | Letter | Approx. freq |
|------|--------|--------------|------|--------|--------------|
| 1 | e | 12.7% | 7 | s | 6.3% |
| 2 | t | 9.1% | 8 | h | 6.1% |
| 3 | a | 8.2% | 9 | r | 6.0% |
| 4 | o | 7.5% | 10 | d | 4.3% |
| 5 | i | 7.0% | 11 | l | 4.0% |
| 6 | n | 6.7% | 12 | u | 2.8% |

Common digrams: th, in, er, re, an. Common trigrams: the, ing, and, ion. The attack: rank ciphertext letters by frequency, tentatively map the top one to e, the next to t, look for `tXe` (suggesting X=h) and `thYt` (suggesting Y=a), then `aZW` (suggesting "and"). Each guess fills more of the key and makes subsequent guesses easier. The `code/main.py` demo counts ciphertext frequencies and prints the ranked guess.

### Probable-word attack

When context gives a likely word — "financial" in an accounting firm's message — the attack matches the word's letter pattern. "financial" has a repeated `i` separated by four letters. Find that pattern in the ciphertext, align the word, and deduce key letters. The chapter example finds "financial" at ciphertext position 30 by testing which candidate position also has the `n` and `a` in the right relative places. Once aligned, the rest of the key falls out via frequency analysis.

### Worked example: breaking the accounting-firm ciphertext

The chapter gives a concrete ciphertext from an accounting firm, blocked into groups of five:

```
Ctbmn Byctc Bt Jds Qxbns Gst Jc Btswx Ctqtz Cqvu J
QJ SGS T JQZZ MNQJ S VLNSX VSZ JU JDSTS JQUUS JUBX J
Dsksu J Sntk Bgaqj Zbgyq T Lctz Bnybn Qj Sw
```

The word "financial" has a repeated letter (`i`) with four other letters between the two occurrences. Search for repeated ciphertext letters at that spacing: 12 candidate positions appear, but only positions 31 and 42 also have the next letter (`n` in plaintext) repeated in the correct place. Of those two, only position 31 also has `a` correctly positioned. So "financial" begins at ciphertext position 30. From there, deduce the key using frequency statistics and look for nearly complete words. The break is deterministic once the probable word anchors the alignment.

### Digram and trigram tables used in practice

Beyond single-letter frequencies, the analyst maintains digram and trigram tables. The most common English digrams (approximate, in order): th, in, er, re, an, he, en, nd, ha, et. The most common trigrams: the, ing, and, ion, ent, for, tio, her, ter, hat. When the analyst has a tentative mapping for three or four letters, checking which digram/trigram frequencies best match English narrows the remaining choices. The columnar transposition cipher (next lesson) preserves these frequencies exactly, which is the tell that distinguishes it from a substitution cipher.

### Why substitution fails and what comes next

Substitution preserves letter order and only disguises identity. Frequency analysis exploits the fact that English statistics survive the substitution. The historical fix is the **polyalphabetic cipher** (Vigenère), which uses multiple substitution alphabets selected by a key word, flattening the frequency distribution. Modern ciphers go further: they operate on bits, not letters, and cascade substitution (S-boxes) with transposition (P-boxes) over many rounds so that no statistical structure survives. The next lessons cover transposition, the one-time pad, and modern block ciphers.

## Build It

1. Run `python3 code/main.py`. It encrypts "attack at dawn" with k=3 and with a monoalphabetic key, decrypts both back, and runs frequency analysis on a sample ciphertext.
2. Feed the script a longer ciphertext (paste 500+ characters) and watch the frequency ranking converge on e, t, a.
3. Add a probable-word detector: search for the repeated-letter pattern of "financial" in the ciphertext and print candidate positions.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|---------------------|
| Caesar encrypt/decrypt | C = E_k(P) and P = D_k(C) round-trip | Round-trip recovers original for any k in 0..25 |
| Monoalphabetic encrypt | 26-letter key maps each letter once | Output has no unmapped letters |
| Frequency analysis | Ciphertext letter ranking matches English | e is most frequent in ciphertext; mapped to e, text becomes readable |
| Probable word | Pattern match finds the word position | The aligned word reveals 4+ key letters at once |

## Ship It

This lesson produces `outputs/substitution-attack-runbook.md`: step-by-step instructions for breaking a monoalphabetic cipher from intercepted ciphertext, including the frequency table to use and the probable-word pattern-matching method.

## Exercises

1. Encrypt "the quick brown fox" with Caesar k=7. Decrypt to verify. How many keys must a brute-force attacker try?
2. Generate a random monoalphabetic key and encrypt 2000 characters of English. Run the frequency analysis in `code/main.py`. How many letters are correctly guessed before any manual intervention?
3. Intercept the ciphertext "Ctbmn Byctc Bt Jds Qxbns" (blocked in fives). Assuming the word "financial" appears, find its position and recover at least 6 key letters.
4. Why does ROT13 work as "obfuscation" on Usenet but fail as encryption? Relate to the 26-key space.
5. Design a simple polyalphabetic cipher using two Caesar alphabets alternated by position. Encrypt 1000 characters and compare the frequency distribution to the monoalphabetic case.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|------------------------|
| Caesar cipher | "shift by three" | A substitution with k=3; only 26 keys total |
| Monoalphabetic cipher | "arbitrary alphabet" | 26-letter permutation key; 26! keys, but broken by statistics |
| Frequency analysis | "counting letters" | Exploiting natural-language letter/digram/trigram frequencies to recover the key |
| Probable word | "guess the word" | Matching a guessed word's letter pattern to ciphertext to anchor the key |
| Digram | "two-letter combo" | Pairs like th, in, er whose frequency betrays substitution |
| Trigram | "three-letter combo" | Triples like the, ing, and that confirm key guesses |
| Polyalphabetic | "multiple alphabets" | Using several substitution alphabets to flatten frequency distribution |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks* (5th ed.), Section 8.1.2
- Kahn, *The Codebreakers* — history of substitution ciphers from antiquity to WWII
- Singh, *The Code Book* — accessible introduction to classical cryptanalysis
- Friedman, "The Index of Coincidence and Its Applications in Cryptanalysis" (1922)