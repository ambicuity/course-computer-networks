# SONET/SDH STS-1 Frame and Overhead

> The basic SONET channel is the **STS-1** (Synchronous Transport Signal 1) frame: a 90-column × 9-row rectangle of 810 bytes emitted every **125 µs**, for a gross rate of **51.840 Mbps** (8000 frames/s, locked to the PCM voice sampling clock). The first three columns carry 27 bytes of transport overhead split into a **section overhead** (rows 1–3: A1/A2 framing 0xF6 0x28, B1 BIP-8, C1 STS-ID, D1–D3 datacom, E1 orderwire, F1 user channel) and a **line overhead** (rows 4–9: H1/H2/H3 pointer, B2 BIP-8, K1/K2 APS, D4–D12 datacom, S1/Z1 sync, E2 orderwire). The remaining 87 columns are the **Synchronous Payload Envelope (SPE)** — 783 bytes, 50.112 Mbps — whose first column is the end-to-end **path overhead** (J1 trace, B3 BIP-8, C2 signal label, G1 REI, F2, H4 multiframe, Z3/Z4/N1), leaving 774 bytes (49.536 Mbps) of user data. The SPE is **floating**: a 10-bit offset in the **H1/H2** pointer tells the receiver where the SPE begins (offset 0–782), so a payload can start anywhere and even **span two back-to-back frames**; **H3** absorbs one byte during negative justification and a stuff byte is inserted after H3 during positive justification. SDH (ITU-T G.707–G.709) is the SONET counterpart starting at STM-1 = STS-3. The failure mode this machinery prevents is loss of byte alignment on a continuous, gapless bit stream where the payload and the transport clock drift relative to each other. This lesson builds a runnable STS-1 frame model that lays out every overhead byte, encodes/decodes the H1/H2 pointer, runs BIP-8 parity checks, and demonstrates the floating SPE.

**Type:** Lab
**Languages:** Python, packet traces
**Prerequisites:** PCM and the 64 kbps voice channel, TDM and the T1/E1 carrier, fiber-optic transmission basics
**Time:** ~80 minutes

## Learning Objectives

- Draw the STS-1 frame as 90 columns × 9 rows and account for every one of the 810 bytes across section, line, path overhead and user payload.
- Compute the gross (51.840), SPE (50.112), and user (49.536) Mbps rates from the 125 µs frame period and the 8000 frames/s cadence.
- Name the byte-level functions of the three overhead sublayers: A1/A2 framing, B1/B2/B3 BIP-8, the H1/H2/H3 pointer, K1/K2 APS, J1 trace, C2 signal label, G1 REI.
- Encode and decode the H1/H2 pointer offset (0–782), and explain positive vs negative justification and what role H3 plays.
- Explain why the SPE can float and span two consecutive frames, and why that matters for multiplexing traffic that arrives asynchronously.
- Distinguish SONET STS-n / OC-n from SDH STM-n, including the OC-3c concatenated case and the column-interleaving rule.

## The Problem

A long-distance carrier lights a single-mode fiber between two cities and needs to carry thousands of digitized voice calls plus leased-line data on it. The fiber emits a continuous bit stream with no gaps, every transmitter and receiver is locked to a master clock good to about 1 part in 10⁹, but the tributary traffic (T1s, packet flows, ATM cells) arrives on its own clock that drifts slightly relative to the line. The receiver sees an unending river of bits: **how does it know where a frame starts, where the payload inside that frame starts, and how it stays locked when the payload clock slips half a byte against the line clock?**

A fixed-position payload would require buffering every tributary to the line clock and would waste a whole frame whenever traffic arrives mid-frame. SONET's answer is a fixed transport frame for clock recovery and framing, with a **floating payload envelope** carried by a **pointer** — the payload can begin anywhere and can be nudged one byte at a time by justification without ever losing byte alignment. Getting this right is the difference between a clean 51.84 Mbps STS-1 and a link that drops frames every time a tributary clock jitters.

## The Concept

### The 90 × 9 frame and the 125 µs cadence

SONET is a synchronous TDM system: one 810-byte frame is emitted every **125 µs**, exactly the PCM sampling interval, so 8000 frames/s match the 8000 samples/s of every 64 kbps voice channel. The frame is drawn as 90 columns wide and 9 rows high, transmitted row by row, left to right. `code/main.py` models this as a 9×90 byte grid and verifies the arithmetic:

| Quantity | Value | Derivation |
|---|---|---|
| Frame size | 810 bytes | 90 × 9 |
| Frame period | 125 µs | 1 / 8000 s |
| Gross rate | 51.840 Mbps | 810 × 8 × 8000 |
| Transport overhead | 27 bytes / 1.728 Mbps | 3 cols × 9 rows |
| SPE | 783 bytes / 50.112 Mbps | 87 × 9 |
| Path overhead | 9 bytes / 0.576 Mbps | 1 col of SPE |
| User payload | 774 bytes / 49.536 Mbps | 86 × 9 |

