# Line Codes, Clock Recovery, and DC Balance

> A receiver cannot decode bits unless it knows *when* to sample the line, yet sending a separate clock wire is a waste of a perfectly good pair. **Line codes** solve this by shaping the voltage waveform itself so that data and timing travel together. **NRZ** follows the bits directly but collapses on long runs of 0s or 1s — 15 zeros look like 16 unless the receiver's clock drifts under a microsecond, which commodity oscillators cannot hold. **NRZI** (USB 1.x/2.x) codes a 1 as a *transition* and a 0 as *no transition*, killing the long-1 run problem but leaving long-0 runs; USB fixes this with **bit stuffing** (a 0 is stuffed after six consecutive 1s). **Manchester** XORs the data with a 2× clock so every bit cell has a transition — used by classic 10BASE5/10BASE2 Ethernet — but pays 100% bandwidth overhead. **4B/5B** (FDDI, 100BASE-TX) maps 4 data bits to a 5-bit codeword chosen so no run exceeds three 0s, adding 25% overhead and leaving 12 of 32 codes free for control symbols like idle `11111` and J/K start-of-stream `11000 10001`. **8B/10B** (PCIe Gen 1-2, gigabit Ethernet 1000BASE-X, SATA, USB 3.0) adds running-disparity tracking so the line is DC-balanced to within ±1 symbol and never sees more than five consecutive identical bits. **AMI/Alternate Mark Inversion** (T1/E1) inverts the polarity of every mark so 1s average to zero. **Scrambling** (SONET/SDH x^7+x^6+1, later x^43+1) whitens the spectrum but famously allowed **killer packets** on early POS links to produce all-zero scrambler output and drop the line. This lesson builds a runnable encoder/decoder for NRZ, NRZI, Manchester, 4B/5B, and 8B/10B with disparity control, plus a run-length and DC-balance analyzer that shows exactly why each code survives or fails a given bit stream.

**Type:** Build
**Languages:** Python, packet traces
**Prerequisites:** Baseband vs passband signaling, Nyquist rate and the bandwidth/bit-rate relationship, frequency-domain intuition for a square wave
**Time:** ~80 minutes

## Learning Objectives

- Encode an arbitrary bit stream in NRZ, NRZI, Manchester, 4B/5B, and 8B/10B and decode each back, explaining where a naive decoder desynchronizes.
- Compute the maximum run of consecutive identical bits and the running DC disparity for each code on a given input, and predict which links would fail.
- Explain why Manchester costs 2× bandwidth and why 4B/5B costs only 25%, deriving both from the Nyquist relation B ≥ bit_rate / (2 × bits_per_symbol).
- Trace 8B/10B running-disparity selection: given the previous disparity, pick the alternate codeword that drives disparity toward zero and state the final disparity.
- Justify the bit-stuffing rule in USB (insert a 0 after six consecutive 1s) and the T1 "no more than 15 consecutive 0s" line-density rule, in terms of clock recovery.
- Read a line-coded waveform from a packet trace and identify the code in use from its transition density and DC behavior.

## The Problem

A hardware team is bringing up a 1 Gb/s serial link over a transformer-coupled coax run. The first prototype locks up whenever the firmware sends a long block of `0x00` fill bytes — the link reports loss of signal, the PLL loses lock, and the receiver's AC-coupling capacitor charges up until the decision threshold slides off the rails. The same link works fine for random data. Meanwhile a USB 2.0 device fails compliance when a test pattern of all-ones is fed through it: the receiver's clock drifts far enough in a long 1-run that it samples one bit early, then doubles a bit. Both symptoms are the same root cause, and neither is fixed by a more expensive oscillator — the line code itself must guarantee transitions and keep the time-average of the voltage near zero. The engineer must pick (or debug) a line code that simultaneously satisfies clock recovery, DC balance, and a bandwidth budget.

## The Concept

### The three independent problems a line code solves

A line code is judged on three largely independent axes. Confusing them is the most common mistake in physical-layer design.

| Property | What it asks | Failure symptom | Codes that address it |
|---|---|---|---|
| **Clock recovery** | Are there enough voltage transitions for the receiver PLL to stay locked? | Long runs of identical bits → PLL drift, dropped/doubled bits | Manchester, NRZI+stuffing, 4B/5B, 8B/10B, scrambling |
| **DC balance** | Does the signal average to ~0 over short windows? | Transformer/capacitive coupling charges up, decision threshold drifts, energy wasted in a filtered DC term | AMI, 8B/10B (disparity), Manchester |
| **Bandwidth efficiency** | How many Hz of channel do you need per bit? | Needs more cable/RF spectrum than the channel allows | NRZ (best, 1 bit/2 Hz), MLT-3, multilevel (PAM) |

