# First-Generation (1G) Mobile Phones: Analog Voice to Third-Generation (3G) Mobile Phones: Digital Voice and Data

> Cellular networks win capacity by reusing frequencies across small cells, then by adding ever-smarter multiple-access on the air interface. **1G AMPS** (Bell Labs, deployed 1982, retired 2008) is analog FM voice over **832 full-duplex 30 kHz channels** using FDMA/FDD: 824-849 MHz mobile-to-base, 869-894 MHz base-to-mobile; control packets carry a **32-bit serial number** and **34-bit phone number** digitally even though voice is analog. **2G GSM** keeps FDD but splits each **200 kHz carrier into 8 TDMA time slots**; each **148-bit burst** lasts **577 us** (incl. a 30 us / 8.25-bit guard), the carrier runs at **270.833 kbit/s** gross, and after framing and FEC each user gets **13 kbit/s** of speech. Handoff in AMPS is network-controlled and takes ~300 ms; GSM uses **MAHO** (Mobile-Assisted HandOff). **3G** (ITU IMT-2000) is W-CDMA/UMTS on **5 MHz** channels (3.84 Mchip/s) or CDMA2000 on **1.25 MHz**: every handset transmits over the whole band at once, separated by orthogonal chip codes, with tight power control limiting capacity. This lesson builds the CDMA spreading/despreading math in `code/main.py` and the framing in the SVG.

**Type:** Learn
**Languages:** Python, signal diagrams
**Prerequisites:** Phase 2 lessons on multiplexing (FDM/TDM), modulation, and the electromagnetic spectrum
**Time:** ~75 minutes

## Learning Objectives

- Explain why frequency reuse across a 7-cell cluster multiplies AMPS capacity by 10-15x versus a single high-power transmitter, and estimate the voice channels left per cell.
- Lay out the AMPS air interface: 832 FDD channels, 30 kHz width, the four channel categories (control, paging, access, data), and the 32-bit serial / 34-bit number registration packet.
- Decode the GSM TDMA burst: the 148-bit data frame, two 57-bit Information fields, the 26-bit Sync (training) field, three delimiter bits each side, and the 4.615 ms / 8-slot frame.
- Show how 3G CDMA separates unsynchronized users on one frequency using orthogonal chip sequences, and why near-far power control is mandatory.
- Run `code/main.py` to spread, sum, and despread multiple handsets, and prove that the wrong chip code recovers only noise.

## The Problem

You are on call for a regional carrier during a stadium event. The complaint queue fills with "no service," "call dropped at the gate," and "voice is choppy." The radio team insists the towers are healthy. Where do you look?

The answer depends on the *generation* of the air interface, because each runs out of capacity differently. A 1G/AMPS cell runs out of **frequencies** (~45-56 voice channels, period). A 2G/GSM cell runs out of **time slots** (8 per 200 kHz carrier). A 3G/CDMA cell has no hard channel count — it degrades as **interference** rises, until the noise floor from too many power-controlled handsets makes everyone's signal unrecoverable. You cannot diagnose the choppy-voice symptom without knowing which wall you hit. This lesson gives you the mechanism and numbers to tell them apart.

## The Concept

The source chapter walks the same arc: a region is divided into **cells**, frequencies are **reused** in non-adjacent cells, and a Mobile Switching Center (MSC, also called MTSO) steers calls and handoffs. What changes from 1G to 3G is purely how the air interface is shared. See the SVG (`assets/first-generation-1g-mobile-phones-analog-voice-to-third-generation-3g-.svg`) for the side-by-side of FDMA, TDMA, and CDMA on the same spectrum.

### Frequency reuse and the cellular idea

Before cells, an IMTS transmitter 100 km across allowed exactly **one call per frequency**. AMPS instead uses 10-20 km cells, each assigned a frequency set used by *none* of its neighbors. Group cells into clusters of seven (A-G) and a frequency set returns only after a ~two-cell buffer — enough separation to keep co-channel interference low. With 100 small cells an AMPS system carries 10-15 calls per frequency in widely separated cells, an order-of-magnitude jump. When a cell overloads, operators **split** it into microcells; portable microcells with satellite backhaul are wheeled into concerts and stadiums.

