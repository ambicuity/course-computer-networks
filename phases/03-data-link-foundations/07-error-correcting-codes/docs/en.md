# Hamming Codes and Forward Error Correction

> A noisy link flips bits, and the data link layer has two ways to respond: detect the damage and ask for a retransmission (ARQ), or repair the damage in place with **forward error correction (FEC)**. FEC trades bandwidth for latency: a frame of *m* data bits carries *r* redundant **check bits** forming an *(n, m)* codeword where *n = m + r*; the **code rate** *m/n* measures how much of the wire is real payload. The workhorse single-error-correcting code is the **Hamming code** (Hamming, 1950): check bits sit at power-of-two positions (1, 2, 4, 8, ...), each checks every data bit whose position includes that power of two in its binary expansion, and the receiver XORs the checks into an **error syndrome** whose integer value *is* the 1-based index of the flipped bit — flip it and you recover the original. A classic Hamming code has **Hamming distance 3**, so it corrects any single-bit error *or* detects any double-bit error, but not both at once. Adding one overall parity bit lifts it to **distance 4** and yields the **SEC-DED** (single-error-correction, double-error-detection) scheme used in ECC memory. Real links that are too noisy for retransmission go further: **convolutional codes** (the NASA *r = 1/2, k = 7* code from Voyager, reused in 802.11) decoded by the **Viterbi** algorithm; **Reed-Solomon** codes operating on 8-bit *symbols* that swallow burst errors (the (255, 233) code corrects 16 symbol errors = a 128-bit burst); and **LDPC** codes (Gallager 1962, revived 1995) now standard in 10 Gbps Ethernet, DVB, and 802.11n/ac/ax. The hard design rule is **2r ≥ m + r + 1**: that is how many check bits you must spend to guarantee correction of every single-bit error. This lesson builds a runnable *(11, 7)* Hamming encoder, syndrome decoder, and SEC-DED extension so you can watch a flipped bit self-heal.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Binary and XOR arithmetic, parity, the data link layer framing problem (Phase 3 framing lesson)
**Time:** ~75 minutes

## Learning Objectives

- Compute the minimum number of check bits *r* for a given *m* using **2r ≥ m + r + 1**, and read off the resulting *(n, m)* code and code rate.
- Place check and data bits in a Hamming codeword by position (power-of-two checks, the rest data) and compute each check bit as the even-parity XOR of its covered positions.
- Decode a received codeword by recomputing the checks into a binary **syndrome**, interpret the syndrome as a bit index, flip that bit, and strip the check bits to recover the message.
- Explain why a distance-3 code corrects one error *or* detects two, and how an extra overall parity bit turns it into a distance-4 SEC-DED code.
- Distinguish Hamming, convolutional (Viterbi), Reed-Solomon, and LDPC codes by symbol size, burst-error behavior, and where each is deployed (ECC RAM, 802.11, CD/DVD, 10GbE).
- Decide between FEC and ARQ given a link's bit-error rate, latency budget, and whether the channel is symmetric (retransmission possible) or one-way (broadcast/satellite downlink).

## The Problem

A satellite downlink transmits a 1-megabyte telemetry frame once per orbit. The uplink is a low-gain dish that takes 90 minutes to acknowledge, and a single flipped bit in a compressed image header renders the whole frame useless. Retransmission is impractical — by the time the ground station asks for a resend the satellite has moved below the horizon. The same shape of problem shows up closer to earth: a Wi-Fi frame on a congested 2.4 GHz channel arrives with a burst of errors inside a single OFDM symbol, and a 4096-byte NFS write over a lossy 802.11 link would trigger so many retransmissions that throughput collapses. The question the data link layer must answer is: *how many redundant bits do I add, and in what pattern, so the receiver can fix the damage itself without asking me to send the frame again?*

## The Concept

### Block codes, codewords, and code rate

