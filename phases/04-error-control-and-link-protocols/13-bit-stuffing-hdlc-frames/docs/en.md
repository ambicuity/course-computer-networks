# Bit stuffing with HDLC flags

> The data link layer must carve a raw bit stream from the physical layer into discrete frames, and the hard part is not the carving but *resynchronizing after an error*. HDLC (ISO/IEC 3309, originally IBM SDLC) solves framing at the bit level with a single 8-bit flag `01111110` (`0x7E`) that delimits every frame. Because that same pattern could appear in payload, the sender scans the outgoing stream and, after any five consecutive `1` bits, **stuffs a `0`**; the receiver, seeing five `1`s followed by a `0`, **destuffs** it. This keeps the flag transparent to the network layer, guarantees a minimum transition density that helps the physical layer's clock-recovery PLL stay locked (the same reason USB 1.1 and CAN bus stuff bits), and makes frame boundaries unambiguous even after a loss of sync — a receiver can simply scan for the flag. The cost is content-dependent expansion: worst case ~12.5% for a payload of all `1`s, since one bit is inserted per byte. The failure mode to watch is the *aborted frame* — six consecutive `1`s (`0111111x`) is an abort signal, not data, which lets a sender kill a frame mid-transmission. This lesson builds a runnable bit-stuff/destuff engine plus an HDLC frame parser and walks the textbook's Fig. 3-5 example end to end.

**Type:** Build
**Languages:** Python
**Prerequisites:** Physical layer bit transmission and clock recovery (Phase 2), framing motivation and byte stuffing (Phase 4 earlier lessons), checksums/CRC (Phase 4 CRC lesson)
**Time:** ~75 minutes

## Learning Objectives

- Explain why a flag byte alone (`0x7E`) is not sufficient to delimit frames and how bit stuffing makes the flag pattern transparent to the payload.
- Apply the "five consecutive 1s → stuff a 0" rule by hand to a bit string and recover the original via the inverse destuffing rule.
- Compute the worst-case and typical line-rate expansion of bit stuffing and relate it to the 12.5% ceiling.
- Distinguish a valid flag (`01111110`), a stuffed bit (five 1s + 0), and an abort sequence (six 1s) by reading a raw line trace.
- Parse an HDLC frame into Flag, Address, Control, Information, FCS, Flag and state the width of each field in the standard 1979 / ISO 13239 layout.
- Diagnose a resynchronization failure: given a garbled byte count vs a garbled bit-stuffed stream, explain which method self-recovers and which does not.

## The Problem

A point-to-point serial link between two routers carries a mix of HTTP text and binary firmware images. The link layer must deliver *frames* — bounded units with a checksum — to the receiver, but the physical layer hands it an undifferentiated bit stream. The engineer reaches for the obvious trick: put a fixed delimiter, the byte `0x7E`, at the start and end of every frame.

It works for the text traffic. Then a firmware image ships, and its bytes happen to contain `0x7E` deep in the payload. The receiver sees the delimiter, declares "end of frame" 400 bytes early, runs a checksum on a truncated frame, drops it as corrupt, and — because it has lost its place — mis-aligns every subsequent frame. Re-synchronization is impossible: a single spurious delimiter has desynchronized the stream indefinitely, and the receiver cannot tell a real boundary from a data byte. The byte-count method fails even more spectacularly: one bit flip in the length field makes the receiver jump to the wrong offset and stay lost.

The engineer needs a delimiter scheme that is *self-synchronizing* — one where the delimiter can never appear in the payload, so a lost receiver can always scan forward to the next real boundary. That scheme is bit stuffing with HDLC flags.

## The Concept

### The flag and the stuffing rule

HDLC frames are delimited by the 8-bit **flag** `01111110` (`0x7E`). The same flag is used at both ends; two flags in a row mark the boundary between consecutive frames. To make the flag impossible to occur inside the payload, the sender applies one rule while emitting bits:

> After any five consecutive `1` bits in the payload, insert one `0` bit.

The receiver applies the inverse:

> After any five consecutive `1` bits, examine the next bit. If it is `0`, delete it (destuff). If it is `1`, you are looking at a flag or an abort — handle accordingly.

