# Fiber Optic Modes and Attenuation Windows

> An optical fiber traps light by **total internal reflection** at the core/cladding boundary, but only rays above the **critical angle** `theta_c = arcsin(n_clad/n_core)` survive. The **numerical aperture** `NA = sqrt(n_core^2 - n_clad^2)` sets the acceptance cone (NA ~0.14 for ITU-T G.652), and the **normalized frequency** `V = (2*pi*a/lambda)*NA` decides mode count: `V < 2.405` means only the fundamental `LP01` mode and the fiber is **single-mode**. The textbook's three near-IR **attenuation windows** — 0.85 um (2.5 dB/km, GaAs, short reach), 1.30 um (0.38 dB/km, the G.652 dispersion zero), and 1.55 um (0.22 dB/km, the silica loss minimum and the **EDFA** amplifier band) — are each 25,000-30,000 GHz wide. The dB budget is `10*log10(P_in/P_out)`, so a factor-of-two loss is exactly 3 dB. Two failure modes dominate: **intermodal dispersion** in 50 um multimode fiber blurs pulses over short distances, and **chromatic dispersion** `|D|*L*DeltaLambda` at 1.55 um (D ~17 ps/nm/km) sets the unrepeated 10G span far tighter than the power budget does. This lesson builds a runnable fiber model — NA, V-number cutoff, dB power budget, and dispersion limit — so you can read the numbers an optical link design leaves behind.

**Type:** Learn
**Languages:** Python, packet traces
**Prerequisites:** Guided transmission media (Phase 2 lessons on copper and bandwidth/limits), the decibel and Shannon capacity, frequency/wavelength relationship
**Time:** ~85 minutes

## Learning Objectives

- Compute the **numerical aperture**, **critical angle**, and **V-number** for a fiber and decide from `V < 2.405` whether it is single- or multi-mode at a stated wavelength.
- Apply the dB definition `10*log10(P_in/P_out)` and build a link power budget across fiber, connector, and splice loss; state received power in dBm and margin.
- Distinguish the 0.85, 1.30, and 1.55 um windows by loss, by the device technology each enabled (GaAs, dispersion-zero, EDFA), and by the dominant limiter.
- Compute chromatic-dispersion broadening `|D|*L*DeltaLambda` and compare it to the bit period to find the dispersion-limited span, separate from the power-limited span.

## The Problem

A network engineer sizes a 40 km campus interconnect. The vendor offers two 10G transceivers: a cheap 0.85 um VCSEL on multimode fiber, and a 1.55 um DFB-laser part on single-mode fiber costing four times more. The link runs over a dark-fiber pair with two connector pairs; the receiver needs at least -28 dBm. The cheap part produces no link — the receivers stay dark. The engineer must work out, from the fiber parameters and the dB definition alone, which window carries 10G over 40 km, why the 0.85 um part fails, and whether 1.30 or 1.55 um is the right single-mode choice. That is exactly the decision `code/main.py` automates, and its printed output is the evidence for a link design document.

## The Concept

### Total internal reflection and the critical angle

An optical fiber is a glass core surrounded by glass cladding with a **lower index of refraction** (`n_core > n_clad`). A ray hitting the boundary below the **critical angle** (from the normal) refracts out and is lost; at or above it the ray is totally reflected and propagates for kilometers: `theta_c = arcsin(n_clad / n_core)`. For G.652 (`n_core = 1.4530`, `n_clad = 1.4462`) the critical angle is ~84.5 degrees from the normal — almost grazing. The textbook's Fig. 2-6 shows three rays: two below the critical angle escape, one above is trapped.

### Numerical aperture and the acceptance cone

Light must **enter** the fiber before it can be guided. The **numerical aperture** measures the cone of external angles that couple into guided rays: `NA = sqrt(n_core^2 - n_clad^2)`. For G.652, `NA ~ 0.14`, so the acceptance-cone half-angle is `arcsin(0.14) ~ 8.1 degrees`. A larger NA captures more light but accepts more rays at more internal angles — the root cause of multimode distortion. OM4 laser-optimized multimode fiber raises NA to ~0.20 to couple efficiently from a VCSEL, at the cost of supporting many modes.

