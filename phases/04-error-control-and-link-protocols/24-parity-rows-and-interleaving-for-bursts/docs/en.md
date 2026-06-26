# Row parity and interleaving to detect burst errors

> A single parity bit detects any odd number of bit flips in a block, which is fine for isolated errors on clean fiber but collapses on a noisy link where a **burst error** garbles a run of consecutive bits. The textbook (Sec. 3.2.2) re-arranges a block of `kn` data bits into a `k × n` matrix and computes one parity bit per **row** (`k` parity bits); if errors stay at most one per row, up to `k` flips are reliably detected. The stronger trick is **interleaving**: compute one parity bit per **column** (`n` parity bits) and transmit row-by-row. A burst of length `n` straddles `n` different columns — at most one error per column — so each column's parity catches it. This is the ubiquitous "spread the burst across codewords" idea reused by RAMM (Reed-Solomon outer code in CDs/DVDs/BAR + interleaving), by the 802.11 OFDM symbol interleaver, and by the ADSL DMT frame interleaver. The failure modes are exact: a burst of length `n + 1` passes undetected if only its first and last bits flip, and a badly garbled block escapes with probability `2^(−n)`. This lesson builds a runnable parity-row/column codec, injects controllable bursts, and shows you the parity-error matrix that proves detection.

**Type:** Build
**Languages:** Python
**Prerequisites:** Single-bit parity and Hamming distance (Phase 4 lessons on parity and Hamming codes); modular-2 / XOR arithmetic; the burst-error model from Tanenbaum & Wetherall Sec. 3.2.1
**Time:** ~75 minutes

## Learning Objectives

- Explain why a single parity bit fails on burst errors and quantify the residual escape probability (0.5 for one block, `2^(−n)` for an interleaved `n`-column block).
- Build a `k × n` parity-row codec, transmit rows left-to-right top-to-bottom, and detect up to `k` bit errors provided no row has more than one flip.
- Build the interleaved variant (column parity, row transmission) and prove it detects any single burst of length `≤ n`, but misses a length-`n+1` burst whose only flipped bits are the endpoints.
- Inject bursts of controlled length and pattern into a transmitted codeword and read the resulting row-parity-error and column-parity-error matrices.
- Contrast this parity scheme with the 16-bit Internet checksum (RFC 1071) and the 32-bit CRC (IEEE 802.3, generator `0x04C11DB7`) for burst coverage, overhead, and cost.
- Decide when interleaved parity is and is not adequate — and when you must step up to a CRC or an interleaved Reed-Solomon code.

## The Problem

A 1000-bit block traveling over a fiber link with bit error rate `10^(−6)` hits, on average, one flip per 1000 blocks; a single parity bit per block catches it, and one retransmission in 1001 bits of overhead per megabit is the whole cost. Now move that same block to a radio link dominated by **impulse noise**: lightning nearby, a microwave oven, a reed relay clicking once. Errors stop arriving one bit at a time and arrive in **bursts** — runs of 5, 7, 50 consecutive bits, all garbled together within a few hundred bit-times. A single parity bit across the whole block sees the *sum* of those flips; if the burst flips an even number of bits inside the block, parity returns to even and the error is invisibly accepted. That residual detection probability is `0.5` — unacceptable for any block that carries money, telemetry, or a disk sector.

The engineer's lever is geometry. Instead of laying the block out flat and XORing all of it, lay it out as a matrix and compute parity along one axis. If errors cluster in **time** (a burst) but you compute parity along the other axis, the burst is spread across many independent parity checks. This is the entire reason burst errors are "good news" in the textbook: a burst of 100 bits hits at most 100 *columns*, not one giant column.

## The Concept

### Single parity and why it dies on bursts

Even parity appends a bit so the total number of 1s in the codeword is even. Equivalently, the parity bit is the XOR (mod-2 sum) of data bits. `1011010` → `1011010 0` (even) or `1011010 1` (odd). A code with one parity bit has **Hamming distance 2**: any single-bit error produces an illegal codeword and is detected, but any two-bit error flips parity back to legal and is missed.

For bursts the math is brutal. A burst of length `L` flips a run of bits whose pattern starts and ends with a 1 and contains anything in between; half of all such patterns have even overall parity. So the detection probability for a fully garbled block is exactly `0.5`, independent of how cleverly we chose the parity. The block is far more reliable than `0.5` implies? Only if we stop computing one giant parity.

### The `k × n` matrix and row parity

Arrange the `kn` data bits as a matrix `k` rows high and `n` columns wide. Compute one parity bit per row, append it to the row. Send all `k` rows, each now `n + 1` bits wide. On receipt, recompute row parity row by row.

