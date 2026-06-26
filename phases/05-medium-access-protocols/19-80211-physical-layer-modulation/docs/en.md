# 802.11 physical layer: DSSS, HR-DSSS/CCK, OFDM, and MIMO across a/b/g/n

> Wi-Fi's MAC barely changed from 1997 to 2009, but the radio under it changed four times. The original 802.11 (1997) defined direct-sequence spread spectrum (DSSS) at 1 and 2 Mbps in the 2.4-GHz ISM band using an 11-chip Barker sequence to spread each bit. 802.11b (1999) stayed in 2.4 GHz and pushed to 5.5 and 11 Mbps by switching to high-rate DSSS with Complementary Code Keying (CCK) — same chip rate, denser codes. 802.11a (1999) jumped to 5 GHz and rebuilt the air interface around OFDM: 52 subcarriers (48 data + 4 pilots) per 20-MHz channel, 3.2 us useful symbol plus a 0.8 us cyclic prefix for a 4 us OFDM symbol, and eight data rates from 6 to 54 Mbps via BPSK up to 64-QAM with convolutional coding. 802.11g (2003) copied the OFDM air interface back into 2.4 GHz for b compatibility. 802.11n (2009) added MIMO (up to 4 spatial streams), channel bonding (20 to 40 MHz), and a short 400-ns guard interval, lifting the headline rate to 600 Mbps. This lesson dissects each generation, ties the math to chip and symbol timing in `code/main.py`, and shows how a real link picks a rate from measured RSSI.

**Type:** Learn
**Languages:** Python
**Prerequisites:** 802.11 architecture (MAC, CSMA/CA, DCF), basic modulation (BPSK, QPSK, QAM), spread spectrum concept
**Time:** ~80 minutes

## Learning Objectives

- Sketch the DSSS transmit chain for 1 and 2 Mbps, name the Barker-11 chip sequence, and explain why spreading satisfies the FCC's ISM power rule.
- Compare HR-DSSS/CCK (802.11b) to plain DSSS by writing out the 5.5 and 11 Mbps symbol-to-chip mappings and naming the CCK codebook structure.
- Draw the 802.11a/g OFDM physical-layer parameters: 20 MHz channel, 64-point IFFT, 52 used subcarriers (48 data + 4 pilots), 0.8 us useful symbol, 0.4 us cyclic prefix, 4 us OFDM symbol, and the 6/9/12/18/24/36/48/54 Mbps rate ladder.
- Compute an 802.11n link rate for a given MCS index, channel width (20/40 MHz), guard interval (800/400 ns), and number of spatial streams, and explain why 600 Mbps is the 4x4, 40 MHz, short-GI, 64-QAM ceiling.
- Predict the rate an 802.11g client will negotiate when joining an 802.11n BSS, and identify the protection mechanism (CTS-to-self or RTS/CTS) the AP must add so that the OFDM frame is not clobbered by a hidden b station.
- Read a Wi-Fi rate-versus-SNR curve and explain why rate adaptation picks 54 Mbps only above ~25 dB SNR and falls back to 6 Mbps near the noise floor.

## The Problem

A site survey of a crowded office building shows the 2.4-GHz band saturated with overlapping APs on channels 1, 6, and 11, plus a microwave oven radiating broadband noise during lunch. The 5-GHz band shows wide empty channels. Two questions follow:

1. "Can we move the SSID to 5 GHz and fix the throughput problem?"
2. "We have a mixed fleet: some clients are 802.11g only, some are 802.11n. When a g client joins the n AP, what rate do they negotiate? Will the whole network slow down?"

The first answer lives in physical-layer tradeoffs: 5 GHz has shorter range, more free spectrum, and wider channels; 2.4 GHz punches through walls better but is congested. The second answer lives in 802.11n's HT-protection rules: a g client forces the AP to use CTS-to-self (or RTS/CTS) to mask the OFDM frame from hidden b clients, and the legacy client's rate caps the protection header. Once you can read the rate table and the protection rules, the answers fall out of the air-interface, not out of policy.

## The Concept

The 802.11 physical layer evolved by replacing the radio while keeping the MAC nearly identical. Four generations, four radios:

