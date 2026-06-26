# Framing

> The physical layer hands the data link layer a raw bit stream that may be longer, shorter, or corrupted versus what was sent — framing is how the receiver recovers discrete, length-bounded units from it. Four classic methods exist: **byte count** (a length field in the header, used alone almost never because a single bit flip desynchronizes the receiver permanently), **flag bytes with byte stuffing** (PPP uses `0x7E` as the flag and `0x7D` as the escape with XOR-`0x20` transformation, per RFC 1662), **flag bits with bit stuffing** (HDLC and USB use the flag `01111110` = `0x7E` and stuff a `0` after every five consecutive `1`s), and **physical-layer coding violations** (4B/5B reserves unused symbols, so Fast Ethernet marks frame edges without touching the data). Real protocols combine them: Ethernet and 802.11 prepend a preamble (72 bits is typical for 802.11) plus a length field. Bit stuffing costs roughly 12.5% in the worst case; byte stuffing can nearly double a frame full of flag bytes. This lesson builds a working PPP-style byte-stuffer and an HDLC bit-stuffer so you can see exactly which bytes the transformation touches and prove round-trip transparency.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib stuffer/destuffer)
**Prerequisites:** Phase 3 · 01 (Data Link Layer Design Issues); binary/hex literacy
**Time:** ~75 minutes

## Learning Objectives

- Explain why a raw physical-layer bit stream is not self-delimiting and what "the receiver lost synchronization" means in concrete terms.
- Compare the four framing methods (byte count, byte stuffing, bit stuffing, coding violations) on resync cost, overhead, and byte/bit alignment.
- Trace PPP byte stuffing by hand: given a payload containing `0x7E` and `0x7D`, predict the exact on-wire bytes per RFC 1662, then verify with `code/main.py`.
- Apply HDLC bit stuffing: insert a `0` after five consecutive `1`s, show the `01111110` flag can never appear inside the data, and compute the worst-case 12.5% expansion.
- Identify the framing fields in a real Ethernet/802.11 capture (preamble, SFD, length) and explain why combining a preamble with a length field is safer than either alone.

## The Problem

A point-to-point serial link between two routers starts dropping into a state where the receiving router logs a flood of "bad FCS" (frame check sequence) errors and the link counters show far fewer frames received than the peer claims to have sent. The line is electrically fine — a single noise burst earlier corrupted one byte. Yet the errors persist long after the burst is gone.

The root cause is a framing failure, not a data-corruption failure. The receiver's data link layer is no longer aligned to frame boundaries: it is computing checksums over byte ranges that straddle two real frames, so every checksum fails. Until the receiver can re-find a frame boundary, the link is effectively dead even though the physical layer is delivering clean bits. Understanding framing tells you why a one-byte glitch can wedge a link, and why the protocol you chose (byte count vs. flag-based) determines whether the link self-heals in microseconds or stays broken.

## The Concept

The data link layer must turn a raw, unreliable bit stream into discrete **frames** so it can attach a checksum to each one and detect errors. The hard part is letting the receiver find the **start of each new frame** cheaply, using little channel bandwidth, and recovering quickly after any error. The diagram in [`assets/framing.svg`](../assets/framing.svg) lays the four methods side by side.

### Method 1 — Byte count

The header carries a field stating how many bytes follow. The receiver reads the count, then knows exactly where the frame ends and the next one begins.

```
Count                                   One byte each
+---+---+---+---+---+   +---+---+---+---+---+   +---+ ...
| 5 | A | B | C | D |   | 5 | E | F | G | H |   | 8 | ...
+---+---+---+---+---+   +---+---+---+---+---+   +---+ ...
  Frame 1 (5 bytes)        Frame 2 (5 bytes)      Frame 3 ...
```

**The fatal flaw:** if a bit flip turns the count `5` into `7`, the receiver consumes 7 bytes, lands in the middle of the *next* frame's data, reads a garbage value as the next count, and is now permanently desynchronized. Even a failing checksum does not help — the receiver knows the frame is bad but has no way to find where the next frame starts, and asking for retransmission is useless because it does not know how many bytes to skip. For this reason byte count is essentially **never used alone**. It survives only paired with a flag or preamble that gives an independent way to resync.

### Method 2 — Flag bytes with byte stuffing (PPP, RFC 1662)

Each frame begins and ends with a special **flag byte**. Two consecutive flags mark the end of one frame and the start of the next, so a lost receiver simply scans for the flag to resync — the killer feature byte count lacks.

