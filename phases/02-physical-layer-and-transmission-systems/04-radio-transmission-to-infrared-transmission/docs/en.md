# Radio Transmission to Infrared Transmission

> Three unguided bands, three personalities. **Radio** (VLF through VHF, kHz–300 MHz) is omnidirectional, penetrates walls, and bends around the earth — VLF/LF/MF ride the ground wave to ~1000 km, HF refracts off the ionosphere (100–500 km up) for intercontinental ham contacts. **Microwave** (above ~100 MHz, GHz range) travels in straight lines, focuses into a parabolic beam, and built the long-distance telephone backbone (MCI = Microwave Communications, Inc.) — but it needs line-of-sight repeaters (~80 km apart for 100 m towers), suffers **multipath fading** from out-of-phase reflected copies, and gets eaten by rain above ~4 GHz where water absorbs the few-centimeter waves. **Infrared** (just below visible light) is short-range, directional, blocked by solid walls — which is exactly why your TV remote (IrDA) does not control your neighbor's set and needs no FCC license. Free-space attenuation follows the inverse-square law: ~6 dB lost per doubling of distance versus ~20 dB/100 m for twisted pair. Unlicensed **ISM** (902–928 MHz, 2.4–2.4835 GHz) and **U-NII** (5 GHz) bands cap transmit power (~1 W) and mandate spread spectrum so uncoordinated devices coexist.

**Type:** Learn
**Languages:** Python (stdlib link-budget + propagation model), signal diagrams
**Prerequisites:** Phase 2 lessons on the electromagnetic spectrum, dB/SNR, and spread spectrum
**Time:** ~70 minutes

## Learning Objectives

- Classify an unguided link as radio, microwave, or infrared from its frequency, and predict its propagation mode (ground wave, sky wave / ionospheric refraction, line-of-sight).
- Compute free-space path loss with the Friis equation and reason about the ~6 dB-per-doubling rule versus the per-unit-distance loss of guided media.
- Explain multipath fading as phase cancellation of delayed reflections, and why operators keep ~10% of channels idle as spares.
- Decide whether a band is licensed or unlicensed (ISM 902–928 MHz / 2.4 GHz, U-NII 5 GHz) and what power and spread-spectrum constraints apply.
- Justify why infrared is wall-blocked, license-free, and harder to eavesdrop, and where IrDA fits versus 802.11.
- Estimate maximum microwave repeater spacing from tower height and the earth's curvature.

## The Problem

You are commissioning a 12 km point-to-point microwave backhaul link between two rooftops to carry traffic for a campus that lost its leased fiber. On the bench the radios show a healthy receive level of −62 dBm. Once installed, the link runs clean overnight, then at mid-morning the receive level collapses by 20 dB and the link drops for ten-minute stretches — always on bright days, never at night. Swapping radios does not help. The vendor blames your antennas; you suspect the air itself.

This is the daily reality of unguided transmission: the medium is invisible, shared, weather-dependent, and frequency-sensitive. To diagnose it you must reason about *which band you are in*, *how those waves propagate*, and *what physical effect — path loss, multipath fading, rain absorption, or thermal beam bending — matches the symptom*. The same physics decides whether a Wi-Fi access point reaches the far bedroom, whether your TV remote works around a corner (it does not), and whether a 60 GHz link can cross a street (oxygen absorption says barely).

## The Concept

Source: [`chapters/chapter-02-the-physical-layer.md`](../../../../chapters/chapter-02-the-physical-layer.md) — Radio, Microwave, and Infrared Transmission, plus the spectrum-politics and ISM/U-NII material that frames them.

As you climb the electromagnetic spectrum from long-wave radio toward visible light, the waves behave **more and more like light and less and less like radio**: they stop bending around obstacles, start travelling in straight lines, refuse to pass through walls, and become easier to focus into a tight beam. That single trend explains almost everything below. The diagram in [`assets/radio-transmission-to-infrared-transmission.svg`](../assets/radio-transmission-to-infrared-transmission.svg) lays the three bands on one frequency axis with their propagation modes.

