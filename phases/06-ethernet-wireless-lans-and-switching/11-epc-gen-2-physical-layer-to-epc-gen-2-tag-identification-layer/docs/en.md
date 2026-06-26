# EPC Gen 2 Physical Layer to EPC Gen 2 Tag Identification Layer

> EPC Gen 2 (ISO/IEC 18000-63, the air interface behind the EPCglobal UHF Class-1 Gen-2 standard) lets one reader inventory hundreds of battery-free tags in the 902–928 MHz ISM band. The reader hops frequencies at least every 400 ms, transmits a continuous carrier that passive tags *harvest* for power, and tags reply by **backscatter** — switching their antenna between reflect and absorb states rather than generating their own RF. Downlink bits use PIE (Pulse-Interval Encoding) where a 1 is a longer symbol than a 0; tags uplink with FM0 or Miller coding at 5–640 kbps. To resolve the multiple-access problem with an *unknown* tag count, Gen 2 runs slotted ALOHA: the reader broadcasts `Query` carrying a 4-bit `Q`, each tag picks a random slot in `[0, 2^Q − 1]` and replies with a 16-bit `RN16` handle; only after the reader echoes that handle in an `ACK` does the tag spend air time on its long EPC. The reader tunes `Q` with `QAdjust` — a binary-exponential-backoff analog — to keep occupancy near one tag per slot. This lesson links the bit-level physical layer to the anti-collision identification layer and the `Query` frame.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib slotted-ALOHA / Q-tuning simulator)
**Prerequisites:** Slotted ALOHA and binary exponential backoff (earlier Phase 6 lessons), ASK modulation, CRC basics
**Time:** ~75 minutes

## Learning Objectives

- Explain why a passive UHF tag uses **backscatter** instead of an active transmitter, and what "the reader is always transmitting" means for half-duplex framing and power harvesting.
- Trace a full `Query → RN16 → ACK → EPC` handshake and explain why the 16-bit RN16 probe precedes the long EPC.
- Compute the slot range `[0, 2^Q − 1]` from the 4-bit `Q` and pick a starting `Q` for a tag population (Tanenbaum problem 34: ~10 tags).
- Describe how the reader adjusts `Q` with `QAdjust` from empty/single/collision slot counts — the RFID analog of binary exponential backoff.
- Decode a `Query` field-by-field: `Command=1000`, `DR`, `M`, `TR`, `Sel`, `Session`, `Target`, `Q`, and the 5-bit `CRC-5`.
- Identify the evidence (slot-occupancy histogram, RN16 collisions, throughput vs. Q) that proves a round is healthy or mis-tuned.

## The Problem

A warehouse dock-door portal must read every RFID-tagged carton on a pallet rolling through. Pallets of 60 cartons read fine, but dense pallets of ~300 drop 10–15% of tags — the WMS shows "missing EPCs" and a worker hand-scans the stragglers. Nothing is broken at the application layer; the EPCs are valid, antennas powered, carrier up.

The failure lives in the **tag identification layer**. The reader started its round with `Q=4`, only `2^4 = 16` slots. With 300 tags contending for 16 slots, almost every slot collides — two or more tags backscatter their RN16 at once, the reader decodes garbage, and those tags go unacknowledged within the round. This is the slotted-ALOHA collapse from classic ALOHA channels, and the fix mirrors Ethernet backoff: *grow the slot count* until occupancy lands near one tag per slot. Diagnosing it means reading the round at the slot level — empty, singleton, collision counts — so you need the physical-layer framing and the `Query`/`QAdjust` loop together. `code/main.py` reproduces the collapse and recovery.

## The Concept

The EPC Gen 2 air interface is two layers on one half-duplex link: a **physical layer** moving bits via backscatter, and a **tag identification layer** arbitrating which tag talks. The SVG in `assets/` shows the handshake timeline and `Query` frame side by side.

### The link: continuous carrier, backscatter, half duplex

Unlike Wi-Fi or Bluetooth, the reader **never stops transmitting** during a round, for two reasons. First, **downlink data**: it modulates its own signal to send commands. Second, **tag power**: when it is the *tag's* turn, the reader emits an unmodulated **continuous wave (CW) carrier** carrying no bits — a passive ("Class-1") tag has no battery and rectifies this carrier to power its logic.

The tag answers by **backscatter**: it toggles its antenna impedance between reflecting and absorbing, like a radar target appearing and disappearing, creating a weak modulation the reader detects after filtering out its own strong outgoing signal. Consequences that surface as evidence:

- The link is **half duplex** — reader and tag take turns, never both at once.
- The uplink is **slow and short-range** because the backscattered signal is tiny.
- **Tags cannot hear each other** — no receiver sensitive enough for another tag's backscatter, so no carrier sense (no CSMA). This is *why* anti-collision must be slot-based, not listen-before-talk.

### Bit encoding: PIE down, FM0/Miller up