| Generation | Year | Band | Radio technique | Rates (Mbps) |
|---|---|---|---|---|
| 802.11 (legacy) | 1997 | 2.4 GHz | DSSS (Barker-11) | 1, 2 |
| 802.11b | 1999 | 2.4 GHz | HR-DSSS with CCK | 1, 2, 5.5, 11 |
| 802.11a | 1999 | 5 GHz | OFDM (52 subcarriers) | 6, 9, 12, 18, 24, 36, 48, 54 |
| 802.11g | 2003 | 2.4 GHz | OFDM (CCK fallback) | 6..54 + 1, 2, 5.5, 11 |
| 802.11n | 2009 | 2.4 / 5 GHz | MIMO-OFDM (up to 4x4) | 6.5 .. 600 |

### The ISM bands and channel numbering

All four PHYs use the Industrial, Scientific, and Medical (ISM) radio bands — license-free slices of spectrum set aside for low-power devices. 802.11 lives in two slices:

| Band | Frequency range | Channel width | 802.11 channels |
|---|---|---|---|
| 2.4 GHz ISM | 2.400 - 2.4835 GHz | 20 MHz, channels 5 MHz apart | US: 1-11, EU: 1-13, Japan: 1-14 |
| 5 GHz U-NII | 5.150 - 5.825 GHz | 20/40 MHz | UNII-1, -2, -2E, -3, -4 sub-bands |

The channel center frequency is `2412 + 5 * (channel - 1)` MHz for 2.4 GHz (e.g. channel 6 is 2.437 GHz). Channels are spaced 5 MHz apart but each 802.11 transmission occupies 20 MHz, so in 2.4 GHz only channels **1, 6, and 11** are non-overlapping. 2.4 GHz has shorter wavelength (~12.5 cm) and propagates through walls better, but is shared with Bluetooth, microwave ovens, ZigBee, and cordless phones. 5 GHz is absorbed more by walls but is wide enough for 23+ non-overlapping 20-MHz channels, plus 40 MHz bonding.

### 802.11 legacy DSSS: spreading 1 bit across 11 chips

The original 802.11 direct-sequence spread spectrum mode transmits each user bit as an 11-chip Barker sequence:

```
+1 -1 +1 +1 -1 +1 +1 +1 -1 -1 -1
```

One bit -> 11 chips. Chips run at **11 Mchip/s**, so 1 Mbps maps to 1 bit per 11 chips with BPSK, 2 Mbps to 2 bits per 11 chips with QPSK. The Barker code has very low autocorrelation except at zero offset, which lets the receiver lock onto the start of a frame with a matched filter even at 10 dB below the noise floor — that is the "processing gain" the FCC requires in exchange for license-free operation.

### 802.11b HR-DSSS and Complementary Code Keying

802.11b keeps the 11 Mchip/s chip rate and the 2.4-GHz band, but replaces the Barker-11 spreading with **Complementary Code Keying (CCK)** for the two new rates:

- **5.5 Mbps** — 4 bits per symbol, each symbol mapped to an 8-chip CCK code word.
- **11 Mbps** — 8 bits per symbol, each symbol mapped to an 8-chip CCK code word.

The CCK code book is built from an 8-chip template, phase-rotated by a per-symbol sequence that encodes the user bits. The result is the same 11 Mchip/s chip rate and 22 MHz channel footprint as legacy DSSS, but more user bits per symbol. A 1 or 2 Mbps DSSS frame from a legacy 802.11 device still decodes — the backward compatibility that kept 802.11b shipping into homes for a decade.

### 802.11a/g OFDM: 52 subcarriers, 4 microseconds per symbol

OFDM is the air interface that everything from 802.11a onward shares. The transmitter takes a stream of bits, groups them into symbols, and modulates each symbol onto one of 52 orthogonal subcarriers simultaneously using a 64-point inverse FFT. The 802.11a/g OFDM parameters are exactly:

| Quantity | Value |
|---|---|
| Channel bandwidth | 20 MHz |
| FFT size | 64 |
| Used subcarriers | 52 (48 data + 4 pilots) |
| Subcarrier spacing | 312.5 kHz (= 20 MHz / 64) |
| Useful symbol (T<sub>u</sub>) | 3.2 us (= 1 / 312.5 kHz) |
| Cyclic prefix (T<sub>cp</sub>) | 0.8 us |
| Total OFDM symbol (T<sub>sym</sub>) | 4.0 us |
| Code rates | 1/2, 2/3, 3/4 |
| Modulations | BPSK, QPSK, 16-QAM, 64-QAM |