| Error pattern on the channel | What row parity reports |
|---|---|
| One isolated flip | The row containing it flags bad; detected |
| `k` flips, at most one per row | All `k` flagged rows light up; detected |
| `k` flips, two in the same row | That row's parity is even; **missed** |
| Burst of length `≤ n` lying across one row | That row flags bad; detected |
| Burst of length `≤ n` lying across two rows | Up to two rows affected — detected unless an even number happens to fall in one row |

Row parity buys you `k` independent tests. The textbook phrasing is "up to `k` bit errors will be reliably detected as long as there is at most one error per row." The cost is `k` parity bits per `kn` data bits — 1 bit of overhead per `n` data bits. For `n = 7, k = 7` that is 7 parity bits per 49 data bits, ~14% overhead.

### Interleaving: column parity, row transmission

A burst corrupts bits that are **adjacent in transmission**. So arrange the matrix so that bytes adjacent on the wire come from different parity groups. The textbook's Fig. 3-8 does exactly this with `n = 7, k = 7` characters of ASCII:

```
column  →   1 2 3 4 5 6 7     parity (XOR down each column)
row 1   N   1 0 0 1 1 1 0  →  0
row 2   e   1 1 0 0 1 0 1  →  0
row 3   t   1 1 1 0 1 0 0  →  0
row 4   w   1 1 1 0 1 1 1  →  1
row 5   o   1 1 0 1 1 1 1  →  1
row 6   r   1 1 1 0 0 1 0  →  1
row 7   k   1 1 0 1 0 1 1  →  0
parity bits sent last:   1 0 1 0 0 0 0
```

Parity is computed down each **column**, but bits are sent across each **row**. A burst of length 7 straddling `n = 7` columns hits at most one bit in each column. Each column's parity independently flags the error. The seven column parity checks together cannot be defeated by a burst that short, because a single flip per column is guaranteed to flip that column's parity.

The transmission order matters because that is what the channel sees as "adjacent." If you computed parity per column but transmitted column-by-column, a burst would land inside one column and parity would collapse exactly the way a single flat parity does — the geometry would be a lie.

### Detection guarantee, and the exact hole at length `n + 1`

Summary of the textbook's claim:

| Burst length `L` on interleaved column parity | Detection |
|---|---|
| `L ≤ n` | **Always detected** (at most one flip per column) |
| `L = n + 1` | Missed *if and only if* only the first and last bits flip and the interior is correct — one specific pattern out of `2^(n−1)` patterns |
| `L > n + 1`, or multiple short bursts | Each column has independent `` ``parity correct by accident'' probability `0.5`; the whole block escapes with probability `2^(−n)` |

So interleaved column parity uses `n` parity bits per `kn` data bits to detect any single burst of length `≤ n`, and degrades gracefully to `2^(−n)` residual probability for longer or multiple bursts. For `n = 16` the residual is `2^(−16) ≈ 1.5×10^(−5)`; for `n = 32` it is `2.3×10^(−10)`, in the same league as a CRC's undetected-error floor.

### A worked numeric example

Take the seven characters `N e t w o r k` (`n = 7`, `k = 7`). Compute even-parity down each column. The seven parity bits the receiver recomputes as `1 0 1 0 0 0 0` (see the table above; verify by hand or with `code/main.py`).