A code can be excellent on one axis and terrible on another. NRZ is the most bandwidth-efficient common code but the worst for clock recovery and DC. Manchester is excellent for clock recovery and DC but wastes half the channel. 8B/10B is the practical compromise: 80% efficient, bounded runs, bounded disparity.

### NRZ: the baseline, and why it is never used alone

NRZ (Non-Return-to-Zero) maps `1 → +V` and `0 → −V` and holds the level for the whole bit cell. The name is historical: the signal does not return to zero between bits. For a bit rate *B*, alternating `1010…` changes the line at rate *B/2*, so by the Nyquist relation the channel must support at least **B/2 Hz**. This is the fundamental floor; no binary code beats it.

The killer is a long run. Consider `000…0` (15 zeros). The line sits at −V for 15 bit times with zero transitions. The receiver PLL, locked only to transitions, freewheels. If its oscillator is off by 100 ppm at 1 Gb/s, that is 100 kHz of error — over 15 ns (15 bit times) it accumulates 1.5 ns of phase error, more than half a bit cell. The decoder samples in the wrong place, then loses count entirely. NRZ is also catastrophically DC-unbalanced: an all-ones block has average +V, which a transformer coupling simply removes, leaving the receiver seeing nothing. `code/main.py` computes the max run and DC imbalance for a stream and shows NRZ failing on `0x00` fill.

### NRZI and bit stuffing: USB's answer

NRZI (Non-Return-to-Zero Inverted) changes the rule: a **1 = transition** at the cell boundary, a **0 = no transition**. This flips the failure mode. Long runs of 1s are now full of transitions (perfect for the PLL); long runs of 0s are now the dead zones. USB 1.x and 2.x use NRZI and patch the 0-run problem with **bit stuffing**: after six consecutive 1s in the *raw data*, the transmitter inserts a 0 (a stuff bit) to force a transition. The receiver counts 1s, removes the stuffed 0 after the sixth, and recovers the data. USB's SYNC field (`KJKJKJKK`) gives the PLL an initial lock reference of alternating transitions before payload begins.

| Input bits | NRZI level behavior (transitions on 1) |
|---|---|
| `1 1 1 1` | transition every cell — PLL happy |
| `0 0 0 0` | no transition — PLL drifts (this is what stuffing prevents in the *raw* stream) |

The cost of stuffing is variable: a worst-case all-ones payload inflates by ~1/6. Real USB traffic is far from worst case, so the average overhead is tiny, but the *maximum* frame size must budget for it.

### Manchester: a clock in every bit, at 2× the cost

Manchester XORs the data with a clock that toggles every bit cell (so the clock runs at 2 × bit rate). Result: **every** bit cell has exactly one transition. A low-to-high transition is a 0, high-to-low is a 1 (the IEEE 802.3 convention; G.E. Thomas convention flips the polarity). Classic 10BASE5 "Thick Ethernet" and 10BASE2 use Manchester. Clock recovery is trivial — there is a transition in every cell — and the signal is DC-balanced because every cell spends half its time high and half low.

The price is bandwidth. Because the line transitions up to once per bit cell (rate *B*), the channel needs at least **B Hz**, twice NRZ's B/2. At 10 Mb/s that was affordable on cheap coax; at 100 Mb/s and above it is not, which is why 100BASE-TX abandoned Manchester for 4B/5B + MLT-3. See `assets/line-codes-clock-recovery-and-dc-balance.svg` for the side-by-side waveform comparison.

### 4B/5B: trading 25% overhead for bounded runs and control symbols

4B/5B maps each 4-bit nibble to a fixed 5-bit codeword chosen so that **no codeword contains more than three consecutive 0s** and no run across codeword boundaries exceeds three 0s at the start or end. Of the 32 possible 5-bit patterns, 16 are data; the remaining 16 (minus a few rejected for run length) become control symbols:

| Symbol | 5B code | Role |
|---|---|---|
| Data 0000–1111 | 11110, 01001, 10100, … (see table in `code/main.py`) | Payload nibble |
| I (Idle) | `11111` | Line idle, continuous transitions |
| J | `11000` | Start-of-stream delimiter part 1 |
| K | `10001` | Start-of-stream delimiter part 2 |
| T | `01101` | End-of-stream |
| R (Reset) | `00111` | Reset / Halt |
| Q (Quiet) | `00000` | Unused — violates run rule |
| H (Halt) | `00100` | Unused — violates run rule |