All higher SONET rates are exact multiples of STS-1; there is no rounding or stuffing at the multiplex boundary, which is what makes the hierarchy clean. The layout is shown in `assets/sonet-sdh-sts-1-frame-and-overhead.svg`.

### The three overhead sublayers

The first three columns (27 bytes) are transport overhead, split by who generates and terminates them:

| Sublayer | Rows | Generated/checked at | Key bytes |
|---|---|---|---|
| **Section overhead (SOH)** | 1–3 | Each regenerator / section endpoint | A1, A2 framing; C1 STS-ID; B1 BIP-8; D1–D3 datacom (192 kbps); E1 orderwire; F1 user channel |
| **Line overhead (LOH)** | 4–9 | Each line / STS-1 multiplex endpoint | H1, H2, H3 pointer; B2 BIP-8; K1, K2 APS; D4–D12 datacom (576 kbps); S1/Z1 sync status; Z2; E2 orderwire |
| **Path overhead (POH)** | 1st column of SPE | End to end across the path | J1 trace; B3 BIP-8; C2 signal label; G1 REI/RDI; F2 user; H4 multiframe; Z3, Z4; N1 |

The sublayering reflects the equipment hierarchy: a **section** is a single fiber span between regenerators; a **line** is the managed connection between STS-1 multiplexers that may contain several sections; a **path** is the end-to-end logical circuit that may traverse many lines. B1 is recomputed at every regenerator, B2 at every line endpoint, B3 only at the path endpoints — so a fault can be localized to whichever sublayer's BIP-8 first reports the mismatch.

### Framing: A1/A2 and frame synchronization

Because the bit stream is continuous and gapless, the receiver must find frame boundaries by content. The first two bytes of every frame are the fixed pattern **A1 = 0xF6** followed by **A2 = 0x28**. The receiver hunts for this 16-bit pattern; if it finds it in the same position across many consecutive frames (the standard requires N consecutive matches, e.g. 24 in common implementations), it declares frame sync. A malicious or unlucky payload could in principle contain 0xF6 0x28 at a regular cadence, but byte-interleaved multiplexing of many tributaries makes a sustained false lock statistically negligible. `code/main.py` seeds `A1`/`A2` in `make_idle_frame()` so the demo frame carries a valid framing word.

### The pointer: H1, H2, H3 and the floating SPE

The 783-byte SPE does not have to begin at row 1, column 4. Its start is given by a **10-bit offset** carried in the **H1** and **H2** bytes of row 4: H1 holds the high 2 bits (plus a 4-bit New Data Flag and a 2-bit SS type field), H2 holds the low 8 bits, giving an offset range of **0–782**. The offset is measured in bytes from the byte immediately after the **H3** byte (row 4, column 3).

| H1/H2 field | Width | Meaning |
|---|---|---|
| NDF (New Data Flag) | 4 bits | Normal = 0110; 1001 marks a new pointer value (concatenation/slip event) |
| SS | 2 bits | 10 for STS-1 |
| Offset | 10 bits | SPE start in bytes after H3, range 0–782 |

Because the offset can point anywhere in the SPE area and the SPE area wraps row-major across the 9 rows, an offset near the end of the range makes the SPE **span two consecutive frames**: the tail of the SPE finishes in the next frame's payload area. `code/main.py`'s `locate_spe_start()` maps an offset to a (row, payload-column) and the `offset=780` case in the demo prints a spanning SPE. This floating design lets a payload that arrives mid-frame be inserted immediately instead of waiting for the next frame boundary — the textbook's point that "if a payload arrives while a dummy frame is being constructed, it can be inserted into the current frame."

### Justification: absorbing clock drift one byte at a time

Tributary and line clocks drift. SONET absorbs the difference with **pointer justification** — single-byte adjustments signalled in the H1/H2 bits, with H3 as the action byte:

| Event | Direction | Mechanism | Effect on offset |
|---|---|---|---|
| **Negative stuffing** | Payload runs early | The H3 byte carries one real payload byte; SPE shrinks by one | offset − 1 |
| **Positive stuffing** | Payload runs late | A dummy stuff byte is inserted right after H3; SPE grows by one | offset + 1 |
| No change | Aligned | Pointer unchanged | offset unchanged |

In real silicon the 10 offset value bits are interleaved with **I** (increment) and **D** (decrement) stuffing bits: to request positive stuffing the transmitter inverts the I bits for one frame, the receiver acts and the offset increments by one; negative stuffing inverts the D bits and H3 carries real data. `code/main.py`'s `pointer_stuff()` models the net effect (±1 on the offset) and `build_pointer_word()`/`decode_pointer_word()` round-trip the encoded value so you can see H1=0x68/H2=0x00 decode back to offset 0.

