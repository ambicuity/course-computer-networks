# The 802.16 Frame Structure to Bluetooth Applications

> Two short-range/last-mile wireless MACs sit side by side here, and both fight noisy radio with different bets. **802.16 (WiMAX)** is connection-oriented and point-to-multipoint: every MAC frame opens with a 6-byte generic header — a 1-bit header-type flag, EC (encryption), 6-bit Type, CI (CRC-present), 2-bit EK (key index), 11-bit Length, 16-bit Connection ID, and an 8-bit Header CRC computed with x^8 + x^2 + x + 1. The payload CRC is *optional* (full IEEE 802 32-bit CRC) because the PHY does FEC and real-time frames are never retransmitted. A bandwidth-request frame flips the lead bit to 1 and carries a 16-bit "bytes needed" field instead of a payload. **Bluetooth** is a centralized TDM piconet: one master, up to 7 active slaves (255 parked), 625 µs slots, 79 × 1 MHz channels, frequency-hopping at up to 1600 hops/s. Its frame is an access code (72 b) + 54-bit header carrying just 18 logical bits repeated 3× with majority voting, then 0–2744 data bits. Links are SCO (fixed-slot 64 kbps voice, never retransmitted) or ACL (best-effort, stop-and-wait ARQ). This lesson parses both header formats byte-for-byte so you can read them in a capture.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib field parser)
**Prerequisites:** Phase 06 lessons on 802.11 framing and the MAC sublayer; binary/hex literacy; CRC concept
**Time:** ~75 minutes

## Learning Objectives

- Decode an 802.16 generic MAC header field-by-field (HT, EC, Type, CI, EK, Length, Connection ID, Header CRC) from raw bytes and explain what each bit changes.
- Distinguish an 802.16 *generic* frame from a *bandwidth-request* frame by the leading header-type bit and predict which fields disappear.
- Map the four 802.16 uplink QoS classes (CBR, rtVBR, nrtVBR, best-effort) to their grant mechanism (dedicated bursts, fixed polling, loose polling, contention + binary exponential backoff).
- Lay out the Bluetooth piconet (1 master / 7 active / 255 parked), the 625 µs TDM slot schedule, and why a 5-slot frame is far more efficient than a 1-slot frame.
- Explain why the Bluetooth 54-bit header carries only 18 real bits (3× repetition + majority vote) and contrast that redundancy strategy with the 802.16 Header CRC.
- Tell SCO from ACL links by their guarantees (fixed-slot voice never retransmitted vs. best-effort stop-and-wait ARQ) and connect each to an L2CAP behavior.

## The Problem

You are commissioning a fixed-wireless backhaul link and pairing a hands-free headset in the same afternoon, and both refuse to behave. The WiMAX subscriber station associates but a real-time voice connection stutters; your analyzer shows MAC frames whose payload CRC is *missing* and you wonder whether the link is corrupt. Meanwhile a colleague insists the Bluetooth headset "lost" half its packets, yet the device claims the audio link is healthy.

Both confusions come from not reading the frame. In 802.16 a missing payload CRC is *legal* — the CI bit says so, and real-time service deliberately skips retransmission. In Bluetooth, an SCO voice link *never* retransmits by design, so "lost frames" on it are expected; only ACL traffic uses ARQ. You cannot diagnose either system from application symptoms. You have to drop to the MAC header, decode the type bits, and let the standard tell you which behaviors are normal. This lesson teaches you to do exactly that, with a parser that turns raw bytes into named fields.

## The Concept

### The 802.16 generic MAC header

Every 802.16 MAC frame begins with a fixed **6-byte (48-bit) generic header**. The fields, in transmission order, are:

| Field | Bits | Meaning |
|---|---|---|
| HT (Header Type) | 1 | 0 = generic frame, 1 = bandwidth-request frame |
| EC (Encryption Control) | 1 | 1 = payload is encrypted |
| Type | 6 | Frame subtype: signals packing and fragmentation present |
| CI (CRC Indicator) | 1 | 1 = a full-frame CRC trailer is present |
| EK (Encryption Key sequence) | 2 | Which of the active keys encrypted the payload |
| Length | 11 | Total frame length in bytes, **including** the header |
| Connection ID | 16 | Which connection this frame belongs to |
| Header CRC | 8 | Checksum over the header only, polynomial x^8 + x^2 + x + 1 |

