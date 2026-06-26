# Byte stuffing and the PPP frame format

> The data link layer's first job is *framing* — slicing a raw bit stream into discrete units so a receiver can find where one frame ends and the next begins. The naive approach (a byte-count field in the header) fails catastrophically on a single bit flip: the count is garbled and the receiver loses frame synchronization with no way to recover. The robust fix is a **flag byte delimiter** (0x7E in HDLC and PPP) at each frame boundary, plus **byte stuffing**: whenever the flag byte 0x7E or the escape byte 0x7D appears inside the payload, the sender prefixes it with 0x7D and XORs the offending byte with 0x20, so the delimiter can never appear "by accident." This is the mechanism the **PPP** (Point-to-Point Protocol, RFC 1661/1662) uses on serial links, dial-up, SONET (RFC 2615), and ADSL. A PPP frame carries a fixed 1-byte Flag, a 1-byte Address (0xFF, "all stations"), a 1-byte Control (0x03, unnumbered), a 1-or-2-byte Protocol field, a variable Payload (default MRU 1500), and a 2-or-4-byte CRC checksum. Three sub-protocols ride on top: **LCP** brings the link up and negotiates options (ACFC, PFC, 4-byte CRC), an optional authentication phase (PAP/CHAP), and per-network-layer **NCP**s configure L3. Because the frame length depends on payload contents, an all-flag-byte payload roughly doubles in size — the central efficiency trade-off of byte stuffing versus bit stuffing (HDLC), which only grows ~12.5%.

**Type:** Build
**Languages:** Python
**Prerequisites:** Framing overview, error detection with CRCs (Phase 4 checksum/CRC lesson), HDLC/bit-stuffing contrast
**Time:** ~80 minutes

## Learning Objectives

- Explain why a byte-count framing field loses synchronization after one bit error, and how a flag-byte delimiter with byte stuffing restores it.
- Encode and decode a PPP payload by hand using the 0x7D escape byte and the XOR-with-0x20 rule, and verify the round trip is transparent.
- Lay out the PPP frame field by field (Flag, Address, Control, Protocol, Payload, CRC) with correct default sizes and values.
- Trace the LCP link-establishment state machine: DEAD → ESTABLISH → AUTHENTICATE → NETWORK → OPEN → TERMINATE.
- Quantify the bandwidth cost of byte stuffing in the worst case (all flag bytes) versus the bit-stuffing worst case (~12.5%), and justify when PPP negotiates field compression.
- Identify the failure mode an undersized CRC (2 vs 4 bytes) misses, and why SONET mandates the 4-byte CRC-32.

## The Problem

A router on a SONET OC-48 backbone link must carry IPv4 packets across a continuous 2.4 Gbps bit stream. The physical layer hands the data link layer a raw sequence of bytes with no intrinsic frame boundaries. The engineer's first instinct — prepend each frame with a 1-byte length field — works until a single bit flips the count from 5 to 7. Now the receiver reads two extra bytes, thinks the next frame starts at the wrong offset, and every subsequent frame is misaligned. The checksum on the bad frame fires, but the receiver *still doesn't know where the next frame begins* — there is no resynchronization signal. Asking for a retransmission is useless because the receiver cannot skip to the start of the retransmitted frame. The link is wedged until a higher-level timer resets it.

The same problem kills SLIP, PPP's predecessor, on noisy dial-up lines. The fix PPP adopts is the HDLC heritage: delimit every frame with the flag byte 0x7E and *escape* any 0x7E that legitimately appears in the data. Now a lost-synchronization receiver merely scans the byte stream for 0x7E — it is mathematically guaranteed to appear only at frame boundaries — and resyncs within one frame. This lesson builds the exact stuffing/destuffing engine and frame encoder PPP uses.

## The Concept

### Why byte counting fails and flag bytes save you

The four classic framing methods are byte count, flag bytes with byte stuffing, flag bits with bit stuffing, and physical-layer coding violations. Byte count is conceptually clean (header says "5 bytes follow") but its count field is itself error-prone, and a corrupted count desynchronizes the receiver irrecoverably. The flag-byte method sidesteps this entirely: the receiver does not trust a count, it trusts a *delimiter pattern* that is engineered to never appear in the data. If the receiver ever loses its place, it scans for the next flag byte and resumes — graceful degradation instead of a hard wedge. This is the design choice PPP inherits from HDLC.

### The byte-stuffing algorithm: 0x7D escape and the XOR-0x20 rule

