# The Bluetooth Link Layers to EPC Gen 2 Architecture

> Two of the smallest MAC designs in networking sit at opposite ends of the cost curve. Bluetooth's **baseband** layer turns a 1 Mbps radio into a centralized TDM piconet: a master owns the even 625-µs slots, slaves answer in odd slots, and frames span 1, 3, or 5 slots with a fixed 126-bit access-code-plus-header overhead and 250–260 µs of per-hop settling. The 18-bit header is sent **three times** (54 bits) and decoded by majority vote, so a basic-rate SCO voice link nets only 13% efficiency: 41% lost to settling, 20% to headers, 26% to repetition. **L2CAP** segments 64 KB upper-layer packets into ACL frames; the protocol is **stop-and-wait** with a single sequence bit. At the cheap end, **EPC Gen 2** RFID readers inventory battery-free Class-1 tags carrying a 96-bit EPC, using **backscatter** in the 902–928 MHz ISM band and a slotted-ALOHA tag-identification protocol driven by the `Q` parameter (slot range 0 to 2^Q−1), an RN16 handshake, and QAdjust feedback that mimics binary exponential backoff. This lesson builds a slot-by-slot simulator of both worlds.

**Type:** Learn
**Languages:** Python (stdlib), Wireshark filters, diagrams
**Prerequisites:** Slotted ALOHA and CSMA (Phase 06 earlier lessons), TDM basics, frame structure and CRC
**Time:** ~75 minutes

## Learning Objectives

- Compute Bluetooth piconet capacity from first principles: 1600 hops/s, 625-µs slots, 800 slots/s per direction, and explain why one uncompressed PCM voice channel saturates a 1 Mbps piconet at 13% efficiency.
- Decode the 18-bit Bluetooth header fields (Addr, Type, Flow, ARQN, SEQN, HEC) and explain why it is transmitted with 3× repetition coding on a 2.5 mW radio.
- Distinguish SCO vs ACL links and L2CAP responsibilities (segmentation of 64 KB packets, mux/demux, ARQ, QoS), and state the stop-and-wait sequence-bit rule.
- Trace the EPC Gen 2 inventory round: Query → RN16 → Ack → EPC, and explain why a 16-bit random number is sent before the 96-bit EPC.
- Tune the `Q` parameter and predict collision/idle/success slot ratios as the unknown tag population changes, relating QAdjust to binary exponential backoff.

## The Problem

A warehouse rolls out UHF RFID for pallet check-in with a fixed `Q = 4` (16 slots). With 8 tags per pallet, throughput is fine. But when a forklift parks 40 tagged cartons under one reader, read rates collapse — the reader keeps reporting "collision" slots and a third of the tags never get read before the truck leaves the dock. Meanwhile a Bluetooth hands-free headset paired to a phone drops audio whenever a file transfer starts on a second device in the same piconet.

Both symptoms are the same MAC-sublayer bug: a contention/allocation mechanism whose parameters do not match the offered load. To fix either you must read the protocol at the slot level — how slots are numbered, who may transmit in which slot, and what feedback adjusts the slot range. This lesson gives you that slot-level model and a simulator (`code/main.py`) that reproduces both the collapse and the fix.

## The Concept

Source material: [`chapters/chapter-04-the-medium-access-control-sublayer.md`](../../../../chapters/chapter-04-the-medium-access-control-sublayer.md), sections 4.6.5 (Bluetooth Link Layers), 4.6.6 (Bluetooth Frame Structure), and 4.7.1–4.7.4 (EPC Gen 2). See [`assets/the-bluetooth-link-layers-to-epc-gen-2-architecture.svg`](../assets/the-bluetooth-link-layers-to-epc-gen-2-architecture.svg) for the piconet slot timeline and the inventory message exchange side by side.

### The piconet is a centralized TDM system

