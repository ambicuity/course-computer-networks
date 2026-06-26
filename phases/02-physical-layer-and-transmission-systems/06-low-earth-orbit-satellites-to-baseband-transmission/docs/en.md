# Low-Earth Orbit Satellites to Baseband Transmission

> A LEO satellite at 750 km (Iridium) has a one-way path delay of about 2.5 ms versus roughly 119 ms for a geostationary bird at 35,800 km, which is why LEO can carry interactive voice while GEO cannot. Iridium flies 66 cross-linked satellites in six near-polar necklaces, each with up to 48 spot-beam cells and 3840 channels, and routes calls satellite-to-satellite through four neighbors; Globalstar uses 48 satellites in a "bent-pipe" design that drops every call straight back to a ground gateway. Whatever the constellation, the bits a phone sends become a **baseband** signal occupying 0 Hz up to some cutoff B, and two laws bound what it can carry: Nyquist's `C = 2B·log2(V)` for a noiseless channel and Shannon's `C = B·log2(1 + S/N)` for a noisy one. Shift baseband up to the L-band (1.6 GHz uplink) and it becomes passband — the same bits, relocated in frequency. Sample below 2B and you alias; push the symbol rate above 2B on a band-limited link and inter-symbol interference closes the eye. This lesson connects orbital geometry to the information-theory ceiling that governs every link in the constellation.

**Type:** Learn
**Languages:** Python (stdlib), signal diagrams
**Prerequisites:** Phase 2 lessons on bandwidth-limited signals, Fourier analysis, and the dB scale
**Time:** ~75 minutes

## Learning Objectives

- Compute one-way and round-trip propagation delay for LEO, MEO, and GEO altitudes and explain why 750 km enables interactive voice while 35,800 km forces a perceptible echo.
- Contrast the Iridium inter-satellite-link (ISL) switching model with the Globalstar bent-pipe model in terms of where switching complexity lives and what fails when a satellite drops.
- Distinguish baseband from passband signals and state the Nyquist sampling minimum (2B) for reconstructing a band-limited signal without aliasing.
- Apply Nyquist's noiseless capacity `2B·log2(V)` and Shannon's noisy capacity `B·log2(1 + S/N)` to a real L-band channel and identify which one binds.
- Convert a linear signal-to-noise ratio to decibels and back, and feed it into the Shannon bound.

## The Problem

You are on the network team for a maritime operator. A research vessel near the South Pole reports that satellite voice calls are clear and snappy, but the legacy GEO data terminal on the same ship has a ~250 ms lag that makes interactive sessions painful. A second symptom: the engineering team tried to push a 9.6 kbps telemetry stream over a narrow voice-grade sub-channel and the receiver is decoding garbage even though the link "has signal."

Both symptoms are physical-layer facts, not application bugs. The voice/data delay gap is pure orbital geometry — speed of light times altitude. The garbled telemetry is a band-limited channel violating Nyquist: the symbol rate is too high for the bandwidth, so harmonics needed to reconstruct the bits never arrive. Diagnosing either means reducing the symptom to delay arithmetic and capacity arithmetic — what `code/main.py` makes concrete.

## The Concept

### Altitude sets delay, and delay sets the application

Propagation delay is `distance / c`, where `c ≈ 299,792 km/s`. For a satellite directly overhead, the one-way ground-to-satellite distance is just the altitude `h`; inter-satellite paths add hops.

| Orbit | Altitude | One-way (overhead) | Round-trip (bent pipe) | Period | Typical use |
|---|---|---|---|---|---|
| LEO (Iridium) | 750 km | ~2.5 ms | ~10 ms | ~100 min | Interactive voice, paging |
| LEO (Globalstar) | ~1,400 km | ~4.7 ms | ~19 ms | ~110 min | Voice, low-rate data |
| MEO (GPS) | ~20,200 km | ~67 ms | — | ~12 h | Navigation |
| GEO | 35,800 km | ~119 ms | ~239 ms | 24 h | TV, broadcast data |

The ITU's threshold for comfortable interactive voice is roughly 150 ms one-way (G.114). A single GEO hop already eats most of that budget before any terrestrial routing, which is why GEO voice has noticeable lag and echo while LEO does not. Kepler's third law (`period ∝ radius^1.5`) explains the rest of the trade: low orbits mean ~100-minute periods, so each satellite is overhead for only minutes — you need a *constellation* of dozens to keep one always in view. `code/main.py` computes these delays from altitude; the SVG plots the delay-vs-altitude curve with the 150 ms voice line drawn in.

### Two constellation philosophies: switch in space or switch on the ground

Iridium and Globalstar solve the same coverage problem in opposite ways.

