# The Local Loop: Modems, ADSL, and Fiber to Switching

> The local loop — the two-wire copper "last mile" from the telephone end office to the house — has carried analog voice for over 100 years, and three generations of technology have fought to push data over it. Voice lines are filtered to 300–3400 Hz (the 3-dB points), quoted as a 4000 Hz channel; modems run at 2400 baud and pack more bits per symbol with QAM and Trellis-Coded Modulation (TCM). V.34 reaches 33.6 kbps near the ~35 kbps Shannon wall; V.90 breaks it asymmetrically (56 kbps down / 33.6 kbps up) by removing one analog loop's quantization noise — capped at 56k by the one stolen signaling bit in 8-bit μ-law PCM at 8000 samples/s. ADSL bypasses the voice filter entirely: a DSLAM at the office and an ADSL modem at the home split 1.1 MHz into 256 channels of 4312.5 Hz each, run DMT (OFDM + QAM, 2–15 bits/symbol per channel by SNR), and reserve channel 0 for POTS and channels 1–5 as guard. G.dmt (1999) does 8 Mbps down; ADSL2+ doubles spectrum to 2.2 MHz for 24 Mbps. Fiber to the Home uses a passive optical network (PON): one fiber per ~100 houses, downstream broadcast plus upstream TDMA slots granted by the OLT after a ranging process. This lesson builds a Python tool that computes Nyquist/Shannon limits, DMT bit-loading, and PON scheduling so you can predict the rate a given loop will actually carry.

**Type:** Learn
**Languages:** Python (stdlib), signal diagrams
**Prerequisites:** Phase 2 lessons on Nyquist/Shannon limits, QAM constellations, and OFDM
**Time:** ~75 minutes

## Learning Objectives

- Derive why a 4000 Hz voice channel caps a telephone modem at 33.6 kbps and why V.90 reaches exactly 56 kbps (not 64 or 70).
- Lay out the ADSL DMT spectrum: 256 channels of 4312.5 Hz, channel 0 = POTS, 1–5 = guard, and how per-channel SNR sets bits/symbol.
- Trace the end-to-end ADSL equipment path: NID → splitter → ADSL modem at the home, splitter → DSLAM → ISP at the office.
- Explain the PON upstream collision problem and how ranging + TDMA grants solve it, versus the trivial downstream broadcast.
- Predict the maximum data rate for a given loop length, line SNR, and technology, and name the failure mode when a customer is "too far from the office."

## The Problem

A customer 4.2 km from the end office orders an "up to 24 Mbps" ADSL2+ plan and gets 1.5 Mbps, with the modem retraining (dropping and resyncing) several times an hour. The provisioning system says the line passed. Support blames the Wi-Fi. The real story is in the physical layer: at 4.2 km on Category 3 copper, the upper DMT channels above ~1 MHz are so attenuated their SNR can't carry even 2 bits/symbol, so the modem's bit-loading table zeroes them out. A nearby bridged tap or an AM radio station injects noise that swings the per-channel SNR, and when too many channels fall below the minimum SNR margin, the modem declares a loss of sync and retrains.

To diagnose this you cannot stay at the application layer. You need the loop's length, its per-channel SNR profile, and the technology's bit-loading rules — and you need to know that ADSL's promised rate is a *best case for lines within 1–2 km*. This lesson gives you the math and a script to turn "it's slow" into "channels 90–250 are dead at this loop length, so the achievable rate is X."

## The Concept

### The local loop and its filter

The local loop is the analog twisted pair from the end office to the premises — the "last mile," though it can be several kilometers. Where each loop terminates in the office, it historically passed through a filter that attenuates everything below 300 Hz and above 3400 Hz. The 300/3400 Hz cutoffs are the 3-dB points; with guard bands the channel is quoted as **4000 Hz** even though the usable span is ~3100 Hz. That artificial filter — optimized for human voice — is what makes telephone modems slow. The physics of the copper itself supports roughly **1 MHz**; the filter throws away 99.7% of it.

