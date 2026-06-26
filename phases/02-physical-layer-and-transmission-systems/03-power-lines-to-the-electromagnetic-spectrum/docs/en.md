# Power Lines to The Electromagnetic Spectrum

> Power-line networking superimposes an MHz data carrier onto the 50/60 Hz mains "hot" wire — the same outlet that powers your TV becomes a LAN drop, but the wiring was built to distribute power, not signal. The mains channel fights back: it attenuates MHz tones, reflects them at every unterminated branch (impedance mismatch), injects impulsive noise every time a motor or dimmer switches, and radiates like an unintentional antenna because house wiring has none of the twist that cancels common-mode emissions in UTP. HomePlug AV (IEEE 1901, OFDM, ~917 carriers over 2–28 MHz) still pushes 100+ Mbps PHY by notching out the licensed amateur-radio bands and using strong forward error correction plus interleaving against burst errors. Wireless is the dual problem: instead of a fixed copper channel you pick a slice of the electromagnetic spectrum where `λf = c` (c ≈ 3×10⁸ m/s, the rule of thumb λ[m]·f[MHz] ≈ 300), and Shannon's law ties the achievable rate to bandwidth and SNR. This lesson connects the worst guided medium (mains) to the medium with the most bandwidth on Earth (the spectrum, ~10⁴ Hz to 10²⁴ Hz), and gives you Python to compute both.

**Type:** Learn
**Languages:** Python (stdlib), signal diagrams
**Prerequisites:** Twisted pair / coax / fiber (Phase 2 · 01–02), Fourier & bandwidth basics, Shannon and Nyquist limits
**Time:** ~75 minutes

## Learning Objectives

- Explain why household electrical wiring is a "horrible" data channel and name the four concrete impairments: high-frequency attenuation, multipath reflection from branch taps, impulsive switching noise, and unintended radiation/ingress.
- Compute wavelength from frequency (and back) with `λf = c`, and apply the λ[m]·f[MHz] ≈ 300 rule of thumb to size an antenna or place a band on the spectrum.
- Read the ITU band table (LF through THF) and map each band to a real use (AM, FM, TV, microwave, fiber).
- Distinguish the three wideband techniques — frequency hopping (FHSS), direct-sequence (DSSS/CDMA), and ultra-wideband (UWB) — by how each spreads energy and what interference it survives.
- Use Shannon `C = B·log₂(1 + SNR)` to show why microwave and optical bands carry orders of magnitude more than the mains channel.

## The Problem

A customer plugs a power-line adapter (HomePlug) into the wall behind the TV and another into the wall by the router. The marketing box says "1000 Mbps." Their `iperf3` measures 22 Mbps, and it drops to 4 Mbps every evening at 7 p.m. When they run a hair dryer it falls to near zero. Meanwhile the local ham-radio operator three doors down complains of interference on the 40-meter band.

Every one of those symptoms is physics in the wiring, not a software bug:

- 7 p.m. crash → neighbors' switching loads and TV power supplies dump impulsive noise into the shared mains.
- Hair-dryer cliff → the motor/heater inrush is broadband impulse noise that overruns the interleaver.
- Distance/branch sensitivity → the data signal reflects at every junction box (impedance discontinuity) and arrives as smeared multipath.
- Ham complaint → un-twisted house wiring radiates the MHz carrier; the standard must *notch* licensed bands to stay legal.

To diagnose this you need to think in the same terms the spectrum forces on every wireless link: where in frequency does the signal sit, how wide is it, how much power survives, and what is the noise. Power-line and wireless are two faces of one question — **how much information can this slice of frequency carry?**

## The Concept

Source: [`chapters/chapter-02-the-physical-layer.md`](../../../../chapters/chapter-02-the-physical-layer.md), Power Lines and The Electromagnetic Spectrum.

### Why the mains is a hostile channel

Power lines were engineered for a single 50 Hz (Europe) or 60 Hz (North America) sinusoid at high current. Data networking superimposes a low-power signal in the **2–28 MHz** range onto that same hot wire. Four properties make this hard:

