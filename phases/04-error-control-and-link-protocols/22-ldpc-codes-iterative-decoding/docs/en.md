# LDPC codes and iterative belief-propagation decoding

> LDPC (Low-Density Parity-Check) codes are linear block codes whose parity-check matrix **H** is *sparse* — each of the *n* codeword bits participates in only a few parity checks, and each of the *m* checks involves only a few bits. This sparsity is what makes them decodable: instead of solving an intractable nearest-codeword search, the receiver runs **iterative belief propagation** (the sum-product algorithm) on a **Tanner graph** with *bit nodes* (one per codeword bit) and *check nodes* (one per parity equation), passing log-likelihood ratios back and forth along edges until all checks are satisfied or an iteration cap is hit. Invented by Gallager in 1962, ignored for 30 years, and revived in 1995 once silicon caught up, LDPC codes now sit in **DVB-S2/S2X** (EN 302 307), **10GBASE-T** Ethernet (IEEE 802.3an, a 2048-byte-block quasi-cyclic LDPC), **802.11n/ac/ax** Wi-Fi (per-code-word LDPC optional, block lengths 648–1944 bits), **ITU-T G.hn** powerline, and **5G NR** data channels (3GPP TS 38.212, two base graphs BG1/BG2 with quasi-cyclic structure). They approach the Shannon limit to within fractions of a dB and — unlike turbo codes — decode in parallel, which is why 10 Gbps and beyond prefer them. The failure mode is the **error floor**: after a sharp waterfall drop, the BER curve flattens around 10⁻⁷–10⁻⁸ because of low-weight (trapping-set) structures in the graph, which is why standards designers agonize over the specific H matrices. This lesson builds a real (7,4) Hamming-equivalent parity-check matrix, encodes with it, injects errors, and decodes with a sum-product BP loop you can watch converge — or stall.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Hamming codes and parity (Phase 4 lesson on error-detecting codes), linear algebra over GF(2), basic probability and log-likelihood ratios
**Time:** ~85 minutes

## Learning Objectives

- Read a parity-check matrix **H** and draw the corresponding **Tanner graph**, distinguishing bit (variable) nodes from check nodes and naming the edges.
- Encode a message word into a codeword by solving Hcᵀ = 0 over GF(2), and verify the syndrome of a received word.
- Run one full iteration of **sum-product belief propagation**: compute bit-to-check messages (π), check-to-bit messages (λ), and update bit LLRs from channel evidence.
- Explain why LDPC decoding parallelizes and why that matters at 10 Gbps, in contrast to the sequential Viterbi trellis.
- Identify the **waterfall**, **error floor**, and **trapping set** regions on a BER-vs-SNR curve and tie each to a property of **H**.
- Map LDPC to its deployed standards: DVB-S2, 802.11n/ac/ax, 802.3an, ITU-T G.hn, and 5G NR TS 38.212 base graphs.

## The Problem

A satellite uplink runs at E_s/N_0 = 1.5 dB. A (255,223) Reed-Solomon outer code plus a rate-1/2 convolutional inner code (the classic DVB-S stack) needs the link to sit closer to 3 dB to hold a 10⁻⁵ output BER, so the operator must either crank up transmit power — shortening transponder lifetime and costing uplink rent — or accept visible artifacts in the digital TV stream. A modern DVB-S2 receiver using a rate-1/2 LDPC code plus a small BCH outer code holds the same BER at roughly 1.0 dB. That 2 dB margin is the difference between a viable service and one that rain-fades twice an hour.

The engineer's question: how does a code whose only structure is "a big sparse matrix of XOR equations" get that close to the Shannon limit, and why does decoding not blow up combinatorially? The answer is belief propagation on the Tanner graph — a local, iterative, parallelizable message-passing scheme that exploits exactly the sparsity Gallager designed in 1962.

## The Concept

### Block codes, codewords, and the parity-check matrix

