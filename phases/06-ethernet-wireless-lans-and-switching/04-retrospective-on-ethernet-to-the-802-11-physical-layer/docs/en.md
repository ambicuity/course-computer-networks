# Retrospective on Ethernet to The 802.11 Physical Layer

> Ethernet won three decades of LAN dominance not by being fastest but by being simple, cheap, and *evolvable*: hub-and-switch topology, connectionless framing that matches IP, and a constant 64-1518-byte frame size carried from 10 Mbps coax to 100 Gbps fiber while CSMA/CD quietly disappeared in full-duplex links. 802.11 inherited the same 802 framing philosophy (an LLC glue sublayer over a MAC sublayer) but had to reinvent the physical layer five times. 802.11b (1999) uses direct-sequence spread spectrum with an 11-chip Barker sequence at 11 Mchips/s, BPSK for 1 Mbps and QPSK for 2 Mbps, then CCK for 5.5 and 11 Mbps in the 2.4-GHz ISM band. 802.11a (1999) switched to OFDM with 52 subcarriers (48 data + 4 pilot), 4-µs symbols, and a 1/2-3/4 convolutional code yielding 6-54 Mbps in 5 GHz. 802.11g (2003) ported that OFDM to 2.4 GHz for backward compatibility; 802.11n (2009) added 40-MHz channels, frame aggregation, and up to 4 MIMO spatial streams to reach 600 Mbps. This lesson connects those physical-layer choices to the evidence an engineer actually sees: rates, modulation, channel widths, and band crowding.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib)
**Prerequisites:** Phase 6 lessons on classic Ethernet, switched Ethernet, and the 802.11 architecture/MAC
**Time:** ~75 minutes

## Learning Objectives

- Explain *why* Ethernet survived 30+ years in terms of four concrete properties (simple, cheap, IP-friendly, evolvable) and tie each to a design decision (switches, twisted pair, connectionless frames, stable frame format).
- Map each 802.11 PHY (b/a/g/n) to its band, modulation, channel width, and data-rate set, and state which two original PHYs (infrared, frequency hopping) are defunct.
- Compute the chip/symbol arithmetic for 802.11b (Barker + CCK) and the subcarrier/symbol arithmetic for 802.11a/g OFDM that produce the published rates.
- Decide, from observed evidence (band, rate, channel width, spatial streams), which PHY a capture is using and predict the range/interference trade-off.
- Explain rate adaptation and why the standard deliberately leaves the algorithm unspecified.

## The Problem

A user complains that the office Wi-Fi is "slow near the kitchen." Your monitoring shows associated clients negotiating 6 Mbps instead of 54 Mbps, and a competing access point on the same channel. Meanwhile a different complaint says the conference-room AP "won't reach the far corner," even though the data-center Ethernet that backhauls it has run flawlessly for years without a single configuration change.

These two stories are the whole lesson in miniature. The wired side is boring precisely because Ethernet made the right architectural bets: it stayed simple, kept a stable frame format, and let speed grow without forcing a rewrite. The wireless side is fragile because the 802.11 physical layer is a moving target — five generations of modulation, two ISM bands, and a rate that collapses by a factor of 10 when the signal weakens. To diagnose either, reduce the symptom to physical-layer facts: which PHY, which band, which channel width, which modulation, and what range/interference trade-off that combination implies.

## The Concept

### Why Ethernet won: four properties, not raw speed

Ethernet was rarely the fastest LAN of its era. ATM, FDDI, and Fibre Channel were faster when introduced and all lost. The reasons Ethernet survived are architectural:

| Property | Mechanism | Evidence you can see |
|---|---|---|
| Simple → reliable | Hub/switch topology; no software beyond the driver; plug-and-go hosts | Near-zero config tables; switch port "up" with no tuning |
| Simple → cheap | Twisted-pair (Cat 5/6a) wiring; commodity NICs; prices fall as volume rises | Same RJ-45 jacks across 100 Mbps → 10 Gbps |
| IP-friendly | Connectionless framing matches connectionless IP; ATM's connection model did not | One Ethernet frame carries one IP packet, no circuit setup |
| Evolvable | Stable 64-1518-byte frame format; speed rises without changing software; old cabling reused | DIX/802.3 frame header identical from 10BASE-T to 100GBASE |

