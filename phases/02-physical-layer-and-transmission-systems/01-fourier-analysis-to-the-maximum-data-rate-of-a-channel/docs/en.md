# Fourier Analysis to The Maximum Data Rate of a Channel

> Every wire, fiber, and radio band has a hard ceiling on bits per second, and that ceiling comes from two equations you can compute by hand. A square digital pulse is really an infinite sum of sine harmonics (Fourier series, Eq. 2-1); the medium acts as a low-pass filter that attenuates the high harmonics, so the received waveform is a rounded-off approximation. Nyquist's noiseless limit, `C = 2B·log2(V)` bits/sec, says a 3 kHz channel with 2 voltage levels tops out at 6000 bps no matter how clever your coding. Shannon's noisy-channel limit, `C = B·log2(1 + S/N)`, caps an ADSL line (B ≈ 1 MHz, SNR ≈ 40 dB) at roughly 13 Mbps regardless of how many signal levels `V` you add. The trap engineers fall into: cranking the symbol rate or constellation size past what bandwidth and SNR physically allow, then blaming the modem when the link trains down or errors spike. This lesson turns those two formulas into a calculator you can point at any real link budget — telephone local loop, Wi-Fi 20 MHz channel, gigabit copper — to predict the wall before you hit it.

**Type:** Learn
**Languages:** Python (stdlib), signal diagrams
**Prerequisites:** Basic algebra and logarithms; decibels; the idea of a periodic signal
**Time:** ~70 minutes

## Learning Objectives

- Decompose a binary signal into Fourier harmonics and explain why limiting bandwidth `B` rounds the pulse and caps the data rate.
- Compute the Nyquist noiseless maximum data rate `C = 2B·log2(V)` for a channel with `B` Hz of bandwidth and `V` discrete levels.
- Compute the Shannon noisy-channel capacity `C = B·log2(1 + S/N)` and convert an SNR given in decibels to a linear power ratio.
- Explain why adding more signal levels `V` cannot beat the Shannon limit, only the SNR or bandwidth can.
- Apply both limits to real links (3 kHz phone loop, 1 MHz ADSL, 20 MHz Wi-Fi) and identify which limit binds.

## The Problem

A field engineer provisions a customer ADSL line spec'd at 12 Mbps. The line trains up at 6 Mbps and won't go higher even after swapping the modem twice. Marketing insists the chipset supports 256-QAM, so "more bits per symbol should fix it." It doesn't. The home is 3.5 km from the exchange, the loop SNR is around 28 dB, and across the ~1 MHz of usable bandwidth Shannon's equation caps the line near 9 Mbps — and real margin requirements knock that down further. No constellation size, no firmware, no vendor escalation changes physics: the ceiling is set by bandwidth and noise, not by the modem.

The same wall shows up everywhere. A 3 kHz analog phone channel cannot carry a clean 2-level signal faster than 6000 bps (Nyquist). A 20 MHz Wi-Fi channel at 25 dB SNR caps near 166 Mbps before you even subtract MAC overhead. Engineers who don't carry these two equations in their head waste days tuning knobs that can't move the limit. The fix is to compute the ceiling first, then ask whether your modulation is anywhere near it.

## The Concept

Source: `chapters/chapter-02-the-physical-layer.md`, sections 2.1.1 (Fourier Analysis), 2.1.2 (Bandwidth-Limited Signals), 2.1.3 (The Maximum Data Rate of a Channel).

### Fourier analysis: a square pulse is a sum of sines

In the early 19th century Jean-Baptiste Fourier proved that any reasonably behaved periodic function `g(t)` of period `T` is a sum of (possibly infinitely many) sines and cosines:

```
g(t) = c + Σ aₙ·sin(2πnft) + Σ bₙ·cos(2πnft)   for n = 1, 2, 3, …
```

Here `f = 1/T` is the **fundamental frequency**, `aₙ` and `bₙ` are the amplitudes of the *n*-th harmonic, and `c` is the DC (average) term. A finite-duration data signal is handled by pretending it repeats forever.

Why this matters for networking: the bit pattern `b` sent at `b` bits/sec has a fundamental period and therefore a set of harmonics. If you transmit the byte `01100010` over and over, eight bits take `8/b` seconds, so the fundamental frequency of that pattern is `f = b/8` Hz. The harmonics live at `f, 2f, 3f, …`. The crisp vertical edges of the square wave are carried by the *high* harmonics — the sharper the edge, the higher the harmonic content needed to reproduce it. See [`assets/fourier-analysis-to-the-maximum-data-rate-of-a-channel.svg`](../assets/fourier-analysis-to-the-maximum-data-rate-of-a-channel.svg) for how the reconstructed waveform sharpens as more harmonics survive.

### Bandwidth-limited signals: the medium is a low-pass filter

No transmission medium passes all frequencies without loss. The range of frequencies passed without strong attenuation is the **bandwidth** `B` (in Hz). A wire, by its physical construction, attenuates high frequencies. The result: high-order harmonics are diminished or removed, and the received signal is a rounded approximation of the square pulse.

