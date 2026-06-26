# Services to The 802.16 Architecture and Protocol Stack

> IEEE 802.16 (WiMAX) is the broadband-wireless cousin of 802.11, but its MAC is built like a cable-modem network: **connection-oriented**, **point-to-multipoint**, and **scheduled by the base station** instead of contended with CSMA/CA. The base station owns the air: every 5 ms (typical) it broadcasts a **DL-MAP** and **UL-MAP** that tell each subscriber station which OFDMA subcarriers and time symbols it may use, so collisions are designed out of the steady state. The data-link layer splits into three sublayers — a **service-specific convergence sublayer** that maps connectionless IP onto connections, a **MAC common part sublayer** carrying the generic 6-byte header with its 16-bit **Connection ID (CID)**, and a **security sublayer** that does mutual RSA/X.509 authentication and AES-CCM payload encryption (headers stay in the clear). Four QoS classes — UGS, rtPS, nrtPS, and BE — decide whether a connection gets standing grants, periodic polls, or has to contend. Bandwidth requests use a stripped 6-byte header, and best-effort contention falls back to the same **binary exponential backoff** Ethernet uses. The header CRC is computed with the 8-bit polynomial x⁸+x²+x+1; the payload CRC is the optional standard IEEE 802 CRC-32. This lesson builds a parser/scheduler in `code/main.py` that constructs both frame types, walks the QoS grant logic, and lays out a TDD/OFDMA frame.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib)
**Prerequisites:** 802.11 MAC and services lessons in Phase 06; OFDM and QAM from the physical-layer phase; binary exponential backoff from the Ethernet lessons
**Time:** ~75 minutes

## Learning Objectives

- Draw the three-sublayer 802.16 data-link stack (convergence, MAC common part, security) and state what each one does, in particular why the convergence sublayer exists at all.
- Decode the 802.16 generic MAC header field-by-field (EC, Type, CI, EK, Length, CID, HCS) and contrast it with the 6-byte bandwidth-request header.
- Explain why the base station's DL-MAP / UL-MAP scheduling replaces CSMA/CA, and trace one TDD frame from preamble to ranging slot.
- Assign a connection to the correct QoS class (UGS, rtPS, nrtPS, BE) and predict whether it receives standing grants, periodic polling, or contention-based access.
- Identify the evidence (CID, grant type, backoff window, HCS failures) that proves normal vs. abnormal behavior on the uplink.

## The Problem

A wireless ISP runs a WiMAX cell serving 40 rooftop subscriber stations plus a handful of moving vehicles. One subscriber complains that their VoIP calls break up exactly when somebody on the same tower starts a large upload, while their neighbor's identical hardware is fine. With 802.11 you'd reach for "channel congestion / collisions" and a spectrum analyzer. But 802.16 has *no contention in steady state* — the base station hands out every uplink opportunity explicitly. So the symptom can't be a collision; it has to be a **scheduling or QoS-provisioning** problem: the VoIP connection was set up as best-effort instead of UGS, or its grants are being starved by a higher-weight connection.

To diagnose this you cannot stay at the IP layer. You have to think in terms of *connections* (each with a 16-bit CID and a service class), *grants* (bursts of subcarriers reserved in the UL-MAP), and the *generic MAC header* that ties a frame to its connection. This lesson gives you the field layouts and the decision logic to reason about exactly that.

## The Concept

Source material: `chapters/chapter-04-the-medium-access-control-sublayer.md`, sections 4.5.2–4.5.5. The architecture and protocol-stack diagram is reproduced in [`assets/services-to-the-802-16-architecture-and-protocol-stack.svg`](../assets/services-to-the-802-16-architecture-and-protocol-stack.svg).

### The architecture: base stations own everything

802.16 is **point-to-multipoint**. A **base station (BS)** connects directly to the provider's backbone (and thence the Internet) and talks to two kinds of stations over the air interface:

- **Subscriber stations (SS)** — fixed location, e.g. a rooftop antenna for home broadband ("Fixed WiMAX", 802.16a, OFDM, 2003).
- **Mobile stations (MS)** — receive service while moving, e.g. a car ("Mobile WiMAX", 802.16e, Scalable OFDMA, 2005).