The deep lesson is **KISS**. FDDI and Fibre Channel were too complicated, which led to complex chips and high prices; Ethernet later borrowed their good ideas (4B/5B line coding from FDDI, 8B/10B from Fibre Channel) and absorbed their speed advantage. By 10-gigabit Ethernet, CSMA/CD was gone entirely — all 10G is full-duplex — yet the frame an application sees is unchanged. That stability is the point: a salesperson who says "throw out your hardware and rewrite your software" loses.

See `assets/retrospective-on-ethernet-to-the-802-11-physical-layer.svg` for the evolution timeline that pairs the wired and wireless tracks.

### The 802.11 protocol stack: same shape as Ethernet

All 802 protocols share structure. The data-link layer splits into an **LLC (Logical Link Control)** sublayer above a **MAC (Medium Access Control)** sublayer. The LLC today is a thin glue layer that names the carried protocol (e.g., IP) inside an 802.11 frame; the MAC decides who transmits next. Below the MAC sits the physical layer — and unlike Ethernet, where the PHY changes but the MAC is essentially constant, 802.11 stacked *five different PHYs* under one MAC:

```text
        Upper layers (IP, …)
   ┌──────────────────────────────┐
   │   LLC  (identifies protocol) │  data-link
   ├──────────────────────────────┤  layer
   │   MAC  (channel allocation)  │
   ├───┬─────┬─────┬─────┬────────┤
PHY│FHSS│DSSS │OFDM │OFDM │ MIMO  │  physical
   │IR  │11b  │11a  │11g  │ 11n   │  layer
   └───┴─────┴─────┴─────┴────────┘
1997-99  1999  1999  2003   2009
```

Two of the three original 1997 PHYs are now defunct: **infrared** (TV-remote style) and **frequency hopping** in 2.4 GHz. The survivor, **direct-sequence spread spectrum (DSSS)** at 1-2 Mbps, was extended to 11 Mbps and became 802.11b.

### 802.11b: spread spectrum, Barker, and CCK

802.11b is a DSSS method in the **2.4-GHz ISM band** supporting **1, 2, 5.5, and 11 Mbps** (in practice almost always 11). It resembles CDMA but with a single shared spreading code. Spreading also satisfies the FCC rule (in force until May 2002) that power be spread across the ISM band.

- The spreading code is an **11-chip Barker sequence** transmitted at **11 Mchips/s**. Its autocorrelation is low except when aligned, which lets a receiver lock onto the start of a transmission.
- **1 Mbps**: Barker + **BPSK**, 1 bit per 11 chips → 11 Mchips/s ÷ 11 chips/bit = 1 Mbps.
- **2 Mbps**: Barker + **QPSK**, 2 bits per 11 chips.
- **5.5 and 11 Mbps**: switch from Barker to **CCK (Complementary Code Keying)** with 8-chip codes — 4 bits per 8-chip code (5.5 Mbps) and 8 bits per 8-chip code (11 Mbps).

`code/main.py` reproduces every one of these rates from first principles (chips, modulation, coding) so you can verify the arithmetic instead of memorizing the table.

### 802.11a/g: OFDM subcarriers and coded symbols

802.11a (5-GHz band) abandoned spread spectrum for **OFDM (Orthogonal Frequency Division Multiplexing)** because OFDM uses spectrum efficiently and resists multipath. The arithmetic:

- **52 subcarriers** per 20-MHz channel: **48 carry data**, **4 are pilots** for synchronization.
- Each OFDM symbol lasts **4 µs** and carries **1, 2, 4, or 6 bits per subcarrier** (BPSK / QPSK / 16-QAM / 64-QAM).
- A binary convolutional code applies a coding rate of **1/2, 2/3, or 3/4**, so only that fraction of bits is non-redundant.
- Combining modulation and code rate yields **eight rates from 6 to 54 Mbps**.

