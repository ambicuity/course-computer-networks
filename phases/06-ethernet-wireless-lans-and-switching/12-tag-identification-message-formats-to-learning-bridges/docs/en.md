# Tag Identification Message Formats to Learning Bridges

> Two compact-format mechanisms sit back to back at the end of the MAC sublayer. EPC Gen 2 RFID identifies tags with a tiny **Query** command — a 22-bit reader-to-tag message (4-bit Command `1000`, DR/M/TR physical flags, 2-bit Sel, 2-bit Session, 1-bit Target, a 4-bit **Q** field, and a 5-bit CRC) that drives a slotted-ALOHA inventory over `0..2^Q-1` slots, where the reader sends **QAdjust** to tune Q like Ethernet binary exponential backoff. Learning bridges (IEEE 802.1D, the modern Ethernet switch) run in **promiscuous mode**, build a station→port hash table by **backward learning** on source MAC addresses, **flood** frames to unknown destinations on every port except the ingress port, and **age out** entries after a few minutes so a moved host is relearned without manual config. Both mechanisms leave precise, checkable evidence: a Q value and slot-collision count for RFID; a forwarding table, flood storms, and MAC-flap logs for bridges. This lesson parses the Query frame bit-by-bit and simulates a learning bridge so you can read both on the wire. Cut-through switching forwards as soon as the 6-byte destination MAC arrives, before the rest of the frame; store-and-forward waits for the FCS.

**Type:** Learn
**Languages:** Wireshark, diagrams, Python (stdlib)
**Prerequisites:** Phase 6 lessons on Ethernet framing, CSMA/CD, slotted ALOHA, and MAC addressing
**Time:** ~75 minutes

## Learning Objectives

- Decode an EPC Gen 2 **Query** command field-by-field (Command, DR, M, TR, Sel, Session, Target, Q, CRC) and compute the slot range `0..2^Q-1`.
- Explain how the reader uses **QRepeat**, **QAdjust**, and the RN16/ACK/EPC handshake to run a slotted-ALOHA inventory and avoid EPC collisions.
- Trace the **backward-learning** algorithm: which source MAC populates which port entry, and when an entry is created vs refreshed.
- Apply the three-case bridge forwarding rule (discard / forward / flood) to a given topology and predict which ports see the frame.
- Identify the observable evidence — Q value, empty/collided slots, forwarding-table contents, flood behavior, aging timer — that proves each mechanism is healthy or broken.
- Distinguish cut-through from store-and-forward switching by what is buffered and when forwarding starts.

## The Problem

You are called to two incidents in the same week.

**Incident 1 — the warehouse.** A dock-door reader inventories pallet tags. Throughput collapsed: a portal that used to read 300 tags in under a second now takes several seconds and misses tags. The integrator blames "interference." But the reader logs show many *collision* slots and many *empty* slots. The fix is not a new antenna — it is the **Q** parameter in the Query command set wrong for the population size.

**Incident 2 — the campus switch.** A user moved a laptop from the 3rd floor to the 2nd. For two minutes, frames to that laptop flooded out every port, and a monitor flagged a "MAC flap" between two switch ports. Nobody touched a config. This is **backward learning** plus **aging** doing exactly what 802.1D specifies — and knowing that stops a 2 a.m. rollback of a change that never happened.

Both incidents are unreadable until you can decode the compact message that drives the behavior: RFID hides its control logic in a 22-bit Query frame; a bridge hides its logic in a hash table you cannot see unless you ask.

## The Concept

### The EPC Gen 2 inventory round

Passive RFID tags cannot hear each other, so the reader arbitrates. The closest classic protocol is **slotted ALOHA**, adapted for Gen 2. The reader opens slot 0 with a **Query**, then advances with **QRepeat** for slot 1, slot 2, and so on. Each tag picks one random slot in the range and replies there.

A tag does not blurt out its long EPC immediately. It first sends a 16-bit random number, **RN16**. If the reader hears a clean RN16 (no collision), it returns an **ACK**, and only then does the tag transmit its full **EPC identifier**. Reason: EPC identifiers are long (96 bits is common), so a collision on the EPC would be expensive. The short RN16 is a cheap collision probe that reserves the slot. Once a tag's EPC is read, it stops answering new Query rounds so the remaining tags get airtime.

```text
reader: Query(slot 0)   QRepeat(1)  QRepeat(2) ----ACK----> QRepeat(3) ...
tag:                                  RN16(2)    EPC                     ...
```

### The Query message format (Fig. 4-40)

The Query is a **reader-to-tag** (downlink) message. Downlink runs slow — 27 kbps to 128 kbps — so the message is deliberately tiny. Field widths in bits:

| Field | Bits | Meaning |
|---|---|---|
| Command | 4 | `1000` identifies the message as a Query |
| DR | 1 | Divide ratio — sets tag backscatter link frequency |
| M | 2 | Cycles per symbol (Miller encoding / FM0) |
| TR | 1 | Pilot tone on/off for tag response |
| Sel | 2 | Which tags respond (all / selected / ~selected) |
| Session | 2 | Inventory session S0–S3 (up to four concurrent) |
| Target | 1 | Respond if inventoried flag is A or B |
| **Q** | 4 | Slot-count exponent; tags pick a slot in `0..2^Q-1` |
| CRC | 5 | CRC-5 protecting the message fields |

Total: 4+1+2+1+2+2+1+4+5 = **22 bits**. The first four flags after Command (DR, M, TR) are **physical-layer parameters**; Sel/Session/Target are **tag selection**. `code/main.py` packs and unpacks exactly these fields and recomputes the CRC-5.

The **Session** field is why two readers can overlap: a tag keeps an independent inventoried flag for each session S0–S3, so reader X on S0 does not disturb reader Y on S1. The **Target** (A/B) flag lets a reader sweep a population, flip targets, and sweep again to confirm.

### Q, slots, and the collision/empty trade-off

**Q** is the most important parameter. With Q, tags randomize over `2^Q` slots:

| Q | Slots `2^Q` | Good for population |
|---|---|---|
| 0 | 1 | 1 tag |
| 2 | 4 | ~2–4 tags |
| 4 | 16 | ~10–16 tags |
| 7 | 128 | ~80–128 tags |
| 15 | 32768 | thousands |

The reader watches outcomes per slot: **empty** (no reply), **single** (one RN16 — success), or **collision** (≥2 RN16s overlap). Too many empty slots → Q is too big, wasting time. Too many collisions → Q is too small, tags keep clashing. This is the same tension as ALOHA channel loading, and the reader's response is **QAdjust** — nudge Q up or down — directly analogous to Ethernet **binary exponential backoff**. Incident 1 was a Q stuck low for a large pallet: mostly collisions. The fix raises Q (or lets the reader's Q-adjust algorithm run) so single-reply slots dominate. `assets/tag-identification-message-formats-to-learning-bridges.svg` shows the Query bit layout and a slot timeline with empty/single/collision outcomes.

### From RFID to switching: the same idea, different layer

RFID's reader learns *which slot* holds *which tag*. A learning bridge learns *which port* holds *which MAC*. Both turn observed traffic into a lookup table that suppresses waste. Now the data-link side.

### Learning bridges and backward learning (IEEE 802.1D)

A **bridge** (modern name: Ethernet **switch**) joins LAN segments at the data-link layer. It forwards on the **destination MAC** and never inspects the payload, so it carries IP, AppleTalk, or anything else — unlike a router, which is protocol-specific. Each bridge runs in **promiscuous mode**: it accepts *every* frame on *every* port.

The forwarding table is a hash table mapping `destination MAC → output port`. When bridges first power on, every table is empty, so they **flood**: a frame for an unknown destination goes out every port except the one it arrived on.

Learning is **backward**: the bridge reads the **source** MAC of each frame and records that this MAC is reachable via the **ingress** port. If B1 sees a frame from C on port 3, it writes `C → port 3`; every later frame addressed to C goes only to port 3, never flooded. Each entry stores the **arrival time**; a background process **purges entries older than a few minutes** (default 802.1D aging time is 300 seconds). A host moved to a new port is relearned the moment it transmits; a silent host ages out and its traffic is flooded until it speaks again. That is Incident 2 exactly: the laptop moved, its old entry was stale, the new entry was learned on its first frame, and the window between looked like a flood plus a flap.

### The three-case forwarding rule

For an incoming frame, given its **source port** and **destination MAC**:

1. **Destination port == source port** → **discard** (already on the right side; e.g. A→B both on B1 port 1).
2. **Destination port known and != source port** → **forward** out that one port.
3. **Destination port unknown** → **flood** out all ports except the source port.

Case 1 can happen even with point-to-point links when a **hub** sits below a port: a hub copies every frame to all its lines, so the bridge sees a frame whose destination is back through the ingress port and simply drops it.

### Cut-through vs store-and-forward

Because forwarding needs only the destination MAC — the first 6 bytes after the preamble — a bridge can start sending **before the whole frame arrives**. This is **cut-through** (wormhole) switching: lower latency, less buffering, but it can forward a runt or a frame that later fails its **FCS** (CRC-32). **Store-and-forward** waits for the entire frame, validates the FCS, then forwards — higher latency, but corrupt frames are dropped at the switch. The lookup-and-update runs in special-purpose VLSI in microseconds.

## Build It