Because the spectrum is **licensed** (typically ~2.5 GHz in the U.S., or 3.5 GHz, anywhere in 2–11 GHz) and expensive, the system is heavily optimized: nothing is "left to chance with CSMA/CA, which may waste capacity with collisions." The BS schedules **downlink** (BS→SS) *and* **uplink** (SS→BS) explicitly. This is the cable-modem model — one headend driving many modems — applied to radio.

### Three data-link sublayers

| Sublayer | Replaces (in 802.11) | Job |
|---|---|---|
| **Service-specific convergence** | LLC sublayer | Interface to the network layer. Maps **connectionless IP** (also Ethernet, ATM) onto **connection-oriented** 802.16 connections — i.e. address ⇄ CID mapping. |
| **MAC common part (CPS)** | MAC | The real protocols: connection management, scheduling, fragmentation/packing, the generic header and CID. |
| **Security** | (no direct equivalent) | Mutual RSA authentication with X.509 certificates; payload encryption with AES (Rijndael) or DES-CBC; integrity with SHA-1. **Only payloads are encrypted, headers are not** — a snooper sees *who* talks to *whom* but not *what*. |

The convergence sublayer is the conceptually interesting one: IP is connectionless, the 802.16 MAC is connection-oriented, so *something* must translate between IP addresses/flows and CIDs. That's it.

### The OFDMA / TDD frame

Mobile WiMAX uses **OFDMA** (Orthogonal Frequency Division Multiple *Access*): different sets of subcarriers go to different stations, so several stations send or receive at once. (Contrast 802.11, where one station owns *all* subcarriers at any instant.) A subcarrier that is faded at one receiver due to multipath may be clear at another, so the BS assigns each subcarrier to the station that can use it best.

Duplexing is usually **TDD** (Time Division Duplex): the cell alternates downlink and uplink in time. The frame structure (Fig. 4-32, reproduced in the SVG) repeats over time:

```
| Preamble | DL-MAP | UL-MAP | DL bursts ... | Guard | UL bursts ... | Ranging |
  ^sync      ^who gets what     ^BS→SS data     ^Tx/Rx  ^SS→BS data     ^new SS
             on DL and UL                        turnaround            joins here
```

1. **Preamble** synchronizes all stations.
2. **DL-MAP / UL-MAP** tell every station which subcarriers and symbols it owns *this frame*. The BS rewrites the maps frame-by-frame, so allocation tracks each station's needs.
3. **Downlink bursts** carry BS→SS traffic at the positions the DL-MAP named.
4. **Guard time** lets stations switch from receive to transmit.
5. **Uplink bursts** carry SS→BS traffic in the reserved UL-MAP positions.
6. **Ranging slot** — a reserved uplink burst where a *new* station adjusts timing and requests initial bandwidth. No connection exists yet, so it "just transmits and hopes there is no collision." This is the *only* place 802.16 behaves like contention.

Modulation per subcarrier adapts to SNR: **QAM-64** (6 bits/symbol) near the BS with high SNR, down to **QPSK** (2 bits/symbol) for distant low-SNR stations, with **QAM-16** in between. Data is convolutional-coded for FEC. Net per 5-MHz channel and antenna pair: up to **12.6 Mbps downlink, 6.2 Mbps uplink**. A 5-MHz mobile channel uses 512 subcarriers with ~100 µs symbol time.

### The four QoS classes (uplink scheduling)

The downlink is easy — the BS just packs frames into bursts it already controls. The **uplink** is where QoS lives, because subscribers compete for it. Every connection is assigned one class at setup:

| Class | Full name | How the BS grants bandwidth | Typical traffic |
|---|---|---|---|
| **UGS** | Constant bit rate (Unsolicited Grant) | Standing bursts dedicated automatically every interval — **no request needed** | Uncompressed voice / T1-style CBR |
| **rtPS** | Real-time variable bit rate | BS **polls at a fixed interval** asking "how much do you need now?" | Compressed video, soft real-time |
| **nrtPS** | Non-real-time variable bit rate | BS polls **often but not on a rigid schedule**; may also use BE contention | Large file transfers |
| **BE** | Best-effort | **No polling** — station contends in slots marked contention-available in the UL-MAP | Web, email, everything else |

For **best-effort**, a station sends a bandwidth request in a contention slot. Success is announced in the next DL-MAP; failure means retry later. To minimize collisions on these contention slots, 802.16 reuses the **Ethernet binary exponential backoff** algorithm: after a collision, double the backoff window and pick a random slot within it.

