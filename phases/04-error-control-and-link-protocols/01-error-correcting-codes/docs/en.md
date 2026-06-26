# Error-Correcting Codes

> Error-correcting codes (FEC) add redundancy so the receiver can repair damaged bits without a retransmission — essential on noisy wireless and space links where a round-trip ARQ retry is too slow or impossible. A block code carries `m` data bits plus `r` check bits in an `n = m + r` codeword, described as an `(n, m)` code with rate `m/n`. The four codes in Tanenbaum 3.2.1 are the (11,7) Hamming code (distance 3, corrects one bit, used in ECC memory), the NASA rate-1/2 constraint-length-7 binary convolutional code (Voyager 1977, reused in 802.11, Viterbi-decoded), the Reed-Solomon (255,233) byte-symbol code (32 check bytes correct 16 symbol errors / a 128-bit burst, used on CD/DVD/Blu-ray, DSL, DVB), and LDPC codes (Gallager 1962, revived 1995, now in 10GBASE-T, DVB-S2, and 802.11n/ac/ax). A code with minimum Hamming distance `d` detects `d-1` errors and corrects `floor((d-1)/2)`. The Hamming decoder recomputes parity, reads the check results as a binary **syndrome**, and the syndrome value is exactly the position of the flipped bit.

**Type:** Build
**Languages:** Python, Wireshark
**Prerequisites:** Phase 03 (framing, the data link layer), binary/XOR arithmetic
**Time:** ~90 minutes

## Learning Objectives

- Compute the check bits of an (11,7) Hamming codeword and decode a single-bit error from its syndrome by hand and in code.
- Derive a code's error-detecting (`d-1`) and error-correcting (`floor((d-1)/2)`) power from its minimum Hamming distance, and apply the bound `(m + r + 1) ≤ 2^r`.
- Distinguish the four families — Hamming, convolutional, Reed-Solomon, LDPC — by structure (block vs. memory), symbol size, and the burst-vs-random error profile each is good at.
- Explain why Reed-Solomon (255,233) corrects bursts up to 128 bits and why concatenating it inside a convolutional code mops up the convolutional decoder's output bursts.
- Justify when forward error correction beats ARQ retransmission (long propagation delay, broadcast, no back-channel) and when it wastes bandwidth.

## The Problem

You are debugging an 802.11 link to a sensor on a factory floor. The application sees corrupted readings only when a forklift drives past the antenna. A capture shows frames arriving — the FCS is *valid* on most of them — yet a few payloads still look scrambled. Your colleague wants to "just add a checksum and retransmit." But this is a half-duplex radio with a tight latency budget, and the noise comes in short bursts, not isolated flips.

The right question is not "how do I detect the error" but "can the receiver *repair* it without asking for a resend?" That is forward error correction. To reason about it you need the vocabulary of codewords, code rate, and Hamming distance, and you need to know which code family matches your error profile: random single-bit flips (Hamming, convolutional) versus contiguous bursts (Reed-Solomon, LDPC). Picking the wrong one either wastes bandwidth on redundancy you don't need or fails to correct the errors you actually get.

## The Concept

### Codewords, rate, and redundancy

Every code here adds redundancy. A frame is `m` data bits plus `r` check bits; the total `n = m + r` is the **codeword**, and we call it an `(n, m)` code. In a **block code** the `r` check bits are a function only of the `m` data bits in that block. In a **systematic** code the data bits are sent verbatim and the check bits are appended (so you can read the message off the wire even before decoding). In a **linear** code the check bits are a linear — usually XOR / modulo-2 — function of the data bits, which is why encoding reduces to a matrix multiply or a few XOR gates. Unless noted, these are linear systematic block codes.

The **code rate** is `m/n`, the useful fraction. Rates vary widely: about `1/2` on a noisy channel (half the bits are redundant) up to nearly `1` on a clean fiber where only a few check bits guard a large message. With `r` check bits only `1/2^r` of the `2^n` possible bit patterns are legal codewords — that sparseness is what lets the receiver tell a corrupted codeword from a valid one.

