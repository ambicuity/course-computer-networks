# Physical-layer coding violations for frame delimiting

> The data link layer receives a raw, unbounded bit stream from the physical layer and must cut it into frames without any out-of-band message saying "frame starts here." The four textbook answers are byte count, flag bytes with byte stuffing (PPP, RFC 1662), flag bits with bit stuffing (HDLC flag `01111110`, the same rule USB uses to guarantee transition density), and **physical-layer coding violations** — the only method that needs no stuffing at all. A line code like **4B/5B** (FDDI, Fast Ethernet) maps 4 data bits onto 5 line bits, leaving 16 of 32 codewords unused; reserved "control" symbols such as `J`, `K`, `T`, `R`, and the `H` (halt) symbol can never appear in payload, so a receiver can find frame boundaries by spotting a pattern that is *syntactically illegal as data*. 8B/10B (gigabit Ethernet, PCIe, USB 3) works identically with comma characters; 64B/66B (10G Ethernet) delimits blocks with a 2-bit sync header that is not part of the 64-bit payload. The payoff is transparency: because the delimiter is a signal the data can never produce, no escape byte or stuffed bit is ever inserted, frame length is data-independent, and resynchronization after an error is a simple scan for the reserved pattern. Real links combine methods — an 802.3 frame opens with a 7-byte preamble plus a 1-byte Start-of-Frame Delimiter (`0xAB`), then carries a length field; 802.11 uses a 72-bit preamble plus a SIGNAL header. This lesson builds a 4B/5B encoder with reserved control symbols and a frame scanner that finds boundaries purely from coding violations.

**Type:** Learn
**Languages:** Python
**Prerequisites:** Framing with byte/byte stuffing and bit stuffing (Phase 4 framing lessons), line codes and NRZI/Manchester modulation (Phase 2 physical layer)
**Time:** ~75 minutes

## Learning Objectives

- Explain why a coding violation can delimit a frame without any stuffing, and why byte-count and flag-byte methods cannot.
- Encode and decode the 4B/5B table including the 12 unused control symbols, and identify which codewords are illegal as data.
- Trace an FDDI/100BASE-TX frame from idle (`I`) symbols through `J`, `K`, payload, and the terminating `T` pair, naming each reserved symbol's role.
- Given a 10GBASE-R 64B/66B block, read the 2-bit sync header and explain why it can never collide with payload.
- Compute the bandwidth overhead of 4B/5B (25%), 8B/10B (25%), and 64B/66B (~3.125%) and justify the trade-off each generation made.
- Diagnose a framing loss: distinguish a garbled length field from a missing coding violation and pick the recovery scan.

## The Problem

A network card's PHY hands the MAC a 155.52 Mbit/s stream of bits from an FDDI fiber. There are no frame markers in the bits themselves — just a tide of 0s and 1s. The MAC must find where each frame begins and ends so it can compute a checksum and hand a clean payload to the network layer. The obvious approach, putting a byte count in the header, fails the moment a single bit flip corrupts the count: the receiver reads "127" instead of "7," skids forward 120 bytes, and loses sync on *every* subsequent frame until something forces a resync. Flag bytes (`0x7E`) fix resync but force byte stuffing, which inflates a payload of pure flag bytes to double its size and ties framing to 8-bit boundaries. Bit stuffing (HDLC) is byte-agnostic but still grows the frame by up to ~12.5% and forces the receiver to track 5-1s-in-a-row state. The engineer wants a delimiter that the data physically cannot produce, so framing costs zero payload overhead and resync is a pure pattern match. That delimiter is a **coding violation**: a signal reserved by the line code and therefore forbidden inside data.

## The Concept

### Why byte count and flag bytes leave residue

| Method | Delimiter | Failure mode | Stuffing | Overhead |
|---|---|---|---|---|
| Byte count | Length field in header | One bit flip in the count desyncs all later frames | none | 0%, but unrecoverable after error |
| Flag + byte stuffing (PPP, RFC 1662) | `0x7E`, escape `0x7D` | Need to escape `0x7E` and `0x7D` in payload | yes | up to 100% on adversarial payload |
| Flag + bit stuffing (HDLC, USB) | `01111110` | Insert a 0 after any five 1s in payload | yes | up to ~12.5% |
| Coding violation (4B/5B, 8B/10B) | Reserved control symbol | Cannot occur in data by construction | none | built into line code |

The first three all share a defect: the delimiter is a *legal data pattern*, so the sender must rewrite the payload to keep it distinguishable. The fourth removes the collision at the source — the line code's alphabet simply has no codeword for the delimiter inside the data space.

### Line codes and the unused code space

