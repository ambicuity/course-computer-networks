# Byte-count and preamble-plus-length framing

> The data link layer's first job is to chop the physical layer's raw bit stream into discrete **frames** so each can carry a checksum and be retransmitted independently. The textbook's four framing methods — **byte count**, **flag bytes with byte stuffing**, **flag bits with bit stuffing**, and **coding violations** — trade resynchronization cost against bandwidth overhead. A pure **byte-count** header (one field giving the frame length in bytes) is the cheapest scheme but is fatally fragile: a single bit flip in the count field desynchronizes the receiver, which then cannot find the start of the *next* frame even after the checksum catches the error — so byte count is **never used alone** in real links. Real systems combine methods: **Ethernet** (IEEE 802.3) opens every frame with a 7-byte **preamble** of `0x55` alternating bits plus a 1-byte **Start Frame Delimiter** `0xD5`, then a **Length** field (802.3) or a **Type** field (Ethernet II), and finally relies on inter-frame **gaps** and idle codes; **802.11 Wi-Fi** uses a longer **PLCP preamble** (~72 bits in the long mode) so the receiver's AGC, bit timing, and equalizer can converge before payload arrives. PPP (RFC 1662) instead uses the HDLC flag `0x7E` with byte stuffing of `0x7E`→`0x7D 0x5E` and `0x7D`→`0x7D 0x5D`. This lesson builds a runnable byte-count and preamble-plus-length framer/parser, injects a single-bit error into the count field, and shows why the receiver loses frame alignment — the exact failure the textbook's Fig. 3-3(b) depicts.

**Type:** Learn
**Languages:** Python
**Prerequisites:** The data link layer's position in the stack (Phase 4 intro), bit error rate and why the physical layer is not error-free, checksums at a conceptual level
**Time:** ~70 minutes

## Learning Objectives

- Explain why a raw bit stream cannot be handed to the network layer and why the link layer must first delimit **frames**.
- Trace a pure byte-count framer: write the count, emit the bytes, parse on the other end, and locate the next frame.
- Diagnose the **count-garbling failure mode**: show how one flipped bit in the length field desynchronizes the receiver so it cannot recover the next frame boundary even when the checksum detects the error.
- Distinguish the four framing methods (byte count, byte stuffing, bit stuffing, coding violations) by overhead, transparency, and post-error resynchronization cost.
- Describe the **preamble-plus-length** combination used by Ethernet (802.3) and 802.11: a known sync pattern for clock/AGC recovery followed by a length field that locates frame end.
- Read a real Ethernet frame header — preamble, SFD, addresses, Length/Type, payload, FCS — and identify which fields delimit, which address, and which check.

## The Problem

A sensor gateway receives a continuous RS-485 stream from a line of industrial meters. The link is noisy: the spec allows a bit error rate around 10⁻⁶, so on a 1 Mbit/s line you expect roughly one error per second. The designer chose the simplest framing possible — a one-byte **length** field followed by exactly that many payload bytes, repeated. It works for hours, then the gateway silently drops every subsequent reading for the rest of the day. The logs show the checksum failing on one frame, and then the parser reports "frame lengths" of 231, 4, 19, 250 ... none of which match real meter packets.

The bug is not in the checksum. The checksum correctly flagged the corrupted frame as bad and discarded it. The bug is that the **length field itself was hit by the bit flip**, so after discarding the bad frame the receiver has no idea how many bytes to skip to reach the start of the *next* frame. It is now reading the stream at the wrong offset, interpreting payload as length fields, and will stay lost until it happens to re-align — which on a noisy line may take thousands of frames. Asking for a retransmission is useless: the sender knows the frame failed, but the receiver cannot say where to resume. This is the textbook's exact objection to byte-count framing, and it is why no production link protocol uses byte count alone.

## The Concept

### Why framing exists at all

The physical layer delivers a **raw bit stream**. Bits may arrive flipped, dropped, or duplicated; the count received may differ from the count sent. The data link layer's contract with the network layer is to deliver discrete, integrity-checked **frames** — each a self-contained unit that can be checksummed, acknowledged, and retransmitted. To do that it must first solve **framing**: where does one frame end and the next begin? A good design makes the boundary easy to find while spending little channel bandwidth on bookkeeping. The textbook lists four approaches; we focus on the first (byte count) and the hybrid that dominates real LANs (preamble + length), and contrast them with stuffing-based schemes.

### Method 1 — Byte count