1. Run `python3 code/main.py`. It (a) builds a Query command with `Q=4, Session=S0`, prints the 22-bit layout and CRC-5, then parses it back; (b) simulates a slotted-ALOHA inventory of N tags at a chosen Q, reporting empty/single/collision slot counts and the read efficiency; (c) runs a learning-bridge simulation over a small topology, printing table state, learning events, and forward/flood/discard decisions.
2. Change `Q` and `N` in `main()` and watch the empty-vs-collision balance. Find the Q where single-reply slots are maximized for N tags (the efficient operating point).
3. In the bridge simulation, send a frame to a host that has not yet transmitted and confirm it floods; then have that host send one frame and confirm the next frame to it is forwarded, not flooded.
4. In Wireshark, capture switch traffic: filter `eth.dst == ff:ff:ff:ff:ff:ff` to see broadcasts that are always flooded, and watch unicast frames to a freshly-connected host before its first transmission.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Decode a Query | 22-bit field dump: Command=`1000`, Q, Session, CRC-5 | Bit widths sum to 22; CRC-5 recomputes to the captured value |
| Diagnose slow RFID inventory | Reader per-slot stats: empty / single / collision counts | Many collisions ⇒ Q too low; many empty ⇒ Q too high; QAdjust converges to mostly-single |
| Read a bridge forwarding table | `show mac address-table` / table dump: MAC, port, age | Each active host maps to exactly one port; ages reset on traffic |
| Explain a flood | Frames to a destination going out every port | Destination MAC is absent or aged-out of the table |
| Explain a "MAC flap" | Logs showing one MAC on two ports over time | A host physically moved, or a loop exists; not a config change |
| Pick cut-through vs store-and-forward | Latency vs error-drop requirement | Low-latency fabric ⇒ cut-through; error isolation ⇒ store-and-forward |

## Ship It

Produce one artifact under `outputs/`:

- A **Query-decode worksheet**: the 22-bit field table plus a CRC-5 worked example.
- A **bridge forwarding runbook**: the three-case rule, aging behavior, and how to tell a benign post-move flood from a real loop.
- The **slot-efficiency table**: for N = 10, 50, 100, 500 tags, the Q that maximizes single-reply slots.

Start from the Query decoder and bridge simulator in `code/main.py` and capture their printed output as your reference artifact.

## Exercises

1. A Query is captured as bits `1000 0 01 0 11 00 1 0101 ?????`. Identify Command, DR, M, TR, Sel, Session, Target, and Q. How many slots will tags randomize over? (Q = `0101` = 5 ⇒ `2^5 = 32` slots.)
2. A dock-door reader inventories ~200 pallet tags but is configured with **Q=2**. Predict the per-slot outcome distribution and state the QAdjust direction the reader should take. Then run `code/main.py` with N=200, Q=2 and confirm.
3. Bridge B1 has an empty table. In order, A→D (A on port 1), C→A (C on port 3), D→C (D on port 4) arrive. Write the table after each frame and label each decision discard/forward/flood.
4. A server is silent for 6 minutes (aging time 5 minutes), then a client sends it a frame. Describe what the switch does and why, and what changes the instant the server replies.
5. Two readers cover the same shelf. Explain how the **Session** field lets both run inventories without forcing tags to be read twice. What goes wrong if both use S0?
6. Compare cut-through and store-and-forward for a frame whose FCS fails. Which switch forwards the bad frame, and where is it finally dropped?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Query / Q field | "the RFID start command" | A 22-bit reader-to-tag command; the 4-bit Q sets the slot range `0..2^Q-1` for slotted ALOHA |
| QAdjust | "retune the reader" | A command that increments/decrements Q based on empty vs collision slot counts — RFID's binary exponential backoff |
| RN16 | "the tag's number" | A 16-bit random number sent as a cheap collision probe before the costly EPC |
| Backward learning | "the switch learns MACs" | The bridge records `source MAC → ingress port`, never the destination, to build the forwarding table |
| Flooding | "broadcasting" | Sending a frame out every port except ingress, used only for unknown-unicast and broadcast/multicast |
| Aging | "the table forgets" | Purging entries older than the aging time (~300 s) so moved hosts are relearned automatically |
| Promiscuous mode | "sniffing" | A bridge accepting every frame on every port, required for learning |
| Cut-through | "fast switching" | Forwarding after only the 6-byte destination MAC arrives, before the FCS — low latency, no error check |
| MAC flap | "a network bug" | The same MAC seen on two ports over time — caused by a host move or a forwarding loop, not always an error |

## Further Reading

- A. S. Tanenbaum & D. J. Wetherall, *Computer Networks*, 5th ed., Chapter 4: §4.7.4 (Tag Identification Message Formats) and §4.8.1–4.8.2 (Uses of Bridges; Learning Bridges).
- **EPC Radio-Frequency Identity Protocols Gen 2 UHF RFID** (EPCglobal / ISO/IEC 18000-63) — Query command and inventory state machine.
- **IEEE 802.1D** — MAC Bridges: filtering database, backward learning, default aging time, and forwarding rules.
- **IEEE 802.3** — Ethernet frame format and the 32-bit FCS used by store-and-forward switches.
- R. Perlman, *Interconnections: Bridges, Routers, Switches, and Internetworking Protocols*, 2nd ed. — the definitive treatment of bridge learning and spanning tree.
- Seifert & Edwards, *The All-New Switch Book*, 2nd ed. — practical switch forwarding, cut-through vs store-and-forward.
