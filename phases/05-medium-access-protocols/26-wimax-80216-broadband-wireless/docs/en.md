# WiMAX / IEEE 802.16 broadband wireless: architecture, OFDM PHY, and deadline MAC

> IEEE 802.16 — nicknamed **WiMAX** by the WiMAX Forum's interoperability program — is the IEEE's Broadband Wireless Access (BWA) standard for metropolitan-area networks. Fixed WiMAX (802.16d, 2004) reaches fixed homes and offices; mobile WiMAX (802.16e, 2005) adds vehicular handoffs; 802.16m (WiMAX 2, 2011) pushed the line toward IMT-Advanced. The PHY is OFDM with 256 subcarriers and FFT sizes 128/192/256 in fixed WiMAX (a Scalable OFDMA extension in 802.16e uses 512/1024/2048), operating between roughly 2 GHz and 11 GHz for non-line-of-sight and 10-66 GHz for line-of-sight, with channel bandwidths from 1.25 MHz to 20 MHz and TDD or FDD duplexing. Adaptive modulation (BPSK, QPSK, 16-QAM, 64-QAM) plus convolutional coding gives roughly 12.6 Mbps downlink and 6.2 Mbps uplink per 5-MHz channel pair. The MAC is **connection-oriented** (a sharp break from 802.11) with a 16-bit Connection ID, a per-frame DL-MAP / UL-MAP broadcast by the base station telling each subscriber station exactly when to transmit, four QoS service classes (UGS, rtPS, nrtPS, BE), and a contention-based CDMA bandwidth-request channel. Range is 1-3 km in NLOS with OFDM and up to 50 km in LOS at 10-66 GHz. UGS supports constant-bit-rate voice with periodic grants; rtPS uses polling to meet per-frame deadlines — a fundamentally scheduled MAC, not a contention one.

**Type:** Learn
**Languages:** Python
**Prerequisites:** OFDM basics (Phase 2 / Chapter 2), CSMA/CA vs scheduled MACs (Phase 5), QoS concepts (UGS/rtPS/nrtPS/BE)
**Time:** ~80 minutes

## Learning Objectives

- Sketch the 802.16 reference architecture — base station, subscriber/mobile station, ASN/CSN gateway — and the three data-link sublayers (security, MAC common, service-specific convergence).
- Decode the 802.16 generic MAC header (6 bytes: EC, Type, CI, EK, Length, CID, HCS) and contrast it with the 4-byte bandwidth-request header, naming which fields shrink for a request.
- Build a TDD frame with a preamble, FCH, DL-MAP / UL-MAP, downlink bursts, TTG, uplink bursts, and RTG; map OFDM symbol slots to per-SS allocations.
- Choose the right service class — UGS for VoIP, rtPS for MPEG, nrtPS for FTP, BE for web — and explain how each is scheduled (periodic grants, polling, contention).
- Trace an OFDM PHY from the 256-point FFT to adaptive burst profiles (BPSK up to 64-QAM) and explain the link-budget trade-off with distance and SNR.
- Implement a small DL-MAP/UL-MAP builder plus a per-class scheduler that turns bytes-into-time-slots for two subscriber stations.

## The Problem

A small carrier has just won a regional license at 3.5 GHz and a rural town of 8,000 people is asking for broadband. The math is unforgiving. Laying fiber to every farmhouse is $20,000-50,000 per home — at this density it will not earn back. DSL fades below 2 Mb/s once a customer is more than 3 km from the central office, and half the town is past that limit. LTE is on the roadmap but the operator wants to light up a coverage footprint tonight.

The engineering questions all funnel into one: can 802.16 reach 10 km from a tower and still deliver a tolerable service? And once it can, how does its MAC discipline actually carry VoIP, video, and web traffic at the same time on one shared radio channel — something CSMA/CA cannot do fairly?

The answer lives in three design moves. First, the PHY trades raw symbol rate for robustness: longer OFDM symbols, more subcarriers, forward error correction, and a four-level adaptive modulation ladder that lets a far SS fall back to QPSK. Second, the MAC is **scheduled, not contended**: the base station is the only transmitter that can speak without permission, and it tells every other station precisely which OFDM slots are theirs. Third, the QoS machinery (UGS/rtPS/nrtPS/BE) gives the scheduler a way to honor latency deadlines instead of best-effort fairness. This lesson builds all three from scratch.