Handoff: a base station notices the signal fading, polls neighbors for received power, and the MSC transfers ownership to the strongest cell, telling the handset to retune. In AMPS this takes about **300 ms** and is entirely network-controlled.

### 1G AMPS air interface (FDMA / FDD)

| Property | Value |
|---|---|
| Multiple access | FDMA with FDD (paired simplex channels) |
| Full-duplex channels | 832 |
| Uplink (mobile to base) | 824-849 MHz |
| Downlink (base to mobile) | 869-894 MHz |
| Channel width | 30 kHz |
| Voice | Analog FM |
| Control info | Digital, repeated, with error-correcting code |

The 832 channels split into four categories: **control** (base to mobile, system management), **paging** (base to mobile, alerting a phone to an incoming call), **access** (bidirectional, call setup and channel assignment), and **data** (bidirectional, the actual voice/fax/data). Because frequencies cannot repeat in nearby cells and 21 channels per cell are reserved for control, the usable voice channels per cell drop to roughly **45**. `amps_voice_channels_per_cell()` in `code/main.py` reproduces this from the reuse cluster and operator split.

**Registration / call setup.** Each phone stores a **32-bit serial number** and a **10-digit number** (3-digit area code in 10 bits + 7-digit subscriber number in 24 bits = 34 bits) in PROM. At power-on it scans 21 preprogrammed control channels for the strongest, then broadcasts its serial and phone number — sent digitally, multiple times, with FEC. The MSC records the visitor and notifies the home MSC; the phone re-registers roughly every **15 minutes**. To dial, the phone sends the target number on the **access channel**; on collision it retries; the MSC finds an idle data channel and returns its number on the control channel.

### 2G GSM air interface (FDD + TDMA)