| Direction | Scheme | Rule | Rate |
|---|---|---|---|
| Reader → Tag | PIE, ASK | Bit value set by **how long** the reader waits before a low-power notch; a `1` is *longer* than a `0`. Tag measures intervals against a preamble. | 27–128 kbps |
| Tag → Reader | FM0 / Miller backscatter | Tag alternates backscatter state over 1–8 pulse periods per bit; `1`s have *fewer* transitions. More periods = more redundancy, slower. | 5–640 kbps |

The reader picks uplink rate and coding via the `DR`, `M`, `TR` flags. More Miller pulses per symbol trade throughput for noise immunity — the knob for a dense-metal environment that corrupts reads.

### The multiple-access problem: slotted ALOHA, not CSMA

The reader wants one RN16 from every tag, but it does **not know how many tags** are present, and tags can't sense each other. "Everyone send your EPC now" would collide — like classic Ethernet, but with no collision detection and no carrier sense. Gen 2 borrows **slotted ALOHA**, the earliest random-access protocol. The reader **synchronizes** the tags — they don't wake on their own schedule like Ethernet stations; the round begins when the reader says so. It announces a **slot range** `[0, 2^Q − 1]` via `Q`, and each tag draws a **random slot** into a 4-bit *slot counter*.

### The Query → RN16 → ACK → EPC handshake

A round runs slot by slot:

```
Reader: Query   (slot 0, carries Q)   -- every tag picks a slot
Reader: QRepeat (slot 1)              -- decrement each slot counter
Reader: QRepeat (slot 2)
   Tag: RN16   (counter hit 0 -> 16-bit handle)
Reader: ACK(RN16)                     -- echo the exact 16 bits back
   Tag: EPC identifier                -- now spend air time on the long ID
Reader: QRepeat (slot 3) ... (slot N)
```

Each `QRepeat` advances a slot; the tag whose counter reaches 0 backscatters its **16-bit RN16**. The two-step handshake is a deliberate optimization. **The EPC is long** (96 bits standard, up to 496) and CRC-protected, so a collision on it wastes a lot of air time. The short **RN16 is a cheap probe**: a cleanly decoded RN16 means the slot is collision-free, so the reader `ACK`s by echoing those exact 16 bits, and the matching tag — knowing the slot is its own — *then* sends the expensive EPC. Any tag whose RN16 was not echoed stays quiet.

Once read, a tag sets an "inventoried" flag for that **session** and stops answering new `Query`s, freeing the rest. Tags track **up to four concurrent sessions (S0–S3)**, letting overlapping readers inventory the same tags independently.

### Tuning Q: the backoff analog

After each slot, the reader classifies it:

| Slot | Reader sees | Q reaction |
|---|---|---|
| **Empty** | CW only, no RN16 | Too many empties ⇒ `Q` too big ⇒ **decrease Q** |
| **Single** | One clean RN16, ACK, EPC | Ideal — leave `Q` |
| **Collision** | Garbled RN16 (≥2 tags) | Too many collisions ⇒ `Q` too small ⇒ **increase Q** |

The reader nudges `Q` with `QAdjust` — analogous to **binary exponential backoff**: high contention doubles the slots (`Q += 1`); a mostly-idle channel shrinks them. Slotted-ALOHA theory maximizes throughput at ~1 tag per slot, i.e. `2^Q ≈ tag count`. So ~300 tags want `Q ≈ 8` (`2^8 = 256`), not `Q = 4`; the 10-tag case (problem 34) wants `Q = 4`. `code/main.py` sweeps `Q` and prints the empty/single/collision breakdown.

### The Query frame format

The downlink is rate-limited, so control frames are tiny — the `Query` is 22 bits total:

| Field | Bits | Meaning |
|---|---|---|
| `Command` | 4 | `1000` identifies the frame as a `Query` |
| `DR` | 1 | Divide ratio — sets tag backscatter link frequency |
| `M` | 2 | Cycles per symbol (FM0 vs. Miller-2/4/8) |
| `TR` | 1 | Pilot-tone / TRext flag |
| `Sel` | 2 | Which tags respond, by their selected flag |
| `Session` | 2 | Session S0–S3 to inventory |
| `Target` | 1 | Inventory the A or B inventoried-flag state |
| `Q` | 4 | Slot-count exponent: slot in `[0, 2^Q − 1]` |
| `CRC-5` | 5 | CRC-5 over the message |

`Sel`, `Session`, `Target` are *selection* fields — inventory only tagged jeans not shirts, or run S1 while another reader uses S2. `DR`, `M`, `TR` set the uplink rate (5–640 kbps). `Q` is the anti-collision knob. The 5-bit `CRC-5` is shorter than Ethernet's CRC-32 because the frame is only 22 bits. `code/main.py` builds, CRC-protects, and decodes this layout.

## Build It

