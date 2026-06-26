# Magnetic Media to Coaxial Cable

> The first three guided transmission media in Tanenbaum 2.2 — magnetic media, twisted pair, and coaxial cable — span an enormous range of the bandwidth/latency trade space. A 60×60×60 cm box of ~1000 Ultrium tapes at 800 GB each holds 800 TB (6.4 Pb); FedExed overnight (86,400 s) that is ~74 Gbps of *throughput* at ~0.5 cents/GB, yet with a *latency* of hours — the "never underestimate the bandwidth of a station wagon full of tapes" rule. Twisted pair carries a signal as the **differential voltage** between two helically twisted copper wires (~1 mm), where the twist makes adjacent half-twists radiate out of phase so noise cancels; Cat 5 runs 100BASE-TX on 2 of 4 pairs, Cat 5e/6 run 1000BASE-T on all 4 pairs in both directions with echo cancellation, and Cat 6/7 are rated to 250–600 MHz. Coax wraps a stiff copper core in a dielectric inside a braided shield: **50 Ω** for digital (10BASE5/10BASE2 Ethernet), **75 Ω** for analog and DOCSIS cable Internet, the split being historical (300 Ω dipoles + 4:1 baluns), with usable bandwidth to a few GHz. This lesson makes the bandwidth-vs-latency trade quantitative and ties impedance, attenuation, and propagation delay to evidence you can compute. The companion `code/main.py` is a stdlib transmission-media calculator that ranks a sneakernet shipment against a live link and flags impedance mismatch.

**Type:** Learn
**Languages:** Python (stdlib), signal diagrams
**Prerequisites:** Phase 02 · 01 (bandwidth, Nyquist/Shannon limits, the decibel)
**Time:** ~70 minutes

## Learning Objectives

- Compute the *effective throughput* and *latency* of a sneakernet shipment and decide when a station wagon of tapes beats a network link.
- Explain why twisting wires and reading the **differential voltage** rejects common-mode noise, and map Cat 3/5/5e/6/7 to their bandwidth ratings and Ethernet uses.
- Distinguish 50 Ω from 75 Ω coax by application (digital Ethernet vs. analog/DOCSIS) and explain why the split is historical, not physical.
- Apply the reflection-coefficient formula Γ = (Z_L − Z_0)/(Z_L + Z_0) to predict the return loss from a connector/impedance mismatch.
- Read attenuation in dB/100 m and propagation delay (nominal velocity factor ~0.66c on coax) as the two evidence numbers that bound a cable run.

## The Problem

A bioinformatics lab must move 800 TB of sequencing data from a sequencer in San Diego to a compute cluster in Boston. The network team quotes a dedicated 10 Gbps link. An engineer protests: "Just ship the drives." Who is right?

Separately, a building's new 10GBASE-T run keeps failing certification at 80 m, and a CATV technician sees ghosting on a TV fed through a barrel connector someone scavenged from a parts bin. All three symptoms — slow bulk transfer, a failing copper certification, and a reflected signal — live at the physical layer, and all three are answered with the same four numbers: capacity, latency, attenuation, and impedance. This lesson makes those numbers computable so the argument stops being a vibe and becomes arithmetic.

## The Concept

### Magnetic media: throughput is not latency

Bulk transfer ("sneakernet") trades terrible latency for spectacular throughput. The canonical figures from Tanenbaum 2.2.1:

| Quantity | Value |
|---|---|
| Ultrium (LTO) tape capacity | 800 GB |
| Tapes per 60×60×60 cm box | ~1000 |
| Box capacity | 800 TB = 6.4 Pb (6400 Tb) |
| Overnight delivery time | 24 h = 86,400 s |
| Effective throughput | 6,400,000 Gb / 86,400 s ≈ **74 Gbps** |
| If 1 hour away by road | ≈ **1778 Gbps** |
| Cost (tape reuse + shipping) | ~$5000 / 800 TB ≈ **0.5 ¢/GB** |

The decision rule is a single inequality. Sneakernet wins when the data volume `V` divided by the link rate `R` exceeds the physical transit time `T_transit`:

```
T_network = V / R                 (plus protocol overhead)
T_sneakernet = T_transit          (write + drive + read, latency-dominated)
ship_if  V / R  >  T_transit
```

For 800 TB over 10 Gbps: `T_network = 6.4e15 bits / 1e10 bps = 640,000 s ≈ 7.4 days`. Overnight shipping is `~1 day`. Ship the drives. `code/main.py` computes both sides and prints the verdict; the SVG (`assets/magnetic-media-to-coaxial-cable.svg`) plots the crossover on a throughput-vs-latency plane so you can see the three media occupy different corners.

### Twisted pair: the differential trick

A twisted pair is two ~1 mm insulated copper wires wound helically "like a DNA molecule." Two things make it work:

1. **Twisting** — two parallel wires form an antenna; consecutive half-twists pick up an interfering wave with opposite phase, so the radiated/received noise largely cancels. More twists per meter = less crosstalk. This is exactly why Cat 5 (more twists) replaced Cat 3 using the same RJ-45 connector.
2. **Differential signaling** — the receiver reads `V_diff = V_+ − V_−`. External noise couples onto *both* wires nearly equally (common mode), so it subtracts out of the difference. This is common-mode rejection.

| Category | Rated bandwidth | Typical Ethernet use |
|---|---|---|
| Cat 3 | 16 MHz | 10BASE-T |
| Cat 5 | 100 MHz | 100BASE-TX (2 of 4 pairs) |
| Cat 5e | 100 MHz | 1000BASE-T (all 4 pairs, both directions) |
| Cat 6 | 250 MHz | 1000BASE-T / 10GBASE-T to 55 m |
| Cat 6a | 500 MHz | 10GBASE-T to 100 m |
| Cat 7 | 600 MHz | shielded (S/FTP), individual + overall shield |

100-Mbps Ethernet uses two of the four pairs (one per direction). 1-Gbps Ethernet (1000BASE-T) uses **all four pairs in both directions simultaneously**, which forces the receiver to subtract its own locally transmitted signal — echo cancellation. Through Cat 6 the cabling is **UTP** (Unshielded Twisted Pair); Cat 7 adds per-pair shielding plus an overall shield (S/FTP), reminiscent of IBM's early-1980s STP.

### Coaxial cable: geometry buys bandwidth and shielding

Coax is a stiff copper core, a dielectric insulator, a braided/foil outer conductor (the shield), and a plastic jacket. The concentric geometry confines the field between core and shield, giving high bandwidth (to a few GHz) with excellent noise immunity. Two impedances dominate:

| Type | Impedance | Primary use | Standards |
|---|---|---|---|
| Thicknet / digital | **50 Ω** | digital Ethernet, RF | 10BASE5 (RG-8), 10BASE2 (RG-58) |
| CATV / broadband | **75 Ω** | analog video, cable Internet | RG-6, RG-59, DOCSIS |

The 50/75 Ω split is *historical*, not because one impedance is "digital." Early dipole antennas were 300 Ω and 4:1 baluns made 75 Ω convenient; 50 Ω became the lab/RF standard. When cable-TV operators started offering Internet over their plant in the mid-1990s (DOCSIS), 75 Ω coax became a data medium too.

### Impedance matching and reflections

A transmission line must be **terminated** in its characteristic impedance `Z_0` or part of the wave reflects. The reflection coefficient at a load `Z_L` is:

```
Γ = (Z_L − Z_0) / (Z_L + Z_0)
Return Loss (dB) = −20 · log10(|Γ|)
VSWR = (1 + |Γ|) / (1 − |Γ|)
```

Worked example — a 75 Ω TV feed terminated by a 50 Ω barrel connector:

```
Γ = (50 − 75) / (50 + 75) = −25/125 = −0.20
|Γ| = 0.20  → 20% of voltage reflects → 4% of power
Return Loss = −20·log10(0.20) ≈ 14 dB
VSWR = 1.2 / 0.8 = 1.5
```

That reflected wave arrives back delayed and produces the "ghost" the CATV tech saw. A perfect match (`Z_L = Z_0`) gives `Γ = 0`, infinite return loss, VSWR 1.0. `code/main.py` computes Γ, return loss, and VSWR for any pair of impedances.

### Attenuation and propagation delay: the two run-length numbers

Two numbers bound a real cable run:

- **Attenuation** in dB/100 m rises with frequency. A signal that loses, say, 20 dB has 1/100 of its power left (`P/P_0 = 10^(−dB/10)`). This is why 10GBASE-T over Cat 6 is limited to ~55 m but Cat 6a reaches 100 m, and why coax runs get amplifiers.
- **Propagation delay**: signals travel at the velocity factor `VF` of the medium, typically `0.6–0.7c` on coax (dielectric-dependent), ~`0.64c` on UTP. One-way delay `t = length / (VF·c)`. For 100 m of UTP at `0.64c`: `t = 100 / (0.64·3e8) ≈ 521 ns`. This delay is what the original 10BASE5 5-4-3 repeater rule and Ethernet's 64-byte minimum-frame / collision-window budget are built around.

`P/P_0 = 10^(−A·L/1000/10)` where `A` is dB/100 m and `L` is metres lets you predict received power for any run length; `code/main.py` reports it alongside the delay.

### Putting the three media on one map

The SVG places magnetic media, twisted pair, and coax on a throughput (Gbps, log) vs. latency (log) plane. Magnetic media sits top-right: enormous throughput, hours of latency. Twisted pair and coax sit lower-left: modest-to-high throughput, microsecond latency. The crossover line is exactly the `V/R = T_transit` inequality — the boundary where shipping wins.

## Build It

