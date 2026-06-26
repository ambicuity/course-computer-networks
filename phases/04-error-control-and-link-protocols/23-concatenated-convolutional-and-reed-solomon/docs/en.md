# Concatenating convolutional and Reed-Solomon codes

> A noisy physical channel rarely hands you isolated single-bit errors — it hands you bursts. A **convolutional code** (the NASA `r=1/2, k=7` code from the Voyager 1977 mission, reused in IEEE 802.11a/g) is excellent at correcting scattered bit flips via the **Viterbi** decoder, but it fails catastrophically when too many errors land close together: the decoder picks a wrong path through the trellis and emits an **error burst** that can run tens of bits long. A **Reed-Solomon** block code operates on *m-bit symbols* over the finite field GF(2^m), most commonly `m=8` so a symbol is a byte; the ubiquitous **(255, 233)** code adds `2t=32` redundant bytes and corrects up to `t=16` symbol errors — which, because the symbols are consecutive, mops up a burst of up to `16 × 8 = 128` bits. **Concatenation** (Forney, 1966) puts the RS code *outside* the convolutional code: the outer RS encoder adds parity bytes, an optional **interleaver** spreads them across time, the inner convolutional encoder produces the transmitted bitstream, the Viterbi decoder cleans up the random errors, and the RS decoder corrects the residual bursts the Viterbi produced. The class of channel this targets is the one the textbook states explicitly — *convolutional codes handle isolated errors, Reed-Solomon handles the bursts that remain* — and it is the architecture behind DVB-S, DVB-T, ATSC, cable modems (DOCSIS), and the Voyager/CCSDS deep-space standard. The failure modes are: Viterbi error propagation when the channel crosses the cutoff rate, RS failure when the burst exceeds `t` symbols, and — most subtly — interleaver overflow when a fade lasts longer than the interleaving depth.

**Type:** Build
**Languages:** Python
**Prerequisites:** Hamming distance and block codes, the basic idea of a convolutional encoder as a state machine, polynomial arithmetic over finite fields (GF(2))
**Time:** ~85 minutes

## Learning Objectives

- Explain *why* a convolutional code alone is insufficient on a bursty channel and quantify the error-burst length a Viterbi decoder can emit when it takes a wrong trellis path.
- Build the NASA `r=1/2, k=7` convolutional encoder from its generator polynomials `g1=171oct` and `g2=133oct`, and decode a noisy received sequence with a Viterbi algorithm over the 64-state trellis.
- Construct a Reed-Solomon `(n=255, k=233)` codeword over GF(2^8) using the primitive polynomial `0x11D`, compute syndromes, and locate/correct up to `t=16` symbol errors.
- Wire RS + interleaver + convolutional code into a concatenated encoder/decoder and demonstrate that the concatenation corrects a burst that defeats the inner code alone.
- Compute the coding gain and overhead of a concatenated scheme and decide when interleaving depth matters.
- Read the evidence — syndrome values, Viterbi path metric, uncorrectable-block flag — that tells you which stage failed.

## The Problem

A satellite downlink sends 2 Mbit/s of telemetry over a link with a raw bit-error rate of `10^-3`, punctuated by rain fades that drop whole 4-ms bursts. The team picked the NASA `r=1/2, k=7` convolutional code because it drives the *isolated* error rate down to `10^-6` at the operating Eb/N0. In the lab it looks great. On orbit it fails: every fade produces a burst the Viterbi decoder turns into a multi-decade-bit error event, and the recovered frame fails its CRC. Raising Eb/N0 is not an option — the link budget is fixed. The team has bandwidth to spare for redundancy but no way to make the channel less bursty. They need a code structure that *absorbs* the Viterbi's residual bursts. That structure is a Reed-Solomon outer code wrapped around the convolutional inner code, with a convolutional interleaver between them.

## The Concept

### The inner code: a rate-1/2, k=7 convolutional encoder

A convolutional encoder is a shift register of `k-1 = 6` memory cells that, for each new input bit, emits two output bits computed as XOR taps. The NASA code is defined by two generator polynomials expressed in octal:

| Output | Generator (octal) | Generator (binary, MSB = current input) |
|---|---|---|
| `c1` | `171` | `1111001` |
| `c2` | `133` | `1011011` |