### The three propagation modes of radio

The properties of radio waves are frequency-dependent, and the band determines how a signal reaches the receiver:

| Band | Frequency | Wavelength | Propagation | Real use | Range |
|------|-----------|-----------|-------------|----------|-------|
| VLF / LF / MF | 3 kHz – 3 MHz | 100 km – 100 m | Ground wave, follows earth's curvature | AM broadcast (MF) | up to ~1000 km |
| HF | 3 – 30 MHz | 100 – 10 m | Sky wave, refracts off ionosphere (100–500 km) | Ham, military, shortwave | intercontinental |
| VHF and up | > 30 MHz | < 10 m | Line-of-sight, ground wave absorbed | FM, TV, Wi-Fi, mobile | horizon-limited |

At low frequencies waves pass through obstacles well but power falls off sharply with distance and bandwidth is tiny (which is why AM radio sounds the way it does). This is why Boston AM ground waves do not reach New York: MF ground waves are absorbed within a few hundred km. HF is special — the ionosphere, a layer of charged particles, **refracts** waves back to earth, and under good conditions a signal bounces between sky and ground several times, letting hams talk across oceans with modest power.

### Path loss and the 6-dB-per-doubling rule

Unguided and guided media attenuate differently, and this is the single most useful contrast to internalize:

- **Guided media** lose a fixed *fraction per unit distance*: twisted pair drops ~20 dB per 100 m. Loss is linear in distance (in dB).
- **Free space** loses a fixed *fraction per doubling of distance*: ~6 dB every time you double the range. Loss is logarithmic in distance (in dB).

This is the inverse-square law (1/r²): the same energy spreads over a sphere whose surface grows as r². The Friis free-space equation makes it exact:

```
FSPL(dB) = 20·log10(d) + 20·log10(f) + 92.45     (d in km, f in GHz)
```

A worked example from `code/main.py`: a 2.4 GHz Wi-Fi link at 100 m has FSPL ≈ 80 dB; at 200 m ≈ 86 dB — exactly 6 dB more for the doubled distance. Because radio loses so slowly with distance, **interference between distant users is the dominant problem**, which is precisely why governments regulate transmitters.

### Microwave: focused beams, repeaters, and multipath fading

Above ~100 MHz waves travel in nearly straight lines and can be focused by a parabolic antenna into a tight, high-SNR beam — but the transmit and receive dishes must be **accurately aligned**, and the link is strictly line-of-sight. Two consequences:

1. **Repeater spacing follows the square root of tower height.** Because microwaves go straight and the earth curves away, the geometric horizon limits hop length. For 100 m towers, repeaters sit ~80 km apart; raising the towers extends the hop roughly as √(height). This is how MCI bypassed AT&T's copper — buy a small plot every ~50 km, raise a pole, no right-of-way needed.

2. **Multipath fading.** Some energy refracts off low atmospheric layers and arrives slightly later than the direct wave. When the delayed copy lands ~180° out of phase, the two cancel and the received signal collapses. It is **weather- and frequency-dependent** — which is exactly the mid-morning rooftop symptom in The Problem: daytime heating creates the atmospheric layering that produces the reflected, out-of-phase copy. Operators keep ~10% of channels idle as spares to switch in when a frequency fades.

Above ~4 GHz a second enemy appears: the waves are only a few centimeters long and **water absorbs them**, so rain attenuates the link. The only fixes for both fading and rain are to shut off the affected frequency/link and route around it.

### Licensed vs unlicensed: ISM and U-NII