### V-number: the single-mode / multimode cutoff

A fiber's **normalized frequency** collapses core radius `a`, wavelength `lambda`, and NA into one dimensionless number: `V = (2*pi*a/lambda)*NA`. The hard rule: **`V < 2.405` means only the fundamental `LP01` mode propagates** — single-mode. Above it, higher-order modes (`LP11`, `LP21`, ...) appear. The crossover is the **cutoff wavelength** `lambda_cutoff = (2*pi*a*NA)/2.405`. The demo fibers illustrate the split:

| Fiber | Core radius `a` | NA | V at 1.55 um | Cutoff | Mode at 1550 nm |
|---|---|---|---|---|---|
| Single-mode G.652 | 4.1 um | 0.140 | 2.33 | 1.50 um | single (LP01 only) |
| Multimode OM4 | 25.0 um | 0.200 | 20.25 | 13.05 um | hundreds of modes |

The G.652 cutoff at 1.50 um is why single-mode fiber is specified for the 1.31 and 1.55 um windows but **not** for 0.85 um — at 0.85 um its V-number exceeds 2.405 and it stops being single-mode. See `assets/fiber-optic-modes-and-attenuation-windows.svg`.

### The three attenuation windows

Silica glass is not uniformly transparent. Its near-IR loss curve has three valleys separated by an `OH` water-absorption peak near 1.4 um; each valley is a **window** 25,000-30,000 GHz wide:

| Window | Wavelength | Loss | Dispersion D | What it enabled |
|---|---|---|---|---|
| 1st | 0.85 um | ~2.5 dB/km | ~-85 ps/nm/km | GaAs lasers + detectors on one chip; short-reach LAN |
| 2nd | 1.30 um | ~0.38 dB/km | ~0 ps/nm/km (G.652 zero) | Low loss + zero dispersion; campus / metro |
| 3rd | 1.55 um | ~0.22 dB/km | ~17 ps/nm/km | Silica loss minimum; the **EDFA** amplifier band; long-haul WDM |

The 0.85 um band came first because GaAs lasers and silicon electronics share one material system; it loses ~2.5 dB/km so it stays in short links. The 1.30 um band sits at G.652's **zero-dispersion wavelength**, so pulses barely spread. The 1.55 um band has the lowest loss and is the only window where the **erbium-doped fiber amplifier (EDFA)** works directly in the optical domain, which is why every long-haul and submarine WDM system lives there.

### The decibel and the link power budget