This is the heart of the opening problem: a VoIP flow on **BE** contends and gets starved during an upload; the same flow on **UGS** gets standing grants and is immune. The fix is provisioning, not RF.

### The generic MAC frame header

Every MAC frame begins with a **6-byte generic header**, optionally followed by a payload and an optional CRC (Fig. 4-33a). Control frames (like channel requests) need no payload; the payload CRC is optional because the PHY already does FEC and real-time frames are never retransmitted.

Generic header fields (bit widths from Fig. 4-33a):

| Field | Bits | Meaning |
|---|---|---|
| **HT** | 1 | Header type. `0` = generic. |
| **EC** | 1 | Encryption Control — is the payload encrypted? |
| **Type** | 6 | Frame type flags — mostly whether **packing** and **fragmentation** are present. |
| **(rsv)** | 1 | reserved |
| **CI** | 1 | CRC Indicator — is the optional payload CRC present? |
| **EK** | 2 | Encryption Key index — which key (if any). |
| **(rsv)** | 1 | reserved |
| **Length** | 11 | Total frame length **including the header**. |
| **Connection ID (CID)** | 16 | Which connection this frame belongs to. |
| **HCS** | 8 | Header Check Sequence — CRC over the **header only**, polynomial **x⁸ + x² + x + 1**. |

If a payload CRC is present it is the standard IEEE 802 **CRC-32**, and then acknowledgements and retransmissions are used for reliability.

### The bandwidth-request header

A connection that needs uplink capacity sends a **bandwidth-request frame** (Fig. 4-33b) — a 6-byte header with *no payload*:

| Field | Bits | Meaning |
|---|---|---|
| **HT** | 1 | Header type. `1` = bandwidth request. |
| **EC** | 1 | `0` (request headers are not encrypted). |
| **Type** | 6 | Request type (aggregate vs. incremental). |
| **Bytes needed** | 16 | How many bytes of uplink the connection is requesting. |
| **Connection ID (CID)** | 16 | Which connection the grant is for. |
| **HCS** | 8 | Same header CRC, x⁸+x²+x+1. |

The HT bit (`0` generic / `1` request) is the first thing a parser branches on — see `code/main.py`, which dispatches on it before decoding the rest.

## Build It

`code/main.py` is a stdlib-only 802.16 MAC toolkit. To work through the mechanism:

1. **Build a generic header.** Call `build_generic_header(cid=0x1A2B, length=48, encrypted=True, crc_present=True)` and print the 6 bytes. Confirm bit 0 is `0` (generic) and the last byte is the HCS.
2. **Verify the HCS.** `header_check_sequence(first5bytes)` computes the CRC-8 with polynomial 0x07 (x⁸+x²+x+1). Flip one bit in the header and watch the HCS change — that's how a receiver detects a corrupt header.
3. **Build a bandwidth request.** `build_bandwidth_request(cid=0x1A2B, bytes_needed=1500)` produces the 6-byte HT=1 frame. Notice there is no payload.
4. **Round-trip parse.** Feed either frame back into `parse_header(raw)` and confirm every field decodes to what you put in.
5. **Run the scheduler.** `schedule_uplink(connections)` walks the four QoS classes and prints, per connection, whether it gets a standing grant (UGS), a poll (rtPS/nrtPS), or must contend (BE) — and applies binary exponential backoff to the BE collisions.

Run it: `python3 code/main.py`.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm a frame belongs to a connection | Generic header CID field (16 bits) | The CID matches the connection set up at admission; convergence sublayer mapped this IP flow to that CID |
| Decide why VoIP breaks under load | Connection's QoS class + UL-MAP grant type | VoIP is UGS with standing grants; if it's BE, that's the bug — reprovision |
| Detect header corruption | HCS recomputed over header bytes vs. transmitted HCS | Recomputed CRC-8 (poly 0x07) equals the received HCS; mismatch ⇒ drop the frame |
| Explain a slow best-effort uplink | Contention slots in UL-MAP + backoff window growth | Repeated collisions double the backoff window (Ethernet BEB); not a hardware fault |
| Distinguish data vs. request frame | Header Type bit (HT, bit 0) | HT=0 generic carries payload; HT=1 is a pure bandwidth request, no payload |