**Iridium (switching in space):** 66 satellites at 750 km in six near-polar "necklaces," one satellite every ~32° of latitude. Each talks to **four** neighbors — two in its own necklace (fore and aft) and two in adjacent necklaces — over inter-satellite links. A North-Pole call can be relayed satellite-to-satellite across the grid and dropped to a South-Pole callee **without touching a ground gateway in between**. Each satellite carries up to 48 spot-beam cells and 3840 channels. The cost: every satellite needs real switching/routing hardware in orbit.

**Globalstar (bent pipe on the ground):** 48 satellites, each a "bent pipe" — it listens on the uplink, amplifies, and rebroadcasts on the downlink, doing no switching. A call goes phone → satellite → ground gateway → terrestrial network → gateway → satellite → phone. Complexity lives on the ground where it is cheap to upgrade and antennas are large enough to recover a weak few-milliwatt handset signal. The cost: you must be within view of *both* a satellite and a gateway, so deep-ocean and polar coverage is weaker than Iridium's.

| Property | Iridium | Globalstar |
|---|---|---|
| Satellites | 66 | 48 |
| Switching | In space (ISL grid, 4 neighbors) | On the ground (bent pipe) |
| Polar / open-ocean coverage | Full (cross-links) | Limited (needs gateway in view) |
| Satellite complexity | High (onboard routing) | Low (amplify + rebroadcast) |
| Failure of one node | Reroute via neighbors | Coverage hole until handover |

### Baseband versus passband

Inside the handset, the encoded voice is a **baseband** signal: its spectrum runs from 0 Hz up to a cutoff `B`. The handset cannot radiate a 0-Hz signal from a small antenna, so it **mixes** the baseband up to a passband centered on the carrier — Iridium's user link sits in the L-band around 1.6 GHz uplink / 1.5 GHz downlink. Passband is just baseband shifted in frequency; demodulation shifts it back. The information is unchanged by the shift — what is constrained is the **bandwidth** `B` of the occupied slice, and `B` is what the capacity laws care about. The SVG shows a baseband lobe at DC and the same lobe translated to a carrier.

### Nyquist: a band-limited signal needs only 2B samples per second

Henry Nyquist proved in 1924 that a signal run through a low-pass filter of bandwidth `B` is **completely** reconstructable from `2B` exact samples per second. Sampling faster recovers nothing — the higher-frequency components were already filtered out. Sampling *slower* than `2B` folds high frequencies onto low ones: **aliasing**, the "wagon wheel spinning backwards" failure. For a line with `V` discrete voltage levels, Nyquist's noiseless capacity is:

```
C = 2 * B * log2(V)   bits/sec
```

A noiseless 3 kHz channel carrying binary (`V = 2`) signals tops out at `2 × 3000 × 1 = 6000` bps. Want more? Add levels: `V = 16` gives `2 × 3000 × 4 = 24,000` bps — but only if there is no noise to confuse the 16 levels. That caveat is exactly where Shannon takes over.

### The band-limited bit stream and inter-symbol interference

A square bit pulse is a sum of harmonics (Fourier). A bit rate of `b` bits/sec sent one bit at a time has a first-harmonic frequency of `b/8` Hz for the 8-bit example in the chapter; a voice-grade line with a ~3000 Hz cutoff passes only the lowest `≈ 24000/b` harmonics. At 9600 bps over that line you keep barely two harmonics — the received waveform is so rounded that adjacent symbols smear into each other (**inter-symbol interference**) and the decoder guesses. This is the telemetry symptom from The Problem: the link "has signal," but the channel bandwidth is below what the symbol rate demands. The fix is to lower the symbol rate, widen `B`, or move to a multi-level/coded scheme that fits the available `B`.

### Shannon: noise sets the real ceiling

Claude Shannon (1948) extended Nyquist to noisy channels. With bandwidth `B` Hz and signal-to-noise ratio `S/N` (a **power** ratio, linear, not in dB):

```
C = B * log2(1 + S/N)   bits/sec
```

SNR is usually quoted in decibels: `dB = 10 · log10(S/N)`, so 10 dB = ratio 10, 20 dB = 100, 30 dB = 1000, 40 dB = 10,000. To use Shannon you must first convert dB back to a linear ratio: `S/N = 10^(dB/10)`. Worked example from the chapter: ADSL over ~1 MHz at 40 dB SNR gives `C = 1,000,000 × log2(1 + 10,000) ≈ 13.3 Mbps` — and no voltage-level count or sampling trick can beat it. When both bounds apply, the channel obeys the **smaller** of the two. `code/main.py` evaluates both and reports which binds, with the dB-to-ratio conversion explicit.

## Build It

