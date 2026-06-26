# Reed-Solomon codes over finite fields for burst-error correction

> A scratched CD still plays. A DSL line keeps syncing even though the copper picks up a 100-bit burst of noise from a fridge motor. A deep-space probe returns a clean image even though the receiver's Viterbi decoder collapses into bursts whenever the signal-to-noise ratio dips. All three lean on **Reed-Solomon (RS) codes**: linear, systematic block codes that operate not on individual bits but on **m-bit symbols** drawn from a finite field GF(2^m). The classic deployed instance is the **(255, 233) RS code over GF(2^8)**: it appends **32 redundancy symbols** to 233 data symbols, and with `2t = 32` redundancy it corrects up to **t = 16 symbol errors** anywhere in the 255-symbol block. Because an 8-bit symbol absorbs a whole burst, those 16 symbol errors can be **16 consecutive bytes — a 128-bit burst** — and the code still recovers. With erasures (locations known, as with a CD scratch) the same 32 symbols correct **32 erasures**, since the Berlekamp-Massey step no longer has to discover error locations. RS codes ride inside the **CD-ROM CIRC** (two RS codes, C1 (32,28) and C2 (28,24), cross-interleaved), **DVD/Blu-ray** ECC blocks, **DVB** and **ATSC** transport, **DSL** (Reed-Solomon + interleaver in ITU G.992), and the outer code of nearly every concatenated space link (CCSDS 131.0-B). The textbook places RS as the third of four error-correcting codes because it is the canonical answer to *burst* errors, exactly the failure mode that defeats bit-oriented Hamming and convolutional codes.

**Type:** Build
**Languages:** Python
**Prerequisites:** Hamming codes and Hamming distance (Phase 4, lesson on error-correcting codes), modular arithmetic, basic polynomial algebra
**Time:** ~85 minutes

## Learning Objectives

- Explain why a Reed-Solomon code treats an m-bit burst and a single-bit error as the same unit of correction, and compute the burst-correcting power of an (n, k) RS code.
- Construct the finite field GF(2^8) from an irreducible polynomial (0x11D) and perform addition, multiplication, and inversion on its elements.
- Encode a (255, 223) RS codeword by evaluating the generator polynomial g(x) = (x - α^1)(x - α^2)…(x - α^32) and appending the remainder as 32 parity symbols.
- Decode a corrupted codeword using syndrome computation, the Berlekamp-Massey algorithm for the error-locator polynomial, Chien search, Forney's algorithm, and correction — and identify each step's output.
- Distinguish error correction (up to t unknown-location errors) from erasure correction (up to 2t known-location errors) and explain why erasures double the budget.
- Read a real-world concatenated stack (CCSDS, DVB, CD CIRC) and identify which layer mops up bursts after the inner code fails.

## The Problem

A satellite ground station receives a 2 Mbps stream from a low-Earth-orbit imager. The inner code is a rate-1/2 convolutional code decoded with a Viterbi decoder; on a clean pass it delivers a BER near 10^-9. But twice per pass, as the satellite crosses a radio-frequency interference band, the Viterbi decoder suffers a **decoding failure**: the noise overwhelms it for several hundred bit times, and instead of isolated bit flips the decoder emits a **burst** of ~150 consecutive wrong bits. A pure convolutional code cannot recover a burst that long — its constraint length k=7 only buys a few bits of memory — so the image downlink silently drops a 150-bit stripe through every frame. The engineer needs an outer code that can swallow a burst of this length and reconstruct the original symbols. CRCs only *detect*; Hamming corrects one bit; the answer is a Reed-Solomon outer code sized so that t × m ≥ the worst burst the inner decoder can emit.

## The Concept

### Symbols, not bits: why RS is the burst specialist

A Hamming code corrects single-bit errors; its check bits are functions of individual data bits. A Reed-Solomon code works one level up: the unit of data and the unit of error is an **m-bit symbol** (almost always a byte, m=8). The code lives in the finite field GF(2^m), where every element is a byte and arithmetic is done modulo an irreducible polynomial of degree m.

