# ADSL (asymmetric Digital Subscriber Loop)

> ADSL carries IP to the home over the same copper local loop as the analog phone, using a four-layer stack the textbook draws in Fig. 3-26: **IP → PPP → AAL5 → ATM → ADSL physical layer**. The physical layer modulates bits with discrete multitone (DMT / OFDM) and protects them with a Reed-Solomon forward-error-correcting code plus a 1-byte CRC. Above it, ATM chops everything into fixed **53-byte cells** (48-byte payload + 5-byte header) carrying a virtual-circuit identifier, and **AAL5** (ATM Adaptation Layer 5) reassembles those cells into variable-length frames using an 8-byte *trailer* (length + 4-byte CRC-32) and 0-47 bytes of padding so the frame is a whole multiple of 48. **PPPoA** (RFC 2364) defines how PPP rides inside AAL5: only the 1-2 byte PPP Protocol field and the PPP payload go into the AAL5 payload — PPP's own flag bytes and CRC are dropped because ATM/AAL5 already frame and check. The AAL5 CRC-32 is the same polynomial used by Ethernet and PPP, and Wang and Crowcroft (1992) showed it even catches cell reordering. The classic failure mode is a PPPoA payload whose total AAL5 frame length is not a multiple of 48 — segmentation then either pads wrong or drops a cell, and the receiver's length/CRC check in the trailer fails.

**Type:** Build
**Languages:** Python, Wireshark
**Prerequisites:** PPP framing and HDLC-style flags (Phase 4 · 06), CRC error detection (Phase 4 · 03), the idea of layered encapsulation
**Time:** ~75 minutes

## Learning Objectives

- Draw the home-to-DSLAM ADSL protocol stack (IP / PPP / AAL5 / ATM / ADSL physical) and say which device terminates each layer.
- Compute how many 53-byte ATM cells a given IP-over-PPPoA packet requires, including AAL5 padding and the 8-byte trailer, and explain the "cell tax" overhead.
- Lay out the AAL5 trailer fields (PAD, 2-byte length, 4-byte CRC-32) and verify the CRC against the same polynomial Ethernet uses.
- Explain why PPPoA (RFC 2364) strips PPP's flag bytes and FCS but keeps the 1-2 byte Protocol field.
- Identify three real failure modes — wrong VPI/VCI, length/CRC mismatch in the AAL5 trailer, and DMT bit-loading collapse — and the evidence each leaves.

## The Problem