Each data subcarrier holds 1, 2, 4, or 6 bits per symbol (BPSK/QPSK/16-QAM/64-QAM), and a convolutional coder punctures the bit stream to 1/2, 2/3, or 3/4. The four pilot subcarriers transmit a known pseudo-random sequence so the receiver can correct residual phase and frequency offsets.

The **cyclic prefix** is the trick that makes OFDM survive multipath. The last 0.8 us of every 3.2 us useful symbol is copied to the front. A delayed echo of the previous symbol, arriving while the receiver is processing the next one, looks like a circular convolution and the FFT absorbs it cleanly — provided the echo delay is shorter than 0.8 us (~240 m of excess path, more than enough for an office).

The **data rate** is then:

```
rate = 48 * (bits per symbol) * code_rate / 4.0e-6
     = 12e6 * (bits per symbol) * code_rate
```

| MCS | Modulation | Code rate | Data rate (Mbps) |
|---|---|---|---|
| 1 | BPSK | 1/2 | 6 |
| 2 | BPSK | 3/4 | 9 |
| 3 | QPSK | 1/2 | 12 |
| 4 | QPSK | 3/4 | 18 |
| 5 | 16-QAM | 1/2 | 24 |
| 6 | 16-QAM | 3/4 | 36 |
| 7 | 64-QAM | 2/3 | 48 |
| 8 | 64-QAM | 3/4 | 54 |

The 5 GHz band that 802.11a uses is wider and quieter than 2.4 GHz, but the higher carrier frequency is absorbed more by walls and water, so an 802.11a cell is typically a quarter the radius of an 802.11b cell. 802.11g re-uses the same OFDM air interface in 2.4 GHz for better propagation, at the cost of more interference.

### 802.11n MIMO-OFDM: spatial streams, 40 MHz, short GI

802.11n keeps the OFDM air interface of 802.11a/g and adds three knobs:

- **Multiple spatial streams** — up to 4 transmit and 4 receive antennas, encoding independent data streams onto the same OFDM symbols. A `4x4` MIMO link sends four parallel streams; the receiver uses the channel matrix to separate them.
- **Channel bonding** — double the channel from 20 MHz to 40 MHz, packing 108 subcarriers (104 data + 4 pilots) into a single OFDM symbol. The useful symbol stays at 3.2 us, the cyclic prefix still adds 0.8 us, but the bit rate doubles because there are twice as many data subcarriers.
- **Short guard interval** — cut the cyclic prefix from 0.8 us to 0.4 us. The total OFDM symbol drops from 4.0 us to 3.6 us, a 10% throughput boost. The trade-off: echoes longer than 0.4 us leak into the next symbol — fine in a small cell, marginal in a warehouse.

The headline 600 Mbps is the MCS-31 / 40 MHz / short-GI / 4-stream maximum:

```
600 Mbps = 4 streams * (108 subcarriers * 6 bits * 5/6 code) / 3.6 us
         = 4 * 150 Mbps
```

MCS-31 is 64-QAM with 5/6 convolutional coding — usable only above ~30 dB SNR with clean line-of-sight. MCS-0 (BPSK 1/2, 1 stream, 20 MHz, long GI) is the floor at 6.5 Mbps.

The 802.11n preamble extends with **HT-SIG** and **HT-capabilities** fields that signal the channel width, the number of spatial streams, the GI choice, and the MCS. Legacy 802.11a/g devices see the HT preamble as a "non-802.11a" signal and defer, so mixed deployments are still possible.

### Backward compatibility and protection

The MAC must keep a 1997 radio working in the same BSS as a 2009 radio:

- **Mixed-mode preamble** — a legacy 802.11a/g short preamble trains the receiver, then the HT preamble carries the new fields. The legacy station reads the L-SIG length, defers for that long, and the HT station continues.
- **Protection (CTS-to-self or RTS/CTS)** — when a 802.11b or 802.11g-only station is associated, the AP transmits a CTS-to-self (or RTS/CTS exchange) at the legacy rate (1 or 2 Mbps DSSS) before every OFDM frame. The CTS carries a NAV that reserves the channel for the OFDM frame duration. A hidden 802.11b station sees the CTS, updates its NAV, and stays quiet. The cost is one extra round trip and 1-2 Mbps signalling on every frame.