Now flip a burst of 7 bits spanning columns 1–7 — for instance, flip the second bit of row 1, second bit of row 2, first bit of row 3, fourth bit of row 5, fifth bit of row 6, third bit of row 7, and the third bit of row 4 (textbook Fig. 3-8's 4-flip illustration is a shorter version). Recompute column parity. Each of the touched columns now disagrees with the transmitted parity bit. All seven column-parity checks light up — the burst is detected. `code/main.py` produces exactly this parity-error matrix when you inject the burst.

Now lengthen the burst to 8 bits but flip *only* the first and last bit and leave the interior 6 bits pristine. Every column's parity matches. The block is accepted as clean. That is the `n + 1` hole — the one pathological pattern interleaved parity cannot reach.

### Where this idea shows up in real protocols

Interleaving is a recursive trick; once you have a code that detects (or corrects) *isolated* errors, interleaving reuses it for bursts:

| Protocol / standard | Code | Interleaving |
|---|---|---|
| **CD-ROM / DVD / Blu-ray** (ECMA-130, ECMA-267) | Outer **Reed-Solomon** (RS-PC), symbol size 8 bits | CIRC / row-column interleaving across the RS codeword so a long scratch becomes a few single-symbol errors per codeword |
| **IEEE 802.11a/g/n/ac** OFDM PHY | Convolutional code, `r = 1/2, K = 7` (generators `0o133, 0o171`) | Block interleaver across the 48 data subcarriers before Viterbi decoding; an impulsive fade hits one *subcarrier* — already interleaved across many code blocks |
| **ADSL / VDSL** (G.992.1) | Outer **Reed-Solomon** `RS(255, 239)` over GF(2⁸) | Convolutional interleaver spreads impulse noise across many RS codewords |
| **DVB-T / DVB-S** | Inner convolutional + outer RS `RS(204, 188)` | Outer convolutional interleaver, depth `I = 12` bytes |
| **Deep-space** (CCSDS, ESA) | Concatenated RS + convolutional or RS + LDPC | Block interleaver between inner and outer codes |

In every one of these the principle is identical: time-localized noise (scrape, fade, click) is spread across many independent "parity groups" so a code designed for isolated errors now fixes a burst. The textbook's column-parity scheme is the same idea, with parity playing the role the RS code plays in the concatenated scheme.

### Decision rule: parity rows, interleaved parity, or CRC?

| You have... | Choose |
|---|---|
| Clean fiber, BER `10^(−10)`, occasional 1-bit flip | One parity bit per block (1 bit overhead/1001 bits in the textbook example) |
| Copper/radio with bursts but bandwidth cheap, want detection only | Interleaved column parity, height/width chosen so `n` ≥ expected burst length |
| Detection of arbitrary length bursts with a hard floor | **CRC** — IEEE 802.3 32-bit CRC catches all bursts ≤ 32 and all odd-bit error bursts; residual for longer is `2^(−32)` |
| Correction of bursts, not just detection | Interleaved **Reed-Solomon** — corrects up to `(n − k)/2` symbol errors per codeword after interleaving |
| Both isolated and burst, low overhead | **CRC + interleaver** (the 802.11 PHY model) or concatenated RS |

`code/main.py` lets you sweep burst lengths against both row parity and interleaved column parity so you can *see* the cliff at `n + 1`.

## Build It

1. Read `code/main.py`. It encodes 7 ASCII characters into a `7 × 7` matrix, computes even parity two ways (per row, per column), and transmits row-by-row — exactly the textbook's Fig. 3-8 order.
2. Run it: `python3 code/main.py`. You will see the matrix, the parity bits for both schemes, the injected burst, and the parity-error matrix that proves detection.
3. Edit `inject_burst()` parameters in `main()` to inject a length-7 burst, then a length-8 burst that flips only the endpoints. Confirm the length-7 burst is detected and the length-8 pathological burst is missed.
4. Change `N_COLS` from 7 to 16 and 32 and rerun. Watch the missed-burst probability for long random bursts converge toward `2^(−16)` and `2^(−32)`.
5. Compare against the CRC helper in the file — the same injected burst is detected by the 32-bit CRC regardless of length, at the cost of 4 bytes of overhead.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm row-parity detection | Row-parity-error vector with one `1` per corrupted row | Exactly the corrupted rows light up; un-corrupted rows stay 0 |
| Confirm interleaved-parity detection | Column-parity-error vector with one `1` per touched column | A burst of length `≤ n` produces a contiguous run of `1`s across `n` columns |
| Reproduce the `n + 1` hole | A length-`n+1` burst with only endpoints flipped produces an all-zero parity-error vector | The pathological pattern is missed while any other pattern of the same length is caught |
| Sweep escape probability | Number of accepted-corrupted blocks / number of trials for long random bursts | Empirical rate ≈ `2^(−n)`; falls by half for every +1 column |
| Justify CRC instead | CRC remainder mismatch on the same burst that defeats interleaved parity | A 32-bit CRC catches bursts up to 32 regardless of pattern; parity only to `n` |
| Justify an interleaver in a layered code | Burst spread across N outer codewords, ≤ `t` symbol errors per codeword | Each outer codeword corrects in isolation; no single codeword overflows |

## Ship It

Produce one artifact under `outputs/`:

- A runbook that takes a chosen block, burst length, and burst pattern, prints the transmitted codeword (with parity bits), the received codeword, the parity-error matrix for both row and interleaved schemes, and the verdict (detected / missed).
- A one-page card on the `n + 1` hole and the `2^(−n)` residual, with the worked example annotated.
- A decision table mapping burst characteristics → parity row / interleaved parity / CRC / interleaved RS.

Start from the printed output of `code/main.py` and annotate it with the burst you injected and the failure mode (or success) you demonstrated.

## Exercises

1. For `n = 7, k = 7`, inject a burst of exactly length 7 that flips one bit in each of the 7 rows, all in column 4. Which scheme detects this — row parity, interleaved column parity, both, or neither? Justify from parity arithmetic.
2. Construct the unique length-8 burst that defeats interleaved column parity on the 7-column block. State the exact condition the textbook gives, and confirm `code/main.py` misses it. Now rotate the burst by one bit; what happens and why?
3. A link has BER `10^(−4)` and bursts average 50 bits. You can afford 8 parity bits per 1024-bit block. Choose `n` and `k` for interleaved parity and compute `2^(−n)`; argue whether it is good enough or whether you owe the link a CRC-16.
4. The 802.3 32-bit CRC with generator `0x04C11DB7` detects all bursts of length ≤ 32 and all bursts affecting an odd number of bits. Show that interleaved column parity with `n = 32` shares the *burst* guarantee but not the *odd-bit* guarantee, and explain why.
5. The CD uses CIRC with two Reed-Solomon codes `C1(32,28)` and `C2(28,24)` plus interleaving. Describe in one paragraph how a 3-mm scratch (a long burst) becomes a sequence of single-symbol errors that each `C1` and `C2` can correct, mapping the textbook's interleaving principle onto this real codec.
6. You are designing an 802.11-style OFDM PHY. The deep fade impulse lasts one OFDM symbol (4 μs) and flips 48 bits in one symbol's worth of subcarriers. Explain where the block interleaver between the convolutional encoder and the IFFT must sit, and why it converts the 48-bit burst into 48 single-bit errors scattered across many code frames.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Parity bit | "a check digit" | XOR of data bits appended to a block so total 1s is even (or odd); gives a distance-2 code |
| Burst error | "a glitch" | A run of ≥ 2 consecutive corrupted bits whose first and last bits are wrong; the interior can be anything |
| Row parity | "parity per row" | One parity bit computed across each row of a `k × n` matrix; up to `k` flips detected if ≤ 1 per row |
| Interleaving | "shuffling bits" | Computing parity along the axis *orthogonal* to transmission so a temporal burst spans many independent parity checks |
| Column parity (interleaved) | "parity stored vertically" | One parity bit per column, transmitted at the end after all `k` data rows; detects any burst of length `≤ n` |
| The `n + 1` hole | "off-by-one" | The single pathological pattern — first and last bits flipped, interior clean — that defeats interleaved column parity at exactly length `n + 1` |
| Residual probability `2^(−n)` | "leakage" | For bursts longer than `n + 1`, each column's parity is wrong by accident with probability `0.5`, so the block slips through with probability `2^(−n)` |
| CIRC | "the CD code" | Cross-Interleaved Reed-Solomon Code — two RS codes plus interleaving that turns a long scratch into isolated symbol errors |
| Concatenated code | "two codes stacked" | Inner + outer code (e.g. convolutional + RS) with an interleaver in between so inner bursts become single outer symbol errors |
| Internet checksum | "the IP checksum" | 16-bit ones-complement sum of words (RFC 1071), unrelated to parity but another parity-group-style integrity check driven by a running sum |

## Further Reading

- **Tanenbaum & Wetherall**, *Computer Networks*, 5th ed., Sec. 3.2.2 — Error-Detecting Codes; Fig. 3-8 (interleaving of parity bits to detect a burst error).
- **RFC 1071** — Computing the Internet Checksum (the 16-bit ones-complement sum complementary to parity).
- **IEEE Std 802.3-2022**, Clause 3 — the 32-bit Frame Check Sequence (CRC) with generator polynomial `x^32 + x^26 + x^23 + x^22 + x^16 + x^12 + x^11 + x^10 + x^8 + x^7 + x^4 + x^2 + x + 1` (`0x04C11DB7`), and the property that it detects all bursts ≤ 32 and all odd-bit bursts.
- **ECMA-130** — Volume and File Structure of CD-ROM; the CIRC interleaver between the C1 and C2 Reed-Solomon codes.
- **IEEE Std 802.11a-1999**, Sec. 17.3.5.5 — the convolutional block interleaver across OFDM subcarriers that turns a symbol-long fade into scattered bit errors.
- **ITU-T G.992.1 (ADSL)**, Sec. 7.4 — the outer Reed-Solomon `RS(255, 239)` code and convolutional interleaver for impulse-noise bursts.
- **Lin & Costello**, *Error Control Coding*, 2nd ed., Ch. 5–6 — interleaving as a general method to convert a code for random errors into a code for burst errors.
- **Ramabadran & Gaitonde**, "A Tutorial on CRC Computations," *IEEE Micro*, 1988 — the standard practitioner's reference for the CRC and its burst guarantees.