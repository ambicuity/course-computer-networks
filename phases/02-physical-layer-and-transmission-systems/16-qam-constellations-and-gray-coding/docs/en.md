# QAM Constellations and Gray Coding

> **Quadrature Amplitude Modulation (QAM)** packs multiple bits into one symbol by combining two orthogonal carriers — an in-phase **I** and a quadrature **Q** — so each symbol is a point in a 2-D constellation. **QPSK** carries 2 bits/symbol on 4 points; **QAM-16** carries 4 on a 4×4 grid; **QAM-64** carries 6, **QAM-256** carries 8. Naive bit labeling is disastrous: if noise shifts the received point to a neighbor, all bits can flip (`0111` → `1000` flips all 4). A **Gray code** re-labels points so adjacent symbols differ in exactly one bit, turning a 4-bit error into a 1-bit error under the realistic assumption that noise is small relative to the inter-point distance. Real systems rely on this: DOCSIS 3.1 runs **QAM-4096** over 192 MHz OFDM subcarriers, Wi-Fi 6 (802.11ax) uses **1024-QAM** at a 5/6 coding rate, LTE defaults to **QAM-64** uplink / **QAM-256** downlink. The failure engineers fight is **symbol error rate (SER)** exploding as the constellation densifies for the same SNR — points crowd closer, decision boundaries shrink, and without Gray coding the bit error rate grows with nearest-neighbor count times the bit distance. This lesson builds a Gray-coded QAM mapper, an AWGN symbol-error simulator, and an SER-vs-SNR sweep so you can watch the constellation close.

**Type:** Lab
**Languages:** Python, GNU Radio
**Prerequisites:** Bandwidth and Nyquist/Shannon limits, baseband vs. passband, I/Q representation
**Time:** ~70 minutes

## Learning Objectives

- Draw the QAM-16 and QAM-64 constellations as I/Q grids, label each point with its Gray-coded bits, and identify the decision boundaries a minimum-distance receiver uses.
- Compute the bits-per-symbol and minimum Euclidean distance for a square M-QAM constellation given M.
- Explain why a Gray code minimizes BER for a fixed SER, and quantify the difference versus a sequential (binary) label assignment.
- Run an AWGN simulation and read off SER and BER, then compare to the theoretical M-QAM SER bound.
- Justify, from Shannon capacity and SNR margin, why a link drops from 1024-QAM to 256-QAM (or lower) when the channel degrades.
- Identify the evidence — constellation points, nearest-neighbor counts, bit-distance histograms — that confirms a mapping is actually Gray-coded.

## The Problem

A Wi-Fi 6 access point is configured for 1024-QAM on a 160 MHz channel, promising 1201 Mbps per spatial stream. A user 15 m away, behind one interior wall, sees throughput collapse to a tenth of that; management frame counters show a spike in FEC-correctable errors and a rising retry rate. The link is still *associated* — the radio has not fallen back to a lower MCS — but it is hemorrhaging bit errors.

The root cause is almost never a software bug. It is geometry. 1024-QAM packs 10 bits per symbol, so 1024 points share a square whose side is the maximum I (and Q) excursion. The minimum Euclidean distance between points — the margin the receiver needs to decide correctly — shrinks as `2·A / (sqrt(M) − 1)`. For the same transmit power, doubling bits-per-symbol roughly *halves* the noise tolerance. The wall ate the SNR margin 1024-QAM required, and the receiver now routinely decodes the *neighboring* symbol. If the bit labels were assigned in plain binary order, every neighbor slip would corrupt several bits; with Gray coding, each slip costs exactly one bit, which the convolutional/LDPC FEC layer then repairs. This lesson shows how the labeling is built and why it is the cheap, mandatory fix that makes dense QAM usable.

## The Concept

### Passband modulation and the I/Q plane

Digital passband transmission modulates a carrier `cos(2πf_c·t)` in amplitude and phase. Because `cos` and `sin` are orthogonal over a symbol period, the transmitter sends `s(t) = I·cos(2πf_c·t) − Q·sin(2πf_c·t)`, where **I** (in-phase) and **Q** (quadrature) are the two real coordinates of a point in the complex plane. The receiver mixes with `cos` and `−sin` and integrates to recover `(I, Q)`. Every QAM symbol is a point `(I, Q)` from a fixed grid. The textbook's Fig. 2-23 draws QPSK as four points at 45°, 135°, 225°, 315° — equivalently `(±A, ±A)` — and QAM-16 as a 4×4 grid.

### Square M-QAM geometry

For **square M-QAM** with M = 4^k (M = 4, 16, 64, 256, …), the points lie on a `sqrt(M) × sqrt(M)` grid. With coordinates spaced `2d` apart and centered on the origin, the I and Q levels are `{±d, ±3d, …, ±(sqrt(M)−1)·d}`. Three quantities determine everything:

| Quantity | Formula | Meaning |
|---|---|---|
| Bits per symbol | `log2(M)` | 2 QPSK, 4 QAM-16, 6 QAM-64, 8 QAM-256, 10 QAM-1024 |
| Minimum Euclidean distance | `d_min = 2d` | Distance between nearest neighbors; the noise margin |
| Average symbol energy | `E_s = (2/3)·(M−1)·d²` | For the square grid; scales the SNR normalization |