The basic unit of Bluetooth is the **piconet**: one master and up to **7 active slaves** (plus up to 255 parked nodes) within ~10 m. Bridged piconets form a **scatternet**. The master clocks everything: it defines a series of **625-µs time slots**, transmits starting in **even** slots, and slaves answer starting in **odd** slots. This is textbook TDM — the master gets half the slots, slaves share the other half. A slave never transmits unless polled, so the piconet is "centralized": no carrier sense, no random access among slaves.

Frames are **1, 3, or 5 slots** long. Frequency hopping happens *only between frames*, never during one, at **1600 hops/s**. Each hop needs **250–260 µs of settling time** for the cheap radio to stabilize — pure overhead. So a 5-slot frame is far more efficient than a 1-slot frame: the per-frame overhead (one access code, one header, one settling gap) amortizes over more payload.

### Worked capacity example — why voice saturates the piconet

Take a basic-rate **SCO** voice link with the most robust 80-bit payload (repetition-coded 3× to fill the 240-bit data field). A slave uses only odd slots → **800 slots/s**; 800 × 80 bits = **64,000 bps** each way — exactly one full-duplex 64 kbps PCM voice channel, which is why 1600 hops/s was chosen.

So despite a **1 Mbps** raw radio, a *single* uncompressed voice call fills the piconet. The **13% efficiency** breaks down as **41%** settling, **20%** headers, **26%** repetition. That is the number to remember when "Bluetooth audio plus a file transfer" stutters — there is almost no basic-rate headroom. Enhanced rates (2×/3×, PSK carrying 2–3 bits/symbol) and multi-slot frames exist precisely to recover this overhead.

### The frame and the 3×-repeated header

The most important frame format (Fig. 4-36) is:

| Field | Basic rate | Notes |
|---|---|---|
| Access code | 72 bits | Identifies the master so slaves in range of two masters know whose traffic is whose |
| Header | 54 bits | An 18-bit logical header repeated **3×** |
| Data | 0–2744 bits (5-slot); 240 bits (1-slot) | Payload, optionally encrypted |

The **18-bit logical header** carries 10 bits of real information:

| Field | Bits | Meaning |
|---|---|---|
| Addr | 3 | Which of the 8 active devices (active member address) |
| Type | 4 | ACL / SCO / poll / null, FEC scheme, and slot count |
| Flow (F) | 1 | Slave asserts when its buffer is full — primitive flow control |
| ARQN (A) | 1 | Piggybacked ACK |
| SEQN (S) | 1 | Sequence bit; protocol is **stop-and-wait**, so 1 bit suffices |
| HEC | 8 | Header checksum |

The receiver examines all three copies of each bit; if they agree it accepts, otherwise the **majority opinion** wins. 54 bits of capacity carry 10 bits of header — the price of reliable delivery on a 2.5 mW radio with almost no compute. The enhanced-rate frame adds a 16-bit guard/sync field (to switch to the faster rate) and a 2-bit trailer; the access code and header always travel at the basic rate.

### SCO, ACL, and what L2CAP does

The **link manager protocol** sets up logical channels after **pairing**. Old pairing used a shared **4-digit PIN** (users left it at `0000`/`1234`, giving almost no security); **secure simple pairing** replaced it with a device-generated passkey that users confirm. Once paired, two link types carry user data:

- **SCO (Synchronous Connection Oriented)** — real-time, fixed reserved slots each direction, up to **3 per slave**, one 64 kbps PCM channel each. **Never retransmitted**; FEC provides reliability because retransmission would blow the latency budget.
- **ACL (Asynchronous ConnectionLess)** — best-effort packet data, **one per slave**, frames may be lost and retransmitted.

ACL data comes from **L2CAP**, which (1) accepts packets up to **64 KB** and segments them into frames (reassembling at the far end), (2) mux/demuxes sources to upper protocols like RFCOMM or service discovery, (3) handles error control and retransmission, and (4) enforces QoS across links.

### EPC Gen 2: readers, backscatter tags, and the 96-bit EPC

Now the cheap end. An **EPC Gen 2** RFID network has **tags** and **readers**. A **Class-1** tag has **no battery**: it harvests power from the reader's carrier and stores a unique **96-bit EPC** identifier plus a little writable memory. The reader is the intelligence — its own power, multiple antennas, full control of when tags talk.