A linear block code takes *k* message bits and produces *n* codeword bits (n = k + r). It is fully described either by a generator matrix **G** (k×n, used to encode: c = mG) or by a parity-check matrix **H** (r×n, used to check: a word c is valid iff Hcᵀ = 0 over GF(2)). The two are equivalent descriptions: the rows of G span the null space of H. The code rate is R = k/n.

LDPC codes are defined by an **H** that is sparse: a tiny, fixed number of 1s per row (row weight w_c) and per column (column weight w_r). A *regular* (n, w_c, w_r) LDPC code has exactly w_r ones per column and w_c per row, with rate R ≈ 1 − w_c/w_r. The (7,4,3) Hamming code is a tiny regular LDPC-like object — H is 3×7 with column weight 3 — and we use it in `code/main.py` because it is small enough to watch by hand:

```
        c1 c2 c3 c4 c5 c6 c7
H  =  [  1  1  1  0  1  0  0 ]   row 1 (check p1)
       [  1  1  0  1  0  1  0 ]   row 2 (check p2)
       [  1  0  1  1  0  0  1 ]   row 3 (check p3)
```

Each row is one even-parity equation; each column says which checks that bit participates in. The syndrome s = Hrᵀ of a received word r is zero iff no error occurred, and nonzero otherwise.

### The Tanner graph: bits and checks as a bipartite graph

The H matrix is also a **bipartite graph** — the **Tanner graph**. One part has *n* **variable (bit) nodes**, one per codeword bit; the other has *r* **check nodes**, one per row of H. An edge connects bit node *i* to check node *j* iff H[j,i] = 1. For the 7,4 Hamming H above, bit c1 touches all three checks; c2 touches checks 1 and 2; c5 touches only check 1. The graph is what makes decoding local: a check node only ever talks to the bits in its row, and a bit node only ever talks to the checks in its column. Sparsity of H = bounded degree of the Tanner graph = bounded work per message. See `assets/ldpc-codes-iterative-decoding.svg` for the full 7-node Tanner graph with the three check nodes and the bit-to-check edges.

| H property | Tanner-graph meaning | Decoding consequence |
|---|---|---|
| Row weight w_c (ones per row) | degree of each check node | each check update touches w_c bits |
| Column weight w_r (ones per column) | degree of each bit node | each bit update touches w_r checks |
| Sparsity (w_c, w_r ≪ n) | bounded-degree graph | messages are cheap, parallelizable |
| Low-weight codewords | short cycles / trapping sets | error floor at high SNR |
| 4-cycles in graph | check pairs share 2 bits | weakens BP independence assumption |

### Channel evidence and log-likelihood ratios

BP operates on **soft information**. For an additive white Gaussian noise (AWGN) channel transmitting ±1 symbols (BPSK), the receiver samples y = x + n where x ∈ {−1, +1} and n ~ N(0, σ²). The log-likelihood ratio for bit b given y is

LLR(b) = ln( P(b=0 | y) / P(b=1 | y) ) = 2y/σ².

Positive LLR → "probably 0", negative → "probably 1", magnitude → confidence. Hard-decision decoding throws away the magnitude; LDPC's strength is feeding the full LLR into the graph. In `code/main.py` we generate soft LLRs from hard bits with an adjustable noise scale so you can watch the decoder pull a wrong bit back.

### Sum-product message passing: one iteration in detail

Each iteration alternates two message phases on the Tanner graph. Let q_{i→j} be the message bit i sends to check j (bit's current belief excluding check j), and r_{j→i} the message check j sends back to bit i.

1. **Initialization.** Every bit node sets its outgoing q_{i→j} to the channel LLR L_ch(i).
2. **Check-node update (λ messages).** Each check node combines the q messages from all its *other* bits. For a check of degree d, the parity constraint says the XOR of those bits is 0, so:
   r_{j→i} = 2 · atanh( ∏_{i'≠i} tanh(q_{i'→j} / 2) ).
   The tanh/atanh form is the exact sum-product rule for an XOR constraint; it multiplies probabilities of "even number of 1s."