1. Read `code/main.py`. It has pure functions `propagation_delay_ms`, `db_to_linear`, `nyquist_capacity_bps`, and `shannon_capacity_bps`, plus a `link_budget` helper that runs both capacity laws and reports the binding one.
2. Run `python3 code/main.py`. Confirm the LEO/GEO delay table matches The Concept and the ADSL example lands near 13.3 Mbps.
3. Trace one row by hand: pick a voice channel, set `V` and SNR, and verify the function output equals your arithmetic.
4. Find the failure mode: lower the bandwidth until the Nyquist number drops below your target symbol rate, and watch `link_budget` flip the binding constraint. That flip is the band-limited-ISI symptom in numeric form.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Explain the voice/data delay gap | One-way delay via `propagation_delay_ms` | You show LEO ≈ 2.5 ms vs GEO ≈ 119 ms against the ~150 ms G.114 budget |
| Choose Iridium vs Globalstar (polar route) | Constellation table; ISL vs bent-pipe | You explain why cross-links cover open ocean and bent-pipe needs a gateway in view |
| Diagnose garbled telemetry on a "working" link | Nyquist number vs symbol rate; harmonic count | You show bandwidth is below the symbol rate and predict closed-eye ISI |
| Size a link's max bit rate | `link_budget` (Nyquist vs Shannon) | You report the smaller bound and name whether levels or noise limits |
| Convert "40 dB SNR" into capacity | `db_to_linear` then Shannon | You get `S/N = 10,000` and a Shannon number matching the ADSL figure |

## Ship It

Produce one artifact under `outputs/`:

- A link-budget worksheet (CSV or markdown table) listing constellation, altitude, one-way delay, bandwidth, SNR (dB and linear), Nyquist cap, Shannon cap, and binding constraint for several real links.
- Or a one-page runbook: "Is this a delay problem or a capacity problem?" decision tree keyed to the symptoms above.

Start from the output of `python3 code/main.py` and the diagram in `assets/low-earth-orbit-satellites-to-baseband-transmission.svg`.

## Exercises

1. A GEO terminal shows 239 ms RTT; a LEO handset on the same ship shows ~10 ms. Reproduce both from altitude with `propagation_delay_ms` and state which application each orbit suits versus the ~150 ms one-way voice budget.
2. List the four neighbors an Iridium satellite reaches and explain the reroute when one fails. Then explain why the same North-to-South-Pole call is impossible on Globalstar without a ground gateway in view.
3. A noiseless voice-grade channel has `B = 3000` Hz. Compute the max bit rate for `V = 2`, `V = 4`, `V = 16`. At which `V` does a 20 dB SNR (Shannon) start to bind below Nyquist?
4. For 9600 bps over a 3000 Hz channel, estimate how many harmonics survive the cutoff and argue whether the receiver can recover the bits. Propose two distinct fixes.
5. A vendor quotes "1 MHz, 30 dB SNR." Convert the SNR to a linear ratio, compute the Shannon capacity, then find the minimum `V` a noiseless Nyquist link of the same bandwidth needs to match it.
6. A CubeSat uses a 25 kHz UHF channel at 15 dB SNR. Compute the Shannon ceiling and explain why this constrains it to telemetry rather than video.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| LEO | "Low satellites" | Orbit ~500–1,500 km; ~2–5 ms one-way delay, ~100 min period, needs dozens of satellites for continuous coverage |
| Bent pipe | "Dumb repeater" | Satellite that listens, amplifies, and rebroadcasts on a different frequency with no onboard switching (Globalstar) |
| Inter-satellite link (ISL) | "Space relay" | Direct satellite-to-satellite path; Iridium connects four neighbors so calls can route entirely in orbit |
| Baseband | "The raw signal" | A spectrum occupying 0 Hz up to cutoff `B`, before any shift to a carrier |
| Passband | "On the carrier" | The same signal shifted up to a higher frequency band (e.g., L-band 1.6 GHz) for radiation |
| Nyquist rate | "Sample twice the freq" | The `2B` samples/sec minimum to reconstruct a band-limited signal; below it you get aliasing |
| Aliasing | "Jagged sampling" | High-frequency components folding onto low ones when sampled below `2B` |
| Shannon capacity | "Max bit rate" | `B·log2(1+S/N)`; the noise-limited ceiling no level count or sample rate can beat |
| SNR in dB | "The signal quality number" | `10·log10(S/N)`; convert with `S/N = 10^(dB/10)` before using Shannon |
| ISI | "Smeared bits" | Inter-symbol interference when symbol rate exceeds what the channel bandwidth supports |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 6th ed., Chapter 2 — Nyquist and Shannon, Low-Earth Orbit Satellites, Satellites versus Fiber.
- C. E. Shannon, "A Mathematical Theory of Communication," *Bell System Technical Journal*, 1948 — the noisy-channel capacity theorem.
- H. Nyquist, "Certain Topics in Telegraph Transmission Theory," *Transactions of the AIEE*, 1928 — sampling and noiseless capacity.
- ITU-T Recommendation G.114 — one-way transmission time; the ~150 ms interactive-voice guidance.
- CCSDS 131.0-B (TM Synchronization and Channel Coding) — coding used on real satellite links to approach the Shannon bound.