This single design choice is why RS is a burst specialist. A noise event that flips 7 consecutive bits inside one byte, and a noise event that flips 1 bit inside one byte, are **both exactly one symbol error** to the decoder. The decoder does not know or care how many bits inside the symbol flipped. Therefore the burst-correcting power of an RS code is `t × m` bits, where `t` is the number of symbol errors it can correct. For the (255, 233) RS code with t=16 and m=8, that is **128 consecutive bits** of corruption, fully corrected, with no special interleaving. See `assets/reed-solomon-codes-for-burst-errors.svg` for the symbol-vs-bit mapping.

### The finite field GF(2^8) and the generator polynomial

RS codes are defined over GF(2^m). For m=8 we use the field defined by the irreducible polynomial **p(x) = x^8 + x^4 + x^3 + x^2 + 1**, written as the 9-bit constant **0x11D**. Field elements are bytes 0x00..0xFF. Addition is bitwise XOR. Multiplication is polynomial multiplication modulo p(x); it is convenient to build two tables — a logarithm table and an exponential table — indexed by a primitive element α (for p(x)=0x11D, α = 0x02 is primitive).

A Reed-Solomon code is a **cyclic code** with generator polynomial

```
g(x) = (x - α^1)(x - α^2) ... (x - α^(2t))
```

For the (255, 223) code with 2t=32 parity symbols, g(x) has degree 32 and 32 roots: α^1 through α^32. The code's parameters come straight from this construction:

| Parameter | Value for (255, 223) | Meaning |
|---|---|---|
| m | 8 | bits per symbol |
| n | 2^m - 1 = 255 | codeword length in symbols |
| k | 223 | data symbols |
| 2t | n - k = 32 | parity symbols |
| t | 16 | correctable symbol errors |
| Burst capability | t × m = 128 bits | longest consecutive bit burst fully corrected |
| Erasure capability | 2t = 32 symbols | with known locations |
| Code rate | k/n ≈ 0.875 | fraction of the codeword that is data |

### Systematic encoding: append the remainder

A systematic RS code sends the k data symbols unchanged followed by the 2t parity symbols. Encoding treats the data as the high-order coefficients of a polynomial `d(x)` of degree k-1, computes the remainder of `x^(2t) · d(x)` divided by `g(x)`, and appends that remainder as the parity. Because `x^(2t)·d(x) = q(x)·g(x) + r(x)`, the codeword `c(x) = x^(2t)·d(x) - r(x)` is exactly divisible by g(x) — i.e. every root α^i (i=1..2t) is also a root of c(x). This divisibility is the invariant the decoder checks. `code/main.py` implements `rs_encode` with this long-division, returning the 223 data symbols plus 32 parity symbols as a 255-element list.

### Decoding: the five-step pipeline

When a codeword c arrives corrupted as `r = c + e` (where e is the error polynomial), the decoder reverses the encoding invariant. The standard pipeline is:

1. **Syndromes.** Evaluate r(x) at each root α^1 … α^2t. Because c(α^i)=0, `S_i = r(α^i) = e(α^i)`. If all S_i are zero, no error. Otherwise the syndromes are linear functions of the error locations and values. There are 2t syndromes.
2. **Error-locator polynomial.** The Berlekamp-Massey algorithm consumes the syndromes and produces Λ(x), the error-locator polynomial whose roots are α^(-j) for each error position j. Its degree equals the number of errors ν (≤ t) — if Berlekamp-Massey needs degree > t, the error pattern is uncorrectable.
3. **Chien search.** Test each position i=0..254 by evaluating Λ(α^(-i)); roots identify the exact symbol positions in error.
4. **Error magnitudes.** Forney's algorithm computes the value e_i at each located position using the syndromes and Λ(x).
5. **Correction.** Subtract e_i from r at each located position. The result is the original codeword; strip the 32 parity symbols to recover the data.

`code/main.py` implements steps 1, 2, and 3 (syndromes, Berlekamp-Massey, Chien search) and uses Forney's formula for magnitudes, decoding up to t errors on a 255-symbol block.

### Erasures double the budget

If the receiver knows *where* an error is — for example, a CD reader knows a byte sits under a scratch and the demodulator flagged it — that position becomes an **erasure** rather than an unknown error. Each erasure costs one syndrome instead of two (the location is given, only the magnitude is unknown), so 2t parity symbols correct **2t erasures** but only **t unknown errors**. CD CIRC exploits this: the C1 (32,28) and C2 (28,24) codes are shorted RS codes (n < 255) chosen so the outer C2 can correct up to 4 errors or 8 erasures per 28-symbol block.

