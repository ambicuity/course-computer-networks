# Passband Transmission to Time Division Multiplexing

> Baseband sends bits starting at 0 Hz; **passband** transmission shifts the signal up to a band `S` to `S+B` Hz so it can ride a carrier, fit a regulatory allocation, and coexist with other signals. Because Nyquist and Shannon depend only on *bandwidth* `B`, not absolute frequency, shifting up costs nothing in capacity. Bits are impressed on the carrier by varying amplitude (**ASK**), frequency (**FSK**), phase (**PSK/BPSK/QPSK**), or amplitude-and-phase together (**QAM-16, QAM-64**, 4 and 6 bits/symbol). A **Gray code** maps bits to constellation points so a one-symbol slip causes only a one-bit error. Once one signal rides a carrier, you share a line: **FDM** gives each user a frequency band (voice = 3100 Hz usable + 900 Hz guard = 4000 Hz allocated), **OFDM** packs orthogonal subcarriers with no guard band (802.11a/g/n/ac, DSL, LTE), and **TDM** gives each user the whole band in a fixed round-robin slot (T1 = 1.544 Mb/s, E1 = 2.048 Mb/s, GSM). **STDM** assigns slots on demand — packet switching by another name.

**Type:** Learn
**Languages:** Python (stdlib), signal diagrams
**Prerequisites:** Bandwidth, Nyquist and Shannon limits, baseband line codes (earlier Phase 2 lessons)
**Time:** ~75 minutes

## Learning Objectives

