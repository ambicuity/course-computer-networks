# Cable Modems to Modulation and Multiplexing Review Lab

> A DOCSIS cable plant is a single shared coaxial medium where one CMTS (Cable Modem Termination System) talks to hundreds of modems, and it leans on every multiplexing technique in the physical-layer toolbox at once. **FDM** carves the spectrum into 6-MHz (US) or 8-MHz (EuroDOCSIS) channels; **QAM** packs bits into each channel (QAM-64 ≈ 36 Mbps raw / 27 Mbps net, QAM-256 ≈ 39 Mbps net downstream); **TDM/STDM** divides upstream time into *minislots* (~8-byte payload) so modems do not collide; and **CDMA** or **slotted ALOHA with binary exponential backoff** resolves contention on the shared request minislot. Because the "starting gun" for a minislot round is not heard simultaneously at every modem, each modem runs a *ranging* exchange to learn its round-trip distance and pre-advance its transmit timing so bursts land in their assigned slots at the headend. Downstream is one-sender STDM with a fixed 204-byte MPEG-2-framed cell (184-byte payload after Reed-Solomon FEC). This lab makes those numbers concrete: you compute channel throughput from constellation size and symbol rate, lay out minislots, simulate ranging offsets, and watch backoff resolve collisions — turning Section 2.8.4–2.8.5 from prose into a runnable model and a reusable link-budget calculator.

**Type:** Build
**Languages:** Python (stdlib), signal diagrams, shell
**Prerequisites:** Lessons 09–11 (QAM/constellations, FDM/TDM, OFDM); basic logarithms and modular arithmetic
**Time:** ~75 minutes

## Learning Objectives

- Compute the raw and net bit rate of a downstream channel from constellation order, symbol rate, and FEC overhead (e.g., 6 MHz × QAM-64 → ~36 Mbps raw).
- Explain why upstream uses a more conservative constellation (QPSK…QAM-128) than downstream, in terms of funneled noise and SNR.
- Lay out an upstream minislot schedule and show why **ranging** is required before a modem may transmit.
- Trace the request/grant cycle (request minislot → CMTS MAP/grant on downstream → data burst) and identify where collisions occur.
- Simulate slotted-ALOHA contention with binary exponential backoff and measure how backoff stabilizes a shared request channel.
- Map each DOCSIS mechanism to exactly one multiplexing primitive: FDM (channels), QAM (modulation), TDM/STDM (minislots), CDMA/ALOHA (contention).

## The Problem

A subscriber on a busy cable segment complains: "Downloads are fine — 200 Mbps — but uploads stall and my VoIP call drops every few minutes during the evening." A field engineer cannot see anything wrong with the downstream QAM lock. The real story is upstream: dozens of modems share a single noisy upstream channel, contend for the same request minislots, and during the 7–10 PM peak the request channel saturates. Collisions force exponential backoff; backed-off modems wait longer and longer; latency-sensitive VoIP misses its grant window.

To diagnose this you must reason quantitatively about the physical layer: how many bits per symbol the upstream can carry, how minislots are scheduled, why a modem that has not completed ranging is invisible to the scheduler, and how backoff behaves as offered load climbs. None of that is visible at the application layer — it lives in the modulation, the FDM channel plan, and the TDM minislot map. This lab builds the model so the numbers are at your fingertips.

## The Concept

Source material: [`chapters/chapter-02-the-physical-layer.md`](../../../../chapters/chapter-02-the-physical-layer.md), Sections **2.8.4 (Cable Modems)** and **2.8.5 (downstream/upstream allocation)**, built on the modulation and multiplexing foundations in **2.5**.

A DOCSIS plant is a **Hybrid Fiber Coax (HFC)** tree: fiber from the CMTS (formerly "headend") to a fiber node, then coax to up to ~100 homes per node. It is a shared bus, so the entire problem is *how many modems share one wire without colliding* — and the answer is a stack of multiplexing techniques layered together. The SVG ([`assets/cable-modems-to-modulation-and-multiplexing-review-lab.svg`](../assets/cable-modems-to-modulation-and-multiplexing-review-lab.svg)) shows the channel plan, the constellation ladder, and the upstream minislot timeline together.

### FDM: the channel plan

The coax spectrum is sliced by **Frequency Division Multiplexing**. Each TV-style channel is **6 MHz wide in North America** (88–108 MHz and up) or **8 MHz under EuroDOCSIS**, including guard bands. A modem is assigned *one upstream and one downstream channel* (or several bonded channels under DOCSIS 3.0). This is pure FDM: channels coexist in frequency and never interfere if guard bands hold. When a modem powers up it **scans the downstream channels** looking for a periodic broadcast packet from the CMTS, then the CMTS assigns it upstream/downstream channels — assignments the CMTS may later change for load balancing.

