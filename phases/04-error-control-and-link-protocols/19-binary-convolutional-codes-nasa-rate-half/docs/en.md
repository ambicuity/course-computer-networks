# Binary convolutional codes: the NASA rate-1/2 k=7 code

> The **NASA rate-1/2, constraint length k=7 binary convolutional code** is the only non-block code the chapter covers, and it shipped: it flew on the **Voyager** probes from 1977 and was reused inside **IEEE 802.11a/g** OFDM PLCP payloads and **CCSDS** deep-space links. The encoder is a 6-stage shift register — each input bit produces two output bits, each a **mod-2 XOR** of a fixed subset of the current input plus the six stored bits. Two bits out per bit in gives **rate 1/2**; an input bit influences the output for **seven shifts** before flushing, giving **constraint length k=7**. Decoding is **maximum-likelihood sequence estimation** via the **Viterbi algorithm**: the decoder walks a **trellis** of 2^6 = 64 states, keeping one survivor per state with the smallest accumulated **Hamming distance** (hard decision) or squared-Euclidean distance (**soft decision**, where the demodulator passes analog confidence like +0.9V / −0.1V instead of hard 1/0). The dominant failure is an **error burst** longer than the free distance, which 802.11 patches with an interleaver and optionally a **Reed-Solomon** stage. This lesson builds a runnable k=7 encoder and a hard-decision Viterbi decoder in `code/main.py`.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Hamming codes and Hamming distance (earlier Phase 4 lesson), mod-2 arithmetic, basic FSM/trellis intuition
**Time:** ~85 minutes

## Learning Objectives

- Encode a bit stream with the NASA k=7 rate-1/2 convolutional coder and predict the two output bits for a given register state.
- Draw the 64-state trellis and explain why only 2^(k−1) states are needed even though k=7.
- Run a hard-decision Viterbi decoder on a noisy codeword and recover the message, accounting for the k−1 flush tail bits.
- Distinguish hard- from soft-decision decoding and quantify the ~2 dB coding gain soft decisions add on an AWGN channel.
- Explain why 802.11 and CCSDS concatenate/interleave a Reed-Solomon stage around the convolutional code, and identify the burst-error failure this defeats.
- Read a Viterbi trace and identify survivor paths, path-metric accumulation, and the instant a wrong survivor is discarded.

## The Problem

A low-earth-orbit telemetry link sends a 512-byte status frame to a ground station. At the chosen Eb/N0 the raw bit-error rate is around 10^−2 — one bit in a hundred is flipped by thermal noise — so the frame arrives with about 40 scattered errors. A pure CRC can *detect* the damage, but recovery is retransmission, and the round-trip time to a fast-moving satellite plus downlink contention makes that expensive. On a deep-space probe the link is one-way for hours — retransmission is not an option at all. You need a code that *corrects* errors in place, works on a continuous stream rather than fixed blocks, and lets the receiver exploit the analog confidence of each demodulated symbol. The NASA k=7 rate-1/2 convolutional code plus a Viterbi decoder is the textbook answer — the same machinery 802.11a/g uses inside every Wi-Fi OFDM frame.

## The Concept

### Why a convolutional code is not a block code

A block code (Hamming, Reed-Solomon) computes *r* check bits from *m* message bits alone and emits an *n*-bit codeword with a hard boundary. A convolutional code has **no natural message boundary**: the encoder is a clocked shift register whose outputs depend on the *current* input plus *previous* inputs still in the register — the output is a convolution of the input stream with the generator impulse response, hence the name. The number of previous bits the output depends on is the **constraint length k**; for the NASA code k=7. A code is described by its **rate** R = (input bits per step) / (output bits per step) and its constraint length: the NASA code is R = 1/2, k = 7.

### The encoder: generator polynomials g1 and g2

The encoder holds **k−1 = 6** memory bits in a shift register. At each step a new input bit *u* enters from the left, the register shifts right, and two output bits are computed as XOR sums over tapped positions.

| Output | Generator (octal) | Taps (current input + register stages) |
|---|---|---|
| Output bit 1 (P1) | **171₈** | input + s2, s3, s5, s6 |
| Output bit 2 (P2) | **133₈** | input + s1, s4, s6 |

The octal generators 171 and 133 are the canonical CCSDS/NASA taps; every textbook figure of "the" convolutional code in 802.11 shows exactly these. Every output bit is a linear (XOR) function of bits, so the code is **binary and linear**; no output bit equals the raw input, so it is **non-systematic**.

