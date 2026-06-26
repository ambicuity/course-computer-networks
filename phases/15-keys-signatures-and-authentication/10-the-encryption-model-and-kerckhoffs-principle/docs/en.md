# The Encryption Model and Kerckhoffs's Principle

> Modern cryptography replaces pencil-and-paper scrambles with two functions, `C = E_K(P)` and `P = D_K(C)`, parameterised by a short secret `K` chosen from a key space of size `2^k`. A symmetric-key cipher uses the same `K` for both operations; an asymmetric cipher uses a public encryption key `E` and a private decryption key `D` linked by a one-way trapdoor (RSA, Diffie-Hellman, ECC). Auguste Kerckhoffs stated the rule in 1883: the algorithm must be public and only the keys may be secret. Trying to keep the algorithm secret — "security by obscurity" — has failed every notable time in history (COMP128 broken, CSS for DVDs, A5/1, WEP). Brute-force work is exponential in the key length: 64 bits is `1.8 × 10^19` candidates (within reach of national labs in 2026), 128 bits is `3.4 × 10^38` (AES-128 baseline), 192 bits is `6.2 × 10^57` (AES-192), 256 bits is `1.2 × 10^77` (AES-256). Cryptanalysis comes in three forms: ciphertext-only (newspaper cryptograms), known-plaintext (cable-tap with "login:" headers), and chosen-plaintext (a malicious encryption oracle). The lesson builds a key-space calculator, a Caesar and Vigenère explorer, and a small known-plaintext demo.

**Type:** Learn
**Languages:** Python (stdlib only), pencil-and-paper crypto puzzles
**Prerequisites:** Phase 1 (binary and hex), Phase 5 (probability)
**Time:** ~60 minutes

## Learning Objectives

- Write the encryption model as `C = E_K(P)` and `P = D_K(C)`, and prove that the decryption function is the inverse of the encryption function on the chosen key.
- Compute the size of a key space as `2^k` for a `k`-bit key, and convert this into a back-of-the-envelope work factor in years at a given number of trials per second.
- State Kerckhoffs's principle in his own terms, give three historical examples of "security by obscurity" failing, and explain why public algorithms attract more attacks and therefore more confidence.
- Distinguish ciphertext-only, known-plaintext, and chosen-plaintext attack models, and identify a real-world setting where each applies.
- Demonstrate the weakness of small keys by exhaustively searching the Caesar key space (25 candidates) and the Vigenère key space (26^k candidates).
- Implement a key-stream XOR scrambler in stdlib Python, then use it to encrypt and decrypt a short message with a known key.

## The Problem

A startup wants to ship a "military-grade" message app. The founders write a custom substitution table and a custom 64-bit block mixer and refuse to publish either, arguing that secrecy of the design is a feature. Six months later an ex-contractor posts the source code on a forum; within days an intern at a rival firm reverses the entire scheme in a weekend. The post-mortem reveals three mistakes: the algorithm is shorter than the security budget allows, the key is shorter than the algorithm, and nobody outside the founders ever tried to break it.

The deeper mistake is conceptual. The founders treated the algorithm as the secret. Kerckhoffs, writing in *La Cryptographie Militaire* in 1883, stated the rule that has guided every successful cipher since: the system must not require secrecy, and it must be able to fall into enemy hands without inconvenience. The algorithm is *expected* to be public; the *key* is the only secret. Public algorithms are studied by thousands of academic cryptanalysts, broken if breakable, and trusted precisely *because* they survive that attention.

## The Concept

### The encryption model as two functions

The model in Fig. 8-2 of the chapter has three actors: Alice (sender), Bob (receiver), and Trudy (the eavesdropper or active intruder). Trudy sees the *ciphertext* C on the wire; Alice and Bob share the *key* K.

| Quantity | Notation | Visible to Trudy? |
|---|---|---|
| Plaintext | P | No (or yes, for a chosen-plaintext attack) |
| Ciphertext | C = E_K(P) | Yes |
| Key | K | No (or partially) |
| Algorithms | E, D | Yes — must be public |

The compound operation `D_K(E_K(P))` must equal `P` for every P in the message space. This is the **correctness** property. It is necessary but not sufficient for security — a correct cipher with `K = 0` is correct and useless.

### Key space and the work factor

For a key of `k` bits the key space has `2^k` elements. If the attacker can test `t` keys per second, the **expected** search time is `2^k / (2t)` seconds (the factor of 2 comes from the average position of the key in a uniform random search).