Normalize `E_s` to 1 for fair comparison: then `d_min = sqrt(6 / (M−1))`. QAM-16: `d_min ≈ 0.632`. QAM-64: `0.316`. QAM-256: `0.158`. Every quadrupling of M halves `d_min`, so the required SNR for the same SER rises by ~6 dB. That single fact is why your phone drops MCS index as you walk away from the AP.

### The labeling problem and nearest-neighbor errors

The constellation tells the radio *which point* to send. The *labeling* tells it *which bits* that point represents. Consider QAM-16. If we label the 16 points left-to-right, top-to-bottom in plain binary (`0000, 0001, …, 1111`), horizontally adjacent points differ by 1 in the LSB but vertically adjacent points differ by 4 in the label — a vertical slip flips up to 3 bits. The worst case is a diagonal neighbor such as `0111` next to `1000`: a small noise burst flips *all 4* bits. Because thermal noise is Gaussian, small errors dominate: the received point lands on a *nearest neighbor* far more often than a distant one. So BER is governed by the bit-distance to nearest neighbors, not the average distance.

### Gray coding: adjacent points differ in one bit

A **Gray code** (reflected binary code, Frank Gray, Bell Labs, 1947) is an ordering of the `2^k` bit words such that consecutive words differ in exactly one bit. For a 1-D axis with `n = sqrt(M)` levels, the n-bit Gray code of index `g` is `g XOR (g >> 1)`. We label the I axis with the high `k/2` Gray bits and the Q axis with the low `k/2` Gray bits, so the 2-D label is `(gray_I, gray_Q)`. Every horizontal and vertical neighbor now differs in exactly one bit; diagonal neighbors differ in at most two. The textbook's Fig. 2-24 shows the result for QAM-16: when `1101` is sent and the receiver decodes a neighbor, the bit-error count is 1 (see `assets/qam-constellations-and-gray-coding.svg`).

### Worked example: labeling one row of QAM-16

QAM-16 has 4 I levels indexed `0..3`. The 2-bit Gray codes are: index 0 → `00`, 1 → `01`, 2 → `11`, 3 → `10` (computed as `g XOR (g>>1)`). Reading across the top row, the labels run `00 01 11 10` — *not* `00 01 10 11`. That single change is what guarantees a horizontal slip flips one bit. `code/main.py` computes this table for any M and prints the full Gray-labeled constellation.

### Symbol error rate and the AWGN bound

For an M-QAM signal in additive white Gaussian noise with one-sided PSD `N0`, the exact SER on the square constellation is (Proakis):

`SER = 1 − [1 − (1 − 1/sqrt(M))·erfc(sqrt(3·E_s / ((M−1)·N0)))]^2`

where `erfc` is the complementary error function and `E_s/N0` is the symbol-energy-to-noise ratio. The `1/sqrt(M)` factor is the `d_min` shrinkage from above. At SER = 10⁻³ the required `E_s/N0` is approximately: QPSK 9.8 dB, QAM-16 14.4 dB, QAM-64 18.8 dB, QAM-256 23.0 dB, QAM-1024 27.3 dB (each quadrupling of M costs ~6 dB). Because Gray coding makes the dominant nearest-neighbor errors cost one bit, `BER ≈ SER / log2(M)` in the high-SNR regime — a 4× to 10× improvement in BER for the same SER versus a sequential label. `code/main.py`'s `sweep` function reproduces these thresholds by Monte-Carlo simulation.

### Adaptive modulation and coding (AMC)

Real radios do not pick one QAM order and keep it. Wi-Fi (802.11ax MCS 0–11), LTE (CQI 0–15), and DOCSIS all run **adaptive modulation**: the receiver estimates SNR via the preamble or pilot subcarriers, reports a channel quality indicator, and the transmitter picks the highest MCS whose required `E_s/N0` sits below the measured SNR minus a margin. The threshold list above is the lookup table the rate-adaptation algorithm walks. When your phone retreats from 1024-QAM to 256-QAM it buys 4 dB of margin by giving up 2 bits/symbol — the `d_min` trade-off. GNU Radio's `constellation_receiver` does the same in real time: a Costas loop tracks phase, slices to the nearest point, and emits error flags the MAC uses to step the MCS down.

## Build It