### Concatenation: RS as the burst mop-up

The textbook's key deployment insight is that RS codes are rarely used alone. The dominant architecture is **concatenation**: an inner convolutional code handles isolated bit errors; an outer RS code, separated from the inner code by a **block interleaver**, absorbs the bursts the inner decoder emits when it fails. The interleaver spreads a contiguous burst across many RS codewords so that no single codeword sees more than t errors. The CCSDS 131.0-B standard for space links specifies exactly this: rate-1/2 convolutional inner code + (255, 223) RS outer code + convolutional interleaver (depth 5, I=5). DVB-S uses a (204, 188) shortened RS code (from (255,239)) outer code plus a convolutional interleaver with I=12.

### Where the parameters come from in practice

| Standard | RS code | Shortened from | t | Notes |
|---|---|---|---|---|
| CCSDS space | (255, 223) | full | 16 | outer of concatenated link |
| DVB-S/T | (204, 188) | (255, 239) | 8 | 188-byte MPEG-2 transport packet + 16 parity |
| ATSC A/53 | (207, 187) | (255, 235) | 10 | 187-byte payload + 20 parity |
| CD-ROM CIRC | C1 (32,28), C2 (28,24) | (255,k) | 2 each | cross-interleaved pair |
| DVD ECC | (208, 192), (182, 172) | GF(2^8) | 8, 5 | per-ECC-block |
| ADSL G.992.1 | (255, 239) | full | 8 | outer code over interleaved frame |

A **shortened** (n', k') code simply uses fewer than k data symbols and transmits n' < n symbols; the math is unchanged because the omitted high-order data symbols are treated as zero.

## Build It

1. Open `code/main.py` and run it: `python3 code/main.py`. It builds GF(2^8) tables, encodes a (255, 223) codeword, injects a configurable burst, and decodes it.
2. Read `build_field_tables()` and confirm that `gf_mul(0x57, 0x83)` reproduces the field multiplication (XOR of logs) — verify against a known test vector.
3. In `rs_encode`, trace the long division: the polynomial `x^32 · d(x)` is reduced modulo `g(x)`, and the 32-byte remainder becomes the parity.
4. In `rs_syndromes`, confirm that an *uncorrupted* codeword yields 32 zero syndromes — this is the divisibility invariant.
5. Run the burst loop in `main()`: it injects 1, 8, 16, 17, and 32 consecutive symbol errors at position 100. Watch bursts of 1–16 symbols (up to 128 bits) recover fully; the degree-16 locator from Berlekamp-Massey is resolved by Chien search and Forney, and the corrected data matches the original byte-for-byte.
6. The 17-symbol burst fails: Berlekamp-Massey needs a locator of degree 17 > t=16, and the decoder flags *uncorrectable* rather than returning silently-wrong data. That is the cliff.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify the field | `gf_mul`, `gf_inv` round-trip: `gf_mul(x, gf_inv(x)) == 1` for all nonzero x | 255/255 nonzero elements invert; 0 has no inverse by design |
| Verify encoding | Syndrome of a clean codeword is all-zero | 32 syndromes == 0 confirms divisibility by g(x) |
| Correct a 16-symbol burst | Inject 16 consecutive symbol errors, decode, compare | Decoded data byte-identical to original; locator degree == 16 |
| Hit the cliff | Inject 17 symbol errors | Decoder returns "uncorrectable" rather than silently wrong data |
| Erasure mode | Pass known error locations, inject 32 erasures | All 32 recovered (2t erasures correctable) |
| Read a real stack | Name the inner code, interleaver, and outer RS code in CCSDS 131.0-B | Convolutional rate-1/2 inner + interleaver + (255,223) RS outer |

## Ship It

Produce `outputs/prompt-reed-solomon-codes-for-burst-errors.md` containing: (1) the 32 syndromes your decoder computed for the demo burst, (2) the degree-16 error-locator polynomial Λ(x) as a coefficient list, (3) the 16 error positions and magnitudes found by Chien + Forney, and (4) a one-paragraph justification, with numbers, of why a (255, 223) outer code is sufficient for the satellite problem's 150-bit burst (hint: 150 bits < 128-bit burst? — recompute, you may need t=16 with interleaving, or a (255, 223) over a wider field, or shortening — state the trade).