If a BSS has *only* 802.11n stations the AP drops the protection and runs in **HT-greenfield** mode — no legacy preamble, no CTS-to-self — for the best throughput.

### Rate adaptation

The radio constantly measures frame error rate and signal quality, then steps the MCS up or down. Minstrel (Linux) and proprietary firmware algorithms do the same thing: try a faster rate; if two or three frames in a row are lost, drop back one or two MCS levels; if 50 or so frames succeed, try the next one up. There is no standard for *how* to adapt — only for what rates are offered.

## Build It

`code/main.py` is a stdlib-only Python module that lets you model the four generations, generate a Barker-11 chip stream, time an OFDM symbol, and pick a rate from a measured RSSI.

1. **Run the rate selector** — `python3 code/main.py select 2.4 -65` picks an 802.11g MCS for a 2.4-GHz network at -65 dBm RSSI. Try `--band 5 --standard n --rssi -55 --streams 2 --width 40` to see 802.11n pick an HT MCS.
2. **Generate a Barker-11 chip stream** — `python3 code/main.py barker 0xABC` spreads a 12-bit hex payload into 132 chips. Compare to the OFDM path and notice the difference between "1 bit -> 11 chips" and "1 bit -> 1/48 of an OFDM symbol."
3. **Time an OFDM symbol** — `python3 code/main.py ofdm` shows the 3.2 us useful symbol + 0.8 us cyclic prefix = 4.0 us total. Toggle the short-guard option to see 3.6 us.
4. **Compute MIMO capacity** — `python3 code/main.py mimo 4 40 64-QAM 400ns` confirms the 600-Mbps 4x4 ceiling and the ~150 Mbps per-stream number.
5. **Inspect the rate table** — `python3 code/main.py table n` prints all 128 802.11n MCS entries, indexed by MCS number, channel width, GI, and stream count.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Pick a DSSS rate for 1 Mbps | Barker-11 chip stream | 11 chips per bit, BPSK modulation, 11 Mchip/s |
| Pick a CCK rate for 11 Mbps | 8-chip code word, 8 bits per symbol | Modulation is QPSK-like, code is CCK not Barker |
| Read an OFDM parameter set | 52 subcarriers, 4 us symbol, 20 MHz channel | Subcarrier spacing 312.5 kHz, 48 data + 4 pilots, 0.8 us GI |
| Compute 802.11g max rate | 64-QAM, 3/4 code, 48 data subcarriers | 54 Mbps exactly |
| Compute 802.11n 600 Mbps ceiling | 4 streams, 40 MHz, short GI, 64-QAM 5/6 | 4 * 150 = 600 Mbps |
| Spot a mixed-mode rate drop | 802.11g joins an 802.11n BSS | AP uses CTS-to-self, throughput overhead ~30% |
| Pick a rate from RSSI | -67 dBm on 5 GHz | Probably MCS-7 (65 Mbps) or MCS-8 (78 Mbps) |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **rate-vs-SNR cheat sheet** listing the minimum RSSI for each MCS in 802.11g and 802.11n, with the channel-width and stream-count factors built in.
- A **Barker-11 chip-sequence generator** (`code/main.py`) wired to a small encoder script you can run on a known input to verify the chip stream.
- A **short note on protection overhead** explaining when an AP should enable CTS-to-self vs HT-greenfield, and the throughput penalty of each.

Start from `outputs/prompt-80211-physical-layer-modulation.md` if present, or create `outputs/wifi-phy-rate-adaptation-note.md`.

## Exercises