Each frame begins with a header field giving the number of bytes in the frame. The receiver reads the count, then consumes exactly that many bytes; the next byte is the count of the following frame. The textbook's Fig. 3-3(a) shows four frames of sizes 5, 5, 8, 8 laid end to end on the wire:

```
|5|1 2 3 4| |5|5 6 7 8| |8|9 0 1 2 3 4 5| |8|6 7 8 9 0 1 2|
```

Each leading digit is the count; the bytes that follow are the payload. Parsing is trivial: read a count *c*, read *c* bytes, repeat. There is no escaping, no reserved bytes, no per-bit overhead. The cost shows up only under error.

### The fatal failure: count garbling

Fig. 3-3(b) flips the second frame's count from 5 to 7. The receiver now consumes 7 bytes for frame 2 — the 5 real payload bytes plus the first 2 bytes of frame 3's count field. It then reads byte 3 of frame 3's payload as the count of frame 4, and is permanently misaligned. Three properties make this catastrophic:

1. **The error is in the framing metadata, not the payload.** The checksum covers the whole frame, so it *will* flag frame 2 as bad — but only after the receiver has already consumed the wrong number of bytes.
2. **Resynchronization is impossible without an external marker.** There is no flag byte to scan for, no idle pattern to anchor on. The receiver cannot tell "where am I in the stream."
3. **Retransmission cannot help.** The sender re-sends frame 2, but the receiver does not know how many bytes to discard before the retransmission begins, so it still cannot find the start.

This is why the textbook states bluntly that **byte count is rarely used by itself**. `code/main.py` reproduces this failure: `byte_count_parse()` walks the stream correctly on a clean frame but, after `inject_bit_flip()` corrupts the length field, it returns nonsense lengths and never recovers — exactly the gateway bug above.

### Method 2 and 3 — Flag bytes with stuffing (PPP, HDLC)

To make resynchronization possible after an error, frame each unit with a special **flag byte**. HDLC and PPP (RFC 1662) use `0x7E`. A receiver that loses alignment simply scans the stream for the next flag; flags are only legal at frame boundaries, so the next flag is the start of a fresh frame. The catch: `0x7E` may occur in binary payload (a JPEG, an encrypted block). The sender therefore **stuffs** an escape byte `0x7D` before any `0x7E` or `0x7D` in the data, and the receiver reverses the transform. The PPP convention:

| Original byte | On the wire |
|---|---|
| `0x7E` (flag) | `0x7D 0x5E` |
| `0x7D` (escape) | `0x7D 0x5D` |

