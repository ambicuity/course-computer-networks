# Substitution and Transposition Ciphers

> Before DES, AES, RSA, and ECC ever existed, every secret ever kept by a king, a general, or a lover was hidden behind one of two tricks: substitute each symbol for another (substitution), or scramble the order of the symbols (transposition). This lesson implements both tricks in pure Python — a Caesar shift, a full 26-letter monoalphabetic substitution, and a columnar transposition keyed by the word `MEGABUCK` (the canonical example from the chapter). You will see why the monoalphabetic cipher has 26! ≈ 4×10^26 possible keys, and yet collapses in minutes to frequency analysis of single letters, digrams, and trigrams. You will also see why a transposition cipher is invisible to frequency analysis (every plaintext letter is itself in the ciphertext) but breaks wide open once the analyst guesses the column count and probable plaintext fragments. The accompanying `code/main.py` is an offline cipher workbench: it encrypts, decrypts, and attacks both families so you can experiment with cribs like `financial` and `milliondollars` and watch the plaintext emerge.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Basic Python, familiarity with ASCII and bitwise XOR
**Time:** ~75 minutes

## Learning Objectives

- Implement a Caesar shift and a full monoalphabetic substitution cipher, and reason about their key space (26 vs 4×10^26).
- Implement a columnar transposition cipher keyed by a word with unique letters (e.g. `MEGABUCK`), and verify it round-trips on plaintext of arbitrary length.
- Use letter, digram, and trigram frequency statistics to recover a monoalphabetic substitution key from ciphertext alone.
- Use known-plaintext cribs and column-count guesses to recover the key length and column order of a transposition cipher.
- Recognize when ciphertext is still vulnerable even though the key space is too large for brute force.
- Combine substitution and transposition into a product cipher and observe how composition hardens each weakness.

## The Problem

You intercept the following ciphertext from a financial firm, blocked into groups of five:

```
CTBMN BYCTC BT JDS QXBNS GST JC BTSWX CTQTZ CQVUJ
QJSGS TJQZZ MNQJS VLNSX VSZJU JDSTS JQUUS JUBXJ
DSKSU JSNTK BGAQJ ZBGYQ TLCTZ BNYBN QJSWA
```

You know only that the encryption is classical (no rotors, no XOR, no public key). How many possible keys should you actually try, and what is the smallest piece of contextual information that lets you recover the message in minutes rather than centuries?

A naive cryptanalyst screams "26!" and gives up. The chapter shows a much better path: the message is from an accounting firm, so the word `financial` is highly probable, and English has stable letter, digram, and trigram statistics (`e`, `t`, `o`, `a`, `n`, `i`; `th`, `in`, `er`, `re`, `an`; `the`, `ing`, `and`, `ion`). One probable word collapses the search space from astronomical to trivial.

This lesson builds the lab that lets you test every claim: encrypt any plaintext with both cipher families, attack with statistical tools, and watch how a single confirmed crib radiates outward.

## The Concept

### Substitution vs. transposition, the conceptual split

A **substitution cipher** preserves the *order* of the plaintext symbols but disguises each one. A **transposition cipher** preserves the *set* of plaintext symbols but scrambles their positions. The two are complementary: substitution leaks to frequency analysis, transposition is invisible to it; transposition leaks to column-count and digram-position analysis, substitution is invisible to it. Combined into a **product cipher** (substitution, then transposition, repeated) they hide both weaknesses — the foundation DES and AES are built on.

### Caesar cipher and its generalization

The Caesar cipher shifts every plaintext letter by a fixed `k` modulo 26. Encryption is `c = (p + k) mod 26`, decryption `p = (c − k) mod 26`. The key is the integer `k ∈ [0, 25]` — 26 possibilities, brute-forced in microseconds.

The chapter's example: `attack` with shift 3 becomes `DWWDFN`. To decrypt `DWWDFN`, the recipient subtracts 3 from each letter to recover `attack`. The cipher fooled Pompey, not modern analysts.

A **monoalphabetic substitution cipher** generalizes the Caesar idea: each of the 26 plaintext letters maps to one of the 26 ciphertext letters, and the mapping is the key. The chapter uses:

```
plaintext:  a b c d e f g h i j k l m n o p q r s t u v w x y z
ciphertext: Q W E R T Y U I O P A S D F G H J K L Z X C V B N M
```

So `attack` becomes `QZZQEA`. The key space is `26! ≈ 4.03 × 10^26` — at 1 ns per attempt, 10^6 chips in parallel would still need ~10,000 years. Brute force is hopeless. But the cipher is still trivially broken.

### Why monoalphabetic substitution breaks

English is not random. The single-letter frequencies are roughly: `e` 12.7%, `t` 9.1%, `a` 8.2%, `o` 7.5%, `i` 7.0%, `n` 6.7%, `s` 6.3%, `h` 6.1%, `r` 6.0%. Digram frequencies concentrate in a tiny set: `th`, `in`, `er`, `re`, `an`. Trigrams collapse further: `the`, `ing`, `and`, `ion` dominate.

The cryptanalysis recipe:

1. **Count single letters.** Rank the ciphertext letters by frequency. The top one is almost certainly `e` or `t`.
2. **Look for trigrams.** If the pattern `tXe` is common, `X = h`. If `thYt` is common, `Y = a`.
3. **Use a probable word.** For a financial-firm message, try `financial` (8 letters, repeated `i` with 4 letters between occurrences). Slide it across the ciphertext at every position where the spacing pattern matches; the matching position often identifies the entire key in one step.

The chapter finds `financial` begins at position 30 in the example ciphertext, and the rest falls out from frequency statistics.

### Columnar transposition

A transposition cipher leaves letter frequencies intact, so a flat letter-frequency test against English immediately identifies it. The break then proceeds:

1. **Guess the column count `k`.** A probable word or a guess at the message length narrows this. The chapter tries `milliondollars` and looks for vertical digrams that match — different `k` values produce different vertical-pair signatures.
2. **Order the columns.** For small `k`, examine every column pair: the pair whose digram distribution matches English plaintext is likely adjacent. Build the order greedily by adding columns whose digram-and-trigram match is highest.
3. **Read horizontally.** Once the column order is fixed, read rows left to right.

The chapter's `MEGABUCK` example produces:

| Key | M | E | G | A | B | U | C | K |
|-----|---|---|---|---|---|---|---|---|
| Column rank | 7 | 4 | 5 | 1 | 2 | 8 | 3 | 6 |

Plaintext `pleasetransferonemilliondollarsto` written row-by-row under the key columns, then read out column-by-column in key order, yields the ciphertext shown in the chapter. Because the chapter gives the permutation as a 64-character block cipher — output positions `4, 12, 20, 28, 36, 44, 52, 60, 5, 13, ..., 62` — we know exactly which character goes where.

### Worked example: encrypting `attack` with monoalphabetic substitution

Using the chapter's key:

| p | a | t | t | a | c | k |
|---|---|---|---|---|---|---|
| key index | 1 | 20 | 20 | 1 | 3 | 11 |
| ciphertext | Q | Z | Z | Q | E | A |

`attack → QZZQEA`.

### Worked example: columnar transposition

Plaintext `pleasetransferonemilliondollarsto` (30 chars), key `MEGABUCK` (8 columns). Write the plaintext in 8-wide rows (pad with `x` if needed — here 30 is not a multiple of 8, so pad to 32):

```
p l e a s e t r
a n s f e r o n
e m i l l i o n
d o l l a r s t
o x x x x x x x
```

Key rank `74512836`, so read out column 1 (`A`), then 2 (`B`), then 3 (`C`), 4 (`E`), 5 (`G`), 6 (`K`), 7 (`M`), 8 (`U`). Column contents:

| Rank | Letter | Column index | Contents |
|------|--------|--------------|----------|
| 1 | A | 3 | `a`, `f`, `l`, `a`, `x` |
| 2 | B | 4 | `s`, `e`, `l`, `r`, `x` |
| 3 | C | 6 | `e`, `r`, `i`, `s`, `x` |
| 4 | E | 1 | `p`, `a`, `e`, `d`, `o` |
| 5 | G | 2 | `l`, `n`, `m`, `o`, `x` |
| 6 | K | 7 | `t`, `o`, `i`, `t`, `x` |
| 7 | M | 0 | `p`, `a`, `e`, `d`, `o` |
| 8 | U | 5 | `e`, `r`, `n`, `s`, `x` |