## The Concept

802.16 is two tightly-coupled designs. The **physical layer** pushes OFDM into licensed wide-area spectrum, scaling channel size, symbol duration, and modulation to stretch a 10 km cell. The **MAC sublayer** then sits on top and replaces contention with a **deadline-aware scheduler** that hands every flow a place in the next frame. The `code/main.py` file we build will compile the MAC header, allocate a Connection ID, schedule four service classes into a 5 ms TDD frame, and emit DL-MAP / UL-MAP information elements.

### 802.16 architecture: one tower, many stations, one backbone

The 802.16 network is a point-to-multipoint cellular system. A **base station (BS)** sits on a tower and is the only node allowed to start a frame. Two kinds of subscriber device exist: a **Subscriber Station (SS)** in 802.16d, fixed to a rooftop or window, and a **Mobile Station (MS)** in 802.16e, free to hand off at vehicular speed. The BS aggregates everything onto a provider backbone that hands off to an **Access Service Network (ASN)** and then to a **Connectivity Service Network (CSN)** — the latter is the IP core, the AAA / RADIUS, the DHCP, the SIP, the public Internet. From a layer-2 point of view, the BS is the only addressable entity on the air; the SSes are not routable until they have been admitted and assigned a CID.

```
   ┌────────────┐                ┌────────────────┐
   │  Internet  │                │  PSTN / VoIP   │
   └─────┬──────┘                └────────┬───────┘
         │                               │
         └─────────────┬─────────────────┘
                       │  CSN (core, AAA, DHCP)
                       │
                ┌──────┴──────┐
                │   ASN GW    │  Access Service Network
                └──────┬──────┘
                       │  point-to-point
                  ┌────┴────┐
                  │   BS    │  Base Station (sector antennas)
                  └────┬────┘
              ┌───────┼───────┐
            SS-1    SS-2     MS-3   ...   SS-N
         (fixed) (fixed)  (mobile)
```

Two physical regimes coexist in 802.16. The original 10-66 GHz bands (802.16, 2001) require line-of-sight and short cells, with single-carrier air interfaces up to 134 Mbps in a 28 MHz channel. The revised 2-11 GHz band (802.16a / 802.16d, 2003-2004) drops LOS, uses OFDM, and is what people mean by "WiMAX." Both 10-66 GHz LOS and 2-11 GHz NLOS variants sit on the same MAC, which is the design's biggest win.

### OFDM PHY: many slow subcarriers beat one fast carrier

The 802.16 PHY borrows OFDM (orthogonal frequency-division multiplexing) from 802.11a/g and scales it up roughly 20x to tolerate multipath in a wide area. The licensed spectrum is split into many narrow subcarriers; data on each is sent slowly enough that a long echo from a building or hill does not blur the next symbol.

| Knob | Fixed WiMAX (802.16d) | Mobile WiMAX (802.16e SOFDMA) | 802.11a/g (for contrast) |
|---|---|---|---|
| FFT size (N) | 256 (also 128, 192) | 128 / 512 / 1024 / 2048 | 64 |
| Subcarrier spacing | ~10.94 kHz | ~10.94 kHz | 312.5 kHz |
| Symbol duration (useful) | ~91.4 us | ~91.4 us | 4 us |
| Cyclic prefix (CP) | 1/4, 1/8, 1/16, 1/32 of symbol | same | 1/4 |
| Channel bandwidth | 3.5 MHz (fixed) | 1.25 / 5 / 10 / 20 MHz | 20 MHz |
| Net downlink (per 5 MHz pair) | ~12.6 Mbps | ~12.6 Mbps | ~30 Mbps |
| Modulation & coding | BPSK 1/2 up to 64-QAM 3/4 | same + collaborative MIMO | same family |

