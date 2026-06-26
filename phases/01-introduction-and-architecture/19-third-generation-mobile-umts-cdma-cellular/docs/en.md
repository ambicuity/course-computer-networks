# Third-Generation Mobile Networks: UMTS, WCDMA, and the Cellular Design

> The third generation of mobile phone networks (3G, deployed from 2001) carries both digital voice and broadband data — the break from the voice-only 1G AMPS (1982) and 2G GSM (1991) designs. The dominant 3G system is **UMTS** (Universal Mobile Telecommunications System), also called **WCDMA** (Wideband Code Division Multiple Access) after its air interface, offering up to 14 Mbps downlink and ~6 Mbps uplink versus GSM's tens-of-kbps GPRS. The scarce, auctioned resource is **radio spectrum**, which forces the **cellular design**: the coverage area is carved into cells, each served by a **Node B** base station, controlled by an **RNC** (Radio Network Controller) — together the radio access network — bridged to a **core network** that is uniquely split into a *circuit-switched* half (MSC/GMSC/MGW toward the PSTN) and a *packet-switched* half (SGSN/GGSN toward the Internet). UMTS lets every cell reuse all frequencies because CDMA separates users by orthogonal spreading codes rather than frequency bands, and supports **soft handover** (connected to two Node Bs at once) where hard handover would tear the call. A **HSS** (Home Subscriber Server) locates each mobile for incoming calls, and a **SIM** card carries the keys for mutual authentication and air-interface encryption (Kasumi/f8/f9 in UMTS, an upgrade on GSM's A5/1). This lesson models the cellular reuse plan, the CDMA spreading/orthogonality math, and the UMTS handover decision so you can see the actual numbers these mechanisms leave behind.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Frequency-division and time-division multiplexing basics; the OSI/Internet layering contrast; an intuitive grasp of signal-to-interference ratio
**Time:** ~85 minutes

## Learning Objectives

- Explain why spectrum scarcity forces the cellular design and compute the capacity gain of a 7-cell reuse cluster versus a single omnidirectional cell.
- Quantify CDMA's near-far problem: derive the required power-control accuracy from the signal-to-interference ratio with N simultaneous users on one channel.
- Build the UMTS spreading example for a 3.84 Mcps chip rate, naming the chip sequence, the processing gain, and the bit energy after despreading.
- Trace a UMTS handover decision (signal threshold, candidate pilot set, soft vs hard) and state which branch preserves the call without interruption.
- Map a packet voice call and a packet data session onto the correct UMTS core nodes (MSC/GMSC vs SGSN/GGSN) and name the Iu-CS and Iu-PS interfaces.
- State the UMTS mutual-authentication and encryption chain (SIM-stored K, AKA challenge-response, f8 confidentiality, f9 integrity) and the attack it closes over GSM.

## The Problem

A national operator has paid billions for a 20 MHz slice of spectrum and has 4 billion subscribers worldwide to serve — far more than 20 MHz of analog FM voice could ever carry. Every caller in a city wants to talk at once, and nobody tolerates the choppy, half-duplex push-to-talk of the old days. The engineer's job: reuse that same 20 MHz across the whole city so that thousands of simultaneous users in thousands of cells share one band without garbling each other. 1G AMPS solved this poorly — it gave each call a dedicated frequency and barred reuse in the six surrounding cells, capping capacity. 2G GSM did better with TDMA into 8 slots and a 4/3/7 reuse cluster, but each cell still had to surrender most of the band to its neighbors. The 3G question is sharper: can a cell use *all* the spectrum *all* the time and still keep the interference from the six adjacent cells tolerable? The answer is CDMA, and it changes both the radio math and the network behind it.

## The Concept

### The cellular design and frequency reuse

The coverage area is tiled with hexagonal **cells**, each with a **base station** (Node B) at its center. The whole point is **frequency reuse**: the same channel can be reused in another cell far enough away that its signal has decayed below the interference floor. In a 1G FDMA system the band is split into *N* channel groups and a **reuse pattern** of *K* cells guarantees no two cells using the same group are adjacent. The classic cluster sizes are 4, 7, and 12.

If the system bandwidth is *B* total and the cluster size is *K*, each cell gets *B/K* of usable spectrum. The hex geometry gives a reuse distance

> D = R · √(3K)

