# MACA and the Hidden/Exposed Terminal Problems in Wireless LANs

> Wireless LANs cannot use CSMA the way Ethernet does. Two physical-layer reasons: (1) a transmitting station's own signal is roughly a million times stronger than any received signal, so collision detection during transmission is impossible; the protocol must rely on **acknowledgements** to discover collisions after the fact. (2) Radio range is limited, so "all stations hear all transmissions" does not hold — which produces two new pathologies. The **hidden terminal problem** (Fig. 4-11a): A and C both want to send to B; A is in B's range but C is not in A's range, so C cannot sense A's transmission and transmits anyway, garbling B's reception. The **exposed terminal problem** (Fig. 4-11b): B is sending to A while C wants to send to D; C senses B's carrier and defers, even though C's transmission would not collide at A or D. **MACA** (Karn 1990) and its successor **MACAW** solve this with a two-frame handshake: the sender transmits a 30-byte **RTS** (Request To Send) containing the future data length; the receiver replies with a **CTS** (Clear To Send) echoing that length. Any station overhearing the RTS defers for the CTS; any station overhearing the CTS defers for the entire data frame. The result: hidden terminals hear the CTS and back off; exposed terminals hear only the RTS and may transmit. This lesson walks the handshake, simulates the four-station geometry, and previews why 802.11 keeps the same RTS/CTS structure with refinements.

**Type:** Lab
**Languages:** Python (stdlib handshake simulator), packet traces
**Prerequisites:** CSMA/CD limitations, propagation delay, signal strength and receiver sensitivity
**Time:** ~80 minutes

## Learning Objectives

- Sketch the four-station radio-range geometry (A, B, C, D with A-B and B-C-D ranges) and label the hidden-terminal and exposed-terminal cases.
- Trace a MACA handshake (A→B) through the RTS, CTS, data, ACK exchange and show the deferral rules for C, D, and E.
- Explain why CSMA fails on wireless even when only a few stations are nearby, using the receiver-interference-vs-sender-interference argument.
- Implement a stdlib Python simulator that places N stations on a plane, lets pairs handshake, and reports which pairs of transmissions can run concurrently without hidden-terminal collisions.
- Predict the 802.11 RTS/CTS variant of MACA and identify the additions (per-frame ACK, retry counters in MACAW, carrier-sense + RTS/CTS hybrid in 802.11 DCF).

## The Problem

A robotics lab's warehouse is laid out in a 60 m x 30 m rectangle with 40 battery-powered AGVs (automated guided vehicles). The AGVs use a 2.4 GHz WiFi link to coordinate paths. The current deployment has random "phantom stops": an AGV freezes for 1-2 seconds in the middle of an aisle, even though no other AGV is visible nearby. Throughput during the freeze drops to near zero.

The team suspects RF interference from the AGV motors. The real cause is hidden terminals. The aisle geometry has line-of-sight blocks every 15 m; two AGVs at opposite ends of an aisle cannot hear each other, but both can hear the access point at the aisle's centre. When AGV A and AGV C both send a path-update to AP B, A and C sense an idle channel (they cannot hear each other), transmit, and the AP receives garbled bits — losing two updates. The AGVs' transport-layer retry causes a 1-2 s freeze.

## The Concept

The textbook frames wireless MAC as a problem of *receiver-side interference*, not sender-side interference. The two pathologies are not bugs in 802.11; they are properties of radio range that any wireless MAC must address.

### Why CSMA is not enough

On a wired bus, all signals propagate to all stations, so sensing the medium at the sender tells you about interference at every receiver. On a wireless channel, this is false. Consider four stations:

```
A ---- B ---- C ... D
```

A and B are within range of each other. C is in range of B but not A. D is in range of C but not B. The medium A senses is the medium at A, not the medium at B. CSMA protects against *A* hearing someone; it does not protect against *B* hearing two people at once.

A second issue is dynamic range. A radio transmitter's own signal at its antenna is on the order of +20 dBm (100 mW). A received signal from 100 m away is on the order of -50 dBm (10 nW) — a 70 dB ratio, or ten million times weaker. The AGC (automatic gain control) in the radio cannot simultaneously listen to the air and blast into it; collision detection is therefore impossible in hardware. Wireless protocols discover collisions *after* the fact by waiting for an ACK and timing out.

### The hidden terminal problem

```
[A] -----R-----> [B] <-----R----- [C]
 ^                                    ^
 |--- can hear B ---|                 |
                     \--- CANNOT HEAR A ---/
```

