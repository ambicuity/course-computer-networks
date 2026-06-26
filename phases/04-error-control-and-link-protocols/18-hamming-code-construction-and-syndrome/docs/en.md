# Building an (11,7) Hamming code with syndrome decoding

> An **(11,7) Hamming code** is the smallest textbook example of a single-error-correcting linear block code: 7 message bits plus 4 check bits, with check bits sitting at positions that are powers of two (1, 2, 4, 8). Each check bit enforces **even parity** over a distinct subset of positions — position `k` is covered by the check bits whose powers-of-two sum to `k`, so bit 11 = 1 + 2 + 8 is checked by `p1`, `p2`, and `p8`. On reception the receiver recomputes every parity check *including the received check bits*; the resulting 4-bit vector is the **syndrome**, and because of the careful numbering the syndrome's binary value *is* the 1-based index of the flipped bit. A syndrome of `0101` = 5 means "flip bit 5." A syndrome of `0000` means the codeword is valid. The construction meets Hamming's 1950 bound `(m + r + 1) ≤ 2r` with equality (7 + 4 + 1 = 12 ≤ 16), giving a code with **Hamming distance 3**: it corrects any single-bit error, or detects any double-bit error, but cannot do both simultaneously. Real deployments of this family are **ECC DRAM** (SEC-DED variants with an extra overall parity bit) and the control channels of early wireless systems; modern links prefer convolutional, Reed-Solomon, and LDPC codes (802.11, 802.16, DVB-S2), but the syndrome idea — *a linear function of the received word that points straight at the error pattern* — is the conceptual backbone of all of them. This lesson builds a complete encoder, a noisy channel, and a syndrome decoder in `code/main.py` and traces the Fig. 3-6 example of an ASCII `'A'` corrupted in bit 5.

**Type:** Build
**Languages:** Python
**Prerequisites:** Binary arithmetic and XOR, the notion of a frame/codeword from the Phase 4 lesson on error-detecting codes (CRC, parity), Hamming distance
**Time:** ~75 minutes

## Learning Objectives

- Encode a 7-bit message into an 11-bit Hamming codeword by placing check bits at power-of-two positions and computing even parity over the correct coverage sets.
- Decode a received word by recomputing the four parity checks into a syndrome, and map a non-zero syndrome to the exact bit position to flip.
- State Hamming's bound `(m + r + 1) ≤ 2r` and show why (11,7) is the tightest single-error-correcting code for 7 data bits.
- Explain the difference between *detect* and *correct* in terms of Hamming distance: distance 3 corrects 1 error or detects 2, never both on the same received word.
- Distinguish the (11,7) Hamming code from SEC-DED ECC memory and from the convolutional/LDPC codes used in 802.11, and justify why links abandon Hamming codes as bit rates climb.
- Read the printed output of `code/main.py` and verify, by hand, that the syndrome points at the injected error and that the decoded message matches the original.

## The Problem

A satellite uplink hands you 7-bit ASCII characters one at a time over a noisy radio channel. The raw bit-error rate is around 10⁻⁴ — roughly one flipped bit per ten thousand — so a naive "send the 7 bits, hope they arrive" scheme corrupts a character every few seconds. Retransmission (ARQ) is expensive here: the round-trip time to the satellite is a quarter of a second, and the uplink bandwidth is the bottleneck. You want to *correct* the common case — a single flipped bit — at the receiver without asking for a resend, while still flagging the rarer two-bit corruption so it can be retransmitted.

You have 7 data bits. You are allowed to add redundant bits, but every extra bit costs uplink airtime, so you want the minimum redundancy that still fixes any single-bit error. The question is: how many check bits, where do they go, and how does the receiver find the bad bit without comparing against a table of all 2⁷ legal codewords?

## The Concept

### Codewords, code rate, and the (n,m) notation