For the `8/b`-second pattern above, the *n*-th harmonic is at `n·b/8` Hz. A channel of bandwidth `B` Hz passes harmonics only up to number `8B/b`. The table below (from the textbook's worked example, a channel of fixed `B = 3000` Hz) shows how many harmonics survive as the bit rate rises:

| Bit rate (bps) | Period T (ms) | First harmonic (Hz) | # harmonics through a 3000 Hz channel |
|---|---|---|---|
| 300 | 26.67 | 37.5 | 80 |
| 600 | 13.33 | 75 | 40 |
| 1200 | 6.67 | 150 | 20 |
| 2400 | 3.33 | 300 | 10 |
| 4800 | 1.67 | 600 | 5 |
| 9600 | 0.83 | 1200 | 2 |
| 19200 | 0.42 | 2400 | 1 |

At 9600 bps only the first two harmonics get through; at 19200 bps only the fundamental survives, and the receiver sees a near-sine blur instead of square bits. **Limiting bandwidth limits the data rate, even on a perfect, noiseless channel.** That observation is what Nyquist made exact.

A note on the word "bandwidth": to an electrical engineer it is a frequency range in Hz; to a computer scientist "bandwidth" usually means the maximum data rate in bits/sec. They are related but not the same — always know which one a spec sheet means.

### Nyquist: the noiseless limit

In 1924 AT&T engineer Henry Nyquist proved that a signal run through a low-pass filter of bandwidth `B` can be **fully reconstructed from `2B` samples per second** — sampling faster is pointless because the higher frequencies were already filtered out. If each sample (symbol) carries one of `V` discrete voltage levels:

```
Nyquist:  C = 2·B·log2(V)   bits/sec
```

`log2(V)` is the bits encoded per symbol. Worked examples:

| Channel | B (Hz) | Levels V | Bits/symbol | Nyquist C |
|---|---|---|---|---|
| Analog phone | 3000 | 2 | 1 | 6000 bps |
| Analog phone | 3000 | 4 | 2 | 12000 bps |
| Analog phone | 3000 | 16 | 4 | 24000 bps |

So a noiseless 3 kHz channel cannot exceed 6000 bps with binary signaling — but you *can* push higher by adding levels. That seems to promise unlimited rate by adding `V`. Noise is what stops it.

### Shannon: the noisy-channel limit

There is always thermal noise from molecular motion. Noise is measured by the **Signal-to-Noise Ratio** `S/N` (signal power over noise power), usually quoted in decibels: `dB = 10·log10(S/N)`. So 10 dB = ratio 10, 20 dB = 100, 30 dB = 1000, 40 dB = 10000.

In 1948 Claude Shannon extended Nyquist to noisy channels (Shannon, 1948 — the founding paper of information theory):

```
Shannon:  C = B·log2(1 + S/N)   bits/sec   (S/N is the LINEAR ratio, not dB)
```

The critical move: convert dB to a linear ratio first. `S/N = 10^(dB/10)`. Worked example for ADSL — `B ≈ 1 MHz`, short-loop SNR ≈ 40 dB:

```
S/N (linear) = 10^(40/10) = 10000
C = 1,000,000 · log2(1 + 10000)
  = 1,000,000 · log2(10001)
  ≈ 1,000,000 · 13.29
  ≈ 13.3 Mbps
```

This is why ADSL is specified up to ~12 Mbps and never magically exceeds ~13 Mbps over that loop. To go faster you must raise SNR (move the exchange closer, add repeaters) or use more bandwidth (ADSL2+ widens the band). Crucially, **`V` does not appear in Shannon's equation** — adding signal levels past the Shannon ceiling just buys you symbols the noise will corrupt. A claimed capacity above the Shannon limit should be treated like a perpetual-motion machine.

### Which limit binds?

Compute both. The real ceiling is the *smaller* of the two — Nyquist if you're level-starved, Shannon if you're noise-starved. `code/main.py` computes both for any link and reports which one binds, exactly as the SVG's decision flow shows.

| Link | B | V | SNR | Nyquist | Shannon | Binds |
|---|---|---|---|---|---|---|
| Phone (modem V.22) | 3000 | 4 | 30 dB | 12 kbps | ~30 kbps | Nyquist |
| ADSL short loop | 1 MHz | 256 | 40 dB | 16 Mbps | ~13.3 Mbps | Shannon |
| Wi-Fi 20 MHz | 20 MHz | 64 | 25 dB | 240 Mbps | ~166 Mbps | Shannon |

## Build It

`code/main.py` is a stdlib-only channel-capacity calculator.

1. `db_to_ratio(db)` — converts an SNR in dB to a linear power ratio with `10**(db/10)`.
2. `nyquist_capacity(bandwidth_hz, levels)` — returns `2·B·log2(V)`.
3. `shannon_capacity(bandwidth_hz, snr_db)` — converts dB then returns `B·log2(1 + S/N)`.
4. `harmonics_through(bit_rate, bandwidth_hz)` — given the `8/b` repeating-byte model, returns how many harmonics survive a channel of bandwidth `B` (reproduces the bandwidth table).
5. `analyze_link(...)` — runs both capacity limits, decides which one binds, and prints a labeled report.
6. `main()` — demonstrates phone, ADSL, and Wi-Fi links plus the harmonic table.

Run it:

```
python3 code/main.py
```

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Find a link's hard ceiling | `B`, SNR in dB, level count `V` from the modem spec | You compute both Nyquist and Shannon and quote the smaller as the real cap |
| Diagnose "modem won't train up" | Loop length → SNR estimate, Shannon result | You show the rate is at the Shannon wall, so more levels can't help |
| Convert SNR | dB value off a line test | You apply `10^(dB/10)` before plugging into Shannon, never the dB directly |
| Explain pulse rounding | Harmonic count vs bit rate | You can name how many harmonics survive and why edges blur |

## Ship It

This lesson produces an artifact under [`outputs/`](../outputs/): a one-page **link-budget capacity cheat sheet** that, given `B`, `V`, and SNR(dB), reports Nyquist, Shannon, the binding limit, and a plain-English verdict ("noise-limited — adding QAM levels won't help"). Generate it with `code/main.py` and the prompt in [`outputs/prompt-fourier-analysis-to-the-maximum-data-rate-of-a-channel.md`](../outputs/prompt-fourier-analysis-to-the-maximum-data-rate-of-a-channel.md).

## Exercises

1. A noiseless channel has `B = 4000` Hz. What is the maximum data rate with 8 voltage levels? Now the customer wants 48 kbps on this channel — how many levels `V` does Nyquist require, and is that realistic once you add any noise?
2. A line test reports SNR = 20 dB over `B = 3.1 kHz`. Compute the Shannon capacity. A vendor claims their modem hits 56 kbps on this exact line. Argue why that violates Shannon — and explain how V.90 dial-up "56k" sidesteps it (hint: the downstream path is partly digital, raising effective SNR).
3. Reproduce the harmonics table for a `B = 3000` Hz channel at 4800 bps using `harmonics_through`. Why does the received square wave look like a near-sine at 19200 bps?
4. ADSL2+ doubles usable bandwidth to ~2 MHz while SNR stays at 40 dB. Compute the new Shannon ceiling and compare to the ~13.3 Mbps of plain ADSL. Did doubling bandwidth double capacity? Explain the `log2(1+S/N)` scaling.
5. A 20 MHz Wi-Fi channel sees SNR drop from 30 dB to 15 dB as the client walks away. Compute Shannon capacity at both SNRs. By roughly what factor does the ceiling fall, and why is the drop sub-linear in dB?
6. Given a fixed Shannon ceiling, is it ever worth increasing `V` past the point where Nyquist `2B·log2(V)` exceeds Shannon `B·log2(1+S/N)`? Justify using the binding-limit rule.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Bandwidth | "How fast my internet is" | Two distinct things: a frequency range in Hz (EE), or max data rate in bits/sec (CS). Spec sheets mean different ones. |
| Fundamental frequency | "The signal's frequency" | `f = 1/T`; the lowest harmonic. For a repeating byte at `b` bps it is `b/8` Hz. |
| Harmonic | "Overtone" | The *n*-th sine term at `n·f`. High harmonics carry the sharp edges; the medium filters them out. |
| Nyquist rate | "Twice the bandwidth" | `2B` samples/sec fully reconstruct a band-limited signal; sampling faster recovers nothing. |
| Signal levels (V) | "Bits per symbol" | Discrete amplitudes per symbol; encodes `log2(V)` bits. Helps Nyquist, useless past Shannon. |
| SNR | "Signal strength" | Signal power ÷ noise power. Quoted in dB; convert with `10^(dB/10)` before Shannon. |
| Shannon capacity | "Theoretical max" | `B·log2(1+S/N)`; an unbeatable ceiling set by bandwidth and noise, independent of `V`. |
| Decibel (dB) | "A loudness unit" | `10·log10(ratio)` of power. 10 dB = ×10, 30 dB = ×1000, 40 dB = ×10000. |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 6th ed., Chapter 2, §2.1.1–2.1.3 (the source for this lesson).
- C. E. Shannon, "A Mathematical Theory of Communication," *Bell System Technical Journal*, 1948 — the founding paper of information theory.
- H. Nyquist, "Certain Topics in Telegraph Transmission Theory," *Transactions of the AIEE*, 1928.
- ITU-T Recommendation G.992.1 (ADSL) and G.992.5 (ADSL2+) — real bandwidth/SNR-driven rate adaptation.
- ITU-T Recommendation V.90 — how "56k" dial-up exploits a partly digital path to raise effective SNR.
- IEEE 802.11 — OFDM subcarriers and adaptive modulation/coding as a practical embodiment of Shannon-limited rate selection.
