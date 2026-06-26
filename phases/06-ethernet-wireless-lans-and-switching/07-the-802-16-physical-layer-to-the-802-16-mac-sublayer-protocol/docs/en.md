# The 802.16 Physical Layer to The 802.16 MAC Sublayer Protocol

> IEEE 802.16 (WiMAX) is a broadband wireless MAN: one base station (BS) talks point-to-multipoint to many subscriber stations (SS) over licensed spectrum from 2-11 GHz, in channels of 1.25-20 MHz. The PHY uses OFDMA — different subcarrier sets go to different stations at once — with adaptive modulation (QPSK = 2 bits/symbol for far/low-SNR stations, QAM-16 = 4, QAM-64 = 6 bits/symbol for near stations) plus convolutional FEC, yielding up to ~12.6 Mbps down / 6.2 Mbps up per 5-MHz channel. Time Division Duplex (TDD) frames repeat: **preamble → DL-MAP / UL-MAP → downlink bursts → guard → uplink bursts (including a contention ranging slot)**. The MAC is *connection-oriented* (unlike 802.11/Ethernet): every connection gets one of four QoS classes — constant bit rate, real-time VBR, non-real-time VBR, best-effort — and uplink bandwidth is granted by the BS via the UL-MAP. Best-effort requests contend in ranging slots and resolve collisions with the **Ethernet binary exponential backoff** algorithm. Every MAC frame opens with a 6-byte generic header guarded by an 8-bit header CRC using polynomial x⁸+x²+x+1; payload and full-frame CRC are both optional. This lesson builds a frame parser and a TDD-map / backoff simulator so the abstract standard becomes observable bytes and timing.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib)
**Prerequisites:** Phase 06 lessons on 802.11 MAC and CSMA/CD backoff; OFDM and modulation from Phase 02
**Time:** ~75 minutes

## Learning Objectives

- Map an 802.16 OFDMA/TDD frame in order (preamble, DL-MAP, UL-MAP, DL bursts, guard, UL bursts, ranging) and explain why the BS rewrites the maps every frame.
- Compute achievable PHY rate from channel width, subcarrier count, symbol time, and modulation (QPSK/QAM-16/QAM-64), and explain adaptive modulation by SNR.
- Decode the 6-byte generic MAC header field-by-field (EC, Type, CI, EK, Length, Connection ID, Header CRC) and the bandwidth-request header variant.
- Pick the correct QoS class (CBR, rt-VBR, nrt-VBR, BE) for a given traffic profile and state how each gets uplink grants (dedicated burst, periodic poll, frequent poll, contention).
- Verify the header CRC over polynomial x⁸+x²+x+1 and explain why the payload CRC is optional for real-time traffic.

## The Problem

A WISP deploys WiMAX to bring Internet to a rural valley. Two complaints land the same week. A VoIP customer 8 km out reports choppy calls during busy hours; a household streaming video next to the tower reports occasional stalls. Both run over the *same* base station and the *same* 5-MHz channel, yet the failure modes are different.

The far VoIP user is at low SNR, so the BS dropped them to QPSK — 2 bits/symbol — and if it scheduled their constant-bit-rate connection late in the uplink map, jitter spikes. The near streamer is on best-effort: their bandwidth requests collide in the contention ranging slot, and binary exponential backoff stretches the wait under load. To diagnose either, you cannot stay at the application layer. You have to read the OFDMA frame map, the QoS class on each connection, and the MAC header bytes. This lesson gives you the field layouts and a working model so "choppy" becomes "your CBR grant lands 4 ms into the uplink subframe" or "your BE request hit its third backoff."

## The Concept

Source: `chapters/chapter-04-the-medium-access-control-sublayer.md`, the 802.16 PHY and MAC sublayer material. The standard is **IEEE 802.16-2009**; the technology is marketed as **WiMAX**.

### Spectrum, channels, and OFDMA

802.16 is built for *licensed* spectrum and *wide-area* links, which drives every PHY choice. Operation spans 2-11 GHz (most deployments sit near 2.5 or 3.5 GHz). Channels are sized to the deployment: 3.5 MHz for fixed WiMAX, 1.25-20 MHz for mobile WiMAX. Transmission is OFDM, but tuned ~20× larger than 802.11: a 5-MHz mobile WiMAX channel carries **512 subcarriers** with a symbol time of roughly **100 µs**. The longer symbol tolerates the larger delay spread of long-range links.

The key MAC-relevant twist is **OFDMA (Orthogonal Frequency Division Multiple Access)**: subcarrier *sets* are handed to different stations, so several SS can transmit or receive in the same symbol period. Contrast 802.11, where one station owns all subcarriers at any instant. OFDMA also lets the BS dodge multipath: a subcarrier faded at one receiver may be clean at another, so it assigns each subcarrier to the station that uses it best.

### Adaptive modulation and the rate budget

Each subcarrier carries a symbol modulated as QPSK, QAM-16, or QAM-64. The BS picks per station by SNR:

| Modulation | Bits/symbol | Used for |
|---|---|---|
| QPSK | 2 | Distant / low-SNR stations |
| QAM-16 | 4 | Mid-range |
| QAM-64 | 6 | Near / high-SNR stations |

Data is first protected with **convolutional FEC** (Chapter 3 coding), so the channel tolerates some bit errors without retransmission — essential when no ARQ runs for real-time traffic. Net result for a 5-MHz channel with a single antenna pair: up to **~12.6 Mbps downlink** and **~6.2 Mbps uplink**. `code/main.py` reproduces this rate arithmetic so you can see how subcarrier count, symbol time, and modulation combine. The down/up asymmetry is deliberate: web traffic is often 2:1, 3:1 or more downstream, so unlike GSM/D-AMPS (equal up/down bands), 802.16 splits the channel flexibly.

### The TDD frame: preamble, maps, bursts, ranging

WiMAX supports both FDD and **TDD (Time Division Duplex)**, but TDD is preferred — easier and more flexible because the down/up split can shift frame to frame. A TDD frame, shown in `assets/the-802-16-physical-layer-to-the-802-16-mac-sublayer-protocol.svg`, repeats over time:

1. **Preamble** — all stations synchronize.
2. **DL-MAP / UL-MAP** — the BS broadcasts maps telling every station which subcarriers/times it owns this frame. The BS owns the maps, so it re-allocates bandwidth each frame to match demand.
3. **Downlink bursts** — BS sends per-SS traffic at the mapped positions.
4. **Guard time** — stations switch from receive to transmit.
5. **Uplink bursts** — each SS transmits in the slots the UL-MAP reserved for it.
6. **Ranging slot** — one uplink burst is reserved for *ranging*: new stations adjust timing and request initial bandwidth. No connection exists yet, so newcomers simply transmit and *hope no collision occurs*.

That hope is the contention point: ranging and best-effort requests can collide, and the system resolves them with binary exponential backoff (below).

### Connection-oriented MAC and four QoS classes

This is the headline difference from 802.11 and Ethernet, which are connectionless at the MAC. **All 802.16 service is connection-oriented**, point-to-multipoint: one BS, many SS, design borrowed from cable modems (one headend, many modems). Each connection is assigned one of four classes at setup, and the class decides how it gets uplink grants:

| QoS class | Intended traffic | How it gets uplink bandwidth |
|---|---|---|
| **Constant bit rate (CBR)** | Uncompressed voice | Dedicated bursts every frame, automatic — never asks |
| **Real-time VBR (rt-VBR)** | Compressed multimedia / soft real-time | BS polls the SS at a *fixed* interval: "how much this time?" |
| **Non-real-time VBR (nrt-VBR)** | Large file transfers | BS polls *often* but not at rigid intervals; may also use BE requests |
| **Best-effort (BE)** | Everything else | No polling; SS contends in marked contention slots |

The downlink is simple: the BS controls the bursts and packs MAC frames into them (individually, or back-to-back to cut overhead). The uplink is the hard part because subscribers compete, which is exactly why QoS scheduling lives there.

### Best-effort contention and binary exponential backoff

A BE subscriber sends a bandwidth request in an uplink burst the UL-MAP marked **available for contention**. Outcome:

- Success → noted in the *next* DL-MAP; the SS gets its grant.
- Failure (collision) → the SS must try again later, and to minimize repeat collisions it uses the **Ethernet binary exponential backoff** algorithm: after the *i*-th collision, wait a random number of slots in `[0, 2^i − 1]` (capped), then retry.

`code/main.py` simulates this: N best-effort stations contending across a fixed number of ranging slots, applying binary exponential backoff, and reports collisions, successful grants, and average delay vs. load — the quantitative version of "calls get choppy at busy hour."

### The generic MAC header — byte layout

Every MAC frame begins with a **6-byte generic header**, followed by an *optional* payload and an *optional* CRC. Control frames (e.g., channel-slot requests) carry no payload. The full-frame CRC is optional too — surprising, but justified: PHY FEC already corrects most errors, and real-time frames are never retransmitted, so a checksum you can't act on is pointless. When present it is the standard IEEE 802 CRC, with ACK/retransmission for reliability.

Generic header fields (bit widths, in order):

| Field | Bits | Meaning |
|---|---|---|
| Header type bit | 1 | `0` = generic header |
| EC | 1 | Encryption Control — is the payload encrypted? |
| Type | 6 | Frame type; mainly whether packing/fragmentation present |
| (reserved) | 1 | — |
| CI | 1 | CRC Indicator — is a full-frame CRC present? |
| EK | 2 | Encryption Key index (which key, if any) |
| Length | 11 | Total frame length *including* header |
| Connection ID | 16 | Which connection this frame belongs to |
| Header CRC | 8 | CRC over the header only, polynomial **x⁸+x²+x+1** |