1. A 2.4-GHz site survey shows 27 access points visible on channels 1-13, with most traffic on 1, 6, and 11. Sketch a channel plan for a 5-floor office and explain why you would (or would not) turn off 2.4-GHz radios on the APs.
2. An 802.11b client associates with an 802.11n AP. Describe the protection frame the AP must transmit before every OFDM data frame, the legacy rate it uses, and the approximate throughput penalty on a 1500-byte frame.
3. The Barker-11 sequence is `+1 -1 +1 +1 -1 +1 +1 +1 -1 -1 -1`. A 1 Mbps DSSS transmitter sends the bits `1 0 1 1 0`. Write out the 55-chip on-air sequence (one bit at a time, starting with the bit 1), and explain why a receiver with the wrong phase offset will still lock on.
4. An 802.11n AP is configured for 40-MHz channels on the 5-GHz band. The first OFDM symbol is sent with a 0.4 us short guard interval. How many microseconds does one symbol take end-to-end, and what is the maximum throughput of a single 64-QAM 5/6 stream?
5. A 4x4 MIMO link at MCS-31 has a maximum PHY rate of 600 Mbps. The AP sends 1500-byte frames and the TCP goodput is 380 Mbps. List three sources of the 220 Mbps gap.
6. An 802.11a/g OFDM symbol carries 48 coded bits per subcarrier at 64-QAM 3/4. Show that the maximum data rate is 54 Mbps, then compute the same rate for 40-MHz channel bonding with a short guard interval and explain why the doubling is *not* exactly 2x.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| ISM band | "the Wi-Fi spectrum" | 2.4-GHz and 5-GHz Industrial/Scientific/Medical license-free bands where 802.11 is allowed to radiate up to ~1 W (50 mW typical) |
| DSSS | "spread the bit" | Direct-sequence spread spectrum; one user bit -> 11 chips of Barker-11 code, 11 Mchip/s |
| Barker-11 | "the original chip code" | `+1 -1 +1 +1 -1 +1 +1 +1 -1 -1 -1`, low autocorrelation except at zero offset |
| HR-DSSS | "802.11b's radio" | High-rate DSSS that keeps the 11 Mchip/s chip rate but uses CCK for 5.5/11 Mbps |
| CCK | "Complementary Code Keying" | Code book of 8-chip codes used by 802.11b to encode 4 or 8 bits per symbol |
| OFDM | "52 subcarriers in parallel" | Orthogonal FDM: 52 subcarriers (48 data + 4 pilots) per 20-MHz channel, 0.8 us GI + 3.2 us symbol = 4 us |
| Cyclic prefix | "the safety tail" | 0.8 us copy of the end of the useful symbol prepended to absorb multipath echoes |
| Subcarrier spacing | "312.5 kHz" | 20 MHz / 64 FFT bins; the OFDM subcarrier width that makes them orthogonal |
| Convolutional code | "the FEC" | Punctured convolutional code at rates 1/2, 2/3, 3/4 (and 5/6 in 802.11n) |
| MCS | "the rate level" | Modulation and Coding Scheme: pairs of (modulation, code rate) used in 802.11a/g/n |
| MIMO | "more antennas, more streams" | Multiple Input Multiple Output: up to 4 independent spatial streams on the same channel |
| Spatial stream | "an independent data path" | One data stream carried over a distinct RF path between transmit and receive antennas |
| Channel bonding | "40 MHz mode" | Doubling the channel width from 20 MHz to 40 MHz by stitching two adjacent 20-MHz channels |
| Short guard interval | "0.4 us GI" | Half-length cyclic prefix; trades multipath tolerance for 10% more throughput |
| Rate adaptation | "Minstrel" | Per-frame choice of MCS, channel width, and stream count based on measured error rate |
| CTS-to-self | "the protection frame" | A CTS frame the AP sends at 1 or 2 Mbps DSSS to mask an OFDM frame from a hidden legacy station |
| HT-SIG | "the 802.11n signal field" | High-Throughput SIGNAL field in the 802.11n preamble: MCS, channel width, GI, stream count |

## Further Reading

- IEEE 802.11-2016, **Clause 17** (DSSS PHY), **Clause 18** (HR-DSSS PHY), **Clause 19** (OFDM PHY), **Clause 20** (HT PHY). The authoritative parameters: 52 subcarriers, 0.8 us CP, 3.2 us useful symbol, 4 us OFDM symbol, 11 Mchip/s Barker rate, 8-chip CCK codes, 600-Mbps 4x4 ceiling.
- Matthew Gast, *802.11n: A Survival Guide* (O'Reilly) and *802.11ac: A Survival Guide* — clearest walkthroughs of HT-SIG, channel bonding, and short-GI signaling.
- Daniel Halford et al., "802.11 with Multiple Antennas for Dummies," *ACM SIGCOMM Computer Communication Review* 40(1), 2010 — short introduction to the MIMO channel matrix and 802.11n's spatial-multiplexing mode.
- Perahia and Stacey, *Next Generation Wireless LANs: 802.11n and 802.11ac* (Cambridge) — the math behind OFDM subcarriers and the OFDM symbol timing budget.
- Tanenbaum and Wetherall, *Computer Networks* (5th ed.), Section 4.4.2 — the source chapter this lesson is based on.