Two design choices in this header are exam-worthy. First, **headers are never encrypted, only payloads** — a snooper can see who talks to whom (the Connection ID) but not what they say. Second, the **payload CRC is optional**. The PHY already applies forward error correction, and 802.16 never retransmits real-time frames, so adding a 32-bit CRC to a frame that will never be re-sent buys nothing. The CI bit records whether the sender bothered. When CI = 1, the frame carries the standard IEEE 802 CRC-32 and the connection uses ACK + retransmission for reliability; when CI = 0, it is fire-and-forget.

The 11-bit Length field caps a frame at 2047 bytes total. The 8-bit Header CRC protects only the 5 preceding bytes; if it fails, the receiver discards the frame before it even looks at the Connection ID, because a corrupted ID could misroute the payload.

See `assets/the-802-16-frame-structure-to-bluetooth-applications.svg` for the bit-packed layout of both 802.16 frame variants drawn to scale.

### The bandwidth-request frame

When a best-effort subscriber needs uplink capacity it sends a **bandwidth-request frame**, Fig. 4-33(b) in Tanenbaum. It is the generic header with the lead **HT bit set to 1**, and the bytes that would have held Type/CI/EK/Length are repurposed:

| Field | Bits | Meaning |
|---|---|---|
| HT = 1 | 1 | Marks this as a bandwidth request |
| EC = 0 | 1 | No payload, so nothing to encrypt |
| Type | 6 | Request type |
| Bytes needed | 16 | How many bytes of uplink the subscriber wants to send |
| Connection ID | 16 | Which connection wants the grant |
| Header CRC | 8 | Header checksum |

A bandwidth-request frame **carries no payload and no full-frame CRC** — it is pure signaling. The base station reads "bytes needed," and if the request arrived in a contention slot it notes success in the next downlink map; failures retry after the **Ethernet binary exponential backoff** algorithm, the same 0..2^k-1 slot randomization used by classic CSMA/CD.

### 802.16 uplink QoS and the grant mechanism

802.16's MAC is connection-oriented: each connection is assigned a service class at setup, and that class decides *how* it gets uplink bandwidth.

| Service class | Intended traffic | How bandwidth is granted |
|---|---|---|
| Constant bit rate (CBR) | Uncompressed voice | Dedicated bursts, no per-burst request |
| Real-time VBR | Compressed video, soft real-time | Base station polls at a fixed interval |
| Non-real-time VBR | Large file transfers | Base station polls often but irregularly |
| Best-effort | Everything else | Contention + binary exponential backoff |

The downlink is simple — the base station owns the schedule and just packs MAC frames into PHY bursts. The uplink is the hard part because subscribers compete, which is exactly why CBR gets standing grants while best-effort has to fight for contention slots.

### The Bluetooth piconet

A Bluetooth **piconet** is one **master** plus up to **7 active slaves** within ~10 m, with up to **255 parked** nodes the master has put in a low-power state (they only wake on a beacon). Multiple piconets can overlap and share a **bridge node** to form a **scatternet**. The architecture is deliberately asymmetric so a complete chip can ship for under $5: slaves are dumb and do what the master says. At its heart a piconet is a **centralized TDM** system — the master owns the clock, and **all traffic is master↔slave**; direct slave-to-slave links do not exist.

The radio uses the 2.4 GHz ISM band split into **79 channels of 1 MHz**, with **frequency-hopping spread spectrum** at up to **1600 hops/s** and a **625 µs** dwell per slot. Every node in the piconet hops together on a pseudo-random sequence the master dictates. **Adaptive frequency hopping** later excised channels busy with 802.11 to stop the two systems ruining each other.

### The Bluetooth TDM slot schedule