3. **Bit-node update (π messages).** Each bit sums the incoming r messages with its own channel LLR:
   L(i) = L_ch(i) + Σ_{j'∈N(i)} r_{j'→i},   and the outgoing q_{i→j} = L(i) − r_{j→i} (exclude check j).
4. **Hard decision & halt test.** Decide ĉ_i = 0 if L(i) ≥ 0 else 1. If Hĉᵀ = 0, decoding succeeds — stop. Otherwise iterate, up to a cap (typically 50–100 in silicon).

`code/main.py` implements exactly these four steps with the tanh/atanh kernel and prints, per iteration, the syndrome weight and the bit LLRs so you can watch a wrong bit cross zero.

### Worked example: one flipped bit, three iterations to converge

Take the valid (7,4) codeword c = `1010010` (Hcᵀ = 0). Flip bit 4: r = `1011010`. Hard-decision syndrome s = Hrᵀ = [0,1,1]ᵀ, weight 2. BP does the same job *softly*: bit 4's channel LLR is the most negative because its sample flipped. After iteration 1, the two checks touching bit 4 (p2, p3) push positive evidence toward it; its total LLR crosses zero; the syndrome vanishes in one iteration. `code/main.py` Case 1 reproduces this exactly.

Flip a second bit (Case 2, bits 2 and 6): now two errors are present. Because the code's minimum distance is 3, the received word is closer to a *different* valid codeword than to the one sent. BP converges — the syndrome hits zero — but to the wrong codeword: a **miscorrection**. This is the same mechanism that produces the LDPC error floor at scale, and it is why DVB-S2 adds a BCH outer code and 5G NR adds CRC + HARQ: the outer layer catches the rare residual that BP "corrected" into a neighboring codeword.

### Why LDPC wins at speed: parallelism and the Shannon gap

| Code | Decoder | Work per bit | Parallelizes? | Gap to Shannon (rate 1/2) |
|---|---|---|---|---|
| Hamming (7,4) | syndrome lookup | O(1) | yes, trivially | ~9 dB |
| Convolutional + Viterbi | trellis, k states | O(k) per step | limited — trellis is sequential | ~3 dB |
| Turbo (parallel concatenated) | two BCJR decoders, interleaved | O(L) per iteration | moderate, two decoders | ~0.8 dB |
| **LDPC, sum-product** | message passing on sparse graph | O(w_r) per iteration | **excellent** — all nodes update independently | **~0.2–0.5 dB** |

The trellis in Viterbi forces an ordering: state *t* depends on state *t−1*. A Tanner graph has no such ordering — every check node updates at once, every bit node updates at once — so a silicon LDPC decoder is a sea of small processing elements that run lockstep per iteration. That is why 802.3an 10GBASE-T and DVB-S2 chose LDPC over turbo: at multi-gigabit rates the parallelism is the deciding factor.

### Standards: where LDPC actually lives

| Standard | Spec | Block length | Rate set | Notes |
|---|---|---|---|---|
| **DVB-S2 / S2X** | EN 302 307 | 64 800 (normal), 16 200 (short) | 1/4 … 9/10 | BCH outer + LDPC inner; the workhorse of satellite TV |
| **802.11n/ac/ax** | IEEE 802.11 | 648, 1296, 1944 | 1/2, 2/3, 3/4, 5/6 | Optional; competes with convolutional code |
| **10GBASE-T** | IEEE 802.3an | 2048 | 1723/2048 ≈ 0.841 | Quasi-cyclic (QC-LDPC), 38 × 6 sub-matrices |
| **G.hn** | ITU-T G.9960 | up to 540 bytes | multiple | powerline + phoneline + coax |
| **5G NR** | 3GPP TS 38.212 | up to 8448 (BG1), 3840 (BG2) | various via puncturing | QC-LDPC, base graphs BG1/BG2, lifted by Z ∈ {2…384} |