The **bandwidth-request header** is a variant: it starts with a `1` bit instead of `0`, replaces the Length field, and uses 16 bits (bytes 2-3) to say how many bytes of bandwidth are needed. It carries no payload and no full-frame CRC. `code/main.py` parses both header types from raw bytes and verifies the 8-bit header CRC.

## Build It

1. Open `code/main.py`. Read `rate_budget()` and reproduce the ~12.6 Mbps figure from 512 subcarriers, ~100 µs symbol time, and QAM-64.
2. Run `parse_generic_header()` on the sample bytes; confirm EC/CI/EK, the 11-bit Length, the 16-bit Connection ID, and that the 8-bit header CRC over x⁸+x²+x+1 validates.
3. Flip one header byte and re-run to watch the header CRC fail — this is your "corrupted header" evidence.
4. Run the TDD/backoff simulator with increasing station counts and chart collisions vs. successful grants.
5. Sketch (or annotate the SVG) the TDD frame for your own deployment: how many DL vs UL bursts, where the ranging slot sits.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm PHY rate ceiling | Channel width, subcarrier count, symbol time, modulation order | Computed Mbps matches the ~12.6/6.2 budget for the configured channel |
| Decode a MAC frame | First 6 header bytes; EC/CI/EK/Type/Length/CID | Fields parse cleanly and header CRC validates over x⁸+x²+x+1 |
| Classify a connection | QoS class assigned at setup; polling vs contention pattern | Voice → CBR dedicated bursts; bulk transfer → nrt-VBR polling |
| Diagnose BE starvation | Contention-slot request rate, backoff counter, grants in next DL-MAP | Collision rate and backoff growth explain the added delay under load |

## Ship It

Produce one artifact under `outputs/`:

- A MAC generic-header decode cheat sheet (bit offsets + the CRC polynomial).
- A QoS-class selection runbook (traffic profile → class → grant mechanism).
- The TDD frame diagram annotated for a real channel plan.
- A short parser/simulator extending `code/main.py` (e.g., add QAM-16, or FDD framing).

Start from `outputs/prompt-the-802-16-physical-layer-to-the-802-16-mac-sublayer-protocol.md`.

## Exercises

1. A 20-MHz mobile WiMAX channel scales the 5-MHz numbers roughly linearly. Estimate downlink throughput at QAM-64 and state the assumptions you carried over from the 5-MHz/512-subcarrier case.
2. A VoIP connection 9 km out is dropped to QPSK. Its CBR connection needs 64 kbps. Explain why CBR (dedicated automatic bursts) protects it where best-effort would not, and what happens to jitter if its grant moves late in the UL subframe.
3. Given the header bytes `00 1C 04 D2 9F` (5 of 6 bytes shown), reconstruct what's missing so the 8-bit header CRC over x⁸+x²+x+1 validates, then state the Connection ID and Length you decoded.
4. Twelve best-effort stations share four contention ranging slots per frame. Using binary exponential backoff, argue what happens to average grant delay as offered load doubles, and which QoS class you would migrate the worst-hit users to.
5. The full-frame CRC is optional. Give one connection where you would *require* it (and accept retransmission) and one where omitting it is correct, justifying each from the FEC + no-retransmit reasoning.
6. Compare 802.16's connection-oriented, BS-scheduled uplink to 802.11's DCF (CSMA/CA with contention). Which guarantees bounded latency for voice, and why does the BS owning the UL-MAP matter?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| WiMAX | "rural 4G" | Marketing name for IEEE 802.16-2009 broadband wireless MAN |
| OFDMA | "WiMAX's OFDM" | Subcarrier *sets* assigned to different stations simultaneously, vs 802.11 where one station owns all subcarriers |
| TDD | "time sharing" | Time Division Duplex — up/down on the same frequency, split shifts per frame; preferred over FDD in WiMAX |
| DL-MAP / UL-MAP | "the schedule" | BS-controlled maps broadcast each frame assigning subcarriers/time slots per station |
| Ranging | "joining" | Uplink contention slot where new stations adjust timing and request initial bandwidth, hoping for no collision |
| CBR / rt-VBR / nrt-VBR / BE | "QoS levels" | Four connection classes fixing how uplink grants arrive: dedicated burst, fixed poll, frequent poll, contention |
| Generic header | "the WiMAX header" | 6-byte MAC header (EC, Type, CI, EK, Length, Connection ID, Header CRC) before optional payload/CRC |
| Header CRC | "checksum" | 8-bit CRC over the header only, polynomial x⁸+x²+x+1 — distinct from the optional full-frame CRC |
| Binary exponential backoff | "the Ethernet trick" | Collision-resolution for best-effort requests: wait random slots in [0, 2^i−1] after the i-th collision |

## Further Reading

- IEEE 802.16-2009 — the authoritative standard (PHY and MAC).
- IEEE 802.16e — mobile WiMAX amendment (Scalable OFDMA).
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 4, §4.5 "Broadband Wireless."
- IEEE 802.3 — origin of the binary exponential backoff algorithm reused here.
- Wireshark display filter reference — for capturing/annotating MAC-layer evidence.