### Hamming distance sets the power of a code

The **Hamming distance** between two codewords is the number of bit positions in which they differ (XOR them, count the 1s). The distance *of a code* is the minimum distance over every pair of legal codewords. Distance is the whole game:

| Goal | Required minimum distance | Why |
|---|---|---|
| Detect up to `d` errors | `d + 1` | `d` flips can't reach another legal codeword |
| Correct up to `d` errors | `2d + 1` | the right codeword stays strictly closest |

So a distance-3 code corrects 1 error *or* detects 2; the distance-5 example from the text (codewords `0000000000`, `0000011111`, `1111100000`, `1111111111`) corrects 2 errors or detects 4 — but not both at once, since a received word can't be interpreted two ways. `code/main.py`'s `min_distance()` computes this directly for that four-codeword set.

For a single-error-correcting code, each of the `2^m` legal messages needs itself plus its `n` distance-1 neighbours reserved, so `(n + 1) 2^m ≤ 2^n`, which with `n = m + r` gives the **Hamming bound**:

```
(m + r + 1) ≤ 2^r        (3-1)
```

For `m = 7`: `r = 3` gives `7+3+1 = 11 > 8`, too few; `r = 4` gives `12 ≤ 16`, just enough. That is exactly the (11,7) code.

### The (11,7) Hamming code: encode and decode

Number codeword bits `1..11` left to right. Positions that are powers of two — **1, 2, 4, 8** — are check bits; the rest (3, 5, 6, 7, 9, 10, 11) carry the 7 data bits. Each check bit `p_k` forces *even parity* over the positions whose binary expansion contains `k`. To find which checks cover data bit at position `j`, write `j` as a sum of powers of two: `11 = 1 + 2 + 8`, so bit 11 is covered by `p1`, `p2`, and `p8`. `assets/error-correcting-codes.svg` lays out all eleven positions, the four coverage sets, and the resulting syndrome.

