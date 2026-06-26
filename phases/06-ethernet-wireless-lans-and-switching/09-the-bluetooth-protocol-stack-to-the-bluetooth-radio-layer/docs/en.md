# The Bluetooth Protocol Stack to The Bluetooth Radio Layer

> Bluetooth's classic stack does not follow OSI, TCP/IP, or 802 — it stacks a **radio layer** (2.4-GHz ISM, 79 channels of 1 MHz, GFSK, 1 Mbps gross), a **link control / baseband** layer (the closest thing to a MAC sublayer), a **link manager**, the **L2CAP** adaptation layer, and **profiles** that each cut a vertical slice through the stack. A piconet is a centralized TDM system: one master, up to 7 active slaves, 625-µs slots, master in even slots and slaves in odd slots, hopping up to 1600 hops/sec under a pseudorandom sequence the master dictates. Frames are 1, 3, or 5 slots long; hops happen only between frames, never inside one. The most common header is 18 logical bits (Addr/Type/Flow/Ack/Seq/Checksum) carried as 54 transmitted bits because every bit is **repeated three times** and decoded by majority vote — a brute-force FEC that exists because the radios are 2.5-mW, sub-$5 parts. SCO links carry one 64-kbps PCM voice channel and are never retransmitted; ACL links are best-effort and use stop-and-wait with a 1-bit sequence number. When Bluetooth and 802.11 jammed each other in the ISM band, the fix was **adaptive frequency hopping (AFH)** — pruning busy channels out of the hop set. This lesson maps the stack, decodes a header byte-for-byte in `code/main.py`, and ties each layer to the evidence you would see in a sniffer trace.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib header decoder)
**Prerequisites:** Phase 6 lessons on 802.11 framing and the MAC sublayer; basic FEC/CRC familiarity
**Time:** ~75 minutes

## Learning Objectives

- Name each layer of the classic Bluetooth stack (radio, link control/baseband, link manager, L2CAP, profiles) and state what it owns and what evidence it leaves.
- Compute the radio-layer parameters: 79 channels x 1 MHz, 625-µs slots, 1600 hops/sec, 250–260 µs settling time per hop, and explain why a 5-slot frame is more efficient than a 1-slot frame.
- Decode the 18-bit Bluetooth header (Addr, Type, Flow, Ack, Seq, Checksum) and explain the 3x repetition / majority-vote FEC that expands it to 54 transmitted bits.
- Distinguish SCO (fixed-slot, never retransmitted, 64-kbps PCM) from ACL (best-effort, stop-and-wait retransmit) links and pick the right one for voice vs. data.
- Explain adaptive frequency hopping (AFH) as the fix for Bluetooth/802.11 ISM-band interference, and what symptom it cures.

## The Problem

A field engineer gets a complaint: a Bluetooth hands-free headset cuts in and out, but only in the conference room — the one with three busy Wi-Fi access points. File transfers between two laptops in that room are also crawling. The user blames "the headset." But the headset, the file transfer, and the Wi-Fi all fight over the same 2.4-GHz ISM band, and the symptom you actually see (choppy audio vs. slow-but-correct file copy) depends on *which Bluetooth link type* each app uses and *how the radio hops*.

To diagnose this you cannot stay at the application layer. You must reduce "headset is choppy" to a layer: the **radio layer** (hop set colliding with Wi-Fi channels)? The **link control layer** (SCO voice frames dropped, which by spec are *never retransmitted*)? Or **L2CAP** (the ACL data path that *does* retransmit, hence slow-but-correct)? Each answer points to a different fix, and only one — pruning the hop set with AFH — actually helps the headset.

## The Concept

### The stack that follows no model

Bluetooth's classic architecture is deliberately its own thing — not OSI, TCP/IP, or 802. From the bottom:

| Layer | Role | OSI analogue | Evidence it produces |
|---|---|---|---|
| **Radio** | Modulation, hopping, 2.4-GHz ISM | Physical | Channel index, hop sequence, RSSI, modulation (1X/2X/3X) |
| **Link control (baseband)** | Slot timing, frame format, access code | MAC + some PHY | 625-µs slot alignment, access code, 18-bit header |
| **Link manager** | Pairing, encryption, power mgmt, QoS, link setup | — | SCO/ACL link establishment, pairing exchange |
| **L2CAP** | Segment/reassemble, multiplex, retransmit, QoS | LLC | Channel IDs (CIDs), packet boundaries, retransmits |
| **Profiles** | Vertical app slices (headset, A2DP, HID...) | App | Which protocols are present/absent for that use case |

The **host-controller interface (HCI)** line splits the stack: everything below (radio, baseband, link manager) lives on the cheap Bluetooth chip; everything above (L2CAP and up) runs on the host CPU. See `assets/the-bluetooth-protocol-stack-to-the-bluetooth-radio-layer.svg` for the layered view with the HCI line drawn in.

Profiles are drawn as *vertical* boxes because each one selects only the protocols it needs. A streaming-audio profile may skip L2CAP entirely if it only has a steady flow of audio samples; a file-transfer profile pulls in L2CAP for segmentation and reliability.

### The radio layer, by the numbers

