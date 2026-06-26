# Viterbi decoding of convolutional codes

> The **NASA standard convolutional code** — rate 1/2, constraint length K=7, generator polynomials 171/133 (octal), first flown on the 1977 Voyager mission — is the textbook example of a code that is *not* a block code: each input bit is XOR-ed with the previous six input bits held in a shift register, producing two output bits per step, so the encoded stream has no natural message boundary and the encoder carries memory. It is reused today inside 802.11 OFDM PLCP service-data fields and in satellite links. Decoding asks a different question than CRC parity checking: instead of *did an error happen*, it asks *which input bit sequence most likely produced this noisy stream* — a maximum-likelihood sequence estimation. For small K, the **Viterbi algorithm** (Forney, 1973) answers exactly that by walking a **trellis** of 2^(K−1) = 64 states, keeping for every state only the single surviving path with the fewest disagreements (the **path metric**); all other paths into that state are discarded because they can never catch up. Hard-decision decoding compares bit-for-bit via Hamming distance; **soft-decision decoding** keeps the analog level and sums squared errors, buying roughly 2 dB of coding gain. The classic failure mode is an **error burst** longer than the code's free distance (10 for this code), which is why real links concatenate an outer Reed-Solomon code to mop up the bursts. This lesson builds the encoder and a hard-decision Viterbi decoder in pure Python and watches it correct three scattered bit errors in a coded frame.

**Type:** Build
**Languages:** Python
**Prerequisites:** Error detection vs. correction (Hamming distance, parity, CRC), binary arithmetic and XOR, the data-link layer framing context from chapter 3.2
**Time:** ~85 minutes

## Learning Objectives

- Encode an arbitrary bit stream with the NASA rate-1/2, K=7 convolutional code and predict each output pair from the generator polynomials and the current shift-register state.
- Draw the 64-state trellis for this code and explain why only 2^(K−1) states are needed when the constraint length is K.
- Execute the Viterbi algorithm by hand for a short received sequence: compute branch metrics, keep survivor paths, and backtrack to recover the most likely input.
- Distinguish hard-decision from soft-decision decoding and quantify the ~2 dB coding gain soft decision buys, given a worked signal-to-noise example.
- Explain why a zero-tail of K−1 bits is appended to flush the encoder back to the all-zero state, and why that lets the decoder force termination in state 0.
- Identify the free distance d_free = 10 of the NASA code and explain why an error burst longer than ⌊(d_free−1)/2⌋ cannot be guaranteed correctable, motivating concatenation with Reed-Solomon.

## The Problem

A low-power Wi-Fi station in a warehouse is sending 802.11a OFDM frames to an access point 40 meters away. The BPSK-modulated signal arrives at roughly 4 dB above the noise floor — strong enough to read most bits, but not strong enough that every bit is right. A single flipped bit in the PLCP SERVICE field corrupts the whole frame's length and rate signalling, so the AP drops the frame and the station backs off and retransmits, eating airtime.

A parity check (CRC-32 in the 802.11 FCS) can tell the receiver that *something* is wrong, but it cannot say *which* bit, and it cannot ask the channel for a retransmission that will arrive any cleaner. What the receiver needs is a code that adds structured redundancy so the most likely original bit sequence can be *reconstructed* from a noisy version, up to a bounded number of errors, without a round trip. That is forward error correction, and convolutional codes with Viterbi decoding are the classical answer at the physical layer — the same machinery Voyager used to return pictures from Jupiter in 1979.

## The Concept

### Convolutional codes: memory, rate, and constraint length

A block code (Hamming, Reed-Solomon) chops data into fixed-size words and maps each word independently to a longer codeword. A **convolutional code** instead treats the input as a continuous bit stream: each input bit is convolved with the previous bits through a shift register. There is no natural message boundary, and the output at time *t* depends on the input at times *t, t−1, …, t−(K−1)*.

| Parameter | Meaning | NASA code value |
|---|---|---|
| Rate **r** | input bits → output bits per step | 1/2 (one bit in, two out) |
| Constraint length **K** | span of input bits that affect a given output | 7 (one current + six stored) |

Because 1 input bit makes 2 output bits, the code rate is 1/2 — the frame on the wire is twice as long as the payload. It is **not systematic**: neither output bit is simply a copy of the input bit, so the receiver must always decode.

