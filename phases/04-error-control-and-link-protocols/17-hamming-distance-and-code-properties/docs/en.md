# Hamming distance and the error-detection/correction tradeoff

> Every error-control code is a geometry problem. The **Hamming distance** between two codewords is the count of bit positions in which they differ, and the **minimum Hamming distance** of a whole codebook — call it *d_min* — is the single number that governs what the code can do. A code with *d_min = 3* (the classic **(11,7) Hamming code**, used in ECC memory and described in Tanenbaum's Fig. 3-6) can **detect up to 2** bit errors **or** **correct 1** — never both at once, because the same received word can be interpreted only one way. The rule is exact: to detect *d* errors you need *d_min ≥ d + 1*; to correct *d* errors you need *d_min ≥ 2d + 1*. The Hamming code places parity bits at power-of-two positions (1, 2, 4, 8, …) so the **syndrome** — the set of failed parity checks read as a binary number — directly names the bad bit position for single-bit errors. Real links mostly do not correct at the frame level: Ethernet, IP, and TCP rely on a 32-bit **CRC** (polynomial remainder, detection only) and a retransmission (ARQ) loop, while correction is reserved for physical media where retransmission is impossible — ECC DRAM (Hamming/SECDED), CDs/DVDs/Blu-ray (**Reed-Solomon**, e.g. RS(255,233) correcting 16 byte-symbols = 128-bit bursts), 802.11 and satellite links (the **NASA r=1/2, k=7 convolutional code** from Voyager 1977, decoded by the **Viterbi algorithm**), and modern 802.11n/ac/ax and 5G (**LDPC** and turbo codes). This lesson builds a runnable (11,7) Hamming encoder/syndrome decoder, computes code distances, and shows exactly why a two-bit error makes a distance-3 code miscorrect.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Binary representation and XOR, parity, the data-link layer framing model (Phase 4 framing lesson)
**Time:** ~75 minutes

## Learning Objectives

- Define Hamming distance operationally, compute it for two codewords, and compute the minimum distance *d_min* of a codebook.
- State and apply the detect/correct rules: detect *d* errors needs *d_min ≥ d + 1*; correct *d* errors needs *d_min ≥ 2d + 1*; explain why both cannot be maxed simultaneously.
- Place parity bits at power-of-two positions in an (11,7) Hamming code and compute which parity bits cover each data position from the binary decomposition of its index.
- Decode a received word by computing the syndrome, interpreting it as the error position, and flipping the offending bit; explain why a two-bit error produces a nonzero syndrome that points at a *third* position (miscorrection).
- Derive the Hamming bound *(m + r + 1) ≤ 2^r* and use it to find the minimum number of check bits *r* for a given message length *m*.
- Distinguish when a link should use forward error correction (FEC) versus detection + ARQ retransmission, naming where each appears in real stacks.

## The Problem

A satellite downlink sends a 7-bit telemetry sample per frame across a channel that flips roughly one bit per million. The one-way light-time to the spacecraft is 40 minutes, so a request to retransmit a corrupted frame takes at least 80 minutes round trip — by then the spacecraft has moved on and the sample is stale. The frame must be corrected *in place* at the receiver, with no second chance.

Meanwhile, an Ethernet link on a quiet datacenter switch sees a corrupted packet perhaps once a week. The right answer there is the opposite: detect the corruption cheaply with a 32-bit CRC frame check sequence and drop the frame; TCP will notice the gap and retransmit within milliseconds. No redundancy is wasted correcting errors that almost never happen.

The engineer's question is the same in both cases: given a channel's error statistics and the cost of a retransmission, *how much redundancy do I add, and should it correct or merely detect?* The answer is dictated entirely by the code's minimum Hamming distance. This lesson makes that tradeoff concrete and runnable.

## The Concept

### Codewords, redundancy, and code rate

A **block code** turns each *m*-bit message into an *n*-bit **codeword** where *n = m + r* and *r* is the number of redundant **check bits**. The code is described as an **(n, m)** code. Only *2^m* of the *2^n* possible *n*-bit patterns are legal codewords — a fraction *1/2^r* — and that sparseness is what makes error detection possible: most random corruptions land on an illegal pattern. The **code rate** is *m/n*, the fraction of each transmitted bit that carries information. A rate of 1/2 (half the bits are redundant) suits a noisy channel; rates near 1 suit a clean one. The codes used in practice are **linear** (check bits are XOR functions of the data bits, so encoding is matrix multiplication) and **systematic** (the *m* data bits appear unmodified in the codeword, with the *r* check bits appended or interleaved).

### Hamming distance and the minimum distance of a code

The **Hamming distance** between two codewords is the number of positions at which they differ — equivalently, the popcount of their XOR. The codewords `10001001` and `10110001` differ in 3 bits, so their distance is 3. If two legal codewords are distance *d* apart, it takes exactly *d* single-bit flips to turn one into the other.

The **minimum distance** *d_min* of a code is the smallest Hamming distance between any two of its legal codewords. It is the code's defining property: *d_min* alone determines how many errors the code can detect and how many it can correct. The four-codeword textbook example — `0000000000`, `0000011111`, `1111100000`, `1111111111` — has *d_min = 5*. `code/main.py` computes exactly this in `code_min_distance()`.

### The detect/correct tradeoff, stated exactly

| Property | Required *d_min* | Why |
|---|---|---|
| Detect up to *d* errors | *d_min ≥ d + 1* | *d* errors cannot reach another legal codeword, so the result is illegal |
| Correct up to *d* errors | *d_min ≥ 2d + 1* | Even after *d* flips the original is still the closest legal codeword |

A code with *d_min = 5* therefore detects up to 4 errors *or* corrects up to 2. It cannot do both at once: a received word 2 flips away from codeword X and 3 flips away from codeword Y could be either "2 errors from X (correctable)" or "3 errors from Y (detectable, not correctable)." You must pick one interpretation policy. Decoding by nearest legal codeword (maximum-likelihood, hard-decision) is optimal when more errors are less likely.

### The (11,7) Hamming code: parity bits at powers of two

Hamming's 1950 construction achieves the theoretical minimum number of check bits for single-error correction. The 11 bit positions are numbered 1 through 11. Positions that are **powers of two** (1, 2, 4, 8) are **parity bits**; the remaining positions (3, 5, 6, 7, 9, 10, 11) carry the 7 data bits. Each parity bit enforces even parity over a specific subset of positions: a data bit at position *k* is checked by exactly those parity bits *p* for which the corresponding bit of *k* is set — that is, by the powers of two in *k*'s binary decomposition.

| Position | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Role | p1 | p2 | d | p4 | d | d | d | p8 | d | d | d |
| Covers (parity bits) | 1 | 2 | 1,2 | 4 | 1,4 | 2,4 | 1,2,4 | 8 | 1,8 | 2,8 | 1,2,8 |

For example, position 11 = 1 + 2 + 8, so data bit 11 is checked by p1, p2, and p8. Position 6 = 2 + 4, checked by p2 and p4. This numbering is the whole trick: it makes the parity-check structure align with binary place values. The codeword for ASCII 'A' (7-bit `1000001`) is `00100001001`, with parity bits [p1, p2, p4, p8] = [0, 0, 0, 1]. The layout is drawn in `assets/hamming-distance-and-code-properties.svg`.

### Syndromes: the parity results name the bad bit

When a word arrives, the receiver recomputes each parity check *including* the received parity bit. For even parity, a check that passes yields 0; one that fails yields 1. Concatenating the four check results — conventionally ordered (p8, p4, p2, p1) — gives a 4-bit value called the **syndrome**:

- **Syndrome = 0**: all parity checks pass; accept the word (no detectable error).
- **Syndrome ≠ 0**: the syndrome, read as a binary number, *is the 1-indexed position of the flipped bit.* Flip that bit and the data is recovered.

In Fig. 3-6 a single-bit error hits position 5; the checks for (p8, p4, p2, p1) read (0, 1, 0, 1), giving syndrome `0101` = 5. The decoder flips bit 5 and recovers 'A'. `code/main.py` reproduces this end to end in `hamming_encode()` / `hamming_syndrome()` / `hamming_decode()`, including the case where the flipped bit is itself a parity bit (syndrome points at the parity position; data is already correct). Because each single-bit error produces a *distinct* nonzero syndrome, the (11,7) code corrects every single-bit error — which is exactly the *d_min ≥ 2·1 + 1 = 3* guarantee.

### Why two errors defeat a distance-3 code

Now flip two bits, say positions 3 and 7. The syndrome is the XOR of the syndromes the two errors would have produced individually: syndrome(3) ⊕ syndrome(7) = `0011` ⊕ `0111` = `0100` = 4. The decoder dutifully flips position 4 — a *third* bit that was never wrong — and now three bits are corrupted, two of them in the data. The data decodes to garbage and no alarm is raised, because the post-"correction" word passes all parity checks. **This is miscorrection**, the defining failure mode of single-error-correcting codes hit by multi-bit errors. It is why the (11,7) code is described as "correct 1 *or* detect 2," never both. The extended **(12,8) SECDED** code adds one more overall-parity bit: a single error gives a nonzero syndrome and even overall parity flips, while a double error gives a nonzero syndrome with overall parity unchanged — letting the decoder *detect* doubles instead of silently miscorrecting. SECDED is what ECC DRAM actually ships.

### The Hamming bound: how few check bits suffice

To correct all single-bit errors, each of the *2^m* legal messages must "own" its own codeword plus the *n* codewords at distance 1 from it (one per bit flip) — *n + 1* patterns per message. Since only *2^n* patterns exist, we need *(n + 1)·2^m ≤ 2^n*. Substituting *n = m + r* and dividing by *2^m* gives the **Hamming bound**:

> **(m + r + 1) ≤ 2^r**

This is the lower bound on *r* for single-error correction. For *m = 7* data bits, *r = 4* check bits is the minimum (since *7 + 4 + 1 = 12 ≤ 16 = 2^4*), yielding the (11,7) code — and Hamming codes are the rare codes that meet the bound with equality. `code/main.py`'s `demo_min_check_bits()` tabulates *r* and the code rate for *m* from 1 to 64: as messages grow, the check-bit overhead falls (rate climbs toward 1), which is why long codewords are more efficient but correct a smaller fraction of corruption.

### Detection-only codes: CRC, and why links usually do not correct

Most link, network, and transport layers choose **detection + retransmission (ARQ)** over correction. A **cyclic redundancy check (CRC)** treats the message as a polynomial over GF(2), divides by an agreed generator polynomial, and appends the remainder as the **Frame Check Sequence (FCS)**. Ethernet uses **CRC-32** (polynomial `0x04C11DB7`, IEEE 802.3); it detects all single- and double-bit errors, all burst errors of length ≤ 32, and a fraction 1 − 2^−32 of longer bursts. CRCs detect far more error patterns per redundant bit than a Hamming code corrects, because they do not spend redundancy on locating the error — they only need to flag it as illegal. The receiver drops the frame; TCP (or a link-layer ARQ like HDLC, PPP, or 802.11 block ACKs) retransmits. Correction is reserved for channels where retransmission is impossible or too expensive: **ECC DRAM** (Hamming/SECDED, one bit per 64-bit word), **CD/DVD/Blu-ray** (Reed-Solomon over 8-bit symbols — RS(255,233) adds 32 check symbols and corrects 16 symbol errors, i.e. a contiguous 128-bit burst, because a byte-symbol error is one error regardless of how many bits inside flipped), **802.11a/g** and satellite links (the **NASA r=1/2, k=7 convolutional code**, Viterbi-decoded), and **802.11n/ac/ax** plus **5G data channels** (**LDPC**, rediscovered from Gallagher's 1962 thesis, decoded iteratively). Reed-Solomon plus convolutional coding — a **concatenated code** — is the classic design: the convolutional code mops up isolated bit errors and RS cleans up the bursts the convolutional decoder emits when it fails.

## Build It

1. Read `code/main.py`. `hamming_distance()` and `code_min_distance()` implement the geometry; `detect_correct()` encodes the *d + 1* / *2d + 1* rules.
2. Run `python3 code/main.py`. Confirm the four-codeword example reports *d_min = 5*, detect 4, correct 2.
3. In the (11,7) section, confirm encoding ASCII 'A' = `1000001` yields codeword `00100001001` with parity bits `[0, 0, 0, 1]` — matching the textbook Fig. 3-6 layout.
4. Inject a single-bit error at position 5 and verify the syndrome is `0101` = 5 and the decoder recovers 'A'. Try a parity-bit error (position 4) and confirm data still recovers.
5. Inject a *two-bit* error (positions 3 and 7) and observe the miscorrection: the syndrome points at position 4, the decoder flips a *third* bit, and `recovered: False`. This is the tradeoff made tangible.
6. Read the Hamming-bound table and confirm *m = 7 → r = 4* is the minimum that satisfies *(m + r + 1) ≤ 2^r*.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Compute a code's minimum distance | All pairwise XOR popcounts; the smallest is *d_min* | Matches the textbook value (e.g. 5 for the 4-word code, 3 for (11,7)) |
| Decide detect vs correct for a given *d_min* | `detect_correct()` output and the *d+1* / *2d+1* rules | You state which is achievable and that both cannot be maxed at once |
| Correct a single-bit error with the syndrome | Syndrome equals the flipped position; flip recovers data | Syndrome 5 → flip bit 5 → 'A' recovered, including when the parity bit itself is flipped |
| Show miscorrection on a double error | Nonzero syndrome pointing at a *third* position; `recovered: False` | You explain *why*: syndrome is XOR of the two single-error syndromes |
| Size check bits for a message length | Hamming bound satisfied with equality for *m = 7, r = 4* | You pick the smallest *r* meeting *(m + r + 1) ≤ 2^r* |
| Choose FEC vs CRC+ARQ | Channel error rate and retransmission cost named | Satellite/one-shot links → FEC; Ethernet/datacenter → CRC + retransmit |

## Ship It

Produce one artifact under `outputs/prompt-hamming-distance-and-code-properties.md`:

- An annotated run of `code/main.py` showing: the *d_min = 5* tradeoff, the (11,7) encode of 'A', a single-error correction, and the two-error miscorrection — each with a one-line explanation of the syndrome arithmetic.
- A short decision table: for channel profiles (BER 10^−3 satellite, BER 10^−6 wireless LAN, BER 10^−12 datacenter Ethernet) state code choice (FEC family vs CRC-32 + ARQ) and the *d_min* or polynomial that justifies it.
- The Hamming-bound row for *m = 64*, showing *r = 7* and code rate ≈ 0.901, with a note on why long codewords are more efficient.

## Exercises

1. Take the codebook `{0000000, 1110100, 1101011, 0011111}`. Compute all six pairwise Hamming distances and state *d_min*. How many errors can this code detect? How many can it correct? Which choice leaves the other on the table?
2. Encode the 7-bit ASCII for 'S' (`1010011`) with the (11,7) Hamming code. Write out the codeword with each position labeled p1/p2/d/p4/d/d/d/p8/d/d/d, and list which parity bits cover data position 11 (show the binary decomposition 11 = 1 + 2 + 8).
3. A received (11,7) word has syndrome `0110` = 6. Which bit is wrong — a data bit or a parity bit? After correction, which data bits changed relative to the uncorrected word? Now suppose the *true* error was two bits at positions 2 and 4. What syndrome does the decoder compute, and what does it wrongly "correct"?
4. You need single-error correction for *m = 32* data bits. Use the Hamming bound to find the minimum *r*, the total codeword length *n*, and the code rate. By how many bits does this fall short of the bound (is it met with equality)?
5. An 802.11 frame uses the NASA r=1/2, k=7 convolutional code, then an outer Reed-Solomon RS(255,233) code. Explain what each layer corrects and why they are concatenated: what failure mode of the inner code does the outer code clean up?
6. Ethernet's CRC-32 detects all bursts of length ≤ 32. A burst error of length 33 has probability 1 − 2^−32 of being detected. Compute the undetected-error probability per frame, and argue why detection + retransmission beats forward correction for a datacenter link with BER ≈ 10^−12.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Hamming distance | "how different two words are" | The count of bit positions in which two equal-length codewords differ; popcount of their XOR |
| Minimum distance (d_min) | "the code's strength" | The smallest Hamming distance between any two legal codewords; it alone sets detect/correct limits |
| Codeword | "an encoded message" | An *n*-bit pattern, of which only 2^m are legal in an (n, m) code; the rest signal corruption |
| Code rate | "efficiency" | *m/n*, the fraction of each transmitted bit that is user data rather than redundancy |
| Parity bit | "an extra check bit" | A bit forcing even (or odd) parity over a defined subset of positions; in Hamming codes it sits at a power-of-two position |
| Syndrome | "the error pointer" | The vector of failed parity checks; in a Hamming code, read as a binary number it *is* the 1-indexed position of the single bad bit |
| SECDED | "ECC memory" | Single-Error-Correction, Double-Error-Detection — an extended Hamming code with one overall-parity bit so doubles are flagged instead of miscorrected |
| CRC / FCS | "the checksum at the end of the frame" | Polynomial remainder over GF(2) appended as the Frame Check Sequence; detects bursts cheaply but locates nothing — the frame is dropped and retransmitted |
| Reed-Solomon | "the CD/DVD code" | A linear block code over *m*-bit symbols; RS(255,233) corrects 16 symbol errors, turning a 128-bit burst into 16 single-symbol errors |
| Convolutional code | "the 802.11 code" | A non-block code where each output depends on current and previous input bits (constraint length *k*); decoded by the Viterbi algorithm, often with soft decisions |
| Hamming bound | "the check-bit limit" | *(m + r + 1) ≤ 2^r* — the minimum check bits *r* to correct any single error in *m* data bits; Hamming codes meet it with equality |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 3, Section 3.2.1 (Error-Correcting Codes) — the (11,7) Hamming example and Fig. 3-6.
- R. W. Hamming, "Error Detecting and Error Correcting Codes," *Bell System Technical Journal* 29(2), 1950 — the original construction.
- IEEE 802.3-2018, Section 3.2.9 — the CRC-32 Frame Check Sequence and generator polynomial `0x04C11DB7`.
- IEEE 802.11-2020, Clause 19 (OFDM PHY) — the r=1/2, k=7 convolutional code and Viterbi decoding.
- IETF RFC 1662 — PPP in HDLC-like framing, including the 16-bit CRC-CCITT FCS for point-to-point links.
- I. S. Reed & X. Chen, *Error-Control Coding for Data Networks*, Kluwer, 1999 — Reed-Solomon RS(255,233) and concatenated code design.
- A. J. Viterbi, "Error Bounds for Convolutional Codes and an Asymptotically Optimum Decoding Algorithm," *IEEE Trans. IT* 13(2), 1967.
- R. G. Gallagher, *Low-Density Parity-Check Codes*, MIT Press, 1963 (PhD thesis) — LDPC, rediscovered for 802.11n and 5G.
- D. J. C. MacKay, *Information Theory, Inference, and Learning Algorithms*, Cambridge, 2003, Chapters 1, 7, 13, 47 — distance, Hamming codes, and modern iterative decoding.