The numbers behind the "20x bigger" claim: a 91 us OFDM symbol with a 1/4 cyclic prefix gives 114 us total, while an 802.11a symbol is 4 us. That 28x ratio is the time-budget that lets 802.16 spread its signal over a 10 km cell with a tolerable amount of inter-symbol interference from distant reflectors. The 256-point FFT then splits the channel into 256 orthogonal subcarriers; pilot subcarriers carry known symbols for channel estimation, guard subcarriers sit at the band edges, and the data subcarriers carry the user's traffic.

Adaptive **burst profiles** are the link-adaptation trick. The BS continuously measures each SS's SNR and picks a profile per frame, per SS:

| Profile | Modulation | Coding rate | Bits / symbol | Typical use |
|---|---|---|---|---|
| 1 | BPSK | 1/2 | 1 | cell edge, deep fading |
| 2 | QPSK | 1/2 | 2 | far SS, rainy weather |
| 3 | QPSK | 3/4 | 3 | mid-cell |
| 4 | 16-QAM | 1/2 | 4 | mid-cell, good SNR |
| 5 | 16-QAM | 3/4 | 6 | near BS |
| 6 | 64-QAM | 2/3 | 8 | near BS, line-of-sight |
| 7 | 64-QAM | 3/4 | 9 | near BS, line-of-sight |

The scheduler uses this per-SS knob to allocate time-slot count, since a 64-QAM burst carries roughly 4.5x the bits of a BPSK burst in the same OFDM slots.

### Duplex: TDD vs FDD, and why TDD wins

The 802.16 frame can be **TDD** (time-division duplex) or **FDD** (frequency-division duplex). TDD puts the downlink and uplink in different time slots of the same channel; FDD puts them on different frequencies. TDD is the preferred mode because Internet traffic is asymmetric (often 2:1 or 3:1 downstream), and TDD lets the operator dial the DL/UL split frame by frame. FDD is reserved for systems that have to maintain symmetric full-duplex connections — mostly legacy voice carriers.

### The TDD frame: preamble, FCH, MAPs, bursts, guards

A 5 ms TDD frame is the heartbeat of the system. It starts with a **preamble** that every SS uses to lock its AGC, synchronize symbol timing, and estimate the channel. The Frame Control Header (FCH) follows with the most important control info. Then the **DL-MAP** and **UL-MAP** — these are the heart of the MAC: a list of "where" and "when" entries that tell every SS which OFDM symbols carry their data. After the maps come the downlink bursts (one per SS, in the order the MAP says), a Transmit/Receive Transition Gap (TTG) to let radios flip from RX to TX, then the uplink bursts, and finally a Receive/Transmit Transition Gap (RTG).

```
|<------------------------- 5 ms TDD frame -------------------------->|
+------+----+---------+-----------------+-----+-----------------+-----+
| Pream| FCH| DL-MAP  |  DL bursts      | TTG |   UL bursts     | RTG |
| ble  |    | +UL-MAP | (per SS, per UI)|     | (per SS, BW-req)|     |
+------+----+---------+-----------------+-----+-----------------+-----+
|<-- DL subframe (variable) --->|<-- UL subframe (variable) ------>|
|<-- OFDM symbol grid: time on X axis, subcarrier on Y axis --->|
```

Ranging and initial-access bursts are special UL slots. When a new SS first powers on it does not yet have a CID, so it transmits in a contention-based ranging region; the BS replies with a ranging response telling the SS to adjust its timing and power before it can be admitted.

### The MAC PDU: generic header, payload, optional CRC

The MAC PDU is a 6-byte generic header followed by an optional payload and an optional CRC. Layout per Fig. 4-33:

| Field | Width | Purpose |
|---|---|---|
| EC | 1 bit | 1 = payload encrypted |
| Type | 6 bits | frame kind: generic, broadcast, ranging, fragment, packing, etc. |
| CI | 1 bit | 1 = CRC present at the end of the frame |
| EK | 2 bits | encryption key index (0-3) |
| Length | 11 bits | total length including header |
| CID | 16 bits | Connection Identifier (which flow this is) |
| HCS | 8 bits | Header Check Sequence, polynomial x^8 + x^2 + x + 1 |
| Payload | 0+ bytes | SDU (or subheaders for packing/fragmentation) |
| CRC | 0 or 4 bytes | only if CI=1 |