`c1` XORs the input with taps at positions 0,1,2,3,6; `c2` XORs taps at 0,2,3,4,6. Because each input bit produces two output bits, the rate is `1/2`. Because the impulse response lasts 7 input bits (it takes 7 shifts to flush one input bit out of the register), the **constraint length** is `k=7`, giving `2^6 = 64` encoder states. The encoder is **non-systematic** — neither output is the raw input bit. After the data, the encoder is flushed with `k-1 = 6` tail bits (zeros) to return the state to 0, which lets the Viterbi decoder terminate cleanly. `code/main.py` implements this encoder bit-for-bit; see `assets/concatenated-convolutional-and-reed-solomon.svg` for the shift-register layout and the tap positions.

### Decoding: the Viterbi algorithm over the trellis

The Viterbi decoder walks the *trellis* — the unrolled state machine — and, at each time step and for each of the 64 states, keeps the single path with the smallest accumulated **Hamming distance** (hard-decision) or squared Euclidean distance (soft-decision) to the received bits. With soft decisions (`-1V`→logical 0, `+1V`→logical 1, decoder works with the analog confidence), a typical implementation gains ~2 dB over hard decision. The key failure mode is **error propagation**: if the channel is bad enough that the correct path's metric exceeds a wrong path's metric at some step, the decoder locks onto the wrong path and stays there, emitting a burst of errors that ends only when the correct path's metric recovers — which, near the cutoff rate, can be tens of bits.

Worked example. Suppose the encoder is in state `000000` and the next 7 input bits are all 0, producing 14 output bits `00 00 00 00 00 00 00`. If a burst flips bits 3..9 (7 consecutive errors), the hard-decision Viterbi decoder may decide the input was `0001000` rather than `0000000` — one wrong bit — *or*, if the burst is long enough, it may diverge onto a wrong path and emit 6–10 wrong bits before recovering. That residual burst is what the outer code must clean up.

### The outer code: Reed-Solomon over GF(2^8)

A Reed-Solomon code treats data as a sequence of *symbols*, not bits — for `m=8` each symbol is a byte. Codewords live over the finite field GF(2^8) defined by the primitive polynomial `0x11D` (`x^8 + x^4 + x^3 + x^2 + 1`), the field used by CCSDS and DVB. A codeword is `n = 2^m - 1 = 255` symbols long. The encoder takes `k` data symbols, treats them as the low-order coefficients of a polynomial, divides by the generator polynomial `g(x) = ∏(x - α^i)` for `i = 1..2t`, and appends the `2t` remainder symbols as parity. The textbook's `(255, 233)` code has `k=233`, `2t=32`, so it corrects `t=16` symbol errors.

The crucial property: a 1-bit error and an 8-bit burst error are both *one symbol error*. So `(255, 233)` corrects a contiguous burst of up to `16 × 8 = 128` bits. With **erasures** (positions known to be bad, e.g. a scratched CD), it corrects up to `2t = 32` symbols — twice as many, because the location is already known and only the value must be recovered.

### Decoding RS: syndromes, Berlekamp-Massey, Chien search, Forney

RS decoding is a four-step pipeline, all over GF(2^8):

1. **Syndrome computation.** Evaluate the received polynomial `r(x)` at `α^1, α^2, …, α^{2t}`. If all `2t` syndromes are zero, the codeword is valid. Otherwise the syndromes encode the error pattern.
2. **Berlekamp-Massey.** From the syndromes, compute the **error-locator polynomial** `Λ(x)`. Its degree equals the number of errors `v` (must be `≤ t`).
3. **Chien search.** Find the roots of `Λ(x)` by trial. Each root `α^{-i}` locates an error at position `i`.
4. **Forney algorithm.** Given the locations, compute the error *values* and subtract (XOR) them from the received word.

If `v > t`, decoding fails — the block is flagged **uncorrectable** and is passed up the stack or requested again via ARQ. `code/main.py` implements a self-contained GF(2^8) RS `(7, 3)` code (small enough to trace by hand, identical mechanics to `(255, 233)`) so you can watch each step.

### Concatenation: outer RS, inner convolutional, interleaver between

Forney's 1966 concatenation puts the two codes in series with the **stronger, block-based** code outermost:

| Stage | Role | Why this order |
|---|---|---|
| RS outer encoder | Adds `2t` symbol parity | Operates on clean data before the channel |
| **Convolutional interleaver** | Spreads consecutive RS symbols across separate codewords/time slots | A single Viterbi error burst hits many *different* RS codewords, one symbol each, instead of one codeword many times |
| Convolutional inner encoder | Produces the transmitted bitstream | Best at random errors; closest to the physical channel |
| Channel | Adds noise / fades | — |
| Viterbi inner decoder | Corrects random bit errors; emits occasional bursts | Reduces BER from `10^-3` to `10^-5`–`10^-6` |
| Convolutional deinterleaver | Reassembles RS codewords | Spreads each Viterbi burst across many RS words |
| RS outer decoder | Corrects residual symbol bursts | Mops up what Viterbi missed |