## Exercises

1. A link emits bursts up to 200 bits. Pick an RS code over GF(2^8) (choose n, k) plus an interleaver depth that lets the outer code correct any single burst. Show the numbers: t required, interleaver depth, code rate.
2. The (255, 233) code is shortened to (204, 188) for DVB. How many symbol errors can the shortened code correct? Why does shortening not change t? Confirm with the generator polynomial degree.
3. Inject a burst of *exactly* 128 bits (16 consecutive byte errors) into the demo and confirm full recovery. Then inject 129 bits across 17 bytes and confirm the decoder declares failure. What does this say about the t × m boundary?
4. Add an erasure-decoding path: accept a list of known-bad positions, skip Berlekamp-Massey, build Λ(x) directly from the erasure locations, and correct 32 erasures. Verify 32 erasures recover but 33 do not.
5. Concatenated link: model a rate-1/2 convolutional inner code that, on a noise event, emits a 150-bit burst, followed by a block interleaver (depth I) and a (255, 223) RS outer code. Find the minimum interleaver depth I such that no RS codeword sees more than t=16 symbol errors. Output I and the residual codeword error rate.
6. The CD CIRC uses C1 (32,28) followed by C2 (28,24). Compute the burst-correcting power of the pair *with* cross-interleaving and explain why two weak codes beat one strong code for the CD scratch model.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Symbol | "a byte in the codeword" | An m-bit element of GF(2^m); the atomic unit of RS encoding and error correction, not a bit |
| GF(2^8) | "some math field" | The 256-element finite field built from p(x)=x^8+x^4+x^3+x^2+1 (0x11D); add=XOR, multiply=poly mult mod p |
| Generator polynomial g(x) | "the thing you divide by" | (x-α^1)…(x-α^2t); its 2t roots define the code; a valid codeword is divisible by it |
| Syndrome | "error fingerprint" | r(α^i) for i=1..2t; zero iff uncorrupted; otherwise encodes error locations and magnitudes |
| Berlekamp-Massey | "the decoder" | Algorithm that turns 2t syndromes into the error-locator polynomial Λ(x) of degree ν |
| Chien search | "finding the errors" | Evaluating Λ(α^-i) for every position i to find which symbols are in error |
| Erasure | "known-bad symbol" | A symbol whose location is known (e.g. flagged by demodulator); costs 1 syndrome not 2, so 2t erasures correctable |
| Interleaver | "shuffler" | Spreads adjacent symbols across many codewords so a burst hits many codewords with ≤t errors each |
| Code rate | "efficiency" | k/n; fraction of transmitted symbols that carry data; (255,223) ≈ 0.875 |
| Concatenated code | "two codes stacked" | Inner convolutional + outer RS; inner fixes isolated bits, outer fixes the bursts the inner emits |

## Further Reading

- ITU-T G.992.1 (G.992.2) — ADSL transceiver specification, Reed-Solomon outer code over interleaved frames.
- CCSDS 131.0-B-3 — *TM Synchronization and Channel Coding*; defines the (255, 223) RS + rate-1/2 convolutional concatenated standard for space links.
- ETSI EN 300 421 — DVB-S framing, channel coding and modulation; the (204, 188) shortened RS code and I=12 convolutional interleaver.
- ATSC A/53 Part 2 — Digital Television System; (207, 187) RS code plus trellis-coded modulation.
- IEC 60908 — Compact Disc digital audio system; the CIRC specification (C1 (32,28), C2 (28,24)).
- Wicker, S. & Bhargava, V. (1994). *Reed-Solomon Codes and Their Applications*. IEEE Press.
- MacWilliams, F. & Sloane, N. (1977). *The Theory of Error-Correcting Codes*. North-Holland. Chapters 10–11 on BCH and Reed-Solomon codes.
- Lin, S. & Costello, D. (2004). *Error Control Coding*, 2nd ed. Pearson. Chapter 7 on Reed-Solomon codes and Berlekamp-Massey decoding.