where *R* is the cell radius. The capacity gain over a single omnidirectional cell is *K*-fold (you reuse the band *K* times in the same area) but each cell pays a 1/*K* cut in its own band. Worked example: a 7-cell cluster with radius 1 km reuses the same band at *D = √21 ≈ 4.58 km*. Doubling the cluster to 14 buys a quieter co-channel (SIR rises by ~6 dB) but halves per-cell capacity — the central cellular trade-off.

### CDMA and why 3G gives every cell every frequency

UMTS/WCDMA abandons the per-cell frequency partition. All cells transmit on the same 5 MHz WCDMA carrier (chip rate 3.84 Mcps). Users in the *same* cell are separated not by frequency or time slot but by **orthogonal spreading codes** — long pseudo-noise sequences multiplied with each user's bit stream so the signal occupies a wide band. The receiver correlates with the intended user's code; every other user appears as low-amplitude noise.

The decisive quantity is the **processing gain** *Gp* = chip rate / bit rate. For a 12.2 kbps voice call (AMR codec) on a 3.84 Mcps carrier:

> Gp = 3.84×10⁶ / 12.2×10³ ≈ 314, i.e. ~25 dB of processing gain.

After despreading, the wanted signal is lifted ~25 dB above every other user's wideband contribution. The catch is the **near-far problem**: a nearby transmitter would swamp a distant one. With *N* users sharing the channel and perfect power control so all arrive at the Node B at equal power *S*, the signal-to-interference ratio at the base station is

> SIR = S / ((N−1)·S) = 1/(N−1)

so the *energy per bit* after the processing gain is Eb/I₀ = Gp/(N−1). Demand Eb/I₀ ≥ 7 dB (~5) for voice, and the pole capacity is N ≤ 1 + Gp/5 ≈ 64 voice users per carrier — *regardless of frequency planning*, since every frequency is reused everywhere. This is why 3G's capacity dwarfed 1G/2G in the same bandwidth. The price is brutal power control: a user 10 dB closer than another must transmit 10 dB less power or wreck the SIR, so UMTS runs a 1500 Hz closed power-control loop on the uplink. `code/main.py` computes the SIR curve and pole capacity for a chosen Eb/I₀ target.

### Orthogonal spreading codes: a worked example

WCDMA uses **OVSF** (Orthogonal Variable Spreading Factor) codes on the downlink, organized as a binary code tree. Each code at spreading factor *SF* is *SF* chips long and is mutually orthogonal to every sibling on a different branch. A worked spreading of a 4-bit message `1011` under SF = 8 code `C = [+1 +1 +1 +1 −1 −1 −1 −1]` (Walsh-style):

| Bit | Logic value | Chips sent (bit × code) |
|---|---|---|
| 1 (logic "1") | +1 | +1 +1 +1 +1 −1 −1 −1 −1 |
| 0 (logic "0") | −1 | −1 −1 −1 −1 +1 +1 +1 +1 |
| 1 | +1 | +1 +1 +1 +1 −1 −1 −1 −1 |
| 1 | +1 | +1 +1 +1 +1 −1 −1 −1 −1 |

The receiver multiplies the incoming chips by the same code and sums (correlates). Sum over one bit period = +8 → bit was 1; −8 → bit was 0. A second user with a *different* orthogonal code contributes exactly 0 to the correlator output — that is the orthogonality that lets everyone share the band. `assets/umts-cdma-cellular-3g.svg` diagrams the OVSF tree and the spread-and-correlate path, and `code/main.py` includes a small OVSF generator and correlator so you can verify the zero-cross-correlation property numerically.

### The UMTS architecture: air interface, RAN, and a split core

UMTS has three layers, drawn in the textbook's Fig. 1-31 and in this lesson's SVG:

1. **Air interface ("Uu").** The radio protocol between mobile (UE) and Node B, based on WCDMA. This is the 5 MHz × 3.84 Mcps CDMA link above.
2. **Radio access network (RAN).** Node B (base station) + RNC (Radio Network Controller). The RNC controls how spectrum is used, manages handovers and power control, and multiplexes many UEs onto the Iu interface. The oddly named "Node B" was a placeholder that stuck.
3. **Core network.** Carries RAN traffic to the rest of the world and is uniquely *split*:

| Core half | Switching style | Key nodes | Interface | Connects to |
|---|---|---|---|---|
| Circuit-switched | Connection-oriented, reserves resources for the call | MSC (Mobile Switching Center), GMSC (Gateway MSC), MGW (Media Gateway) | Iu-CS | PSTN (voice) |
| Packet-switched | Connectionless per-packet forwarding | SGSN (Serving GPRS Support Node), GGSN (Gateway GPRS Support Node) | Iu-PS | Internet (data) |

The dual core is the surprise the textbook highlights: phone companies kept their circuit-switched voice heritage (MSC/GMSC/MGW for PSTN-bound voice at 64 kbps, or 3–4× less with compression) while bolting on a packet core (SGSN/GGSN) for data, starting with 2G's GPRS at tens of kbps and now running multiple-Mbps data. The SGSN serves a mobile's location/routing for data within its serving area; the GGSN anchors the mobile's IP address (PDP context) and is the gateway to the Internet, much like a foreign/home agent in Mobile IP. This split is the cellular industry mid-transition from circuits to packets — and is exactly what 4G LTE retires by going all-IP.

### Handover: hard, soft, and the pilot set

When a UE moves out of one Node B's range and into another's, the data flow must be re-routed — this is **handover** (or handoff). Either the UE or the Node B may request it when signal quality drops below a threshold. CDMA's reuse-everywhere design enables a trick the FDMA/TDMA generations could not do safely: **soft handover**, where the UE connects to the *new* Node B before disconnecting from the old one, so for a brief window it talks to two base stations at once and the RNC combines the two frames (make-before-break). A **hard handover** is break-before-make — disconnect, then connect — which can clip the call.

The decision uses the **pilot set** the UE measures continuously:

| Set | Meaning | Handover role |
|---|---|---|
| Active set | Pilots currently in soft handover; the UE is demodulating each | Candidate for frame combining at the RNC |
| Candidate set | Strong pilots not yet active but flagged for addition | Above an add threshold → promote to active (soft handover) |
| Neighbor set | Pilots the network tells the UE to watch | Source of candidates |
| Remaining set | Everything else on the carrier | Future neighbors |

A soft handover triggers when a neighbor pilot's *Ec/I₀* (chip energy per interference density) rises above the **add threshold** for a dwell time ΔT. It drops when a pilot in the active set falls below the **drop threshold** for a longer ΔT_drop — the hysteresis prevents ping-pong between cells. `code/main.py` runs this state machine over a moving UE's pilot strength trace and prints which cells enter/leave the active set and whether each handover is soft or hard.

### Locating the mobile and the SIM security chain

To route an *incoming* voice call to a moving UE, the network consults the **HSS** (Home Subscriber Server) in the core, which knows each subscriber's current location area and serves authentication/authorization — the cellular analog of Mobile IP's home agent binding cache.

Security rests on the **SIM** (Subscriber Identity Module), a removable chip carrying the subscriber's permanent secret key *K* and identity (IMSI). UMTS closes two holes GSM left open:

- **Mutual authentication (AKA).** GSM only authenticated the *subscriber to the network*; a rogue base station could impersonate the operator. UMTS AKA (Authentication and Key Agreement) sends a random challenge RAND; the SIM computes RES = f2(K, RAND), and the network expects a *guaranteed* MAC = f1(K, ...) over the challenge that the SIM verifies — so the SIM also proves the network is legit. A mismatch rejects the network.
- **Air encryption and integrity.** AKA derives cipher key CK = f3(K, RAND) and integrity key IK = f4(K, RAND). Confidentiality uses the **f8** algorithm (Kasumi-based stream cipher) over the user data; integrity uses **f9** (a MAC over the signaling). GSM's A5/1 was a weak stream cipher vulnerable to known-plaintext attacks; UMTS's f8/f9 with a longer key and message integrity closes the tampering gap that GSM could not.

The IMSI is normally sent rarely — a temporary **TMSI** masks it on the air to defeat location tracking. The cipher (Kasumi, the successor to GSM's COMP128/A3/A8 family) is not a panacea — research attacks have reduced Kasumi's effective margin — but for the design intent it preserved billing integrity and the audio quality that phone companies care about. `code/main.py` simulates the AKA challenge/response sequence end-to-end (with a toy HMAC standing in for the f1–f5 functions) so you can read the exact field flow.

## Build It

1. Open `code/main.py`. It is stdlib-only — run with `python3 code/main.py`. The script is organized into five demos that each print a numbered block.
2. **Cellular reuse demo** (`cellular_reuse`): edit the cluster size `K` and cell radius `R` and read off the reuse distance `D = R·√(3K)` and the per-cell band share. Confirm the SIR trade when you double K from 7 to 14.
3. **CDMA SIR/pole-capacity demo** (`cdma_sir`): set the Eb/I₀ target and the processing gain Gp; the function prints the SIR curve and the pole capacity `N = 1 + Gp/(Eb/I0)`. Try Eb/I₀ = 7 dB and Gp = 314 — you should see ~64 users.
4. **OVSF spread-and-correlate demo** (`ovsf_demo`): it spreads a 4-bit message under an SF=8 OVSF code, correlates, recovers the bits, and shows a *different* OVSF code contributes 0 to the correlator. Flip a chip and watch the despreading fail.
5. **Handover state machine demo** (`handover_demo`): feed a pilot-strength trace for three Node Bs and watch the active set grow (soft handover) and shrink. Change the add/drop thresholds to toggle between soft and hard decisions.
6. **AKA demo** (`aka_demo`): runs the UMTS challenge-response, prints RAND/RES/MAC/CK/IK, and verifies the mutual-authentication check. Swap in a wrong network MAC to see the SIM reject the network.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Justify the cellular reuse plan | Reuse distance D = R·√(3K) computed; SIR quoted for K=7 vs K=14 | The cluster size is the knob that buys quiet co-channel at the cost of per-cell capacity |
| Confirm CDMA pole capacity | SIR = 1/(N−1), Eb/I₀ = Gp/(N−1), N ≈ 64 for voice | Higher Gp (lower-rate service) admits more users; near-far forces tight power control |
| Verify OVSF orthogonality | Cross-correlation of two different OVSF codes sums to 0 over a bit period | Users are separated by code, not frequency, so all cells reuse all frequencies |
| Trace a soft handover | Pilot crosses add threshold → active set grows to 2 → RNC combines frames → later drops below drop threshold → leaves | Make-before-break; the call never loses service during the transition |
| Route a call to the right core half | Voice → Iu-CS → MSC/GMSC/MGW → PSTN; data → Iu-PS → SGSN/GGSN → Internet | The interface name (Iu-CS vs Iu-PS) is the giveaway for which core half carries it |
| Confirm UMTS mutual auth | AKA: network sends RAND, SIM returns RES, network also returns MAC the SIM verifies | The SIM rejects a forged network; both sides prove knowledge of K |

## Ship It

Produce one artifact under `outputs/` named `prompt-umts-cdma-cellular-3g.md`: an annotated UMTS capacity-and-handover report built from the printed output of `code/main.py`. It must contain:

- A reuse-distance table for K ∈ {4, 7, 12, 14} with the resulting per-cell band share and the co-channel SIR rank.
- The CDMA pole-capacity calculation for two services (12.2 kbps voice AMR at Eb/I₀=7 dB; 384 kbps data at Eb/I₀=3 dB), showing how the lower-rate service admits more users.
- The OVSF spread/correlate trace for a chosen 4-bit message, including the proof that a second user's code contributes zero.
- A handover timeline from the pilot trace, marking each add/drop as soft or hard and the dwell times used.
- The AKA transcript (RAND, RES, MAC, derived CK/IK) with the mutual-authentication verdict.

Start from `code/main.py`'s printed output and annotate it with the failure mode you induced (wrong power, wrong code, forged network MAC).

## Exercises

1. A city has a 20 MHz spectrum allocation. Compare an FDMA 1G system with a 7-cell reuse cluster versus a WCDMA UMTS system reusing the same 5 MHz carrier in every cell. Estimate the number of simultaneous 12.2 kbps voice users each supports, and explain the gap in one sentence.
2. A UE is 30 m from Node B₁ and 3 km from Node B₂. If both uplink transmissions use the same power, by how many dB does the far user's signal arrive below the near user's? What Eb/I₀ target becomes unreachable, and why does the 1500 Hz power-control loop have to close to within ~1 dB?
3. Spread the bit sequence `01` with the SF=8 OVSF code C₈,₂ = [+1 +1 −1 −1 +1 +1 −1 −1], then despread. Now repeat with a single chip flipped at index 3. Compute the correlator output for each bit and state the decision the receiver would make — and whether bit 0 and bit 1 are affected symmetrically.
4. A UE measures pilot Ec/I₀ from three Node Bs over six samples: B1 = {−9, −10, −11, −9, −8, −7} dB, B2 = {−18, −16, −13, −10, −9, −8} dB (add threshold −12 dB, drop threshold −14 dB, dwell ΔT = 3 samples). Trace the active-set transitions and classify each handover as soft or hard.
5. An incoming voice call arrives for a roaming UE. Walk through HSS lookup → MSC routing → Iu-CS → handover if the UE crosses a cell boundary mid-call. Now do the same for a data session: which nodes, which interface (Iu-PS), and what anchor plays the role of Mobile IP's home agent?
6. A rogue base station tries to impersonate the operator to a UMTS SIM. Describe exactly which AKA field the SIM checks, which f-function computes it, and why the GSM-only design (network-not-authenticated) would have let the attack succeed. Then state one residual weakness of Kasumi/f8 that a modern attacker would target instead.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| UMTS / WCDMA | "3G" | Universal Mobile Telecommunications System; WCDMA is its wideband-CDMA air interface (5 MHz, 3.84 Mcps), not a different network |
| Cellular design | "lots of cell towers" | Tiling the area with reuse cells so the same spectrum is reused many times; the cell radius and cluster size trade capacity vs co-channel SIR |
| Frequency reuse | "reusing the band" | Reusing the same channel group in cells separated by D = R·√(3K); narrower in 1G (K=7), universal in 3G CDMA |
| Node B | "the base station" | The UMTS base station implementing the air interface; the temporary label became its permanent name |
| RNC | "the controller" | Radio Network Controller — owns spectrum usage, power control, soft-handover frame combining, and multiplexing onto Iu |
| Processing gain | "CDMA's trick" | Gp = chip rate / bit rate (≈25 dB for 12.2 kbps voice); how far despreading lifts the wanted signal above same-cell interference |
| Near-far problem | "the close phone is too loud" | A nearby transmitter swamps a distant one unless power is controlled so all arrive at the Node B at equal S; drives the 1500 Hz closed loop |
| Pole capacity | "max users" | N ≤ 1 + Gp/(Eb/I₀ target); the theoretical load at which the uplink SIR collapses, independent of frequency planning |
| OVSF | "the code tree" | Orthogonal Variable Spreading Factor codes; siblings on different branches are mutually orthogonal, which is what lets users share one frequency |
| Soft handover | "make before break" | UE connects to the new Node B before dropping the old; RNC combines the two frames; CDMA-only, impossible in FDMA/TDMA |
| Iu-CS / Iu-PS | "the RAN-to-core links" | Iu-CS (circuit) routes voice to MSC/GMSC/MGW→PSTN; Iu-PS (packet) routes data to SGSN/GGSN→Internet — the split core |
| MSC / GMSC / MGW | "the circuit core" | Mobile Switching Center, Gateway MSC (PSTN entry point), Media Gateway (media conversion) — the legacy circuit-switched half |
| SGSN / GGSN | "the packet core" | Serving and Gateway GPRS Support Nodes; GGSN anchors the mobile's IP (PDP context) and faces the Internet like Mobile IP's home agent |
| HSS | "where is the mobile" | Home Subscriber Server — knows each subscriber's location area and the keys for authentication/authorization; routes incoming calls to the right MSC/SGSN |
| SIM / AKA | "the chip that logs you in" | SIM holds K and IMSI; UMTS AKA challenges the SIM with RAND and a MAC the SIM verifies back — *mutual* auth, the fix over GSM's one-way check |
| f8 / f9 | "the UMTS ciphers" | f8 = Kasumi-based confidentiality over user data; f9 = integrity MAC over signaling — both derived from keys AKA produces (CK, IK) |
| Hard handover | "break before make" | Disconnect old Node B before connecting new; the FDMA/TDMA generations' only option; can clip the call |

## Further Reading

- **3GPP TS 25.201** — Physical layer general description (WCDMA FDD, 3.84 Mcps, 5 MHz carrier).
- **3GPP TS 25.212** — Multiplexing and channel coding (OVSF spreading, processing gain, transport-format combinations).
- **3GPP TS 25.301** — Radio interface protocol architecture (Uu: physical, MAC, RLC layers).
- **3GPP TS 25.331** — RRC protocol (active/candidate/neighbor/remaining pilot sets, handover thresholds).
- **3GPP TS 33.102** — 3G security architecture: AKA, f1–f5, Kasumi-based f8/f9, MUTUAL-Authenticate.
- **3GPP TS 23.060** — GPRS / UMTS packet core: SGSN, GGSN, PDP context, Iu-PS.
- **3GPP TS 23.009** — Handover procedures (soft, hard, softer, inter-RNC relocation).
- **ITU-T E.212 / IMT-2000** — The ITU definition of 3G (≥2 Mbps stationary, 384 kbps vehicular) that UMTS satisfies.
- Viterbi, *CDMA: Principles of Spread Spectrum Communication*, Addison-Wesley, 1995 — the capacity and power-control math.
- Holma & Toskala, *WCDMA for UMTS*, 5th ed., Wiley, 2010 — the canonical air-interface reference.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Section 1.5.2 — the source chapter for this lesson.