To avoid total chaos, the ITU-R coordinates worldwide allocation and the FCC allocates in the US, using historically a beauty contest, a lottery, or — the modern method — **spectrum auctions** (the UK's 2000 3G auction fetched ~$40B against a ~$4B estimate). But some bands are deliberately *not* allocated: the **ISM** (Industrial, Scientific, Medical) bands let anyone transmit, controlled instead by strict power limits and mandatory spread spectrum so short range prevents interference:

| Band | Range | Width | Used by |
|------|-------|-------|---------|
| 900 MHz ISM | 902–928 MHz | 26 MHz | Early 802.11, cordless phones |
| 2.4 GHz ISM | 2.400–2.4835 GHz | 83.5 MHz | 802.11b/g, Bluetooth; **microwave-oven interference** |
| 5 GHz U-NII | 5.25–5.825 GHz (several sub-bands) | ~555 MHz | 802.11a, modern Wi-Fi |
| 60 GHz | 57–64 GHz | 7 GHz | Short-range HD streaming; **oxygen-absorbed** |

ISM devices must limit transmit power (e.g., ~1 W) and spread their signals. The 2.4 GHz band shares spectrum with microwave ovens and radar, which is a real source of Wi-Fi interference. The 60 GHz millimeter band has enormous bandwidth but oxygen absorption kills its range — perfect for one-room HD links, useless for reaching across a building.

### Infrared and free-space optics: when radio becomes light

Infrared sits just below visible light and behaves like light: short-range, directional, and **blocked by solid walls**. Your TV remote (standardized as **IrDA**, the Infrared Data Association) will not work if you stand between it and the set. The wall-blocking is a feature, not just a bug:

- An IR system in one room does not interfere with the room next door — no neighbor accidentally changing your channel.
- Eavesdropping is harder than with omnidirectional radio, because the signal is contained by walls.
- **No FCC license is needed** — IR is outside the regulated radio bands entirely.

The trade-off: IR cannot cover a building the way 802.11 does, so it stayed a desktop/peripheral technology. Going further up, **free-space optics** uses lasers between rooftops for very high bandwidth and good security (a narrow beam is hard to tap), but aiming a millimeter-wide beam over hundreds of meters is unforgiving, and sun-driven thermal convection currents can bend the beam off-target — the classic failure where a rooftop laser link works perfectly at night and fails every sunny morning.

### Decision logic: which band for which job

`code/main.py` encodes this rule set:

- Need to penetrate walls and reach the whole building → low-frequency **radio** (Wi-Fi at 2.4 GHz over 5 GHz when range matters more than throughput).
- Need a long, cheap, high-capacity point-to-point hop with line-of-sight → **microwave** with aligned dishes and repeaters every √(height)·k km.
- Need a short, secure, license-free link confined to one room → **infrared / IrDA**, or free-space optics for a rooftop bridge.
- Crossing rain or fog → avoid >4 GHz microwave and free-space optics; both are absorbed.

## Build It

`code/main.py` is a propagation and link-budget toolkit tied directly to the concepts above. To work through it:

1. Run `python3 main.py` and read the printed band classifier — feed it a frequency and confirm it names the band and propagation mode.
2. Inspect `friis_path_loss()` and verify the 6-dB-per-doubling rule by comparing 100 m and 200 m at 2.4 GHz.
3. Read `microwave_repeater_spacing()` and confirm ~80 km for 100 m towers, then see how √(height) scales the hop.
4. Trace `link_budget()` end to end: TX power + antenna gains − path loss − rain margin, then compare against receiver sensitivity to get the fade margin.
5. Study `recommend_band()` — the decision tree that maps wall-penetration, range, security, and weather needs to radio/microwave/infrared.

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Classify an unguided link | Carrier frequency, wavelength | You name the band and its propagation mode (ground/sky/LOS) without guessing |
| Predict coverage | Friis FSPL, fade margin vs RX sensitivity | Computed receive level is within a few dB of measured; margin > 0 means the link closes |
| Diagnose intermittent microwave drops | Time-of-day pattern, 20 dB dips, weather correlation | You identify multipath fading or rain absorption rather than blaming hardware |
| Choose licensed vs unlicensed | Band edges (902–928, 2.4–2.4835, 5 GHz), power cap | You know whether you need an FCC license and the ~1 W / spread-spectrum ISM rules |
| Justify infrared for a use case | Wall-blocking, no license, eavesdrop resistance | You pick IrDA where containment is the point, not where building-wide coverage is needed |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **link-budget worksheet** for a real or hypothetical microwave/Wi-Fi hop, showing TX power, gains, FSPL, rain margin, and the resulting fade margin.
- A **band-selection runbook**: given range, wall-penetration, security, weather, and licensing constraints, it outputs radio / microwave / infrared with the rule that fired.
- A **multipath-fading diagnosis checklist** mapping symptoms (time-of-day, weather, frequency-specific dips) to causes and fixes.

Start from the output of `code/main.py` and the SVG, then capture your own numbers.

## Exercises

1. A vendor quotes a 2.4 GHz link with −62 dBm at the bench and you measure −82 dBm mid-morning on sunny days only, recovering at night. Name the effect, explain the phase mechanism, and give two mitigations (frequency diversity / spare channels are one family).
2. You must link two buildings 60 km apart with microwave. Your towers are 45 m tall. Using the √(height) rule (anchor: 80 km at 100 m), estimate whether one hop suffices or you need a repeater, and state what limits the hop.
3. Compute the free-space path loss at 5 GHz over 1 km, then over 2 km, using Friis. Confirm the difference is ~6 dB and explain why doubling distance — not adding a fixed length — is what costs 6 dB.
4. A product manager wants 60 GHz radios to stream HD video between two buildings across a parking lot. Explain the oxygen-absorption problem and propose the correct band or medium instead.
5. Compare an IrDA remote and a 2.4 GHz Wi-Fi remote for a hospital where each patient room must not interfere with the next. Argue which property of infrared makes it the better fit and what you give up.
6. Your campus runs both a 900 MHz ISM link and a 2.4 GHz Wi-Fi network. The Wi-Fi degrades whenever the cafeteria microwave runs. Explain the band overlap and two unlicensed-band constraints (power, spread spectrum) that exist precisely to limit this.

## Key Terms

| Term | What people say | What it actually means |
|------|-----------------|------------------------|
| Path loss | "The signal gets weaker" | Inverse-square free-space attenuation: ~6 dB lost per doubling of distance, vs ~20 dB/100 m fixed-per-length for twisted pair |
| Multipath fading | "Random dropouts" | A delayed, reflected copy arrives ~180° out of phase and cancels the direct wave; weather- and frequency-dependent, mitigated with spare channels |
| Ground wave | "AM range" | VLF/LF/MF propagation that follows the earth's curvature for up to ~1000 km |
| Sky wave | "Shortwave bounce" | HF refraction off the ionosphere (100–500 km altitude), enabling intercontinental links |
| Line-of-sight | "Needs clear view" | VHF-and-up straight-line propagation; horizon-limited, needs repeaters as the earth curves away |
| ISM band | "The free Wi-Fi spectrum" | Unlicensed 902–928 MHz / 2.4–2.4835 GHz bands with ~1 W power cap and mandatory spread spectrum |
| U-NII | "The 5 GHz band" | Unlicensed National Information Infrastructure bands around 5.25–5.825 GHz used by 802.11a |
| Friis equation | "The range formula" | FSPL = 20·log₁₀(d) + 20·log₁₀(f) + 92.45 (km, GHz) — free-space loss from distance and frequency |
| IrDA | "The remote-control thing" | Infrared Data Association standard; wall-blocked, license-free, eavesdrop-resistant short-range link |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., §2.3.2–2.3.4 (Radio, Microwave, Infrared) and §2.3.1 (the electromagnetic spectrum).
- ITU-R recommendations on the radio spectrum; ITU-R P.525 (free-space attenuation) and P.530 (terrestrial line-of-sight propagation, including multipath fading).
- FCC Part 15 — rules for unlicensed ISM/U-NII operation, power limits, and spread-spectrum requirements.
- IEEE 802.11 — wireless LAN PHY operating in the 2.4 GHz ISM and 5 GHz U-NII bands.
- IrDA physical layer specifications (Infrared Data Association) for short-range optical links.
- Friis, "A Note on a Simple Transmission Formula," *Proc. IRE*, 1946 — origin of the free-space path-loss equation.