Two recurring engineering choices: **quasi-cyclic** structure (H is built from small circulant Z×Z sub-blocks) so the encoder/decoder index memory with shifts instead of random lookups, and a **puncturing/shortening** layer so one base graph serves many rates.

### Error floors, trapping sets, and the outer BCH

LDPC BER curves have three regions: a **waterfall** (BER drops steeply with SNR), a possible **error floor** (BER flattens between 10⁻⁷ and 10⁻⁸), and the **effective-failure** region at very low SNR. The floor is caused by **trapping sets** — small subgraphs (a few bits and checks) where BP messages reinforce the wrong decision and never escape, even though the noise is mild. DVB-S2 wraps a BCH outer code around the LDPC inner code precisely to mop up the rare residual errors that escape the floor; 5G NR relies on CRC + HARQ retransmission instead. Designing H to avoid small trapping sets (no 4-cycles, large girth) is the art that separates a working code from one that floors at 10⁻⁵.

## Build It

1. Open `code/main.py`. It defines the (7,4,3) Hamming parity-check matrix `H`, the corresponding generator `G`, and a `tanner_graph(H)` builder.
2. Run `python3 code/main.py`. The demo encodes message `1010`, injects a single-bit error, then runs `belief_propagation_decode()` and prints each iteration's syndrome weight and per-bit LLRs.
3. Find the line where `flips` is set to `[3]` and change it to `[1, 5]` (two errors). Rerun and watch what happens: BP still drives the syndrome to zero in one or two iterations, but the decoded word is *wrong*. With d_min = 3, two errors put the received word closer to a different valid codeword than to the one sent — this **miscorrection** is exactly the error-floor / trapping-set phenomenon in miniature, and it is why a real standard pairs LDPC with a BCH or CRC outer code.
4. Push `noise_sigma` higher (Case 3) and watch the decoder converge confidently to the wrong codeword — high confidence in a wrong answer is the silent failure mode soft decoders introduce, which CRC + HARQ exist to catch.
5. Read `assets/ldpc-codes-iterative-decoding.svg` alongside the run: trace one q message from bit c4 to check p2 and the r message that comes back, matching the printed LLRs.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify a codeword is valid | `H @ c % 2 == 0` (syndrome all zero) | Syndrome is the zero vector; no parity equation violated |
| Confirm BP converged | syndrome weight hits 0 before `max_iter`; final LLR signs match sent bits | Iteration count < max_iter; LLRs polarize with large magnitudes |
| Detect an error floor | BER flattens as SNR rises; a trapping-set subgraph identified | Floor location matches the minimum distance / trapping set of H |
| Pick LDPC vs convolutional | required throughput, target BER, silicon area | Multi-Gbps or near-Shannon → LDPC; low complexity, short blocks → convolutional |
| Map to a standard | block length, rate, spec number | DVB-S2 = 64 800; 802.11n = 648/1296/1944; 5G NR BG1/BG2 |

## Ship It

Produce one artifact under `outputs/prompt-ldpc-codes-iterative-decoding.md`:

- An annotated BP-decoding trace from `code/main.py` for a one-error and a two-error run, with the per-iteration syndrome weight and the iteration at which each wrong bit's LLR crossed zero called out.
- A one-page standards card: DVB-S2, 802.11n, 802.3an, G.hn, 5G NR — block length, rate, base-graph structure, and the outer code (BCH / CRC) each pairs with LDPC.
- A short note on the error floor: which trapping set in the (7,4) graph causes the two-error stall you observed, and how an outer BCH would catch it.

Start from the printed output of `code/main.py` and annotate it by hand.

## Exercises

