# PPP Framing and LCP over SONET

> SONET hands a router a continuous, clocked bitstream organized as 810-byte frames recurring every 125 µs (e.g. OC-48 at 2.488 Gbps); it carries no notion of "packet start" or "packet end." **PPP** (Point-to-Point Protocol, RFC 1661) supplies the missing framing using the HDLC flag byte `0x7E`, byte-stuffs any `0x7E`/`0x7D` inside the payload via the escape byte `0x7D` plus `XOR 0x20`, and ends each frame with a 2- or 4-byte **CRC** (the 32-bit CRC-32, same polynomial as Ethernet, is mandatory over SONET per **RFC 2615**). The fixed Address `0xFF` and Control `0x03` fields mark an unnumbered, connectionless frame — PPP over SONET almost never runs the RFC 1663 reliable mode with sliding windows. Before data flows, peers run the **Link Control Protocol (LCP)** to negotiate options (ACFC, PFC, MRU, authentication), then move through the DEAD → ESTABLISH → AUTHENTICATE → NETWORK → OPEN state machine, and finally exchange **NCP** packets (e.g. IPCP, RFC 5072) to assign IP addresses. Because SONET clock recovery needs bit transitions, RFC 2615 also mandates **payload scrambling** with the x^7+x^6+1 polynomial so a user cannot send a long run of 0s and desync the line. This lesson builds a runnable PPP-over-SONET frame encoder/decoder with byte-stuffing, CRC-32 verification, and a tiny LCP option-negotiation simulator so you can see the exact bytes and state transitions these protocols leave behind.

**Type:** Project
**Languages:** Python, packet traces
**Prerequisites:** Framing and byte stuffing (Phase 3 earlier lessons), CRC error detection, SONET/physical-layer bitstream concepts
**Time:** ~80 minutes

## Learning Objectives

- Dissect a PPP frame field-by-field: Flag, Address, Control, Protocol, Payload, FCS, Flag — and state the default size and value of each.
- Apply the byte-stuffing rule (`0x7D` escape, `XOR 0x20`) to encode and decode a payload that itself contains `0x7E` or `0x7D`, and prove a receiver can find frame boundaries by scanning for `0x7E` alone.
- Trace the LCP option negotiation (Configure-Request/Ack/Nak/Reject) and the DEAD→ESTABLISH→AUTHENTICATE→NETWORK→OPEN→TERMINATE state machine.
- Compute the on-wire byte overhead of a PPP frame over SONET (4-byte FCS, uncompressed Address/Control/Protocol) versus a compressed frame, and justify why RFC 2615 says "don't compress."
- Explain why SONET mandates payload scrambling (x^7+x^6+1) and what failure mode (loss of clock / long run of zeros) it prevents.
- Distinguish the 2-byte CRC-16 from the 4-byte CRC-32 FCS, and identify which PPP-over-SONET uses and why.

## The Problem

A backbone operator lights up an OC-48 link between two core routers — 2.488 Gbps of pristine synchronous bitstream, 810-byte SONET frames every 125 µs, all day every day. The routers need to push IPv4 and IPv6 packets across it. But SONET itself has no concept of "here starts a packet" or "here ends one" — it just delivers bits. Worse, if a user sends a packet that is mostly zeros, the SONET framer's phase-locked loop can drift and lose byte alignment, taking the whole link down. The operator needs: (1) a framing method that unambiguously delimits variable-length packets inside that bitstream, (2) a way to detect when the optical path corrupts a frame, (3) a control protocol to bring the link up, agree on options, authenticate, and tear it down cleanly, and (4) a guarantee that no packet a user can construct will starve the line of transitions. PPP over SONET (the "Packet over SONET" or POS stack) is the standard answer, specified across RFC 1661 (PPP), RFC 1662 (HDLC-like framing), and RFC 2615 (PPP over SONET/SDH).

## The Concept

### The PPP frame format (RFC 1662, HDLC-like)