The **CID** is the heart of the connection-orientation. Unlike an 802.11 MAC address (a per-station identifier) or an IP 5-tuple (a stateless flow hash), a CID binds a particular (SS, service class, transport) tuple to a 16-bit ID for the lifetime of the connection. When an SS enters the network it gets a 16-bit basic + primary management CID pair; once admitted, each service flow gets its own CID. A single SS can therefore hold many CIDs simultaneously — one for UGS voice, one for rtPS video, one for nrtPS file transfer, one for BE web. The BS uses the CID, not the MAC address, to decide how to schedule and police.

A **bandwidth-request (BW-REQ)** frame is a stripped-down PDU: 1 bit `1` (header type discriminator) + 1 bit `0` + 6 bits Type + 16 bits Bytes-Needed + 16 bits CID + 8 bits HCS. No payload, no CRC. The SS sends it on the contention-based CDMA ranging/code region of the UL subframe and the BS grants bytes in the next UL-MAP.

### Four service classes: a deadline-aware scheduler

This is the conceptual break from 802.11. 802.11 is best-effort on a shared contention channel; 802.16 is **connection-oriented with four QoS classes** decided at admission time.

| Class | Acronym | Use case | Scheduling | Latency target |
|---|---|---|---|---|
| Unsolicited Grant Service | UGS | VoIP (G.711), CBR circuits | BS issues a fixed-size grant every frame automatically — no polling, no contention | <20 ms jitter |
| Real-Time Polling Service | rtPS | MPEG video, VoIP with silence suppression | BS polls the SS at fixed interval; SS reports queue depth in BW-REQ | <100 ms |
| Non-Real-Time Polling Service | nrtPS | FTP, bulk transfer | BS polls regularly but not at fixed cadence; SS can also use contention | seconds |
| Best-Effort | BE | Web, email | No polling; SS contends for any unallocated UL slots | no guarantee |

UGS is the cleanest demonstration of "deadline MAC." The connection is admitted with a maximum sustained traffic rate and a grant interval. Once admitted, the SS does not need to ask for grants — every TDD frame the BS automatically reserves enough OFDM slots at the agreed profile to carry the CBR. rtPS works the same way but the data rate varies frame to frame: the BS polls the SS once per superframe, the SS reports its current queue depth in a BW-REQ, and the BS grants exactly that many bytes in the next frame. nrtPS gets polled but tolerates jitter; BE gets whatever is left over and contends on the BW-REQ channel like a 1-persistent Ethernet.

This design is what makes 802.16 look more like a 4G cellular system than like Wi-Fi. The MAC is **deadline-aware**: the scheduler has an explicit budget per frame, per class, and runs a "what gets me closest to my deadline next?" pass to fill the UL-MAP. A late UGS packet is dropped and reported; a late rtPS packet is also dropped, but the BS gives the SS another chance to catch up. A late BE packet just sits in the queue.

### DL-MAP and UL-MAP: the per-frame schedule

The MAPs are the schedule. Each is a list of **Information Elements (IEs)**: a fixed-format record per allocation. A DL-MAP IE says "starting at OFDM symbol S, lasting L symbols, using burst profile P, destined for CID C" and a UL-MAP IE says the same but for the uplink. The BS broadcasts both MAPs in the FCH region of every frame; an SS reads them and figures out which slots to wake on and which to sleep through. Our `code/main.py` will emit a pair of small MAPs for two SSes.

### Security: PKMv1, PKMv2, and AES-CCM

The security sublayer sits below the MAC common sublayer and handles authentication, key management, and encryption. PKMv1 (Privacy Key Management, version 1) uses X.509 certificates and RSA public keys for mutual authentication at association, then derives a Traffic Encryption Key (TEK) and keys it to a Security Association (SA). PKMv2 (in 802.16e) replaces the static RSA handshake with EAP-based extensible authentication and adds AES-CCM (counter mode with CBC-MAC) for both confidentiality and integrity of the MAC PDU payload. Only the payload is encrypted — the headers stay in the clear so any relay in the BS can still see the CID and route accordingly.