Because the flag itself contains six `1`s (`01111110`), the stuffing rule guarantees the payload can never produce that pattern: at the fifth `1`, a `0` is forced in, breaking the run before a sixth `1` can accumulate. The flag is therefore reserved exclusively for frame boundaries. See `assets/bit-stuffing-hdlc-frames.svg` for the visual contrast of original, line, and stored bits.

### Worked example (textbook Fig. 3-5)

Original data (a): `0 1 1 0 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 0 0 1 0`

The sender scans left to right. The run of `1`s begins at position 5 (after `0 1 1 0 1`). After the fifth consecutive `1`, stuff a `0`:

Line (b): `0 1 1 0 1 1 1 1 1 0 1 1 1 1 1 0 1 1 1 1 1 0 1 0 0 1 0`

Three stuffed bits are inserted — one after each group of five `1`s. The receiver strips them:

Stored (c): `0 1 1 0 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 0 0 1 0`

identical to the original. `code/main.py` reproduces this exact trace and asserts round-trip equality.

### The complete HDLC frame layout

A standard HDLC frame (ISO/IEC 13239, the successor to ISO 3309) has the following fields:

| Field | Width | Purpose |
|---|---|---|
| Flag | 8 bits | `01111110` — start delimiter |
| Address | 8 bits (extended: multiples of 8) | Secondary station address; LSB = extension bit (0 = more address octets follow) |
| Control | 8 or 16 bits | Frame type, sequence numbers (see below) |
| Information | 0–N bits | Payload; transparent — bit-stuffed |
| FCS | 16 or 32 bits | Frame Check Sequence, CRC-16-CCITT or CRC-32, computed over Address+Control+Information *before* stuffing |
| Flag | 8 bits | `01111110` — end delimiter |

The **Control field** encodes three frame classes:

| Control field (8-bit) | Bits 0–1 | Type | Contents |
|---|---|---|---|
| `0SeqNS-P/F-SeqNR` | `0` | I-frame (information) | N(S) send seq, N(R) recv seq, P/F poll/final |
| `1 0 Type SeqNR` | `01` | S-frame (supervisory) | RR/REJ/RNR + N(R) |
| `1 1 Type N(R)` | `11` | U-frame (unnumbered) | SABM, DISC, UA, FRMR, etc. |

The **FCS** is computed over the unstuffed bits of Address + Control + Information using CRC-CCITT (`x^16 + x^12 + x^5 + 1`, polynomial `0x1021`) or, for longer links, CRC-32 (`0x04C11DB7`). Critically, the FCS is calculated *before* stuffing and checked *after* destuffing — stuffing is a line-coding concern, transparent to the FCS logic. This is why a receiver must destuff before verifying the CRC.

### Transparency and the network layer

Bit stuffing is **transparent**: the network layer at both ends sees the exact bit sequence it handed down, with no escape bytes or reserved patterns to avoid. A payload may legally contain `0x7E`, `0xFF`, or any pattern; the link layer's job is to make that invisible. This is the property the textbook calls transparency, and it is what lets HDLC carry arbitrary binary data — images, encrypted traffic, compressed streams — without negotiation.

The cost is **content-dependent expansion**. With byte stuffing (PPP), a payload of all flag bytes roughly doubles the frame. With bit stuffing the worst case is bounded: a payload of all `1`s forces one stuffed `0` per 5 payload bits, i.e. ~20% expansion; for typical mixed data the rate is far lower. The textbook's 12.5% figure comes from reasoning per byte: an all-`1` byte `11111111` becomes `11111011 0...`, roughly one extra bit per eight payload bits.

### Clock recovery and minimum transition density

A physical receiver's phase-locked loop (PLL) needs **transitions** to stay synchronized to the sender's clock. A long run of `1`s (or `0`s) in NRZ encoding would produce a DC level with no edges, and the receiver's clock would drift. Bit stuffing guarantees that a `0` appears at least every six bit-times, bounding the maximum run of `1`s to five and guaranteeing a minimum transition density. This is the same reason **USB 1.1** stuffs a `0` after six consecutive `1`s and **CAN 2.0** stuffs after five identical bits — the rule is older than HDLC and is reused wherever a self-clocked line code must avoid long runs. The textbook explicitly cites USB for this reason.

### Abort, idle, and resynchronization