The master defines a stream of **625 µs slots**. The master starts transmissions in **even slots**, slaves in **odd slots** — classic TDM where the master gets half and the slaves share the other half. Frames are **1, 3, or 5 slots** long, and **hops happen only between frames, never inside one**. Each frame pays a fixed overhead of **126 bits** (access code + header) plus a **250–260 µs settling time** per hop. Because that overhead is constant, a 5-slot frame is far more efficient than a 1-slot frame: same header cost, much more data.

Worked example: a basic-rate SCO frame uses the master's even slots only, giving 800 slots/s in each direction. With an 80-bit payload variant (the most redundant, contents repeated 3×), that is 800 × 80 = 64,000 bits/s — exactly one PCM voice channel.

### The Bluetooth frame and its triple-redundant header

The Bluetooth data frame (Fig. 4-36) is: **72-bit access code** (usually identifies the master so a slave hearing two masters knows which traffic is its own) + **54-bit header** + **0–2744 data bits** at basic rate (up to 8184 at enhanced rate, with a guard/sync field and a 2-bit trailer).

The header is where the cleverness hides. The *logical* header is only **18 bits**: 3-bit Address (which of 8 active devices), 4-bit Type (ACL/SCO/poll/null, FEC kind, slot count), 1-bit Flow (slave's buffer full), 1-bit Acknowledgement (piggyback ACK), 1-bit Sequence (stop-and-wait needs only 1 bit), 8-bit Checksum. Those 18 bits are **transmitted three times** to fill the 54-bit field. The receiver examines all three copies of each bit and takes the **majority vote**. So 54 bits of capacity carry just ~10 bits of real information — the price of reliable delivery from a 2.5 mW radio with almost no compute.

### SCO vs. ACL links and L2CAP

Two link types carry user data:

| Link | Slots | Reliability | Use |
|---|---|---|---|
| SCO (Synchronous Connection Oriented) | Fixed reserved slot each way (up to 3 per slave) | **Never retransmitted**; FEC only | Real-time 64 kbps PCM voice |
| ACL (Asynchronous ConnectionLess) | Whatever is free (1 per slave) | Best-effort, **stop-and-wait ARQ** | Packet data |

ACL data comes from **L2CAP**, which (1) segments upper-layer packets up to 64 KB into frames and reassembles them, (2) multiplexes/demultiplexes sources to RFcomm, service discovery, etc., (3) handles error control and retransmission, and (4) enforces QoS across links. This is why "lost frames" on an SCO voice link are normal — only ACL/L2CAP retransmits. `code/main.py` encodes exactly this SCO-vs-ACL decision so you can test a frame's Type against expected behavior.

## Build It

`code/main.py` is a stdlib-only parser/builder for both header families.

1. **Parse an 802.16 generic header.** Feed the 6 header bytes; the parser unpacks HT/EC/Type/CI/EK/Length/Connection-ID, then computes the 8-bit Header CRC with polynomial x^8 + x^2 + x + 1 and compares it to the stored value.
2. **Detect the frame variant.** The parser branches on the HT bit: HT=0 → generic, HT=1 → bandwidth request (reinterpreting the middle bytes as the 16-bit "bytes needed" field).
3. **Build a frame.** Pass field values and get the packed bytes back, with the Header CRC filled in automatically — useful for crafting test vectors.
4. **Decode a Bluetooth header.** Feed the 18 logical bits (or the 54-bit triple-repeated form) and recover Address/Type/Flow/ARQN/SEQN/Checksum, then apply majority voting on a corrupted copy to show the bit-recovery in action.
5. **Run `main()`** to see all of the above printed for real example frames.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Identify an 802.16 frame variant | Leading HT bit in the first header byte | HT=0 routes to generic decode; HT=1 to bandwidth-request decode |
| Confirm a payload CRC is legitimately absent | CI bit = 0 in the header | You explain that real-time/no-retransmit connections skip CRC by design, not corruption |
| Validate a received 802.16 header | Recomputed Header CRC (x^8+x^2+x+1) vs. stored 8-bit field | Match → header trusted; mismatch → frame discarded before reading Connection ID |
| Classify a Bluetooth link's loss behavior | Type field (SCO vs ACL) in the 18-bit header | SCO loss is expected (FEC, no ARQ); ACL loss triggers stop-and-wait retransmit |
| Recover a corrupted Bluetooth header bit | The three repeated copies of each header bit | Majority vote yields the correct bit; you can show which copy was wrong |

## Ship It

Produce one artifact under `outputs/`:

- A **field-decode cheat sheet** mapping every 802.16 and Bluetooth header bit to its meaning and the symptom a wrong value causes.
- A **runbook** for "missing payload CRC" (802.16) and "SCO frames not retransmitted" (Bluetooth) that distinguishes by-design behavior from real faults.
- The **parser** in `code/main.py`, extended with your own captured frames as test vectors.
- The scaled **frame-layout diagram** at `assets/the-802-16-frame-structure-to-bluetooth-applications.svg`.

Start from `outputs/prompt-the-802-16-frame-structure-to-bluetooth-applications.md` if present.

## Exercises

1. You capture an 802.16 frame whose first header byte is `0x40`. Decode HT, EC, and the start of Type. Is this a generic or bandwidth-request frame, and is the payload encrypted? Verify with `code/main.py`.
2. A real-time voice connection shows MAC frames with no trailing CRC. A teammate files a "data corruption" bug. Using the CI bit and the 802.16 retransmission rule, write the two-sentence reply that closes the bug.
3. Build a bandwidth-request frame asking for 1500 bytes on Connection ID 0x00A3. Hand the field values to the builder, then re-parse the bytes and confirm "bytes needed" reads back as 1500.
4. A piconet has a master, 7 active slaves, and someone wants to add an 8th active device. Explain what must happen first (parking, scatternet, or bridge) and why 7 is the active ceiling.
5. A Bluetooth header arrives with its three copies of one bit reading 1, 0, 1. State the recovered bit and which copy was corrupted. Then explain why stop-and-wait only needs a 1-bit Sequence number.
6. Compute the throughput of a basic-rate SCO link at the 240-bit payload variant (800 slots/s each way). Compare it to the 80-bit variant's 64 kbps and explain the reliability tradeoff.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Header CRC (802.16) | "The frame checksum" | An 8-bit CRC over the *header only* using x^8+x^2+x+1; the *payload* CRC is a separate, optional CRC-32 |
| CI bit | "CRC on/off flag" | Indicator that a full-frame CRC trailer is present; CI=0 is legal for no-retransmit real-time connections |
| Connection ID | "Like a MAC address" | A 16-bit per-connection identifier in a connection-oriented MAC; visible even when payload is encrypted |
| Bandwidth-request frame | "A control packet" | A header-only frame (HT=1) with a 16-bit "bytes needed" field and *no* payload or full-frame CRC |
| Piconet | "A Bluetooth network" | One master + ≤7 active (+255 parked) slaves; a centralized TDM cell with no slave-to-slave links |
| Scatternet | "Mesh Bluetooth" | Multiple piconets joined by a bridge node that participates in more than one |
| 54-bit header (Bluetooth) | "A big header" | 18 logical bits sent 3× with per-bit majority voting; ~10 bits of real info |
| SCO link | "Voice channel" | Fixed-slot, FEC-protected, **never retransmitted** 64 kbps PCM link |
| ACL link | "Data channel" | Best-effort, stop-and-wait ARQ link feeding L2CAP segmentation |
| L2CAP | "Bluetooth's TCP" | Segments ≤64 KB packets into frames, multiplexes to RFcomm/SDP, and does error control + QoS |

## Further Reading

- IEEE Std 802.16-2009 — *Air Interface for Broadband Wireless Access Systems* (the authoritative WiMAX MAC/PHY spec).
- IEEE Std 802.15.1 — Bluetooth radio and baseband (the IEEE-ratified version of the Bluetooth Core).
- Bluetooth Core Specification v4.0 (2009) — defines low-energy operation; later versions for AFH and secure simple pairing.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 4, §4.5.5 (802.16 frame structure) and §4.6 (Bluetooth architecture, applications, link layers, frame structure).
- IEEE 802.3 binary exponential backoff — the same retry algorithm 802.16 reuses for best-effort uplink contention.
- Wireshark display-filter reference (`btle`, `btl2cap`, and WiMAX dissectors) for locating these fields in live captures.