| Impairment | Cause | Effect on the data signal |
|---|---|---|
| High-frequency attenuation | Wiring is a low-pass structure; series inductance rises with f | MHz carriers lose tens of dB; the usable band shrinks |
| Multipath / reflection | Every outlet and junction is an unterminated branch (impedance mismatch) | Echoes arrive delayed → inter-symbol interference, frequency-selective fading |
| Impulsive noise | Appliances switching, dimmers, motor brushes, SMPS supplies | Wideband bursts that erase whole OFDM symbols |
| Radiation / ingress | No twist → wiring acts as an antenna | Emits (interferes with ham/AM bands) and picks up external RF |

Because the channel is so variable house-to-house and minute-to-minute, the standard cannot assume a clean pipe. HomePlug AV / IEEE 1901 answers with **OFDM**: it splits the 2–28 MHz band into roughly 917 narrow subcarriers, measures the SNR of each one, loads more bits onto the good subcarriers and fewer (or zero) onto the bad ones, and **notches out** the amateur-radio and other licensed segments so it never transmits there. Forward error correction (turbo codes) plus a time interleaver spread each codeword across many symbols, so a 100 µs impulse from a light switch damages a few bits per codeword instead of destroying one packet. See the channel sketch in [`assets/power-lines-to-the-electromagnetic-spectrum.svg`](../assets/power-lines-to-the-electromagnetic-spectrum.svg).

The headline number from the source: despite all this, **100+ Mbps is practical over typical household wiring** using schemes that resist impaired frequencies and burst errors.

### From a copper channel to the whole spectrum

When electrons accelerate they radiate electromagnetic waves (Maxwell, 1865; first generated and detected by Hertz, 1887). Two quantities describe a wave:

- **frequency** `f` — oscillations per second, in Hz.
- **wavelength** `λ` — distance between two maxima, in meters.

They are locked together by the speed of propagation:

```
λ · f = c        c ≈ 3 × 10⁸ m/s in vacuum  (≈ 30 cm per nanosecond)
```

In copper or fiber the speed drops to about **2/3 c** and becomes slightly frequency-dependent (this is why propagation delay on a cable is ~5 ns/m, not 3.3 ns/m). The handy engineering shortcut, with λ in meters and f in MHz:

```
λ[m] · f[MHz] ≈ 300
```

So a 100 MHz FM signal is ~3 m long, a 1000 MHz (1 GHz) wave is 0.3 m, and a 2.4 GHz Wi-Fi carrier is ~12.5 cm — which is why a quarter-wave Wi-Fi antenna is about 3 cm. `code/main.py` computes these conversions exactly.

### The ITU spectrum bands

The radio, microwave, infrared, and visible-light portions can all carry information by modulating amplitude, frequency, or phase. The ITU names bands by wavelength decade:

| Band | Name | Frequency | Wavelength | Typical use |
|---|---|---|---|---|
| LF | Low Frequency | 30–300 kHz | 10 km – 1 km | Maritime/navigation, long-wave AM |
| MF | Medium Frequency | 300 kHz – 3 MHz | 1 km – 100 m | AM broadcast radio |
| HF | High Frequency | 3–30 MHz | 100 m – 10 m | Shortwave, amateur radio, **power-line band sits here** |
| VHF | Very High Frequency | 30–300 MHz | 10 m – 1 m | FM radio, VHF TV |
| UHF | Ultra High Frequency | 300 MHz – 3 GHz | 1 m – 10 cm | UHF TV, cellular, Wi-Fi, GPS |
| SHF | Super High Frequency | 3–30 GHz | 10 cm – 1 cm | Satellite, terrestrial microwave, radar |
| EHF | Extremely High Frequency | 30–300 GHz | 1 cm – 1 mm | mmWave 5G, point-to-point links |
| THF | Tremendously High Frequency | 300 GHz – 3 THz | 1 mm – 0.1 mm | Emerging / terahertz |

Above EHF/THF lie infrared and visible light (where fiber operates, ~10¹⁴ Hz), then UV, X-ray, and gamma rays — better in theory because of higher frequency and bandwidth, but hard to modulate, blocked by walls, and dangerous. This is exactly why networking people love fiber: it sits far to the right on the log-frequency axis where bandwidth is enormous.