A line code maps *n* data bits onto *m* line bits with *m > n* to guarantee enough transitions for clock recovery and DC balance. Because 2^m > 2^n, many of the *m*-bit codewords are unused — they correspond to no *n*-bit data value. The encoder's table is intentionally sparse, and the unused slots become the "control" vocabulary.

The canonical example is **4B/5B** (ANSI X3T9.5, used by FDDI and the MII of 100BASE-TX). 4 data bits → 5 line bits, so 16 of 32 codewords encode data and 16 are free for control and idle.

### The 4B/5B table, data and control symbols

| Data (hex) | 5B code | Symbol | | Control symbol | 5B code | Meaning |
|---|---|---|---|---|---|---|
| 0 | `11110` | 0 | | `I` (Idle) | `11111` | Line idle, continuous transitions |
| 1 | `01001` | 1 | | `H` (Halt) | `00100` | Transmit halt / error |
| 2 | `10100` | 2 | | `J` (Start-1) | `11000` | First byte of Starting Delimiter |
| 3 | `10101` | 3 | | `K` (Start-2) | `10001` | Second byte of Starting Delimiter |
| 4 | `01010` | 4 | | `T` (End) | `01101` | Terminating delimiter byte |
| 5 | `01011` | 5 | | `R` (Reset) | `00111` | Second byte of `T,R` end pair / line reset |
| 6 | `01110` | 6 | | `Q` (Quiet) | `00000` | Line quiet (no transitions) |
| 7 | `01111` | 7 | | unused | `11001`,`11010`,`11011`,`10110`,`10111` | illegal as data |
| 8 | `10010` | 8 | | | | |
| 9 | `10011` | 9 | | | | |
| A | `10110` | A | | | | |
| B | `10111` | B | | | | |
| C | `11010` | C | | | | |
| D | `11011` | D | | | | |
| E | `11100` | E | | | | |
| F | `11101` | F | | | | |

Notice `J` (`11000`) and `K` (`10001`) are not in the data column — no 4-bit value maps to them. They are **coding violations**: a sequence of bits that the encoder is structurally forbidden to emit as a data nibble. Their presence on the wire therefore unambiguously signals "this is control, not payload." `code/main.py` builds exactly this table and rejects any attempt to encode a control symbol as data.

### FDDI frame delimiting with J, K, T, R

An FDDI frame is bracketed by reserved symbol pairs rather than flag bytes:

```
Idle...Idle | J K  FC  DA  SA  ...  payload  ...  FCS | T R | Idle...Idle
            ^SD                                ^ED
```

- `J K` — the **Starting Delimiter (SD)**: two consecutive reserved symbols (`11000 10001`). Because no nibble of payload can be `J` or `K`, the receiver finds frame start by scanning for the `J,K` pair. No stuffing required.
- `T R` — the **Ending Delimiter (ED)**: `T` (`01101`) is reserved, `R` (`00111`) is the reset/second byte. A frame ends where `T` appears.
- `I` (`11111`) fills the gaps with idle, keeping the receiver's clock locked between frames.

Because `J`, `K`, `T` are absent from the data alphabet, a payload of all-`0xFF` bytes, a payload of all-`0x00` bytes, and a payload that happens to contain the bit pattern `1100010001` are all delivered verbatim — the encoder cannot produce `J` or `K` from any 4-bit input, so the delimiter can never be synthesized accidentally. This is the textbook's point: "because they are reserved signals, it is easy to find the start and end of frames and there is no need to stuff the data."

### 8B/10B and the comma character

Gigabit Ethernet (1000BASE-X), Fibre Channel, PCIe gen 1–2, and USB 3.0's older cousin all use **8B/10B** (Widmer & Franaszek, IBM). 8 data bits → 10 line bits, giving 1024 codewords for 256 data values plus a rich control set. The key reserved construct is the **comma** — a 7-bit bit pattern (`0011111` or `1100000`, plus its rotation) that appears in exactly one control codeword and never spans a data codeword boundary. The comma is the alignment marker: when the receiver sees it, it knows it is on a correct 10-bit codeword boundary and can lock its descrambler. Control symbols `K28.5` (the comma, used as a frame-start / idle delimiter) and `K28.3`, `K28.6` (frame end) are the coding-violation delimiters of the 8B/10B world. 8B/10B also runs a **running disparity** counter so the long-term DC stays balanced — a data-independent property byte/flag stuffing cannot offer.

### 64B/66B: delimiting with a 2-bit sync header