### The NASA encoder, generator polynomials, and a worked step

The encoder holds the last K−1 = 6 input bits in a shift register. For each new input bit *b*, it computes two output bits as the parity (XOR) of selected taps:

- **Output 0** taps `1111001` binary = `171` octal — the current bit plus registers 1,2,3,6.
- **Output 1** taps `1011011` binary = `133` octal — the current bit plus registers 2,3,5,6.

The textbook's Fig. 3-7 draws exactly this; `code/main.py` implements it in `encode()`. Worked example, starting from the all-zero register and feeding `1, 1, 1`:

| Step | Input | Register after shift | Window (b,s1..s6) | Output 0 (171) | Output 1 (133) |
|---|---|---|---|---|---|
| 1 | 1 | 100000 | 1100000 | 1 | 1 |
| 2 | 1 | 110000 | 1110000 | 1 | 0 |
| 3 | 1 | 111000 | 1111000 | 0 | 1 |

So input `111` produces output `11 10 01` — matching the textbook's worked example. It takes seven shifts to flush a single input bit completely out of the register, which is why the constraint length is K = 7.

### The trellis: states, branches, and outputs

To decode, view the encoder as a finite-state machine. The state is the content of the six memory registers — 2^6 = **64 states**. From each state there are exactly two outgoing branches, one for input 0 and one for input 1; each branch leads to a deterministic next state and emits a deterministic output pair. Unrolling these transitions over time gives the **trellis diagram** (see `assets/viterbi-decoding-of-convolutional-codes.svg`).

| Element | Meaning |
|---|---|
| Node (state, time) | A possible register content at step *t* |
| Branch | A legal (input, output) transition between two states |
| Branch metric | Cost of that transition versus the received pair |
| Path metric | Sum of branch metrics along a path through the trellis |
| Survivor | The single lowest-metric path retained at each state |

Because the register shifts one bit at a time, each state has exactly two predecessors — the **butterfly** structure that makes Viterbi cheap: O(K·2^(K−1)) work per step.

### The Viterbi algorithm: keep the survivor, drop the rest

The decoder's job is **maximum-likelihood sequence estimation**: find the input sequence most likely to have produced the noisy received stream. Viterbi does this exactly by exploiting the Markov structure of the trellis.