Worked example for 54 Mbps: 48 data subcarriers × 6 bits (64-QAM) = 288 coded bits/symbol; × 3/4 code rate = 216 data bits/symbol; ÷ 4 µs = **54 Mbps**. For 6 Mbps: 48 × 1 bit (BPSK) × 1/2 ÷ 4 µs = 6 Mbps.

**802.11g** (2003) copies 802.11a's OFDM but runs in **2.4 GHz** for compatibility with nearby 802.11b devices, offering the same 6-54 Mbps — which is why a single NIC commonly advertises 802.11a/b/g.

### 802.11n: MIMO, wider channels, aggregation

802.11n (ratified October 2009) targeted ≥100 Mbps of usable throughput — a raw increase of at least 4×. Three levers, all observable:

1. **Doubled channel width** from 20 MHz to 40 MHz (roughly doubles subcarriers).
2. **Frame aggregation** — sending a group of frames together to amortize fixed per-frame overhead.
3. **MIMO (Multiple Input Multiple Output)** — up to **four antennas** sending up to **four spatial streams** simultaneously. The streams interfere at the receiver but are separated mathematically. With four streams and 40-MHz channels, 802.11n defines rates up to **600 Mbps**. MIMO can be spent on speed *or* traded for better range and reliability.

### Bands, power, and the range/interference trade-off

All 802.11 PHYs use unlicensed **2.4-GHz or 5-GHz ISM** bands, capped at ≤1 W radiated power (≈50 mW typical for laptops). The trade-offs are physical:

| Factor | 2.4 GHz | 5 GHz |
|---|---|---|
| Range | Longer (802.11b ≈ 7× the range of 802.11a) | Shorter (higher frequency attenuates faster) |
| Crowding | Heavy — microwaves, cordless phones, garage-door openers, Bluetooth | Cleaner spectrum, more channels |
| PHYs | 11b, 11g, 11n | 11a, 11n |

### Rate adaptation: deliberately unspecified

Because rates span a 10× range (1 → 11 Mbps, or 6 → 54 Mbps), choosing the right rate for current signal quality — **rate adaptation** — is critical. A weak signal forces a low, robust rate; a clean signal allows the top rate. Crucially, the standard does **not** specify the algorithm: rate adaptation is not needed for interoperability, so vendors compete on it. That is why two laptops in the same spot can negotiate different rates. The "slow near the kitchen" symptom is usually rate adaptation responding correctly to a weak or interfered signal — not a bug.

## Build It

1. Run `python3 code/main.py`. It builds the full rate table for 802.11b/a/g/n from the underlying chip/subcarrier/MIMO parameters and prints a band-vs-rate comparison.
2. Read the `b_rate()` function and confirm the 11-Mchips/s ÷ 11-chip Barker math gives 1 Mbps for BPSK and 2 Mbps for QPSK.
3. Read `ofdm_rate()` and reproduce the 54 Mbps worked example (48 subcarriers × 6 bits × 3/4 ÷ 4 µs) by hand, then check it against the program output.
4. Capture or open an 802.11 trace in Wireshark. In the **Radiotap header**, read the channel frequency (2412-2484 MHz → 2.4 GHz; 5xxx MHz → 5 GHz) and the data rate. Use the rate to infer the PHY (1/2/5.5/11 → 11b; 6-54 → 11a/g; MCS index present → 11n).
5. Draw the range/interference trade-off for your own AP: which band, which channel, which neighbors share it.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Identify the PHY from a capture | Radiotap channel frequency + data rate / MCS field | You can say "5 GHz, 54 Mbps → 802.11a/g OFDM" or "MCS 7, 40 MHz → 802.11n" with reasoning |
| Explain a low negotiated rate | Signal strength (dBm), retries, competing APs on the channel | You attribute it to rate adaptation responding to weak/interfered signal, not a fault |
| Justify a 5-GHz move | 2.4-GHz channel utilization, non-Wi-Fi interferers | You name the range cost (shorter reach) against the crowding benefit |
| Verify Ethernet stability claim | Frame format unchanged across speeds; full-duplex (no CSMA/CD) at 10G | You show the same frame header from 10BASE-T to 10GBASE and explain why no rewrite was needed |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **PHY identification cheat-sheet** mapping observed band + rate/MCS → 802.11 generation, with the chip/subcarrier math.
- A **rate-adaptation runbook** for the "slow near the kitchen" symptom.
- The annotated rate table emitted by `code/main.py`, saved as a reference.