A and C both want to send to B. A starts transmitting. C senses the medium — silent, because C is out of A's range. C transmits, B receives both, both are garbled. A's transmission *was* a valid signal at A; C's deferral decision was made on the wrong signal. The protocol needs a way for B to advertise "I am about to receive a long frame, stay quiet."

### The exposed terminal problem

```
[B] -----R-----> [A]   C -----R-----> [D]
 ^                              ^
 |--- transmits to A           |--- wants to send to D
 \--- C defers because it senses B ---/
```

B transmits to A. C wants to send to D. C senses the medium — busy (B is in C's range). C defers. But C's transmission to D would not collide with B's transmission to A: the two pairs are out of each other's reception range. The deferral is wasted capacity. The protocol needs to let C know that the *receiver* of interest (D) is idle.

### MACA: the two-frame handshake

MACA (Karn 1990) replaces carrier sense with a *receiver-driven* handshake. The sender stimulates the receiver to advertise the upcoming transmission, so any station that can hear the receiver knows to defer.

1. **A** sends a 30-byte **RTS** to B, containing the length of the data frame to follow.
2. **B** replies with a 30-byte **CTS** to A, echoing the length.
3. **A** transmits the data frame.
4. (Optional, in MACAW) B sends an ACK.

Each control frame triggers a *directional* deferral:

| Frame overheard | Heard by | Deferral |
|---|---|---|
| RTS | Stations in range of A (sender) | For long enough that the CTS can return to A without conflict |
| CTS | Stations in range of B (receiver) | For the entire data frame, whose length is in the CTS |
| Data | Stations in range of A | Implicit, they're already deferring from the RTS |
| ACK | Stations in range of B | Implicit, they already deferred for the data frame |

Now look at the four-station figure:

- **A → B**: A sends RTS. B replies CTS. A transmits data.
- **C** (range of A, not B): hears RTS, defers for the CTS window only. As soon as the CTS would have been heard, C is free to transmit. C does not know the data is coming because it is not in B's range.
- **D** (range of B, not A): does not hear the RTS, but hears the CTS. D now knows a frame is coming to B for the duration announced in the CTS; D defers for the whole data frame.
- **E** (range of both A and B): hears both, defers through to the end of the data.

The result: hidden terminals (which can hear the receiver) hear the CTS and back off. Exposed terminals (which hear the sender but not the receiver) hear only the RTS and may transmit.

### MACAW and 802.11 refinements

MACAW (Bharghavan 1994) added three things: a per-frame ACK so the sender discovers a collision at the receiver, an RRDT (Request-Ready-To-Send) so the receiver can flow-control the sender, and a per-link retry counter visible to both ends. 802.11 (WiFi) uses the same RTS/CTS structure with these refinements and adds:

- CSMA/CA *and* RTS/CTS (RTS/CTS is optional but used for large frames)
- Per-frame ACK at the end of every unicast data frame
- Network Allocation Vector (NAV) — virtual carrier sense based on the Duration field
- Exponential backoff after a missed ACK, doubling the contention window

The structure of the lesson is the MACA handshake; the structure of 802.11 is what you would build next.

### Limits of MACA

MACA does not solve *all* wireless problems. Two stations can still collide on their RTS — both go quiet, both retry, and exponential backoff is the only defence. The protocol also assumes a single channel (no CDMA). Modern WiFi adds OFDMA, MIMO, and beamforming that change the radio-range model entirely, but RTS/CTS still appears in 802.11ax for spatial-reuse scenarios.

## Build It

`code/main.py` ships two stdlib-only tools:

1. **Radio-range simulator** — places N stations on a 2D grid, lets you mark which pairs are in range of which. A transmission from A to B collides at B if any other station in B's range transmits at the same time. The simulator enumerates concurrent transmissions that are safe and reports hidden/exposed terminal pairs.
2. **MACA handshake tracer** — given a four-station geometry from the chapter, simulates a MACA handshake between A and B, prints the RTS/CTS/data timing, and lists which stations defer and for how long.

Run `python3 code/main.py` and inspect the deferral table; try removing the CTS step and watch the hidden-terminal collision return.

## Use It

| Task | Evidence | What Good Looks Like |
|---|---|---|
| Diagnose phantom stops in a WiFi AGV fleet | AP logs, RSSI map | You identify hidden terminals at aisle ends, not RF noise |
| Decide whether to enable RTS/CTS | Frame size, cell density | Large frames or dense cells -> enable; small/VoIP frames -> leave off (overhead) |
| Trace a MACA handshake | Frame timestamps | You identify the RTS, CTS, data, ACK windows and the directional deferrals |
| Test concurrency | Two simultaneous pairs | You prove the pairs are non-interfering and the MAC permits them |
| Tune RTS threshold | Frame size distribution | You set the threshold so the RTS/CTS overhead is amortised on large frames |

Wireshark filter: `wlan.fc.type == 1 && wlan.fc.subtype in {11, 12}` shows RTS and CTS frames in an 802.11 capture.

## Ship It

Produce one reusable artifact under `outputs/`:

- A **range diagram** of the four-station geometry, with arrows showing the deferral rules per frame.
- A **MACA handshake trace** with timestamps (in slot units) showing when each station transmits, defers, and resumes.
- A **WiFi tuning note** explaining when to enable 802.11 RTS/CTS in a production AP and how to set the threshold.

Start from `outputs/prompt-maca-wireless-hidden-exposed-terminals.md`.

## Exercises

1. Draw the four-station figure (A, B, C, D with the ranges in §4.2.5). Mark the two cases in which CSMA defers unnecessarily and the case in which CSMA fails to defer when it should.
2. With A transmitting RTS at time 0 to B at 100 m, the RTS is 30 bytes at 1 Mbps, propagation 5 us, and CTS turnaround at B is 20 us. When does C (in range of A) finish its deferral, and when does D (in range of B) finish its deferral?
3. Run `code/main.py`'s radio-range simulator with stations A=(0,0), B=(50,0), C=(100,0), D=(150,0) and a range of 75 m. Which pairs can transmit simultaneously? Is the AGV hidden-terminal case reproduced?
4. Why does the chapter's MACA not include an ACK in the original Karn 1990 paper, and what does MACAW add to fix the gap? What does 802.11 add on top of MACAW?
5. The 802.11 RTS threshold defaults to 500 bytes. Frames smaller than this skip the RTS/CTS handshake. Why is this a sensible default, and what is the trade-off?
6. Sketch the timing of a successful 802.11 RTS/CTS/data/ACK exchange between AP and client, including DIFS, SIFS, and the NAV updates. Identify which stations defer for which intervals.

## Key Terms

| Term | What people say | What it actually means |
|---|---|---|
| Hidden terminal | "can't sense the other sender" | A station whose transmission collides at a receiver because a third station (out of the sender's range) is also transmitting |
| Exposed terminal | "sensed someone irrelevant" | A station that defers unnecessarily because it senses a transmission that would not collide with its own at the intended receiver |
| RTS | "Request To Send" | A 30-byte control frame sent by the data sender to the receiver, containing the future data frame length |
| CTS | "Clear To Send" | A 30-byte control frame sent by the receiver in response to RTS, echoing the length so neighbours of the receiver know to defer |
| MACA | "Karn 1990" | Multiple Access with Collision Avoidance — the two-frame (RTS/CTS) handshake that replaces carrier sense for wireless |
| MACAW | "Bharghavan 1994" | MACA for Wireless LAN — adds per-frame ACK, RRDT flow control, and a per-link retry counter |
| NAV | "virtual carrier sense" | Network Allocation Vector — a per-station timer set from the Duration field of overheard frames, used to defer transmissions |
| Receiver-side interference | "what matters is at the receiver" | Wireless MAC's defining constraint: carrier sense at the sender is not the same as a clear channel at the receiver |

## Further Reading

- **Tanenbaum & Wetherall, *Computer Networks* (5th ed.), §4.2.5 "Wireless LAN Protocols"** — the source chapter.
- **Karn, P. (1990), "MACA — A New Channel Access Method for Packet Radio," *ARRL/CRRL Amateur Radio 9th Computer Networking Conference*** — the original MACA paper.
- **Bharghavan, V. et al. (1994), "MACAW: A Media Access Protocol for Wireless LAN's," *SIGCOMM '94*** — adds ACK and per-link state.
- **IEEE 802.11-2020, §9.3 "MAC sublayer functional description"** — the modern refinement: DCF, RTS/CTS, NAV, exponential backoff.
- **Xu, K. et al. (2003), "Revealing the Hidden Terminal Problem in 802.11," *MobiCom '03*** — the modern hidden-terminal measurements that motivate RTS/CTS in dense cells.
- **L. Kleinrock & F. Tobagi, "Packet Switching in Radio Channels: Part III" (1975)** — the foundational carrier-sense and hidden-terminal analysis that predates WiFi by two decades.