HDLC defines two more line conditions out-of-band of the stuffing rule:

- **Abort**: six or more consecutive `1`s (`01111111...`). This is not data — it is a signal that the sender is cancelling the frame mid-transmission. A receiver that sees six `1`s discards the partial frame and waits for the next flag.
- **Idle / mark idle**: a continuous stream of `1`s (no flags) is the idle channel state. The first flag after idle marks the start of the next frame.

These exist precisely because the stuffing rule reserves six `1`s as impossible-in-data. The sender "spends" that reserved pattern on two special signals: the flag (`01111110`) and the abort (`0111111x`). This is the elegance of the scheme — one forbidden run buys you delimiting, abort, and idle signaling all at once.

### Resynchronization after an error

The decisive advantage over byte count is **self-synchronization**. If a bit error corrupts a frame, the CRC will catch it and the frame is discarded — but the receiver has not lost its place, because the next `01111110` on the line is guaranteed to be a real flag (stuffing prevents the pattern in data). The receiver scans forward to the next flag and resumes. With byte count, a single bit flip in the length field desynchronizes the stream with no way to recover except timing out and re-anchoring — which is why byte count is never used alone.

`code/main.py` simulates this: it corrupts one bit in a stuffed stream, runs destuffing, and shows that the flag scanner still finds the next valid boundary where a byte-count receiver would be lost.

### Bit stuffing vs byte stuffing vs coding violations

| Method | Delimiter | Transparency mechanism | Self-sync after error? | Used by |
|---|---|---|---|---|
| Byte count | length field | none | No — length error loses stream | rarely alone |
| Byte stuffing | flag byte `0x7E` | escape byte `0x7D` before flags in data | Yes — scan for flag | PPP (RFC 1662) |
| Bit stuffing | flag `01111110` | insert `0` after five `1`s | Yes — scan for flag | HDLC, USB, CAN |
| Coding violation | reserved line code | physical-layer redundancy, no stuffing needed | Yes — reserved signals | 4B/5B (FDDI), Manchester |