Communication uses **backscatter**: the reader always transmits, even when the tag is "sending." To send a bit, the tag toggles between **reflecting** and **absorbing** the reader's carrier (like a radar return). Because that signal is weak, tags transmit slowly and **cannot hear each other** — exactly the condition that makes slotted ALOHA the right protocol. In the U.S. this runs in the unlicensed **902–928 MHz** UHF ISM band; the reader frequency-hops at least every **400 ms**. The link is **half duplex** with simple ASK modulation.

### The inventory round — slotted ALOHA with an RN16 handshake

The reader's main job is to **inventory** the unknown set of nearby tags (Fig. 4-39):

1. Reader sends **Query** (slot 0), announcing the slot range via `Q`: tags pick a random slot in **0 … 2^Q − 1**.
2. Reader advances slots with **QRepeat** messages.
3. In its chosen slot a tag replies with a **16-bit random number (RN16)** — *not* its identifier.
4. If exactly one tag answered, the reader echoes back an **Ack**, and only then does the tag send its **96-bit EPC**.
5. An identified tag goes quiet so the rest can be read.

Why send RN16 first? EPCs are long (96 bits); colliding on them wastes the channel. The short RN16 is a cheap probe to test whether the slot is collision-free before committing to the expensive identifier — the RTS/CTS reservation idea scaled down to a cents-cost tag.

### Tuning Q — slotted ALOHA's backoff in disguise

The hard part is choosing the slot range. Too few slots → collisions; too many → wasted idle slots. The reader watches each slot's outcome (idle / single / collision) and sends a **QAdjust** message to grow or shrink the range — **analogous to binary exponential backoff** in Ethernet. Slotted ALOHA peaks at throughput **1/e ≈ 0.368** when the expected contenders per slot is 1, i.e. when **2^Q ≈ number of unresponded tags**. The warehouse bug is now obvious: fixed `Q = 4` (16 slots) against 40 tags means ~2.5 tags/slot, far past the peak, so most slots collide. The `Q` message (Fig. 4-40) is just 4-bit Command `1000`, physical-parameter flags (DR/M/TR), tag-selection fields (Sel/Session/Target), the 4-bit `Q`, and a short **5-bit CRC** — tiny because downlink runs only 27–128 kbps.

## Build It

`code/main.py` is a stdlib-only, three-part simulator tied directly to the sections above.

1. **Bluetooth capacity calculator** — per-direction slots/s, SCO voice capacity, multi-slot throughput, and the 13% efficiency breakdown. Confirm the 64,000 bps result and the 41/20/26 split.
2. **Bluetooth header codec** — packs the 18-bit header (Addr/Type/Flow/ARQN/SEQN/HEC), applies 3× repetition, flips bits, and recovers by majority vote — showing one recoverable case and one where two of three copies are lost.
3. **EPC Gen 2 inventory simulator** — runs the slotted-ALOHA round for N tags at a chosen `Q`, classifies each slot idle/single/collision, performs the RN16→Ack→EPC handshake, applies QAdjust feedback, and sweeps `Q` to show the throughput peak near 2^Q ≈ N.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Verify piconet capacity | `main.py` capacity output; 800 slots/s × 80 bits | You reproduce 64,000 bps and the 41/20/26% efficiency split |
| Read a Bluetooth header | Type/Flow/ARQN/SEQN bits after majority decode | You explain why a flipped bit still decodes correctly |
| Diagnose RFID read collapse | Slot-outcome histogram (idle/single/collision) vs N and Q | Collision fraction matches 2^Q vs tag-count mismatch; QAdjust restores reads |
| Pick Q for a population | Q-sweep table from `main.py` | You choose 2^Q ≈ N and land near the 0.368 ALOHA peak |
| Justify the RN16 step | Round trace Query→RN16→Ack→EPC | You explain cost of colliding on 96-bit vs 16-bit messages |

## Ship It

Produce one artifact under `outputs/`:

- A **Q-tuning runbook**: given an observed collision-to-idle slot ratio, the QAdjust decision (raise/lower Q) and the target `2^Q ≈ unread tags`.
- A **Bluetooth capacity worksheet** that turns slot length, payload size, and frame slot-count into throughput and efficiency.
- An annotated inventory-round diagram (export the SVG and label a real collision).

Start from the simulator output: run `python3 code/main.py > outputs/inventory-trace.txt` and annotate the slot-by-slot collapse-then-recover behavior.

## Exercises

1. A reader inventories **30 tags** with fixed `Q = 3` (8 slots). Using `main.py`, report the first-round collision fraction and the total slots to read all 30; then find the `Q` that minimizes total slots and explain why it sits near `2^Q ≈ 30`.
2. Compute the throughput of a **3-slot ACL** frame at basic rate carrying a 1500-bit payload, and compare its efficiency to the 1-slot SCO case. Why is the 3-slot frame more efficient even though both pay one settling gap?
3. Flip 2 of the 3 copies of the **SEQN** bit in the header codec. Does majority decoding still recover it? At what total corruption does the header become unrecoverable?
4. Two readers cover overlapping shelves. Explain how the **Session** field (4 concurrent sessions) in the Query message lets both inventory without corrupting each other's "already identified" state.
5. A SCO voice call is active and a user starts an ACL file transfer in the same piconet. Using the capacity numbers, argue quantitatively why audio stutters, and name two features that recover headroom.
6. Sketch the QAdjust loop as a state machine: inputs (idle count, collision count) per round; outputs Q+1 / Q / Q−1. Where is it identical to, and where does it differ from, Ethernet's binary exponential backoff?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Piconet | "a Bluetooth network" | One master + up to 7 active slaves in a centralized 625-µs-slot TDM system; master owns even slots |
| SCO link | "Bluetooth audio" | Fixed-slot synchronous link, ≤3 per slave, 64 kbps PCM, **never retransmitted** — FEC instead |
| ACL link | "Bluetooth data" | Best-effort packet-switched link, one per slave, stop-and-wait with retransmission |
| L2CAP | "the Bluetooth transport" | Segments 64 KB packets into frames, muxes upper protocols, does ARQ and QoS |
| 3× header repetition | "error correction" | 18-bit header sent three times, decoded bit-by-bit by majority vote on a 2.5 mW radio |
| Backscatter | "the tag transmits" | The tag reflects/absorbs the reader's carrier; it has no transmitter and cannot hear other tags |
| EPC | "the RFID number" | A 96-bit Electronic Product Code identifier, a richer electronic barcode |
| Q parameter | "the RFID setting" | Defines the slotted-ALOHA range 0…2^Q−1; tune so 2^Q ≈ unread tag count |
| RN16 | "the tag handshake" | A 16-bit random probe sent before the 96-bit EPC to cheaply test a collision-free slot |
| QAdjust | "RFID backoff" | Reader feedback that grows/shrinks the slot range — analogous to binary exponential backoff |

## Further Reading

- A. S. Tanenbaum & D. J. Wetherall, *Computer Networks*, 5th ed., §4.6 (Bluetooth) and §4.7 (RFID).
- **Bluetooth Core Specification 4.0+** — baseband, link manager (LMP), and L2CAP layers; SCO/ACL link definitions.
- **IEEE 802.15.1-2005** — the IEEE standardization of the Bluetooth lower layers.
- **EPCglobal / GS1 EPC UHF Gen 2 Air Interface Protocol (ISO/IEC 18000-63)** — Query/QueryAdjust/QueryRep commands, RN16 handshake, and the Q-based inventory algorithm.
- L. Roberts, "ALOHA Packet System with and without Slots and Capture," 1972 — the 1/e ≈ 0.368 slotted-ALOHA throughput result that bounds RFID inventory.
- Wireshark `btl2cap`, `btbrlmp`, and `bthci_acl` dissectors for inspecting captured Bluetooth link-layer traffic.
</content>
</invoke>