The radio layer moves bits master↔slave. It is a low-power (2.5 mW), ~10-meter system in the **2.4-GHz ISM band**, the same band as 802.11. Key figures you should be able to reproduce:

- **79 channels** of **1 MHz** each (2.402–2.480 GHz).
- **Frequency-hopping spread spectrum**: up to **1600 hops/sec**, slot **dwell time 625 µs** (1/1600 s).
- All nodes in a piconet hop **simultaneously**, following the master's pseudorandom hop sequence and slot clock.
- **Modulation**: basic rate is GFSK (frequency shift keying), 1 symbol/µs = **1 Mbps gross**. Bluetooth 2.0 EDR adds phase-shift keying: **2 bits/symbol (2 Mbps)** and **3 bits/symbol (3 Mbps)**, used **only in the data portion** of a frame.

Sanity check: 1600 hops/sec x 625 µs/slot = 1.0 s — slot rate and dwell time are two views of the same clock.

### Adaptive frequency hopping (AFH) — the ISM coexistence fix

Early Bluetooth and 802.11 transmitted blindly across the same band and **ruined each other's transmissions**; some companies banned Bluetooth outright. The fix is **adaptive frequency hopping**: the master measures which of the 79 channels carry other RF energy (e.g., a Wi-Fi AP on channels 1/6/11) and **removes those channels from the hop set** — the sequence stays pseudorandom, just drawn from a smaller, cleaner pool. This is the cure for the conference-room headset: AFH steers Bluetooth away from the busy Wi-Fi channels, restoring the SCO voice link.

### Link control / baseband: slots, frames, and TDM

The baseband layer is "the closest thing Bluetooth has to a MAC sublayer." The master defines **625-µs slots**; **master transmits in even slots, slaves in odd slots** — strict centralized TDM where the master owns half the airtime and the slaves share the other half. Frames are **1, 3, or 5 slots** long, and hops occur **only between frames**, never mid-frame. Every frame carries a fixed **126-bit overhead** (72-bit access code + 54-bit header) plus a **250–260 µs settling time per hop** so the cheap radio can stabilize on the new frequency. Because that overhead is constant per frame, a **5-slot frame is far more efficient** than a 1-slot frame: same overhead, ~5x the payload, and fewer settling gaps per byte delivered.

### SCO vs. ACL: the two link types

The link manager sets up two kinds of user-data links — and choosing wrong is exactly the headset bug:

| Property | SCO (Synchronous Connection-Oriented) | ACL (Asynchronous Connectionless) |
|---|---|---|
| Use case | Real-time voice / telephony | Bursty packet data |
| Slots | Fixed reserved slot each direction | Best-effort, irregular |
| Retransmission | **Never** — uses FEC instead | **Yes** — stop-and-wait retransmit |
| Per-slave limit | Up to **3** SCO links | **1** ACL link |
| Payload | One **64,000-bps PCM** audio channel | From L2CAP, up to 64 KB packets |

This is why the headset goes *choppy* (SCO: a corrupted voice frame is gone forever) while the file copy goes *slow but correct* (ACL: bad frames are retransmitted until they arrive).

### L2CAP: the host-side adaptation layer

ACL data comes from **L2CAP**, which has four jobs: **segmentation/reassembly** (accept packets up to **64 KB** from upper layers, chop them into baseband frames, reassemble at the far end); **multiplexing/demultiplexing** (route each reassembled packet to the right upper protocol — RFCOMM, service discovery, ...); **error control & retransmission** (detect errors, resend unacknowledged packets); and **QoS enforcement** across multiple links.

### The header: 18 logical bits, 54 transmitted bits

The most important frame format (Fig. 4-36) starts with a **72-bit access code** (usually derived from the master, so a slave in range of two masters can tell which traffic is its own), followed by the **54-bit header**. That header is really **18 logical bits** repeated **three times**:

| Field | Bits | Meaning |
|---|---|---|
| Addr | 3 | Which of the 8 active devices (1 master + 7 slaves) the frame targets |
| Type | 4 | Frame type (ACL/SCO/poll/null), FEC type, slot length |
| Flow (F) | 1 | Slave asserts when its buffer is full — primitive flow control |
| Ack (A) | 1 | Piggybacked acknowledgement |
| Seq (S) | 1 | 1-bit sequence number — protocol is **stop-and-wait** |
| Checksum | 8 | Header error check (HEC) |

18 x 3 = 54. On receive, a tiny circuit looks at all three copies of each bit; if they agree, accept; if not, **majority vote wins**. So 54 bits of channel capacity carry 10 bits of useful header information. That brute-force redundancy exists precisely because the radios are cheap, low-power (2.5 mW), and operate in a noisy band. `code/main.py` decodes a real 18-bit header and demonstrates the 3x majority-vote recovery from a single-bit error.

### Data field sizes

At the **basic (1X) rate** the data field is **0–2744 bits** for a 5-slot frame (240 bits for a single slot). At **enhanced (2X/3X) rate**, a 16-bit guard/sync pattern precedes a data field of **0–8184 bits** plus a short trailer — the access code and header still ride at 1X; only the payload speeds up.

## Build It

