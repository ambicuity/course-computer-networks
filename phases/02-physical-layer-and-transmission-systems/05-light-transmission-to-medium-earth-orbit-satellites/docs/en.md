# Light Transmission to Medium-Earth Orbit Satellites

> Unguided optical links (free-space optics, FSO) and Medium-Earth Orbit (MEO) satellites sit at opposite ends of the same physical-layer trade-off: how far the signal travels versus how much it costs in delay, pointing precision, and number of relays. A laser link uses a beam roughly 1 mm wide that must hit a photodetector hundreds of meters away — modulated as a pulse of light for a 1 bit and darkness for a 0, with no FCC license required because the carrier is ~10^14 Hz infrared, not licensed RF. MEO satellites orbit at ~20,200 km (the GPS constellation of ~30 satellites), between the Lower and Upper Van Allen radiation belts, with one-way propagation latency of roughly 35–85 ms and an orbital period near 6 hours, so ground antennas must *track* them. Round-trip delay is dominated by speed-of-light propagation `t = 2d/c` where c ≈ 3×10^8 m/s in vacuum, not by switching. The two failure modes that define this lesson are *beam misalignment* (wind, thermal gradients, scintillation, rain/fog attenuation for FSO) and *coverage gaps* (too few satellites for a given altitude). This lesson builds a Python link-budget and latency calculator that turns those physics into numbers an engineer can defend.

**Type:** Learn
**Languages:** Python, signal diagrams
**Prerequisites:** Phase 02 lessons on the electromagnetic spectrum, fiber optics, and transmission impairments
**Time:** ~75 minutes

## Learning Objectives

- Compute one-way and round-trip propagation latency for GEO (35,800 km), MEO (20,200 km), and LEO (750 km) using `t = d/c`, and explain why distance, not switching, dominates.
- Explain why MEO satellites must be tracked while GEO satellites appear motionless, from Kepler's third law (`T ∝ r^{3/2}`).
- Describe the free-space optics (FSO) signaling model — 1 bit = pulse of light, 0 bit = absence — and list its four dominant impairments (pointing error, scintillation, rain/fog, beam divergence).
- Estimate the number of satellites needed for global coverage as a function of altitude and footprint, and state why LEO needs ~50 while GEO needs 3.
- Justify why FSO needs no FCC license and why a narrow beam is simultaneously its security strength and its alignment weakness.
- Produce a reusable link-budget / latency artifact and read its output to make a deploy-or-reject decision.

## The Problem

A field engineer must connect two buildings 500 m apart whose fiber duct is full, and separately estimate whether a navigation-grade satellite link can support a low-latency control loop. Both reach for unguided technologies that share one physics core: **light (or RF) travelling through free space, where the carrier is the electromagnetic wave itself and the budget is set by geometry and the speed of light.**

The symptoms are concrete. The rooftop laser link works on a clear morning, then drops to zero in fog and "flickers" on a hot windy afternoon — the beam is physically walking off the photodetector. The satellite link shows a stubborn ~270 ms round trip on a GEO bird that no bandwidth upgrade fixes, because the delay is `2 × 35,800 km ÷ c ≈ 240 ms` of pure propagation plus relay overhead. The engineer's job is to reduce vague complaints ("it's slow", "it's flaky") to layer-1 evidence: a latency number from a distance, a link margin in dB, and a satellite count for continuous coverage.

## The Concept

### Unguided optical signaling (free-space optics)

Optical signaling through air is centuries old — Paul Revere's "one if by land, two if by sea" was binary optical signaling from the Old North Church. The modern version mounts a **laser and a photodetector on each of two rooftops**. Because a laser is inherently *unidirectional*, a duplex link needs two lasers and two photodetectors — one pair per direction. The signaling convention is the same as fiber: a **pulse of light is a 1 bit, the absence of light is a 0 bit**.

This scheme has four genuine engineering advantages and one structural weakness:

| Property | FSO laser link | Why it matters |
|---|---|---|
| Bandwidth | Very high (carrier ~3×10^14 Hz) | Gbps capacity at low cost |
| Licensing | **No FCC license** | Infrared carrier is unlicensed, unlike microwave |
| Security | Hard to tap a 1 mm beam | Eavesdropper must physically intercept the cone |
| Install | Rooftop boxes, no trenching | Days, not months — useful when ducts are full |
| **Weakness** | Aiming 1 mm beam at a pinhead 500 m away | Needs marksmanship; lenses *defocus* slightly to widen the target |

The narrow beam is both the strength (security, no interference) and the weakness (alignment). Engineers deliberately add lenses to **defocus the beam slightly** so it forms a wider cone at the receiver, trading some power density for pointing tolerance.

### The four FSO impairments

The terrestrial FSO link fails in four physically distinct ways. The SVG (`assets/light-transmission-to-medium-earth-orbit-satellites.svg`) shows the beam geometry and each impairment:

1. **Pointing / misalignment error** — building sway, mount creep, and *wind* push the beam off the detector. A 1 mm beam over 500 m has an angular tolerance of roughly `arctan(0.001 / 500) ≈ 0.0001°`.
2. **Scintillation** — *temperature gradients* create air cells of varying refractive index that bend the beam moment-to-moment, like a road mirage. This causes amplitude "flicker".
3. **Atmospheric absorption / scattering** — laser beams **cannot penetrate rain or thick fog**; clear-day links can go fully dark in dense fog. Note: these impairments *vanish* when both endpoints are spacecraft (vacuum), which is why inter-satellite optical links are attractive.
4. **Beam divergence loss** — even the best laser spreads with distance; received power falls roughly as `1/d^2` over the divergence cone.

`code/main.py` includes an FSO link-budget estimator that takes transmit power, divergence angle, distance, and an atmospheric loss term, then reports received power and link margin in dB.

### Satellite orbital regions and the Van Allen belts

A satellite's altitude is not free to choose. Two **Van Allen belts** — layers of charged particles trapped by Earth's magnetic field — would destroy electronics flown inside them. This carves the usable space into three regions:

| Region | Altitude | One-way latency (≈) | RTT (≈) | Period | Sats for global coverage | Must track? |
|---|---|---|---|---|---|---|
| **GEO** (Geostationary) | 35,800 km | ~120 ms | ~270 ms | 24 h | 3 | No |
| **MEO** (Medium-Earth) | ~20,200 km | ~35–85 ms | ~70–170 ms | ~6–12 h | ~10 | **Yes** |
| **LEO** (Low-Earth) | ~750 km | ~1–4 ms | ~1–7 ms | ~90–100 min | ~50–66 | Yes |

MEO sits **between the lower and upper Van Allen belts**. The canonical MEO system is the **GPS constellation: ~30 satellites at ~20,200 km**, used for navigation rather than telecom. Because MEOs **drift slowly in longitude (~6 h to circle the Earth as seen from the ground)**, ground antennas must track them — unlike a GEO bird, which appears motionless.

### Why GEO is motionless and MEO is not — Kepler's third law

Kepler's third law says the orbital period varies as the orbital radius to the 3/2 power:

```
T ∝ r^(3/2)
```

- At ~35,800 km altitude the period is exactly **24 hours**, matching Earth's rotation, so a GEO satellite hovers over one longitude — Arthur C. Clarke's 1945 insight.
- At ~20,200 km the period drops below a day, so the MEO satellite *slides* across the sky.
- Near the surface (~750 km LEO) the period falls to ~90 minutes, so each satellite is overhead for only minutes and you need a large constellation with hand-off.

This single law explains the whole "satellites needed" column above: lower orbit → shorter period → faster ground track → more satellites for continuous coverage, but also lower latency and cheaper transmitters (smaller footprint, closer target).

### Latency is propagation, not switching

The defining number for any satellite link is **propagation delay**, computed directly from geometry:

```
one-way delay  t = d / c
round-trip     RTT = 2 d / c        (single hop, ignoring switching)
```

with c ≈ 299,792,458 m/s ≈ 3×10^8 m/s in vacuum. Worked examples (straight-up path; a real slant path is longer):

- **GEO**: `t = 35,800,000 m ÷ 3×10^8 ≈ 119 ms`, so RTT ≈ 238 ms (the book quotes ~270 ms including relay/processing).
- **MEO/GPS**: `t = 20,200,000 m ÷ 3×10^8 ≈ 67 ms`, RTT ≈ 135 ms.
- **LEO**: `t = 750,000 m ÷ 3×10^8 ≈ 2.5 ms`, RTT ≈ 5 ms.

The key engineering insight: **no bandwidth upgrade reduces propagation delay.** A GEO control loop is physically incapable of sub-200 ms RTT. If the application needs low latency, the answer is a lower orbit and more satellites, not a fatter pipe. `code/main.py` computes these directly and adds an optional slant-range correction for a given elevation angle.

### Bent pipe vs. on-board switching

A satellite is essentially a **microwave repeater in the sky** with several **transponders** (a modern bird has ~40, each ~36 MHz wide). A transponder that listens on one frequency, amplifies, and rebroadcasts on another is a **bent pipe** — simple, but it *amplifies the uplink noise too*. On-board digital regeneration instead cleans up the signal and routes data streams, improving the noise budget. This distinguishes mesh designs that relay traffic in space (the LEO Iridium grid) from bent-pipe designs (Globalstar) that bounce every call back to a ground station.

## Build It