A subscriber calls in: "The phone works fine but the Internet is dead." The line trains up (the DSL modem's sync light is solid), so the ADSL physical layer is alive, yet no IP packets reach the ISP. Where is the break?

ADSL is not one protocol; it is a stack of four, each terminated by a different box. The copper can be perfectly synchronized while the ATM virtual circuit is misconfigured, the PPPoA session never authenticates, or the AAL5 reassembly silently discards every frame because a length field is off by one cell. "It's the line" is rarely the real answer. To diagnose it you have to know exactly which layer owns the symptom — and what evidence each layer leaves in a cell header, an AAL5 trailer, or a PPP LCP exchange. This lesson builds an AAL5/PPPoA segmenter-and-reassembler so you can see those fields directly, then reason about which layer a symptom belongs to.

## The Concept

### The four-layer ADSL stack

The textbook's Fig. 3-26 shows the most common deployment. Inside the home a PC sends IP packets to the DSL modem over Ethernet. The modem encapsulates them and sends them down the local loop to the **DSLAM** (DSL Access Multiplexer) in the telephone company's local office, where the IP packets are extracted and handed to the ISP network.

| Layer | Protocol | Unit | Terminated by | Job |
|---|---|---|---|---|
| Network | IP | Packet | End hosts | Routing across the Internet |
| Link (logical) | PPP | Protocol field + payload | DSL modem ↔ DSLAM/router | Link setup (LCP), auth, IP framing |
| Adaptation | AAL5 | Frame (multiple of 48 B) | DSL modem ↔ DSLAM | Segmentation & reassembly, CRC-32 |
| Link (cell) | ATM | 53-byte cell | ATM switches | Fixed-cell forwarding by VPI/VCI |
| Physical | ADSL (DMT/OFDM) | DMT symbol | Modem ↔ DSLAM line card | Reed-Solomon FEC + 1-byte CRC |

`assets/adsl-asymmetric-digital-subscriber-loop.svg` draws this stack and the encapsulation pipeline from one IP packet down to a row of 53-byte cells.

### ATM: fixed 53-byte cells

ATM (Asynchronous Transfer Mode) is connection-oriented. Every cell carries a **virtual circuit identifier** (a VPI/VCI pair in the 5-byte header) and switches forward cells along an established path using only that identifier — no per-cell addressing. "Asynchronous" means cells are sent only when there is data, unlike SONET's continuous synchronous bit stream.

A cell is exactly **53 bytes**: a 48-byte payload plus a 5-byte header. The small, fixed size lets ATM slice a link into fine time grains so voice samples are not stuck behind a long data packet (low jitter). The odd 48-byte payload is famously political: Europe wanted 32-byte cells, the U.S. wanted 64, and 48 was the deadlock-breaking compromise.

### AAL5: turning packets into cells

ATM only moves cells, so a packet must be mapped into a sequence of cells — **segmentation and reassembly**. For packet data the adaptation layer is **AAL5**. Instead of a header, an AAL5 frame has an 8-byte **trailer**:

```
+------------------+-------+---------+--------+--------+----------+
|  AAL5 payload    |  PAD  | Unused  | Unused | Length |  CRC-32  |
|  (PPP proto +    | 0..47 |  1 byte | 1 byte | 2 byte |  4 byte  |
|   PPP payload)   | bytes |  (UU)   | (CPI)  |        |          |
+------------------+-------+---------+--------+--------+----------+
|<------------ multiple of 48 bytes total -------------------->|
```

The **PAD** (0 to 47 bytes) rounds the whole frame up to a multiple of 48 so it divides evenly into cells. The 2-byte **Length** gives the real payload length (so the receiver can strip the pad). The 4-byte **CRC-32** is computed over the entire frame and is *the same polynomial used by PPP and IEEE 802 LANs like Ethernet* (0x04C11DB7). Wang and Crowcroft (1992) showed this CRC is strong enough to catch nontraditional errors such as cell reordering. No addresses appear in the frame — the per-cell VPI/VCI already steers it.

### PPPoA: PPP inside AAL5 (RFC 2364)

How does PPP ride ATM? Through **PPPoA** (PPP over ATM), RFC 2364. It is less a protocol than a rule for combining PPP and AAL5. Only the PPP **Protocol** field (1 or 2 bytes) and the PPP payload go into the AAL5 payload. The Protocol field tells the DSLAM whether the payload is an IP packet (0x0021) or a control packet such as LCP (0xC021).

Two things PPP normally carries are deliberately *dropped*:

- **PPP flag bytes (0x7E):** ATM and AAL5 already delimit frames, so HDLC-style flag framing would be redundant.
- **PPP FCS (CRC-16):** AAL5's trailer already carries a stronger CRC-32, so PPP's own check is pointless.

This is layering discipline in the wild: never pay twice for framing or error detection. Compare it to packet-over-SONET, where PPP *does* keep its flags and FCS because SONET provides no per-frame check.

### Error control: belt and suspenders

ADSL is a far noisier channel than a fiber SONET link, so it uses two distinct mechanisms at different layers:

- **Physical layer:** a **Reed-Solomon** forward-error-correcting code *fixes* bit errors in flight, plus a **1-byte CRC** to detect anything Reed-Solomon missed. This is *correction* — no retransmission needed for most noise.
- **AAL5 layer:** the **4-byte CRC-32** *detects* (does not correct) residual frame corruption, including reordering. A failed AAL5 CRC drops the whole frame; recovery, if any, is left to higher layers (TCP).

### Worked example: cell tax on one IP packet

Take a 100-byte IP packet sent over PPPoA with a 2-byte PPP Protocol field.

1. AAL5 payload = 2 (PPP proto) + 100 (IP) = **102 bytes**.
2. Trailer is 8 bytes; payload + trailer = 102 + 8 = 110 bytes.
3. Round 110 up to a multiple of 48 → **144 bytes** (so PAD = 144 − 110 = **34 bytes**).
4. 144 / 48 = **3 ATM cells**, i.e. 3 × 53 = **159 bytes on the wire**.

Efficiency = 100 useful IP bytes / 159 wire bytes ≈ **63%**. The remaining 37% is "cell tax" — ATM/AAL5 overhead plus padding. `code/main.py` computes exactly this for any packet size and prints the cell layout and CRC-32.

## Build It

1. Read `code/main.py`. It implements `aal5_encapsulate()` (builds the PPPoA payload, appends pad + 8-byte trailer with a real CRC-32), `segment_into_cells()` (splits into 48-byte ATM payloads and prepends a 5-byte header with a VPI/VCI), and `reassemble()` (the inverse, validating length and CRC).
2. Run it: `python3 code/main.py`. Watch it encapsulate a sample IP packet, print every 53-byte cell in hex, then reassemble and verify.
3. Change the packet size near the top of `main()` and re-run. Confirm the cell count and efficiency match the worked example above.
4. Flip one byte in the cell stream (uncomment the corruption line) and confirm the AAL5 CRC check fails on reassembly — that is exactly the trailer-CRC failure mode.
5. In Wireshark, open a PPPoA or ATM capture (or the supplied sample) and apply the display filter `atm` or `ppp`; map the VPI/VCI and PPP Protocol field you see to the fields the code prints.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm the physical layer is up | Modem sync/train state, DMT bit-loading, line attenuation/SNR margin | Sync solid but no IP → fault is above the physical layer |
| Verify the ATM virtual circuit | VPI/VCI in cell headers (Wireshark `atm.vpi`, `atm.vci`) | Cells use the VPI/VCI the ISP provisioned; wrong pair = no reassembly |
| Validate AAL5 reassembly | AAL5 trailer Length and CRC-32 | Length equals real payload; CRC matches; frame is a multiple of 48 B |
| Check the PPP session | LCP/IPCP exchange, PPP Protocol field (0xC021 / 0x0021) | LCP reaches Opened, IPCP assigns an IP; auth (PAP/CHAP) succeeds |

## Ship It

Produce one artifact under `outputs/`:

- The AAL5/PPPoA segmenter-reassembler from `code/main.py`, extended to read a real packet capture.
- A one-page runbook mapping each symptom ("sync but no IP", "high retrains", "auth fails") to the layer and the field that proves it.
- A cell-tax calculator table for common MTU sizes (576, 1492, 1500 bytes).

Start from [`outputs/prompt-adsl-asymmetric-digital-subscriber-loop.md`](../outputs/prompt-adsl-asymmetric-digital-subscriber-loop.md).

## Exercises

1. A subscriber's line trains at full rate (sync light solid) but no web pages load and `ping` to the ISP gateway fails. Which layers are confirmed working, and what are the two most likely failing layers? Name the field you'd inspect for each.
2. Compute the on-the-wire bytes and efficiency for a full 1500-byte IP packet over PPPoA (2-byte Protocol field). How many ATM cells, and how many pad bytes in the last cell's AAL5 frame?
3. An ISP provisions VPI/VCI = 8/35 but the modem is configured for 0/35. The line syncs. Describe precisely what happens to the cells at the DSLAM and why no AAL5 frame is ever reassembled.
4. Explain why PPPoA drops PPP's flag bytes and FCS but packet-over-SONET keeps them. What property does SONET lack that ATM/AAL5 provides?
5. Corrupt one byte of an AAL5 payload so the CRC-32 fails but the Length field still parses. Trace what the receiver does and at which layer recovery (if any) happens.
6. The 48-byte ATM payload was a political compromise between 32 and 64. Recompute the efficiency of the 100-byte-IP example if cells had been 32-byte or 64-byte payloads. Which would have lowered the cell tax here, and why isn't that always true?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| ADSL | "home DSL Internet" | A four-layer stack (IP/PPP/AAL5/ATM/DMT) over the analog phone local loop; asymmetric = faster downstream |
| DSLAM | "the box at the exchange" | DSL Access Multiplexer; terminates ADSL/ATM, extracts IP, hands it to the ISP |
| ATM cell | "tiny fixed packet" | Exactly 53 bytes: 48 payload + 5 header carrying a VPI/VCI virtual-circuit identifier |
| AAL5 | "how packets become cells" | Adaptation layer with an 8-byte *trailer* (PAD + Length + CRC-32), frame sized to a multiple of 48 |
| PPPoA | "PPP for DSL" | RFC 2364 rule putting only PPP Protocol + payload in AAL5; drops PPP flags and FCS |
| VPI/VCI | "the circuit number" | Virtual Path/Channel Identifier in the cell header; switches forward by it, no per-cell addressing |
| Cell tax | "ATM overhead" | Header + AAL5 trailer + padding; ~37% on a 100-byte packet, the price of fixed cells |
| DMT / OFDM | "the modulation" | Discrete multitone: many sub-carriers, each bit-loaded to its own SNR; Reed-Solomon FEC on top |

## Further Reading

- A. S. Tanenbaum & D. J. Wetherall, *Computer Networks*, 5th ed., §3.5.2 (ADSL) and §2.5.3 (DSL physical layer).
- RFC 2364 — *PPP over AAL5* (Gross et al., 1998): the PPPoA specification.
- RFC 1662 — *PPP in HDLC-like Framing*: the flag/FCS framing PPPoA deliberately omits.
- ITU-T G.992.1 / G.992.5 — ADSL and ADSL2+ physical layer (DMT, Reed-Solomon FEC, bit loading).
- ITU-T I.363.5 — the AAL5 specification (trailer format, CRC-32, segmentation and reassembly).
- Wang & Crowcroft (1992) — analysis showing the AAL5 CRC-32 detects cell reordering.
- Siu & Jain (1995) — a concise overview of ATM.