### Why bandwidth here means data rate

Shannon ties everything together. For a channel of bandwidth `B` (Hz) and signal-to-noise ratio `SNR` (linear, not dB):

```
C = B · log₂(1 + SNR)      bits per second
```

Worked example from the source: the 1.30-µm fiber window is 0.17 µm wide. Converting those wavelengths to frequencies via `λf = c` gives a band roughly **30,000 GHz** wide. At a modest 10 dB SNR (SNR = 10 linear), capacity ≈ 30,000 GHz × log₂(11) ≈ **300 Tbps**. Compare the mains: ~26 MHz of band at maybe 15 dB SNR yields on the order of 100 Mbps — a factor of a million difference, driven almost entirely by how much spectrum each medium owns. `code/main.py` runs both numbers.

### Narrowband vs. spread spectrum

Most links use a **narrow** band (Δf/f ≪ 1) and concentrate power there for efficiency. But three wideband techniques deliberately spread the signal:

| Technique | How it spreads | What it survives | Real use |
|---|---|---|---|
| **FHSS** (frequency hopping) | Transmitter hops across many frequencies hundreds of times/sec | Jamming, narrowband interference, multipath fading | Bluetooth (79 channels, 1600 hops/s); early 802.11 |
| **DSSS** (direct sequence) | XORs data with a fast pseudo-random chip code, widening the band | Narrowband interference, multipath; codes enable **CDMA** | 802.11b, 3G mobile, GPS |
| **UWB** (ultra-wideband) | Rapid sub-nanosecond pulses spread thinly over ≥500 MHz (or ≥20% of center f) | Strong narrowband interferers; *underlays* them with tiny per-Hz energy | High-rate PANs (~1 Gbps), through-wall imaging, precise ranging |

Historical note worth keeping: frequency hopping was co-invented by actress Hedy Lamarr and composer George Antheil, who patented a 88-frequency scheme (U.S. Patent 2,292,387) — the number of keys on a piano.

### The unlicensed ISM bands

Spread spectrum thrives in the crowded **ISM (Industrial, Scientific, Medical)** bands — notably 2.4 GHz — where many systems coexist without licenses. FHSS and DSSS both tolerate the resulting interference because no single impaired frequency stays in use long enough (hopping) or carries enough of the signal (spreading) to break the link. This is the same robustness logic HomePlug uses on the mains: assume the channel is partly broken at any instant, and design so no single broken slice kills the connection.

## Build It

`code/main.py` is a spectrum and channel calculator. Build understanding by tracing what it computes:

1. **Wavelength ↔ frequency** — `freq_to_wavelength()` and `wavelength_to_frequency()` implement `λf = c` exactly, plus a rule-of-thumb cross-check (`rule_of_thumb_300`).
2. **Band classification** — `classify_band()` maps any frequency to its ITU band (LF…THF) and prints the wavelength range.
3. **Shannon capacity** — `shannon_capacity()` takes bandwidth and SNR (in dB) and returns bits/sec; run it on the mains channel and the fiber window to feel the spectrum gap.
4. **Antenna sizing** — `quarter_wave_antenna()` shows why a 2.4 GHz antenna is ~3 cm and an AM antenna is hundreds of meters.
5. **Power-line band check** — `power_line_band_report()` places the 2–28 MHz HomePlug band on the spectrum and flags that it overlaps the HF amateur bands (hence notching).

Run it:

```bash
python3 code/main.py
```

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Place a signal on the spectrum | Frequency, computed λ, ITU band name | 2.4 GHz → 12.5 cm → UHF; you can name the band without a chart |
| Explain a power-line throughput cliff | iperf3 timeline correlated with appliance use; spectrum analyzer impulse bursts | You attribute the drop to impulsive noise / multipath, not the OS |
| Justify fiber's bandwidth lead | Shannon C for fiber window vs. mains | You show the ~10⁶× gap comes from band width, not better SNR |
| Diagnose ham-radio interference | The notched HF amateur segments in the HomePlug spectral mask | You explain *why* the standard notches and where |
| Choose a spread-spectrum scheme | Interference type (jam / narrowband / coexistence) | FHSS for jamming, DSSS/CDMA for sharing, UWB for underlay |