The interleaver is the secret ingredient. Without it, a Viterbi burst of 40 bits lands inside a single `(255, 233)` word as 5 byte errors — fine, correctable. But a 200-bit burst lands as 25 byte errors in one word, exceeding `t=16`, and that word is lost even though the total error count is small. A depth-`I` convolutional interleaver spreads those 200 bits across `I` different RS words, ~`200/I` bits each, every one well under `t`. The rule of thumb: choose interleaving depth so the worst-case Viterbi burst, divided by the depth, is comfortably under `t × m` bits.

### Worked numeric example

Take a short payload of `k_RS = 3` data symbols over GF(2^8) and an RS `(7, 3)` code (`t=2` symbol corrections). Inner convolutional code: NASA `r=1/2, k=7`. Channel: injects a 5-bit burst. Three scenarios, run in `code/main.py`:

| Scenario | Viterbi output (after inner decode) | RS input | RS result |
|---|---|---|---|
| No outer code | 2 residual bit errors in one byte | — | Frame lost (CRC fails) |
| RS, no interleaver | 5-bit burst → 1 byte error | 1 symbol error | Corrected (≤ t) |
| RS + interleaver | 5-bit burst spread → 5 single-bit errors | 5 errors across 5 words, 1 each | All corrected |

The concatenated scheme survives; the convolutional code alone does not. The crossover where concatenation pays off is when the channel's burst length exceeds the Viterbi decoder's free-distance margin — typically near Eb/N0 ≈ 4–5 dB for the NASA code at the operating point.

### Where this is deployed

| System | Inner code | Outer code | Notes |
|---|---|---|---|
| **CCSDS / Voyager** (deep space) | `r=1/2, k=7` convolutional | `(255, 223)` RS | Forney's original target; later + turbo/LDPC |
| **DVB-S / DVB-T** | Punctured convolutional | `(204, 188)` shortened RS | Shortened from (255,239); interleaver depth `I=12` |
| **DOCSIS** cable modem | Trellis-coded QAM | `(128, 122)` RS | Downstream burst protection |
| **802.11a/g** | `r=1/2, k=7` convolutional | (none — relies on CRC + ARQ) | Short frames; interleaving is per-frame, no outer RS |
| **ATSC** (US digital TV) | Trellis-coded 8-VSB | `(207, 187)` RS | ~2.5 dB gain from concatenation |

The common thread: long, bursty links get the full concatenation; short, interactive links (Wi-Fi) skip the outer RS and rely on retransmission because latency budget forbids deep interleaving.

## Build It

1. Open `code/main.py`. It implements, stdlib-only: the GF(2^8) field with the `0x11D` primitive polynomial (log/antilog tables), an RS `(7,3)` encoder/decoder, the NASA `r=1/2, k=7` convolutional encoder with generator polynomials `171`/`133` octal, a 64-state Viterbi decoder, and a depth-`I` block interleaver.
2. Run `python3 code/main.py`. The demo encodes a payload, injects a burst error, and decodes three ways: inner-only, RS-only, and concatenated. Confirm the concatenation is the only path that recovers the payload.
3. Read the printed Viterbi path metric. It rises during the burst and recovers — that rise is the residual burst the outer code must absorb.
4. Edit `BURST_LEN` to 9 bits. Watch RS-only decoding fail (one codeword exceeds `t`) while RS + interleaver still succeeds because the burst is spread across two RS words.
5. Set `BURST_LEN` to 30. Confirm both RS-only and concatenated fail — the interleaver depth is no longer large enough. Increase `INTERLEAVER_DEPTH` and re-run; the concatenation recovers.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm the inner code corrects random errors | Viterbi path metric stays near 0; output equals input | Random BER reduced by 2–3 orders of magnitude with no residual bursts |
| Confirm RS corrects a burst | All syndromes zero after Forney correction | Up to `t` symbol errors fixed; uncorrectable flag set only above `t` |
| Confirm concatenation beats either alone | Payload recovered at a burst length that breaks inner-only and RS-only | The interleaver spreads the Viterbi burst across enough RS words that none exceeds `t` |
| Diagnose a decoder failure | Non-zero syndrome + Berlekamp-Massey returns degree > t | Block flagged uncorrectable; the system requests retransmission (ARQ) or conceals the loss |
| Size the interleaver | Worst-case burst / depth ≤ t × m bits | Depth chosen so the deepest expected fade never overflows one RS word |

## Ship It