Byte stuffing (PPP, RFC 1662) is byte-oriented and convenient for asynchronous octet links; bit stuffing is bit-oriented and works for any frame size including non-octet-aligned lengths — the textbook notes HDLC allows frames of, say, 30.25 bytes. Coding violations sidestep stuffing entirely by reserving signals that cannot appear in valid data, but they require a line code with redundancy (like 4B/5B's 16-of-32 used codes).

## Build It

1. Read `code/main.py`. It implements `stuff(bits)`, `destuff(bits)`, `find_flags(bits)`, and a full `HDLCFrame` parser.
2. Run it: `python3 code/main.py`. The demo reproduces the textbook Fig. 3-5 trace (original → line → stored), parses a sample HDLC frame into its fields, and runs a resynchronization test.
3. Inspect `stuff()`: confirm it scans bit by bit, counts consecutive `1`s, and inserts a `0` only when the count reaches five — never on the flag itself.
4. Inspect `destuff()`: confirm the inverse — five `1`s followed by a `0` drops the `0`; five `1`s followed by a `1` is flagged as a possible flag/abort.
5. Change the payload in the demo to all `1`s and rerun. Observe the ~20% expansion and verify round-trip equality still holds.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify transparency | Round-trip a payload containing `0x7E` and `0xFF`; confirm destuffed output equals input | No data byte is special; the flag never appears inside the stuffed payload |
| Confirm the stuffing rule | Count stuffed bits in the trace; each follows exactly five `1`s | Exactly one `0` after every run of five `1`s, never after four, never after six |
| Measure worst-case expansion | Stuff 8000 bits of all `1`s; ratio of output to input | ~1.2×, i.e. one stuffed bit per five payload bits |
| Detect an abort | Feed `01111111` into the flag scanner | Scanner flags six `1`s as abort, not as a flag |
| Recover after a bit error | Flip one payload bit, then scan for the next flag | Receiver re-anchors at the next real flag; byte-count would be lost |
| Parse an HDLC frame | Decompose a hex frame into Flag/Address/Control/Info/FCS/Flag | Field widths match ISO 13239; FCS computed over pre-stuffing bits |

## Ship It

Produce one artifact under `outputs/prompt-bit-stuffing-hdlc-frames.md`:

- A worked bit-stuffing trace for a payload you choose (at least 32 bits), showing original, on-line, and stored forms with every stuffed bit annotated.
- An HDLC frame decomposition of a 12-byte sample frame, with each field labeled and the FCS region identified.
- A short analysis: under what payload distribution does bit stuffing cost the most, and why USB/CAN reuse the rule.

Start from the printed output of `code/main.py` and annotate it.

## Exercises

1. Stuff the bit string `0111111011111101111100` by hand. Identify every position where a `0` is inserted, write the line form, then destuff it and confirm you recover the original. Where would a naive scanner that stuffs after *four* `1`s go wrong?
2. A payload of 8000 bits is transmitted over an HDLC link. Compute the minimum and maximum number of stuffed bits, and the corresponding line-length range. What payload content produces each extreme?
3. You receive the line sequence `...01111101001111110...`. Is the second `01111110` a real frame boundary, or could it be data? Justify by destuffing the preceding bits and stating whether a stuffed `0` was removed.
4. Compare HDLC bit stuffing and PPP byte stuffing (RFC 1662, escape `0x7D`) for carrying a 1500-byte IPv4 packet that is mostly ASCII text versus a 1500-byte encrypted payload. Which expands more, and by roughly how much in each case?
5. Design the receiver state machine: states Hunt (searching for flag), Receive (in frame, destuffing), and Abort (six `1`s seen). Give the transitions on each input bit and the action taken. What event returns the receiver to Hunt?
6. A sender aborts a frame by transmitting six `1`s mid-payload. Explain why the receiver cannot confuse this with a stuffed-data situation, and trace what the receiver does with the partial frame and its CRC.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Flag | "the delimiter" | The 8-bit pattern `01111110` (`0x7E`) that marks the start and end of every HDLC frame; reserved by the stuffing rule |
| Bit stuffing | "adding zeros" | Inserting a `0` after any five consecutive `1`s in the payload so the flag pattern can never appear in data |
| Transparency | "data-agnostic" | The property that the payload may contain any bit pattern, including `0x7E`, and the network layer sees it unchanged |
| FCS | "the checksum" | Frame Check Sequence — CRC-16-CCITT or CRC-32 computed over Address+Control+Information *before* stuffing, verified *after* destuffing |
| Abort | "killing a frame" | Six or more consecutive `1`s; a sender signal to discard the in-progress frame, made unambiguous by the stuffing rule |
| Control field | "the type byte" | 8/16-bit field encoding I/S/U frame class plus N(S), N(R), and P/F bit |
| P/F bit | "poll or final" | A single bit in the control field: Poll when primary solicits a response, Final when secondary finishes its response |
| Coding violation | "physical-layer trick" | Using reserved line signals (impossible in valid data, e.g. unused 4B/5B codes) to delimit frames with no stuffing at all |
| Resynchronization | "getting back in sync" | A lost receiver scanning the line for the next flag, guaranteed to be a real boundary because stuffing forbids the pattern in data |
| Mark idle | "channel quiet" | A continuous stream of `1`s indicating an idle channel; the first flag after idle starts the next frame |

## Further Reading

- **ISO/IEC 13239** — Information technology — High-level Data Link Control (HDLC) procedures (the current HDLC standard, superseding ISO 3309).
- **ISO/IEC 3309** — Original HDLC frame structure definition.
- **RFC 1662** — PPP in HDLC-like Framing, defining byte-stuffed PPP frames with `0x7E`/`0x7D` (the byte-oriented counterpart to this lesson).
- **ITU-T Q.921** — ISDN LAP-D, an HDLC derivative showing the Address/Control/FCS layout in a real WAN protocol.
- **USB 1.1 Specification, Chapter 7** — Bit stuffing after six consecutive `1`s for clock recovery.
- **ISO 11898 (CAN 2.0)** — Controller Area Network bit stuffing after five identical bits.
- Tanenbaum, Feamster & Wetherall, *Computer Networks*, 6th ed., Section 3.1.2 (Framing) and the HDLC/PPP comparison near the end of Chapter 3.
- Stallings, *Data and Computer Communications*, HDLC chapter for the full I/S/U frame taxonomy.