Attenuation in dB is `10 * log10(P_in / P_out)`, so a factor-of-two loss is `10*log10(2) = 3.01 dB` (the textbook's worked example). Power in **dBm** is `10*log10(P_mW)` (1 mW = 0 dBm). The link budget sums every loss:

| Component | Loss (typical) |
|---|---|
| Fiber, per km | alpha (window-dependent) |
| Connector pair (physical contact) | ~0.35 dB each |
| Fusion splice | ~0.1 dB each |

`P_rx(dBm) = P_launch(dBm) - total_loss`; **margin** = `P_rx - sensitivity`. Worked 40 km example from `code/main.py` (0 dBm launch, -28 dBm, 2 connectors):

| Window | Fiber loss | Connector loss | Total | Received | Margin |
|---|---|---|---|---|---|
| 0.85 um | 100.0 dB | 0.7 dB | 100.7 dB | -100.7 dBm | -72.7 dB (FAIL) |
| 1.30 um | 15.2 dB | 0.7 dB | 15.9 dB | -15.9 dBm | +12.1 dB |
| 1.55 um | 8.8 dB | 0.7 dB | 9.5 dB | -9.5 dBm | +18.5 dB |

The 0.85 um part fails by ~73 dB; both single-mode windows pass. The **power-limited** span is `(P_launch - sensitivity - connector_loss) / alpha`: 10.9 km at 0.85 um, 71.8 km at 1.30 um, 124.1 km at 1.55 um. The SVG renders this budget as bars.

### Chromatic dispersion: the other reach limit

Loss is not the only thing that ends a link. Any real laser has a spectral width `DeltaLambda`, and different wavelengths travel at different speeds in glass. The pulse spreads: `DeltaT = |D| * L * DeltaLambda` (D in ps/(nm*km)). A common rule keeps broadening under ~30% of the bit period. At 10 Gbps the bit period is `1/10e9 = 100 ps`. The demo takes a 0.1 nm laser over 80 km:

| Window | D (ps/nm/km) | Spread / 80 km | Bit period | Spread / bit | Max km (30% rule) |
|---|---|---|---|---|---|
| 0.85 um | -85 | 680 ps | 100 ps | 680% | 3.5 km |
| 1.30 um | 0 | 0 ps | 100 ps | 0% | infinite (loss-limited) |
| 1.55 um | 17 | 136 ps | 100 ps | 136% | 17.6 km |

At 1.30 um dispersion is zero, so the 71.8 km power limit binds. At 1.55 um the dispersion limit (17.6 km) is far tighter than the power limit (124.1 km), which is why long 10G systems at 1.55 um use **dispersion-shifted fiber**, **dispersion-compensating fiber**, or external modulation to narrow `DeltaLambda`. The textbook also describes **solitons** — `1/cosh(t)`-shaped pulses whose self-phase modulation cancels chromatic dispersion, reaching thousands of km.

### Single-mode versus multimode in practice

A 50 um multimode core supports hundreds of modes, each taking a different path length. Even with a monochromatic source the modes arrive at different times — **intermodal dispersion**, of order tens of ns/km, which is why 10GBASE-SR is specified only to ~300 m on OM4. A single-mode core (8-10 um) admits one mode, killing intermodal dispersion and enabling 100 Gbps over 100 km with no in-line amplification. The trade-off is cost: single-mode lasers, connectors, and alignment are tighter. This is the datacenter split: multimode VCSELs for intra-row (cheap, short), single-mode for inter-building and long-haul (expensive, far).

## Build It

1. Read `code/main.py`. Three models: `analyze_fiber()` (modes: NA, V, cutoff), `link_budget()` / `max_span_km()` (power budget), `dispersion_limit()` (dispersion slot budget).
2. Run it: `python3 code/main.py`. Confirm the G.652 V-number at 1.55 um is 2.33 (single-mode) and OM4 is 20.25 (multimode).
3. Confirm the sanity check prints `3.01 dB` for a factor-of-two power loss.
4. Change `length_km` to 120 km. The 1.30 um margin goes negative while 1.55 um still passes — why long-haul lives at 1.55 um.
5. Change `spectral_width_nm` from 0.1 to 1.0 and watch the 1.55 um max span collapse from 17.6 to 1.76 km — why direct-modulated lasers cannot do long 10G.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Classify a fiber | V-number vs 2.405 | Single-mode iff V < 2.405 at the operating wavelength |
| Size a power budget | dBm received, margin | Margin >= 3 dB; every connector/splice counted; fiber loss = alpha * L |
| Pick a window | Loss, dispersion, tech | 0.85 um short reach; 1.30 um metro; 1.55 um long-haul + EDFA |
| Find the real reach | min(power span, dispersion span) | At 1.55 um 10G dispersion binds, not power |
| Catch a bad transceiver | Rx power below sensitivity | 0.85 um VCSEL on 40 km fails by tens of dB before dispersion matters |
| Diagnose pulse overlap | Spread vs bit period | Spread > ~30% of bit period closes the eye and raises BER |

## Ship It

Produce one artifact under `outputs/`:

- A link design sheet for a span you choose (distance, transceiver, fiber): V-number classification, power budget for all three windows, dispersion-limited span, and the chosen window with a one-sentence justification. Start from `code/main.py` output and annotate the failure mode you tested (e.g. 0.85 um failing 40 km, or 1.55 um failing when the laser linewidth widens). The artifact lives at `outputs/prompt-fiber-optic-modes-and-attenuation-windows.md`.

## Exercises

1. An 8.2 um core single-mode fiber has `n_core = 1.4530`, `n_clad = 1.4462`. Compute its V-number at 0.85, 1.30, and 1.55 um. At which wavelengths is it actually single-mode, and what does that tell you about a 0.85 um transceiver on it?
2. A 0 dBm launch, -25 dBm receiver, 60 km of fiber, one splice. Compute received power and margin at 1.30 um (0.38 dB/km) and 1.55 um (0.22 dB/km). Which works, and by how much?
3. A directly-modulated 10G laser at 1.55 um has a 1.0 nm linewidth. Compute the dispersion-limited span and explain in one sentence why long-reach 10G uses external modulation.
4. A 300 m OM4 link at 0.85 um has a fine power budget but errors out at 10G and works at 1G. Name the failure mode and why lowering the bitrate fixes it.
5. You need 100 km unrepeated at 10G. Using the demo numbers, show 1.30 um is power-limited (71.8 km) while 1.55 um is dispersion-limited (17.6 km). What two engineering choices let 1.55 um reach 100 km?
6. An EDFA only amplifies in the 1.55 um band. Explain why this, plus the loss minimum at 1.55 um, makes WDM long-haul and submarine systems overwhelmingly 1.55 um despite worse dispersion.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Numerical aperture (NA) | "how much light it catches" | `sqrt(n_core^2 - n_clad^2)`, sine of the acceptance-cone half-angle |
| Critical angle | "the bounce angle" | `arcsin(n_clad/n_core)`; below it rays escape, at/above it totally reflected |
| V-number | "the mode number" | `(2*pi*a/lambda)*NA`; below 2.405 only LP01 propagates |
| Cutoff wavelength | "where it becomes single-mode" | Longest wavelength below which higher-order modes appear; G.652 ~1.50 um |
| Single-mode fiber | "thin fiber" | 8-10 um core, V < 2.405, one mode, no intermodal dispersion |
| Multimode fiber | "thick fiber" | 50 um core, hundreds of modes, intermodal-dispersion-limited to short reach |
| Attenuation window | "a band you use" | A near-IR silica loss valley: 0.85, 1.30, or 1.55 um; each 25,000-30,000 GHz |
| dB / dBm | "loss / power" | dB is a ratio `10*log10(P_in/P_out)`; dBm is power relative to 1 mW |
| Chromatic dispersion | "pulse spreading" | `|D|*L*DeltaLambda`; different wavelengths travel at different speeds |
| EDFA | "the optical amp" | Erbium-doped fiber amplifier; amplifies 1.55 um light in the optical domain |
| Soliton | "a special pulse" | `1/cosh`-shaped pulse whose self-phase modulation cancels chromatic dispersion |

## Further Reading

- **ITU-T G.652** — single-mode fiber spec (9.7-10.1 um mode field, ~0.22 dB/km at 1310/1550, zero dispersion at 1310 nm); G.652.D is the low-water-peak, low-PMD variant.
- **ITU-T G.655** — non-zero dispersion-shifted fiber for WDM at 1.55 um.
- **IEEE 802.3** — 10GBASE-SR (0.85 um MMF, 300 m), 10GBASE-LR (1.31 um SMF, 10 km), 10GBASE-ER (1.55 um SMF, 40 km), 100GBASE-LR4/ER4.
- **IEC 60793** / **TIA-568.3-D** — OM3/OM4/OM5 multimode and OS2 single-mode classes.
- Agrawal, *Fiber-Optic Communication Systems*, 4th ed., Wiley — chapters 2-3.
- Mollenauer & Gordon, *Solitons in Optical Fibers* — soliton shape and dispersion cancellation.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 2, Section 2.2.5.