A **block code** takes `m` message bits and emits `n = m + r` bits, where `r` is the number of redundant **check bits**. The full `n`-bit unit is a **codeword**. The **code rate** is `m/n` — the fraction of each transmitted bit that carries new information. For (11,7) the rate is 7/11 ≈ 0.636, so roughly 36% of every codeword is redundancy. A 1/2-rate code spends half its bandwidth on redundancy and is typical for a noisy channel; a high-quality fiber link might run close to 1.0 with only a CRC trailer.

The (11,7) code is **linear** (check bits are XOR sums of message bits), **systematic** (the 7 message bits are transmitted verbatim, not encoded into something else), and a **block** code (each codeword is independent, with no memory of previous ones — unlike the convolutional code in Fig. 3-7).

### Hamming distance and what it buys you

The **Hamming distance** between two codewords is the number of positions at which they differ — equivalently, the number of 1s in their XOR. The **distance of a code** is the minimum Hamming distance between any two of its legal codewords. Distance governs everything:

| Code distance d | Detect up to | Correct up to |
|---|---|---|
| 1 | 0 | 0 (no redundancy) |
| 2 | 1 | 0 |
| 3 | 2 | **1** |
| 4 | 3 | 1 (or 2 with clever decoding) |
| 2t + 1 | 2t | t |

The rule is mechanical: to *correct* `t` errors you need distance `2t + 1`, so that even after `t` flips the received word is still closer to the original than to any other codeword. To *detect* `d` errors you only need distance `d + 1`. A distance-3 code like (11,7) Hamming corrects 1 error **or** detects 2 — but not both at once, because a 2-bit error looks exactly like a 1-bit error on a *different* nearby codeword. You must pick a mode. ECC DRAM resolves this by adding one extra **overall parity bit**, turning the code into distance 4 (**SEC-DED**: Single-Error-Correct, Double-Error-Detect): a single flip is corrected, a double flip is detected as uncorrectable.

### Hamming's bound: why 4 check bits are exactly enough

To correct any single-bit error, every one of the `2m` legal messages must own a private "sphere" of `n + 1` words: itself plus the `n` words at distance 1 (one per flipped position). These spheres must not overlap, so the total `(n + 1) · 2m` words must fit inside the `2n` possible bit patterns:

```
(n + 1) · 2m  ≤  2n
m + r + 1     ≤  2r          (dividing by 2m, using n = m + r)
```