| k | 2^k | Years at `10^9` keys/sec | Years at `10^12` keys/sec |
|---|---|---|---|
| 32 | `4.3 × 10^9` | `0.07 s` | `70 us` |
| 56 | `7.2 × 10^16` | `2.3 years` | `8 hours` |
| 64 | `1.8 × 10^19` | `570 years` | `210 days` |
| 128 | `3.4 × 10^38` | `1.1 × 10^22` years | `1.1 × 10^19` years |
| 192 | `6.2 × 10^57` | `2.0 × 10^41` years | `2.0 × 10^38` years |
| 256 | `1.2 × 10^77` | `3.7 × 10^60` years | `3.7 × 10^57` years |

The "years" columns are why the chapter says 64-bit keys keep out your kid brother, 128-bit keys cover commerce, and 256-bit keys resist nation-state adversaries. The DES key (56 bits) is listed separately because it is a special historical case: in 1977 Diffie and Hellman estimated a $20M machine could break it in a day; a 2006 replica called **COPACOBANA** (University of Bochum and Kiel) cost $10,000 and does the same. The number of operations is unchanged; the cost per operation fell.

### Kerckhoffs's principle, in his own words

Kerckhoffs's principle: "All algorithms must be public; only the keys are secret." The chapter paraphrases it this way. The corollary is that a cipher's strength is the *minimum of* (a) the cost of breaking the algorithm given the key, and (b) the cost of guessing the key. Property (a) is what the public reviews over years; property (b) is the work factor of the table above. A scheme is only as strong as the weaker of the two.

The principle is sometimes called Shannon's maxim when stated in the 1940s ("the enemy knows the system") and was the foundation of the British **COLOSSUS** attacks on the Lorenz cipher in 1944: the British knew the algorithm but not the wheel settings, which is the same key-vs-algorithm split Kerckhoffs described.

### Three attack models

The chapter names three principal attack settings:

- **Ciphertext-only.** Trudy has C, perhaps many of them. Newspaper cryptograms are an example. Breaking a monoalphabetic substitution by frequency analysis is a ciphertext-only attack.
- **Known-plaintext.** Trudy has matched (P, C) pairs. A classic example is a login prompt: the bytes `login: ` appear in many protocol exchanges, and matching them against the corresponding ciphertext gives the analyst a known block. The chapter's "many real systems are vulnerable to this" line follows from this fact.
- **Chosen-plaintext.** Trudy can submit any P of his choice and read C. The "Mafia in the middle" scenario — a malicious server that pretends to be your bank and lets you "log in" — is the modern example. A cipher that resists this is **semantically secure** in the IND-CPA sense (Goldwasser-Micali 1982, formalising exactly this property).

A fourth model, **chosen-ciphertext**, is mentioned for completeness: Trudy can submit any C and read the corresponding P (a decryption oracle). Modern provable-security proofs (Cramer-Shoup, RSA-OAEP) work in this model.

### Why published algorithms get stronger

The chapter is emphatic: "by publicizing the algorithm, the cryptographer gets free consulting from a large number of academic cryptologists." Every successful modern cipher has been published, attacked, and survived:

- **DES** (1977) — FIPS 46; attacked, weakened, replaced by 3DES and then AES.
- **AES / Rijndael** (2001) — five-year bake-off winner; published as FIPS 197.
- **SHA-3** (2012) — selected from 64 candidates (Keccak).
- **RSA, Diffie-Hellman, ECC** — all published in the 1970s-80s.

Counter-examples (algorithms kept secret and then broken): **CSS** for DVD (1996) — broken 1999; **WEP** for Wi-Fi (1999) — short IV, broken 2001; **A5/1** for GSM (1987) — broken publicly 1999; **COMP128** for SIM — broken at a 1998 conference; **KASUMI / A5/3** — related-key attack 2010.

### Security by obscurity vs open review

The chapter calls "security by obscurity" a non-starter. A secret algorithm is reverse-engineered, leaked, or stolen eventually, and the unknown attack surface keeps getting worse. A public algorithm is attacked constantly; the known attack surface is bounded. The lesson is that *time* is a function of attention, and obscurity attracts less academic attention than publication.

## Build It

`code/main.py` is a stdlib-only toolkit. It contains:

1. `work_factor(k_bits, trials_per_sec)` — converts a key length and rate into years of expected search.
2. `caesar_encrypt(text, shift)` / `caesar_decrypt(text, shift)` — circular shift on the 26-letter alphabet.
3. `vigenere_encrypt(text, key)` / `vigenere_decrypt(text, key)` — repeating key XOR over A-Z.
4. `xor_stream(plaintext, key)` — the core stream-cipher primitive used in OTP, PGP, and CTR mode.
5. `frequency_attack(ciphertext)` — recovers a monoalphabetic key from letter frequency, illustrating a ciphertext-only attack.