## Build It

`code/main.py` is a stdlib-only toolkit with three pieces wired to the concept.

1. **Generic MAC header + BW-REQ encoder** — packs the 6-byte generic header and the 4-byte bandwidth-request header into `bytes`, computes the 8-bit Header Check Sequence over the first 40 bits using the polynomial x^8 + x^2 + x + 1, and exposes a `decode_header()` that reverses it.
2. **Connection-ID allocator + service-flow scheduler** — `ServiceFlow` objects carry (CID, class, grant interval, current queue). The scheduler walks the four classes in priority order each frame, polls rtPS/nrtPS, gives UGS its pre-reserved grant, and returns a list of allocations.
3. **DL-MAP / UL-MAP builder** — turns a list of allocations into a 5 ms TDD frame (256-OFDM-symbol budget, 50/50 split) with one IE per SS per direction, plus a tiny ASCII rendering of the schedule so you can eyeball the frame.

Run `python3 code/main.py` and watch the scheduler fill the frame, then change the queue sizes or the SS count and rerun to see the schedule shift.

## Use It

| Task | Evidence | What good looks like |
|---|---|---|
| Pick the right service class | Application profile | UGS for 64 kbps G.711 voice with strict jitter, rtPS for VBR MPEG, nrtPS for FTP, BE for web |
| Decode a generic MAC header | `code/main.py` `decode_header()` | EC=1, Type=0, CI=0, EK=2, Length=42, CID=0x0A0F, HCS=0xC6 |
| Build a TDD frame | Frame text dump | 5 ms, 50/50 split, 4 bursts (2 DL, 2 UL), preamble + FCH + MAPs accounted for |
| Allocate per-SS | DL-MAP IE | Each IE has OFDM-symbol start, length, burst profile, CID |
| Schedule deadline traffic | Scheduler output | UGS gets first 8 UL slots every frame, rtPS gets polled, BE goes to contention |
| Pick modulation | SNR measurement | BPSK at SNR<8 dB, QPSK 8-15 dB, 16-QAM 15-25 dB, 64-QAM >25 dB |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **frame-dissection cheat sheet** mapping every byte of the generic MAC header and the BW-REQ frame, plus a 1-page TDD frame diagram (preamble / FCH / MAPs / DL / TTG / UL / RTG).
- A **service-class card** with the UGS / rtPS / nrtPS / BE rules, polling cadences, and an example traffic profile each.
- The **encoder + scheduler script** (`code/main.py`) wired to your own test traffic and a plot of the resulting frame.

Start from `outputs/prompt-wimax-80216-broadband-wireless.md`.

## Exercises