Start from `outputs/prompt-retrospective-on-ethernet-to-the-802-11-physical-layer.md` and extend it with your own captures.

## Exercises

1. An 802.11b client reports it is sending at 5.5 Mbps. Using the CCK parameters (8-chip codes, 11 Mchips/s), show how 4 bits per 8-chip code produces 5.5 Mbps, and explain why it is *not* using the Barker sequence at this rate.
2. A capture shows a 5-GHz channel, 4-µs symbols, 16-QAM, and a 1/2 code rate. Compute the data rate from the OFDM formula (48 data subcarriers) and identify the PHY.
3. A site survey finds 802.11b reaches the far conference room but 802.11a does not, despite 802.11a being faster. Explain the physical reason using the ≈7× range relationship and the 5-GHz attenuation property.
4. Your 2.4-GHz AP is on channel 6 alongside a neighbor's AP and a microwave oven. List the specific 802.11b/g symptoms you'd expect and one band-level remedy.
5. An 802.11n AP advertises 600 Mbps but a single client only reaches 150 Mbps. Using the three 802.11n levers (40-MHz channels, aggregation, up to 4 spatial streams), give two concrete reasons the client falls short.
6. Argue why Ethernet's *connectionless* frame, not its speed, is what let it beat ATM for carrying IP, and name one piece of evidence in a frame capture that supports the argument.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| DSSS / Barker sequence | "the old slow Wi-Fi" | 802.11b spreads each bit over an 11-chip Barker code at 11 Mchips/s; low autocorrelation lets the receiver lock onto frame start |
| CCK | "11 Mbps mode" | Complementary Code Keying replaces Barker for 5.5/11 Mbps: 4 or 8 bits per 8-chip code |
| OFDM | "the fast modulation" | 52 subcarriers (48 data + 4 pilot), 4-µs symbols, used by 802.11a/g; resists multipath and uses spectrum efficiently |
| Subcarrier / pilot | "channels within a channel" | Parallel narrowband tones; 48 carry data, 4 are pilots for synchronization |
| MIMO | "multiple antennas" | Up to 4 spatial streams sent at once and separated at the receiver; trade speed for range |
| ISM band | "the Wi-Fi frequencies" | Unlicensed 2.4/5 GHz, ≤1 W; shared with microwaves, cordless phones, Bluetooth |
| Rate adaptation | "auto speed" | Choosing a rate to match signal quality; deliberately unspecified by the standard, so vendors differ |
| CSMA/CD retirement | "Ethernet collision detection" | Full-duplex 10G+ Ethernet dropped CSMA/CD entirely while keeping the frame format |

## Further Reading

- **IEEE 802.11-2007** — the consolidated wireless LAN standard (PHY and MAC).
- **IEEE 802.11a-1999, 802.11b-1999, 802.11g-2003, 802.11n-2009** — the individual PHY amendments referenced throughout this lesson.
- **IEEE 802.3** — Ethernet, including 10-gigabit (10GBASE-SR/LR/ER/T) and the move to full-duplex.
- **IEEE 802.2** — Logical Link Control, the glue sublayer shared by all 802 protocols.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 4 (sections 4.3.8 "Retrospective on Ethernet" and 4.4 "Wireless LANs").
- M. Gast, *802.11 Wireless Networks: The Definitive Guide* (O'Reilly) — practical PHY and MAC detail.
- Halperin et al. (2010) — introduction to multiple-antenna (MIMO) techniques in 802.11.
