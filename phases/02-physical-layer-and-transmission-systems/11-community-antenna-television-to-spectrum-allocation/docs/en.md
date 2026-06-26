# Community Antenna Television to Spectrum Allocation

> Cable TV started in the late 1940s as **CATV** (Community Antenna Television): a hilltop antenna, a **headend** amplifier, and one-way coaxial cable feeding a town. To carry Internet, operators rebuilt the plant into **HFC** (Hybrid Fiber Coax) — fiber trunks terminating at **fiber nodes** that feed coax serving 500–2000 homes per segment. The hard constraint is that coax is a *shared broadcast medium*: one heavy downloader steals bandwidth from neighbors, unlike a telephone local loop. The fix is **frequency division multiplexing (FDM)** layered over the existing TV plan. In North America, TV occupies 54–550 MHz in 6-MHz channels (FM radio at 88–108 MHz), upstream data lives in the noisy **5–42 MHz** band, and downstream data sits above 550 MHz (up to 750 MHz+). Downstream channels carry **QAM-64 (~36 Mbps raw, ~27 Mbps net)** or **QAM-256 (~39 Mbps net)** in fixed **204-byte MPEG-2-aligned frames** (184-byte payload + Reed-Solomon FEC). Upstream is contention-based: time is sliced into **minislots**, modems learn their cable distance via **ranging**, and collisions are resolved with **slotted ALOHA + binary exponential backoff** — because modems cannot carrier-sense each other on the cable. **DOCSIS** (1.0/1997, 2.0/2001, 3.0/2006; EuroDOCSIS in Europe) standardized the modem.

**Type:** Learn
**Languages:** Python (stdlib), signal diagrams
**Prerequisites:** Phase 02 lessons on coaxial cable, bandwidth/Nyquist, FDM/TDM, and modulation (QAM/QPSK)
**Time:** ~70 minutes

## Learning Objectives

- Lay out the North American cable spectrum from memory: upstream 5–42 MHz, FM 88–108 MHz, TV 54–550 MHz in 6-MHz channels, downstream data above 550 MHz.
- Compute downstream throughput from channel width and QAM order, and explain why upstream is far slower (noise funneling + QPSK/QAM-16 + FEC overhead).
- Trace the cable-modem registration sequence: scan downstream, find sync packet, announce upstream, get channel assignment, perform ranging.
- Explain why upstream uses slotted ALOHA with binary exponential backoff instead of CSMA/CD, tying it to the "stations cannot sense the medium" property.
- Distinguish the three sharing mechanisms a cable modem uses at once: FDM (channels), TDM (minislots), and CDMA (code sharing within a contended minislot).

## The Problem

A subscriber on a 1,200-home HFC segment complains every weeknight from 8 to 11 PM: pages stall, video buffers, speed tests show 4 Mbps instead of the 38 Mbps they pay for. At 2 PM the same line tests at 38 Mbps. Nothing is "broken" — no link is down, the modem stays registered, downstream SNR is fine.

This is the defining property of cable: **the coax past the fiber node is a shared broadcast bus.** Unlike a DSL local loop, which is private all the way to the central office, every home on a coax segment competes for the same downstream channels and upstream minislots. When 300 of your 1,200 neighbors stream at once, the headend's statistical TDM downstream is oversubscribed and your share collapses. Diagnosing this means reasoning about *which frequencies carry your data*, *how many homes share the segment*, and *how upstream contention is resolved* — exactly what spectrum allocation, ranging, and minislot scheduling are for.

## The Concept

### From CATV to HFC

The original CATV system was simple and **one-way**: antenna → headend amplifier → coax → taps → drop cables → houses, with amplifiers added as runs got long, all pushing signal *downstream only*. To carry Internet, every one-way amplifier had to become a **two-way amplifier**, and long coax runs were broken up and re-homed onto **fiber nodes** — electro-optical converters where high-bandwidth fiber from the headend meets the coax neighborhood. Because fiber bandwidth dwarfs coax, one node feeds several coax segments. The headend was upgraded from a "dumb amplifier" into a **CMTS (Cable Modem Termination System)** with a fiber uplink to an ISP. The SVG in `assets/` shows this topology and the spectrum plan together.

### The spectrum plan (FDM)

TV and Internet must coexist on one cable because cities regulate channel lineups — operators legally cannot just drop TV. The answer is FDM over the legacy TV plan:

| Band | Frequency (NA) | Direction | Use |
|---|---|---|---|
| Upstream data | 5–42 MHz | Modem → headend | Contention, noisy, QPSK–QAM-128 |
| (gap) | 42–54 MHz | — | Guard / transition |
| FM radio | 88–108 MHz | Downstream | Broadcast FM (inside TV band) |
| TV channels | 54–550 MHz | Downstream | 6-MHz channels, analog or digital TV |
| Downstream data | 550–750+ MHz | Headend → modem | QAM-64 / QAM-256 |

The asymmetry is structural: only **37 MHz** (5–42) sits *below* the TV band for upstream, while *hundreds* of MHz sit above 550 MHz for downstream. Two-way amplifiers can be built to amplify 5–42 MHz one way and 54 MHz-and-up the other, so the split is cheap to implement. Most users want more downstream anyway. In Europe the low end is ~65 MHz and channels are 6–8 MHz wide for PAL/SECAM.

### Downstream: throughput from QAM order

Each 6-MHz downstream data channel is modulated with **QAM-64** (6 bits/symbol) or, on clean plant, **QAM-256** (8 bits/symbol). The worked numbers from the standard:

- 6 MHz × QAM-64 → **~36 Mbps raw**, **~27 Mbps net** after overhead.
- 6 MHz × QAM-256 → **~39 Mbps net**; European 8-MHz channels are ~1/3 larger.

Downstream framing reuses the **MPEG-2 transport** so TV and data look identical on the wire: a **fixed 204-byte frame** with a **184-byte payload** and the rest carrying **Reed-Solomon FEC** plus overhead. There is exactly one downstream sender — the headend — so there is no contention, just **statistical TDM** across all modems on the channel. `code/main.py` derives these rates from `(channel_width, bits_per_symbol, fec_overhead)`.

### Upstream: minislots, ranging, and contention

Upstream is the hard direction. RF noise from every home funnels back to the headend (the "noise funnel"), and there are *many* senders, so the system uses conservative modulation (QPSK up to QAM-128, with Trellis Coded Modulation stealing symbols for error protection) plus a contention protocol.

Each upstream channel is divided into **minislots** (typical payload ~8 bytes). Because the cable is long, the headend's "go" signal reaches near and far modems at different times, so each modem must know its propagation delay. It learns this through **ranging**: it sends a special packet and times the round trip, then computes *how long ago the first minislot actually started* and aligns its transmission to land in the correct minislot window at the headend.

The reservation flow:

1. Computer hands a packet to the modem.
2. Modem requests N minislots via a contention request minislot assigned at init.
3. Headend, if it accepts, puts an **acknowledgement on the downstream** naming the reserved minislots.
4. Modem transmits starting in its allocated minislot; a header field can piggyback further requests.

Multiple modems share the *same* request minislot, so requests collide. Two resolutions exist:

- **CDMA**: subscribers with distinct code sequences transmit in the same minislot at reduced rate — no collision.
- **No CDMA**: a collision means no ACK; the modem waits a random time and retries, **doubling the interval after each failure** — precisely **slotted ALOHA with binary exponential backoff**.

### Why not CSMA/CD?

Ethernet uses CSMA/CD: listen before sending, detect collisions while transmitting. That cannot work upstream on cable because **a modem cannot hear the other modems** — they all transmit *toward* the headend, not toward each other, and directional amplifiers prevent a modem from sensing a peer's upstream signal. No carrier sense means no collision *detection*. Slotted ALOHA sidesteps this: it needs only slot alignment (from ranging) and backoff, not sensing. That is why Ethernet's collision logic does not transplant to HFC.

### Three multiplexing schemes at once

A cable modem uses all three classic sharing techniques at once:

| Technique | What it divides | Where |
|---|---|---|
| **FDM** | The cable's frequency band into 6/8-MHz channels | Pick one (or several under DOCSIS 3.0) upstream + downstream channel |
| **TDM** | Each upstream channel into minislots | Different subscribers send in different minislots |
| **CDMA** | A contended minislot among subscribers | Code sequences let several modems share one minislot |

DOCSIS 3.0 (2006) adds **channel bonding** — a modem uses multiple 6-MHz channels at once per direction — multiplying throughput without changing the spectrum plan.

## Build It

`code/main.py` is a stdlib-only cable-spectrum toolkit. Build understanding step by step:

1. Run `python3 main.py`. It prints the spectrum map, classifies sample frequencies (5, 38, 100, 200, 600 MHz), computes downstream throughput for QAM-64/256, and simulates upstream slotted-ALOHA contention.
2. Read `classify_frequency()` and confirm 38 MHz is upstream, 100 MHz is FM, 600 MHz is downstream data.
3. Read `downstream_throughput()` and verify QAM-64 gives ~27 Mbps net and QAM-256 the higher rate on a 6-MHz channel.
4. Read `simulate_slotted_aloha()` and watch the backoff window double after each collision.
5. Change `num_modems` from 8 to 40 and watch collisions and retries climb — the 8 PM congestion scenario in miniature.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Locate your data on the spectrum | Modem diagnostic page: downstream/upstream channel frequencies and power | Downstream channels above 550 MHz; upstream channels in 5–42 MHz; you can name each band |
| Explain downstream speed | Channel width, QAM order (64/256), bonded channel count | Measured throughput ≈ per-channel net rate × bonded channels (e.g., 4 × 38 ≈ 150 Mbps) |
| Diagnose evening slowdown | Per-segment subscriber count, time-of-day speed tests, upstream utilization | Slowdown correlates with neighbor activity, not a down link — a shared-medium contention story |
| Spot upstream trouble | Ranging failures, T3/T4 timeouts, rising correctable/uncorrectable codewords | Upstream SNR drop or noise funnel; modem re-ranges or drops |

## Ship It

Produce one artifact under `outputs/`:

- A **spectrum cheat-sheet** (band → frequency → direction → modulation) on one page.
- A **modem-registration runbook**: scan downstream → sync packet → upstream announce → channel assignment → ranging → online, with the failure mode at each step.
- A **throughput calculator** (channel width, QAM order, bonded-channel count → net Mbps) built on `code/main.py`.

Start from the printed output of `code/main.py` and the diagram in `assets/`.

## Exercises

1. A modem reports four bonded downstream channels at QAM-256 (6 MHz each) and three bonded upstream channels at QAM-16. Estimate the gross downstream rate. Why is the realized upstream rate so much lower than a naive bits-per-symbol calculation suggests?
2. Your segment has 1,500 homes on two fiber nodes. The operator splits it into four nodes of ~375 homes each. Explain in spectrum/contention terms why evening speeds improve even though no individual modem's channel changed.
3. A new modem powers up but never comes online. Walk the registration sequence and name the exact step that fails if (a) it never sees the periodic downstream sync packet, and (b) ranging never completes.
4. Two modems are assigned the same request minislot and the operator has disabled CDMA. Trace what happens to their requests across three collision rounds, giving the backoff window growth.
5. Explain why CSMA/CD cannot be used on the upstream cable, referencing the directional amplifiers and the "cannot sense the medium" property. What does ranging provide that carrier sense would have?
6. North American channels are 6 MHz; European are 6–8 MHz and EuroDOCSIS rates are ~1/3 higher. Compute the QAM-256 net downstream rate for an 8-MHz channel and check it against the "1/3 larger" rule of thumb.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| HFC | "fiber Internet from cable" | Fiber trunks to a **fiber node**, coax for the last 500–2000 homes; coax is shared/broadcast |
| Headend / CMTS | "the cable office" | Upgraded from a one-way amplifier to a Cable Modem Termination System with an ISP fiber uplink |
| Spectrum allocation | "the channels" | FDM split: upstream 5–42 MHz, TV 54–550 MHz, downstream data above 550 MHz |
| Minislot | "a time slot" | Small upstream TDM unit (~8-byte payload) a modem must align to via ranging |
| Ranging | "modem setup" | Round-trip timing so the modem knows its cable distance and lands packets in the right minislot |
| Slotted ALOHA + BEB | "random retry" | Upstream contention resolution: no carrier sense, retry after a random delay that doubles each collision |
| QAM-64 / QAM-256 | "the speed" | 6/8 bits per symbol; ~27 vs ~39 Mbps net per 6-MHz downstream channel |
| DOCSIS | "the cable standard" | CableLabs modem spec (1.0/1997, 2.0/2001, 3.0/2006); 3.0 adds bonding |
| Channel bonding | "more speed" | DOCSIS 3.0 uses several channels at once per direction |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, Ch. 2 §2.8 (Cable Television: CATV, Internet over Cable, Spectrum Allocation, Cable Modems, ADSL vs Cable).
- **DOCSIS 3.0/3.1** specifications, CableLabs — the PHY and MULPI (MAC and Upper Layer Protocols Interface) specs.
- **ITU-T J.83** — Digital multi-programme systems for television over cable (Annex B is the North American QAM-64/256 downstream PHY).
- **ITU-T J.222** — the DOCSIS 3.0 family as ratified by the ITU.
- **EN 300 429** (ETSI / EuroDOCSIS) — European downstream framing and 8-MHz channelization.
- ISO/IEC 13818-1 — MPEG-2 transport stream, source of the 188/204-byte framing reused downstream.