1. A VoIP connection uses 64 kbps G.711 with 20 ms frames. The base station issues UGS grants. How many bytes per 5 ms TDD frame should the BS reserve, and why must the BS pick the grant size based on profile (e.g. 64-QAM at SNR=28 dB vs QPSK at SNR=12 dB)?
2. A 10 km cell with 256-OFDM-symbol budget and a 50/50 TDD split. The OFDM symbol duration is 91.4 us (useful) plus 1/4 cyclic prefix. Compute (a) total DL symbols per frame, (b) raw DL bit rate at 64-QAM 3/4, and (c) why this is well below the 12.6 Mbps headline number.
3. Two SSes both have a single rtPS connection. SS-A polled this frame reports 800 bytes waiting; SS-B polled reports 200 bytes. The UL subframe has 16 OFDM symbols at QPSK 1/2. Draw the UL-MAP IEs the BS will issue and explain the fairness rule.
4. A best-effort Web session gets no polling. The contention-based BW-REQ channel is 4 codes per UL slot. Two SSes both contend in the same slot. What is the backoff algorithm and what is the worst-case number of attempts before the BS admits a request, given the Ethernet-style 0..15 truncation?
5. The 802.16e amendment adds SOFDMA with 512/1024/2048 FFT sizes for a constant 10.94 kHz subcarrier spacing. Why does keeping the subcarrier spacing fixed when the channel bandwidth grows give you a free win in wideband deployments (10 MHz, 20 MHz)?
6. Run `code/main.py` with three SSes (one UGS, one rtPS, one BE) and 30 OFDM symbols of DL budget. From the printed DL-MAP, identify which SS got how many symbols, justify the priority order, and propose a tweak to give BE a fair share without harming UGS.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| WiMAX | "wireless DSL" | The WiMAX Forum's brand for IEEE 802.16 BWA products (certified interoperable subsets of the standard) |
| BWA | "last-mile wireless" | Broadband Wireless Access — metropolitan-scale last-mile alternative to cable / DSL / fiber |
| 802.16d / 802.16e / 802.16m | "fixed / mobile / WiMAX 2" | Fixed NLOS (2004), mobile with handoffs (2005), IMT-Advanced (2011) |
| OFDM | "many subcarriers" | 256-point FFT, ~10.94 kHz spacing, ~91 us useful symbol, 1/4 cyclic prefix, BPSK → 64-QAM adaptive |
| OFDMA | "subcarriers per user" | Orthogonal FDMA — subcarriers are time-shared across SSes inside the same frame |
| TDD | "share the channel by time" | DL/UL in different time slots of one channel; lets the BS tune the DL/UL split frame by frame |
| DL-MAP / UL-MAP | "the schedule" | Per-frame broadcasts naming which OFDM symbols each CID may use; the entire scheduled MAC |
| CID | "which connection" | 16-bit Connection Identifier — the per-(SS, service-flow) handle inside 802.16's connection-oriented MAC |
| UGS / rtPS / nrtPS / BE | "QoS classes" | Unsolicited grant, real-time polling, non-real-time polling, best-effort; UGS gets a grant every frame, BE contends |
| Burst profile | "the bit-loading" | Per-SS choice of (modulation, coding) for the next frame, picked from the 7-profile ladder |
| BW-REQ | "ask for airtime" | 4-byte contention-based bandwidth request on the UL; BS grants bytes in the next UL-MAP |
| Ranging | "find the cell" | New-SS uplink procedure to adjust timing, power, and frequency before admission; uses contention code channels |
| PKMv1 / PKMv2 | "the key exchange" | X.509 + RSA (v1) or EAP (v2) for mutual auth; AES-CCM for payload confidentiality + integrity |
| AES-CCM | "the cipher" | Counter-mode AES with CBC-MAC; encrypts MAC PDU payload, headers stay clear so the BS can read CIDs |
| FCH / TTG / RTG | "frame glue" | Frame Control Header (just after preamble), Transmit/Receive Transition Gap, Receive/Transmit Transition Gap |
| HCS | "header checksum" | 8-bit CRC over the 40-bit header, polynomial x^8 + x^2 + x + 1, lets the BS drop a corrupt header without decrypting |

## Further Reading

- **IEEE 802.16-2004** — *IEEE Standard for Local and Metropolitan Area Networks — Part 16: Air Interface for Fixed Broadband Wireless Access Systems.* The fixed-WiMAX baseline; OFDM PHY, MAC PDUs, MAPs, security.
- **IEEE 802.16e-2005** — *Amendment for Physical and Medium Access Control Layers for Combined Fixed and Mobile Operation in Licensed Bands.* SOFDMA, handoff, PKMv2, real-world mobile WiMAX.
- **IEEE 802.16m-2011** — *Advanced Air Interface.* WiMAX 2 / IMT-Advanced target, FDD + TDD, multi-user MIMO.
- Andrews, J. G., Ghosh, A., & Muhamed, R. (2007), *Fundamentals of WiMAX: Understanding Broadband Wireless Networking.* Prentice Hall — the most readable single treatment of the PHY / MAC trade-offs in 802.16.
- Eklund, C., Marks, R. B., Stanwood, K. L., & Wang, S. (2002), "IEEE Standard 802.16: A Technical Overview of the WirelessMAN Air Interface for Broadband Wireless Access," *IEEE Communications Magazine* — the original overview paper.
- Tanenbaum, A. S. & Wetherall, D. J., *Computer Networks* (5th ed.), Section 4.5 — the source chapter for this lesson.