### Telephone modems: Nyquist, QAM, and TCM

A modem ("modulator-demodulator") converts bits to an analog signal the voice channel can carry and back. Nyquist says a perfect 3000 Hz line has no point sending faster than 6000 baud; in practice modems use **2400 baud** and win by carrying more bits per symbol. Larger constellations mean more bits but smaller spacing, so noise causes errors — high-speed standards spend symbols on **Trellis-Coded Modulation (TCM)** for error correction.

| Standard | Baud | Bits/symbol (data + check) | Rate | Note |
|---|---|---|---|---|
| 2400-bps | 2400 | 1 | 2.4 kbps | 0 V / 1 V, 1 bit |
| V.32 | 2400 | 4 + 1 | 9.6 kbps | 32-point constellation |
| V.32 bis | 2400 | 6 + 1 | 14.4 kbps | |
| V.34 | 2400 | 12 | 28.8 kbps | thousands of points |
| V.34 bis | 2400 | 14 | 33.6 kbps | at the Shannon wall |

The reason this series stops at 33.6 kbps is the **Shannon limit** for an average analog loop with this line quality: about **35 kbps**. Going faster with two analog loops would violate thermodynamics.

### Breaking 35 kbps: how V.90 reaches 56k

The 35 kbps limit assumes *two* analog loops, one at each end, each adding quantization noise. The core of the phone network is already digital. If the ISP takes a **direct digital feed** from the office, you eliminate one loop's analog-to-digital conversion noise and the SNR roughly doubles, lifting the downstream ceiling toward 70 kbps.

So why 56k, not 70k? Nyquist again. A voice channel is carried inside the network as **8000 PCM samples/second**, 8 bits each. In the U.S. (μ-law), **1 of those 8 bits may be robbed for signaling**, leaving 7 × 8000 = **56,000 bits/s** of user data. Europe (A-law) keeps all 8 bits — 64 kbps was possible — but to standardize internationally, 56k was chosen.

- **V.90 / V.92:** 56 kbps downstream (ISP→user, digital end), 33.6 / 48 kbps upstream (user→ISP, still analog). The asymmetry exists because the upstream still crosses a full analog loop, and because users download more than they upload. Between two home users on analog lines, the cap is still 33.6 kbps.

### ADSL: discrete multitone over the whole loop

The trick of xDSL is that a subscriber's loop is connected to a switch *without* the voice filter, exposing the full ~1.1 MHz. ADSL divides that into **256 independent channels of 4312.5 Hz** and runs **DMT (Discrete MultiTone)** — OFDM where each subcarrier carries its own QAM stream at ~4000 symbols/s.

```
Power
 |   ▁▁▁                    ▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁
 |  | 0 |   (1-5 guard)    |   upstream   ||   downstream   ...
 +--+---+-----------------+--------------+----------------------> kHz
    0   25                              1100
  POTS                  256 × 4.3125 kHz channels
```

Channel assignment and bit-loading rules:

| Element | Rule |
|---|---|
| Channel 0 | POTS (0–4000 Hz), so the existing phone still works |
| Channels 1–5 | unused guard, keeps voice and data from interfering |
| Per channel | QAM, line SNR monitored continuously |
| High-SNR channel | up to **15 bits/symbol** |
| Low-SNR channel | down to 2, 1, or **0 bits/symbol** (channel disabled) |
| Split | provider picks; a common split is **32 channels upstream**, rest downstream (the "A" in ADSL) |

| Standard | Year | Spectrum | Down / Up (best case) |
|---|---|---|---|
| G.dmt | 1999 | 1.1 MHz | 8 Mbps / 1 Mbps |
| ADSL2 | 2002 | 1.1 MHz | 12 Mbps / 1 Mbps |
| ADSL2+ | — | 2.2 MHz | 24 Mbps / — |
| G.lite (splitterless) | — | 1.1 MHz | 1.5 Mbps (less reliable) |