GSM keeps FDD but adds time division: each **200 kHz carrier** (vs AMPS's 30 kHz) is split into **8 time slots**, so eight calls share one frequency pair. At 900 MHz a GSM system has 124 carrier pairs; uplink and downlink are separated by 55 MHz. A handset never transmits and receives in the same slot — the radio cannot do both and needs time to switch.

The framing hierarchy (see the SVG timing strip):

| Layer | Size | Duration |
|---|---|---|
| Data burst | 148 bits | 577 us (incl. 30 us / 8.25-bit guard) |
| TDM frame | 8 bursts | 4.615 ms |
| 26-frame multiframe | 26 TDM frames | 120 ms |

Each **148-bit burst** is laid out as: `[000] [57-bit Info] [1 stealing bit] [26-bit Sync] [1 stealing bit] [57-bit Info] [000]`. The three `0` bits at each end delimit the frame; the **26-bit Sync (training) field** in the middle lets the receiver lock onto the sender's bit boundaries against multipath; each stealing/control bit flags whether its Information field is voice or signalling. Gross carrier rate is **270,833 bit/s** over 8 users; overhead leaves ~24.7 kbit/s per user, and after channel coding **13 kbit/s** of compressed speech remains — well below the 64 kbit/s PCM of the wired network, but adequate with GSM's speech codec.

In the 26-frame multiframe, **slot 12** is a control frame and **slot 25** is reserved, leaving 24 frames for traffic. A separate **51-frame multiframe** carries the logical control channels: the **broadcast control channel** (continuous base-station identity/status, monitored for cell reselection), the **dedicated control channel** (location update, registration, call setup; feeds each BSC's **VLR** database), and the **common control channel**, itself split into **paging**, **random access** (collisions are retried), and **access grant** subchannels.

**Handoff differs too.** Because a GSM mobile is idle in most slots, it spends that idle time measuring neighbor base stations and reports the measurements to the BSC, which decides when to hand off. This is **MAHO (Mobile-Assisted HandOff)** — contrast AMPS, where the MSC does it alone.

### 3G CDMA: many users, one frequency

3G grew out of ITU's **IMT-2000** blueprint (2 GHz spectrum, target rates of 2 Mbit/s stationary, 384 kbit/s walking, 144 kbit/s in a car). Two systems won: **W-CDMA / UMTS** (Ericsson/EU, **5 MHz** channels, 3.84 Mchip/s) and **CDMA2000** (Qualcomm, **1.25 MHz** channels, built on the 2G IS-95 base). Both are broadband CDMA.

CDMA is neither FDM nor TDM: **every user transmits on the same band at the same time**, and the receiver pulls them apart by code. Each bit is divided into `m` **chips** (typically 64 or 128; the code uses 8 for clarity). A station gets a unique `m`-chip sequence in bipolar (+1/-1) form. To send a **1** it transmits the chip sequence; to send a **0** it transmits the negation. The channel sums all stations' chips. To recover station S, the receiver computes the normalized inner product of the summed signal with S's code: **orthogonal** codes from other users cancel to 0, leaving +1 (bit 1) or -1 (bit 0).

`code/main.py` builds orthogonal **Walsh-Hadamard** codes via the recursion `H(2n) = [[H, H], [H, -H]]`, spreads three handsets, sums them onto one wire, and despreads each. A worked slice from the output:

```
Handset-A: code=(+ - + - + - + -)  bits=[1, 0, 1, 1]
Summed air signal (first 8 chips): (+ - + - - + + -)
Recover Handset-A: [1, 0, 1, 1]  [OK]
Eavesdrop with unassigned code (+ - - + - + + -) -> [0, 0, 0, 0]
```

The eavesdrop line is the point: without the assigned chip code, the despread output is noise, not data.

### The near-far problem and power control

The base-to-mobile direction is **synchronous** — the base transmits all codes time-aligned, so they stay orthogonal. The mobile-to-base direction is **asynchronous**: independent handsets cannot align their chip starts, so UMTS uses long **pseudorandom sequences** with low cross-correlation at *all* offsets, not just when aligned. But correlation stays small only if received powers are similar. If a nearby handset swamps a distant one, a small cross-correlation with the strong signal can drown the weak signal's auto-correlation peak — the classic **near-far problem**. UMTS runs fast closed-loop **power control** (hundreds to ~1500 updates/sec) so every handset arrives at roughly equal power. Interference, not a channel count, caps CDMA capacity — which is why a 3G cell degrades gracefully instead of giving a hard busy signal.

The three capacity walls, one symptom:

| Generation | Shares by | Hard limit | What "full" feels like |
|---|---|---|---|
| 1G AMPS | Frequency (30 kHz) | ~45 voice channels/cell | Fast busy signal; no channel |
| 2G GSM | Time slot (1 of 8) | 8 calls per 200 kHz carrier | Call setup rejected |
| 3G CDMA | Code, full band | Interference / noise floor | Dropped bits, choppy voice, then drop |

## Build It

1. Read `code/main.py`. The 1G/2G section is plain capacity arithmetic; the 3G section is the CDMA engine (`walsh_codes`, `spread`, `air_combine`, `despread`).
2. Run `python3 main.py`. Confirm the generation table, the AMPS per-cell count, and that all three handsets recover cleanly.
3. Trace one bit by hand: pick Handset-B's code and first bit, spread it, and verify the despread inner product divided by `m` gives back the right bit.
4. Break orthogonality on purpose: assign two handsets the *same* Walsh row and re-run. Watch their recovered bits collide — this is what happens when code planning fails.
5. Annotate the SVG: label which spectrum axis is divided in FDMA, TDMA, and CDMA.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Identify the generation from a complaint | Carrier width (30/200 kHz, 5 MHz), busy vs choppy symptom | You name FDMA/TDMA/CDMA and the matching capacity wall |
| Read a GSM burst | 148-bit layout: 3 + 57 + 1 + 26 + 1 + 57 + 3, 577 us slot | You can point to the Sync field and explain training |
| Prove CDMA separation | `despread` output equals input bits; wrong code -> noise | Inner product / m is +1 or -1 for the right code only |
| Explain a 3G "choppy then dropped" call | Rising interference, power-control failure, near-far | You tie it to power control, not a channel count |
| Estimate AMPS cell capacity | Reuse cluster, control reservation, operator split | Result lands near the textbook's ~45 voice channels |

## Ship It

Produce one artifact under `outputs/`:

- A CDMA encode/decode worksheet (chip codes, summed signal, recovered bits) generated from `code/main.py`.
- A one-page GSM burst-format reference card with the 148-bit field map and timing.
- A 1G/2G/3G capacity-wall runbook keyed to the three symptoms in the table above.

Start from the `code/main.py` output and the SVG framing diagram.

## Exercises

1. An AMPS cell shows a fast busy signal during rush hour but the towers are healthy. Using the per-cell voice-channel estimate, explain why splitting the cell into microcells (Fig. 2-45b) fixes it, and what reuse buffer you must preserve.
2. A GSM carrier at 890.4/935.4 MHz, slot 2 is dropping calls. Walk the 148-bit burst and the 4.615 ms frame; identify which fields would corrupt under heavy multipath and how the 26-bit Sync field mitigates it.
3. Modify `walsh_codes` usage in `code/main.py` so two handsets share one code. Run it, capture the colliding output, and explain why CDMA code planning is non-negotiable.
4. A 3G UMTS cell near a stadium gives clear calls to handsets at the gate but choppy calls to handsets at the back of the lot. Explain this as the near-far problem and describe what closed-loop power control does about it.
5. Compare the handoff mechanisms: AMPS network-controlled (~300 ms) vs GSM MAHO. Which idle resource does GSM exploit for measurements, and why can't AMPS do the same?
6. Given a 5 MHz W-CDMA channel at 3.84 Mchip/s and 128 chips/bit, compute the per-user bit rate before coding, and compare it to the 8-user, 270.833 kbit/s GSM carrier.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Frequency reuse | "Towers share channels" | The same frequency set is reused only in non-adjacent cells (≈7-cell cluster) to multiply capacity while bounding co-channel interference |
| FDD | "Two-way radio" | Frequency Division Duplex: separate uplink/downlink bands (AMPS +80 MHz, GSM +55 MHz) so a handset sends and receives at once |
| Handoff / MAHO | "Switching towers" | Transfer of a call to a stronger cell; AMPS does it in the network (~300 ms), GSM uses Mobile-Assisted HandOff from idle-slot measurements |
| TDMA burst | "A GSM packet" | A 148-bit frame in a 577 us slot: 3+57+1+26+1+57+3, including a 26-bit Sync training field |
| Chip sequence | "The CDMA code" | The `m`-chip +/-1 pattern (often a Walsh code) a station sends for a 1 and negates for a 0 |
| Orthogonality | "Codes don't interfere" | Normalized inner product of two distinct codes is 0, so summed transmissions separate by correlation |
| Near-far problem | "Loud phone wins" | A strong nearby signal's cross-correlation can swamp a weak far signal's auto-correlation, requiring fast power control |
| IMT-2000 | "3G" | ITU's 3G blueprint: 2 GHz spectrum, 2 Mbit/s stationary down to 144 kbit/s mobile; realized as W-CDMA/UMTS and CDMA2000 |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., the "Mobile Telephone System" section (1G AMPS, 2G GSM, 3G CDMA) and the CDMA spreading discussion under multiplexing.
- EIA/TIA **IS-54** and **IS-136** — D-AMPS (digital AMPS, TDMA over the 30 kHz carrier).
- TIA/EIA **IS-95** (cdmaOne) — the 2G CDMA system that became the technical basis for CDMA2000.
- **3GPP TS 45.002** — GSM multiplexing and multiple access on the radio path (burst and multiframe structure).
- **3GPP TS 25.213** — UMTS spreading and modulation (W-CDMA, channelization/Walsh codes, scrambling).
- ITU-R **M.1457** — Detailed specifications of the IMT-2000 radio interfaces.
- A. J. Viterbi, *CDMA: Principles of Spread Spectrum Communication* (1995) — the definitive treatment of power control and the near-far problem.