### Error monitoring: BIP-8 at three sublayers

SONET uses **BIP-8** (Bit Interleaved Parity, 8 bits): the transmitter computes even parity of bit position k across all covered bytes and places the resulting 8-bit code in the overhead; the receiver recomputes and compares. A mismatch on bit k means an odd number of bit-k errors occurred in the covered block since the last check.

| Byte | Sublayer | Coverage |
|---|---|---|
| **B1** | Section | All 810 bytes of the *previous* frame |
| **B2** | Line | All bytes of the line overhead + the SPE in the previous STS-1 frame (one B2 per STS-1) |
| **B3** | Path | All bytes of the SPE in the previous frame |

BIP-8 detects an odd number of errors per bit position but cannot correct them and misses even-numbered errors on the same bit — so it is a monitoring tool that drives the **G1** far-end block error (REI) and remote defect indication (RDI) signals, not a recovery mechanism. The demo's `_demo_bip8()` computes a BIP-8 over a deterministic payload, flips one bit, and shows the recomputed parity differs — exactly how B1/B2/B3 flag a section/line/path error.

### The SONET/SDH multiplex hierarchy

Higher rates are exact multiples of STS-1. The electrical signal is **STS-n**, the optical signal is **OC-n** (bit-identical modulo a scrambling/reordering for clock density), and the SDH equivalent is **STM-n**. SDH starts at STM-1 = STS-3 because ITU systems had no native 51.84 Mbps rate.

| STS | OC | SDH | Gross (Mbps) | SPE (Mbps) | User (Mbps) |
|---|---|---|---|---|---|
| STS-1 | OC-1 | — | 51.840 | 50.112 | 49.536 |
| STS-3 | OC-3 | STM-1 | 155.520 | 150.336 | 148.608 |
| STS-12 | OC-12 | STM-4 | 622.080 | 601.344 | 594.432 |
| STS-48 | OC-48 | STM-16 | 2488.320 | 2405.376 | 2377.728 |
| STS-192 | OC-192 | STM-64 | 9953.280 | 9621.504 | 9510.912 |
| STS-768 | OC-768 | STM-256 | 39813.120 | 38486.016 | 38043.648 |

An **OC-3c** (concatenated) signal is a single 155.52 Mbps stream rather than three separate OC-1s: its payload is one wide SPE carried by a single pointer, and the three STS-1s are interleaved **column by column** (column 1 of stream 1, then column 1 of stream 2, then column 1 of stream 3, then column 2 of stream 1, …) giving a frame 270 columns wide and 9 rows deep. Non-concatenated OC-3 carries three independent STS-1s, each with its own pointer and path overhead.

## Build It

1. Read `code/main.py`. It models the STS-1 frame as a 9×90 byte grid with separate accessors for the 3-column overhead block and the 87-column SPE.
2. Run it: `python3 code/main.py`. Confirm the overhead layout (A1/A2/B1/…/H1/H2/H3/…/K1/K2), the rate budget (51.840 → 50.112 → 49.536 Mbps), and the pointer round-trip.
3. Inspect `build_pointer_word()` / `decode_pointer_word()`: encode offset 522 and verify H1=0x6A H2=0x0A decodes back to 522 with the SPE starting at row 1, payload column 1.
4. Run the BIP-8 demo: a one-bit flip in the payload changes the recomputed parity, mirroring how B1/B2/B3 report an error to the far end via G1.
5. Inspect the floating-SPE demo at offset 780: only 3 bytes of the SPE fit in the current frame; the remaining 780 wrap into the next frame — the spanning case drawn in the SVG.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify framing | A1=0xF6, A2=0x28 in row 1 cols 1–2, stable across N frames | Receiver locks frame sync; no out-of-frame alarm |
| Locate the SPE | H1/H2 decode to offset 0–782; SPE start row/column match | Offset is consistent frame to frame unless a slip occurred |
| Confirm rate budget | 810×8×8000 = 51.84 Mbps gross; 774×8×8000 = 49.536 Mbps user | Transport OH = 1.728 Mbps, path OH = 0.576 Mbps reconcile exactly |
| Detect a section error | B1 recomputed ≠ B1 received; G1 REI count increments | The bit position that differs tells which parity column caught the error |
| Diagnose clock drift | Pointer increments (positive stuffing) or decrements (negative stuffing) frequently | Occasional justification is normal; continuous slip means tributary clock is out of spec |
| Read an STM-1 | Three column-interleaved STS-1s, one 270-column frame, single pointer if OC-3c | STM-1 gross = 155.520 Mbps = 3 × 51.840 |

## Ship It

Produce one artifact under `outputs/`:

- `outputs/prompt-sonet-sdh-sts-1-frame-and-overhead.md` — an annotated STS-1 frame dump: the 9×90 grid with every overhead byte labeled, the H1/H2 pointer decoded, a BIP-8 computation over a sample payload, and a worked justification event (one positive, one negative) showing the offset change and the role of H3. Start from the printed output of `code/main.py` and annotate it with the failure mode you tested (a forced bit flip driving a B1 mismatch, and a forced clock slip driving a pointer adjustment).

## Exercises

1. A receiver sees A1=0xF6 A2=0x28 in the correct position for 3 consecutive frames, then a single corrupted frame where A2=0x29. Walk through the sync state machine: does it drop out of frame immediately? What is the role of the consecutive-match threshold?
2. Encode the pointer for offset 300 by hand from the H1/H2 layout (NDF=0110, SS=10), and verify against `build_pointer_word(300)`. Now set the NDF to 1001 — what event in the network would cause a transmitter to assert the New Data Flag?
3. A tributary clock runs slightly fast relative to the line clock, so payload accumulates faster than frames can carry it. Over 10 frames you observe the pointer move 522 → 521 → 520 → 519 → 518. Which justification direction is this, what byte carries real payload each time, and what would eventually happen if the drift exceeds one byte per frame?
4. Compute the user payload rate of an OC-3c (concatenated) link and compare it to three separate OC-1s. Why does concatenation save exactly the overhead of two path-overhead columns plus two pointers?
5. A BIP-8 check at B2 reports a mismatch but B1 (section) is clean. Where is the fault located, and why does the sublayering of B1/B2/B3 let you localize it?
6. An STM-1 frame is 270 columns × 9 rows. Describe the column-interleaving order of three STS-1s that produces it, and explain why SDH has no equivalent of a standalone OC-1.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| STS-1 | "the basic SONET rate" | The 90×9, 810-byte, 125 µs frame at 51.840 Mbps gross; the building block every higher SONET rate is a multiple of |
| SPE | "the payload area" | Synchronous Payload Envelope — 783 bytes (87 columns × 9 rows) that floats inside the frame and carries the path overhead plus user data |
| Pointer (H1/H2/H3) | "an offset field" | A 10-bit offset (0–782) in H1/H2 giving the SPE start in bytes after H3; H3 is the justification action byte for negative stuffing |
| Section overhead | "regenerator overhead" | Rows 1–3 of the transport OH, terminated at each regenerator; carries A1/A2 framing, B1 BIP-8, D1–D3 datacom |
| Line overhead | "the mux overhead" | Rows 4–9 of the transport OH, terminated at STS-1 line endpoints; carries the pointer, B2 BIP-8, K1/K2 APS |
| Path overhead | "end-to-end header" | The first column of the SPE, carried end to end; J1 trace, B3 BIP-8, C2 signal label, G1 REI/RDI |
| BIP-8 | "a checksum" | Bit Interleaved Parity over 8 bit positions: bit k = even parity of bit k across all covered bytes; detects odd errors per bit, no correction |
| Justification | "stuffing" | Single-byte pointer adjustment (positive: +1 with a stuff byte; negative: −1 with H3 carrying real data) that absorbs tributary/line clock drift |
| OC-n / STS-n | "the optical line" | OC-n is the optical signal; STS-n is the electrical frame that is bit-identical modulo scrambling; both are n × STS-1 |
| OC-3c | "a fat OC-3" | Concatenated OC-3: one 155.52 Mbps stream with a single SPE and single pointer, column-interleaved into a 270×9 frame |
| STM-n | "the SDH rate" | SDH equivalent of STS-n; starts at STM-1 = STS-3 because ITU had no native 51.84 Mbps rate |

## Further Reading

- **ANSI T1.105** — SONET — Basic Description including Multiplex Structure, Rates, and Formats (the STS-1 frame definition).
- **ITU-T G.707** — Network node interface for the synchronous digital hierarchy (SDH); the STM-n frame and pointer rules.
- **ITU-T G.708 / G.709** — SDH sub-STM-0 and convergence of SONET/SDH; interfaces for the optical transport network (OTN).
- **Bellamy, *Digital Telephony*, 3rd ed., Wiley, 2000** — the canonical SONET/SDH reference, especially the pointer and justification chapters.
- **Goralski, *Sonet/SDH*, 3rd ed., McGraw-Hill, 2002** — overhead byte-by-byte walkthrough and APS (K1/K2) operation.
- **Shepard, *Sonet/SDH Demystified*, McGraw-Hill, 2001** — practical framing, BIP-8, and pointer maintenance.
- **Tanenbaum & Wetherall, *Computer Networks*, 5th ed., Chapter 2, Section 2.6.4 (Trunks and Multiplexing, SONET/SDH).**
- **RFC 2615** — PPP over SONET/SDH, which defines how IP packets are framed inside an STS payload using HDLC-like framing — a direct user of the SPE modeled here.