Those are best-case for lines within **1–2 km**. Bandwidth falls fast with distance (see `assets/the-local-loop-modems-adsl-and-fiber-to-switching.svg`), which is why the provider's chosen speed implies a service radius — distant customers get told they live "too far from the office." `code/main.py` implements the per-channel bit-loading: it walks the 256 channels, computes SNR after distance attenuation, and sums bits/symbol × 4000 sym/s to predict the real rate.

### ADSL equipment path

A technician installs a **NID (Network Interface Device)** marking the property boundary. A **splitter** separates the 0–4000 Hz POTS band (to phone/fax) from the data band (to the ADSL modem, which does the OFDM in DSP, reached over Ethernet/USB/802.11).

```
Customer premises                     End office
  Telephone ──┐                    ┌── Voice switch
              ├─ Splitter ── loop ─ Splitter ─┤
  ADSL modem ─┘   (>26 kHz)        └── DSLAM ── packets → ISP
```

At the office a matching splitter sends voice to the normal switch and the signal **above 26 kHz** to a **DSLAM (Digital Subscriber Line Access Multiplexer)**, which recovers bits, forms packets, and hands them to the ISP. This clean voice/data separation is why ADSL is cheap to deploy — buy a DSLAM and a splitter. **G.lite** drops the customer's splitter (no expensive "truck roll") and instead puts a microfilter at each jack: a low-pass (<3400 Hz) for phones, high-pass (>26 kHz) for the modem — at the cost of reliability, capping G.lite at 1.5 Mbps.

### Fiber to the Home and the PON

To beat copper's distance limits, carriers run optical fiber to (or near) the home — **FttH**, or **FttX** when copper covers the last short hop. The fiber local loop is **passive**: no powered amplifiers, just glass carrying light, which cuts cost and improves reliability.

Fibers from up to ~100 houses join into a single fiber to the office, forming a **PON (Passive Optical Network)**:

- **Downstream** — easy. The OLT broadcasts on one wavelength; **optical splitters** copy it to every house. Encryption ensures only the addressed house decodes it.
- **Upstream** — hard. On a second wavelength, houses share one fiber, can't hear each other, and would collide. The office (OLT) **grants TDMA time slots** to each house's ONU, and a **ranging** process pre-adjusts each house's transmit timing so bursts arrive synchronized (same idea as cable modems).

| PON type | Standard body | Typical rate |
|---|---|---|
| **GPON** (Gigabit-capable) | ITU | 2.4 Gbps down / 1.2–2.4 Gbps up |
| **EPON** (Ethernet PON) | IEEE | ~1 Gbps symmetric |

Even after splitting, fiber's bandwidth and low attenuation deliver these rates over **up to 20 km** — far past copper's "last mile" wall. `code/main.py` includes a PON scheduler that hands out upstream slots and shows why two simultaneous ONU bursts collide without grants.

## Build It

1. Read `code/main.py`. The `nyquist_rate`, `shannon_capacity`, and `modem_rate` functions reproduce the modem table above; run it and confirm V.34 lands at 28.8 kbps and the 56k derivation prints 7 × 8000.
2. Study `dmt_loadable_rate(loop_km, ...)`: it models loop attenuation rising with frequency and distance, computes each channel's SNR, maps SNR→bits/symbol (Shannon-gap rule, capped at 15), and sums the rate.
3. Run the demo at 1 km, 3 km, and 5 km and watch the achievable ADSL rate collapse — this is the "service radius" problem made concrete.
4. Read `pon_schedule`: feed it upstream requests from several ONUs and confirm it serializes them into non-overlapping slots; then call it without ranging to see a collision.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Explain a slow modem | Constellation size, baud, Shannon estimate | You state 33.6 kbps is the analog-loop Shannon wall, not a config bug |
| Justify 56k asymmetry | μ-law 8-bit, 1 robbed bit, 8000 sam/s | You compute 7×8000=56000 and explain the digital ISP feed |
| Diagnose short-rate ADSL | Loop length + per-channel SNR/bit table | You show which DMT channels zeroed out and the summed achievable rate |
| Explain ADSL retrains | SNR margin dropping channels below threshold | You tie loss-of-sync to crosstalk/noise pushing channels under min SNR |
| Reason about PON upstream | Grant table, ranging offsets | You show two ungranted ONUs collide and grants serialize them |