1. Using the H matrix in `code/main.py`, draw the Tanner graph by hand and list, for each of the 7 bit nodes, exactly which check nodes it connects to. Identify the shortest cycle (its girth). Does this graph contain a 4-cycle, and what does that imply for sum-product decoding?
2. Encode message `m = 0110` with the generator G from `code/main.py`, then flip bit 2. Compute the hard-decision syndrome by hand and confirm BP converges to the same bit. Now flip bits 2 and 6 (Case 2 in `code/main.py`) — BP still drives the syndrome to zero, but the decoded word is wrong. Explain, using d_min = 3, why this miscorrection is unavoidable and what outer mechanism a real standard uses to detect it.
3. The check-node update rule uses `2·atanh(∏ tanh(q/2))`. For a degree-3 check with incoming q values of +4, +4, and −6, compute the outgoing r message by hand. What sign does it have, and why?
4. A DVB-S2 receiver uses a rate-1/2 LDPC code (n = 64 800). Estimate the number of bit-node and check-node processing elements a fully parallel decoder would need, and explain why real chips use partial parallelism (e.g. 360 PEs). What does the quasi-cyclic structure buy?
5. Plot (conceptually) the BER vs E_b/N_0 curve for the (7,4) code: identify the waterfall region and predict where the error floor would begin given the code's minimum distance of 3. Why does DVB-S2 add a BCH outer code on top?
6. 5G NR (TS 38.212) uses two base graphs: BG1 for large payloads and high rates, BG2 for small payloads and low rates. Argue why a single base graph cannot serve both regimes efficiently, in terms of the rate-flexibility trade-off (puncturing, shortening, lifting size Z).

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Parity-check matrix H | "the code's table" | An r×n binary matrix; a word c is a codeword iff Hcᵀ = 0 over GF(2) |
| Tanner graph | "the code's picture" | Bipartite graph of variable (bit) nodes and check nodes; an edge per 1 in H |
| Belief propagation | "the LDPC decoder" | Sum-product message passing: bit and check nodes exchange LLRs iteratively until the syndrome vanishes |
| LLR | "soft bit" | Log-likelihood ratio ln(P(0)/P(1)); sign is the decision, magnitude the confidence |
| Trapping set | "a stuck pattern" | A small subgraph where BP messages reinforce a wrong decision, causing the error floor |
| Code rate | "the overhead" | k/n, the fraction of codeword bits that carry information |
| Quasi-cyclic (QC-LDPC) | "structured LDPC" | H built from circulant Z×Z sub-blocks; enables shift-based encode/decode, used in 802.3an and 5G NR |
| Girth | "shortest cycle" | Length of the shortest cycle in the Tanner graph; larger girth → better BP convergence |
| Error floor | "BER flattens" | Region where BER stops dropping with SNR because of trapping sets, typically 10⁻⁷–10⁻⁸ |
| Waterfall region | "the steep drop" | Low-SNR region where BER falls sharply as SNR rises — the useful operating point |

## Further Reading

- R. G. Gallager, *Low-Density Parity-Check Codes*, MIT Press, 1963 (the original thesis, revived 1995).
- T. Richardson & R. Urbanke, *Modern Coding Theory*, Cambridge University Press, 2008 — the definitive treatment of density evolution and code design.
- **EN 302 307** (ETSI) — DVB-S2/S2X framing structure and LDPC + BCH coding.
- **IEEE 802.3an-2006** — 10GBASE-T, Clause 55, the 2048-byte QC-LDPC code.
- **IEEE 802.11-2020**, Annex R — LDPC parity-check matrices for 648/1296/1944-bit codes.
- **3GPP TS 38.212** — 5G NR multiplexing and channel coding, LDPC base graphs BG1/BG2.
- **ITU-T G.9960** (G.hn) — LDPC for powerline, phoneline, and coax.
- F. R. Kschischang, B. J. Frey, H.-A. Loeliger, "Factor Graphs and the Sum-Product Algorithm," IEEE Trans. Inf. Theory, 47(2), 2001.
- S. Lin & D. Costello, *Error Control Coding*, 2nd ed., Prentice Hall, 2004 — Chapters 15–17 on LDPC and iterative decoding.