At 10 Gbit/s the 25% overhead of 8B/10B is too expensive. **64B/66B** (IEEE 802.3 Clause 49, 10GBASE-R) carries 64 payload bits with only a 2-bit **sync header**: `01` for a data block, `10` for a control block. The header itself is the coding violation — `01` and `10` are valid 2-bit patterns, but the block structure forces the receiver to interpret bits 0–1 as a header, never as payload. A `01` block is eight data bytes; a `10` block carries a block type field and mixed control/data. Because the header is positional and never part of the payload, no stuffing exists and overhead is 2/64 ≈ 3.125%. Frame start/end within the 64B/66B stream use control block types (`S` start, `T` terminate) that are again reserved. `code/main.py` includes a 64B/66B block encoder showing the sync-header discipline.

### Combining methods: the Ethernet and 802.11 pattern

Real links rarely trust one mechanism. As the textbook notes, Ethernet and 802.11 combine a long preamble (so the receiver's AGC and clock-recovery PLL lock) with a coding-violation delimiter and a length field:

| Link | Preamble | Start delimiter | Length |
|---|---|---|---|
| 802.3 Ethernet | 7 bytes `0x55` (alternating) | 1 byte SFD `0xD5` (`10101011`) — the violated `...11` ending | Length/type field in header |
| 802.11 Wi-Fi | 72 bits (PLCP preamble) | SIGNAL field + coded header | Length in SIGNAL (`LENGTH` × 4 µs) |
| FDDI | `I` idle symbols | `J K` coding violation | — |
| 1000BASE-X | `/I/` idle (8B/10B) | `/S/` start (8B/10B control) | Length/type in MAC header |

The SFD `0xD5` is a coding violation in a Manchester-encoded preamble: the preamble is `10101010...` with a transition in the middle of every bit; the SFD's final `11` breaks that rhythm and the receiver latches on it. Layered defense — preamble to lock the clock, coding violation to mark the boundary, length to find the end — is why a single bit error rarely costs more than one frame.

### Worked example: overhead on a 1000-byte FDDI payload

A 1000-byte payload is 2000 nibbles. Over 4B/5B that becomes 2000 × 5 = 10 000 line bits = 1250 bytes on the wire, plus 2 symbols (`J,K`) = 10 bits for the SD and 2 symbols (`T,R`) = 10 bits for the ED. Total line bits = 10 020, payload bits = 8000, framing+code overhead = (10 020 − 8000)/8000 = 25.25%. The framing portion alone (`J,K,T,R`) is 20 bits = 0.25% of the payload — stuffing-free. Contrast with byte stuffing on the same payload if it were all `0x7E`: 1000 bytes → ~2000 bytes of stuffed payload, 100% overhead. `code/main.py` computes this comparison.

## Build It

1. Open `code/main.py`. It implements the full 4B/5B data table plus the `J,K,T,R,I,H,Q` control symbols and rejects illegal codewords.
2. Run `python3 code/main.py`. You will see: (a) the data/control tables, (b) an FDDI frame built around a sample payload with `J,K ... T,R` delimiters, (c) a scanner that finds the `J,K` pair in a synthetic idle+payload+idle stream and reports the payload nibbles between `J,K` and `T`, and (d) an overhead comparison between coding-violation framing and byte stuffing.
3. Edit `SAMPLE_PAYLOAD` to a byte string that contains `0x7E` (`~`) and `0xFF` repeatedly. Confirm the 4B/5B output is unchanged in structure — no stuffing appeared — while the byte-stuffing overhead balloons.
4. Inspect the `Block66B` encoder: feed it a data block and a control block and confirm the sync header is `01` vs `10` and the 64-bit payload is untouched.
5. Consult `assets/physical-layer-coding-violations-framing.svg` for the FDDI frame timeline showing `I` idle, `J K` start, payload, and `T R` end.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm a frame was delimited by coding violation | `J,K` symbol pair found at the start, `T` at the end; no escape bytes anywhere | The scanner returns the payload with zero stuffed symbols regardless of payload content |
| Verify transparency | Payload containing `11000 10001` (`J,K` bits) survives untouched | The encoder never emits `J`/`K` from data nibbles; only an explicit control call produces them |
| Compare overhead | 4B/5B line overhead ~25.25% on 1000 B; byte-stuff overhead up to 100% on `0x7E` payload | Coding-violation overhead is constant and tiny beyond the line code; stuffing is data-dependent and unbounded |
| Read a 64B/66B block | Sync header `01` = data, `10` = control; 64 payload bits intact | Header is positional, never extracted from payload, so no collision is possible |
| Diagnose framing loss | Scanner cannot find `J,K` after a noisy region | Receiver drops to idle hunt, scanning for the next reserved symbol pair rather than trusting a (possibly garbled) length |

## Ship It

Produce one artifact under `outputs/prompt-physical-layer-coding-violations-framing.md`:

- An annotated FDDI frame trace for a payload you choose, with every reserved symbol labeled (`I`, `J`, `K`, `T`, `R`) and the bit-level 5B codes shown.
- A side-by-side overhead table: coding-violation framing vs byte stuffing vs bit stuffing for three payloads (all-`0x00`, all-`0x7E`, random).
- A one-paragraph decision rule: when to pick a coding-violation delimiter vs a flag+stuffing delimiter given the available PHY.

Start from the printed output of `code/main.py` and annotate the boundary symbols.

## Exercises

1. A 4B/5B receiver has lost sync and is scanning an idle stream. It sees the bit sequence `11000 10001 01010 ...`. Which symbols did it find, and what does it conclude about frame state? What single bit error would make it misread the start delimiter?
2. Encode the byte `0xFF` in 4B/5B and show that the line bits contain the substring `11111` — the same 5 bits as the `I` (idle) symbol. Explain why this is *not* a framing collision, and what rule keeps idle and data distinct.
3. An FDDI frame carries a 1500-byte IP packet. Compute the total line bits including `J,K` start, `T,R` end, and the 4B/5B expansion. What fraction is pure framing (delimiters) versus line-code overhead?
4. A 10GBASE-R receiver sees a 66-bit block whose first two bits are `00`. Is this a valid data block, a valid control block, or an error? Justify from the 64B/66B sync-header rule and describe the receiver's next action.
5. Contrast the 802.3 SFD (`0xD5`, a Manchester rhythm break) with FDDI's `J,K` (reserved 4B/5B symbols). Both are "coding violations" — what exactly is being violated in each case, and why does neither require stuffing?
6. You are designing a 25 Gbit/s serial link and must choose between 8B/10B (25% overhead) and 64B/66B (3.125% overhead). Give two reasons beyond raw overhead that push you toward 64B/66B, and one reason 8B/10B's running-disparity guarantee is still attractive.
7. PPP uses flag byte `0x7E` with byte stuffing (RFC 1662). Explain precisely why PPP could not instead use a 4B/5B coding violation, and what property of the PPP-over-serial PHY forces the choice.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Coding violation | "an illegal signal" | A reserved line-code symbol (e.g. 4B/5B `J`=`11000`) that no data nibble can produce, used as a frame delimiter with zero stuffing |
| 4B/5B | "the FDDI code" | A line code mapping 4 data bits to 5 line bits; 16 of 32 codewords are data, the rest are idle/control/illegal |
| 8B/10B | "gigabit code" | 8 data bits → 10 line bits with running-disparity DC balance and a comma control character for block alignment |
| 64B/66B | "the 10G code" | 64 payload bits plus a 2-bit sync header (`01` data, `10` control); header is positional, overhead ~3.125% |
| Starting delimiter (SD) | "frame start" | The reserved symbol pair (`J,K` in FDDI, `/S/` in 1000BASE-X, SFD `0xD5` in 802.3) marking the first payload bit |
| Comma | "alignment marker" | A 7-bit 8B/10B pattern (`0011111`) appearing in exactly one control codeword, used to lock codeword boundaries |
| Running disparity | "DC balance" | The running count of 1s minus 0s in 8B/10B; the encoder picks the codeword polarity that drives it toward zero |
| Transparency | "data passes through" | The property that any payload bit pattern is delivered verbatim because the delimiter is unrepresentable as data |
| Idle (`I`) | "filler" | The `11111` 4B/5B symbol filling inter-frame gaps, keeping the receiver's clock-recovery PLL locked |
| Byte stuffing | "escaping flags" | Inserting an escape byte before a `0x7E` or `0x7D` in payload — the overhead coding violations eliminate |

## Further Reading

- **ANSI X3.166 / X3T9.5** — FDDI Physical Layer Medium Dependent (PMD); defines 4B/5B and the `J,K,T,R,I,H,Q` control symbols.
- **IEEE 802.3 Clause 24** — 100BASE-X physical coding sublayer (4B/5B over MII).
- **IEEE 802.3 Clause 36** — 1000BASE-X 8B/10B physical coding sublayer.
- **Widmer & Franaszek**, "A DC-Balanced, Partitioned-Block, 8B/10B Transmission Code," IBM J. R&D, 1983 — the original 8B/10B paper.
- **IEEE 802.3 Clause 49** — 64B/66B physical coding sublayer for 10GBASE-R.
- **RFC 1662** — PPP in HDLC-like Framing (flag `0x7E`, byte stuffing with `0x7D`).
- **ISO/IEC 7498-1 / ISO 8802-2** — HDLC frame structure with bit stuffing flag `01111110`.
- Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 3, Section 3.1.2 (Framing) — the four framing methods and the coding-violation shortcut.
