# Wireless LAN Protocols

> Radios cannot detect collisions while transmitting — the echo of your own signal is up to a million times stronger than a distant sender, so classic CSMA/CD is impossible on air. Worse, carrier sense answers the wrong question: it reports activity at the *transmitter*, but a collision is decided by interference at the *receiver*. This mismatch produces two failure modes — the **hidden terminal problem** (two senders out of each other's range both transmit to a common receiver and garble each other) and the **exposed terminal problem** (a sender needlessly defers because it hears an unrelated transmission whose receiver is elsewhere). MACA (Multiple Access with Collision Avoidance, Karn 1990) solves the hidden case with a 30-byte **RTS/CTS** handshake: the sender's RTS carries the data length, the receiver echoes it in a CTS, and every station overhearing the CTS stays silent for exactly that many microseconds. This RTS/CTS-with-NAV idea is the direct ancestor of IEEE 802.11's virtual carrier sense; collisions on the RTS itself are resolved by binary exponential backoff.

**Type:** Build
**Languages:** Python, models
**Prerequisites:** CSMA/CD and collision detection (Phase 5 · 04–05), the broadcast channel model (Phase 5 · 01)
**Time:** ~90 minutes

## Learning Objectives

- Explain why a wireless transceiver cannot perform collision detection and must rely on acknowledgements instead.
- Distinguish the hidden terminal problem from the exposed terminal problem using radio-range geometry, and state which one MACA fixes and which it does not.
- Trace a complete MACA exchange (RTS → CTS → DATA → ACK) and compute the NAV silence interval each overhearing station must honour.
- Predict which neighbouring stations defer after hearing an RTS versus a CTS, and explain why those sets differ.
- Implement a discrete-event simulation of RTS/CTS over a topology graph and measure how MACA changes successful-delivery rate versus naive CSMA.

## The Problem

You are debugging a warehouse Wi-Fi deployment. Two handheld scanners, on opposite ends of a 60-metre aisle, both associate to the same ceiling access point in the middle. Each scanner shows a strong signal to the AP and near-zero retries to the user. Yet aggregate throughput collapses whenever both scanners are busy, and the AP's counters show a flood of CRC errors and missing acknowledgements.

Neither scanner can hear the other — they are 60 m apart and their radios reach only ~35 m. So each one senses an idle channel, decides it is safe, and transmits. Both frames arrive at the AP simultaneously and collide. The senders never witness the collision; they only learn something is wrong when no ACK comes back, then retransmit, making congestion worse. This is the **hidden terminal problem**, and plain carrier sense cannot see it. To fix it you need a protocol where the *receiver* tells the neighbourhood to be quiet. That protocol is MACA, and its descendant runs inside every 802.11 chip on your network.

## The Concept

Source: `chapters/chapter-04-the-medium-access-control-sublayer.md`, the Wireless LAN Protocols section. A wireless LAN is a broadcast channel where a cell — an access point plus the stations in radio range — shares a single channel offering up to 600 Mbps. The wired assumption "if one station sends, every station hears it" does not hold on air, and almost every wireless MAC complication flows from that.

### Why collision detection is impossible on radio

On wired Ethernet, a transceiver compares the bits it puts on the cable with the bits it reads back; a mismatch means a collision, so it aborts within one slot time (CSMA/CD). A radio cannot do this. The received copy of a distant station's frame can be a **million times fainter** (roughly 60 dB down) than the station's own outgoing signal — listening for a collision while you transmit is like watching for a single ripple in the wake of your own speedboat. So wireless MACs abandon collision *detection* and substitute collision *avoidance* plus positive acknowledgement: a frame is presumed lost unless an ACK confirms it arrived.

### Carrier sense asks the wrong question

Carrier sense measures energy at the antenna of the *sender*. But whether a frame survives depends only on the signal-to-interference ratio at the *receiver*. With short-range radio, two facts follow that have no analogue on a shared wire:

- Two senders can be mutually inaudible yet still collide at a shared receiver between them (hidden terminals).
- Two senders can hear each other yet *not* collide, because their receivers are in opposite directions and far apart (exposed terminals).

A wire forces one transmission at a time everywhere; radio allows many simultaneous transmissions as long as their receivers are mutually out of range — like several conversations in a large room. We want that concurrency, and naive carrier sense throws it away.

### Hidden and exposed terminals

Consider four stations in a line, A — B — C — D, where each station reaches only its immediate neighbours. The geometry produces both pathologies. The diagram in [`assets/wireless-lan-protocols.svg`](../assets/wireless-lan-protocols.svg) shows the radio ranges overlapping.

| Problem | Setup | What carrier sense does | Why it is wrong | Cost |
|---|---|---|---|---|
| **Hidden terminal** | A and C both send to B | C senses idle (cannot hear A) and transmits | Both frames collide at B; A's frame is destroyed | Wasted bandwidth, retransmission storm |
| **Exposed terminal** | B sends to A while C wants to send to D | C senses busy (hears B) and defers | C→D would only interfere in empty space between B and C; both receivers are clear | Wasted opportunity, lower throughput |

MACA attacks the hidden-terminal problem directly. It does not fully solve the exposed-terminal problem — a station that hears an RTS but not the matching CTS may still transmit (it is hidden from the receiver), which is exactly the concurrency we want.

### MACA: the RTS/CTS handshake

MACA replaces carrier sense with an explicit exchange that makes the *receiver* announce the upcoming transmission. To send a frame, A does the following:

1. **RTS (Request To Send).** A sends a short frame — about **30 bytes** — to B containing the length of the data frame that will follow.
2. **CTS (Clear To Send).** B replies with a CTS that copies the data length out of the RTS. The CTS is what makes MACA work: it is broadcast from the *receiver's* location.
3. **DATA.** On receiving the CTS, A transmits the data frame.
4. **ACK.** (In MACA's descendants such as 802.11) B acknowledges, because radios cannot detect collisions and the sender otherwise has no way to know the frame arrived.

The reactions of overhearing stations are the heart of the protocol:

| A station that hears… | Is close to… | Must stay silent for… | Reason |
|---|---|---|---|
| the **RTS** only | the sender A | long enough for the CTS to return | so it does not clobber the CTS coming back to A |
| the **CTS** | the receiver B | the whole data-frame duration (read from the length field) | so it does not interfere at B during the data transfer |
| **both** RTS and CTS | both A and B | until the data frame completes | it is adjacent to the receiver |

In the A–B–C–D line, when A sends to B: **C** hears A's RTS but not B's CTS, so once the CTS window passes, C is free to transmit elsewhere (the exposed-terminal concurrency MACA preserves). **D** hears B's CTS but not the RTS — that tells D it sits next to a station about to receive, so D defers for the full data duration. **E**, hearing both, defers as well.

### NAV: turning a length field into a silence timer

The data-length field is the protocol's clock. A station that overhears a CTS converts the announced length into a duration and refuses to transmit until that timer expires. In MACA this is informal ("be silent for the data frame"); 802.11 formalises it as the **Network Allocation Vector (NAV)** — a microsecond countdown set from a Duration/ID field. This is **virtual carrier sense**: a station defers not because it senses energy, but because a frame *told* it to. Worked example: at 54 Mbps, a 1500-byte data frame plus headers takes roughly 280 µs on the air; a neighbour that decodes that length sets its NAV to ~280 µs and skips its own contention for exactly that window. `code/main.py` computes these NAV intervals from frame size and bit rate.

### Residual collisions and backoff

RTS/CTS shrinks the collision window but does not eliminate it. Two stations — say B and C — can send RTS frames to A in the *same slot*; those short frames collide and are lost. With no collision detection, each sender discovers the failure only by the **absence of a CTS within the expected interval**, then waits a random time and retries. MACA's descendants use **binary exponential backoff**: the contention window doubles after each failure (in 802.11, from CWmin = 15 slots up to CWmax = 1023 slots), so a second collision is unlikely. Crucially, collisions now happen only on the tiny 30-byte RTS, never on the large data frame — that is the bandwidth win.

## Build It

`code/main.py` is a deterministic simulator of MACA over an arbitrary radio-range topology. Work through it in this order:

1. **Model the topology.** Stations are nodes; an undirected edge means two stations are within radio range. The default graph is the A–B–C–D line plus a node E near B and C.
2. **Carrier-sense reachability.** `can_hear(x, y)` is an adjacency lookup; `neighbors(x)` returns every station that would overhear x.
3. **Run an RTS/CTS exchange.** `maca_exchange()` builds the RTS, derives the CTS, and classifies which stations defer after the RTS, after the CTS, or for the full data window.
4. **Compute NAV.** `nav_microseconds(frame_bytes, mbps)` converts an announced length and rate into a silence interval.
5. **Compare against naive CSMA.** `naive_csma_collision()` shows two hidden senders both pass carrier sense and collide, while MACA's CTS would have silenced one of them.

Run it with plain `python3 main.py` — no dependencies, no network.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Identify a hidden-terminal collision | AP CRC/FCS error counters rise while both senders report success and no mutual retries | You can name the two stations that cannot hear each other but share a receiver |
| Confirm RTS/CTS is active | Wireshark frames `wlan.fc.type_subtype == 0x1b` (RTS) and `0x1c` (CTS) preceding data | Each data burst is preceded by a CTS from the receiver's MAC |
| Read a NAV / Duration value | The Duration/ID field (µs) in an RTS or CTS frame | Neighbour idle time matches the announced duration; you can derive frame length from it |
| Distinguish exposed from hidden | Topology map plus which station deferred | An exposed terminal deferred when it could have safely transmitted; you can prove its receiver was clear |

## Ship It

Produce one reusable artifact under `outputs/`:

- A one-page runbook for diagnosing hidden-terminal symptoms (high AP CRC errors, low per-station retries, throughput collapse under concurrent load) and when to enable the RTS/CTS threshold on an AP.
- The annotated topology + state diagram exported from `assets/wireless-lan-protocols.svg`.
- A NAV calculator wrapper around `code/main.py` that takes a pcap-style length/rate and prints the neighbour silence interval.

## Exercises

1. In the A–B–C–D line, A transmits a 1200-byte frame to B at 24 Mbps. List exactly which of C, D, E defer, for how long each, and which event (RTS or CTS) triggered each deferral. Verify against `maca_exchange`.
2. Construct a 5-station topology where enabling RTS/CTS *reduces* total throughput. Explain why (hint: the 30-byte RTS/CTS overhead dominates when frames are small and there are no hidden terminals). This is why real APs only enable RTS/CTS above a length threshold.
3. Two stations send RTS to the same receiver in the same slot. Walk through how each detects the failure (no CTS), then simulate two rounds of binary exponential backoff with CWmin = 15. What is the probability they collide again on the retry?
4. Modify the simulator so radio ranges are asymmetric (A hears B but B does not hear A). Show how this breaks the CTS assumption and produces collisions MACA cannot prevent.
5. An exposed terminal C wants to send to D while B→A is in progress. Show in code that C hears the RTS but not the CTS, and argue why C is therefore safe to transmit — the concurrency MACA deliberately preserves.
6. Compute the RTS/CTS overhead as a fraction of channel time for a 64-byte frame versus a 1500-byte frame at 54 Mbps. At which frame size does the handshake cost more than it saves?

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Hidden terminal | "weak signal" | Two senders out of each other's radio range that share a common receiver and collide there despite both passing carrier sense |
| Exposed terminal | "interference" | A sender that needlessly defers because it hears an unrelated transmission whose receiver is elsewhere — a lost opportunity, not a collision |
| RTS / CTS | "Wi-Fi handshake" | A ~30-byte Request-To-Send / Clear-To-Send exchange where the *receiver*'s CTS silences its own neighbourhood |
| MACA | "old Wi-Fi" | Karn's 1990 protocol that replaces carrier sense with RTS/CTS; the direct ancestor of 802.11 virtual carrier sense |
| NAV | "the timer" | Network Allocation Vector — a microsecond countdown set from a frame's Duration field implementing *virtual* carrier sense |
| Collision avoidance | "CSMA/CD for radio" | Avoiding collisions *before* they happen plus ACKing every frame, because radios cannot *detect* collisions mid-transmission |
| Virtual carrier sense | "channel busy" | Deferring because a frame announced a duration, not because the antenna senses energy |

## Further Reading

- A. S. Tanenbaum & D. J. Wetherall, *Computer Networks*, 5th ed., Ch. 4 — Wireless LAN Protocols and 802.11.
- P. Karn, "MACA — A New Channel Access Method for Packet Radio," *ARRL/CRRL Amateur Radio 9th Computer Networking Conference*, 1990 (the original MACA paper).
- V. Bharghavan et al., "MACAW: A Media Access Protocol for Wireless LANs," *SIGCOMM '94* — adds carrier sense, ACK, and per-flow backoff to MACA.
- IEEE Std 802.11-2020 — the DCF, RTS/CTS exchange, and the Network Allocation Vector.
- Wireshark display-filter reference: `wlan.fc.type_subtype`, `wlan.duration` for inspecting RTS/CTS/NAV on real captures.