| DOCSIS version | Year | Key change |
|---|---|---|
| 1.0 | 1997 | First open CableLabs standard |
| 2.0 | 2001 | Higher upstream rate for symmetric services (IP telephony) |
| 3.0 | 2006 | Channel **bonding** — multiple channels per modem, both directions |

### QAM: bits per symbol

Within a channel, **Quadrature Amplitude Modulation** maps groups of bits to constellation points. The number of bits per symbol is `log2(M)` where `M` is the constellation order. The CMTS constantly monitors line quality and **adapts the constellation to the SNR**:

| Constellation | Bits/symbol | Use |
|---|---|---|
| QPSK (QAM-4) | 2 | Noisy upstream |
| QAM-16 | 4 | Moderate SNR |
| QAM-64 | 6 | Good downstream (default) |
| QAM-128 | 7 | Upstream ceiling (with TCM) |
| QAM-256 | 8 | Excellent downstream |

Worked example — downstream raw rate:

```
rate = symbol_rate × bits_per_symbol
     = 6e6 sym/s* × 6 bits  ≈ 36 Mbps   (QAM-64)
     = 6e6 sym/s* × 8 bits  ≈ 48 Mbps   (QAM-256, before FEC trims it to ~39 Mbps net)
```

*The 6-MHz channel supports roughly 6 Msym/s after pulse-shaping roll-off; `code/main.py` uses the textbook figures (QAM-64 ≈ 36 Mbps raw, ~27 Mbps net; QAM-256 ≈ 39 Mbps net). Net rate subtracts MPEG-2 framing and Reed-Solomon FEC overhead.

**Upstream is asymmetric on purpose.** The plant was built for one-way TV; upstream RF noise from every home is *funneled* toward the CMTS, lowering SNR. So upstream stays conservative — **QPSK to QAM-128**, with some symbols spent on **Trellis Coded Modulation (TCM)** for error protection. Fewer bits/symbol upstream means the up/down asymmetry is even larger than the channel plan suggests.

### TDM / STDM: minislots

Multiple modems share one upstream channel, so time is divided by **TDM** into **minislots**. Minislot length is network-dependent; **a typical payload is 8 bytes**. An upstream burst must fit in one or more *consecutive* minislots as received at the CMTS. The CMTS periodically announces the start of a new minislot round (the DOCSIS MAP message), and the scheduler grants specific minislots to specific modems.

Downstream is different: **one sender (the CMTS)**, so no contention and no minislots — it is **statistical TDM (STDM)** with a **fixed 204-byte cell** (184-byte payload after Reed-Solomon FEC and overhead), chosen to match **MPEG-2** so TV and data frame identically.

### Ranging: why timing is hard on a shared bus

The "starting gun" announcing a minislot round is **not heard at all modems simultaneously** — propagation delay down the coax differs per modem. So each modem runs **ranging**: it sends a special packet and measures the round-trip time to learn its distance from the CMTS. Knowing that distance, the modem computes *how long ago* the first minislot really started and **pre-advances its transmit timing** so its burst lands in the correct slot at the CMTS. A modem that has not completed ranging cannot be scheduled — it is effectively invisible. This is the same principle as PON ranging and GPS-style time-of-flight.

### Contention: request minislots, CDMA or ALOHA

During init the CMTS assigns each modem a minislot to use for **bandwidth requests**. To send a packet the modem requests the needed minislots; the CMTS grants them via a downstream acknowledgement; the modem then sends starting in the granted minislot. But **request minislots are shared**, so requests collide. Two resolutions:

1. **CDMA** — code-division multiplexing lets several modems transmit in the same minislot at a reduced rate; their orthogonal codes separate at the CMTS. No collision.
2. **No CDMA** — a collision means no acknowledgement. The modem waits a **random time and retries, doubling the random window after each failure**. This is exactly **slotted ALOHA with binary exponential backoff**. Ethernet's carrier sense cannot be used here because modems cannot hear each other on the bus.

`code/main.py` simulates option 2 and shows how backoff keeps the request channel stable as offered load rises, and how it collapses past a load threshold — exactly the evening-VoIP failure from The Problem.

### Putting it together — the request/grant cycle

```
modem: power up → scan downstream → find CMTS broadcast → get channel assignment
modem: RANGING (measure RTT, set timing advance)
modem: contend on request minislot ──► (collision? backoff & retry)
CMTS:  grant N minislots on downstream MAP ──►
modem: send data burst in granted consecutive minislots
```

## Build It

Steps tied to `code/main.py`:

1. **Channel rate.** Call `channel_bitrate(bandwidth_hz, constellation, fec_efficiency)` for 6-MHz QAM-64 and QAM-256; confirm ~36 Mbps raw and ~27/39 Mbps net.
2. **Constellation ladder.** Print bits/symbol for QPSK → QAM-256 and verify each is `log2(M)`.
3. **Minislot layout.** Use `MinislotSchedule` to lay out a round of minislots and assign bursts; observe how an 8-byte payload maps to one or more consecutive slots.
4. **Ranging.** Feed per-modem cable distances into `ranging_offset()` and watch each modem's timing advance differ; show that without it, bursts overlap at the CMTS.
5. **Contention.** Run `simulate_slotted_aloha()` across rising offered loads; record throughput and collision rate; find the load where backoff stops keeping up.
6. Run the whole demo: `python3 code/main.py`.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Compute downstream throughput | `channel_bitrate()` output for QAM-64/256 | Raw ≈ 36/48 Mbps; net ≈ 27/39 Mbps; matches textbook |
| Justify upstream asymmetry | Upstream constellation = QPSK..QAM-128 vs QAM-256 down | You cite funneled noise + lower SNR, not "ISPs are stingy" |
| Verify ranging is needed | Two modems at different distances, offsets printed | Bursts only align at CMTS *after* timing advance |
| Explain evening upload stalls | Slotted-ALOHA throughput vs offered load curve | You point to backoff collapse past the load threshold |
| Map mechanism → primitive | Each of FDM/QAM/TDM/CDMA labeled | No mechanism is left as "magic" |

## Ship It

Produce one artifact under `outputs/`:

- A **DOCSIS link-budget / minislot calculator** (extend `code/main.py`) that, given channel width, constellation, and modem count, prints per-modem upstream/downstream rates and a minislot map.
- Or a one-page **runbook** mapping the evening-VoIP symptom to upstream contention, with the slotted-ALOHA throughput curve as evidence.

Start from the printed output of `code/main.py` and the SVG channel-plan diagram.

## Exercises

1. A 6-MHz downstream channel runs QAM-256 but the SNR drops and the CMTS falls back to QAM-64. By how many Mbps (net) does the subscriber's share drop? Show the arithmetic.
2. EuroDOCSIS uses 8-MHz channels. The textbook says European values are "1/3 larger." Confirm that 8/6 ≈ 1.33 and compute the EuroDOCSIS net rate for QAM-64.
3. Two modems sit 2 km and 14 km of coax from the CMTS (≈5 µs/km one-way). Compute each modem's required timing advance and explain what collides at the CMTS if the closer modem skips ranging.
4. In `simulate_slotted_aloha()`, raise the modem count until throughput peaks then falls. Report the peak offered load (modems × request rate) and relate it to the classic slotted-ALOHA maximum of ~0.368.
5. A 1500-byte IP packet must go upstream where each minislot carries an 8-byte payload. How many consecutive minislots does the burst need (ignore framing overhead, then add 10% for it)?
6. Argue why DOCSIS chose CDMA *or* exponential-backoff ALOHA for the request channel instead of CSMA/CD as in classic Ethernet. What physical-layer fact rules out carrier sense here?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| CMTS | "the headend" | Cable Modem Termination System — the single downstream sender and upstream scheduler; the modern intelligent replacement for the dumb amplifier headend |
| Minislot | "a time slot" | The smallest TDM allocation unit upstream; network-dependent length, typical 8-byte payload; bursts span consecutive minislots |
| Ranging | "ping the headend" | RTT measurement so a modem can pre-advance transmit timing; without it the modem is unschedulable |
| QAM-64 / QAM-256 | "the modulation" | Constellations of 64/256 points → 6/8 bits per symbol; chosen adaptively from SNR |
| FDM channel | "a frequency" | A 6-MHz (US) / 8-MHz (Euro) guard-banded slice; the FDM layer of DOCSIS |
| Channel bonding | "DOCSIS 3.0 speed" | Assigning several FDM channels to one modem to multiply throughput |
| Binary exponential backoff | "retry later" | Double the random wait window after each request collision (slotted ALOHA) |
| STDM | "downstream" | Statistical TDM — one sender, 204-byte fixed cells, no minislots |
| HFC | "the cable" | Hybrid Fiber Coax: fiber to a node, coax to homes; a shared bus |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Ch. 2 §2.8.4–2.8.5 (cable modems) and §2.5 (modulation & multiplexing).
- **DOCSIS 3.0/3.1 specifications**, CableLabs (MULPI — MAC and Upper Layer Protocols Interface; PHY).
- **ITU-T J.83** Annex A/B/C — framing and Reed-Solomon FEC for digital cable (the 204-byte MPEG-2 cell).
- **ITU-T G.984** (GPON) for the analogous PON ranging/grant design.
- **RFC 3046** (DHCP Relay Agent Information Option) — used in DOCSIS provisioning to identify the modem.
- **IEEE 802.3** for the carrier-sense contrast (why CSMA/CD does not apply to the cable bus).