1. **Read `build_query()`** — confirm it packs `Command=0b1000` then `DR/M/TR/Sel/Session/Target/Q/CRC-5` in order, and `decode_query()` round-trips `Q` and rejects a flipped CRC-5 bit.
2. **Run a single round.** `simulate_round(num_tags=10, q=4)` returns the slotted-ALOHA fingerprint: mostly empty + singleton slots, a few collisions.
3. **Reproduce the failure.** `simulate_round(num_tags=300, q=4)`: nearly all 16 slots collide, success craters to ~0.
4. **Recover.** `sweep_q(num_tags=300)` finds the `Q` (~8–9) maximizing identified tags per slot.
5. **Map outcomes to evidence.** For each slot class, write what a reader debug log or spectrum capture shows.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Confirm the link is alive | Reader CW + tag backscatter sidebands on a spectrum analyzer | Continuous carrier between commands; weak backscatter only in a tag's slot |
| Validate a `Query` frame | Decoded `Command=1000`, `Q`, passing CRC-5 | All 22 bits parse; `2^Q` matches the on-air slot count |
| Judge round health | Slot-occupancy histogram (empty/single/collision) | Singletons dominate; collisions a small minority; `2^Q ≈ tag count` |
| Diagnose dropped tags | Mostly collision slots, few ACKs | `Q` too small → recovery after `QAdjust` raises `Q` |
| Confirm session isolation | Two readers, `Session=S1` vs `S2` | Inventoried flags advance independently; no mutual reset |

## Ship It

Produce one reusable artifact under `outputs/`:

- A **Q-selection runbook**: tag count → starting `Q` and the empty/collision thresholds that trigger `QAdjust`.
- A **`Query`-frame decode card** mapping the 22 bits to fields and legal values.
- A **slot-occupancy diagnostic** (extend `code/main.py` to ingest slot outcomes and recommend a `Q`).

Start from [`outputs/prompt-epc-gen-2-physical-layer-to-epc-gen-2-tag-identification-layer.md`](../outputs/prompt-epc-gen-2-physical-layer-to-epc-gen-2-tag-identification-layer.md).

## Exercises

1. **Problem 34 (Tanenbaum).** Ten tags surround a reader. What single `Q` gives the best throughput, and what slot range? Show `2^Q ≈ 10` and compute the expected singleton slots out of `2^Q`.
2. **The dense-pallet collapse.** A reader fixed at `Q=4` faces 300 tags. Estimate the fraction of the 16 slots that collide and why ~10–15% of tags go unread per round. What `Q` fixes it?
3. **Why RN16 first?** An engineer proposes skipping the RN16 and backscattering the 96-bit EPC directly. Compare the air-time cost of a collision versus the `RN16 → ACK → EPC` handshake, and explain Gen 2's choice.
4. **Decode a Query.** Split `1000 1 01 0 00 01 0 0110 11010` into fields and report `Session`, `Target`, `Q`. How many slots do tags randomize over?
5. **QAdjust as backoff.** Map `QAdjust` onto Ethernet backoff: what plays the contention window, the collision signal, the "double" step? Where does the analogy break (tags can't sense each other)?
6. **Session overlap.** Two readers cover one shelf, both using `Session=S0`. Describe the failure, fix it with sessions, and explain how the four-session state prevents cross-reader interference.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Backscatter | "The tag transmits" | The tag has no transmitter; it modulates the *reader's* carrier by switching antenna reflection on/off. Weak, short-range, and why tags can't sense each other. |
| `Q` parameter | "How many tags" | A 4-bit exponent; slot range `[0, 2^Q − 1]`. Optimal when `2^Q ≈ tag count` (~1 tag/slot). |
| RN16 | "The tag ID" | A 16-bit *temporary handle*, not the EPC — a cheap collision probe the reader echoes in an `ACK` before the tag sends its real EPC. |
| QAdjust | "Retry" | Reader command to grow/shrink `2^Q` from empty/collision counts — the RFID analog of binary exponential backoff. |
| Session (S0–S3) | "A connection" | One of four independent inventoried-flag states, letting overlapping readers inventory the same tags without resetting each other. |
| PIE | "The bit timing" | Pulse-Interval Encoding downlink: a `1` is longer than a `0`; tags decode by comparing intervals to a preamble. |

## Further Reading

- **EPCglobal / GS1, "EPC UHF Gen2 Air Interface Protocol, v2.x"** — authoritative `Query`/`QueryAdjust`/`ACK` command and CRC-5 spec.
- **ISO/IEC 18000-63** — international standard mirroring EPC Gen 2 UHF Class-1.
- **Tanenbaum & Wetherall, _Computer Networks_, 5th ed., Sec. 4.7 (RFID)** — Figures 4-37 to 4-40; end-of-chapter problems 34–35.
- **Abramson (1970), "The ALOHA System"** — the slotted-ALOHA root protocol Gen 2 adapts.
- **IEEE 802.3 Clause 4** — binary exponential backoff, for comparison with `QAdjust`.