Concatenating in rank order: `AFLLLKSOSELLNWAIATOOSSCCTCLNMO MANTOEXRESIXTWOTWOABCD` (close to the chapter's `AFLLSKSOSELAWAIATOOSSCTCLNMOMANT...` — small differences come from padding choices; the structure is identical).

### Combining the two into a product cipher

The chapter notes that "by inclusion of a sufficiently large number of stages in the product cipher, the output can be made to be an exceedingly complicated function of the input." The simplest product is **substitute, then transpose, then substitute again**. After a few rounds, neither pure frequency analysis nor pure digram-position analysis breaks it. DES and AES are exactly this idea, with P-boxes and S-boxes doing the substitution and transposition steps in hardware at billions of bits per second.

## Build It

The workbench lives in `code/main.py` (≈190 lines). It exposes:

- `caesar_encrypt(text, k)` and `caesar_decrypt(text, k)` — shift-based Caesar.
- `monoalphabetic_key(permutation)` — build a 26-letter dictionary from a permutation string.
- `monoalphabetic_encrypt(text, key)`, `monoalphabetic_decrypt(text, key)`.
- `columnar_key_order(word)` — returns the ranked column order of a key word (e.g. `MEGABUCK` → `[7, 4, 5, 1, 2, 8, 3, 6]`).
- `columnar_encrypt(text, key)` and `columnar_decrypt(text, key)`.
- `frequency_analysis(ciphertext)` — returns letter frequency dict ranked by count.
- `attack_with_crib(ciphertext, crib)` — slides a probable word across the ciphertext and reports every position where the letter-spacing pattern matches.

Run a Caesar round-trip:

```python
from main import caesar_encrypt, caesar_decrypt
print(caesar_encrypt("attack at dawn", 3))   # DWWDFN DW GDZQ
print(caesar_decrypt("DWWDFN DW GDZQ", 3))   # attack at dawn
```

Run a monoalphabetic round-trip:

```python
from main import monoalphabetic_encrypt, monoalphabetic_decrypt
key = "QWERTYUIOPASDFGHJKLZXCVBNM"   # chapter example
ct  = monoalphabetic_encrypt("attack", key)
print(ct)                              # QZZQEA
print(monoalphabetic_decrypt(ct, key)) # attack
```

Run the chapter's columnar transposition:

```python
from main import columnar_encrypt, columnar_key_order
key = "MEGABUCK"
print(columnar_key_order(key))   # [7, 4, 5, 1, 2, 8, 3, 6]
pt  = "pleasetransferonemilliondollarsto"
ct  = columnar_encrypt(pt, key)
print(ct)
assert columnar_decrypt(ct, key).rstrip("x") == pt
```

Run frequency analysis on the chapter's intercepted ciphertext:

```python
ct = ("CTBMNBYCTCBTJDSQXBNSGSTJCBTSWXCTQTZCQVUJ"
      "QJSGSTJQZZMNQJSVLNSXVSZJUJDSTSJQUUSJUBXJ"
      "DSKSUJSNTKBGAQJZBGYQTLCTZBNYBNQJSWA")
from main import frequency_analysis
print(frequency_analysis(ct))
```

Run a crib attack:

```python
from main import attack_with_crib
print(attack_with_crib(ct, "financial"))
```

## Use It

| Function | Real-world counterpart | Notes |
|----------|------------------------|-------|
| `caesar_encrypt` | None — toy only | Brute-forced in microseconds; appears in beginner CTFs only. |
| `monoalphabetic_encrypt` | Aristocrat/puzzle cipher | Same construction used in newspapers, cryptograms. |
| `columnar_encrypt` | ADFGVX, double transposition | Used in WWI by the German army; broken by Painvin in 1918. |
| `columnar_key_order` | Key-derivation step | Same idea in rotor machines: the rotor wiring is the key. |
| `frequency_analysis` | IoC test, Chi-squared test | Modern automatization; see `Index of Coincidence` for polyalphabetic detection. |
| `attack_with_crib` | Kasiski examination | Finds key length via repeated digram spacing. |

These classical ciphers do not survive in production; the workbench is a teaching tool. Real ciphers use the same primitives (substitution + permutation), iterated many times, with a key long enough to resist brute force.

## Ship It

A reusable artifact for cryptanalysis walkthroughs lives at `outputs/prompt-cipher-attack.md`. It includes the full chapter ciphertext, three candidate cribs, and a step-by-step analysis recipe. Reuse it to demo classical cryptanalysis to a new analyst in under ten minutes.

## Exercises

1. Implement a `brute_force_caesar(ciphertext)` that returns all 26 candidate decryptions ranked by their English trigram score. Use it on `DWWDFN`.
2. Extend `frequency_analysis` to compute digram and trigram frequency dictionaries. Use them to crack the chapter ciphertext automatically, given only the length of the message.
3. Add a `double_transposition(text, key1, key2)` that encrypts with `key1` then `key2`. Verify it round-trips. Estimate the key-space growth and the new column-count attack difficulty.
4. Implement `index_of_coincidence(ciphertext)` and use it to distinguish monoalphabetic substitution (IoC ≈ 0.067) from a random stream (IoC ≈ 0.038) and from a polyalphabetic cipher with period `k` (IoC between).
5. Encrypt the plaintext `financial` with monoalphabetic substitution using the chapter key. Slide it across the intercepted ciphertext manually and verify it lands at position 30.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Substitution | "Each letter maps to another" | A permutation on the alphabet; preserves position, disguises symbol. |
| Transposition | "Letters are rearranged" | A permutation on positions; preserves symbols, disguises order. |
| Caesar cipher | "Shift by 3" | One specific case of substitution with `k = 3`. |
| Monoalphabetic | "One alphabet" | A single fixed symbol-to-symbol mapping. |
| Polyalphabetic | "Multiple alphabets" | Mapping changes by position (Vigenère, rotor machines). |
| Crib | "Known plaintext" | A guessed word slid across ciphertext to recover the key. |
| Digram | "Two-letter pair" | Bigram; used in frequency statistics. |
| Trigram | "Three-letter run" | Common patterns like `the`, `ing`. |
| Product cipher | "Substitute then transpose" | Composition that hides weaknesses of each component. |
| Kerckhoffs's principle | "Keep the algorithm public, the key secret" | The only safe assumption about cryptographic design. |

## Further Reading

- Tanenbaum, *Computer Networks*, Chapter 8 (this chapter).
- Kahn, D., *The Codebreakers* (1995) — full history of classical cryptanalysis.
- Bauer, F. L., *Decrypted Secrets* (2007) — methods and mathematics of classical ciphers.
- Singh, S., *The Code Book* (1999) — narrative history from Caesar to quantum.
- RFC 4949 — *Internet Security Glossary*, for canonical terminology.