A **block code** takes *m* message bits and appends *r* check bits computed solely from those *m* bits, producing an *n*-bit **codeword** with *n = m + r*. We call this an *(n, m)* code. The **code rate** is *m/n* — the fraction of each transmitted codeword that is actual information. A rate of 1/2 spends half the wire on redundancy and is typical of a very noisy channel (Voyager's convolutional code); a rate near 1 adds a handful of check bits to a large message and fits a clean fiber.

The codes in this family share three properties the textbook is careful to name: they are **linear** (each check bit is a modulo-2 / XOR combination of data bits, so encoding is matrix multiplication over GF(2)), **systematic** (the *m* data bits appear unchanged in the codeword, with check bits interleaved — you can read the message directly after stripping checks), and **block** (each codeword is independent, unlike a convolutional code that has memory across bits).

### Hamming distance: how many errors a code can tolerate

Given two *n*-bit codewords, their **Hamming distance** is the number of positions at which they differ — equivalently, the popcount of their XOR. The **distance of a code** is the minimum Hamming distance between any two of its legal codewords. This single number dictates the error budget:

| Code distance *d* | Can detect up to | Can correct up to |
|---|---|---|
| 2 | 1 error | 0 (no correction) |
| 3 | 2 errors | 1 error |
| 4 | 3 errors | 1 error (plus detect 2) |
| 5 | 4 errors | 2 errors |
| *d* | *d − 1* | ⌊(*d* − 1)/2⌋ |

The rule is symmetric: to **detect** *e* errors you need distance *e + 1* (no combination of *e* flips can turn one legal codeword into another); to **correct** *e* errors you need distance *2e + 1* (even with *e* flips, the received word is still closer to the original than to any other legal codeword). A code with distance 3 therefore corrects 1 error *or* detects 2 — but not both simultaneously, because a double-bit error lands at distance 2 from the original, which is also distance 1 from two different neighbors, and the decoder cannot tell correction from detection apart.

### The Hamming bound: how many check bits you must spend

To correct every single-bit error, each of the 2*m* legal messages needs a private "cloud" of *n* illegal codewords at distance 1 (one for each flipped bit), plus itself — that is *n + 1* patterns per message. The total patterns cannot exceed 2*n*, so (n + 1)·2*m* ≤ 2*n*. Substituting *n = m + r* and dividing by 2*m* gives the **Hamming bound**:

> **2^r ≥ m + r + 1**

This is the lower limit on check bits for single-error correction. For *m = 7* data bits: *r = 3* gives 8 < 11 (too small), *r = 4* gives 16 ≥ 11 (works) — so a 7-bit message needs 4 check bits, yielding the *(11, 7)* Hamming code at rate 7/11 ≈ 0.636. For *m = 64* (a 64-bit word), *r = 6* gives 64 < 71, *r = 7* gives 128 ≥ 71 — so ECC memory uses 7 check bits per 64-bit word, an *(72, 64)* SEC-DED code. `code/main.py` has a `min_check_bits(m)` function that solves this bound directly.

### Building an (11, 7) Hamming code: positions and parity covers

In a Hamming code the codeword positions are numbered from **1** at the left. Positions that are **powers of two** (1, 2, 4, 8, ...) hold check bits; every other position (3, 5, 6, 7, 9, 10, 11, ...) holds a data bit. For the *(11, 7)* code the layout is:

| Position | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Role | p1 | p2 | d1 | p4 | d2 | d3 | d4 | p8 | d5 | d6 | d7 |

Each check bit *p* at position 2^k covers every position whose binary expansion includes 2^k. A data bit at position *j* is checked by the check bits whose powers appear in *j*'s binary decomposition — position 11 = 8 + 2 + 1 is covered by p8, p2, p1; position 6 = 4 + 2 is covered by p4, p2. Encoding is then: for each check position, XOR all data bits in its cover set, and write the result into that check position. The code sets **even parity**, so the XOR of every covered bit (check included) is 0.

Worked example, message = `1000001` (ASCII 'A', 7 bits), data bits placed at positions 3,5,6,7,9,10,11 (so pos3=1, pos5=0, pos6=0, pos7=0, pos9=0, pos10=0, pos11=1):
- p1 covers positions 1,3,5,7,9,11 → 1,0,0,0,1 → p1 = 1⊕0⊕0⊕0⊕1 = 0
- p2 covers positions 2,3,6,7,10,11 → 1,0,0,0,1 → p2 = 1⊕0⊕0⊕0⊕1 = 0
- p4 covers positions 4,5,6,7 → 0,0,0 → p4 = 0
- p8 covers positions 8,9,10,11 → 0,0,1 → p8 = 1

Codeword (positions 1–11): `0 0 1 0 0 0 0 1 0 0 1`. `code/main.py`'s `encode_hamming(data)` reproduces this exactly — run it and compare.

### The syndrome: the error's address

Decoding re-runs the same parity checks, this time including the received check bits. Each check that passes contributes 0 to the **syndrome**; each that fails contributes 1. The syndrome is a binary number with one bit per check position, ordered by check power (p1 is the least-significant bit, then p2, p4, p8, ...).

The design is what makes this magical: because position *j* is covered by exactly the check bits in its binary expansion, a single error at position *j* makes exactly those checks fail — so the syndrome *equals j*. A syndrome of 0 means no error; a syndrome of 5 (binary `0101`, p4 and p1 failed) means position 5 is wrong. The receiver flips that one bit and discards the check positions to recover the message.

Continuing the example: if the channel flips position 5 (the data bit at pos 5, which was 0, becomes 1), the received word is `0 0 1 0 1 0 0 1 0 0 1`. Recomputing:
- p1 check: positions 1,3,5,7,9,11 = 0,1,1,0,0,1 → XOR = 1 (fail)
- p2 check: positions 2,3,6,7,10,11 = 0,1,0,0,0,1 → XOR = 0 (pass)
- p4 check: positions 4,5,6,7 = 0,1,0,0 → XOR = 1 (fail)
- p8 check: positions 8,9,10,11 = 1,0,0,1 → XOR = 0 (pass)

Syndrome bits (LSB first) = `1 0 1 0` = 5. Flip position 5, strip checks (positions 3,5,6,7,9,10,11) → `1000001`. The error has self-healed. See `assets/error-correcting-codes.svg` for the encode → channel → syndrome → flip pipeline.

### SEC-DED: adding the overall parity bit

A plain Hamming code has distance 3, so a **double** error produces a nonzero syndrome pointing at a *third*, innocent position — the decoder "corrects" a bit that was never wrong and silently corrupts the message. ECC memory cannot tolerate that, so it appends one **overall parity bit** covering the entire codeword. Now:

| Syndrome | Overall parity | Verdict |
|---|---|---|
| 0 | even | No error — accept |
| nonzero | odd | Single error — correct bit at syndrome index |
| nonzero | even | Double error — **detect**, do not correct |
| 0 | odd | Error in the overall parity bit itself — accept data |

This is a **distance-4** code: it corrects one error and detects two (**SEC-DED**), the standard for DRAM ECC. `code/main.py` implements this as `encode_secded` / `decode_secded`, returning a tag (`OK`, `CORRECTED`, `DOUBLE_ERROR`) so you can see the three outcomes.

### Where each FEC code is deployed

Hamming/SEC-DED is cheap and corrects one bit — perfect for memory, wrong for a bursty radio. The deployed landscape:

| Code | Symbol | Strength | Where you meet it |
|---|---|---|---|
| Hamming (SEC-DED) | 1 bit | 1-bit correction | ECC DRAM (72,64), early telemetry |
| Convolutional (NASA *r=1/2, k=7*) | bit stream | isolated bit errors, soft-decision | 802.11a/g PLCP, GSM, satellite, Voyager |
| Reed-Solomon (255, 233) | 8-bit byte | up to *t* of 2*t* redundant symbols; burst-proof | CD/DVD/Blu-ray, DSL, cable modems, DVB, QR codes |
| LDPC | large blocks | near-Shannon-limit, iterative | 10 Gbps Ethernet (802.3an), DVB-S2/T2, 802.11n/ac/ax, 5G data |

Two practical combinations matter. **Reed-Solomon inside a convolutional code** ("RS-CC") handles both isolated bit errors (the convolutional code) and the error bursts the convolutional decoder emits when it finally fails (Reed-Solomon mops those up) — this is the 802.11a/g and many satellite chains. **LDPC with soft information** is what lets a modern Wi-Fi or 5G link approach the Shannon limit on a fading channel where retransmission would be catastrophic for latency.

### FEC versus ARQ: the engineering choice

FEC is not free. Every check bit is bandwidth you cannot use for payload, and the decoder costs silicon and power. The textbook framing is exact: on a **noisy wireless link** with no return path (satellite broadcast, deep-space) FEC is mandatory — without it nothing gets through. On a **clean fiber** the bit-error rate is so low (10⁻¹² or better) that FEC's overhead wastes more capacity than it saves, and a CRC plus retransmission (**ARQ**) is cheaper: detect, drop, ask again. The middle ground — a link with moderate errors *and* a working return path, like Wi-Fi — uses **hybrid ARQ**: FEC fixes the common single-bit case, and only the residual uncorrectable errors trigger a retransmission. The decision rests on three numbers: the bit-error rate, the round-trip time, and whether the channel is one-way.

## Build It

1. Open `code/main.py` and read `min_check_bits(m)` — confirm it solves 2^r ≥ m + r + 1 by incrementing *r* until the inequality holds, then run it for *m = 7, 64, 1024* and check against the Hamming bound by hand.
2. Run `encode_hamming([1,0,0,0,0,0,1])` and verify it produces `0 0 1 0 0 0 0 1 0 0 1` — the *(11, 7)* codeword for ASCII 'A' (run `python3 main.py` to see the full trace).
3. Inject an error with `inject_error(codeword, 5)` (flips position 5) and pass the result to `decode_hamming`. Confirm the syndrome is 5 and the recovered message is the original.
4. Run the SEC-DED path: encode with `encode_secded`, inject errors at *two* positions, and confirm `decode_secded` returns tag `DOUBLE_ERROR` instead of silently miscorrecting.
5. Run `python3 main.py` to execute `main()`, which prints the encode/decode trace, a single-error correction, a double-error detection, and the check-bit budget table for *m ∈ {7, 64, 1024, 4096}`.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify encoding matches the textbook | `encode_hamming('A')` output vs Fig. 3-6 | Bit-for-bit identical codeword `111100110 01` |
| Confirm single-error correction | Inject at position 5, decode | Syndrome == 5, recovered data == original |
| Confirm double-error detection | SEC-DED with two flips | Tag `DOUBLE_ERROR`, data flagged untrusted |
| Size a code for a word width | `min_check_bits(64)` | Returns 7 → matches (72,64) ECC DRAM |
| Read a deployed code | Identify the (255,233) RS code | Knows it adds 32 symbols, corrects 16 = a 128-bit burst |
| Choose FEC vs ARQ | Given BER 10⁻⁵, RTT 2 ms, bidirectional | Picks hybrid ARQ, justifies with numbers |

## Ship It

Run `python3 code/main.py > outputs/prompt-error-correcting-codes.txt` (or save the printed trace into `outputs/prompt-error-correcting-codes.md`). The artifact is the encode → channel → syndrome → recovered-message trace for a single-error correction and a SEC-DED double-error detection, plus the check-bit budget table. That trace is the proof the encoder and decoder are correct and that the syndrome really does equal the flipped bit's index.

## Exercises

1. A 16-bit message is sent with a Hamming code. Compute *r* from the Hamming bound, state the resulting *(n, m)* code and its code rate, and list which positions are check bits.
2. Encode the 7-bit message `1011001` with the *(11, 7)* Hamming code by hand, then inject a single error at position 9 and compute the syndrome. Confirm the syndrome equals 9 and the recovered message matches the original.
3. A received *(11, 7)* codeword has hexadecimal value `0xE4F` (12 bits including the SEC-DED overall parity). Decode it: report the syndrome, the overall-parity check, the verdict (OK / CORRECTED / DOUBLE_ERROR), and the recovered 7-bit message.
4. The (255, 233) Reed-Solomon code over 8-bit symbols corrects up to 16 symbol errors. Compute the longest contiguous bit burst it can repair, and explain why the same code can correct up to 32 *erasures* but only 16 *unknown* errors.
5. A satellite downlink has BER 10⁻⁵ and a 12-minute one-way light time; a fiber link has BER 10⁻¹³ and 2 ms RTT. For each, choose FEC-only, ARQ-only, or hybrid ARQ, and justify with the round-trip time and the probability that a 1500-byte frame arrives uncorrectable.
6. Add a function to `code/main.py` that, given *m*, returns the code rate *m/(m+r)* for the smallest valid *r*, and plot (in a printed table) how rate climbs toward 1 as *m* grows from 4 to 4096. Explain in one sentence why ECC overhead becomes negligible for large blocks.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Hamming distance | "how different two bit strings are" | popcount of the XOR of two codewords; a code's *minimum* distance sets its detect/correct budget |
| Code rate | "the speed of the code" | *m/n*, the fraction of a codeword that is payload, not redundancy |
| Syndrome | "the error flag" | The XOR vector of re-checked parities; its integer value *is* the 1-based index of the single flipped bit |
| SEC-DED | "ECC memory" | Single-Error-Correction, Double-Error-Detection — a distance-4 Hamming code plus an overall parity bit |
| Convolutional code | "the Wi-Fi code" | A non-block, memoryful code where each input bit produces *k* output bits as XORs of input and shift-register state; decoded by Viterbi |
| Constraint length | "how far back the code looks" | *k*, the number of input bits (current + previous) that influence an output; the NASA code has *k = 7* |
| Soft-decision decoding | "using the analog signal" | Decoding from bit *probabilities* (e.g. 0.9 V ≈ "likely 1") rather than hard 0/1, gaining ~2 dB over hard-decision |
| Reed-Solomon | "the CD/DVD code" | A linear block code over *m*-bit symbols (typically bytes) that corrects up to *t* symbol errors from 2*t* redundant symbols; burst-proof |
| LDPC | "the new Wi-Fi/5G code" | Low-Density Parity-Check code — sparse parity matrix, iterative near-Shannon-limit decoding; 10GbE, DVB-S2, 802.11n+ |

## Further Reading

- R. W. Hamming, "Error Detecting and Error Correcting Codes," *Bell System Technical Journal*, 29(2), 1950 — the original (11,7) construction and the distance argument.
- S. Lin and D. J. Costello, *Error Control Coding*, 2nd ed., Prentice Hall, 2004 — the standard reference for Hamming, convolutional, RS, and LDPC codes, with the Viterbi and Berlekamp-Massey algorithms.
- A. J. Viterbi, "Error bounds for convolutional codes and an asymptotically optimum decoding algorithm," *IEEE Trans. IT*, 13(2), 1967 — the Viterbi algorithm.
- I. S. Reed and G. Solomon, "Polynomial Codes Over Certain Finite Fields," *J. SIAM*, 8(2), 1960 — the Reed-Solomon code; the (255, 233) instance is standardized in CCSDS 131.0-B-3 for space links.
- R. G. Gallager, *Low-Density Parity-Check Codes*, MIT Press, 1963 (PhD thesis, 1962) — LDPC, revived by MacKay and Neal in 1995.
- IEEE 802.3an-2006, *10 Gb/s Ethernet Task Force* — LDPC for 10GBASE-T.
- ETSI EN 302 307, *DVB-S2* — LDPC + BCH concatenated code for digital video broadcasting.
- IEEE 802.11-2020, Clause 17 (OFDM PLCP) — the NASA *r = 1/2, k = 7* convolutional code as the legacy 6 Mbps mandatory rate, plus LDPC in 802.11n/ac/ax amendments.
- J. E. Meggitt, "Error correcting codes for correcting bursts of errors," *IBM J. Res. Dev.*, 4(3), 1960 — fire codes and the burst-error motivation that drives RS adoption.