## Ship It

Produce one artifact under `outputs/`:

- A **frame-decode cheat sheet** mapping every generic-header and bandwidth-request bit to its meaning and width.
- A **QoS provisioning runbook**: given an application (VoIP, video, FTP, web), which class to assign and what grant behavior to expect.
- The **TDD/OFDMA frame diagram** annotated with where ranging, maps, and guard time live.

Start from [`outputs/prompt-services-to-the-802-16-architecture-and-protocol-stack.md`](../outputs/prompt-services-to-the-802-16-architecture-and-protocol-stack.md).

## Exercises

1. A subscriber's VoIP degrades only when a neighbor uploads a large file. Both connections terminate at the same BS. Using the QoS table, explain which class each connection is probably in, why the VoIP suffers, and the exact provisioning change that fixes it without touching RF.
2. You capture a 6-byte header `0x00 ...` with HT=0 but the Length field reads `3`. Is that plausible for a generic frame? Compute the minimum legal Length and explain what a Length smaller than the header implies.
3. Take a generic header, flip the most significant bit of the CID, and recompute the HCS with `header_check_sequence`. By how many bits does the HCS differ? What does that tell you about the polynomial x⁸+x²+x+1 as an error detector for single-bit header errors?
4. A new mobile station powers on inside the cell. Walk it through the TDD frame: which slot does it use first, why is that the only place collisions can occur, and what does it request there?
5. Two best-effort stations both send bandwidth requests in the same contention slot and collide. Show the backoff window for each over three consecutive collisions under binary exponential backoff, and explain why this is borrowed from Ethernet rather than invented for WiMAX.
6. Argue why the 802.16 designers made the payload CRC *optional* but the header HCS *mandatory*. Tie your answer to FEC at the PHY and the no-retransmit policy for real-time frames.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Connection ID (CID) | "the WiMAX address" | A 16-bit identifier for a *connection*, not a station. The convergence sublayer maps IP flows to CIDs; one station can hold many CIDs with different QoS classes. |
| DL-MAP / UL-MAP | "the schedule" | Per-frame broadcasts telling every station exactly which subcarriers/symbols it owns this frame; this is what replaces CSMA/CA. |
| UGS | "the voice class" | Unsolicited Grant Service — standing bursts delivered automatically every interval with no bandwidth request, for constant-bit-rate traffic. |
| rtPS / nrtPS | "the polling classes" | BS polls the connection (fixed interval for rtPS, loose interval for nrtPS) to ask how much it needs; for variable-rate real-time and non-real-time traffic. |
| Ranging | "joining the network" | The one contention slot where a new station with no connection adjusts timing and asks for initial bandwidth — the only steady-state place collisions can happen. |
| HCS | "the header checksum" | Header Check Sequence: an 8-bit CRC over the header only using polynomial x⁸+x²+x+1; mandatory even when the payload CRC is omitted. |
| Convergence sublayer | "the top MAC layer" | The shim that bridges connectionless IP to the connection-oriented 802.16 MAC by mapping addresses to CIDs. |
| TDD | "time-sharing the channel" | Time Division Duplex: downlink and uplink alternate in time on the same frequencies; preferred in WiMAX over FDD for flexibility. |

## Further Reading

- **IEEE Std 802.16-2009**, *Air Interface for Broadband Wireless Access Systems* — the consolidated standard (fixed + mobile WiMAX).
- **IEEE Std 802.16e-2005** — Mobile WiMAX amendment introducing Scalable OFDMA.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 4, §4.5 "Broadband Wireless" (4.5.2 architecture/stack, 4.5.3 PHY, 4.5.4 MAC, 4.5.5 frame structure).
- Andrews, Ghosh & Muhamed, *Fundamentals of WiMAX* (Prentice Hall, 2007) — deep treatment of OFDMA scheduling and QoS.
- **RFC 5121** — *Transmission of IPv6 via the IPv6 Convergence Sublayer over IEEE 802.16 Networks* — a real-world convergence-sublayer mapping.
- **ITU-T X.509** — the certificate format used for 802.16 mutual authentication.
- Wireshark display-filter reference (`wimax`, `wmx`) for annotating captured 802.16 MAC frames.
</content>
</invoke>