Run `python3 code/main.py`. Try the Caesar attack with a 25-element brute force; try the Vigenère attack by varying the key length. The work-factor table is computed at startup.

## Use It

| Task | Tool | What good looks like |
|---|---|---|
| Choose a key size | `work_factor()` | You pick 128 bits minimum for symmetric; explain why 64 is no longer adequate. |
| Encrypt a message | `xor_stream()` | You can recover the plaintext by re-running with the same key. |
| Brute-force Caesar | shift 0..25 loop | All 25 candidates appear; only one is a real English word. |
| Break a monoalphabetic cipher | `frequency_attack()` | E/T/A/O/I/N frequency counts match English; the recovered plaintext is readable. |
| Reject "obscure" schemes | principle checklist | You can list three historical failures (CSS, WEP, A5/1) and explain why publication is the antidote. |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **key-length work-factor table** for `k = 32, 40, 56, 64, 80, 96, 112, 128, 192, 256` at trial rates `10^6, 10^9, 10^12` keys/sec.
- A **Kerckhoffs's-principle checklist** documenting, for any proposed cipher, (a) the algorithm is public, (b) the key is the only secret, (c) the key space is large, (d) the algorithm has been publicly reviewed.
- A **one-pager** mapping each "obscure scheme" failure (CSS, WEP, A5/1, COMP128) to the year broken and the technique used.

Start from `outputs/prompt-the-encryption-model-and-kerckhoffs-principle.md`.

## Exercises

1. Compute the expected brute-force time for a 40-bit key at `10^9` keys/sec. Convert the answer into a sentence ("less than a second / a coffee break / a working day / my lifetime").
2. A scheme uses 1024 different algorithms, each selected uniformly at random per session. An attacker who has neither the algorithm nor the key faces `1024 × 2^k` candidates. Why is this *not* 11 bits of extra security on top of a 40-bit key? (Hint: try `2^40` and `2^50` and read the table.)
3. Show that the Caesar cipher has 25 keys (not 26), and that one of them maps "attack" to "attack". What does this say about ciphertext-only attacks?
4. A message of 200 bytes is encrypted with `xor_stream` using a 4-byte key. How does the effective key space compare with a 800-byte random pad? (Hint: think about the inner loop of the attack.)
5. Your colleague proposes a 48-bit symmetric key and argues that "the algorithm is secret, so 48 bits is plenty." Apply the Kerckhoffs checklist. How many items does the proposal fail? What do you recommend?
6. Using `frequency_attack` on a 1000-character monoalphabetic ciphertext, predict how many of the 26 letters will appear above the mean English frequency of `0.0385`. Compare with the simulator's output.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Plaintext | "the message" | The original, unencrypted data P |
| Ciphertext | "the scrambled message" | The encrypted data C = E_K(P) |
| Symmetric key | "shared secret" | K used for both E and D; both parties must know it |
| Public/private key | "asymmetric" | Public E for everyone, private D for the owner |
| Key space | "all possible keys" | The set of `2^k` candidates for a k-bit key |
| Work factor | "brute-force cost" | Expected number of trials to find the key, `2^k / 2` on average |
| Kerckhoffs's principle | "don't keep the algorithm secret" | Algorithms public, keys secret |
| Security by obscurity | "secret algorithm" | A non-property; has failed for every notable historical cipher |
| Ciphertext-only attack | "blind attack" | Attacker sees only C |
| Known-plaintext attack | "have some matches" | Attacker has matched (P, C) pairs |
| Chosen-plaintext attack | "Mafia in the middle" | Attacker can encrypt any P of his choice |

## Further Reading

- **Kerckhoffs, A. (1883)** — "La Cryptographie Militaire," *Journal des Sciences Militaires* 9:5-38, 161-191. The original statement of the principle.
- **Shannon, C. E. (1949)** — "Communication Theory of Secrecy Systems," *Bell System Technical Journal* 28(4):656-715. The "enemy knows the system" reformulation.
- **Diffie, W. & Hellman, M. E. (1977)** — "Exhaustive Cryptanalysis of the NBS Data Encryption Standard," *Computer* 10(6):74-84. The $20M DES-breaking machine estimate.
- **Kumar, S. et al. (2006)** — "Breaking Ciphers with COPACOBANA." The $10K modern replica.
- **NIST FIPS 197** (2001) — Advanced Encryption Standard.
- **Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §8.1** — the source chapter.
- **Ferguson, N., Schneier, B. & Kohno, T. (2010)** — *Cryptography Engineering*.