## Ship It

Produce one artifact under `outputs/`:

- A spectrum cheat-sheet (band table + λf=c worked examples) generated from `code/main.py`.
- A one-page power-line troubleshooting runbook mapping each symptom (evening crash, dryer cliff, branch distance, ham complaint) to its physical cause and the measurement that confirms it.
- The annotated channel diagram in [`assets/power-lines-to-the-electromagnetic-spectrum.svg`](../assets/power-lines-to-the-electromagnetic-spectrum.svg).

## Exercises

1. A power-line adapter advertises "AV2 2000 Mbps" but `iperf3` shows 90 Mbps and collapses to 6 Mbps whenever the fridge compressor cycles. Identify which of the four mains impairments dominates and the smallest measurement (oscilloscope, spectrum analyzer, or timed iperf3) that confirms it.
2. Using `λf = c`, compute the wavelength of a 5 GHz Wi-Fi channel and a 27 MHz CB-radio channel. Which needs the longer antenna, and by what factor?
3. Run `shannon_capacity()` for the 26 MHz mains band at 15 dB SNR, then for the 30,000 GHz fiber window at 10 dB SNR. Explain in one sentence why fiber wins despite the *worse* SNR.
4. The HomePlug spectral mask notches 7.0–7.3 MHz and 14.0–14.35 MHz. Which ITU band is that, and which real-world users are being protected? What does notching cost in throughput?
5. You must put a covert military link in a jammed environment and a high-rate short-range PAN link through interior walls. Pick FHSS, DSSS/CDMA, or UWB for each and justify by spreading mechanism.
6. Bluetooth hops 1600 times/sec across 79 channels in the 2.4 GHz ISM band. Explain how this survives a microwave oven (a strong narrowband interferer near 2.45 GHz) that a fixed-frequency link would not.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Power-line networking | "Internet through the wall socket" | An MHz OFDM data signal superimposed on the 50/60 Hz mains, fighting attenuation, multipath, impulse noise, and radiation |
| HomePlug / IEEE 1901 | "the powerline standard" | OFDM over ~2–28 MHz with ~917 subcarriers, per-carrier bit loading, FEC + interleaving, and a notched spectral mask |
| `λf = c` | "wavelength times frequency" | The fundamental wave relation; with λ in m and f in MHz, λf ≈ 300 |
| ITU band (LF…THF) | "radio frequencies" | Wavelength-decade bands; each maps to specific allowed uses |
| Shannon capacity | "the speed limit" | C = B·log₂(1+SNR); rate scales linearly with band width, logarithmically with SNR |
| ISM band | "the free 2.4 GHz" | Unlicensed Industrial/Scientific/Medical spectrum where spread-spectrum systems coexist |
| FHSS | "frequency hopping" | Hops across many frequencies hundreds of times/sec; beats jamming and fading |
| DSSS / CDMA | "spread spectrum" | Spreads with a chip code; different codes let many signals share one band |
| UWB | "ultra-wideband" | ≥500 MHz (or ≥20% center f) of thin pulses that underlay narrowband users |
| Notching | "blocking a frequency" | Zeroing subcarriers over licensed bands so the link stays legal |

## Further Reading

- A. S. Tanenbaum & D. J. Wetherall, *Computer Networks*, 5th ed., Ch. 2 (Guided Transmission Media; The Electromagnetic Spectrum).
- IEEE 1901-2020 — Broadband over Power Line Networks (HomePlug AV PHY/MAC).
- IEEE 802.11-2020 — DSSS (802.11b) and FHSS PHYs in the 2.4 GHz ISM band.
- ITU-R Recommendation V.431 — Nomenclature of the frequency and wavelength bands.
- C. E. Shannon, "A Mathematical Theory of Communication," *Bell System Technical Journal*, 1948 — the capacity theorem.
- U.S. Patent 2,292,387 (Markey/Hedy Lamarr & Antheil, 1942) — the original frequency-hopping "Secret Communication System."
- FCC Part 15 / Part 18 — unlicensed and ISM emission rules underlying ISM-band operation.