1. Read the magnetic-media, twisted-pair, and coax sections of `code/main.py`; confirm the constants match the table above (800 GB tapes, 86,400 s, 50/75 Ω).
2. Run `python3 code/main.py`. It prints (a) the sneakernet-vs-link verdict for 800 TB, (b) a Cat-category lookup, (c) the Γ/return-loss/VSWR for a 50→75 Ω mismatch, and (d) attenuation + delay for a 100 m run.
3. Change the shipment to 5 TB over a 10 Gbps link and re-run — confirm the verdict flips to "use the network."
4. Feed `compute_reflection(75, 75)` and confirm Γ = 0, return loss = ∞, VSWR = 1.0 (perfect match).
5. Cross-check the SVG crossover line against the printed `V/R` and `T_transit` numbers.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Decide ship vs. transmit | `V/R` (link transfer time) vs. `T_transit` | You quote both times; the larger `V/R` justifies sneakernet for petabyte bulk |
| Pick a copper category | Required rate + run length vs. category MHz/distance table | Cat 6a for 10GBASE-T at 100 m; Cat 5e is rejected with a reason |
| Diagnose a reflection | Γ, return loss (dB), VSWR from measured impedances | A 50 Ω part on a 75 Ω feed gives Γ=−0.2, RL≈14 dB, VSWR 1.5 — matches the ghost |
| Bound a cable run | Attenuation (dB/100 m) and one-way propagation delay | Received power and delay computed; run rejected if power below receiver sensitivity |

## Ship It

Produce one artifact under `outputs/`:

- A media-selection runbook (sneakernet threshold table + Cat category chart + 50/75 Ω cheat sheet).
- The `code/main.py` calculator extended with your own cable's attenuation spec.
- A one-page impedance-mismatch troubleshooting card (Γ / return loss / VSWR with the ghost example).

Start from [`outputs/prompt-magnetic-media-to-coaxial-cable.md`](../outputs/prompt-magnetic-media-to-coaxial-cable.md).

## Exercises

1. A studio must move 2 PB of raw footage cross-country. The WAN link is 40 Gbps. Compute `V/R` and decide ship vs. transmit; then find the link rate at which the network beats overnight FedEx.
2. A contractor pulls Cat 5e for a new 10GBASE-T floor at 90 m runs. Explain, using the category table, why certification will fail and what cable fixes it.
3. Compute Γ, return loss, and VSWR for a 50 Ω transceiver driving a 75 Ω cable. Is the mismatch better or worse than the 75→50 Ω case, and why is the magnitude of Γ the same?
4. 10BASE2 ("thinnet") required a 50 Ω terminator at each end of the bus. Using the reflection formula, explain what happens to the segment if a terminator is missing (open circuit, `Z_L → ∞`).
5. A coax run shows 18 dB of loss at the operating frequency. What fraction of the transmitted power reaches the receiver? If the receiver needs −20 dBm and the transmitter sends 0 dBm, does the run pass?
6. Compute the one-way propagation delay of a 185 m 10BASE2 segment (VF ≈ 0.66) and relate it to why Ethernet defines a minimum frame size.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Sneakernet | "Just FedEx the drives" | Latency-dominated bulk transfer whose *throughput* (V/T_transit) can exceed any link while its *latency* is hours |
| Differential signaling | "Two wires instead of one" | Receiver reads V_+ − V_−; common-mode noise on both wires cancels (common-mode rejection) |
| Twist rate | "The cable is twisted" | Twists/meter set crosstalk; more twists (Cat 5 vs Cat 3) push usable bandwidth higher on the same connector |
| UTP vs STP | "Shielded or not" | Cat 3–6 are Unshielded Twisted Pair; Cat 7 adds per-pair + overall shield (S/FTP) |
| Characteristic impedance Z_0 | "Ohm rating of the cable" | The impedance a line must be terminated in to avoid reflections; 50 Ω digital, 75 Ω CATV |
| Reflection coefficient Γ | "Signal bounces back" | Γ = (Z_L−Z_0)/(Z_L+Z_0); fraction of voltage reflected at an impedance discontinuity |
| Return loss | "How good the match is" | −20·log10|Γ| in dB; higher is better, ∞ at a perfect match |
| Velocity factor | "Speed of the signal" | Fraction of c at which a wave travels in the medium (~0.66 on coax), sets propagation delay |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th/6th ed., §2.2 Guided Transmission Media (magnetic media, twisted pair, coaxial cable, power lines).
- ANSI/TIA-568 — Commercial Building Telecommunications Cabling Standard (Cat 5e/6/6a definitions and certification limits).
- ISO/IEC 11801 — generic cabling, Categories/Classes (Cat 7 / Class F).
- IEEE 802.3 — Ethernet: Clause 10 (10BASE5), Clause 10/11 (10BASE2), Clause 40 (1000BASE-T), Clause 55 (10GBASE-T).
- CableLabs DOCSIS specifications — data over 75 Ω HFC coaxial plant.
- IEC 61196 / MIL-C-17 — coaxial cable types (RG-6, RG-58, RG-8) and impedance specs.