The problem: the flag byte can appear inside binary payload data (photos, compressed audio). The fix is **byte stuffing** — the sender inserts an **escape byte** before any accidental flag in the data; the receiver strips the escape. If an escape byte itself appears in the data, it too is escaped.

PPP's concrete values (this is what `code/main.py` implements):

| Role | Value | On-wire encoding |
|------|-------|------------------|
| Flag | `0x7E` | data `0x7E` → `0x7D 0x5E` |
| Escape | `0x7D` | data `0x7D` → `0x7D 0x5D` |
| Control chars `<0x20` | e.g. `0x11` (XON) | `0x7D` + (byte XOR `0x20`) |

PPP escapes by emitting `0x7D` followed by the original byte **XOR `0x20`** (so `0x7E` → `0x7D 0x5E`, since `0x7E ^ 0x20 = 0x5E`). XOR `0x20` again on receive recovers the original. Worst case (a payload of all flag bytes) nearly **doubles** frame size, because every byte becomes two.

### Method 3 — Flag bits with bit stuffing (HDLC, USB)

Byte stuffing is tied to 8-bit bytes. HDLC frames at the **bit** level, so a frame can hold any number of bits. The flag is the bit pattern `01111110` (`0x7E`). To keep that pattern from appearing inside the data, whenever the sender emits **five consecutive `1` bits**, it stuffs a `0` afterward:

```
Original : 0110 11111 11111 11111 0010
On wire  : 0110 11111 0 11111 0 11111 0 0010    (0 stuffed after each run of five 1s)
Stored   : 0110 11111 11111 11111 0010          (receiver deletes the 0 after five 1s)
```

Because no run of six `1`s can ever survive on the wire, the flag `01111110` (which contains six `1`s) **cannot occur inside data** — only at real frame boundaries. This also guarantees a minimum density of `0→1` transitions, which the physical layer needs to keep its clock locked; that is precisely why **USB uses bit stuffing**. Worst case (all `1`s data) adds one bit per five, about a **12.5% expansion** versus byte stuffing's potential doubling.

### Method 4 — Physical-layer coding violations

Line codes add redundancy that leaves some signal patterns unused. In **4B/5B** (Fast Ethernet, FDDI), 4 data bits map to 5 line bits, so only 16 of 32 symbols carry data and 16 are spare. Reserved "illegal" symbols mark frame start/end — a **coding violation** the receiver spots instantly. The beauty: no stuffing at all, because the delimiter is a signal that can never appear in data. The cost is that it only works when the physical layer already has spare code space.

### Combining methods in real protocols

Production protocols layer these for safety. Ethernet and 802.11 start a frame with a **preamble** (a known alternating pattern, ~72 bits for 802.11) to let the receiver's clock lock and prepare, then a **Start Frame Delimiter (SFD)**, then a **length/type** field that locates the end. The preamble gives robust resync (like a flag), and the length field gives an exact boundary (like byte count) — each covering the other's weakness.

| Method | Resync after error | Overhead | Alignment | Used by |
|--------|--------------------|----------|-----------|---------|
| Byte count | None — stays broken | ~1–2 bytes | Byte | (only combined) |
| Byte stuffing | Scan for flag | Up to ~2× | Byte | PPP |
| Bit stuffing | Scan for flag | ~12.5% worst | Bit | HDLC, USB |
| Coding violation | Detect symbol | ~0 (in line code) | Symbol | Fast Ethernet (4B/5B) |
| Preamble + length | Preamble + count | Fixed header | Byte | Ethernet, 802.11 |

## Build It

`code/main.py` implements both stuffers so you can watch the transformation byte by byte:

1. **PPP byte stuffer** — `ppp_stuff(payload)` wraps a payload in `0x7E` flags, escaping `0x7E`, `0x7D`, and control characters with `0x7D` + (byte XOR `0x20`). `ppp_unstuff(frame)` reverses it.
2. **HDLC bit stuffer** — `hdlc_stuff(bits)` inserts a `0` after every five consecutive `1`s and frames with `01111110`; `hdlc_unstuff(framed)` removes the stuffing.
3. **Round-trip check** — for adversarial payloads (all flags, all escapes, all `1`s) the code asserts `unstuff(stuff(x)) == x`, proving transparency.
4. **Overhead report** — it prints actual vs. theoretical expansion (≈2× for byte stuffing, ≈12.5% for bit stuffing).

Run it:

```
python3 code/main.py
```

## Use It