4B/5B is 80% efficient (4 payload bits per 5 line bits), so a 100 Mb/s data stream needs 125 Mbaud on the line — 100BASE-TX then maps the 5B symbols through MLT-3 to compress the spectral footprint into a ~31.25 MHz band. FDDI used 4B/5B directly. 4B/5B solves clock recovery (bounded runs) but **not** DC balance — it is single-level, so a density of 1s drifts the average. That is acceptable on DC-coupled twisted pair but would fail on transformer-coupled coax, which is why gigabit Ethernet moved to 8B/10B.

### 8B/10B: disparity tracking for DC balance

8B/10B (Widmer & Franaszek, IBM, 1983) maps 8 data bits to 10 line bits and is 80% efficient like 4B/5B. Its distinguishing feature is **running disparity (RD)** control. The 8-bit input is split 5+3 and mapped to a 6-bit + 4-bit output. Each 10-bit codeword is one of:

- **Perfectly balanced** (five 1s, five 0s) — disparity 0, does not change RD.
- **Unbalanced** — comes in a **positive** form (six 1s, four 0s, disparity +2) and a **negative** form (four 1s, six 0s, disparity −2).

The encoder keeps a running disparity, initialized to **−1** (negative). Before emitting an unbalanced codeword it picks whichever polarity *reduces the absolute disparity*: if RD is negative it emits the positive form (pulling RD toward 0); if RD is positive it emits the negative form. With this rule the running disparity stays in {−1, +1} and the **worst-case cumulative imbalance is 2 bits** — so over any window the DC average is within ±0.1 of zero. As a bonus, every valid codeword has at least one transition and bounded runs (no more than five consecutive identical bits), giving clock recovery for free.

Worked example, encoding an **unbalanced** symbol such as D.23 (`0x17`, data `00010111`, split `011 00000`... in practice `111 00000`), whose two forms carry disparity +2 and −2:

1. Start RD = −1 (negative).
2. The encoder looks up the two forms. One has six 1s (disparity +2), the other four 1s (disparity −2). Because RD is negative, the encoder emits the **+2 form** to pull the running disparity up toward zero.
3. After the symbol, RD flips to **+1**. The next unbalanced symbol would then emit its **−2 form**, pulling RD back down.
4. Balanced symbols (five 1s, five 0s — e.g. D.0 `00000000` → `1001110100`/`0110001011`, both disparity 0) leave RD unchanged and can be emitted in either form.

`code/main.py` implements this selection and prints the chosen form and RD after every symbol, so you can watch the disparity oscillate around zero even on a payload that is mostly unbalanced symbols — exactly the case where 4B/5B and NRZ fail.

`code/main.py` implements this selection and prints the chosen form and RD after every symbol, so you can watch the disparity oscillate around zero even on an all-zeros payload — exactly the case where 4B/5B and NRZ fail.

8B/10B is the line code of PCIe Gen 1 and 2 (8.0 GT/s raw for 6.4 Gb/s payload), 1000BASE-X gigabit Ethernet, SATA, and USB 3.0. PCIe Gen 3 onward switched to **128B/130B** (98.5% efficient) with scrambling instead of disparity coding, because at 8 GT/s the 20% overhead became the binding constraint.

### AMI and the mark/space vocabulary

AMI (Alternate Mark Inversion), also called bipolar encoding, represents a 0 as 0 V and a 1 ("mark") as alternately +V and −V. Every second 1 inverts the polarity, so the 1s average to zero no matter how dense they are. T1 (DS1, 1.544 Mb/s over T1 lines) and E1 (2.048 Mb/s) use AMI. The remaining problem is **zero density**: a long run of 0s has no transitions, so T1 originally required users to send no more than 15 consecutive 0s. The modern fix is **B8ZS** (North America) or **HDB3** (Europe): when 8 (or 4) consecutive 0s appear, the code deliberately inserts a **bipolar violation** — a 1 with the *wrong* polarity — which the receiver recognizes as a substituted pattern, restores the 0s, and uses the violation as a guaranteed transition. AMI plus B8ZS gives both DC balance and clock recovery.

### Scrambling: making data look random, and the killer-packet trap

Scrambling XORs the data with a pseudorandom bit sequence (PRBS) generated by a linear-feedback shift register before line coding. SONET/SDH used the polynomial **x^7 + x^6 + 1** (a 7-bit LFSR, period 127); later POS standards moved to **x^43 + 1** to make malicious self-synchronization effectively impossible. Scrambling adds no bandwidth overhead and whitens the spectrum, which suppresses discrete EMI peaks from repetitive data.