For `m = 7`: `7 + r + 1 ≤ 2r`  →  `r + 8 ≤ 2r`  →  `r ≥ 4`. Three check bits give `2³ = 8`, which is less than `7+3+1 = 11` — not enough. Four check bits give `2⁴ = 16 ≥ 12` — enough, with room to spare (the code is not *perfect* for `m=7` only in the loose sense; the classic perfect Hamming codes are `(2r − 1, 2r − 1 − r)`, i.e. (7,4), (15,11), (31,26); (11,7) is the textbook's truncated worked example). The point of the bound is that you cannot do better than 4 check bits for 7 data bits with single-error correction.

### Position numbering: why check bits sit at powers of two

This is the heart of Hamming's trick. Number the codeword positions **1 through 11, left to right**. Positions that are powers of two — 1, 2, 4, 8 — hold check bits `p1, p2, p4, p8`. The remaining positions — 3, 5, 6, 7, 9, 10, 11 — hold the seven message bits `m1…m7` in order.

```
Position:  1   2   3   4   5   6   7   8   9  10  11
Content:  p1  p2  m1  p4  m2  m3  m4  p8  m5  m6  m7
```

Why powers of two? Because every integer `k` decomposes uniquely into a sum of distinct powers of two (its binary representation). Position `k` is *covered by* exactly the check bits whose power-of-two terms appear in that decomposition:

| Position k | Binary | Covered by check bits |
|---|---|---|
| 3 | 0011 | p1, p2 |
| 5 | 0101 | p1, p4 |
| 6 | 0110 | p2, p4 |
| 7 | 0111 | p1, p2, p4 |
| 9 | 1001 | p1, p8 |
| 10 | 1010 | p2, p8 |
| 11 | 1011 | p1, p2, p8 |

Each check bit `pX` is then set to the XOR of all the *data* positions it covers, forcing even parity over its coverage set (including itself):

```
p1 = m1 ⊕ m2 ⊕ m4 ⊕ m5 ⊕ m7      (covers positions 3,5,7,9,11)
p2 = m1 ⊕ m3 ⊕ m4 ⊕ m6 ⊕ m7      (covers positions 3,6,7,10,11)
p4 = m2 ⊕ m3 ⊕ m4                 (covers positions 5,6,7)
p8 = m5 ⊕ m6 ⊕ m7                 (covers positions 9,10,11)
```

### The syndrome: the error position, spelled in binary

On reception the receiver recomputes each parity check **over the entire received word, check bits included**. Each check yields a 0 (parity holds) or a 1 (parity violated). Stack the four results as a binary number with `p8`'s result as the most significant bit and `p1`'s as the least:

```
syndrome = (check8 << 3) | (check4 << 2) | (check2 << 1) | check1
```

Three cases:

- **`0000`** — all parities hold. Accept the codeword (or, with an extra overall parity bit, declare it clean).
- **Non-zero, value ≤ 11** — the binary value *is* the 1-based index of the single flipped bit. Flip it and you have the original codeword.
- **Non-zero, value > 11** — an uncorrectable multi-bit error. In a plain (11,7) code this is misdecoded as a single-bit error at a nonexistent position, which is exactly the failure mode a SEC-DED overall parity bit catches.

The reason the scheme works is that each bit position `k` is covered by precisely the check bits corresponding to the 1-bits of `k`'s binary representation. Flipping position `k` flips exactly those check results, so the recomputed syndrome reads out `k` directly. This is why the numbering is so fussy — it makes decoding a *lookup-free* operation.

### Worked example: ASCII 'A' with an error in bit 5

ASCII `'A'` is `1000001` (7 bits). Laying it into the data positions `m1…m7` at positions 3,5,6,7,9,10,11:

```
Pos:   1  2  3  4  5  6  7  8  9 10 11
Data:     ?  1  ?  0  0  0  ?  0  0  1
```

Compute the check bits (even parity):

```
p1 = m1⊕m2⊕m4⊕m5⊕m7 = 1⊕0⊕0⊕0⊕1 = 0
p2 = m1⊕m3⊕m4⊕m6⊕m7 = 1⊕0⊕0⊕0⊕1 = 0
p4 = m2⊕m3⊕m4        = 0⊕0⊕0      = 0
p8 = m5⊕m6⊕m7        = 0⊕0⊕1      = 1
```

Transmitted codeword: `0 0 1 0 0 0 0 1 0 0 1`. Now inject a single error in **position 5** (flip the `0` to `1`). Received word: `0 0 1 0 1 0 0 1 0 0 1`. Recompute the checks over the whole received word:

```
check1 = bits at 1,3,5,7,9,11 = 0⊕1⊕1⊕0⊕0⊕1 = 1
check2 = bits at 2,3,6,7,10,11 = 0⊕1⊕0⊕0⊕0⊕1 = 0
check4 = bits at 4,5,6,7       = 0⊕1⊕0⊕0      = 1
check8 = bits at 8,9,10,11     = 1⊕0⊕0⊕1      = 0
```

Syndrome = `check8 check4 check2 check1` = `0101` = 5. Flip position 5, recover `0 0 1 0 0 0 0 1 0 0 1`, extract the data bits → `1000001` → `'A'`. This is exactly the Fig. 3-6 trace, and `code/main.py` reproduces it. See `assets/hamming-code-construction-and-syndrome.svg` for the encoder layout and the syndrome-decoding flow.

### Where Hamming codes actually live

Pure (11,7) Hamming codes are a teaching device, but the family is everywhere in disguise:

- **ECC DRAM** uses a (n,8) Hamming-style code *plus an overall parity bit* (SEC-DED). A 64-bit data word typically uses 8 check bits (a (72,64) code), correcting any single-bit error and flagging any double-bit error — the dominant real-world deployment of single-error correction.
- **Early modem and wireless control channels** used short Hamming codes where decoder simplicity mattered more than rate.
- **802.11a/g/n/ac/ax** data frames use binary **convolutional codes** (the NASA `r=1/2, k=7` code of Fig. 3-7, decoded by the Viterbi algorithm) and, since 802.11n, **LDPC** for high-throughput MCS. **Reed-Solomon** codes (e.g. (255,233)) handle burst errors on DSL, cable, satellite, and optical discs.
- The **syndrome** concept itself — a linear projection of the received word onto a space whose non-zero coordinates identify the error — generalizes to all of these. Viterbi, Berlekamp-Massey, and belief-propagation decoders are all, at heart, smarter ways to turn a syndrome-like residual into a most-likely error pattern.

## Build It

Open `code/main.py` and work through it in this order:

1. **`coverage(positions)`** — for each check-bit power of two, return the list of positions it covers. Verify against the table above.
2. **`encode(message: list[int]) -> list[int]`** — place the 7 message bits at the non-power-of-two positions, then compute each `pX` as the XOR of its data coverage set. Returns an 11-bit codeword.
3. **`syndrome(received: list[int]) -> int`** — recompute the four parity checks over the *entire* received word and pack them into a 4-bit integer (MSB = `p8`'s check).
4. **`decode(received: list[int]) -> tuple[list[int], int]`** — compute the syndrome; if zero, extract data; if non-zero and ≤ 11, flip that position then extract; otherwise report uncorrectable.
5. **`inject_error(codeword, position)`** and **`main()`** — encode `'A'`, inject the bit-5 error from the worked example, decode, and print the syndrome, the corrected codeword, and the recovered character. Then run a Monte-Carlo loop over all 11 single-bit error positions to confirm every one decodes back to `'A'`.

Run it with `python3 code/main.py`. The output should show syndrome `5` for the bit-5 case and a clean recovery for all single-bit injections.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Encode an arbitrary 7-bit message | `encode([1,0,1,1,0,0,1])` returns an 11-bit list with powers-of-two positions holding the parity values | The four check positions change predictably when any data bit flips |
| Inject and correct a single error | `inject_error` then `decode` returns the original message and the corrected position index | Syndrome equals the injected position for every position 1–11 |
| Hit the uncorrectable case | Inject *two* errors; observe the syndrome is non-zero and points at a third, wrong position | You can explain *why* a double error is misdecoded (distance 3) |
| Read the bound | Compute `(m+r+1) ≤ 2r` for m=7, r=3 and r=4 | You can show r=3 fails (11 ≤ 8 is false) and r=4 passes (12 ≤ 16) |
| Map to real systems | Name where SEC-DED ECC memory and 802.11's convolutional/LDPC codes sit relative to this lesson | You distinguish "single-error-correcting block code" from "soft-decision convolutional decoding" |

## Ship It

Produce the artifact described in `outputs/prompt-hamming-code-construction-and-syndrome.md`: a short trace showing (1) the encoded codeword for a chosen 7-bit message, (2) a single-bit error injected at a position of your choice, (3) the syndrome the receiver computes, (4) the corrected codeword, and (5) the recovered message. Include the Monte-Carlo table confirming all 11 single-bit errors decode correctly. The deliverable is the printed `main.py` output annotated with which line corresponds to which step of the encode → corrupt → syndrome → correct pipeline.

## Exercises

1. **Two errors, two stories.** Encode `'A'` and inject errors at positions 3 and 5 simultaneously. What syndrome does the receiver compute, and which (wrong) position does it "correct"? Explain in terms of Hamming distance why a distance-3 code cannot distinguish this from a single error at the syndromed position.
2. **Tighten to a perfect code.** The (15,11) Hamming code is *perfect*: `(11+4+1)=16=2⁴`. Extend `encode`/`decode` to (15,11) and confirm that every one of the 15 single-bit errors decodes correctly. What is the code rate, and how does it compare to (11,7)?
3. **Add SEC-DED.** Append a 12th bit that is the overall even parity of the 11-bit codeword (making a distance-4 code). Modify `decode` so that a single-bit error is corrected but a double-bit error is *detected and flagged uncorrectable* rather than misdecoded. Demonstrate on a double error of your choice.
4. **Burst errors.** Hamming codes correct scattered single-bit errors but a burst of 3 consecutive flips is a 3-bit error — uncorrectable. Confirm experimentally: inject a 3-bit burst starting at position 4 and show the decoder either miscorrects or reports failure. Contrast with how a (255,233) Reed-Solomon code treats an 8-bit burst as a single *symbol* error.
5. **Code-rate trade-off.** For a channel with BER 10⁻⁵, estimate the probability that an 11-bit codeword arrives with ≥ 2 errors (and is thus uncorrectable). Repeat for a hypothetical (7,4) code over the same 7-bit payload. Which gives lower residual error, and at what bandwidth cost?
6. **From hard to soft.** The lesson's decoder is *hard-decision*: each received bit is already 0 or 1. Describe how a convolutional decoder (Viterbi) instead consumes soft decisions like "0.9 V = likely 1" and explain in one paragraph why this typically gains ~2 dB of effective SNR on a noisy link.

## Key Terms

| Term | What people say | What it actually means |
|------|----------------|----------------------|
| Codeword | "The encoded frame" | One of the `2m` legal `n`-bit patterns the encoder is allowed to emit; everything else is an error pattern |
| Check bit (parity bit) | "The extra bits" | A bit at a power-of-two position set to the XOR of a defined coverage set so that coverage set has even parity |
| Syndrome | "The error fingerprint" | The 4-bit vector of recomputed parity checks; for a single error its numeric value *is* the 1-based index of the flipped bit |
| Hamming distance | "How far apart two words are" | The count of differing bit positions between two codewords; the code's minimum distance sets its correct/detect capability |
| Code rate | "Efficiency" | `m/n`, the fraction of each transmitted bit that is new information rather than redundancy; (11,7) ≈ 0.64 |
| Systematic code | "Data sent as-is" | The `m` message bits appear unmodified in the codeword, alongside the check bits — not encoded into a different form |
| SEC-DED | "ECC memory's mode" | Single-Error-Correct, Double-Error-Detect: a distance-4 code (Hamming + overall parity) that corrects 1 flip and flags 2 as uncorrectable |
| Perfect code | "Wastes no space" | A code whose error spheres exactly tile the space of all bit patterns, so `(n+1)·2m = 2n`; (7,4) and (15,11) Hamming codes are perfect, (11,7) is the textbook's worked truncation |

## Further Reading

- **Tanenbaum & Wetherall, *Computer Networks*, 6th ed., §3.2.1 "Error-Correcting Codes"** — the source of the (11,7) worked example and Fig. 3-6 used throughout this lesson.
- **R. W. Hamming, "Error Detecting and Error Correcting Codes," *Bell System Technical Journal* 29(2), 1950** — the original construction and the bound that bears his name.
- **S. Lin and D. J. Costello, *Error Control Coding*, 2nd ed., Prentice Hall, 2004** — the standard reference for block, convolutional, and Reed-Solomon codes.
- **IEEE 802.11-2020, §19 (OFDM PHY)** — the convolutional (`k=7, r=1/2`) and LDPC codes used in modern Wi-Fi, the practical successor to single-error-correcting block codes.
- **JEDEC Standard JESD79-5 (DDR5 SDRAM)** — SEC-DED ECC memory operation, the largest deployed instance of Hamming-style single-error correction in the wild.