| Task | Evidence | What Good Looks Like |
|------|----------|----------------------|
| Spot framing in a capture | Wireshark `frame` details; Ethernet preamble/SFD (if the NIC exposes it), PPP `0x7E` delimiters | You point to the exact delimiter bytes and the length/type field |
| Prove byte-stuffing transparency | `code/main.py` round-trip on a payload containing `0x7E 0x7D` | Destuffed output is bit-identical to input; on-wire bytes match RFC 1662 |
| Diagnose a desync'd link | Counters: frames-in ≪ frames-out, sustained bad-FCS after a single glitch | You explain why byte count can't resync and a flag/preamble can |
| Compute overhead | Frame size before/after stuffing | You predict ~2× (byte) or ~12.5% (bit) and the code confirms it |

## Ship It

Produce one artifact under [`outputs/`](../outputs/):

- A PPP/HDLC stuffing cheat-sheet (flag `0x7E`, escape `0x7D`, XOR `0x20`, five-ones rule) you can keep next to Wireshark.
- A one-page runbook: "link stuck on bad-FCS after a glitch" → confirm framing desync, identify the framing method, predict whether it self-heals.

Start from [`outputs/prompt-framing.md`](../outputs/prompt-framing.md).

## Exercises

1. **Byte-count desync.** A byte-count link sends frames of size 5, 5, 8, 8. A bit flip changes the second count from `5` to `7`. Trace by hand where the receiver believes each subsequent boundary is, and state how many frames it mis-parses before (if ever) it accidentally realigns.
2. **PPP by hand, then verify.** The payload is `0x7E 0x11 0x7D 0x41`. Write the exact on-wire byte sequence PPP produces (including both flags), then run `ppp_stuff` in `code/main.py` to check. Explain the `0x11 → 0x7D 0x31` step.
3. **HDLC worst case.** A payload is sixteen `1` bits. Show the on-wire bit string after stuffing, count the stuffed bits, and confirm it matches the ~12.5% expansion figure. Then prove `01111110` cannot appear in your stuffed data.
4. **Why USB stuffs bits.** USB has no separate clock wire; it recovers timing from data transitions. Explain how bit stuffing's "no more than five consecutive identical bits" guarantee keeps the receiver's clock locked, and what would go wrong on a long run of identical bits without it.
5. **Combine for safety.** Design a framing scheme for a noisy wireless link where bursts are common. Justify pairing a preamble with a length field, and explain which single-method scheme you would never use alone and why.
6. **Capture hunt.** In a PPP or SLIP capture, find a frame whose payload contained a `0x7E`. Show the stuffed `0x7D 0x5E` on the wire and the destuffed `0x7E` Wireshark reconstructs.

## Key Terms

| Term | What people say | What it actually means |
|------|-----------------|------------------------|
| Framing | "Chopping the stream into frames" | Making the bit stream *self-delimiting* so the receiver can find each frame's start cheaply and resync after errors |
| Flag byte | "The start marker" | A reserved byte (`0x7E` in PPP/HDLC) that delimits frames and must be stuffed when it appears in data |
| Byte stuffing | "Escaping special bytes" | Inserting an escape (`0x7D`) before flag/escape/control bytes; PPP emits `0x7D` + (byte XOR `0x20`) |
| Bit stuffing | "Adding extra bits" | Inserting a `0` after five consecutive `1`s so the `01111110` flag never appears in data; also maintains clock transitions |
| Coding violation | "Physical-layer trick" | Using line-code symbols that are illegal in normal data (e.g., reserved 4B/5B symbols) as frame delimiters |
| Byte count | "Length field" | A header length field; unusable alone because one bit flip in the count desynchronizes the receiver permanently |
| Preamble | "Junk at the front" | A known pattern (≈72 bits in 802.11) that locks the receiver clock and signals an incoming frame, paired with a length field |
| Desynchronization | "Link is flaky" | The receiver's frame boundaries no longer match the sender's, so every checksum fails until it re-finds a flag/preamble |

## Further Reading

- **RFC 1662** — *PPP in HDLC-like Framing* (the authoritative source for `0x7E` flag, `0x7D` escape, XOR `0x20`, and the async control-character map).
- **RFC 1661** — *The Point-to-Point Protocol (PPP)*.
- **ISO/IEC 13239** — *HDLC procedures* (bit stuffing and the `01111110` flag).
- **IEEE 802.3** — Ethernet preamble (7 bytes) and Start Frame Delimiter (`10101011`).
- **IEEE 802.11** — PLCP preamble and frame format.
- Tanenbaum & Wetherall, *Computer Networks*, 5th/6th ed., Chapter 3, §3.1.2 (Framing) and §3.5 (PPP).
- USB 2.0 Specification, §7.1.9 — bit stuffing for clock recovery.