PPP uses two reserved bytes: the **flag** 0x7E (01111110) and the **escape** 0x7D (01111101). The sender scans the payload; whenever it encounters 0x7E or 0x7D it emits 0x7D followed by the original byte XORed with 0x20. XORing with 0x20 flips bit 5, which moves 0x7E → 0x5E and 0x7D → 0x5D — taking the byte out of the reserved range. The receiver scans for 0x7D; on seeing it, it drops the 0x7D and XORs the next byte with 0x20 to recover the original.

| Original byte | On the wire | Recovery |
|---|---|---|
| 0x7E (flag, in data) | 0x7D 0x5E | drop 0x7D, 0x5E XOR 0x20 = 0x7E |
| 0x7D (escape, in data) | 0x7D 0x5D | drop 0x7D, 0x5D XOR 0x20 = 0x7D |
| 0x41 ('A', ordinary) | 0x41 | unchanged |

A useful invariant: a real flag byte 0x7E can *only* appear as a frame delimiter, never inside an escaped payload. This is what makes resynchronization-by-scanning safe. See `assets/byte-stuffing-ppp-frame-format.svg` for the byte-by-byte diagram, and `code/main.py` for a runnable implementation of `byte_stuff()` and `byte_destuff()` that you can fuzz against random payloads.

### The PPP frame format, field by field

All PPP frames begin and end with the HDLC flag byte 0x7E. Between the flags:

| Field | Size (default) | Default value | Notes |
|---|---|---|---|
| Flag | 1 byte | 0x7E | Start delimiter; one flag may serve as both end-of-frame-N and start-of-frame-N+1 |
| Address | 1 byte | 0xFF | "All stations accept" — avoids assigning data-link addresses on a point-to-point link |
| Control | 1 byte | 0x03 | Unnumbered frame (no sequence numbers, no ACKs) |
| Protocol | 1 or 2 bytes | 2 bytes | Identifies the payload type: 0x0021 = IPv4, 0x0057 = IPv6, 0xC021 = LCP, 0x80FD = CBCP, 0xC023 = PAP, 0xC223 = CHAP |
| Payload | variable | MRU 1500 bytes | Stuffed; may be padded |
| CRC (FCS) | 2 or 4 bytes | 2 bytes (CRC-16) | 4-byte CRC-32 negotiable; covers Address…Payload, not the flags |

Two LCP-negotiated compressions shave bytes: **ACFC** (Address-and-Control-Field-Compression) drops the always-0xFF-0x03 pair; **PFC** (Protocol-Field-Compression) shrinks the Protocol field to 1 byte when its high byte is 0. On slow dial-up links these savings matter; on SONET they are not worth the parsing cost and RFC 2615 recommends leaving all fields uncompressed.

### Protocol field codes: the multiplexing heart of PPP

Unlike a dedicated link, PPP is a *multiprotocol* framer — it can carry IPv4, IPv6, IPX, AppleTalk, and PPP's own control protocols in the same stream. The Protocol field is the demultiplexer. Codes with the high bit 0 carry network-layer data; codes with the high bit 1 carry PPP control protocols.

| Protocol code | Meaning |
|---|---|
| 0x0021 | IPv4 |
| 0x0057 | IPv6 |
| 0x002B | IPX |
| 0x0029 | AppleTalk |
| 0xC021 | LCP (Link Control Protocol) |
| 0xC023 | PAP (Password Authentication Protocol) |
| 0xC223 | CHAP (Challenge-Handshake Authentication Protocol) |
| 0x80FD | CBCP / compressed payloads |
| 0x8021 | IPCP (IP Control Protocol — the NCP for IP) |

This is why PPP needs NCPs at all: each network layer has its own negotiation (for IP, IPCP negotiates the local IP address and DNS servers). LCP handles only link-level concerns.

### The CRC/FCS: 2 bytes default, 4 bytes on SONET

The Frame Check Sequence is the sole error-detection mechanism on most PPP links. The default 2-byte CRC-16 (CRC-CCITT, polynomial 0x1021) catches all bursts up to 16 bits and detects ~99.998% of longer errors — fine for benign serial lines. On high-speed, high-BER optical links RFC 2615 mandates the 4-byte CRC-32 (the same generator used in Ethernet, polynomial 0x04C11DB7), because a 16-bit FCS is too easily defeated by the multi-bit error bursts a SONET regenerator can introduce. The FCS covers everything from Address through Payload (and the stuffed bytes on the wire), but never the flag bytes themselves.

### LCP and the link-establishment state machine

PPP is more than a frame format — it is a layered control plane. Before a single data packet flows, the peers run LCP to bring the link up through a well-defined state machine:

| State | Entered when | Activity |
|---|---|---|
| DEAD | No physical carrier | Physical layer down |
| ESTABLISH | Carrier detected | Peers exchange LCP Configure-Request/Ack/Nak to agree options (MRU, ACFC, PFC, auth, FCS size) |
| AUTHENTICATE | LCP options agreed (if auth required) | PAP (cleartext, 2-way) or CHAP (challenge-response, 3-way) |
| NETWORK | Auth success | Per-L3 NCPs run — IPCP assigns IP addresses, negotiates DNS |
| OPEN | NCPs done | Data transport; IP packets ride in Protocol-0x0021 frames |
| TERMINATE | LCP Terminate-Request or carrier loss | Clean teardown, return to DEAD |

The textbook's Fig. 3-25 captures this exactly. Note the asymmetry: LCP negotiates *link* properties, NCP negotiates *network-layer* properties. A link can be OPEN at L2 (LCP done) but still unconfigured at L3 (IPCP not yet run) — packets would be framed but unroutable.

### Transparency and the worst-case overhead

Byte stuffing makes the on-wire frame length *data-dependent*. In the benign case (no 0x7E or 0x7D in the payload) the overhead is just the fixed header/trailer. In the pathological case — a payload consisting entirely of 0x7E bytes — every byte becomes two, so a 1500-byte payload balloons to ~3000 stuffed bytes. Bit stuffing (HDLC) bounds the worst case far better: at most one stuffed bit per five consecutive 1s, capping overhead near 12.5% regardless of content. The trade-off PPP accepts: byte orientation is simpler to implement in software on byte-oriented serial hardware, and the worst case is rare for real IP traffic (which rarely contains runs of 0x7E).

### Bit stuffing vs byte stuffing: the PPP/HDLC split

HDLC and PPP share the 0x7E flag and an almost identical frame shape, but they stuff at different granularities. HDLC stuffs *bits* — after any five consecutive 1s it inserts a 0 — so frames need not be byte-aligned and the worst-case overhead is bounded at ~12.5%. PPP stuffs *bytes* — escaping whole 0x7E/0x7D values — so frames are always an integral number of bytes and the worst-case overhead is ~100%. PPP chose byte orientation because its target media (async serial, dial-up modems) are byte-oriented at the hardware level; HDLC's bit orientation suits the synchronous bit-piped links (ISDN, X.25) it grew up on. USB uses bit stuffing for the same transition-density reason that motivated HDLC.

## Build It

1. Open `code/main.py`. The module models a PPP link end-to-end with stdlib only.
2. Run `python3 code/main.py`. It will (a) byte-stuff and destuff a sample payload and assert the round trip is transparent, (b) build a full PPP frame around an IPv4 pseudo-payload with CRC-16, (c) parse that frame back, recompute the FCS, and confirm integrity, and (d) print a worst-case overhead table for all-flag-byte payloads.
3. Read `byte_stuff()` / `byte_destuff()`. Confirm the XOR-0x20 rule against the table in *The Concept*.
4. Read `build_ppp_frame()`. Match each field to the field table — Flag 0x7E, Address 0xFF, Control 0x03, Protocol 0x0021, Payload (stuffed), CRC-16.
5. Edit the sample payload to include 0x7E and 0x7D bytes and rerun; watch the stuffed output and confirm destuffing recovers them exactly.
6. Toggle `USE_CRC32 = True` at the top of `main()` and observe the 4-byte FCS, as RFC 2615 requires for SONET.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Prove transparency | Stuff then destuff a payload containing 0x7E, 0x7D, 0x41 | Output equals input byte-for-byte; no 0x7E appears inside the stuffed stream |
| Validate a frame | Parse a built frame, recompute FCS over Address…Payload | Recomputed FCS matches the trailer's 2 (or 4) bytes exactly |
| Detect corruption | Flip one bit in the payload of a built frame, then verify | FCS recompute differs from the trailer; frame is flagged bad and discarded |
| Size the worst case | Stuff a 1500-byte all-0x7E payload | Stuffed length ≈ 3000 bytes; overhead ≈ 100% vs ~12.5% for bit stuffing |
| Justify field compression | Compare a 40-byte TCP ACK in default vs ACFC+PFC frames | ACFC+PFC saves 3 bytes per frame; meaningful on dial-up, not on SONET |
| Trace link bring-up | Read the LCP state walk printed by `main()` | DEAD→ESTABLISH→AUTHENTICATE→NETWORK→OPEN ordering matches the textbook state diagram |

## Ship It