Bit stuffing (HDLC's `01111110` flag, insert a 0 after any five consecutive 1s) is the bit-level analogue: it is not tied to 8-bit bytes and adds at most ~12.5% overhead (one stuffed bit per byte of all-ones data). USB uses bit stuffing for the same reason — to guarantee a minimum transition density that keeps the receiver's clock-recovery PLL locked. The price both pay is **variable frame length**: a frame's wire size depends on its contents, which complicates fixed-size buffering.

### Method 4 — Coding violations

When the physical line code is redundant (4B/5B, 8B/10B, 64B/66B), some signal symbols are unused by legal data. A protocol can reserve those "illegal" symbols as frame delimiters. Because they can never appear in payload, no stuffing is needed and resynchronization is just "scan for the reserved symbol." Gigabit Ethernet's 64B/66B block type fields and the J/K/T/R control characters of 8B/10B are examples. The textbook calls these **coding violations** — they violate the data encoding rules on purpose to signal structure.

### Method 5 (the real one) — Preamble plus length

Production LAN protocols combine methods for safety. The dominant pattern, used by both Ethernet and 802.11, is: open with a known **preamble** that lets the receiver prepare, then carry an explicit **length** field that locates the frame end.

**Ethernet (IEEE 802.3)** frame layout:

| Field | Bytes | Purpose |
|---|---|---|
| Preamble | 7 | `0x55` pattern (`10101010…`); lets the receiver recover bit clock and adjust gain |
| Start Frame Delimiter (SFD) | 1 | `0xD5` (`10101011`); marks the last byte of preamble, byte-aligns the receiver |
| Destination MAC | 6 | Receiver address |
| Source MAC | 6 | Sender address |
| Length / Type | 2 | 802.3: length of payload in bytes (≤ 1500); Ethernet II: EtherType (≥ 1536) |
| Payload | 46–1500 | Network-layer packet, padded to ≥ 46 |
| Frame Check Sequence (FCS) | 4 | CRC-32 over DA, SA, Len/Type, Payload |

The preamble is **not** counted as part of the frame and is not covered by the FCS — it is pure physical-layer synchronization. The SFD hands off to byte-aligned parsing. The Length field then does the byte-count job, but safely: if the length is corrupt, the receiver can still resynchronize on the **next preamble** it sees, because the inter-frame gap (12 bytes of idle, minimum 9.6 µs at 10 Mbit/s) and the preamble pattern are findable. Ethernet thus gets the cheap parsing of byte count and the recoverability of a sync pattern. Note the classic ambiguity: a 2-byte field ≤ 1500 means **Length** (802.3 framing); ≥ 1536 means **Type/EtherType** (Ethernet II framing, e.g. `0x0800` = IPv4). Modern adapters auto-detect.

**802.11 Wi-Fi** takes the same idea further because radio is harder. The PLCP (Physical Layer Convergence Procedure) header begins with a long preamble — 128 bits (long mode) of `1 0 1 0…` sync followed by a SFD, roughly the 72 bits the textbook cites for the short-preamble mode — giving the receiver time for automatic gain control, antenna selection, channel estimation, and equalizer convergence before the SIGNAL field arrives. The SIGNAL field then carries the **LENGTH** (in microseconds) and the data rate, so the receiver knows exactly how long to keep demodulating. Preamble plus length, scaled up for a hostile medium.

### Worked example: a 5-byte payload under each scheme

Suppose the payload is the bytes `03 7E 7D FF 00` (note it contains both the flag `0x7E` and the escape `0x7D`).

| Scheme | On-the-wire bytes (count/flag fields in **bold**) |
|---|---|
| Byte count (1-byte count) | **07** 03 7E 7D FF 00  (7 bytes total: count + 5 payload + ... here count=6 for count+5) |
| PPP flag + stuffing | **7E** 03 7D 5E 7D 5D FF 00 **7E** |
| Byte count, count corrupted to 9 | **09** 03 7E 7D FF 00 → receiver reads 9 bytes, eats into the next frame, never recovers |

`code/main.py` builds exactly these encodings and prints them side by side, then corrupts the count field to demonstrate the desynchronization.

### Decision rule: which method when?

| Requirement | Pick |
|---|---|
| Absolute simplicity, trusted clean channel (test harness, loopback) | Byte count alone — accept the fragility |
| Recoverable framing on a byte-oriented serial link | Flag + byte stuffing (PPP, RFC 1662) |
| Bit-oriented, transparent, minimum-density for clock recovery | Flag + bit stuffing (HDLC, USB) |
| High-speed LAN with redundant line code | Coding violations (8B/10B, 64B/66B) |
| Noisy shared medium needing AGC/equalizer settle time | Preamble + length (Ethernet, 802.11) |

The textbook's recommendation is the last row: real links combine a long, findable preamble with an explicit length field. Pure byte count is the cautionary tale, not the design.

## Build It

1. Read `code/main.py`. It implements three framers: `byte_count_frame()`, `ppp_frame()` (flag + byte stuffing per RFC 1662), and `ethernet_frame()` (preamble + SFD + length + FCS placeholder).
2. Run it: `python3 code/main.py`. The demo emits three encoded frames for the payload `03 7E 7D FF 00`, parses each back, and prints the recovered payload.
3. Watch the **error injection** block: `inject_bit_flip()` flips one bit in the byte-count frame's length field, and `byte_count_parse()` then walks the stream at the wrong offset, printing garbage lengths — the gateway bug from *The Problem*, reproduced.
4. Inspect `ethernet_frame()`: confirm the preamble is `0x55 × 7`, the SFD is `0xD5`, the Length field holds the payload size, and the FCS is a real CRC-32 over the addressed fields.
5. Change the payload to include `0x7E 0x7D` and rerun the PPP framer — confirm stuffing expands the wire size and that `ppp_parse()` recovers the original bytes exactly.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm round-trip framing | Parse output equals original payload for all three framers | Zero data corruption; stuffing fully reversed |
| Reproduce count-garble failure | After `inject_bit_flip`, `byte_count_parse` yields wrong lengths and never realigns | The receiver stays desynchronized; the next real frame is missed |
| Justify preamble + length | Ethernet frame has findable `0x55×7 0xD5` then a Length; 802.11 trace has a PLCP preamble then LENGTH | A lost frame is recoverable by scanning for the next preamble |
| Distinguish Length vs Type | 2-byte field ≤ 1500 → Length (802.3); ≥ 1536 → EtherType (e.g. `0x0800` IPv4) | Adapter auto-detects and parses accordingly |
| Explain stuffing overhead | All-`0x7E` payload nearly doubles PPP frame size; all-ones payload adds ~12.5% under bit stuffing | Variable-length frames accounted for in buffer sizing |

## Ship It

Produce one artifact under `outputs/` (start from `outputs/prompt-framing-by-byte-count-and-preamble.md`):

- A side-by-side hex dump of the same 5-byte payload under byte-count, PPP-stuffed, and Ethernet (preamble+length) framing.
- The corrupted-byte-count trace: the original stream, the flipped bit, the parser's first five "lengths" after the error, and a written diagnosis of why resynchronization fails.
- A one-paragraph justification, with field sizes, for why Ethernet puts a 7-byte preamble plus a 1-byte SFD in front of a 2-byte Length field rather than relying on Length alone.

## Exercises

1. Take the byte-count stream `05 41 42 43 44 05 45 46 47 48 08 49 50 51 52 53 54 55`. Flip the bit that turns the second count `05` into `07`. Trace the parser's reads byte by byte for the next three "frames" and state where it finally resynchronizes (or whether it ever does).
2. Encode the payload `7E 7D 7E 00 7D` under PPP framing. Write the exact on-the-wire bytes including opening and closing flags, and show the `ppp_parse()` destuffing step recovering the original.
3. An Ethernet frame carries a 60-byte IPv4 packet. Give the byte count and purpose of every field from preamble through FCS, and state which fields are covered by the CRC-32.
4. A 2-byte Length/Type field reads `0x0800`. Is this 802.3 Length or Ethernet II EtherType? How does an adapter decide, and what value would force the opposite interpretation?
5. Compare the worst-case wire-size overhead of byte stuffing (PPP) versus bit stuffing (HDLC) for a 1000-byte payload consisting entirely of `0xFF` bytes. Compute the percentage overhead for each.
6. 802.11's long PLCP preamble is 128 bits, far longer than Ethernet's 64 preamble bits. Give two physical-layer reasons radio needs a longer preamble than copper, and explain how the SIGNAL field's LENGTH then makes the rest of the frame self-delimiting.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Framing | "splitting packets" | Delimiting where one frame ends and the next begins in a raw bit stream, so each can be checksummed and retransmitted independently |
| Byte count | "a length field" | A header field giving the frame's length in bytes; cheapest to parse but fatally fragile if corrupted, so never used alone |
| Flag byte | "a marker" | A reserved byte (HDLC/PPP `0x7E`) that delimits frames; findable after desynchronization, but payload occurrences must be stuffed |
| Byte stuffing | "escaping bytes" | Inserting an escape (`0x7D`) before any flag or escape byte in payload so it survives the wire; reversed by the receiver |
| Bit stuffing | "inserting zeros" | Inserting a 0 after five consecutive 1s (HDLC) so the `01111110` flag cannot appear in data; also guarantees transition density for clock recovery |
| Coding violation | "illegal signals" | A reserved line-code symbol unused by legal data (8B/10B, 64B/66B) used as a delimiter; needs no stuffing |
| Preamble | "the sync bytes" | A known alternating-bit pattern (Ethernet `0x55×7`) that lets the receiver recover the clock and set gain before payload arrives |
| SFD | "start byte" | Start Frame Delimiter (`0xD5`), the last preamble byte that byte-aligns the receiver and hands off to header parsing |
| FCS | "the checksum" | Frame Check Sequence — a CRC-32 over the addressed header and payload that detects (but does not correct) transmission errors |
| Desynchronization | "losing alignment" | The receiver reading the stream at the wrong byte offset, typically because a length field was corrupted; unrecoverable without a findable marker |

## Further Reading

- **IEEE 802.3-2022** — Ethernet frame format: preamble, SFD, Length/Type, FCS, inter-frame gap.
- **RFC 1662** — PPP in HDLC-like framing; defines the `0x7E` flag and `0x7D` byte-stuffing transform.
- **ISO/IEC 13239** — High-level Data Link Control (HDLC): the `01111110` flag and bit-stuffing rule.
- **IEEE 802.11-2020** — PLCP preamble, SIGNAL field (LENGTH, RATE), and long/short preamble modes.
- **USB 2.0 Specification** — bit stuffing for transition density and clock recovery on a serial bus.
- Tanenbaum, Feamster & Wetherall, *Computer Networks*, 6th ed., Section 3.1.2 ("Framing").
- Kurose & Ross, *Computer Networking: A Top-Down Approach*, Chapter 6, on the link layer's framing and error-detection services.