1. Read `code/main.py`. It defines the radio-layer constants (79 channels, 625 µs, 1600 hops/sec) and a `decode_header()` that takes 54 transmitted bits and recovers the 18-bit header by majority vote.
2. Run `python3 main.py`. Confirm the printed radio summary (channel count, hop rate, slot timing) matches the numbers above.
3. Watch the majority-vote demo: the program flips one bit in one copy of the header and shows that the decoded Addr/Type/Flow/Ack/Seq/Checksum are still correct.
4. Use the link-type chooser at the bottom: feed it "voice" and "bulk-file" workloads and confirm it picks SCO vs. ACL with the right rationale.
5. Sketch the slot timeline (even = master, odd = slave) for a 5-slot master frame and note where the next legal hop boundary is.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Locate the failing layer | Sniffer channel map, link type (SCO/ACL), retransmit counters | You can say "SCO voice on a busy hop set," not just "headset is broken" |
| Verify normal radio behavior | Hop sequence across 79 channels, RSSI per channel, 625-µs slot alignment | Master/slave alternate even/odd slots; hops only between frames |
| Diagnose ISM interference | Per-channel error rate vs. Wi-Fi channel occupancy | Busy channels show high errors; AFH-pruned hop set avoids them |
| Confirm header integrity | The three header copies and the majority-vote result | All three copies agree, or the majority recovers a single-bit flip |
| Pick the right link | Workload (real-time vs. bursty) mapped to SCO vs. ACL | Voice → SCO (no retransmit, FEC); data → ACL (stop-and-wait) |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **trace-annotation checklist** for a Bluetooth capture: access code → 18-bit header fields → link type → slot parity → hop channel.
- A **one-page runbook** for "choppy headset in a Wi-Fi-heavy room" that walks radio → AFH → SCO vs. ACL.
- The **stack diagram** (`assets/the-bluetooth-protocol-stack-to-the-bluetooth-radio-layer.svg`) annotated with the HCI line and where each piece of evidence appears.

Start from `outputs/prompt-the-bluetooth-protocol-stack-to-the-bluetooth-radio-layer.md`.

## Exercises

1. A piconet master needs to talk to 7 slaves plus reserve 3 SCO voice links to one of them. Lay out a 16-slot timeline (even/odd parity) and show where the SCO reserved slots land. How many slots remain for ACL data?
2. Wi-Fi APs occupy 2.412, 2.437, and 2.462 GHz (channels 1/6/11), each ~22 MHz wide. Estimate how many of Bluetooth's 79 1-MHz channels AFH should prune, and what fraction of the hop set survives.
3. Take the 18-bit header `Addr=101 Type=0011 F=1 A=0 S=1 HEC=10110100`. Hand-expand it to 54 transmitted bits, flip bit 7 of the second copy, then show the majority-vote decoder recovers the original. Verify against `code/main.py`.
4. A streaming-audio profile and a file-transfer profile both run over the same piconet. Which one would skip L2CAP and why? What L2CAP function makes the file transfer reliable but the audio not?
5. A 5-slot ACL frame carries 2744 payload bits at 1X; compute the effective throughput including the 126-bit overhead and 250-µs settling time per hop, and compare it to five back-to-back 1-slot frames.
6. The user pairs with PIN "0000." Explain why the old PIN method gave almost no security and how secure simple pairing (passkey confirmation) closes that gap without the user choosing a PIN.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Piconet | "a Bluetooth network" | Centralized TDM cell: 1 master + up to 7 active slaves, master owns the clock and hop sequence |
| Scatternet | "lots of devices" | Several piconets bridged by a node that belongs to more than one |
| Slot | "a time chunk" | A 625-µs interval; master uses even slots, slaves odd; frames span 1/3/5 slots |
| Hop | "channel change" | A jump to a new 1-MHz channel between frames; up to 1600/sec, pseudorandom |
| AFH | "Bluetooth coexistence" | Pruning busy ISM channels out of the hop set to avoid 802.11 interference |
| SCO link | "the voice one" | Fixed-slot, never-retransmitted, 64-kbps PCM; reliability via FEC, not ARQ |
| ACL link | "the data one" | Best-effort, stop-and-wait retransmit, one per slave, fed by L2CAP |
| L2CAP | "the adaptation layer" | Segments 64-KB packets, multiplexes, retransmits, enforces QoS — host side of HCI |
| 54-bit header | "a big header" | 18 logical bits repeated 3x, decoded by majority vote for cheap noisy radios |
| HCI line | "chip vs. host" | Split where radio/baseband/link-manager run on the chip and L2CAP+ run on the host |

## Further Reading

- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 4 (Bluetooth): architecture, radio layer, link layers, and frame structure (Figs. 4-34 through 4-36).
- IEEE 802.15.1-2005 — the standardized form of the classic Bluetooth PHY/MAC.
- Bluetooth Core Specification (Bluetooth SIG) — baseband, L2CAP, link manager, and adaptive frequency hopping details.
- IEEE 802.11 (for the ISM-band coexistence story Bluetooth's AFH was designed to solve).
- Wireshark Bluetooth capture documentation and the `btbb`/`btle` display-filter references for annotating real traces.