## Ship It

Produce one artifact under `outputs/`:

- A loop-rate calculator runbook (loop length + technology → predicted rate and limiting factor).
- A DMT bit-loading annotation: per-channel table (channel #, frequency, SNR, bits/symbol) for a sample line.
- A one-page PON upstream-scheduling diagram with the ranging/grant sequence.

Start from the output of `code/main.py` and the SVG in `assets/`.

## Exercises

1. A customer reports 33.6 kbps on a brand-new "56k" modem talking to another home user (also a modem on an analog line). Explain in one sentence why 56k is impossible for this call and what would have to change.
2. Using `dmt_loadable_rate`, find the approximate loop length (km) at which an ADSL2+ line drops below 4 Mbps achievable. State which channel range dies first and why (hint: attenuation rises with frequency).
3. A provider allocates 32 of the 250 usable DMT channels to upstream. Compute the rough upstream/downstream symbol-rate split and explain why this asymmetry is "the A in ADSL."
4. In a PON, two ONUs both have data ready at t=0. Walk through what the OLT does so the bursts don't collide, and explain what the ranging process measured beforehand.
5. A line passes provisioning but retrains 6 times an hour. Given the DMT SNR-margin model, propose two physical-layer causes and the per-channel evidence you'd collect to confirm each.
6. Compare ADSL's DMT (256 fixed channels, adaptive bits/symbol) with V.90's single 4 kHz channel: why does spreading across many narrow channels survive a bad loop better than one wide one?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Local loop | "the phone line to your house" | Analog twisted pair from end office to premises; the bandwidth-limiting "last mile," ~1 MHz physical capacity |
| DMT | "the ADSL modulation" | OFDM specialized for ADSL: 256 channels × 4312.5 Hz, each running QAM with per-channel adaptive bit-loading |
| Bit-loading | "how fast the line goes" | Per-channel assignment of 0–15 bits/symbol based on that channel's measured SNR |
| DSLAM | "the box at the office" | Digital Subscriber Line Access Multiplexer; recovers bits above 26 kHz and forms packets to the ISP |
| Splitter / microfilter | "the dongle on the jack" | Analog filters separating 0–4 kHz POTS from the >26 kHz data band; G.lite uses per-jack microfilters instead |
| V.90 | "56k modem" | Asymmetric standard exploiting a digital ISP feed; 56 kbps = 7 usable bits × 8000 PCM samples/s |
| PON | "fiber internet" | Passive Optical Network: one fiber per ~100 homes, downstream broadcast + upstream TDMA via OLT grants |
| Ranging | "fiber sync" | OLT-measured per-ONU timing offset so upstream bursts arrive aligned and don't overlap |

## Further Reading

- ITU-T **G.992.1 (G.dmt)** and **G.992.5 (ADSL2+)** — ADSL physical layer and DMT.
- ITU-T **G.992.2 (G.lite)** — splitterless ADSL.
- ITU-T **G.984** (GPON) and **IEEE 802.3ah** (EPON / Ethernet in the First Mile).
- ITU-T **V.34**, **V.90**, **V.92** — voice-band modem recommendations.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., §2.6.3 "The Local Loop: Modems, ADSL, and Fiber."
- Starr, Sorbara, Cioffi & Silverman, *DSL Advances* (2003) — DMT and loop engineering.