Worked example — ASCII `'A'` = `1000001` (the textbook's Fig. 3-6). After encoding, the codeword sent is `00100001001`. Suppose the channel flips **position 5**, so the receiver gets `00101001001`. The decoder recomputes each parity sum:

| Check | Covers positions | Parity over received | Result |
|---|---|---|---|
| `p1` | 1,3,5,7,9,11 | odd | fail → +1 |
| `p2` | 2,3,6,7,10,11 | even | pass |
| `p4` | 4,5,6,7 | odd | fail → +4 |
| `p8` | 8,9,10,11 | even | pass |

The check results read as `p8 p4 p2 p1 = 0101` = **5**. The non-zero **syndrome** *is* the position in error. Flip bit 5, drop the check bits, and you recover `1000001` = `'A'`. If the syndrome is 0, all sums are even and the frame is accepted. `code/main.py` reproduces every step in `encode_hamming_11_7()`, `syndrome()`, and `decode_hamming_11_7()`, and prints the syndrome for a flip at each of the 11 positions to show every single-bit error maps to a distinct, correctable syndrome.

The distance-3 limit bites with two errors: flipping positions 3 and 7 yields syndrome 4 (non-zero, so detected) but the decoder "corrects" bit 4 and hands back the wrong byte. Distance 3 cannot repair two flips — you'd need distance 5.

### Convolutional codes: memory instead of blocks

A convolutional code has no block boundary. An encoder streams input bits through shift registers and emits output bits that depend on the current bit *and* several previous ones; the number of input bits that influence an output is the **constraint length** `k`. The text's example is the **NASA rate-1/2, k=7** code: each input bit produces two output XOR sums, first flown on Voyager in 1977 and later adopted in 802.11. Its six memory registers shift right each tick; feeding `111` from an all-zero state produces outputs `11`, `10`, `01`, and it takes 7 shifts to flush a bit's influence — hence `k = 7`. It is *not* systematic, since no output equals the raw input.

Decoding finds the input stream most likely to have produced the received (possibly corrupted) output, via the **Viterbi algorithm**, which tracks, per step and per register state, the lowest-error path. Convolutional codes shine with **soft-decision decoding**: instead of slamming `0.9V` to "1" and `-0.1V` to "0" immediately, the decoder treats `0.9V` as "very likely 1" and `-0.1V` as "maybe 0," folding bit confidence into the path search for stronger correction. Deciding each bit first is **hard-decision decoding**.

### Reed-Solomon: symbols beat bursts

Reed-Solomon codes are linear, systematic block codes, but they operate on `m`-bit **symbols**, not single bits. The intuition: an `n`-degree polynomial is fixed by `n+1` points, so extra points are redundant — send your data points plus check points on the same curve, and if one point arrives wrong you re-fit the curve and recover it. Formally they work over finite fields; codewords are `2^m − 1` symbols long. With `m = 8`, symbols are bytes and a codeword is **255 bytes**. The widely deployed **(255, 233)** code adds 32 check bytes: with `2t` redundant symbols you correct `t` errors, so 32 bytes correct **16 symbol errors**. Because each symbol is 8 contiguous bits, that's a burst of up to **128 bits** corrected as a side effect — exactly why RS protects CDs, DVDs, Blu-ray, DSL, cable data, and satellite. (For *erasures* — symbols known to be missing, like a scratch — you correct up to `2t`.) Decoding uses the **Berlekamp–Massey** algorithm.

RS is often **concatenated** inside a convolutional code: the convolutional code handles isolated flips but fails in bursts; the inner RS decoder mops up those bursts. The pair guards against both random and burst errors.

### LDPC: low-density parity check

LDPC codes are linear block codes from Gallager's 1962 thesis, forgotten until 1995 when computing caught up. Each output bit depends on only a fraction of input bits, so the parity-check matrix is mostly zeros (low density). Decoding is iterative belief-propagation that refines a best fit to a legal codeword. LDPC has excellent performance at large block sizes and now appears in DVB-S2, 10-Gbps Ethernet (10GBASE-T), power-line networks, and the latest 802.11.

### Choosing a family

| Code | Operates on | Distance/power | Best at | Real use |
|---|---|---|---|---|
| Hamming (11,7) | bits | d=3, corrects 1 | random single flips | ECC RAM |
| Convolutional (NASA k=7) | bit stream | rate 1/2, Viterbi | random errors, soft-decision | Voyager, GSM, 802.11 |
| Reed-Solomon (255,233) | 8-bit symbols | corrects 16 symbols / 128-bit burst | bursts, erasures | CD/DVD/Blu-ray, DSL, DVB |
| LDPC | bits (sparse matrix) | near-capacity | large blocks, high rate | DVB-S2, 10GBASE-T, 802.11ax |

## Build It

1. Read `code/main.py`. The four core functions are `encode_hamming_11_7()`, `syndrome()`, `decode_hamming_11_7()`, and the distance tools `hamming_distance()` / `min_distance()`.
2. Run `python3 main.py`. Confirm `'A'` encodes to `00100001001` and that flipping position 5 yields syndrome 5 and recovers `'A'` — matching Fig. 3-6.
3. Read the per-position syndrome table the program prints. Verify every single flip produces a *unique* syndrome equal to the flipped position (the defining property of the construction).
4. Inspect the double-error case: flip two bits and observe a non-zero-but-wrong syndrome. This is the distance-3 wall.
5. Change the input character (e.g. encode `'k'`), recompute the check bits by hand using the coverage table, and check your work against the program's output.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Encode a Hamming codeword | `encode_hamming_11_7()` output vs. hand-computed check bits | Check bits at positions 1,2,4,8 force even parity over their coverage sets |
| Locate a corrupted bit | Syndrome value from `syndrome()` | Syndrome equals the flipped position; flipping it restores the message |
| Bound a code's power | `min_distance()` on a codeword set | You state detect = `d-1`, correct = `floor((d-1)/2)` and explain the trade-off |
| Match code to error profile | Burst length vs. RS symbol math | You pick RS for bursts, convolutional+Viterbi for random/soft-decision |
| Justify FEC vs. ARQ | Link RTT, duplex, back-channel availability | FEC chosen for high-latency/broadcast/no-return-path links |

## Ship It

Produce one artifact under `outputs/`:

- A one-page decode runbook: the coverage table, the syndrome → position map, and the "flip the bit named by the syndrome" rule.
- A short script that fuzzes random single- and double-bit errors against `code/main.py` and tallies corrected vs. mis-corrected, demonstrating the distance-3 boundary empirically.
- A decision card: error profile (random vs. burst), back-channel availability, and latency budget → recommended code family.

Start from `outputs/prompt-error-correcting-codes.md`.

## Exercises

1. Encode the ASCII character `'k'` (`1101011`) into an (11,7) codeword by hand, then verify against `encode_hamming_11_7()`. Which check bits end up as 1?
2. Apply the Hamming bound `(m + r + 1) ≤ 2^r` to a 16-bit message. What is the minimum number of check bits for single-error correction, and what `(n, m)` code results?
3. Take the distance-5 code `{0000000000, 0000011111, 1111100000, 1111111111}`. Receiver gets `0000000111`. Which codeword does a "correct up to 2 errors" decoder choose, and why can't it *also* detect 4 errors on this link?
4. A Reed-Solomon (255,223) code (32 check bytes) protects a link. How many symbol errors can it correct? What is the longest contiguous bit burst it absorbs, and how does the answer change if those symbols are *erasures*?
5. The NASA k=7 convolutional encoder starts in state `000000` and receives input `111`. Trace the six-register state and the two output bits after each of the three input bits. Why does it take seven shifts to flush one input bit?
6. Your satellite downlink has a 250 ms one-way delay and is broadcast to many receivers with no return channel. Argue why FEC is mandatory here and an ARQ retransmission scheme is not viable.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Hamming distance | "how different two strings are" | The count of differing bit positions; the code's *minimum* distance fixes its detect/correct power |
| Syndrome | "the error flag" | The check-results read as a binary number; in a Hamming code it *equals the position* of the flipped bit |
| Code rate | "overhead" | The useful fraction `m/n`; ~1/2 on noisy links, near 1 on clean ones |
| Systematic code | "encoded data" | Data bits are sent verbatim with check bits appended — readable before decoding |
| Constraint length `k` | "how long the code is" | How many past input bits influence an output bit in a convolutional code (NASA code: `k=7`) |
| Soft-decision decoding | "more accurate decoding" | Feeding analog bit *confidence* (e.g. 0.9V = "very likely 1") into Viterbi instead of pre-quantized 0/1 |
| Reed-Solomon symbol | "a byte of error correction" | An `m`-bit unit (m=8 ⇒ byte); one symbol error covers any flip *or* burst inside those 8 bits |
| Concatenated code | "double encoding" | An inner code (RS) nested in an outer code (convolutional) so RS mops up the bursts the convolutional decoder emits |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks* (6th ed.), §3.2.1 Error-Correcting Codes — the source for this lesson.
- R. W. Hamming, "Error Detecting and Error Correcting Codes," *Bell System Technical Journal*, 1950 — the original (11,7)-style construction.
- A. J. Viterbi (1967) / G. D. Forney, "The Viterbi Algorithm," *Proc. IEEE*, 1973 — convolutional decoding.
- I. S. Reed and G. Solomon, "Polynomial Codes over Certain Finite Fields," 1960; J. Massey, "Shift-Register Synthesis and BCH Decoding," 1969 — RS and Berlekamp–Massey.
- R. G. Gallager, "Low-Density Parity-Check Codes," 1962 — the LDPC origin.
- IEEE 802.11 (Wi-Fi, convolutional and LDPC coding) and IEEE 802.3 / 10GBASE-T (LDPC) standards.
- ETSI EN 302 307 (DVB-S2, LDPC + BCH) and ECMA-130 (CD-ROM, Reed-Solomon CIRC).