- Explain why passband transmission carries the same information as baseband, and state the antenna-size and regulatory reasons engineers shift signals up in frequency.
- Compute bits/symbol and bit rate for ASK, BPSK, QPSK, QAM-16, and QAM-64, and explain why Gray coding bounds a symbol error to a single bit error.
- Lay out an FDM plan for voice-grade channels using the 3100/4000 Hz usable/allocated split, and explain what a guard band protects against.
- Contrast OFDM orthogonal subcarriers (zero-crossing at neighbours' centres) with classic FDM guard bands.
- Build a TDM round-robin multiplexer at the sum bit rate, and distinguish fixed-slot TDM from statistical STDM (packet switching).
- Use `code/main.py` to generate a Gray-coded QAM constellation, an FDM band plan, and a TDM aggregate frame, and verify each against the model.

## The Problem

You are bringing up a microwave backhaul link that carries 28 voice circuits between two cell sites. The radio reports a clean RF carrier and full transmit power, yet the far end logs a steady ~1% bit error rate that climbs whenever it rains. Voice calls sound garbled but never fully drop. Layer 3 looks fine — pings succeed, the routing table is stable — so the on-call network engineer first blames "the application."

It is not the application. The symptom lives in the physical layer's modulation and multiplexing. The radio runs QAM-64 (6 bits/symbol) to hit its rated throughput; rain fade lowers the signal-to-noise ratio, the dense constellation's points blur together, and the receiver picks adjacent symbols. Whether that costs you 1 bit or 6 bits per slipped symbol depends on whether the bits were Gray coded. Whether one fading circuit corrupts its neighbours depends on guard bands and slot synchronisation. To diagnose this you have to reduce a vague "calls sound bad" complaint into constellation order, SNR margin, bits-per-symbol, and the multiplexing scheme — exactly the mechanisms in this lesson.

## The Concept

Source: `chapters/chapter-02-the-physical-layer.md`, the "Digital Modulation and Multiplexing" section (passband transmission, FDM/OFDM, TDM/STDM). See the flow diagram in `assets/passband-transmission-to-time-division-multiplexing.svg`.

### Baseband versus passband

A **baseband** signal occupies `0` to `B` Hz — it is the raw line code, and its lowest meaningful frequency is essentially DC. A **passband** signal occupies an arbitrary band `S` to `S+B` Hz centred on a carrier. Engineers shift up for concrete reasons:

- **Antenna physics.** A practical antenna must be a useful fraction (often a quarter) of the wavelength. At 3 kHz audio the wavelength is 100 km — no one builds a 25 km antenna. At 900 MHz it is 33 cm, so a quarter-wave antenna is ~8 cm.
- **Regulation and coexistence.** Spectrum regulators (FCC, ITU) hand you a band; you transmit inside it and nowhere else.
- **Sharing.** Putting different signals in different bands lets them share one medium.

The capacity argument is what makes this free: Nyquist (`max symbol rate = 2B`) and Shannon (`C = B·log2(1+S/N)`) both depend only on the *width* `B`, never on the absolute centre frequency. A 0–3100 Hz voice channel shifted to 60,000–63,100 Hz carries identical information. The receiver mixes it back down to baseband to detect symbols.

### Impressing bits on the carrier

Digital modulation varies one or more carrier properties per symbol:

| Scheme | What varies | Symbols | Bits/symbol | Note |
|---|---|---|---|---|
| ASK (Amplitude Shift Keying) | amplitude | 2 | 1 | e.g. on/off keying |
| FSK (Frequency Shift Keying) | frequency | 2+ | 1+ | two or more tones |
| BPSK (Binary PSK) | phase (0°/180°) | 2 | 1 | "binary" = 2 phases, not 2 bits |
| QPSK (Quadrature PSK) | phase (45/135/225/315°) | 4 | 2 | = QAM-4 |
| QAM-16 | amplitude + phase | 16 | 4 | square 4×4 constellation |
| QAM-64 | amplitude + phase | 64 | 6 | square 8×8 constellation |

Frequency and phase cannot both be modulated independently because frequency is the rate of change of phase. Practical high-order schemes therefore modulate **amplitude and phase together** as independent I (in-phase) and Q (quadrature) axes — which is why constellations look like square grids, not concentric rings: it is easier to build electronics that set an `(I, Q)` pair than an `(amplitude, angle)` pair.

`bit_rate = symbol_rate × bits_per_symbol`. The worked example in `code/main.py` holds the symbol rate at 1,000,000 baud and shows BPSK → 1 Mb/s, QPSK → 2 Mb/s, QAM-16 → 4 Mb/s, QAM-64 → 6 Mb/s, QAM-256 → 8 Mb/s. Denser constellations buy throughput but pack points closer, so they need a higher SNR — the rain-fade trap from The Problem.

### Constellations and Gray coding

A **constellation diagram** plots each symbol as a point in the I/Q plane; phase is the angle to the origin, amplitude is the distance. The danger is bit assignment. If neighbouring points `0111` and `1000` are adjacent and the receiver slips one symbol, **all four bits flip**. A **Gray code** assigns labels so that any two horizontally or vertically adjacent points differ in exactly **one** bit position. Now the expected error — decoding to a near neighbour — costs a single bit.

`code/main.py` builds the constellation by Gray-coding each axis independently (`gray = n XOR (n>>1)`) and concatenating the I and Q halves, then `verify_gray_adjacency()` proves the one-bit property holds for every neighbour pair. The SVG shows the Gray-labelled QAM-16 grid; note the bottom row reads `0000 0001 0011 0010` — successive labels differ by one bit.

### FDM: share by frequency

**FDM (Frequency Division Multiplexing)** gives each user exclusive ownership of a frequency band for all time. AM radio is the canonical example: ~500–1500 kHz of spectrum sliced into station channels with enough separation to prevent interference.

The classic telephone example multiplexes voice-grade channels: filters limit usable bandwidth to **3100 Hz**, but **4000 Hz** is allocated per channel. The extra **900 Hz is the guard band**, which keeps channels separated because real filters lack sharp edges — a spike at one channel's edge leaks into its neighbour as nonthermal noise. `plan_fdm()` stacks three channels from 60 kHz: usable 60.0–63.1, 64.0–67.1, 68.0–71.1 kHz. Spectral efficiency is `9300 / 12000 = 77.5%` — the guard bands are pure overhead.

### OFDM: orthogonal subcarriers, no guard bands

For digital data you can do better. **OFDM (Orthogonal Frequency Division Multiplexing)** divides the band into many tightly packed subcarriers, each carrying data (often with QAM). The subcarriers overlap, but each one's frequency response is **zero at the centre of every neighbour**, so sampling a subcarrier at its centre frequency sees no interference from neighbours. Instead of many frequency guard bands, OFDM needs a small **guard time** (cyclic prefix) that repeats part of the symbol so the orthogonality holds. The whole set is implemented efficiently as a Fourier transform (IFFT/FFT) across all subcarriers rather than modulating each separately. OFDM is used in 802.11a/g/n/ac/ax Wi-Fi, DSL, cable, power-line networking, and 4G/5G cellular. A bonus: a high-rate stream is split into many low-rate parallel substreams, so a few badly faded subcarriers can be dropped while the rest survive.

### TDM: share by time

**TDM (Time Division Multiplexing)** flips the axis: users take turns round-robin, each getting the **entire bandwidth** for a short slot. Bits from each input land in a fixed time slot and feed one aggregate stream running at the **sum rate** of all inputs. This requires the streams to be synchronised in time; small **guard times** (analogous to FDM guard bands) absorb timing jitter.

`tdm_multiplex()` interleaves three byte streams round-robin: slot 0 → stream A, slot 1 → stream B, slot 2 → stream C, repeat. Crucially the demo shows an **idle slot padded with `0x00`** when stream B runs short — fixed TDM reserves the slot whether or not the tributary has data. Real-world TDM hierarchies: **T1** carries 24 voice channels at 1.544 Mb/s, **E1** carries 32 at 2.048 Mb/s; GSM uses TDM within each frequency carrier.

### STDM: TDM on demand

**STDM (Statistical Time Division Multiplexing)** keeps the time-slot idea but assigns slots according to **demand statistics**, not a fixed schedule. An idle tributary gets no slot; a busy one gets more. The textbook's blunt summary: *STDM is packet switching by another name.* This is the conceptual bridge from circuit-style physical multiplexing to the packet networks of later phases.

## Build It

1. Read `code/main.py` end to end. Map each function to a concept above: `build_qam` / `verify_gray_adjacency` (constellation + Gray code), `bit_rate` (rate math), `plan_fdm` (FDM band plan), `tdm_multiplex` / `tdm_demultiplex` (TDM).
2. Run `python3 main.py`. Confirm `Gray-adjacency-1bit=True` for QPSK, QAM-16, and QAM-64.
3. Change the symbol rate in the bit-rate loop to a real radio figure (say 7,000,000 baud) and read off the QAM-64 throughput — that is the rated capacity the rain fade is eroding.
4. Add a `QAM-256` (8 bits/symbol) branch to the modulation loop and confirm `build_qam` and Gray adjacency still hold for an even-power-of-two order.
5. Break Gray coding on purpose: replace `gray_encode(col)` with the raw `col` and re-run `verify_gray_adjacency`; watch it report `False` and reason about how many bits a symbol slip now costs.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Identify the modulation order | Radio config / link report showing QAM-N | You can state bits/symbol and the SNR it demands |
| Explain a rain-fade BER rise | Before/after SNR, constellation density, Gray-code status | Hypothesis predicts ~1 bit per slipped symbol under Gray coding |
| Validate an FDM plan | Channel start/stop frequencies and guard bands | No two usable bands overlap; guard ≥ 900 Hz; efficiency reported |
| Distinguish OFDM from FDM | Subcarrier spacing, cyclic prefix vs guard band | You can say why OFDM needs guard *time*, not guard *bands* |
| Read a TDM aggregate frame | Slot order and per-slot stream id | Demux recovers every tributary; idle slots identified as pad |
| Decide TDM vs STDM | Whether slots are fixed or demand-driven | You name STDM as packet switching for bursty traffic |

## Ship It

Produce one reusable artifact under `outputs/`:

- A QAM constellation + Gray-code reference card (export from `build_qam`).
- An FDM band-plan worksheet for a given channel count and base frequency.
- A TDM vs STDM decision runbook keyed on traffic burstiness.
- A modulation-order vs required-SNR cheat sheet for link budgeting.

Start from `outputs/prompt-passband-transmission-to-time-division-multiplexing.md` and back it with output from `code/main.py`.

## Exercises

1. A radio runs at 5 Msymbol/s. Compute its throughput under QPSK, QAM-16, and QAM-64 using `bit_rate`. The link must deliver 24 Mb/s — which is the lowest-order constellation that meets it, and why prefer the lowest?
2. During rain fade the receiver downshifts from QAM-64 to QPSK. By what factor does throughput drop, and why does this *improve* the bit error rate? Tie your answer to constellation point spacing.
3. Modify `verify_gray_adjacency` to also count bit errors for a *non-Gray* assignment. For QAM-16, what is the worst-case bit error count for a single adjacent-symbol slip, and what is it under Gray coding?
4. Plan an FDM stack for 12 voice channels starting at 60 kHz. What is the total occupied span, the usable bandwidth, and the spectral efficiency? How much spectrum is lost to guard bands alone?
5. Three streams feed a TDM mux at 8, 8, and 8 kb/s. What is the aggregate rate? Stream 2 then goes idle for half its slots — how much capacity is wasted under fixed TDM, and how would STDM recover it?
6. Explain to a colleague why shifting a 0–3100 Hz voice channel up to 60,000–63,100 Hz does not change how many bits/second it can carry, citing the Nyquist and Shannon formulas.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Passband | "the high-frequency one" | A signal occupying band `S` to `S+B` Hz on a carrier; same capacity as baseband because only bandwidth `B` matters |
| Baseband | "the raw signal" | A signal occupying `0` to `B` Hz, detected after down-conversion |
| QAM-64 | "fast Wi-Fi mode" | 64-point amplitude+phase constellation, 6 bits/symbol, needs high SNR |
| Constellation diagram | "the dot picture" | I/Q plot where angle = phase, distance = amplitude, each dot a symbol |
| Gray code | "some encoding trick" | Bit-to-symbol map where adjacent symbols differ in 1 bit, bounding a symbol slip to a single bit error |
| Guard band | "wasted spectrum" | Spectral gap (e.g. 900 Hz of a 4000 Hz voice slot) that absorbs non-ideal filter roll-off |
| FDM | "split by frequency" | Each user owns a frequency band for all time (AM radio, DSL, cellular) |
| OFDM | "the Wi-Fi/LTE one" | Orthogonal subcarriers, zero-crossing at neighbours' centres, cyclic-prefix guard time instead of guard bands |
| TDM | "split by time" | Round-robin fixed time slots; aggregate runs at the sum rate (T1, E1, GSM) |
| STDM | "smart TDM" | Slots assigned by demand, not schedule — packet switching by another name |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks* (6th ed.), Chapter 2, "Digital Modulation and Multiplexing."
- ITU-T G.711 — PCM voice coding (the 64 kb/s tributaries TDM carries).
- ITU-T G.704 / ANSI T1.107 — E1/T1 framing and the 32/24-channel TDM hierarchy.
- IEEE 802.11a-1999 — first widely deployed OFDM Wi-Fi PHY (52 subcarriers, 64-point IFFT).
- 3GPP TS 45.002 — GSM multiframe structure (TDM over FDM carriers).