PPP borrows HDLC's frame shape but is **byte-oriented** (all frames are an integral number of bytes; HDLC is bit-oriented and can have "30.25-byte" frames). The full frame in unnumbered mode, default (uncompressed) form:

| Field | Default size | Default value | Meaning |
|---|---|---|---|
| Flag | 1 byte | `0x7E` | Frame delimiter; scan for this to find boundaries |
| Address | 1 byte | `0xFF` | "All stations accept" — avoids assigning data-link addresses on a point-to-point link |
| Control | 1 byte | `0x03` | Unnumbered frame (no sequence numbers, no ACK) |
| Protocol | 2 bytes | varies | Identifies the payload: `0x0021` = IPv4, `0x0057` = IPv6, `0xC021` = LCP, `0x80FD` = CCP, `0x002B` = IPX … |
| Payload | variable | up to MRU (default 1500) | The carried packet; may be padded |
| FCS | 2 or 4 bytes | CRC | Frame Check Sequence — CRC-16 by default, CRC-32 over SONET |
| Flag | 1 byte | `0x7E` | End of frame (also serves as next frame's start flag) |

A leading `0` bit in the Protocol field marks a network-layer protocol (IP, IPX); a leading `1` bit marks a PPP control protocol (LCP, NCP, CCP). Only one flag byte is needed between consecutive frames; idle links fill with repeated `0x7E` flags.

### Byte stuffing: keeping `0x7E` sacred

The whole framing scheme collapses if `0x7E` can appear inside the payload — the receiver could not tell a real frame boundary from data. PPP solves this with **byte stuffing**:

- The escape byte is `0x7D`.
- Any byte `b` in the payload (and FCS) equal to `0x7E`, `0x7D`, or any byte below `0x20` is transmitted as the two bytes `0x7D (b XOR 0x20)`.
- Example: a payload byte `0x7E` is sent as `0x7D 0x5E` (since `0x7E XOR 0x20 = 0x5E`). A payload byte `0x7D` is sent as `0x7D 0x5D`.

The destuffing rule is symmetric: on seeing `0x7D`, drop it and `XOR` the next byte with `0x20`. Because both the flag and the escape are neutralized, a receiver can locate frame boundaries reliably by scanning for a bare, unescaped `0x7E`. `code/main.py` implements `stuff()` and `unstuff()` exactly this way and includes a worked example where the payload itself contains `0x7E 0x7D 0x00`.

### Why unnumbered mode and no retransmission

HDLC classically provides reliable service: sequence numbers, a sliding window, ACKs, timeouts. PPP *can* do this (RFC 1663, "PPP Reliable Transmission"), but on SONET it almost never does. SONET is a clean optical channel with bit-error ratios around 10^-12; retransmitting at the link layer would duplicate work the transport layer already does, and the sliding-window state would cap throughput far below OC-48 line rate. So PPP over SONET runs in **unnumbered mode**: Address `0xFF`, Control `0x03`, no sequence numbers, no ACKs, no retransmission. Corrupted frames are silently dropped by the FCS check and left for TCP to recover end-to-end. This is the "connectionless, unacknowledged" service the textbook describes.

### FCS: CRC-16 versus CRC-32

The FCS is the *only* error-detection mechanism over the optical, data-link, and network layers on a POS link, so RFC 2615 mandates the **4-byte CRC-32** (generator polynomial 0x04C11DB7, the same one used in Ethernet and AAL5). The shorter 2-byte CRC-16 (the "industry-standard" CRC) is permitted on noisier低速 links but is not strong enough for the high data rates and long frames on SONET. Crucially, the FCS is computed over the *unstuffed* Address+Control+Protocol+Payload bytes and then *itself* is stuffed before transmission — `code/main.py` shows this two-step: compute CRC-32 over the raw frame body, append it, then stuff the whole thing.

| FCS variant | Size | Polynomial | Used over SONET? | Notes |
|---|---|---|---|---|
| CRC-16 | 2 bytes | 0x8408 (reflected) | No (too weak at high rate) | Default on low-speed PPP links |
| CRC-32 | 4 bytes | 0x04C11DB7 | **Yes — mandatory (RFC 2615)** | Same as Ethernet/AAL5; detects reordering |

### LCP: bringing the link up

The **Link Control Protocol** (Protocol field `0xC021`) rides inside PPP frames and runs a classic request/ack option negotiation. LCP packet types:

| Type | Code | Purpose |
|---|---|---|
| Configure-Request | 1 | "I want these options" — proposes a set |
| Configure-Ack | 2 | "I accept all of them" |
| Configure-Nak | 3 | "These values are wrong, try these instead" |
| Configure-Reject | 4 | "I don't recognize/support these options at all" |
| Terminate-Request | 5 | "Take the link down gracefully" |
| Terminate-Ack | 6 | "Acknowledged, going down" |
| Code-Reject / Protocol-Reject | 7 / 8 | "You sent something I don't understand" |
| Echo-Request / Echo-Reply | 9 / 10 | Link-quality / keepalive probe |

Common LCP options negotiated at ESTABLISH:

| Option | ID | Effect |
|---|---|---|
| MRU (Maximum-Receive-Unit) | 1 | Sets max payload (default 1500); backbone links often negotiate 4470 to match classical IP over ATM |
| ACFC (Address-and-Control-Field-Compression) | 8 | Drop the constant `0xFF 0x03` — saves 2 bytes/frame |
| PFC (Protocol-Field-Compression) | 7 | Shrink Protocol from 2 bytes to 1 when it fits in `0x00`–`0xFF` |
| Authentication-Protocol | 3 | Demand PAP (0xC023) or CHAP (0xC022) before NETWORK |
| Magic-Number | 5 | Random value to detect looped links |

RFC 2615 explicitly recommends **against** ACFC and PFC on SONET: at OC-48 the 2–3 bytes saved per frame is negligible, and uncompressed fields keep framers and analyzers simple. `code/main.py`'s `lcp_negotiate()` simulates a Configure-Request/Ack exchange and reports which options survive.

### The PPP state machine

Before any IP packet crosses the SONET line, the link walks this state machine (textbook Fig. 3-25):

| Transition | Trigger | What happens |
|---|---|---|
| DEAD → ESTABLISH | Carrier detected (SONET path comes up) | Peers exchange LCP Configure-Request/Ack to settle options |
| ESTABLISH → AUTHENTICATE | LCP negotiation succeeds | Optional PAP/CHAP exchange; if no auth configured, pass through |
| AUTHENTICATE → NETWORK | Auth succeeds (or skipped) | NCP packets configure the network layer — for IP, IPCP negotiates local/remote IP addresses |
| NETWORK → OPEN | NCP configuration done | Data transport begins: IP packets carried in PPP frames |
| OPEN → TERMINATE | LCP Terminate-Request or carrier loss | Clean shutdown |
| TERMINATE → DEAD | Physical layer dropped | Link is gone |

The DEAD state is literal: there is no physical-layer connection. On a POS link, "carrier detected" means the SONET framer has achieved frame and pointer alignment and is passing a valid byte stream up. If LCP negotiation fails (a Configure-Reject war with no convergence), the link falls back from ESTABLISH to TERMINATE rather than forward misconfigured traffic.

### Scrambling: why SONET needs the payload randomized

SONET receivers recover clock from bit transitions in the stream. Voice traffic transitions naturally, but a data packet can be a long run of zeros — enough to make the PLL drift and lose byte alignment. RFC 2615 therefore requires the entire PPP frame (between the flags) to be **scrambled** with the ITU-T x^7+x^6+1 polynomial (a self-synchronous scrambler) before insertion into the SONET SPE (Synchronous Payload Envelope). Scrambling XORs the data with a long pseudo-random sequence, making the probability of a pathological run vanishingly small. The descrambler at the far end inverts the operation. Without this, a single all-zero packet from a user could crash a 2.4 Gbps link — a genuinely catastrophic user-triggerable failure. The SVG (`assets/ppp-over-sonet.svg`) shows where scrambling sits in the encode/decode pipeline.

### Worked example: a 20-byte IPv4 packet on the wire

Take a 20-byte IPv4 header (no payload) as the PPP payload. Over SONET with default (uncompressed, 4-byte FCS) settings, the frame body *before byte-stuffing* is:

- Flag `7E` (1) + Address `FF` (1) + Control `03` (1) + Protocol `0021` (2) + Payload (20) + FCS-32 (4) + Flag `7E` (1) = **30 bytes** for 20 bytes of IP, a 50% overhead on a tiny packet.

A real IPv4 header is full of `0x00` bytes, and RFC 1662 stuffs *every* byte below `0x20`, so the actual on-wire count grows. `code/main.py` uses a header containing `0x7E`, `0x7D`, and several `0x00` bytes and the stuffed frame comes out to 50 bytes — that is the stuffing overhead, not framing overhead. Negotiate ACFC+PFC on a *low-speed* link with a payload that has no stuffable bytes and the same 20-byte packet shrinks to `7E` + Protocol(1) + Payload(20) + FCS-16(2) + `7E` = 25 bytes. On SONET you keep the uncompressed form because the constant-field savings is noise against OC-48 and the robustness matters more. For a realistic 1500-byte packet the constant-field overhead drops to ~0.8% (the demo prints exactly 0.80% for CRC-32 uncompressed), which is why those fields are not worth removing.

## Build It

1. Read `code/main.py`. It implements `stuff()`, `unstuff()`, `crc32_ppp()`, `build_frame()`, `parse_frame()`, `lcp_negotiate()`, and a `pos_encode_pipeline()` that chains body-build → CRC → stuff → (notional) scramble.
2. Run it: `python3 code/main.py`. You should see a 20-byte IPv4 packet encoded to a 30-byte stuffed PPP frame, the FCS-32 printed, and a successful round-trip parse that recovers the original bytes.
3. Inspect the stuffed output: confirm the in-payload `0x7E` became `0x7D 0x5E` and `0x7D` became `0x7D 0x5D`. Flip one payload bit before parsing and watch `parse_frame()` raise a CRC mismatch.
4. Run the LCP simulator block: it prints a Configure-Request proposing MRU=4470, ACFC, PFC, Magic-Number, and the Configure-Ack that survives (note RFC 2615 would *reject* ACFC/PFC on a real POS link — the simulator flags this).
5. Open `assets/ppp-over-sonet.svg` and trace the encode pipeline: IP → PPP body → CRC-32 → byte-stuff → scramble → SONET SPE.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Encode a PPP frame | Hex dump of Flag+Addr+Ctrl+Protocol+Payload+FCS+Flag with FCS-32 correct | A 20-byte IP packet yields exactly 30 on-wire bytes over SONET |
| Round-trip byte stuffing | `unstuff(stuff(payload)) == payload` for inputs containing `0x7E`, `0x7D`, `0x00` | No bare `0x7E` appears inside the stuffed region; boundaries are unambiguous |
| Detect corruption | Flip one bit; `parse_frame()` raises CRC-32 mismatch | The corrupted frame is dropped, not mis-delivered — TCP retransmits |
| Negotiate LCP options | Configure-Request → Configure-Ack exchange with surviving option set | ACFC/PFC acknowledged on a low-speed link but flagged "do not use on POS" |
| Trace the state machine | DEAD→ESTABLISH→AUTHENTICATE→NETWORK→OPEN transitions printed | Each transition tied to a real LCP/NCP packet code, not a timer guess |
| Justify 4-byte FCS | Why CRC-32 not CRC-16 over OC-48 | FCS is the only error check across PHY+link+net layers on a POS link |

## Ship It

Produce one artifact under `outputs/prompt-ppp-over-sonet.md`:

- A hex-annotated capture of one PPP-over-SONET frame carrying a 20-byte IPv4 packet, with every field labeled (Flag, Address, Control, Protocol, Payload, FCS-32, Flag) and the stuffing transformations called out.
- A short LCP negotiation transcript (Configure-Request/Ack) showing the option set and explaining why ACFC/PFC are rejected on POS per RFC 2615.
- A one-paragraph justification for CRC-32 and for x^7+x^6+1 scrambling, naming the failure each prevents.

Start from the printed output of `code/main.py` and annotate the bytes by hand.

## Exercises

1. A payload contains the bytes `7E 7D 00 41 7E`. Write out the stuffed byte sequence PPP transmits, then show the receiver's destuffed result. How many bytes did stuffing add?
2. Two routers negotiate PPP over an OC-3 link. Router A proposes MRU=4470, ACFC, PFC, and CHAP. Router B supports MRU and CHAP but not ACFC or PFC. Show the exact LCP packet types A and B exchange and the final surviving option set. Why would B's answer differ on a SONET link versus a dial-up link?
3. A 1500-byte IPv4 packet is sent over a POS link with the default (uncompressed, 4-byte FCS) framing and again over a compressed low-speed link with ACFC+PFC and 2-byte FCS. Compute the on-wire byte count and the percentage overhead for each. At what payload size does the constant-field overhead drop below 1% on the POS link?
4. The SONET scrambler is self-synchronous using x^7+x^6+1. Explain what happens to the descrambler state if a single bit is corrupted on the line, and why this is acceptable given that the FCS will catch the frame anyway.
5. Trace the PPP state machine when an operator issues `clear controller sonet` on a live link carrying TCP traffic. Which LCP packet is sent, which state transitions occur, and what does TCP observe at the far end?
6. A captured POS frame fails CRC-32. List three distinct causes (optical, framing, software) and the single piece of evidence that lets you localize each. Why does PPP not request a retransmission?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Flag byte | "the frame marker" | `0x7E` (HDLC flag); the only byte that delimits frames, made safe by byte-stuffing |
| Byte stuffing | "escaping bytes" | Replacing `0x7E`/`0x7D`/low bytes with `0x7D` + (byte XOR 0x20) so the flag stays unique |
| FCS | "the checksum" | Frame Check Sequence — CRC-16 (default) or CRC-32 (mandatory on SONET); computed over the unstuffed body, then stuffed itself |
| LCP | "the setup protocol" | Link Control Protocol (0xC021) — negotiates framing options, auth, MRU via Configure-Request/Ack/Nak/Reject |
| NCP | "the network setup" | Network Control Protocol — one per network layer (IPCP for IP); runs in the NETWORK state to assign addresses |
| ACFC / PFC | "compression options" | Address/Control-Field-Compression and Protocol-Field-Compression — drop constant bytes; rejected on SONET per RFC 2615 |
| Unnumbered mode | "no ACKs" | Control `0x03`, no sequence numbers, no retransmission — the normal POS mode; reliable mode is RFC 1663 and almost unused |
| Scrambling | "randomizing" | XOR with the x^7+x^6+1 PRBS before SONET insertion to guarantee transitions for clock recovery |
| MRU | "the packet size" | Maximum-Receive-Unit — largest payload accepted; default 1500, often 4470 on backbone POS links |
| SONET SPE | "the payload area" | Synchronous Payload Envelope — the bytes inside the SONET frame where scrambled PPP frames are placed |

## Further Reading

- **RFC 1661** — The Point-to-Point Protocol (PPP): core state machine and LCP.
- **RFC 1662** — PPP in HDLC-like Framing: the Flag/Address/Control/Protocol/Payload/FCS layout and byte stuffing.
- **RFC 1663** — PPP Reliable Transmission with sequence numbers and sliding window (rarely used).
- **RFC 2615** — PPP over SONET/SDH: mandates CRC-32, scrambling, and recommends against ACFC/PFC.
- **ITU-T G.707** — SONET/SDH frame structure and the x^7+x^6+1 scrambler.
- **RFC 5072** — IP Version 6 over PPP (IPCP for IPv6).
- **RFC 1334 / RFC 1994** — PAP and CHAP authentication over PPP.
- Tanenbaum, Feamster & Wetherall, *Computer Networks*, 6th ed., Section 3.5.1 (Packet over SONET).