Worked example, all-zero state, input `1 1 1` (the textbook's Fig. 3-7 trace):

| Step | Input | Register after shift | P1 | P2 | Emitted pair |
|---|---|---|---|---|---|
| 1 | 1 | 1 0 0 0 0 0 | 1 | 1 | `1 1` |
| 2 | 1 | 1 1 0 0 0 0 | 0 | 1 | `0 1` |
| 3 | 1 | 1 1 1 0 0 0 | 1 | 0 | `1 0` |

This matches the textbook: input `111` from state `000000` produces `11`, `01`, then `10` as the third shift completes. See `code/main.py` `encode()` for the tap walk and `assets/binary-convolutional-codes-nasa-rate-half.svg` for the register diagram.

### Trellis, states, and branches

The encoder is a Mealy machine with **2^(k−1) = 64** states (the 6-bit register contents). From every state there are two outgoing branches (input 0 or 1), each labeled with the 2-bit output pair it produces and landing on a deterministic next state. Unrolling this FSM gives the **trellis** — a layered graph where each layer holds 64 nodes and 128 edges. Any valid codeword is a single path through it, and any path corresponds to exactly one input sequence. So decoding becomes "find the trellis path whose labeled outputs are closest to what we received" — maximum-likelihood sequence estimation, which Viterbi solves in time linear in the message length and constant (128 additions/comparisons) per step.

### The Viterbi algorithm: survivors and path metrics

At each trellis layer, for each of the 64 states, the decoder keeps exactly one **survivor path** — the input sequence ending at that state whose emitted outputs differ from the received word in the fewest positions. That count is the **path metric** (Hamming distance for hard decisions). For each state *s* at layer *t+1*: examine the two predecessors *p0* (input 0) and *p1* (input 1) that can reach *s*; candidate = survivor_metric(p) + branch_metric, where branch_metric is the Hamming distance between the branch's 2-bit label and the 2 received bits; keep the predecessor with the smaller candidate, record a back-pointer, and discard the other. At the end the smallest-metric state yields the decoded path; following back-pointers recovers the most likely input bit stream. The textbook states it precisely: the algorithm "walks the observed sequence, keeping for each step and for each possible internal state the input sequence that would have produced the observed sequence with the fewest errors."

### Hard vs soft decision: the 2 dB gift

A hard-decision receiver quantizes each demodulated symbol to 0 or 1 *before* decoding, discarding analog confidence. If the channel delivers +0.9V (clearly 1) and −0.1V (almost 0), hard decision records `1 0` and treats both equally. A **soft-decision** Viterbi decoder feeds the raw analog values (or a few-bit quantization) into the branch metric: squared-Euclidean distance replaces Hamming distance, so a confident symbol sways the path more than an ambiguous one. On an AWGN channel, 3-bit soft quantization gives roughly **2 to 2.5 dB** of extra coding gain over hard decision — nearly doubling transmitter power for free. The textbook's example (−1V = 0, +1V = 1, receiving 0.9V, −0.1V) is exactly this idea.

### Tail bits, termination, and the free distance

To make the decoder know where the path ends, the encoder is **terminated**: after the last message bit the sender clocks in **k−1 = 6** zero "tail bits" to flush the register to the all-zero state. The receiver decodes (message + 6) input bits and drops the 6 tail bits — this termination makes 802.11 frames self-contained. The code's strength is captured by its **free distance d_free** — the minimum Hamming distance between any two distinct codewords. For the NASA k=7 code, d_free = 10, so a hard-decision Viterbi decoder corrects up to ⌊(d_free−1)/2⌋ = **4 random errors** in a decoded span. Beyond that, survivor confusion and the **error burst** failure take over: errors close in time can drag the decoder off the correct path for many bits before it recovers.

### Concatenation and interleaving in 802.11 and deep space

Because a convolutional decoder struggles with bursts, real systems never run it naked. **Interleaving** (802.11a/g): encoded bits are permuted across OFDM subcarriers so a narrowband fade (a burst) lands as isolated single-bit errors at the decoder. The 802.11 PLCP uses the same k=7, R=1/2 generators (171, 133), with puncturing to reach 2/3 or 3/4. **Concatenation with Reed-Solomon** (CCSDS, DVB-S): an outer RS code corrects symbol errors, the inner convolutional code plus Viterbi handles random noise, and an interleaver between them spreads residual bursts. The textbook: "Reed-Solomon decoding can mop up the residual errors within the convolutional code."

### Puncturing: trading correction for rate

R=1/2 doubles the bandwidth needed. To reclaim it, 802.11 **punctures** the encoder output — systematically deleting some output bits per a pattern (e.g. delete one P2 bit per two inputs → R=2/3) and the receiver marks those positions erased (soft 0, no metric contribution). The same k=7 encoder thus supports 6–54 Mbit/s OFDM rates in 802.11a/g.

## Build It

1. Open `code/main.py`. The `NASAConvolutionalCode` class encodes taps 171₈/133₈ as masks; `encode()` walks the input bit-by-bit, shifts the 6-bit register, and XORs the tapped bits into each P1/P2 pair.
2. Run `python3 code/main.py`. The demo encodes a 16-bit message, appends 6 tail bits, injects controlled errors, then `viterbi_decode()` prints the recovered message against the original.
3. Read the Viterbi loop: each step computes the 64 survivor metrics via `min over predecessors of (prev_metric + branch_hamming)`, stores back-pointers, and traces back from the terminating state 0.
4. Crank injected errors from 3 to 6: at 4 you still recover (d_free=10); at 6 the first decode failure — the burst/overload mode.
5. The worked trace at the top: `1 1 1` from state 0 emits `11, 01, 10`, matching the textbook figure.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm encoding matches the textbook | Input `111` from state 0 emits `11 01 10` | Output pairs match Fig. 3-7 exactly |
| Verify random-error correction | Inject 3 flips; recovered message equals original | Terminal-state path metric equals the error count |
| Find the correction cliff | Increase errors until decode fails | Failure at ~5+ errors per span, consistent with d_free=10 |
| Justify soft decision | Decode the same noisy frame hard vs soft | Soft recovers a frame hard loses; ~2 dB margin |
| Diagnose a burst failure | Inject 6 errors in consecutive pairs | Decoder diverges for many bits before re-locking |
| Explain 802.11 puncturing | Trace which P2 bits are deleted for R=2/3 | Receiver marks erased positions as soft-0 |

## Ship It

Produce one artifact under `outputs/prompt-binary-convolutional-codes-nasa-rate-half.md`: an annotated encoder trace for a 24-bit message (register state, input bit, P1, P2, emitted pair per step, plus the 6 tail-bit flush); a Viterbi survivor trace for the same message with 3 injected errors showing the correct survivor's metric vs the runner-up at the divergence/merge step; and a one-page decision card for NASA k=7 vs Reed-Solomon vs LDPC keyed to channel type (AWGN vs burst), latency budget, and required rate. Start from the printed output of `code/main.py`.

## Exercises

1. Encode `1 0 1 1 0 0 1 0` from the all-zero state by hand and verify against `code/main.py`. How many output bits precede the 6 tail bits, and what is the total codeword length?
2. The code has d_free = 10. How many *random* hard errors can it correct, and how many can it detect but not correct? Inject 5 errors in the demo — what happens, and why is the answer not "5 is corrected"?
3. A receiver gets soft values `+0.9, −0.1, +0.8, −0.9` for one trellis step. Compute the hard-decision (Hamming) and soft-decision (squared-Euclidean) branch metrics against a branch labeled `1 1 0 0`. Why does soft decision down-weight the ambiguous `−0.1` symbol?
4. You must transmit at R = 2/3. Describe the puncturing pattern that deletes one P2 bit per two input bits, and explain how the Viterbi decoder treats the deleted positions.
5. A deep-space link suffers a 12-bit burst fade. Why will the bare convolutional decoder fail, and what interleaver + outer Reed-Solomon stage (RS symbol size, interleaving depth) would recover the frame?
6. Contrast the k=7 NASA code with LDPC (802.11n/ac/ax). Give two reasons modern Wi-Fi moved to LDPC, and one scenario where the convolutional code is still preferable.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Constraint length (k) | "the memory" | Input bits (current + stored) that affect each output; k=7 → 6 register bits |
| Code rate (R) | "how much overhead" | Input bits per output bit; R=1/2 → two channel bits carry one information bit |
| Generator (g1=171₈, g2=133₈) | "the taps" | Octal masks selecting which register positions are XORed into each output bit |
| Trellis | "the diagram" | Unrolled FSM: 64 states per step, two branches out of each; every codeword is one path through it |
| Survivor / path metric | "the best guess" | Per state, the surviving input sequence and its accumulated Hamming (or Euclidean) distance to the received word |
| Viterbi algorithm | "the decoder" | Maximum-likelihood sequence estimation that prunes all but one survivor per state per step |
| Soft decision | "analog decoding" | Feeding demodulator confidence (not just 0/1) into the branch metric; ~2 dB gain on AWGN |
| Tail bits | "extra zeros" | k−1 zero bits appended to flush the register to state 0 so the decoder knows the path end |
| Free distance (d_free) | "the strength" | Min Hamming distance between any two codewords; =10 for the NASA code, so it corrects ⌊9/2⌋=4 errors |
| Puncturing | "dropping bits for speed" | Deleting encoder outputs (marked erased at the receiver) to raise R above 1/2 |
| Concatenation | "two codes stacked" | Outer RS + inner convolutional code with an interleaver; RS mops up residual bursts |

- **CCSDS 131.0-B-3** — TM Synchronization and Channel Coding; specifies the NASA k=7, R=1/2 code (generators 171, 133) for deep-space telemetry.
- **IEEE Std 802.11-2020**, Annex F — OFDM PLCP: the convolutional encoder, puncturing patterns for R = 1/2, 2/3, 3/4, and the interleaver.
- **J. G. Proakis, *Digital Communications***, 5th ed., Chapter 7 — convolutional codes, Viterbi decoding, and soft-decision coding gain.
- **A. J. Viterbi**, "Error bounds for convolutional codes and an asymptotically optimum decoding algorithm," IEEE Trans. Inf. Theory, IT-13, 1967 — the original algorithm.
- **G. D. Forney**, "The Viterbi algorithm," Proc. IEEE 61(3), 1973 — the canonical exposition.
- **S. Lin & D. J. Costello, *Error Control Coding***, 2nd ed., Chapters 11–12 — state diagrams, trellis, free distance bounds, concatenated coding.
- Tanenbaum, Feamster & Wetherall, *Computer Networks*, 6th ed., Section 3.2.1 (Error-Correcting Codes) — the textbook basis for this lesson.