The trap: a scrambler is linear, so if the attacker finds an input equal to the running PRBS sequence, the XOR is **all zeros** — exactly the worst case for clock recovery. Early "IP over SONET" (Malis & Simpson, 1999) used the short x^7+x^6+1 scrambler, so a crafted **killer packet** could deliberately zero the line and drop the link. The fix was the longer x^43+1 polynomial and, in some links, a guaranteed minimum transition density check. Scrambling is a *probabilistic* guarantee; 8B/10B's bounded-run property is a *deterministic* one. That distinction is the whole reason 8B/10B still exists at all in safety-critical short reach.

### Decision table: which code for which link

| If your link… | Clock recov need | DC balance need | BW budget | Pick |
|---|---|---|---|---|
| On-board, DC-coupled, short, cheap | low | none | generous | NRZ (or PAM-N) |
| USB-style, DC-coupled, cheap, variable data | high | none | medium | NRZI + bit stuffing |
| Classic 10 Mb/s Ethernet on coax | high | high | generous | Manchester |
| 100 Mb/s over Cat5, DC-coupled | high | none | medium | 4B/5B + MLT-3 |
| 1 Gb/s+ over fiber/short copper, transformer-coupled | high | high | medium | 8B/10B |
| 8+ Gb/s where 20% overhead is fatal | high | medium | tight | 128B/130B + scrambling |
| Telco T1/E1 over repeatered copper | high | high | medium | AMI + B8ZS/HDB3 |

## Build It

1. Read `code/main.py`. It implements `nrz()`, `nrzi()`, `manchester()`, `encode_4b5b()`, and `encode_8b10b()` with running-disparity tracking, each paired with a matching decoder.
2. Run it: `python3 code/main.py`. Confirm the demo prints the encoded waveform for the sample payload `0x00 0xFF 0x6A` under all five codes, plus the **max run** and **running DC disparity** each produces.
3. Inspect `analyze_runs_and_disparity()`: it walks the line bits and reports the longest run of identical bits and the peak absolute running disparity — the two numbers that predict PLL loss-of-lock and AC-coupling drift.
4. Feed it the killer payload `bytes([0x00]*20)` and observe: NRZ run = 160, 4B/5B run stays ≤ 3, 8B/10B disparity stays in {−1,+1}. That is the whole lesson in one run.
5. Edit the payload to a real USB-ish frame (SYNC `KJKJKJKK` + data) and confirm NRZI + stuffing keeps the run ≤ 6.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm a code is clock-recovery-safe | Max run of identical bits over a test payload | NRZ > 15 fails; Manchester = 1; 4B/5B ≤ 3; 8B/10B ≤ 5 |
| Confirm a code is DC-balanced | Peak absolute running disparity over the payload | AMI and 8B/10B ≤ 2; NRZ grows unbounded with payload |
| Verify 8B/10B disparity selection | Per-symbol RD printout oscillating in {−1,+1} | RD never escapes {−1,+1} even on all-zeros input |
| Verify bit stuffing | NRZI line stream contains no run of 1s longer than 6 | A stuff bit appears after the 6th consecutive 1 |
| Pick a line code for a spec | Bandwidth budget, coupling type, run-length requirement | The decision table maps the spec to exactly one code |
| Spot the killer-packet risk | Scrambler polynomial length, self-sync input feasibility | x^7+x^6+1 is vulnerable; x^43+1 is not in practice |

## Ship It

Produce one artifact under `outputs/prompt-line-codes-clock-recovery-and-dc-balance.md`:

- The encoded waveforms (from `code/main.py` output) for `0x00*20` under all five codes, annotated with the max-run and peak-disparity numbers and a one-line verdict per code (pass/fail for clock recovery and DC balance).
- A worked 8B/10B disparity trace: show the first four symbols of an all-zeros payload, the RD before/after each, and which polarity form was chosen and why.
- A one-page line-code selection card: for each of {on-board serial, USB, 10 Mb/s Ethernet, 100 Mb/s Ethernet, 1 Gb/s Ethernet, PCIe Gen 3, T1}, the chosen code and the single reason it won.

## Exercises