1. Read `code/main.py`. It has two engines: a **satellite latency calculator** (`propagation_delay`, `slant_range`, `rtt`) and an **FSO link-budget estimator** (`fso_link_budget`).
2. Run `python3 main.py`. The demo prints a latency table for GEO/MEO/LEO and an FSO budget for a 500 m rooftop link in clear air, moderate fog, and dense fog.
3. Change the MEO altitude to a real GPS value (20,200 km) and confirm the one-way delay lands near 67 ms.
4. For the FSO link, lower transmit power until the link margin goes negative — that is the fade threshold where the link drops. Note which weather column fails first.
5. Identify, from the output, the *one* number you would put in a runbook to justify "GEO cannot meet a 150 ms RTT SLA."

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Justify a latency SLA verdict | `rtt()` output for the chosen orbit | You quote `RTT = 2d/c` and the altitude, not a vendor brochure number |
| Diagnose a flaky rooftop FSO link | Link margin (dB) per weather state | Margin is positive in clear air but negative in fog → impairment is atmospheric, not the radio |
| Size a constellation | Period from Kepler + footprint | You explain why LEO needs ~50 and GEO needs 3 |
| Choose orbit for a control loop | Latency table across GEO/MEO/LEO | You pick MEO/LEO for low latency and accept the tracking + satellite-count cost |
| Defend "no license needed" | Carrier frequency of the FSO link | You note the ~10^14 Hz infrared carrier is unlicensed, unlike microwave |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **link-budget + latency runbook** that, given altitude (or distance) and weather, prints latency and link margin and a deploy/reject verdict — driven by `code/main.py`.
- Start from [`outputs/prompt-light-transmission-to-medium-earth-orbit-satellites.md`](../outputs/prompt-light-transmission-to-medium-earth-orbit-satellites.md) and paste in your own scenario (e.g. a 1.2 km campus FSO link, or an MEO navigation downlink at 20,200 km).

## Exercises

1. A vendor proposes a GEO link for a remote-surgery control loop requiring **RTT ≤ 150 ms**. Using `rtt()` at 35,800 km, prove the proposal cannot meet the SLA, then compute the maximum altitude that *can* and name the orbit class.
2. A 500 m rooftop FSO link works at 09:00 and fails at 15:00 on a hot, breezy day. There is no rain. Which of the four FSO impairments are in play, and what cheap mechanical change (hint: lenses) increases pointing tolerance?
3. GPS satellites orbit at 20,200 km with a period near 12 hours. Using Kepler's `T ∝ r^{3/2}` and the 24 h / 35,800 km GEO anchor, sanity-check that 20,200 km gives a sub-24 h period, and explain why GPS receivers therefore see satellites *move*.
4. Compute the slant-range latency penalty for an MEO satellite seen at 20° elevation versus straight overhead. Roughly how many extra milliseconds of one-way delay does the low elevation cost?
5. Compare a bent-pipe MEO/LEO design with an on-board-regeneration design for a link with a noisy uplink. Which one keeps uplink noise out of the downlink, and why does that improve the effective SNR?
6. The same infrared FSO link that fails in terrestrial fog is proposed for an **inter-satellite** optical link. Explain why three of the four impairments disappear in vacuum, and which one (pointing) remains the hard problem.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Free-space optics (FSO) | "rooftop lasers" | Unguided optical link; 1 bit = light pulse, 0 = darkness; needs one laser + photodetector per direction |
| Beam divergence | "the beam spreads" | Deliberate slight *defocus* via lenses to widen the target so pointing is feasible; costs power density |
| Scintillation | "the link flickers" | Refractive-index turbulence from temperature gradients bending the beam, not a hardware fault |
| MEO | "the GPS orbit" | ~20,200 km, between the Van Allen belts, ~6–12 h period, must be tracked, ~35–85 ms latency |
| GEO | "fixed satellite" | 35,800 km, 24 h period, appears motionless, ~270 ms RTT, only 3 needed for global coverage |
| Van Allen belts | "radiation" | Charged-particle layers that destroy satellites flown inside them; they fix the GEO/MEO/LEO altitude bands |
| Bent pipe | "the satellite relays" | Listen-amplify-rebroadcast transponder that also amplifies uplink noise; no on-board regeneration |
| Transponder | "a satellite channel" | One of ~40 onboard ~36 MHz units that shift frequency to avoid uplink/downlink interference |
| Propagation delay | "the lag" | `d/c` — the speed-of-light floor that no bandwidth upgrade can remove |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 6th ed., Chapter 2 — §2.3 (free-space optics) and §2.4 (GEO/MEO/LEO satellites, Van Allen belts, transponders).
- Arthur C. Clarke, "Extra-Terrestrial Relays," *Wireless World*, October 1945 — the original geostationary-orbit proposal.
- ITU-R S.1428 and ITU orbital slot allocation — geostationary 2° spacing and slot governance.
- IEEE 802.11 / Bluetooth specs — spread-spectrum context; ITU-T G.652 — single-mode fiber, for the guided-vs-unguided light contrast.
- Kepler's third law (`T² ∝ r³`) — the period-vs-altitude trade-off behind the satellite-count column.