1. Open `code/main.py` and read `gray_code` — it implements `g XOR (g >> 1)` for k-bit words. Confirm it yields `000, 001, 011, 010, 110, 111, 101, 100` for k=3.
2. Run `python3 main.py` and inspect the printed QAM-16 constellation grid. Verify every horizontal and vertical neighbor pair differs in exactly one bit.
3. Call `simulate(M=16, snr_db=14, trials=200_000)` and read the printed SER and BER. Cross-check BER against `SER / log2(16)`.
4. Run `sweep(M=64)` and watch SER cross 10⁻³ near 18–19 dB, matching the table.
5. In GNU Radio, build *Random Source* → *Constellation Modulator* (QAM-16, Gray) → *Channel Model* (noise tuned to 14 dB SNR) → *Constellation Receiver* → *BER* sink. Vary noise and watch the SER waterfall as the order goes 16 → 64 → 256.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify a constellation is Gray-coded | Print the label grid and count bit-differences for all neighbor pairs | Every horizontal/vertical pair differs in exactly 1 bit; diagonal in at most 2 |
| Predict SER at a target SNR | Run `simulate()` and compare to the erfc bound | Simulated SER within ~10% of the theoretical curve |
| Find the SNR knee for an MCS | Run `sweep(M)`, locate where SER crosses 10⁻³ | 16-QAM ≈ 14 dB, 64-QAM ≈ 19 dB, 256-QAM ≈ 23 dB |
| Quantify Gray vs. binary labeling | Run `simulate()` swapping `gray=True/False`, compare BER at fixed SNR | Gray BER is ~`log2(M)`× lower in the high-SNR regime |
| Diagnose a link falling back | Read the MCS, the measured SNR, and the table | A 20 dB link cannot hold 256-QAM (needs 23 dB) but holds 64-QAM (needs 19 dB) |

## Ship It

Produce the artifact `outputs/prompt-qam-constellations-and-gray-coding.md` containing: (1) the Gray-labeled QAM-16 and QAM-64 constellation grids, (2) the simulated SER-vs-SNR curves for M = 16, 64, 256 on one log plot, (3) a one-paragraph verdict naming the highest MCS sustainable at a measured SNR of 21 dB with a 3 dB margin, with the `d_min` and required-`E_s/N0` numbers that justify it. Attach the SVG showing the Gray-labeled QAM-16 grid with the `1101`→neighbor error arrows.

## Exercises

1. A receiver measures `E_s/N0 = 20 dB` and must choose between QAM-64 (needs ~19 dB) and QAM-256 (needs ~23 dB) with a 3 dB safety margin. Which MCS does it select, and how many bits/symbol does it sacrifice? Show the margin arithmetic.
2. Construct the Gray-coded QAM-64 label grid by hand for the first I row (8 levels). Confirm `gray(6) = 101` and `gray(7) = 100`, and that the wrap between index 7 and 0 differs in one bit.
3. A link running sequential (binary) QAM-16 reports SER = 4×10⁻³ at 12 dB. Estimate the BER under binary labeling (assume a 2-bit vertical slip dominates) and under Gray labeling. What is the BER ratio?
4. The transmitter normalizes `E_s = 1`. Compute `d_min` for QAM-16, QAM-64, and QAM-1024 and show that doubling bits-per-symbol costs ~6 dB of noise tolerance.
5. In GNU Radio, build the QAM-16 flowgraph and raise noise until SER ≈ 10⁻². Capture the constellation sink: points form fuzzy clouds. Identify which neighbor `1101` is most often confused with, and confirm from the Gray table that the slip costs one bit.
6. DOCSIS 3.1 uses QAM-4096 (12 bits/symbol) on a 192 MHz OFDM subcarrier. Estimate the required `E_s/N0` at SER = 10⁻³ by extrapolating the 6-dB-per-quadrupling trend, and discuss why this forces aggressive HFC-plant equalization.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| QAM | "It's just faster Wi-Fi" | A 2-D modulation mapping `log2(M)` bits onto one point in the I/Q plane |
| Constellation | "The dot diagram" | The set of legal (I, Q) points the transmitter may emit, drawn as a grid |
| Gray code | "Some bit trick" | A labeling where adjacent symbols differ in exactly one bit, minimizing BER for a given SER |
| d_min | "Spacing" | Minimum Euclidean distance between constellation points; the noise margin |
| SER | "Error rate" | Probability the receiver decodes the wrong *point* — distinct from bit error rate |
| E_s/N0 | "SNR" | Symbol energy per noise PSD; the quantity the SER formulas use (vs. E_b/N0 for BER) |
| MCS index | "Speed setting" | Modulation-and-coding-scheme identifier tying a QAM order + FEC rate to a required SNR |
| AMC | "Rate adaptation" | Adaptive Modulation and Coding: picking the MCS whose required SNR fits the channel |

## Further Reading

- IEEE 802.11ax-2021 — Wi-Fi 6, MCS 0–11 including 1024-QAM at code rates 3/4 and 5/6.
- 3GPP TS 36.211 — LTE physical channels; QAM-16/64/256 uplink/downlink modulation mappings.
- DOCSIS 3.1 PHY Spec, CM-SP-PHYv3.1 — QAM up to 4096 over 20–192 MHz OFDM subcarriers.
- J. G. Proakis, *Digital Communications*, 5th ed., McGraw-Hill, 2008 — square M-QAM SER formula and Gray-code BER analysis.
- M. K. Simon & M.-S. Alouini, *Digital Communication over Fading Channels*, 2nd ed., Wiley, 2005 — SER/BER under fading.
- F. Gray, "Pulse Code Communication," U.S. Patent 2,632,058, filed 1947, issued 1953 — the original reflected-binary-code patent.