Produce one artifact under `outputs/prompt-byte-stuffing-ppp-frame-format.md`:

- A captured byte-level trace of one PPP frame carrying a chosen payload, showing the pre-stuff payload, the post-stuff wire bytes (with each 0x7D/0x5E and 0x7D/0x5D pair annotated), the full frame with all six fields labeled, the computed CRC, and a destuffing walk that recovers the original.
- A short justification paragraph: when you would negotiate ACFC+PFC, when you would insist on the 4-byte CRC-32, and the worst-case overhead you accept by choosing byte stuffing over bit stuffing.

Start from the printed output of `code/main.py` and annotate it by hand.

## Exercises

1. A PPP payload is the 6 bytes `7E 41 7D 42 7E 43`. Write out the stuffed byte stream a sender places on the wire, then walk through the receiver's destuffing step by step and confirm the original 6 bytes are recovered.
2. A single bit flips the Control field of a PPP frame from 0x03 to 0x07. Does the FCS catch it? Does the receiver lose frame synchronization? Contrast this with a single bit flip in a byte-count framing field.
3. You are designing PPP over a 2.4 Gbps SONET OC-48 link (RFC 2615). Argue for the 4-byte CRC-32 over the 2-byte CRC-16, and against negotiating ACFC and PFC. What BER assumption drives your argument?
4. A peer proposes LCP option ACFC on a 56 kbps dial-up line. Quantify the per-frame savings for a stream of 40-byte TCP acknowledgements (IPv4 header 20 + TCP header 20) and compute the percentage bandwidth gain.
5. Contrast the worst-case overhead of byte stuffing (PPP) and bit stuffing (HDLC) for a payload of 1000 bytes that is entirely 0x7E. Show the arithmetic for both.
6. The link-establishment state machine reaches AUTHENTICATE but CHAP fails. Trace the allowed transitions back to DEAD, and explain why no NCP packets are ever exchanged in this case.
7. A receiver scanning a noisy line sees the byte sequence `… 7E <garbage> 7E <garbage> 7E …`. Explain how the flag-byte design lets it resynchronize and find a valid frame, and why a byte-count design could not.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Flag byte | "the marker" | 0x7E (01111110); the only byte allowed at frame boundaries because stuffing guarantees it never appears in payload |
| Byte stuffing | "escaping" | Inserting 0x7D before any 0x7E/0x7D in the payload and XORing that byte with 0x20, so the delimiter stays unique |
| Escape byte | "the 0x7D thing" | 0x7D; signals "the next byte is data, not a delimiter — XOR it with 0x20 to recover it" |
| Transparency | "data independence" | The guarantee that any byte pattern — including 0x7E itself — can be carried unchanged after stuffing/destuffing |
| ACFC | "drop the address" | Address-and-Control-Field-Compression; LCP option to omit the always-0xFF-0x03 pair, saving 2 bytes/frame |
| PFC | "shrink protocol" | Protocol-Field-Compression; shrinks the 2-byte Protocol field to 1 byte when the high byte is 0 |
| LCP | "link setup" | Link Control Protocol; runs in Protocol-0xC021 frames to negotiate MRU, auth, ACFC/PFC, FCS size |
| NCP | "network setup" | A family of Network Control Protocols (e.g. IPCP for IP) that configure each network layer after LCP opens the link |
| FCS | "the checksum" | Frame Check Sequence — a 2-byte CRC-16 (default) or 4-byte CRC-32 (SONET) over Address…Payload |
| MRU | "max packet" | Maximum Receive Unit; the negotiated largest payload, default 1500 bytes |
| Unnumbered mode | "no ACKs" | Control field 0x03; connectionless, unacknowledged service — the near-universal PPP mode on the Internet |

## Further Reading

- **RFC 1661** — The Point-to-Point Protocol (PPP), defining LCP and the frame multiplexing model (Simpson, 1994).
- **RFC 1662** — PPP in HDLC-like Framing, the exact byte-stuffing and frame-format specification.
- **RFC 1663** — PPP Reliable Transmission with sequence numbers and retransmission (rarely deployed).
- **RFC 2615** — PPP over SONET/SDH, mandating the 4-byte CRC-32 and recommending uncompressed fields.
- **RFC 1334** — PPP Authentication Protocols (PAP and CHAP).
- **RFC 1332** — The PPP IP Control Protocol (IPCP).
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 3, Sections 3.1.2 (Framing) and 3.5.1 (Packet over SONET).
- ISO/IEC 13239 — High-level Data Link Control (HDLC) procedures, the bit-stuffed ancestor PPP derives its frame shape from.