At each time step, for each state, every incoming branch proposes a candidate path metric = (predecessor's surviving metric) + (branch metric). The algorithm keeps only the **minimum-cost candidate** as that state's survivor and discards the rest — a discarded path can never catch up later, because all future branch metrics are added equally to both competitors and the loser stays behind by at least its current deficit.

The hard-decision branch metric (used in `code/main.py`) is the **Hamming distance** between the expected output pair and the received pair: 0, 1, or 2. At the end of the stream, the decoder picks the lowest-metric terminal state and **backtracks** through stored back-pointers to read off the input bits in reverse.

### Worked numeric decode on a K=3 toy code

To make the mechanics concrete, consider a smaller code with K=3, generators G0=`111`, G1=`101`, giving 4 states. The trellis (printed by `code/main.py`) is:

| State | in=0 → (next, out) | in=1 → (next, out) |
|---|---|---|
| 00 | (00, 00) | (10, 11) |
| 01 | (00, 11) | (10, 00) |
| 10 | (01, 10) | (11, 01) |
| 11 | (01, 01) | (11, 10) |

Encode input `1 1 0 1` from state 00: outputs are `11 01 01 00`. Now suppose the channel flips one bit and the receiver gets `11 01 00 00` (third pair corrupted from `01` to `00`). Viterbi, starting from state 00, walks all four steps keeping survivors; the surviving path at termination has metric 1 and backtracks to input `1 1 0 1` — the single error is corrected. The full NASA K=7 decoder in `code/main.py` does the same on 64 states and corrects three scattered errors in a coded "NET" frame.

### Soft-decision decoding and coding gain

Hard decision first slices each received voltage to a 0/1 (e.g. −0.1 V → 0, +0.9 V → 1) and only then measures Hamming distance. That throws away confidence: −0.1 V and +0.9 V are both "decided", but +0.9 V is far more trustworthy.

**Soft-decision decoding** keeps the analog level and uses a metric proportional to squared error: if the expected symbol is ±1 and the received voltage is *v*, the branch cost is *(v − expected)²*. A sample at +0.9 V against expected +1 contributes 0.01, while a sample at −0.1 V against expected −1 contributes 0.81 — the decoder can prefer the path that explains the strong sample even if the weak one disagrees. Soft decision typically buys **about 2 dB** of coding gain over hard decision on an AWGN channel, which is why every real 802.11 / satellite receiver uses it. The cost is wider datapaths (3- or 4-bit soft samples instead of 1-bit hard decisions) and a multiply instead of an XOR.

### Free distance, error bursts, and concatenation with Reed-Solomon

The **free distance** d_free of a convolutional code is the minimum Hamming distance between any two distinct infinitely long codewords — the smallest error pattern that can fool the decoder. For the NASA K=7 code, d_free = 10, so hard-decision Viterbi can guarantee correction of up to **⌊(d_free−1)/2⌋ = 4** random errors in a decoding window.

The catch is *random*. Viterbi corrects isolated errors beautifully but degrades sharply on **burst errors** — several errors in a row — because a long burst looks like a legal alternative codeword over that span. The textbook's remedy is concatenation: put a Reed-Solomon outer code (e.g. (255, 233) over 8-bit symbols, correcting up to 16 symbol = 128-bit bursts) around the inner convolutional code. The convolutional code handles isolated errors and passes its occasional burst failures up to Reed-Solomon, which is built for exactly that. Voyager, DVB-S, and WiMAX all use this concatenated arrangement; modern standards (DVB-S2, 5G) have largely moved to LDPC and turbo codes, but the Viterbi/Reed-Solomon tandem is still the cleanest pedagogical example of why inner and outer codes play different roles.

## Build It

1. Open `code/main.py` and read the encoder in `encode()`. Confirm the generator masks `G0 = 0o171` and `G1 = 0o133` match the textbook's Fig. 3-7 tap pattern.
2. Run `python3 code/main.py`. The clean-channel block should print `Path metric: 0` and `Decoded info: 'NET'` — a round trip with zero disagreement.
3. Read `build_trellis()`: it precomputes, for every one of the 64 states and each input bit, the next state and expected output pair. Verify that the state count is 2^(K−1) = 64, not 2^K.
4. Read `viterbi_decode()`: the `dp` array holds one survivor per state; `history` snapshots let it backtrack at the end. Note the all-zero start assumption and the forced termination in state 0 (the zero tail).
5. The error-injection block flips the first bit of pairs 3, 11, and 19. Run it and confirm the decoder still recovers `'NET'` with path metric 3 — three errors corrected.
6. Increase the corrupted indices to four consecutive pairs (a burst) and rerun. Observe the decoded string breaking — that is the burst-error failure mode that motivates an outer Reed-Solomon code.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify the encoder | Output pairs for input `111` are `11 10 01` | Matches the textbook's worked example exactly |
| Confirm a clean round trip | Clean-channel path metric = 0, decoded = original | No disagreement means the trellis and encoder share one convention |
| Demonstrate error correction | 3 scattered bit errors, decoded string still correct | Path metric = number of injected errors; survivors absorbed them |
| Spot a burst failure | 4+ consecutive corrupted pairs, decoded string wrong | Long burst exceeds the correction radius; argues for Reed-Solomon |
| Justify soft decision | Per-sample squared-error metric replaces Hamming | A strong sample outweighs a weak one; ~2 dB gain expected |
| Read the trellis | Each state has exactly 2 predecessors and 2 successors | Butterfly structure; O(K·2^(K−1)) work per step |

## Ship It

Produce one artifact under `outputs/` — see `outputs/prompt-viterbi-decoding-of-convolutional-codes.md` for the brief. Annotate the printed trace from `code/main.py` with:

- The encoder output for input `111` and a hand-check of each output pair against the 171/133 taps.
- A survivor-table snapshot for the first three steps of the toy K=3 decode, showing which path was discarded at each state and why.
- The path metric before and after injecting three errors, with the corrupted pair indices called out.
- A one-paragraph argument, grounded in d_free = 10, for why a 5-error burst is not guaranteed correctable and what an outer (255, 233) Reed-Solomon code adds.

## Exercises

1. Using the NASA 171/133 taps and a starting register of all zeros, hand-encode the input sequence `1 0 1 1 0 0 1` and write out the 14 output bits. Verify your answer against `encode()` in `code/main.py`.
2. The decoder in `code/main.py` assumes the encoder started in state 0. Modify the demo to start the encoder in a non-zero state and explain why the decoder now fails on a clean channel — then describe the two standard fixes (zero-tail flushing or training the decoder on an initial state).
3. Inject four errors into *consecutive* pairs (a burst) and rerun. Report the decoded string, the path metric, and whether the result is correct. Then inject the same four errors scattered across the frame and compare — what does this tell you about Viterbi's burst sensitivity?
4. The free distance of the NASA K=7 code is 10. State the maximum number of random errors the hard-decision decoder can guarantee to correct, and show the calculation. Then explain why doubling the constraint length to K=9 (used in DVB-S) raises d_free to 12 and what that costs in decoder complexity.
5. Replace the hard Hamming branch metric with a soft-decision squared-error metric that accepts float voltages in [−1, +1] (expected symbols ±1). Re-run the demo feeding slightly noisy samples and confirm the decoder still recovers the message. Quantify the margin in dB between the weakest correctable soft sample and the weakest correctable hard sample.
6. A concatenated Voyager-style link uses the NASA K=7 convolutional inner code and a (255, 223) Reed-Solomon outer code over 8-bit symbols. Compute how many symbol errors the outer code corrects, convert that to a maximum correctable bit burst, and explain why this combination handles both isolated and burst errors better than either code alone.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Convolutional code | "a stream code" | An error-correcting code where each output bit is the XOR of the current and previous K−1 input bits through a shift register; no fixed block boundary |
| Constraint length K | "the memory" | The number of input bits (current + stored) that influence a given output; the NASA code has K=7, so 6 registers |
| Code rate r | "the overhead" | Output bits per input bit; r=1/2 means the coded stream is twice as long as the payload |
| Generator polynomial | "the taps" | An octal mask (171, 133 for NASA) specifying which register positions are XOR-ed into each output bit |
| Trellis | "the diagram" | The unrolled state machine: 2^(K−1) states per time step, two branches out of each, showing every legal (input, output) transition |
| Survivor | "the kept path" | At each state, the single lowest-metric path retained; all competing paths into that state are discarded and can never win |
| Path metric | "the score" | Cumulative cost of a path through the trellis; the decoder minimises it over all paths |
| Hard-decision decoding | "1-bit decoding" | Slice each sample to 0/1 first, then use Hamming distance; throws away confidence |
| Soft-decision decoding | "analog decoding" | Keep the sample voltage and use a squared-error metric; buys ~2 dB of coding gain |
| Free distance d_free | "the code's strength" | Minimum Hamming distance between any two distinct codewords; the smallest error pattern that can fool the decoder (10 for the NASA code) |
| Zero tail | "the flush bits" | K−1 zero bits appended to the input to drive the encoder back to state 0 so the decoder can force termination |

## Further Reading

- **IEEE Std 802.11-2020**, Clause 21 (OFDM PLCP) — the convolutional encoder (rate 1/2, K=7, 171/133) used in 802.11a/g.
- **CCSDS 131.0-B-3** — TM Synchronization and Channel Coding; specifies the NASA/Voyager convolutional code and concatenated Reed-Solomon for space links.
- **Forney, G. D. Jr.**, "The Viterbi Algorithm," *Proceedings of the IEEE*, vol. 61, no. 3, pp. 268–278, March 1973 — the canonical exposition.
- **Viterbi, A. J.**, "Error Bounds for Convolutional Codes and an Asymptotically Optimum Decoding Algorithm," *IEEE Trans. Information Theory*, IT-13, pp. 260–269, 1967.
- **ETSI EN 300 421** (DVB-S) — concatenated Reed-Solomon (204, 188) outer with convolutional inner, the textbook concatenated arrangement.
- **Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 3, Section 3.2.1** — the source treatment of convolutional codes, Viterbi, soft decision, and Reed-Solomon concatenation.
- **Lin & Costello, *Error Control Coding*, 2nd ed., Prentice Hall, 2004** — Chapters 11–12 on convolutional codes and the Viterbi algorithm in depth.