Produce one artifact under `outputs/prompt-concatenated-convolutional-and-reed-solomon.md`: a decoder runbook for a bursty satellite link. It must contain (a) the chosen RS parameters `(n, k, t)`, (b) the chosen interleaver depth with the burst-budget calculation that justifies it, (c) the printed output of `code/main.py` at three burst lengths showing where inner-only, RS-only, and concatenated each break, and (d) a one-paragraph decision rule for when to add the outer RS code versus raising Eb/N0.

## Exercises

1. The NASA convolutional code has free distance `d_free = 10`. Calculate how many random hard-decision bit errors the Viterbi decoder is guaranteed to correct per 7 input bits, and explain why that guarantee vanishes for a burst.
2. A DVB-S link uses RS `(204, 188)` shortened from `(255, 239)` with interleaver depth `I=12`. A 1000-bit rain fade arrives. Compute the number of symbol errors per RS codeword after deinterleaving and state whether decoding succeeds.
3. In `code/main.py`, disable the interleaver and inject a 7-bit burst that lands entirely inside one RS codeword. Show that RS-only fails while concatenation-with-interleaver succeeds, and explain in terms of `t`.
4. Change the RS primitive polynomial from `0x11D` to `0x11B` (the AES field) and rerun. Explain why the encoder produces *different* parity bytes but the decoder still corrects the same number of errors — both are valid GF(2^8) fields.
5. A Wi-Fi link uses the same `r=1/2, k=7` convolutional code but no outer RS. Give two concrete reasons (latency, frame size) why concatenation is not used, and name the mechanism 802.11 relies on instead.
6. Compute the overhead of the concatenated scheme RS `(255, 233)` + `r=1/2` convolutional as a fraction of the input data rate, and compare it to the overhead of the convolutional code alone. Quantify the "redundancy tax" the outer code adds.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Constraint length `k` | "the memory size" | The number of input bits (current + `k-1` previous) that affect each output; the NASA code's `k=7` gives 64 states |
| Code rate `r` | "how much it expands" | Input bits / output bits; `r=1/2` doubles the bit rate on the wire |
| Viterbi decoder | "the decoder" | Maximum-likelihood trellis search; keeps one surviving path per state and emits the lowest-metric path — but propagates errors when it locks onto a wrong path |
| Free distance `d_free` | "the code's strength" | The minimum Hamming distance between any two valid codeword sequences; corrects up to `⌊(d_free−1)/2⌋` random errors |
| Reed-Solomon `(n,k)` | "a byte code" | A block code over GF(2^m) with `n=2^m−1` symbols, `n−k=2t` parity, correcting `t=(n−k)/2` symbol errors |
| Syndrome | "error fingerprint" | `2t` field values from evaluating the received word at `α^1..α^{2t}`; zero iff the word is a valid codeword |
| Interleaver | "a shuffler" | A buffer that spreads adjacent symbols across time/codewords so a burst hits many words lightly instead of one word heavily |
| Concatenation | "two codes in a row" | Forney's 1966 scheme: outer block code (RS) + inner convolutional code, with an interleaver between, so each code's strengths cover the other's weaknesses |
| Soft decision | "analog decoding" | Passing bit *confidence* (e.g. ±0.9V) into the Viterbi metric instead of a hard 0/1; gains ~2 dB |
| Erasure | "a known-bad position" | A symbol whose location is known bad (e.g. a scratch); RS corrects `2t` erasures versus `t` unknown errors |

## Further Reading

- **Forney, G. D.** — *Concatenated Codes*, MIT Press, 1966 (the original concatenation result).
- **CCSDS 131.0-B-3** — TM Synchronization and Channel Coding (the deep-space RS `(255, 223)` + `r=1/2, k=7` standard used by Voyager and later missions).
- **ETSI EN 300 421** — DVB-S framing, channel coding and modulation (RS `(204, 188)` + punctured convolutional, interleaver depth 12).
- **ETSI EN 300 744** — DVB-T framing, channel coding and modulation.
- **Viterbi, A. J.** — "Error Bounds for Convolutional Codes and an Asymptotically Optimum Decoding Algorithm," *IEEE Trans. IT*, 1967.
- **Reed & Solomon** — "Polynomial Codes over Certain Finite Fields," *J. SIAM*, 1960.
- **Massey, J. L.** — "Shift-Register Synthesis and BCH Decoding," *IEEE Trans. IT*, 1969 (the Berlekamp-Massey algorithm).
- **Wicker & Bhargava**, *Reed-Solomon Codes and Their Applications*, IEEE Press, 1994.
- **Tanenbaum & Wetherall**, *Computer Networks*, 5th ed., Section 3.2.1 (Error-Correcting Codes).