1. A 100BASE-TX link must carry 100 Mb/s of payload over Cat5 with a ~31 MHz bandwidth. Show why 4B/5B (125 Mbaud) + MLT-3 (three levels, fundamental at Mbaud/4) fits, and why Manchester would not.
2. Encode the byte `0x6A` (binary `01101010`) in NRZI starting from level LOW. Then show where USB bit stuffing would insert a stuff bit if the preceding raw stream were `111111 0`.
3. For 8B/10B, suppose running disparity is −1 and the next data symbol is D.0 (`000`|`00000`). The two forms have disparities +2 and −2. Which does the encoder emit, and what is RD after the symbol? Repeat assuming RD was +1.
4. A SONET link uses the x^7+x^6+1 scrambler. Construct a 127-bit payload that, when XORed with the LFSR output, produces all zeros, and explain why this is a denial-of-service against the line. Why does x^43+1 remove the practical threat?
5. T1 with plain AMI drops a 16-zero run. Describe exactly how B8ZS replaces the 8th zero with a bipolar violation and how the receiver distinguishes the violation from a real bit error.
6. You are designing a 10 Gb/s short-reach SerDes over DC-coupled board traces. Argue for 128B/130B + scrambling over 8B/10B, giving the effective payload rate of each and the bandwidth overhead.
7. Given a captured line waveform with transition density ~1.0 transition/bit and perfect DC balance but no obvious clock doubling, identify the code and rule out Manchester and NRZ.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Line code | "the voltage pattern" | The mapping from bits to a physical waveform that bakes in clock recovery, DC balance, and bandwidth efficiency |
| NRZ | "just use +1/−1" | Non-Return-to-Zero: level held for the whole bit cell; most bandwidth-efficient binary code, worst for runs and DC |
| NRZI | "transition means 1" | Non-Return-to-Zero Inverted: 1 = transition, 0 = no transition; USB uses it with bit stuffing after six 1s |
| Manchester | "the Ethernet code" | Data XORed with a 2× clock; one transition per bit; DC-balanced but needs B Hz for B bits/s |
| 4B/5B | "FDDI's code" | 4 data bits → 5-bit codeword with ≤3 consecutive 0s; 80% efficient; leaves control symbols; not DC-balanced |
| 8B/10B | "the IBM code" | 8→10 bits with running-disparity tracking; DC-balanced to ±2 bits, runs ≤5; PCIe/SGMII/SATA/USB3 |
| Running disparity | "the +/- counter" | Signed running sum of (1s − 0s); 8B/10B keeps it in {−1,+1} by choosing codeword polarity |
| AMI / bipolar | "the T1 code" | Alternate Mark Inversion: 0s are 0 V, 1s alternate +V/−V so 1s average to zero; needs B8ZS/HDB3 for zero runs |
| Bit stuffing | "USB's trick" | Forcing a transition by inserting a 0 after six consecutive 1s in NRZI; receiver strips it |
| Scrambling | "whitening" | XORing data with a PRBS LFSR sequence to randomize the spectrum; linear, so vulnerable to killer packets |
| Killer packet | "a malicious frame" | A payload equal to the scrambler's PRBS that XORs to all zeros and drops a SONET/POS link |
| Baud rate | "the speed" | Symbol rate (transitions/s); equals bit rate only when each symbol carries one bit; distinct from bit rate |

## Further Reading

- **IEEE 802.3-2022** Clause 1 (10 Mb/s Manchester baseband), Clause 24 (100BASE-TX 4B/5B + MLT-3), Clause 36 (1000BASE-X 8B/10B).
- **ANSI X3.230-1994** — Fibre Channel Physical Interface (FC-0/FC-1), defining the 8B/10B implementation used by FC, PCIe, and SATA.
- **Widmer & Franaszek**, "A DC-Balanced, Partitioned-Block, 8B/10B Transmission Code," IBM J. Research & Development, 27(5), 1983 — the original 8B/10B paper.
- **ANSI T1.403** — DS1 metallic interface, defining AMI line code and the 15-zero density rule; **T1.408** for B8ZS.
- **ITU-T G.703 / G.824** — E1 interface and HDB3 coding.
- **ITU-T G.707 / G.783** — SONET/SDH scrambling polynomial x^7+x^6+1.
- **Malis & Simpson**, "PPP over SONET/SDH," RFC 1619 (1994) and the update in RFC 2615 — the killer-packet vulnerability history.
- **USB 2.0 Specification**, Chapter 7 (transceiver): NRZI encoding and the six-consecutive-1s bit-stuff rule.
- **PCI Express Base Specification 2.0** §4.2 (8B/10B); **PCIe 3.0** §4.2 (128B/130B + scrambling).
- Tanenbaum, Feamster & Wetherall, *Computer Networks*, 6th ed., §2.5.1 "Baseband Transmission."
